"""
Event Handler Lambda - 处理 Security Hub 事件并触发 Phase 1 分析

Phase 1: 接收 Finding → 创建任务 → 调用 Analyzer Agent → 发送审批邮件
"""
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


def convert_floats_to_decimals(obj):
    """递归转换字典/列表中的 float 为 Decimal，用于 DynamoDB 兼容性"""
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: convert_floats_to_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimals(item) for item in obj]
    return obj

# 配置日志
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# 环境变量
TASKS_TABLE = os.environ.get('TASKS_TABLE', 'shara-dev-tasks')
TOKENS_TABLE = os.environ.get('TOKENS_TABLE', 'shara-dev-approval-tokens')
ASR_PLAYBOOKS_BUCKET = os.environ.get('ASR_PLAYBOOKS_BUCKET', 'shara-dev-asr-playbooks-870414140965')
MEMORY_ID = os.environ.get('AGENTCORE_MEMORY_ID', '')
ANALYZER_RUNTIME_ARN = os.environ.get('ANALYZER_RUNTIME_ARN', '')  # Analyzer Agent Runtime ARN
STAGE = os.environ.get('STAGE', 'dev')
REGION = os.environ.get('AWS_REGION', 'us-east-1')
# GitHub 配置 (用于容器漏洞修复)
GITHUB_OWNER = os.environ.get('GITHUB_OWNER', 'Wyifei')  # GitHub 用户名/组织名
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'awsome')  # GitHub 仓库名 (直接指定，避免动态搜索)
APPROVAL_EMAIL = os.environ.get('APPROVAL_EMAIL', '')  # 审批者邮箱
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', '')  # 发件人邮箱
API_GATEWAY_URL = os.environ.get('API_GATEWAY_URL', '')  # API Gateway URL
APPROVAL_EXPIRY_HOURS = int(os.environ.get('APPROVAL_EXPIRY_HOURS', '24'))
# Inspector 扫描等待时间（秒）- 等待 Inspector 完成全部漏洞扫描
INSPECTOR_SCAN_WAIT_SECONDS = int(os.environ.get('INSPECTOR_SCAN_WAIT_SECONDS', '30'))

# DynamoDB 资源
dynamodb = boto3.resource('dynamodb', region_name=REGION)
tasks_table = dynamodb.Table(TASKS_TABLE)
tokens_table = dynamodb.Table(TOKENS_TABLE)

# SES 客户端
ses_client = boto3.client('ses', region_name=REGION)

# Inspector 客户端 (用于容器漏洞聚合)
inspector_client = boto3.client('inspector2', region_name=REGION)


def lambda_handler(event: dict, context) -> dict:
    """
    Lambda 入口函数

    Args:
        event: EventBridge Security Hub Finding 事件或 API Gateway 事件
        context: Lambda 上下文

    Returns:
        dict: 响应结果
    """
    logger.info(f"Received event: {json.dumps(event)}")

    try:
        # 判断事件来源
        if 'detail' in event and 'findings' in event.get('detail', {}):
            # EventBridge Security Hub 事件
            return handle_security_hub_event(event, context)
        elif 'httpMethod' in event:
            # API Gateway 事件
            return handle_api_request(event, context)
        else:
            logger.warning(f"Unknown event type: {event}")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Unknown event type'})
            }

    except Exception as e:
        logger.exception(f"Error processing event: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def handle_security_hub_event(event: dict, context) -> dict:
    """处理 Security Hub Finding 事件"""
    findings = event.get('detail', {}).get('findings', [])

    if not findings:
        logger.info("No findings in event")
        return {'statusCode': 200, 'body': json.dumps({'message': 'No findings'})}

    results = []
    for finding in findings:
        try:
            result = process_finding(finding, context)
            results.append(result)
        except Exception as e:
            logger.exception(f"Error processing finding: {e}")
            results.append({
                'finding_id': finding.get('Id', 'unknown'),
                'error': str(e)
            })

    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': f'Processed {len(results)} findings',
            'results': results
        })
    }


def classify_finding(finding: dict) -> dict:
    """
    分类 Finding 类型，返回分类信息

    Args:
        finding: Security Hub Finding (ASFF 格式)

    Returns:
        dict: 分类信息
            {
                "type": "FSBP_CONTROL" | "CONTAINER_CVE" | "EC2_CVE" | "UNSUPPORTED",
                "control_id": "S3.1" | "CVE-2025-xxxxx" | None,
                "resource_type": "AwsS3Bucket" | "AwsEcrContainerImage" | "AwsEc2Instance",
                "can_remediate": True | False,
                "reason": "..."
            }
    """
    resources = finding.get('Resources', [])
    resource = resources[0] if resources else {}
    resource_type = resource.get('Type', '')

    # 检查 ProductName 来识别 Inspector findings
    product_name = finding.get('ProductName', '')
    generator_id = finding.get('GeneratorId', '')

    # Inspector CVE findings 的特征
    is_inspector = 'Inspector' in product_name or 'inspector' in generator_id.lower()

    if is_inspector:
        # 提取 CVE ID
        cve_id = None
        vulnerabilities = finding.get('Vulnerabilities', [])
        if vulnerabilities:
            cve_id = vulnerabilities[0].get('Id', '')

        # 如果没有 Vulnerabilities 字段，尝试从 Title 提取
        if not cve_id:
            title = finding.get('Title', '')
            cve_match = re.search(r'(CVE-\d{4}-\d+)', title)
            if cve_match:
                cve_id = cve_match.group(1)

        if resource_type == 'AwsEcrContainerImage':
            return {
                'type': 'CONTAINER_CVE',
                'control_id': cve_id,
                'resource_type': resource_type,
                'can_remediate': False,
                'reason': 'Container image vulnerabilities require developer team to update the image'
            }
        elif resource_type == 'AwsEc2Instance':
            return {
                'type': 'EC2_CVE',
                'control_id': cve_id,
                'resource_type': resource_type,
                'can_remediate': False,
                'reason': 'EC2 software vulnerabilities require manual patching'
            }
        else:
            # 其他 Inspector findings (如 Lambda 漏洞)
            return {
                'type': 'UNSUPPORTED',
                'control_id': cve_id,
                'resource_type': resource_type,
                'can_remediate': False,
                'reason': f'Unsupported Inspector finding type for resource: {resource_type}'
            }

    # FSBP Control findings
    control_id = extract_control_id(finding)
    if control_id:
        return {
            'type': 'FSBP_CONTROL',
            'control_id': control_id,
            'resource_type': resource_type,
            'can_remediate': True,
            'reason': None
        }

    # 无法分类
    return {
        'type': 'UNSUPPORTED',
        'control_id': None,
        'resource_type': resource_type,
        'can_remediate': False,
        'reason': 'Could not classify finding type'
    }


def extract_cve_details(finding: dict) -> dict:
    """
    从 Inspector Finding 提取 CVE 详情

    Args:
        finding: Security Hub Finding (ASFF 格式)

    Returns:
        dict: CVE 详情
            {
                "cve_id": "CVE-2025-xxxxx",
                "severity": "CRITICAL",
                "cvss_score": 9.8,
                "package_name": "openssl",
                "current_version": "3.5.4",
                "fixed_version": "3.5.4-1~deb13u2",
                "remediation_command": "apt-get update && apt-get upgrade",
                "reference_urls": [...],
                "exploit_available": True/False,
                "description": "..."
            }
    """
    vulnerabilities = finding.get('Vulnerabilities', [])
    vuln = vulnerabilities[0] if vulnerabilities else {}

    # 提取 CVE ID
    cve_id = vuln.get('Id', '')
    if not cve_id:
        title = finding.get('Title', '')
        cve_match = re.search(r'(CVE-\d{4}-\d+)', title)
        if cve_match:
            cve_id = cve_match.group(1)

    # 提取严重性
    severity = finding.get('Severity', {}).get('Label', 'UNKNOWN')

    # 提取 CVSS 分数
    cvss_score = 0.0
    cvss_list = vuln.get('Cvss', [])
    if cvss_list:
        # 优先使用 CVSS v3
        for cvss in cvss_list:
            if cvss.get('Version', '').startswith('3'):
                cvss_score = cvss.get('BaseScore', 0.0)
                break
        if cvss_score == 0.0 and cvss_list:
            cvss_score = cvss_list[0].get('BaseScore', 0.0)

    # 提取受影响的包信息
    vulnerable_packages = vuln.get('VulnerablePackages', [])
    package = vulnerable_packages[0] if vulnerable_packages else {}
    package_name = package.get('Name', 'Unknown')
    current_version = package.get('Version', 'Unknown')
    fixed_version = package.get('FixedInVersion', 'Not available')
    remediation_command = package.get('Remediation', '')

    # 如果没有修复命令，根据包管理器生成建议
    if not remediation_command:
        pkg_manager = package.get('PackageManager', '')
        if pkg_manager in ['APT', 'DPKG']:
            remediation_command = f'apt-get update && apt-get upgrade {package_name}'
        elif pkg_manager in ['YUM', 'RPM']:
            remediation_command = f'yum update {package_name}'
        elif pkg_manager == 'APKG':
            remediation_command = f'apk upgrade {package_name}'
        else:
            remediation_command = f'Update {package_name} to version {fixed_version}'

    # 提取参考链接
    reference_urls = vuln.get('ReferenceUrls', [])

    # 检查是否有公开利用
    exploit_available = vuln.get('ExploitAvailable', 'NO') == 'YES'

    # 提取描述
    description = finding.get('Description', '')

    return {
        'cve_id': cve_id,
        'severity': severity,
        'cvss_score': cvss_score,
        'package_name': package_name,
        'current_version': current_version,
        'fixed_version': fixed_version,
        'remediation_command': remediation_command,
        'reference_urls': reference_urls,
        'exploit_available': exploit_available,
        'description': description
    }


def get_container_findings(
    repo_name: str,
    image_tag: str,
    image_digest: str,
    registry_id: str
) -> list:
    """获取指定容器镜像的所有 HIGH/CRITICAL 漏洞。

    调用 Inspector list_findings API，按镜像 digest 筛选漏洞。

    Args:
        repo_name: ECR 仓库名称 (如 "shara-analyzer")
        image_tag: 镜像标签 (如 "v1.2.3")
        image_digest: 镜像摘要 (如 "sha256:abc123...")
        registry_id: ECR 注册表 ID (即 AWS 账户 ID)

    Returns:
        list: 漏洞列表，每个漏洞包含:
            {
                "cve_id": "CVE-2024-1234",
                "severity": "CRITICAL",
                "cvss_score": 9.8,
                "package_name": "requests",
                "current_version": "2.28.0",
                "fixed_version": "2.31.0",
                "package_manager": "pip",
                "exploit_available": True/False,
                "description": "..."
            }
    """
    logger.info(f"Fetching Inspector findings for {repo_name}:{image_tag}")
    logger.info(f"Filter: repo={repo_name}, digest={image_digest}")

    vulnerabilities = []
    next_token = None

    try:
        # 构建筛选条件
        # 注意: Inspector API 的 ecrImageHash 需要完整的 sha256:xxx 格式
        filter_criteria = {
            # 按镜像仓库和 digest 筛选
            'ecrImageRepositoryName': [{'comparison': 'EQUALS', 'value': repo_name}],
            'ecrImageHash': [{'comparison': 'EQUALS', 'value': image_digest}],
            # 只获取 HIGH 和 CRITICAL 级别
            'severity': [
                {'comparison': 'EQUALS', 'value': 'CRITICAL'},
                {'comparison': 'EQUALS', 'value': 'HIGH'}
            ],
            # 只获取容器漏洞
            'findingType': [{'comparison': 'EQUALS', 'value': 'PACKAGE_VULNERABILITY'}],
            'resourceType': [{'comparison': 'EQUALS', 'value': 'AWS_ECR_CONTAINER_IMAGE'}]
        }

        logger.info(f"Inspector filter criteria: {json.dumps(filter_criteria)}")

        while True:
            # 调用 Inspector API
            params = {
                'filterCriteria': filter_criteria,
                'maxResults': 100  # 每页最多 100 条
            }
            if next_token:
                params['nextToken'] = next_token

            response = inspector_client.list_findings(**params)

            # 处理响应
            findings_in_page = response.get('findings', [])
            logger.info(f"Inspector API returned {len(findings_in_page)} findings in this page")

            for finding in findings_in_page:
                vuln = extract_vulnerability_from_inspector_finding(finding)
                if vuln:
                    vulnerabilities.append(vuln)
                else:
                    # 记录被过滤掉的 finding 以便调试
                    finding_arn = finding.get('findingArn', 'unknown')
                    vuln_id = finding.get('packageVulnerabilityDetails', {}).get('vulnerabilityId', 'N/A')
                    logger.debug(f"Filtered out finding: {finding_arn}, vuln_id: {vuln_id}")

            # 检查是否有更多结果
            next_token = response.get('nextToken')
            logger.info(f"Next token: {'present' if next_token else 'none'}")
            if not next_token:
                break

        logger.info(f"Found {len(vulnerabilities)} HIGH/CRITICAL vulnerabilities for {repo_name}:{image_tag}")
        return vulnerabilities

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        logger.error(f"Inspector API error ({error_code}): {e}")
        raise
    except Exception as e:
        logger.exception(f"Error fetching Inspector findings: {e}")
        raise


def extract_vulnerability_from_inspector_finding(finding: dict) -> Optional[dict]:
    """从 Inspector Finding 提取漏洞信息。

    Args:
        finding: Inspector Finding (Inspector API 格式，非 ASFF)

    Returns:
        dict: 漏洞信息，或 None (如果无法提取)
    """
    try:
        # Inspector API 返回的结构与 Security Hub ASFF 不同
        # 参考: https://docs.aws.amazon.com/inspector/latest/user/findings-understanding.html

        # 提取 CVE ID - 支持多种格式 (CVE-, GHSA-, etc.)
        vulnerability_id = finding.get('packageVulnerabilityDetails', {}).get('vulnerabilityId', '')
        if not vulnerability_id:
            # 尝试从 title 提取
            vulnerability_id = finding.get('title', '')
            logger.debug(f"No vulnerabilityId, using title: {vulnerability_id}")

        if not vulnerability_id:
            logger.warning(f"Skipping finding without vulnerability ID: {finding.get('findingArn', 'unknown')}")
            return None

        # 提取严重性
        severity = finding.get('severity', 'UNKNOWN')

        # 提取 CVSS 分数
        cvss_score = 0.0
        cvss_list = finding.get('packageVulnerabilityDetails', {}).get('cvss', [])
        for cvss in cvss_list:
            # 优先使用 CVSS v3
            if cvss.get('version', '').startswith('3'):
                cvss_score = cvss.get('baseScore', 0.0)
                break
        if cvss_score == 0.0 and cvss_list:
            cvss_score = cvss_list[0].get('baseScore', 0.0)

        # 提取受影响的包信息
        vulnerable_packages = finding.get('packageVulnerabilityDetails', {}).get('vulnerablePackages', [])
        if not vulnerable_packages:
            logger.debug(f"No vulnerablePackages for {vulnerability_id}, using defaults")
            package_name = 'Unknown'
            current_version = 'Unknown'
            fixed_version = 'Not available'
            package_manager = 'Unknown'
        else:
            package = vulnerable_packages[0]
            package_name = package.get('name', 'Unknown')
            current_version = package.get('version', 'Unknown')
            fixed_version = package.get('fixedInVersion', 'Not available')
            package_manager = package.get('packageManager', 'Unknown')

        # 检查是否有公开利用
        exploit_available = finding.get('exploitAvailable', 'NO') == 'YES'

        # 提取描述
        description = finding.get('description', '')

        return {
            'cve_id': vulnerability_id,
            'severity': severity,
            'cvss_score': cvss_score,
            'package_name': package_name,
            'current_version': current_version,
            'fixed_version': fixed_version,
            'package_manager': package_manager.lower(),
            'exploit_available': exploit_available,
            'description': description
        }

    except Exception as e:
        logger.warning(f"Error extracting vulnerability from Inspector finding: {e}")
        return None


def aggregate_vulnerabilities(vulnerabilities: list) -> dict:
    """聚合漏洞信息，生成摘要。

    Args:
        vulnerabilities: 漏洞列表

    Returns:
        dict: 聚合结果
            {
                "vulnerabilities": [...],  # 去重后的漏洞列表
                "summary": {
                    "total": 5,
                    "critical": 2,
                    "high": 3
                },
                "packages_affected": ["requests", "urllib3"],
                "package_managers": ["pip"]
            }
    """
    # 按 CVE ID 去重
    seen_cves = set()
    unique_vulns = []
    critical_count = 0
    high_count = 0
    packages_affected = set()
    package_managers = set()

    for vuln in vulnerabilities:
        cve_id = vuln.get('cve_id', '')
        if cve_id and cve_id not in seen_cves:
            seen_cves.add(cve_id)
            unique_vulns.append(vuln)

            severity = vuln.get('severity', '')
            if severity == 'CRITICAL':
                critical_count += 1
            elif severity == 'HIGH':
                high_count += 1

            packages_affected.add(vuln.get('package_name', ''))
            pkg_manager = vuln.get('package_manager', '')
            if pkg_manager:
                package_managers.add(pkg_manager)

    # 按严重性排序 (CRITICAL 优先)
    unique_vulns.sort(key=lambda x: (0 if x.get('severity') == 'CRITICAL' else 1, -x.get('cvss_score', 0)))

    return {
        'vulnerabilities': unique_vulns,
        'summary': {
            'total': len(unique_vulns),
            'critical': critical_count,
            'high': high_count
        },
        'packages_affected': list(packages_affected),
        'package_managers': list(package_managers)
    }


def process_finding(finding: dict, context) -> dict:
    """处理单个 Finding

    Args:
        finding: Security Hub Finding (ASFF 格式)
        context: Lambda 上下文

    Returns:
        dict: 处理结果
    """
    finding_id = finding.get('Id', '')
    severity = finding.get('Severity', {}).get('Label', 'MEDIUM')

    # 只处理 HIGH 和 CRITICAL 级别
    if severity not in ['HIGH', 'CRITICAL']:
        logger.info(f"Skipping finding {finding_id} with severity {severity}")
        return {
            'finding_id': finding_id,
            'status': 'skipped',
            'reason': f'Severity {severity} not in scope'
        }

    # 分类 Finding
    classification = classify_finding(finding)
    logger.info(f"Finding {finding_id} classified as: {classification['type']}")

    if classification['type'] == 'FSBP_CONTROL':
        # 原有流程: 调用 Analyzer Agent
        return process_fsbp_finding(finding, classification, context)

    elif classification['type'] in ['CONTAINER_CVE', 'EC2_CVE']:
        # 新流程: 直接处理 CVE，不调用 Agent
        return process_cve_finding(finding, classification, context)

    else:
        # 跳过不支持的类型
        logger.warning(f"Skipping unsupported finding type: {classification['type']}")
        return {
            'finding_id': finding_id,
            'status': 'skipped',
            'reason': classification.get('reason', 'Unsupported finding type')
        }


def process_fsbp_finding(finding: dict, classification: dict, context) -> dict:
    """处理 FSBP Control Finding（原有逻辑）

    Args:
        finding: Security Hub Finding (ASFF 格式)
        classification: 分类信息
        context: Lambda 上下文

    Returns:
        dict: 处理结果
    """
    finding_id = finding.get('Id', '')
    severity = finding.get('Severity', {}).get('Label', 'MEDIUM')
    control_id = classification['control_id']

    # 检查是否已存在该 Finding 的 task（24小时内未过期）
    existing_tasks = tasks_table.query(
        IndexName='GSI2',
        KeyConditionExpression='GSI2PK = :pk',
        ExpressionAttributeValues={':pk': f'FINDING#{finding_id}'},
        Limit=1
    )
    if existing_tasks.get('Items'):
        existing_task = existing_tasks['Items'][0]
        logger.info(f"Skipping duplicate finding {finding_id}, existing task: {existing_task.get('taskId')}")
        return {
            'finding_id': finding_id,
            'status': 'skipped',
            'reason': 'duplicate',
            'existing_task_id': existing_task.get('taskId')
        }

    # 创建任务
    task_id = str(uuid.uuid4())
    memory_session_id = f"session-task-{task_id}"

    # 提取资源信息
    resources = finding.get('Resources', [])
    resource = resources[0] if resources else {}

    now = datetime.now(timezone.utc).isoformat()

    # 计算 TTL (与审批链接有效期一致)
    task_ttl = int((datetime.now(timezone.utc) + timedelta(hours=APPROVAL_EXPIRY_HOURS)).timestamp())

    task_item = {
        # Keys
        'PK': f'TASK#{task_id}',
        'SK': 'METADATA',
        'GSI1PK': 'STATUS#pending',
        'GSI1SK': now,
        'GSI2PK': f'FINDING#{finding_id}',
        'GSI2SK': now,
        'GSI3PK': f'ACCOUNT#{finding.get("AwsAccountId", "")}',
        'GSI3SK': now,

        # 核心控制字段
        'taskId': task_id,
        'findingId': finding_id,
        'controlId': control_id,
        'findingType': 'FSBP_CONTROL',  # 标记为 FSBP Control
        'remediationType': 'aws_api',   # 修复类型: AWS API 调用
        'status': 'pending',
        'phase': 'pre_approval',
        'severity': severity,

        # 资源标识
        'resourceType': resource.get('Type', ''),
        'resourceId': resource.get('Id', ''),
        'awsAccountId': finding.get('AwsAccountId', ''),
        'region': finding.get('Region', REGION),

        # Agent 会话
        'memorySessionId': memory_session_id,
        'actorId': finding.get('AwsAccountId', ''),  # Memory actor_id (AWS Account ID)

        # 元数据
        'createdAt': now,
        'updatedAt': now,
        'version': 1,
        'traceId': context.aws_request_id if context else None,

        # TTL - 与审批链接有效期一致 (24小时)
        'ttl': task_ttl
    }

    # 设置初始状态为 analyzing
    task_item['status'] = 'analyzing'
    task_item['GSI1PK'] = 'STATUS#analyzing'

    # 保存任务
    tasks_table.put_item(Item=task_item)
    logger.info(f"Created task {task_id} for FSBP finding {finding_id}")

    # 调用 Analyzer Agent (Phase 1)
    # 使用 AWS Account ID 作为 actor_id，确保同账户的修复经验可以共享
    actor_id = finding.get('AwsAccountId', '')

    try:
        analysis_result = run_phase1_analysis(
            task_id=task_id,
            finding=finding,
            control_id=control_id,
            memory_session_id=memory_session_id,
            actor_id=actor_id
        )

        if analysis_result.get('success'):
            # 更新任务状态和分析结果，并发送审批邮件
            update_task_with_analysis(task_id, analysis_result)

            return {
                'finding_id': finding_id,
                'task_id': task_id,
                'status': 'waiting_approval',
                'control_id': control_id
            }
        else:
            update_task_status(task_id, 'analysis_failed', {
                'error': analysis_result.get('error', 'Unknown error')
            })
            return {
                'finding_id': finding_id,
                'task_id': task_id,
                'status': 'analysis_failed',
                'error': analysis_result.get('error')
            }

    except Exception as e:
        logger.exception(f"Analysis failed for task {task_id}: {e}")
        update_task_status(task_id, 'analysis_failed', {'error': str(e)})
        return {
            'finding_id': finding_id,
            'task_id': task_id,
            'status': 'analysis_failed',
            'error': str(e)
        }


def process_cve_finding(finding: dict, classification: dict, context) -> dict:
    """处理 CVE 漏洞 Finding (容器/EC2)

    - 容器镜像漏洞 (CONTAINER_CVE): 调用 Analyzer Agent 自动修复
    - EC2 软件漏洞 (EC2_CVE): 发送通知邮件 (手动修复)

    Args:
        finding: Security Hub Finding (ASFF 格式)
        classification: 分类信息
        context: Lambda 上下文

    Returns:
        dict: 处理结果
    """
    finding_id = finding.get('Id', '')
    finding_type = classification['type']  # CONTAINER_CVE or EC2_CVE

    # 容器漏洞: 走自动修复流程
    if finding_type == 'CONTAINER_CVE':
        return process_container_cve_finding(finding, classification, context)

    # EC2 漏洞: 走通知流程 (保持原有行为)
    return process_ec2_cve_finding(finding, classification, context)


def process_container_cve_finding(finding: dict, classification: dict, context) -> dict:
    """处理容器镜像漏洞 Finding - 调用 Analyzer Agent 自动修复

    流程:
    1. 提取容器镜像信息 (ECR repo, tag, digest)
    2. 调用 Inspector API 获取该镜像所有 HIGH/CRITICAL 漏洞
    3. 聚合漏洞并创建 Task (remediation_type: "github_pr")
    4. 调用 Analyzer Agent 进行分析

    Args:
        finding: Security Hub Finding (ASFF 格式)
        classification: 分类信息
        context: Lambda 上下文

    Returns:
        dict: 处理结果
    """
    finding_id = finding.get('Id', '')
    severity = finding.get('Severity', {}).get('Label', 'HIGH')

    # 提取资源信息
    resources = finding.get('Resources', [])
    resource = resources[0] if resources else {}
    resource_id = resource.get('Id', '')

    # 提取容器镜像详情
    container_details = extract_container_details(resource)
    if not container_details:
        logger.warning(f"Cannot extract container details from resource: {resource_id}")
        # 降级到通知流程
        return process_ec2_cve_finding(finding, classification, context)

    image_digest = container_details.get('image_digest', '')
    logger.info(f"Processing container CVE for {container_details['ecr_repository']}:{container_details['image_tag']} (digest: {image_digest[:20]}...)")

    # 按镜像 digest 去重 (24小时内同一镜像只处理一次)
    dedup_key = f"CVE_RESOURCE#CONTAINER_CVE#{image_digest}"
    existing_records = tasks_table.query(
        IndexName='GSI2',
        KeyConditionExpression='GSI2PK = :pk',
        ExpressionAttributeValues={':pk': dedup_key},
        Limit=1
    )

    if existing_records.get('Items'):
        existing_record = existing_records['Items'][0]
        logger.info(f"Skipping duplicate container CVE for image {image_digest[:20]}..., existing task: {existing_record.get('taskId')}")
        return {
            'finding_id': finding_id,
            'status': 'skipped',
            'reason': 'duplicate_image',
            'image_digest': image_digest,
            'existing_task_id': existing_record.get('taskId')
        }

    # 生成任务 ID 并立即创建占位记录，防止并发处理
    task_id = str(uuid.uuid4())
    memory_session_id = f"session-task-{task_id}"
    now = datetime.now(timezone.utc).isoformat()

    # 创建占位任务 (status: collecting)，让后续的 Lambda 能检测到去重
    try:
        tasks_table.put_item(
            Item={
                'PK': f'TASK#{task_id}',
                'SK': 'METADATA',
                'GSI1PK': 'STATUS#collecting',
                'GSI1SK': now,
                'GSI2PK': dedup_key,  # 关键：设置去重键
                'GSI2SK': now,
                'taskId': task_id,
                'findingId': finding_id,
                'findingType': 'CONTAINER_CVE',
                'status': 'collecting',  # 正在收集漏洞
                'phase': 'pre_approval',
                'container': convert_floats_to_decimals(container_details),
                'createdAt': now,
                'updatedAt': now,
            },
            ConditionExpression='attribute_not_exists(PK)'  # 确保不覆盖已有任务
        )
        logger.info(f"Created placeholder task {task_id} for image {image_digest[:20]}...")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            logger.info(f"Task already exists, skipping duplicate")
            return {
                'finding_id': finding_id,
                'status': 'skipped',
                'reason': 'duplicate_task_creation',
                'image_digest': image_digest
            }
        raise

    # 等待 Inspector 完成扫描
    # 当收到第一个漏洞 Finding 时，Inspector 可能还没扫描完所有漏洞
    # 等待一段时间可以确保获取到更完整的漏洞列表
    if INSPECTOR_SCAN_WAIT_SECONDS > 0:
        logger.info(f"Waiting {INSPECTOR_SCAN_WAIT_SECONDS}s for Inspector to complete scan...")
        time.sleep(INSPECTOR_SCAN_WAIT_SECONDS)

    # 调用 Inspector API 获取该镜像的所有漏洞
    try:
        all_vulns = get_container_findings(
            repo_name=container_details['ecr_repository'],
            image_tag=container_details['image_tag'],
            image_digest=image_digest,
            registry_id=container_details['registry_id']
        )
    except Exception as e:
        logger.exception(f"Failed to fetch Inspector findings: {e}")
        # 降级: 使用当前 finding 的单个漏洞
        cve_details = extract_cve_details(finding)
        all_vulns = [{
            'cve_id': cve_details['cve_id'],
            'severity': cve_details['severity'],
            'cvss_score': cve_details['cvss_score'],
            'package_name': cve_details['package_name'],
            'current_version': cve_details['current_version'],
            'fixed_version': cve_details['fixed_version'],
            'package_manager': 'unknown',
            'exploit_available': cve_details['exploit_available'],
            'description': cve_details['description']
        }]

    # 聚合漏洞
    aggregated = aggregate_vulnerabilities(all_vulns)

    if aggregated['summary']['total'] == 0:
        logger.info(f"No HIGH/CRITICAL vulnerabilities found for {container_details['ecr_repository']}:{container_details['image_tag']}")
        # 删除占位任务
        try:
            tasks_table.delete_item(Key={'PK': f'TASK#{task_id}', 'SK': 'METADATA'})
            logger.info(f"Deleted placeholder task {task_id} (no vulnerabilities found)")
        except Exception as e:
            logger.warning(f"Failed to delete placeholder task: {e}")
        return {
            'finding_id': finding_id,
            'status': 'skipped',
            'reason': 'no_vulnerabilities',
            'image_digest': image_digest
        }

    logger.info(f"Aggregated {aggregated['summary']['total']} vulnerabilities for container image")

    # 更新占位任务为完整任务 (task_id 和 memory_session_id 已在前面创建)
    now = datetime.now(timezone.utc).isoformat()
    task_ttl = int((datetime.now(timezone.utc) + timedelta(hours=APPROVAL_EXPIRY_HOURS)).timestamp())

    # 更新任务，添加漏洞数据
    tasks_table.update_item(
        Key={'PK': f'TASK#{task_id}', 'SK': 'METADATA'},
        UpdateExpression='''
            SET GSI1PK = :gsi1pk,
                GSI3PK = :gsi3pk,
                GSI3SK = :gsi3sk,
                remediationType = :remediation_type,
                #status = :status,
                severity = :severity,
                vulnerabilities = :vulnerabilities,
                vulnerabilitySummary = :vuln_summary,
                packagesAffected = :packages_affected,
                packageManagers = :package_managers,
                resourceType = :resource_type,
                resourceId = :resource_id,
                awsAccountId = :aws_account_id,
                #region = :region,
                memorySessionId = :memory_session_id,
                actorId = :actor_id,
                updatedAt = :updated_at,
                #version = :version,
                traceId = :trace_id,
                #ttl = :ttl
        ''',
        ExpressionAttributeNames={
            '#status': 'status',
            '#region': 'region',
            '#version': 'version',
            '#ttl': 'ttl'
        },
        ExpressionAttributeValues={
            ':gsi1pk': 'STATUS#analyzing',
            ':gsi3pk': f'ACCOUNT#{finding.get("AwsAccountId", "")}',
            ':gsi3sk': now,
            ':remediation_type': 'github_pr',
            ':status': 'analyzing',
            ':severity': severity,
            ':vulnerabilities': convert_floats_to_decimals(aggregated['vulnerabilities']),
            ':vuln_summary': convert_floats_to_decimals(aggregated['summary']),
            ':packages_affected': aggregated['packages_affected'],
            ':package_managers': aggregated['package_managers'],
            ':resource_type': resource.get('Type', ''),
            ':resource_id': resource_id,
            ':aws_account_id': finding.get('AwsAccountId', ''),
            ':region': finding.get('Region', REGION),
            ':memory_session_id': memory_session_id,
            ':actor_id': finding.get('AwsAccountId', ''),
            ':updated_at': now,
            ':version': 1,
            ':trace_id': context.aws_request_id if context else None,
            ':ttl': task_ttl
        }
    )
    logger.info(f"Updated container CVE task {task_id} with {aggregated['summary']['total']} vulnerabilities")

    # 调用 Analyzer Agent
    actor_id = finding.get('AwsAccountId', '')

    try:
        analysis_result = run_phase1_container_analysis(
            task_id=task_id,
            finding=finding,
            container_details=container_details,
            vulnerabilities=aggregated['vulnerabilities'],
            summary=aggregated['summary'],
            memory_session_id=memory_session_id,
            actor_id=actor_id
        )

        if analysis_result.get('success'):
            update_task_with_analysis(task_id, analysis_result)
            return {
                'finding_id': finding_id,
                'task_id': task_id,
                'status': 'waiting_approval',
                'remediation_type': 'github_pr',
                'vulnerabilities_count': aggregated['summary']['total']
            }
        else:
            update_task_status(task_id, 'analysis_failed', {
                'error': analysis_result.get('error', 'Unknown error')
            })
            return {
                'finding_id': finding_id,
                'task_id': task_id,
                'status': 'analysis_failed',
                'error': analysis_result.get('error')
            }

    except Exception as e:
        logger.exception(f"Container CVE analysis failed for task {task_id}: {e}")
        update_task_status(task_id, 'analysis_failed', {'error': str(e)})
        return {
            'finding_id': finding_id,
            'task_id': task_id,
            'status': 'analysis_failed',
            'error': str(e)
        }


def extract_container_details(resource: dict) -> Optional[dict]:
    """从 ASFF Resource 提取容器镜像详情。

    Args:
        resource: ASFF Resource 对象

    Returns:
        dict: 容器镜像详情，或 None
            {
                "ecr_repository": "shara-analyzer",
                "ecr_registry": "870414140965.dkr.ecr.ap-northeast-1.amazonaws.com",
                "image_tag": "v1.2.3",
                "image_digest": "sha256:abc123...",
                "registry_id": "870414140965"
            }
    """
    if resource.get('Type') != 'AwsEcrContainerImage':
        return None

    # 从 Details 中提取
    details = resource.get('Details', {}).get('AwsEcrContainerImage', {})

    # 从资源 ID 提取 (格式: arn:aws:ecr:region:account:repository/repo-name/image/sha256:digest)
    resource_id = resource.get('Id', '')

    # 提取 ECR 仓库名称
    repo_name = details.get('RepositoryName', '')
    if not repo_name and '/repository/' in resource_id:
        # 从 ARN 中提取完整的仓库路径
        # ARN 格式: arn:aws:ecr:region:account:repository/prefix/repo-name/image/sha256:digest
        # 需要提取 repository/ 和 /image/ 之间的所有内容
        after_repo = resource_id.split('/repository/')[-1]  # prefix/repo-name/image/sha256:xxx
        if '/image/' in after_repo:
            repo_name = after_repo.split('/image/')[0]  # prefix/repo-name
        else:
            # 兼容没有 /image/ 的格式
            parts = after_repo.split('/')
            if len(parts) >= 2:
                repo_name = '/'.join(parts[:-1])  # 去掉最后一段 (可能是 sha256)

    # 提取镜像标签
    image_tags = details.get('ImageTags', [])
    image_tag = image_tags[0] if image_tags else 'latest'

    # 提取镜像摘要
    image_digest = details.get('ImageDigest', '')
    if not image_digest:
        # 从 ARN 中提取 sha256:xxx
        if 'sha256:' in resource_id:
            image_digest = 'sha256:' + resource_id.split('sha256:')[1]

    # 提取注册表 ID (AWS 账户 ID)
    registry_id = details.get('RegistryId', '')
    if not registry_id:
        # 从 ARN 中提取 account ID
        arn_parts = resource_id.split(':')
        if len(arn_parts) >= 5:
            registry_id = arn_parts[4]

    # 构建注册表 URL
    region = resource_id.split(':')[3] if len(resource_id.split(':')) > 3 else REGION
    ecr_registry = f"{registry_id}.dkr.ecr.{region}.amazonaws.com"

    if not repo_name or not image_digest:
        return None

    return {
        'ecr_repository': repo_name,
        'ecr_registry': ecr_registry,
        'image_tag': image_tag,
        'image_digest': image_digest,
        'registry_id': registry_id
    }


def process_ec2_cve_finding(finding: dict, classification: dict, context) -> dict:
    """处理 EC2 软件漏洞 Finding - 发送通知邮件 (保持原有行为)

    Args:
        finding: Security Hub Finding (ASFF 格式)
        classification: 分类信息
        context: Lambda 上下文

    Returns:
        dict: 处理结果
    """
    finding_id = finding.get('Id', '')
    finding_type = classification['type']

    # 提取资源 ID
    resources = finding.get('Resources', [])
    resource = resources[0] if resources else {}
    resource_id = resource.get('Id', '')

    # 提取 CVE 详情
    cve_details = extract_cve_details(finding)

    logger.info(f"Processing EC2 CVE finding {finding_id} (cve: {cve_details['cve_id']}, resource: {resource_id})")

    # 按资源 ID 去重检查
    dedup_key = f"CVE_RESOURCE#{finding_type}#{resource_id}"
    existing_records = tasks_table.query(
        IndexName='GSI2',
        KeyConditionExpression='GSI2PK = :pk',
        ExpressionAttributeValues={':pk': dedup_key},
        Limit=1
    )

    if existing_records.get('Items'):
        existing_record = existing_records['Items'][0]
        logger.info(f"Skipping duplicate CVE for resource {resource_id}, existing record: {existing_record.get('taskId')}")
        return {
            'finding_id': finding_id,
            'status': 'skipped',
            'reason': 'duplicate_resource',
            'resource_id': resource_id,
            'existing_task_id': existing_record.get('taskId'),
            'cve_id': cve_details['cve_id']
        }

    # 创建去重记录
    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    task_ttl = int((datetime.now(timezone.utc) + timedelta(hours=APPROVAL_EXPIRY_HOURS)).timestamp())

    dedup_record = {
        'PK': f'TASK#{task_id}',
        'SK': 'METADATA',
        'GSI1PK': f'STATUS#cve_notified',
        'GSI1SK': now,
        'GSI2PK': dedup_key,
        'GSI2SK': now,
        'GSI3PK': f'ACCOUNT#{finding.get("AwsAccountId", "")}',
        'GSI3SK': now,

        'taskId': task_id,
        'findingId': finding_id,
        'findingType': finding_type,
        'remediationType': 'manual',  # 手动修复
        'status': 'cve_notified',
        'phase': 'notification',

        'resourceType': resource.get('Type', ''),
        'resourceId': resource_id,
        'awsAccountId': finding.get('AwsAccountId', ''),
        'region': finding.get('Region', REGION),

        'cveId': cve_details['cve_id'],
        'cveSeverity': cve_details['severity'],

        'createdAt': now,
        'updatedAt': now,
        'ttl': task_ttl,
        'traceId': context.aws_request_id if context else None
    }

    tasks_table.put_item(Item=dedup_record)
    logger.info(f"Created EC2 CVE dedup record {task_id} for resource {resource_id}")

    # 发送通知邮件
    email_sent = False
    try:
        email_sent = send_cve_notification_email(finding_id, finding, classification, cve_details)
        if email_sent:
            logger.info(f"CVE notification email sent for finding {finding_id}")
        else:
            logger.warning(f"Failed to send CVE notification email for finding {finding_id}")
    except Exception as e:
        logger.exception(f"Error sending CVE notification email for finding {finding_id}: {e}")

    return {
        'finding_id': finding_id,
        'task_id': task_id,
        'status': 'notified' if email_sent else 'notification_failed',
        'classification': finding_type,
        'resource_id': resource_id,
        'cve_id': cve_details['cve_id']
    }


def send_cve_notification_email(
    finding_id: str,
    finding: dict,
    classification: dict,
    cve_details: dict
) -> bool:
    """发送 CVE 通知邮件

    Args:
        finding_id: Finding ID
        finding: Security Hub Finding
        classification: 分类信息
        cve_details: CVE 详情

    Returns:
        bool: 是否发送成功
    """
    if not APPROVAL_EMAIL or not SENDER_EMAIL:
        logger.warning("APPROVAL_EMAIL or SENDER_EMAIL not configured, skipping email")
        return False

    try:
        # 格式化邮件内容
        email_body = format_cve_notification_email(finding_id, finding, classification, cve_details)

        # 构建邮件主题
        cve_id = cve_details['cve_id']
        severity = cve_details['severity']
        finding_type = classification['type']

        if finding_type == 'CONTAINER_CVE':
            type_label = '容器镜像漏洞'
        else:
            type_label = 'EC2 软件漏洞'

        email_subject = f'[SHARA] 🔴 {type_label}通知 - {cve_id} ({severity})'

        # 发送邮件 (HTML 格式)
        ses_client.send_email(
            Source=SENDER_EMAIL,
            Destination={'ToAddresses': [APPROVAL_EMAIL]},
            Message={
                'Subject': {
                    'Data': email_subject,
                    'Charset': 'UTF-8'
                },
                'Body': {
                    'Html': {
                        'Data': email_body,
                        'Charset': 'UTF-8'
                    }
                }
            }
        )

        logger.info(f"CVE notification email sent (HTML) for finding {finding_id}")
        return True

    except ClientError as e:
        logger.error(f"Failed to send CVE notification email: {e}")
        return False
    except Exception as e:
        logger.exception(f"Error sending CVE notification email: {e}")
        return False


def format_cve_notification_email(
    finding_id: str,
    finding: dict,
    classification: dict,
    cve_details: dict
) -> str:
    """格式化 CVE 通知邮件 (HTML 格式)

    Args:
        finding_id: Finding ID
        finding: Security Hub Finding
        classification: 分类信息
        cve_details: CVE 详情

    Returns:
        str: HTML 格式的邮件内容
    """
    finding_type = classification['type']
    resources = finding.get('Resources', [])
    resource = resources[0] if resources else {}

    # 严重性颜色和显示
    severity = cve_details['severity']
    severity_colors = {
        'CRITICAL': ('#dc3545', '🔴 CRITICAL'),
        'HIGH': ('#fd7e14', '🟠 HIGH'),
        'MEDIUM': ('#ffc107', '🟡 MEDIUM'),
        'LOW': ('#28a745', '🟢 LOW')
    }
    severity_color, severity_display = severity_colors.get(severity, ('#6c757d', f'⚪ {severity}'))

    # 漏洞类型
    if finding_type == 'CONTAINER_CVE':
        type_display = '🐳 容器镜像漏洞'
        type_icon = '🐳'
        responsible_team = 'DevOps / 开发团队'
    else:
        type_display = '🖥️ EC2 软件漏洞'
        type_icon = '🖥️'
        responsible_team = '运维 / SRE 团队'

    # 资源信息
    resource_id = resource.get('Id', 'N/A')
    resource_type = resource.get('Type', 'N/A')

    # 容器镜像额外信息
    container_row = ''
    if finding_type == 'CONTAINER_CVE' and '/' in resource_id:
        parts = resource_id.split('/')
        if len(parts) >= 2:
            repo_name = parts[-2] if len(parts) > 2 else parts[-1]
            container_row = f'<tr><td style="padding:8px;border-bottom:1px solid #eee;color:#666;">Repository</td><td style="padding:8px;border-bottom:1px solid #eee;"><code>{repo_name}</code></td></tr>'

    # 公开利用状态
    if cve_details['exploit_available']:
        exploit_html = '<span style="color:#dc3545;font-weight:bold;">⚠️ YES - 需紧急处理!</span>'
    else:
        exploit_html = '<span style="color:#28a745;">❌ NO</span>'

    # 漏洞描述（截断处理）
    description = cve_details.get('description', '')
    if len(description) > 500:
        description = description[:500] + '...'

    # 参考链接
    reference_urls = cve_details.get('reference_urls', [])
    reference_links_html = ''
    if reference_urls:
        links = ''.join([f'<li><a href="{url}" style="color:#0066cc;">{url}</a></li>' for url in reference_urls[:5]])
        if len(reference_urls) > 5:
            links += f'<li style="color:#666;">... 还有 {len(reference_urls) - 5} 个链接</li>'
        reference_links_html = f'''
        <div style="background:#f8f9fa;padding:15px;border-radius:8px;margin-top:20px;">
            <h3 style="margin:0 0 10px 0;color:#333;">📚 参考链接</h3>
            <ul style="margin:0;padding-left:20px;">{links}</ul>
        </div>
        '''

    # 修复步骤
    if finding_type == 'CONTAINER_CVE':
        remediation_steps = f'''
        <ol style="margin:10px 0;padding-left:20px;line-height:1.8;">
            <li>更新 Dockerfile 或基础镜像中的软件包</li>
            <li>执行: <code style="background:#f5f5f5;padding:2px 6px;border-radius:3px;">{cve_details["remediation_command"]}</code></li>
            <li>重新构建并推送镜像到 ECR</li>
            <li>重新部署使用该镜像的服务 (ECS/EKS/Lambda)</li>
            <li>在 Security Hub 中验证 Finding 已解决</li>
        </ol>
        '''
    else:
        remediation_steps = f'''
        <ol style="margin:10px 0;padding-left:20px;line-height:1.8;">
            <li>在测试环境验证补丁兼容性</li>
            <li>安排维护窗口 (建议在业务低峰期)</li>
            <li>执行: <code style="background:#f5f5f5;padding:2px 6px;border-radius:3px;">{cve_details["remediation_command"]}</code></li>
            <li>重启相关服务或实例</li>
            <li>验证服务正常运行</li>
            <li>在 Security Hub 中验证 Finding 已解决</li>
        </ol>
        '''

    # 构建 HTML
    html = f'''
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:0;padding:20px;background:#f5f5f5;">
<div style="max-width:700px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,0.1);">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,{severity_color},#333);color:#fff;padding:25px;text-align:center;">
        <div style="font-size:40px;margin-bottom:10px;">{type_icon}</div>
        <h1 style="margin:0;font-size:22px;">SHARA 安全漏洞通知</h1>
        <p style="margin:10px 0 0 0;opacity:0.9;">需要手动处理</p>
    </div>

    <!-- CVE Badge -->
    <div style="text-align:center;padding:20px;background:#f8f9fa;border-bottom:1px solid #eee;">
        <span style="display:inline-block;background:{severity_color};color:#fff;padding:8px 20px;border-radius:20px;font-weight:bold;font-size:16px;">
            {cve_details["cve_id"]} - {severity}
        </span>
    </div>

    <div style="padding:25px;">

        <!-- 基本信息 -->
        <h2 style="color:#333;border-bottom:2px solid #eee;padding-bottom:10px;margin-top:0;">📋 基本信息</h2>
        <table style="width:100%;border-collapse:collapse;margin-bottom:25px;">
            <tr><td style="padding:8px;border-bottom:1px solid #eee;color:#666;width:140px;">漏洞类型</td><td style="padding:8px;border-bottom:1px solid #eee;">{type_display}</td></tr>
            <tr><td style="padding:8px;border-bottom:1px solid #eee;color:#666;">CVSS 分数</td><td style="padding:8px;border-bottom:1px solid #eee;"><strong style="color:{severity_color};">{cve_details["cvss_score"]}</strong></td></tr>
            <tr><td style="padding:8px;border-bottom:1px solid #eee;color:#666;">是否有公开利用</td><td style="padding:8px;border-bottom:1px solid #eee;">{exploit_html}</td></tr>
        </table>

        <!-- 受影响资源 -->
        <h2 style="color:#333;border-bottom:2px solid #eee;padding-bottom:10px;">📦 受影响资源</h2>
        <table style="width:100%;border-collapse:collapse;margin-bottom:25px;">
            <tr><td style="padding:8px;border-bottom:1px solid #eee;color:#666;width:140px;">资源类型</td><td style="padding:8px;border-bottom:1px solid #eee;">{resource_type}</td></tr>
            <tr><td style="padding:8px;border-bottom:1px solid #eee;color:#666;">资源 ID</td><td style="padding:8px;border-bottom:1px solid #eee;word-break:break-all;"><code style="font-size:12px;">{resource_id}</code></td></tr>
            {container_row}
            <tr><td style="padding:8px;border-bottom:1px solid #eee;color:#666;">AWS 账户</td><td style="padding:8px;border-bottom:1px solid #eee;">{finding.get("AwsAccountId", "N/A")}</td></tr>
            <tr><td style="padding:8px;border-bottom:1px solid #eee;color:#666;">区域</td><td style="padding:8px;border-bottom:1px solid #eee;">{finding.get("Region", "N/A")}</td></tr>
        </table>

        <!-- 漏洞详情 -->
        <h2 style="color:#333;border-bottom:2px solid #eee;padding-bottom:10px;">🐛 漏洞详情</h2>
        <table style="width:100%;border-collapse:collapse;margin-bottom:15px;">
            <tr><td style="padding:8px;border-bottom:1px solid #eee;color:#666;width:140px;">受影响包</td><td style="padding:8px;border-bottom:1px solid #eee;"><code>{cve_details["package_name"]}</code></td></tr>
            <tr><td style="padding:8px;border-bottom:1px solid #eee;color:#666;">当前版本</td><td style="padding:8px;border-bottom:1px solid #eee;"><code>{cve_details["current_version"]}</code></td></tr>
            <tr><td style="padding:8px;border-bottom:1px solid #eee;color:#666;">修复版本</td><td style="padding:8px;border-bottom:1px solid #eee;"><code style="color:#28a745;">{cve_details["fixed_version"]}</code></td></tr>
        </table>
        <div style="background:#f8f9fa;padding:15px;border-radius:8px;margin-bottom:25px;">
            <strong style="color:#666;">漏洞描述:</strong>
            <p style="margin:10px 0 0 0;line-height:1.6;color:#333;">{description if description else "(无描述信息)"}</p>
        </div>

        <!-- 修复建议 -->
        <h2 style="color:#333;border-bottom:2px solid #eee;padding-bottom:10px;">🔧 修复建议</h2>
        <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:8px;padding:15px;margin-bottom:15px;">
            <strong style="color:#856404;">⚠️ 无法自动修复 - 需要 {responsible_team} 处理</strong>
        </div>
        <div style="background:#f8f9fa;padding:15px;border-radius:8px;">
            <strong>建议操作:</strong>
            {remediation_steps}
        </div>

        {reference_links_html}

    </div>

    <!-- Footer -->
    <div style="background:#f8f9fa;padding:20px;text-align:center;border-top:1px solid #eee;">
        <p style="margin:0 0 10px 0;color:#666;">此邮件为通知性质，无需审批操作</p>
        <p style="margin:0;color:#999;font-size:12px;">如果此漏洞已修复或不再相关，请在 Security Hub 中归档此 Finding</p>
        <hr style="border:none;border-top:1px solid #eee;margin:15px 0;">
        <p style="margin:0;color:#999;font-size:12px;">SHARA - Security Hub Auto-Remediation Agent | Powered by AWS Bedrock</p>
    </div>

</div>
</body>
</html>
'''
    return html


def format_github_pr_approval_email(
    task_id: str,
    analysis_data: dict,
    approve_url: str,
    reject_url: str
) -> str:
    """格式化 GitHub PR 审批邮件内容 (HTML 格式)

    用于容器漏洞自动修复流程，显示 PR 相关信息。

    Args:
        task_id: 任务 ID
        analysis_data: 分析结果数据
        approve_url: 批准链接
        reject_url: 拒绝链接

    Returns:
        str: 格式化的 HTML 邮件内容
    """
    # 从 analysis_data 提取信息
    # 支持两种格式：旧格式（container）和新格式（service_info）
    container = analysis_data.get('container', {})
    service_info = analysis_data.get('service_info', {})
    vulnerabilities = analysis_data.get('vulnerabilities', [])
    file_changes = analysis_data.get('file_changes', [])
    remediation = analysis_data.get('remediation', {})
    can_remediate = remediation.get('can_remediate', True) if remediation else analysis_data.get('can_remediate', True)

    # 容器/服务信息 - 优先使用原始 container 信息（来自 Finding）
    ecr_repository = container.get('ecr_repository') or service_info.get('ecr_repository', 'N/A')
    image_tag = container.get('image_tag', 'latest')
    image_digest = container.get('image_digest', '')
    # 容器镜像显示：repo:tag
    container_image = f"{ecr_repository}:{image_tag}"
    # 镜像摘要单独显示
    image_digest_display = image_digest if image_digest else 'N/A'
    # 仓库文件路径 - 来自 Agent 的 GitHub 搜索结果
    service_path = service_info.get('path', 'N/A')
    if service_path in ('N/A', 'unknown', ''):
        service_path = '未找到 (Agent 未能在 GitHub 中定位服务)'

    # 漏洞统计
    total_vulns = len(vulnerabilities)
    critical_count = sum(1 for v in vulnerabilities if v.get('severity') == 'CRITICAL')
    high_count = sum(1 for v in vulnerabilities if v.get('severity') == 'HIGH')

    # 构建漏洞列表 HTML
    vuln_rows = ''
    for v in vulnerabilities[:10]:  # 最多显示 10 个
        severity = v.get('severity', 'UNKNOWN')
        severity_color = '#dc3545' if severity == 'CRITICAL' else '#fd7e14' if severity == 'HIGH' else '#6c757d'
        # 兼容两种字段名：installed_version (Analyzer) 和 current_version (旧格式)
        current_ver = v.get('installed_version') or v.get('current_version', 'N/A')
        vuln_rows += f'''
            <tr>
                <td style="padding:8px;border-bottom:1px solid #eee;"><code>{v.get('cve_id', 'N/A')}</code></td>
                <td style="padding:8px;border-bottom:1px solid #eee;"><span style="color:{severity_color};font-weight:bold;">{severity}</span></td>
                <td style="padding:8px;border-bottom:1px solid #eee;"><code>{v.get('package_name', 'N/A')}</code></td>
                <td style="padding:8px;border-bottom:1px solid #eee;"><code>{current_ver}</code> → <code style="color:#28a745;">{v.get('fixed_version', 'N/A')}</code></td>
            </tr>
'''
    if total_vulns > 10:
        vuln_rows += f'<tr><td colspan="4" style="padding:8px;color:#666;text-align:center;">... 还有 {total_vulns - 10} 个漏洞</td></tr>'

    # 构建文件变更列表
    file_changes_html = ''
    if file_changes:
        file_rows = ''
        for fc in file_changes:
            # 兼容两种字段名：path (Analyzer) 和 file_path (旧格式)
            file_path = fc.get("path") or fc.get("file_path", "N/A")
            file_rows += f'<li><code>{file_path}</code> ({fc.get("change_type", "update")})</li>'
        file_changes_html = f'''
        <div style="margin-top:15px;">
            <strong>将修改的文件:</strong>
            <ul style="margin:10px 0;padding-left:20px;">{file_rows}</ul>
        </div>
'''

    # 不可修复的警告
    cannot_remediate_html = ''
    if not can_remediate:
        # 尝试从多个位置获取原因
        reason = analysis_data.get('cannot_remediate_reason') or \
                 remediation.get('reason') or \
                 remediation.get('description', '')
        # 如果没有明确原因，根据 service_info 推断
        if not reason:
            if service_info.get('path') in ('unknown', 'N/A', '', None):
                reason = 'Agent 未能在 GitHub 中定位到对应的服务代码，无法生成 PR。请检查：\n1. GitHub PAT 是否配置正确\n2. 仓库是否存在对应的 Dockerfile/requirements.txt'
            else:
                reason = '未知原因'
        cannot_remediate_html = f'''
        <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:8px;padding:15px;margin:20px 0;">
            <strong style="color:#856404;">⚠️ 无法自动修复</strong>
            <p style="margin:10px 0 0 0;color:#856404;white-space:pre-line;">{reason}</p>
        </div>
'''

    # 构建 HTML
    html = f'''<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:0;padding:20px;background:#f5f5f5;">
<div style="max-width:800px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,0.1);">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,#1a73e8,#0d47a1);color:#fff;padding:25px;text-align:center;">
        <div style="font-size:40px;margin-bottom:10px;">🐳</div>
        <h1 style="margin:0;font-size:22px;">SHARA 容器漏洞修复审批</h1>
        <p style="margin:10px 0 0 0;opacity:0.9;">将创建 GitHub Pull Request 修复依赖版本</p>
    </div>

    <!-- Stats Badge -->
    <div style="text-align:center;padding:20px;background:#f8f9fa;border-bottom:1px solid #eee;">
        <span style="display:inline-block;background:#dc3545;color:#fff;padding:8px 16px;border-radius:20px;font-weight:bold;margin:0 5px;">
            {critical_count} CRITICAL
        </span>
        <span style="display:inline-block;background:#fd7e14;color:#fff;padding:8px 16px;border-radius:20px;font-weight:bold;margin:0 5px;">
            {high_count} HIGH
        </span>
        <span style="display:inline-block;background:#6c757d;color:#fff;padding:8px 16px;border-radius:20px;font-weight:bold;margin:0 5px;">
            共 {total_vulns} 个漏洞
        </span>
    </div>

    <div style="padding:25px;">

        <!-- 任务信息 -->
        <h2 style="color:#333;border-bottom:2px solid #eee;padding-bottom:10px;margin-top:0;">📋 任务信息</h2>
        <table style="width:100%;border-collapse:collapse;margin-bottom:25px;">
            <tr><td style="padding:8px;border-bottom:1px solid #eee;color:#666;width:140px;">任务 ID</td><td style="padding:8px;border-bottom:1px solid #eee;"><code>{task_id}</code></td></tr>
            <tr><td style="padding:8px;border-bottom:1px solid #eee;color:#666;">ECR Repository</td><td style="padding:8px;border-bottom:1px solid #eee;"><code>{ecr_repository}</code></td></tr>
            <tr><td style="padding:8px;border-bottom:1px solid #eee;color:#666;">容器镜像</td><td style="padding:8px;border-bottom:1px solid #eee;"><code>{container_image}</code></td></tr>
            <tr><td style="padding:8px;border-bottom:1px solid #eee;color:#666;">镜像摘要</td><td style="padding:8px;border-bottom:1px solid #eee;"><code style="font-size:12px;word-break:break-all;">{image_digest_display}</code></td></tr>
            <tr><td style="padding:8px;border-bottom:1px solid #eee;color:#666;">仓库文件路径</td><td style="padding:8px;border-bottom:1px solid #eee;"><code>{service_path}</code></td></tr>
        </table>

        {cannot_remediate_html}

        <!-- 漏洞列表 -->
        <h2 style="color:#333;border-bottom:2px solid #eee;padding-bottom:10px;">🐛 待修复漏洞</h2>
        <table style="width:100%;border-collapse:collapse;margin-bottom:25px;">
            <thead>
                <tr style="background:#f8f9fa;">
                    <th style="padding:10px;text-align:left;border-bottom:2px solid #ddd;">CVE ID</th>
                    <th style="padding:10px;text-align:left;border-bottom:2px solid #ddd;">严重性</th>
                    <th style="padding:10px;text-align:left;border-bottom:2px solid #ddd;">软件包</th>
                    <th style="padding:10px;text-align:left;border-bottom:2px solid #ddd;">版本更新</th>
                </tr>
            </thead>
            <tbody>
{vuln_rows}
            </tbody>
        </table>

        <!-- 文件修改 -->
        {file_changes_html}

        <!-- 审批按钮 -->
        <div style="text-align:center;margin:30px 0;padding:20px;background:#f8f9fa;border-radius:8px;">
            <p style="margin:0 0 15px 0;color:#666;">请审核以上信息后做出决定:</p>
            <a href="{approve_url}" style="display:inline-block;background:#28a745;color:#fff;padding:12px 32px;border-radius:6px;text-decoration:none;font-weight:bold;margin:0 10px;">✅ 批准创建 PR</a>
            <a href="{reject_url}" style="display:inline-block;background:#dc3545;color:#fff;padding:12px 32px;border-radius:6px;text-decoration:none;font-weight:bold;margin:0 10px;">❌ 拒绝</a>
        </div>

        <!-- 注意事项 -->
        <div style="background:#d1ecf1;border:1px solid #17a2b8;border-radius:8px;padding:15px;margin-top:20px;">
            <strong style="color:#0c5460;">💡 说明</strong>
            <ul style="margin:10px 0 0 0;padding-left:20px;color:#0c5460;">
                <li>批准后，Agent 将自动创建 GitHub Pull Request</li>
                <li>PR 创建后需要人工 Review 和 Merge</li>
                <li>Merge 后请重新构建并部署容器镜像</li>
            </ul>
        </div>

    </div>

    <!-- Footer -->
    <div style="background:#f8f9fa;padding:20px;text-align:center;border-top:1px solid #eee;">
        <p style="margin:0 0 10px 0;color:#666;">审批链接有效期: {APPROVAL_EXPIRY_HOURS} 小时</p>
        <hr style="border:none;border-top:1px solid #eee;margin:15px 0;">
        <p style="margin:0;color:#999;font-size:12px;">SHARA - Security Hub Auto-Remediation Agent | Powered by AWS Bedrock</p>
    </div>

</div>
</body>
</html>'''
    return html


def run_phase1_analysis(
    task_id: str,
    finding: dict,
    control_id: str,
    memory_session_id: str,
    actor_id: str = ''
) -> dict:
    """运行 Phase 1 分析 - 通过 AgentCore Runtime 调用 Analyzer Agent

    Args:
        task_id: 任务 ID
        finding: Security Hub Finding
        control_id: Control ID
        memory_session_id: Memory Session ID
        actor_id: Actor ID (通常是 AWS Account ID，用于 Memory 共享)

    Returns:
        dict: 分析结果
    """
    if not ANALYZER_RUNTIME_ARN:
        logger.warning("ANALYZER_RUNTIME_ARN not configured, using fallback")
        return _fallback_analysis(task_id, finding, control_id)

    try:
        from bedrock_agentcore.runtime import AgentCoreRuntimeClient

        # 构建 Agent 输入
        agent_input = {
            'task_id': task_id,
            'finding': finding,
            'control_id': control_id,
            'memory_session_id': memory_session_id,
            'actor_id': actor_id  # 传递 actor_id 以确保 Memory 共享
        }

        # 构建请求
        request_body = {
            'session_id': memory_session_id,
            'prompt': json.dumps(agent_input)
        }

        # 创建 Runtime 客户端
        client = AgentCoreRuntimeClient(region=REGION)

        logger.info(f"Calling Analyzer Runtime: {ANALYZER_RUNTIME_ARN}")

        # 调用 Runtime (使用 HTTP 模式)
        response_data = client.invoke(
            runtime_arn=ANALYZER_RUNTIME_ARN,
            request=request_body
        )

        logger.info(f"Analyzer Runtime response received for task {task_id}")

        return {
            'success': True,
            'task_id': task_id,
            'response': response_data.get('output', response_data)
        }

    except ImportError:
        logger.warning("bedrock_agentcore not available, using HTTP fallback")
        return _invoke_runtime_http(task_id, finding, control_id, memory_session_id, actor_id)
    except Exception as e:
        logger.exception(f"Failed to run analysis: {e}")
        return {
            'success': False,
            'task_id': task_id,
            'error': str(e)
        }


def _invoke_runtime_http(
    task_id: str,
    finding: dict,
    control_id: str,
    memory_session_id: str,
    actor_id: str = ''
) -> dict:
    """通过 boto3 调用 AgentCore Runtime (fallback 方式)

    当 bedrock_agentcore SDK 不可用时使用此方法
    """
    try:
        # 使用 boto3 的 bedrock-agentcore 客户端
        # 配置较长的超时时间（AgentCore Runtime 冷启动 + LLM 推理需要时间）
        # connect_timeout=60s, read_timeout=280s（略小于 Lambda 300s 超时）
        agentcore_config = Config(
            connect_timeout=60,
            read_timeout=280,
            retries={'max_attempts': 1}  # 不重试，因为 Lambda 本身有超时限制
        )
        client = boto3.client('bedrock-agentcore', region_name=REGION, config=agentcore_config)

        # 构建请求体
        payload = {
            'prompt': json.dumps({
                'task_id': task_id,
                'finding': finding,
                'control_id': control_id,
                'memory_session_id': memory_session_id,
                'actor_id': actor_id  # 传递 actor_id 以确保 Memory 共享
            })
        }

        logger.info(f"Calling Analyzer Runtime via boto3: {ANALYZER_RUNTIME_ARN} (timeout: 280s)")

        # 调用 invoke_agent_runtime
        response = client.invoke_agent_runtime(
            agentRuntimeArn=ANALYZER_RUNTIME_ARN,
            runtimeSessionId=memory_session_id,
            payload=json.dumps(payload).encode('utf-8')
        )

        # 处理流式响应
        content_type = response.get('contentType', '')
        response_body = response.get('response', b'')

        # 读取响应
        if hasattr(response_body, 'read'):
            response_data = response_body.read().decode('utf-8')
        elif hasattr(response_body, 'iter_lines'):
            # 处理流式响应
            content = []
            for line in response_body.iter_lines():
                if line:
                    line_str = line.decode('utf-8') if isinstance(line, bytes) else line
                    if line_str.startswith('data: '):
                        content.append(line_str[6:])
                    else:
                        content.append(line_str)
            response_data = ''.join(content)
        else:
            response_data = str(response_body)

        logger.info(f"AgentCore Runtime boto3 response received for task {task_id}")
        logger.info(f"Response content-type: {content_type}")
        logger.debug(f"Raw response data (first 500 chars): {response_data[:500] if response_data else 'EMPTY'}")

        # 检查响应是否为空
        if not response_data or response_data.strip() == '':
            logger.error(f"Task {task_id}: Empty response from AgentCore Runtime")
            return {
                'success': False,
                'task_id': task_id,
                'error': 'Empty response from AgentCore Runtime'
            }

        # 尝试解析 JSON 响应
        try:
            parsed_response = json.loads(response_data)
            logger.info(f"Task {task_id}: Parsed response keys: {list(parsed_response.keys()) if isinstance(parsed_response, dict) else 'not a dict'}")
        except json.JSONDecodeError as e:
            logger.warning(f"Task {task_id}: JSON decode failed: {e}. Raw data: {response_data[:200]}")
            parsed_response = {'output': response_data}

        return {
            'success': True,
            'task_id': task_id,
            'response': parsed_response.get('output', parsed_response)
        }

    except Exception as e:
        logger.exception(f"Failed to invoke Runtime via boto3: {e}")
        return {
            'success': False,
            'task_id': task_id,
            'error': str(e)
        }


def _fallback_analysis(task_id: str, finding: dict, control_id: str) -> dict:
    """Fallback 分析结果（当 AgentCore 未配置时）"""
    return {
        'success': True,
        'task_id': task_id,
        'response': json.dumps({
            'analysis': {
                'control_id': control_id,
                'finding_type': finding.get('Title', ''),
                'resource_type': finding.get('Resources', [{}])[0].get('Type', ''),
                'resource_id': finding.get('Resources', [{}])[0].get('Id', ''),
            },
            'remediation': {
                'summary': f'Remediation for {control_id}',
                'description': 'Auto-generated remediation description',
                'steps': ['Step 1: Analyze issue', 'Step 2: Apply fix'],
            }
        })
    }


def run_phase1_container_analysis(
    task_id: str,
    finding: dict,
    container_details: dict,
    vulnerabilities: list,
    summary: dict,
    memory_session_id: str,
    actor_id: str = ''
) -> dict:
    """运行 Phase 1 容器漏洞分析 - 通过 AgentCore Runtime 调用 Analyzer Agent

    Args:
        task_id: 任务 ID
        finding: Security Hub Finding (ASFF 格式)
        container_details: 容器镜像详情
        vulnerabilities: 聚合后的漏洞列表
        summary: 漏洞摘要
        memory_session_id: Memory Session ID
        actor_id: Actor ID

    Returns:
        dict: 分析结果
    """
    if not ANALYZER_RUNTIME_ARN:
        logger.warning("ANALYZER_RUNTIME_ARN not configured, using fallback")
        return _fallback_container_analysis(task_id, finding, container_details, vulnerabilities, summary)

    try:
        # 构建 Agent 输入 (容器漏洞专用格式)
        agent_input = {
            'task_id': task_id,
            'remediation_type': 'github_pr',  # 标记为 GitHub PR 修复流程
            'finding': finding,  # 传递完整的 Security Hub Finding
            'container': container_details,
            'vulnerabilities': vulnerabilities,
            'summary': summary,
            'memory_session_id': memory_session_id,
            'actor_id': actor_id,
            # GitHub 配置 (直接指定 repo，避免动态搜索失败)
            'github_owner': GITHUB_OWNER,
            'github_repo': GITHUB_REPO
        }

        # 使用 boto3 调用 AgentCore Runtime
        agentcore_config = Config(
            connect_timeout=60,
            read_timeout=280,
            retries={'max_attempts': 1}
        )
        client = boto3.client('bedrock-agentcore', region_name=REGION, config=agentcore_config)

        payload = {
            'prompt': json.dumps(agent_input)
        }

        logger.info(f"Calling Analyzer Runtime for container CVE: {ANALYZER_RUNTIME_ARN}")
        logger.info(f"Vulnerabilities to analyze: {summary['total']} ({summary['critical']} CRITICAL, {summary['high']} HIGH)")

        response = client.invoke_agent_runtime(
            agentRuntimeArn=ANALYZER_RUNTIME_ARN,
            runtimeSessionId=memory_session_id,
            payload=json.dumps(payload).encode('utf-8')
        )

        # 处理响应
        response_body = response.get('response', b'')

        if hasattr(response_body, 'read'):
            response_data = response_body.read().decode('utf-8')
        elif hasattr(response_body, 'iter_lines'):
            content = []
            for line in response_body.iter_lines():
                if line:
                    line_str = line.decode('utf-8') if isinstance(line, bytes) else line
                    if line_str.startswith('data: '):
                        content.append(line_str[6:])
                    else:
                        content.append(line_str)
            response_data = ''.join(content)
        else:
            response_data = str(response_body)

        logger.info(f"Container CVE analysis response received for task {task_id}")

        if not response_data or response_data.strip() == '':
            logger.error(f"Task {task_id}: Empty response from AgentCore Runtime")
            return {
                'success': False,
                'task_id': task_id,
                'error': 'Empty response from AgentCore Runtime'
            }

        try:
            parsed_response = json.loads(response_data)
        except json.JSONDecodeError:
            parsed_response = {'output': response_data}

        return {
            'success': True,
            'task_id': task_id,
            'response': parsed_response.get('output', parsed_response)
        }

    except Exception as e:
        logger.exception(f"Failed to run container CVE analysis: {e}")
        return {
            'success': False,
            'task_id': task_id,
            'error': str(e)
        }


def _fallback_container_analysis(
    task_id: str,
    finding: dict,
    container_details: dict,
    vulnerabilities: list,
    summary: dict
) -> dict:
    """Fallback 容器漏洞分析结果（当 AgentCore 未配置时）"""
    # 生成简单的 PR 元数据
    cve_ids = [v['cve_id'] for v in vulnerabilities[:5]]  # 最多显示 5 个 CVE
    cve_list = ', '.join(cve_ids)
    if len(vulnerabilities) > 5:
        cve_list += f' (+{len(vulnerabilities) - 5} more)'

    return {
        'success': True,
        'task_id': task_id,
        'response': json.dumps({
            'remediation_type': 'github_pr',
            'can_remediate': True,
            'container': {
                'ecr_repository': container_details.get('ecr_repository'),
                'service_path': 'unknown',
                'service_name': container_details.get('ecr_repository')
            },
            'file_changes': [],
            'pr_metadata': {
                'title': f"fix(security): Update dependencies for {cve_list}",
                'body': f"## Summary\n\nUpdate dependencies to fix {summary['total']} vulnerabilities "
                        f"({summary['critical']} CRITICAL, {summary['high']} HIGH).\n\n"
                        f"## CVEs Fixed\n\n" +
                        '\n'.join([f"- {v['cve_id']} ({v['severity']}) - {v['package_name']}" for v in vulnerabilities[:10]]),
                'branch_name': f"fix/container-cve-{container_details.get('ecr_repository', 'unknown')[:20]}",
                'base_branch': 'main'
            },
            'vulnerabilities': vulnerabilities
        })
    }


def extract_control_id(finding: dict) -> Optional[str]:
    """从 Finding 中提取 Control ID

    Args:
        finding: Security Hub Finding

    Returns:
        str: Control ID (如 S3.1, EC2.19) 或 None
    """
    # 尝试从 GeneratorId 提取
    generator_id = finding.get('GeneratorId', '')

    # 常见格式:
    # - aws-foundational-security-best-practices/v/1.0.0/S3.1
    # - security-control/S3.1
    patterns = [
        r'/([A-Za-z]+\.\d+)$',  # 匹配末尾的 Service.Number
        r'security-control/([A-Za-z]+\.\d+)',
        r'aws-foundational-security-best-practices/.*?/([A-Za-z]+\.\d+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, generator_id)
        if match:
            return match.group(1)

    # 尝试从 Compliance.SecurityControlId 提取
    compliance = finding.get('Compliance', {})
    security_control_id = compliance.get('SecurityControlId', '')
    if security_control_id:
        return security_control_id

    # 尝试从 Types 提取
    types = finding.get('Types', [])
    for t in types:
        match = re.search(r'/([A-Za-z]+\.\d+)$', t)
        if match:
            return match.group(1)

    return None


def update_task_status(task_id: str, status: str, extra_data: dict = None):
    """更新任务状态"""
    now = datetime.now(timezone.utc).isoformat()

    update_expr = 'SET #status = :status, updatedAt = :updated, GSI1PK = :gsi1pk'
    expr_values = {
        ':status': status,
        ':updated': now,
        ':gsi1pk': f'STATUS#{status}'
    }
    expr_names = {'#status': 'status'}

    if extra_data:
        for key, value in extra_data.items():
            # Use ExpressionAttributeNames to handle reserved keywords like 'error'
            attr_name = f'#{key}'
            update_expr += f', {attr_name} = :{key}'
            expr_values[f':{key}'] = value
            expr_names[attr_name] = key

    tasks_table.update_item(
        Key={'PK': f'TASK#{task_id}', 'SK': 'METADATA'},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_values,
        ExpressionAttributeNames=expr_names
    )


def update_task_with_analysis(task_id: str, analysis_result: dict):
    """更新任务的分析结果（只保存控制相关字段）"""
    now = datetime.now(timezone.utc).isoformat()

    # 获取任务元数据以获取 findingId
    task_response = tasks_table.get_item(
        Key={'PK': f'TASK#{task_id}', 'SK': 'METADATA'}
    )
    task_metadata = task_response.get('Item', {})
    finding_id = task_metadata.get('findingId', '')

    # 解析分析结果
    response = analysis_result.get('response', '{}')
    try:
        if isinstance(response, str):
            # 尝试从响应中提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                analysis_data = json.loads(json_match.group())
            else:
                analysis_data = {}
        else:
            analysis_data = response
    except json.JSONDecodeError:
        analysis_data = {'raw_response': response}

    # 验证分析数据是否有效
    # 如果 analysis 或 remediation 为空，记录警告
    analysis = analysis_data.get('analysis', {})
    remediation = analysis_data.get('remediation', {})
    if not analysis or not analysis.get('control_id'):
        logger.warning(f"Task {task_id}: analysis data is empty or missing control_id")
        logger.warning(f"Raw response: {str(response)[:500]}")
    if not remediation:
        logger.warning(f"Task {task_id}: remediation data is empty")

    # 检查是否可以自动修复
    can_remediate = analysis_data.get('remediation', {}).get('can_remediate', True)

    # 根据是否可修复设置状态
    if can_remediate:
        new_status = 'waiting_approval'
    else:
        new_status = 'not_remediatable'

    # 提取 ASR 匹配信息（只保留关键字段）
    asr_match = analysis_data.get('asr_match', {})
    asr_info = {
        'matched': asr_match.get('matched', False),
        'playbook_id': asr_match.get('playbook_id', ''),
    } if asr_match.get('matched') else {'matched': False}

    # 只保存任务控制相关字段到 DynamoDB
    tasks_table.update_item(
        Key={'PK': f'TASK#{task_id}', 'SK': 'METADATA'},
        UpdateExpression='''
            SET #status = :status,
                updatedAt = :updated,
                GSI1PK = :gsi1pk,
                canRemediate = :can_remediate,
                asrMatch = :asr_match
        ''',
        ExpressionAttributeValues={
            ':status': new_status,
            ':updated': now,
            ':gsi1pk': f'STATUS#{new_status}',
            ':can_remediate': can_remediate,
            ':asr_match': asr_info
        },
        ExpressionAttributeNames={'#status': 'status'}
    )

    # 发送审批邮件
    # 对于容器漏洞 (github_pr)，从 task_metadata 补充原始 container 信息
    # 这样即使 Agent 搜索失败，也能显示正确的镜像信息
    remediation_type = analysis_data.get('remediation_type') or task_metadata.get('remediationType', 'aws_api')

    if remediation_type == 'github_pr':
        # 容器漏洞: 从任务记录获取原始 container 信息
        original_container = task_metadata.get('container', {})
        if original_container:
            # 合并原始 container 信息到 analysis_data
            analysis_data['container'] = original_container
            # 同时更新 vulnerabilities（如果 Agent 没有返回）
            if not analysis_data.get('vulnerabilities'):
                analysis_data['vulnerabilities'] = task_metadata.get('vulnerabilities', [])
        logger.info(f"Task {task_id}: Using original container info from task metadata")
    else:
        # AWS API 模式: 验证 analysis_data 是否有效
        if not analysis.get('control_id') and not analysis.get('finding_type'):
            logger.error(f"Task {task_id}: Skipping email - analysis data is invalid or empty")
            logger.error(f"analysis_data keys: {list(analysis_data.keys()) if analysis_data else 'None'}")
            # 仍然更新任务状态，但不发送邮件
            return

    email_sent = send_approval_email(task_id, {'response': analysis_data}, finding_id)
    if email_sent:
        logger.info(f"Approval email sent for task {task_id}")
    else:
        logger.warning(f"Failed to send approval email for task {task_id}")


def handle_api_request(event: dict, context) -> dict:
    """处理 API Gateway 请求"""
    http_method = event.get('httpMethod', '')
    path = event.get('path', '')

    if http_method == 'GET' and '/tasks' in path:
        return get_tasks(event)
    elif http_method == 'GET' and '/task/' in path:
        task_id = path.split('/task/')[-1]
        return get_task(task_id)
    else:
        return {
            'statusCode': 404,
            'body': json.dumps({'error': 'Not found'})
        }


def get_tasks(event: dict) -> dict:
    """获取任务列表"""
    query_params = event.get('queryStringParameters') or {}
    status = query_params.get('status', 'waiting_approval')

    response = tasks_table.query(
        IndexName='GSI1',
        KeyConditionExpression='GSI1PK = :pk',
        ExpressionAttributeValues={':pk': f'STATUS#{status}'},
        ScanIndexForward=False,
        Limit=50
    )

    tasks = [item for item in response.get('Items', []) if item.get('SK') == 'METADATA']

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({'tasks': tasks}, default=str)
    }


def get_task(task_id: str) -> dict:
    """获取单个任务详情"""
    response = tasks_table.get_item(
        Key={'PK': f'TASK#{task_id}', 'SK': 'METADATA'}
    )

    if 'Item' not in response:
        return {
            'statusCode': 404,
            'body': json.dumps({'error': 'Task not found'})
        }

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(response['Item'], default=str)
    }


# ============================================================================
# 审批邮件相关函数
# ============================================================================

def generate_approval_token(task_id: str, action: str) -> str:
    """生成审批 token 并保存到 DynamoDB

    Args:
        task_id: 任务 ID
        action: 操作类型 (approve/reject)

    Returns:
        str: 审批 token
    """
    import hashlib

    token = str(uuid.uuid4())
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expiry_time = datetime.now(timezone.utc) + timedelta(hours=APPROVAL_EXPIRY_HOURS)
    ttl = int(expiry_time.timestamp())

    tokens_table.put_item(Item={
        'PK': f'TOKEN#{token_hash}',
        'SK': f'TASK#{task_id}',
        'token': token,
        'token_hash': token_hash,
        'task_id': task_id,
        'action': action,
        'createdAt': datetime.now(timezone.utc).isoformat(),
        'expiresAt': expiry_time.isoformat(),
        'expires_at': ttl,  # TTL 属性
        'used': False
    })

    logger.info(f"Generated {action} token for task {task_id}")
    return token


def send_approval_email(task_id: str, analysis_result: dict, finding_id: str = '') -> bool:
    """发送审批邮件

    Args:
        task_id: 任务 ID
        analysis_result: Analyzer Agent 的分析结果
        finding_id: Security Hub Finding ID

    Returns:
        bool: 是否发送成功
    """
    if not APPROVAL_EMAIL or not SENDER_EMAIL:
        logger.warning("APPROVAL_EMAIL or SENDER_EMAIL not configured, skipping email")
        return False

    try:
        # 解析分析结果
        response = analysis_result.get('response', {})
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except json.JSONDecodeError:
                response = {}

        # 生成审批 tokens
        approve_token = generate_approval_token(task_id, 'approve')
        reject_token = generate_approval_token(task_id, 'reject')

        # 构建审批链接
        # 格式: /api/v1/approvals/{taskId}/respond?token=xxx&action=approve|reject
        base_url = API_GATEWAY_URL.rstrip('/')
        approve_url = f"{base_url}/api/v1/approvals/{task_id}/respond?token={approve_token}&action=approve"
        reject_url = f"{base_url}/api/v1/approvals/{task_id}/respond?token={reject_token}&action=reject"

        # 检查修复类型
        remediation_type = response.get('remediation_type', 'aws_api')

        # 根据修复类型选择邮件格式
        if remediation_type == 'github_pr':
            # 容器漏洞 - GitHub PR 修复
            email_body = format_github_pr_approval_email(task_id, response, approve_url, reject_url)

            # 设置邮件主题
            container = response.get('container', {})
            ecr_repo = container.get('ecr_repository', 'container')
            vuln_count = len(response.get('vulnerabilities', []))
            email_subject = f'[SHARA] 🐳 容器漏洞修复审批 - {ecr_repo} ({vuln_count} 个漏洞)'
        else:
            # FSBP Control - AWS API 修复 (原有流程)
            can_remediate = response.get('remediation', {}).get('can_remediate', True)
            email_body = format_approval_email(task_id, response, approve_url, reject_url, finding_id)

            # 根据是否可修复设置邮件主题
            control_id = response.get("analysis", {}).get("control_id", task_id)
            if can_remediate:
                email_subject = f'[SHARA] 安全修复审批请求 - {control_id}'
            else:
                email_subject = f'[SHARA] 安全发现通知 (无法自动修复) - {control_id}'

        # 发送邮件 (HTML 格式)
        ses_client.send_email(
            Source=SENDER_EMAIL,
            Destination={'ToAddresses': [APPROVAL_EMAIL]},
            Message={
                'Subject': {
                    'Data': email_subject,
                    'Charset': 'UTF-8'
                },
                'Body': {
                    'Html': {
                        'Data': email_body,
                        'Charset': 'UTF-8'
                    }
                }
            }
        )

        logger.info(f"Approval email sent for task {task_id}")
        return True

    except ClientError as e:
        logger.error(f"Failed to send approval email: {e}")
        return False
    except Exception as e:
        logger.exception(f"Error sending approval email: {e}")
        return False


def format_approval_email(
    task_id: str,
    analysis_data: dict,
    approve_url: str,
    reject_url: str,
    finding_id: str = ''
) -> str:
    """格式化审批邮件内容 (HTML 格式)

    Args:
        task_id: 任务 ID
        analysis_data: 分析结果数据
        approve_url: 批准链接
        reject_url: 拒绝链接
        finding_id: Security Hub Finding ID

    Returns:
        str: 格式化的 HTML 邮件内容
    """
    analysis = analysis_data.get('analysis', {})
    remediation = analysis_data.get('remediation', {})
    asr_match = analysis_data.get('asr_match', {})
    similar_experiences = analysis_data.get('similar_experiences', [])
    risk_assessment = analysis.get('risk_assessment', {})
    current_state = analysis.get('current_state', {})

    # 检查是否可以自动修复
    can_remediate = remediation.get('can_remediate', True)
    cannot_remediate_reason = remediation.get('cannot_remediate_reason', '')

    # 处理 Finding ID 显示
    finding_id_display = 'N/A'
    if finding_id:
        if finding_id.startswith('arn:aws:securityhub:'):
            parts = finding_id.split(':', 5)
            if len(parts) >= 6:
                finding_id_display = parts[5]
            else:
                finding_id_display = finding_id
        else:
            finding_id_display = finding_id

    # 风险等级样式
    risk_level = risk_assessment.get('level', 'UNKNOWN')
    risk_colors = {
        'CRITICAL': ('#dc3545', '#fff'),
        'HIGH': ('#dc3545', '#fff'),
        'MEDIUM': ('#ffc107', '#000'),
        'LOW': ('#28a745', '#fff')
    }
    risk_bg, risk_fg = risk_colors.get(risk_level, ('#6c757d', '#fff'))

    # 影响等级样式
    impact_level = remediation.get('estimated_impact', 'UNKNOWN')
    impact_colors = {
        'HIGH': ('#dc3545', '#fff'),
        'MEDIUM': ('#ffc107', '#000'),
        'LOW': ('#28a745', '#fff')
    }
    impact_bg, impact_fg = impact_colors.get(impact_level, ('#6c757d', '#fff'))

    # HTML 模板
    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #1a73e8 0%, #0d47a1 100%); color: white; padding: 20px; border-radius: 8px 8px 0 0; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 24px; }}
        .content {{ background: #fff; border: 1px solid #e0e0e0; border-top: none; padding: 20px; border-radius: 0 0 8px 8px; }}
        .section {{ margin-bottom: 24px; }}
        .section-title {{ font-size: 16px; font-weight: 600; color: #1a73e8; border-bottom: 2px solid #1a73e8; padding-bottom: 8px; margin-bottom: 12px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        td {{ padding: 8px 12px; vertical-align: top; }}
        .label {{ font-weight: 500; color: #666; width: 140px; }}
        .value {{ color: #333; }}
        .badge {{ display: inline-block; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: 600; }}
        .badge-danger {{ background: #dc3545; color: #fff; }}
        .badge-warning {{ background: #ffc107; color: #000; }}
        .badge-success {{ background: #28a745; color: #fff; }}
        .badge-info {{ background: #17a2b8; color: #fff; }}
        .step-list {{ margin: 0; padding-left: 20px; }}
        .step-list li {{ margin-bottom: 8px; }}
        .checkbox-list {{ list-style: none; padding-left: 0; }}
        .checkbox-list li {{ margin-bottom: 6px; }}
        .checkbox-list li:before {{ content: "☐ "; color: #666; }}
        .impact-box {{ background: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 6px; padding: 16px; margin-top: 16px; }}
        .impact-row {{ display: flex; justify-content: space-between; margin-bottom: 8px; }}
        .impact-row:last-child {{ margin-bottom: 0; }}
        .btn {{ display: inline-block; padding: 12px 32px; border-radius: 6px; text-decoration: none; font-weight: 600; margin: 8px; }}
        .btn-approve {{ background: #28a745; color: #fff !important; }}
        .btn-reject {{ background: #dc3545; color: #fff !important; }}
        .btn-container {{ text-align: center; margin: 24px 0; }}
        .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 24px; padding-top: 16px; border-top: 1px solid #e0e0e0; }}
        .warning-box {{ background: #fff3cd; border: 1px solid #ffc107; border-radius: 6px; padding: 12px; margin: 16px 0; }}
        .info-box {{ background: #d1ecf1; border: 1px solid #17a2b8; border-radius: 6px; padding: 12px; margin: 16px 0; }}
        code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-family: monospace; font-size: 13px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔐 SHARA 安全修复审批请求</h1>
    </div>
    <div class="content">
        <!-- 基本信息 -->
        <div class="section">
            <div class="section-title">📋 基本信息</div>
            <table>
                <tr><td class="label">任务 ID</td><td class="value"><code>{task_id}</code></td></tr>
                <tr><td class="label">Finding ID</td><td class="value"><code>{finding_id_display}</code></td></tr>
                <tr><td class="label">Control ID</td><td class="value"><strong>{analysis.get("control_id", "N/A")}</strong></td></tr>
                <tr><td class="label">问题类型</td><td class="value">{analysis.get("finding_type", "N/A")}</td></tr>
                <tr><td class="label">资源类型</td><td class="value">{analysis.get("resource_type", "N/A")}</td></tr>
                <tr><td class="label">资源 ID</td><td class="value"><code>{analysis.get("resource_id", "N/A")}</code></td></tr>
            </table>
        </div>

        <!-- 风险评估 -->
        <div class="section">
            <div class="section-title">⚠️ 风险评估</div>
            <table>
                <tr>
                    <td class="label">风险等级</td>
                    <td class="value"><span class="badge" style="background:{risk_bg};color:{risk_fg}">{risk_level}</span></td>
                </tr>
            </table>
            <div style="margin-top: 12px;">
                <strong>风险因素:</strong>
                <ul class="step-list">
'''

    # 风险因素
    factors = risk_assessment.get('factors', [])
    if factors:
        for factor in factors:
            html += f'                    <li>{factor}</li>\n'
    else:
        html += '                    <li>未提供风险因素</li>\n'

    html += f'''                </ul>
            </div>
            <div style="margin-top: 12px;">
                <strong>评估说明:</strong>
                <p style="margin: 8px 0; color: #555;">{risk_assessment.get("justification", "N/A")}</p>
            </div>
        </div>

        <!-- 当前状态 -->
        <div class="section">
            <div class="section-title">📊 当前状态</div>
'''

    # 当前状态
    if current_state:
        if current_state.get('status') == 'RESOURCE_NOT_FOUND':
            html += f'''            <div class="warning-box">
                <strong>⚠️ 资源未找到</strong>
                <p>{current_state.get("error", "N/A")}</p>
            </div>
'''
        else:
            html += '            <table>\n'
            for key, value in current_state.items():
                if isinstance(value, bool):
                    value_display = '<span class="badge badge-success">✅ 已启用</span>' if value else '<span class="badge badge-danger">❌ 未启用</span>'
                else:
                    value_display = str(value)
                html += f'                <tr><td class="label">{key}</td><td class="value">{value_display}</td></tr>\n'
            html += '            </table>\n'
    else:
        html += '            <p style="color: #666;">无状态信息</p>\n'

    html += f'''        </div>

        <!-- 修复方案 -->
        <div class="section">
            <div class="section-title">🔧 修复方案</div>
            <table>
                <tr><td class="label">方案名称</td><td class="value"><strong>{remediation.get("summary", "N/A")}</strong></td></tr>
            </table>
            <div style="margin-top: 12px;">
                <strong>方案描述:</strong>
                <p style="margin: 8px 0; color: #555;">{remediation.get("description", "N/A")}</p>
            </div>
'''

    # 前置条件
    prerequisites = remediation.get('prerequisites', [])
    if prerequisites:
        html += '            <div style="margin-top: 16px;"><strong>📋 前置条件（审批前请确认）:</strong><ul class="checkbox-list">\n'
        for item in prerequisites:
            html += f'                <li>{item}</li>\n'
        html += '            </ul></div>\n'

    # Agent 执行步骤
    agent_actions = remediation.get('agent_actions', [])
    if agent_actions:
        html += '            <div style="margin-top: 16px;"><strong>🤖 Agent 将执行:</strong><ol class="step-list">\n'
        for step in agent_actions:
            html += f'                <li>{step}</li>\n'
        html += '            </ol></div>\n'

    # 后续操作
    post_actions = remediation.get('post_actions', [])
    if post_actions:
        html += '            <div style="margin-top: 16px;"><strong>📝 后续操作（修复后请处理）:</strong><ul class="checkbox-list">\n'
        for item in post_actions:
            html += f'                <li>{item}</li>\n'
        html += '            </ul></div>\n'

    # 影响评估
    rollback_display = '✅ 是' if remediation.get('rollback_available') else '❌ 否'
    destructive_display = '❌ 是 (请谨慎!)' if remediation.get('is_destructive') else '✅ 否'

    html += f'''            <div class="impact-box">
                <table>
                    <tr><td class="label">预计影响</td><td><span class="badge" style="background:{impact_bg};color:{impact_fg}">{impact_level}</span></td></tr>
                    <tr><td class="label">可回滚</td><td>{rollback_display}</td></tr>
                    <tr><td class="label">破坏性操作</td><td>{destructive_display}</td></tr>
                </table>
            </div>
        </div>

        <!-- ASR Playbook -->
        <div class="section">
            <div class="section-title">📚 ASR Playbook 匹配</div>
'''

    if asr_match.get('matched'):
        confidence = asr_match.get('confidence', 0)
        confidence_pct = int(confidence * 100) if confidence <= 1 else confidence
        html += f'''            <table>
                <tr><td class="label">匹配状态</td><td><span class="badge badge-success">✅ 已匹配</span></td></tr>
                <tr><td class="label">Playbook ID</td><td><code>{asr_match.get("playbook_id", "N/A")}</code></td></tr>
                <tr><td class="label">置信度</td><td>{confidence_pct}%</td></tr>
            </table>
            <div class="info-box">
                💡 此修复方案基于 AWS 官方 ASR (Automated Security Response) 预定义的 Playbook，已经过充分测试。
            </div>
'''
    else:
        html += f'''            <table>
                <tr><td class="label">匹配状态</td><td><span class="badge badge-warning">❌ 未匹配</span></td></tr>
            </table>
            <div class="warning-box">
                ⚠️ 此修复将使用 AI 生成的修复策略，请仔细审核修复步骤。
            </div>
'''

    html += '''        </div>

        <!-- 相似经验 -->
        <div class="section">
            <div class="section-title">📖 相似修复经验</div>
'''

    if similar_experiences:
        # 过滤经验，使用不同阈值：
        # - Reflection (方法论): 相似度 >= 50%
        # - Episode (执行记录): 相似度 >= 35% (包含实际执行结果，价值更高)
        high_relevance_experiences = []
        for exp in similar_experiences:
            score = exp.get('relevance', exp.get('similarity_score', 0)) or 0
            exp_type = exp.get('type', 'reflection')  # 默认为 reflection
            if exp_type == 'episode':
                if score >= 0.35:
                    high_relevance_experiences.append(exp)
            else:
                if score >= 0.5:
                    high_relevance_experiences.append(exp)
        total_high_relevance = len(high_relevance_experiences)

        # 按相似度排序，取前 3 条
        high_relevance_experiences.sort(
            key=lambda x: x.get('relevance', x.get('similarity_score', 0)) or 0,
            reverse=True
        )
        top_experiences = high_relevance_experiences[:3]

        if top_experiences:
            if total_high_relevance > 3:
                html += f'            <p>找到 <strong>{total_high_relevance}</strong> 条相关历史经验，显示最相关的 3 条:</p><ul class="step-list">\n'
            else:
                html += f'            <p>找到 <strong>{total_high_relevance}</strong> 条相关历史经验:</p><ul class="step-list">\n'

            for exp in top_experiences:
                relevance = exp.get('relevance', exp.get('similarity_score', 0))
                relevance_pct = int(relevance * 100) if relevance <= 1 else relevance
                exp_type = exp.get('type', 'reflection')

                # 类型徽章：区分方法论 (Reflection) 和执行记录 (Episode)
                if exp_type == 'episode':
                    type_badge = '<span class="badge badge-success" style="font-size:10px;margin-right:4px;">执行记录</span>'
                else:
                    type_badge = '<span class="badge" style="background:#6c757d;color:#fff;font-size:10px;margin-right:4px;">方法论</span>'

                # 固定格式: Analyzer Agent 已加工为中文结构化内容
                title = exp.get('title', '')
                problem = exp.get('problem', '')
                solution = exp.get('solution', '')
                result = exp.get('result', '')

                # 构建显示内容
                if title and problem and solution:
                    # 完整格式: 标题 + 问题 + 解决方案
                    display_html = f'''{type_badge}<strong>{title}</strong>
                        <br><span style="color:#666;font-size:12px;">问题: {problem[:60]}</span>
                        <br><span style="color:#666;font-size:12px;">方案: {solution[:60]}</span>'''
                    if result:
                        display_html += f'''<br><span style="color:#28a745;font-size:12px;">结果: {result[:40]}</span>'''
                elif title:
                    # 只有标题
                    display_html = f'{type_badge}<strong>{title}</strong>'
                else:
                    # 回退: 使用旧格式兼容
                    content = exp.get('content', '')
                    if isinstance(content, str) and len(content) > 10:
                        display_html = type_badge + (content[:150] + '...' if len(content) > 150 else content)
                    else:
                        display_html = type_badge + '历史修复经验'

                html += f'                <li><span class="badge badge-info">{relevance_pct}%</span> {display_html}</li>\n'
            html += '            </ul>\n'

            if total_high_relevance > 3:
                html += f'            <p style="color: #666; font-size: 12px;">💡 还有 {total_high_relevance - 3} 条相关经验未显示</p>\n'
        else:
            html += '            <p style="color: #666;">暂无相关历史修复经验</p>\n'
    else:
        html += '            <p style="color: #666;">暂无相关历史修复经验</p>\n'

    html += '        </div>\n'

    # 操作按钮
    if can_remediate:
        html += f'''
        <!-- 操作按钮 -->
        <div class="btn-container">
            <a href="{approve_url}" class="btn btn-approve">✅ 批准修复</a>
            <a href="{reject_url}" class="btn btn-reject">❌ 拒绝修复</a>
        </div>
        <p style="text-align: center; color: #666; font-size: 12px;">⏰ 此审批链接将在 {APPROVAL_EXPIRY_HOURS} 小时后过期</p>
'''
    else:
        html += f'''
        <!-- 无法自动修复提示 -->
        <div class="warning-box">
            <strong>⚠️ 此 Finding 无法自动修复</strong>
            <p><strong>原因:</strong> {cannot_remediate_reason or "需要手动处理"}</p>
            <p><strong>建议操作:</strong></p>
            <ul>
                <li>如果资源已删除，请在 Security Hub 中归档此 Finding</li>
                <li>如果是软件漏洞，请通知开发团队更新相关组件</li>
                <li>如果需要手动配置，请按照上述修复步骤手动操作</li>
            </ul>
            <p style="color: #666;">此邮件仅供参考，无需审批操作。</p>
        </div>
'''

    html += '''
        <!-- 页脚 -->
        <div class="footer">
            <p>SHARA - Security Hub Auto-Remediation Agent</p>
            <p>Powered by AWS Bedrock</p>
        </div>
    </div>
</body>
</html>'''

    return html
