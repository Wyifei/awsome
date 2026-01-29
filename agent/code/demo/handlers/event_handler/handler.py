"""
Event Handler Lambda

处理 Security Hub Finding 事件:
1. 接收 EventBridge 事件
2. 清洗数据，提取 Agent 所需的关键信息
3. 创建修复任务
"""

import json
import logging
import os
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Optional, List, Dict

import boto3

# 配置日志
log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)

# 环境变量
TASKS_TABLE = os.environ.get("TASKS_TABLE", "shara-tasks-dev")
EVENTS_TABLE = os.environ.get("EVENTS_TABLE", "shara-task-events-dev")
STAGE = os.environ.get("STAGE", "dev")

# AWS 客户端
dynamodb = boto3.resource("dynamodb")
tasks_table = dynamodb.Table(TASKS_TABLE)
events_table = dynamodb.Table(EVENTS_TABLE)


# ============================================
# 数据模型 - 清洗后的 Finding 结构
# ============================================

@dataclass
class CleanedResource:
    """清洗后的资源信息"""
    arn: str                    # 资源 ARN
    type: str                   # 资源类型 (AwsS3Bucket, AwsEc2SecurityGroup, etc.)
    id: str                     # 资源 ID (bucket name, sg-xxx, etc.)
    region: str                 # 资源所在区域
    account_id: str             # 资源所属账户
    tags: Dict[str, str]        # 资源标签 (如果有)
    details: Dict[str, Any]     # 资源特定详情 (精简版)


@dataclass
class CleanedFinding:
    """
    清洗后的 Finding 结构

    只保留 Agent 处理所需的关键信息，避免 token 过长
    """
    # 基本标识
    finding_id: str             # Finding 唯一 ID
    finding_arn: str            # Finding ARN
    generator_id: str           # 生成器 ID (控制项 ID)

    # 严重级别
    severity: str               # CRITICAL, HIGH, MEDIUM, LOW
    severity_score: float       # 数值评分 (0-100)

    # 问题描述
    title: str                  # 简短标题
    description: str            # 详细描述

    # 合规信息
    compliance_status: str      # FAILED, PASSED, etc.
    control_id: str             # 控制项 ID (S3.1, EC2.19, etc.)
    control_standard: str       # 标准名称 (AWS Foundational Security Best Practices)

    # 资源信息
    resource: CleanedResource   # 受影响的资源

    # 修复建议
    remediation_recommendation: str   # 修复建议文本
    remediation_url: str              # 修复文档链接

    # 时间信息
    first_observed_at: str      # 首次发现时间
    updated_at: str             # 最后更新时间

    # AWS 账户信息
    aws_account_id: str         # 发现所属账户
    region: str                 # 发现所属区域


def extract_cleaned_finding(raw_finding: Dict[str, Any]) -> CleanedFinding:
    """
    从原始 Security Hub Finding 中提取关键信息

    原始 Finding 可能有 50+ 个字段，我们只提取 Agent 需要的信息
    """

    # 提取资源信息 (取第一个资源)
    raw_resources = raw_finding.get("Resources", [{}])
    raw_resource = raw_resources[0] if raw_resources else {}

    # 解析资源 ARN 获取详细信息
    resource_arn = raw_resource.get("Id", "")
    resource_type = raw_resource.get("Type", "")

    # 从 ARN 解析账户和区域
    arn_parts = resource_arn.split(":") if resource_arn.startswith("arn:") else []
    resource_region = arn_parts[3] if len(arn_parts) > 3 else ""
    resource_account = arn_parts[4] if len(arn_parts) > 4 else ""

    # 提取资源 ID (ARN 的最后部分)
    resource_id = resource_arn.split("/")[-1] if "/" in resource_arn else resource_arn.split(":")[-1]

    # 提取资源标签
    resource_tags = {}
    for tag in raw_resource.get("Tags", {}):
        if isinstance(tag, dict):
            resource_tags[tag.get("Key", "")] = tag.get("Value", "")

    # 提取资源详情 (精简版)
    raw_details = raw_resource.get("Details", {})
    resource_details = extract_resource_details(resource_type, raw_details)

    cleaned_resource = CleanedResource(
        arn=resource_arn,
        type=resource_type,
        id=resource_id,
        region=resource_region,
        account_id=resource_account,
        tags=resource_tags,
        details=resource_details,
    )

    # 提取合规信息
    compliance = raw_finding.get("Compliance", {})
    compliance_status = compliance.get("Status", "UNKNOWN")

    # 提取控制项 ID
    product_fields = raw_finding.get("ProductFields", {})
    control_id = product_fields.get("ControlId", "")
    control_standard = product_fields.get("StandardsArn", "").split("/")[-1] if product_fields.get("StandardsArn") else ""

    # 提取修复建议
    remediation = raw_finding.get("Remediation", {})
    recommendation = remediation.get("Recommendation", {})
    remediation_text = recommendation.get("Text", "")
    remediation_url = recommendation.get("Url", "")

    # 提取严重级别
    severity = raw_finding.get("Severity", {})
    severity_label = severity.get("Label", "UNKNOWN")
    severity_score = severity.get("Normalized", 0)

    # 构建清洗后的 Finding
    cleaned = CleanedFinding(
        finding_id=raw_finding.get("Id", ""),
        finding_arn=raw_finding.get("ProductArn", ""),
        generator_id=raw_finding.get("GeneratorId", ""),
        severity=severity_label,
        severity_score=severity_score,
        title=raw_finding.get("Title", ""),
        description=truncate_text(raw_finding.get("Description", ""), max_length=500),
        compliance_status=compliance_status,
        control_id=control_id,
        control_standard=control_standard,
        resource=cleaned_resource,
        remediation_recommendation=truncate_text(remediation_text, max_length=300),
        remediation_url=remediation_url,
        first_observed_at=raw_finding.get("FirstObservedAt", ""),
        updated_at=raw_finding.get("UpdatedAt", ""),
        aws_account_id=raw_finding.get("AwsAccountId", ""),
        region=raw_finding.get("Region", ""),
    )

    return cleaned


def extract_resource_details(resource_type: str, raw_details: Dict) -> Dict[str, Any]:
    """
    根据资源类型提取关键详情

    只提取 Agent 修复时需要的信息
    """
    details = {}

    if resource_type == "AwsS3Bucket":
        s3_details = raw_details.get("AwsS3Bucket", {})
        details = {
            "bucket_name": s3_details.get("Name", ""),
            "public_access_block": s3_details.get("PublicAccessBlockConfiguration", {}),
            "bucket_acl": simplify_acl(s3_details.get("AccessControlList", {})),
            "encryption": s3_details.get("ServerSideEncryptionConfiguration", {}),
            "versioning": s3_details.get("BucketVersioningConfiguration", {}).get("Status", ""),
        }

    elif resource_type == "AwsEc2SecurityGroup":
        sg_details = raw_details.get("AwsEc2SecurityGroup", {})
        details = {
            "group_id": sg_details.get("GroupId", ""),
            "group_name": sg_details.get("GroupName", ""),
            "vpc_id": sg_details.get("VpcId", ""),
            # 只提取有问题的规则 (0.0.0.0/0 或 ::/0)
            "risky_ingress_rules": extract_risky_rules(sg_details.get("IpPermissions", [])),
            "risky_egress_rules": extract_risky_rules(sg_details.get("IpPermissionsEgress", [])),
        }

    elif resource_type == "AwsIamUser":
        iam_details = raw_details.get("AwsIamUser", {})
        details = {
            "user_name": iam_details.get("UserName", ""),
            "user_id": iam_details.get("UserId", ""),
            "path": iam_details.get("Path", ""),
            "create_date": iam_details.get("CreateDate", ""),
        }

    elif resource_type == "AwsIamRole":
        iam_details = raw_details.get("AwsIamRole", {})
        details = {
            "role_name": iam_details.get("RoleName", ""),
            "role_id": iam_details.get("RoleId", ""),
            "path": iam_details.get("Path", ""),
        }

    elif resource_type == "AwsEc2Instance":
        ec2_details = raw_details.get("AwsEc2Instance", {})
        details = {
            "instance_id": ec2_details.get("InstanceId", ""),
            "instance_type": ec2_details.get("InstanceType", ""),
            "vpc_id": ec2_details.get("VpcId", ""),
            "subnet_id": ec2_details.get("SubnetId", ""),
            "security_groups": [sg.get("GroupId", "") for sg in ec2_details.get("SecurityGroups", [])],
        }

    else:
        # 其他资源类型，保留基本信息
        details = {"raw_type": resource_type}

    return details


def extract_risky_rules(rules: List[Dict]) -> List[Dict]:
    """提取有风险的安全组规则 (0.0.0.0/0 或 ::/0)"""
    risky = []

    for rule in rules:
        ip_ranges = rule.get("IpRanges", [])
        ipv6_ranges = rule.get("Ipv6Ranges", [])

        # 检查是否有开放到全网的规则
        has_open_ipv4 = any(r.get("CidrIp") == "0.0.0.0/0" for r in ip_ranges)
        has_open_ipv6 = any(r.get("CidrIpv6") == "::/0" for r in ipv6_ranges)

        if has_open_ipv4 or has_open_ipv6:
            risky.append({
                "protocol": rule.get("IpProtocol", ""),
                "from_port": rule.get("FromPort", ""),
                "to_port": rule.get("ToPort", ""),
                "open_to_world": True,
            })

    return risky


def simplify_acl(acl: Dict) -> Dict:
    """简化 ACL 信息"""
    if not acl:
        return {}

    grants = acl.get("Grants", [])
    return {
        "has_public_grants": any(
            g.get("Grantee", {}).get("URI", "").endswith("AllUsers") or
            g.get("Grantee", {}).get("URI", "").endswith("AuthenticatedUsers")
            for g in grants
        ),
        "grant_count": len(grants),
    }


def truncate_text(text: str, max_length: int = 500) -> str:
    """截断文本，避免过长"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


# ============================================
# Lambda Handler
# ============================================

def lambda_handler(event: dict, context: Any) -> dict:
    """
    Lambda 入口点

    处理:
    1. EventBridge - Security Hub Finding
    2. API Gateway - 手动操作
    """
    logger.info(f"Received event: {json.dumps(event, default=str)[:1000]}...")  # 只打印前1000字符

    try:
        # 判断事件来源
        if "source" in event and event["source"] == "aws.securityhub":
            return handle_security_hub_event(event)
        elif "httpMethod" in event:
            return handle_api_event(event)
        else:
            logger.warning(f"Unknown event type")
            return {"statusCode": 400, "body": "Unknown event type"}

    except Exception as e:
        logger.exception(f"Error processing event: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }


def handle_security_hub_event(event: dict) -> dict:
    """处理 Security Hub Finding 事件"""
    logger.info("Processing Security Hub event")

    findings = event.get("detail", {}).get("findings", [])
    processed_count = 0

    for raw_finding in findings:
        try:
            # 清洗数据
            cleaned = extract_cleaned_finding(raw_finding)

            logger.info(
                f"Processing finding: {cleaned.finding_id}, "
                f"Control: {cleaned.control_id}, "
                f"Severity: {cleaned.severity}, "
                f"Resource: {cleaned.resource.type}/{cleaned.resource.id}"
            )

            # 创建任务
            task_id = create_task(cleaned)
            processed_count += 1

            logger.info(f"Created task: {task_id} for finding: {cleaned.control_id}")

        except Exception as e:
            logger.error(f"Failed to process finding: {e}")
            continue

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": f"Processed {processed_count} findings",
            "total": len(findings),
        }),
    }


def create_task(cleaned: CleanedFinding) -> str:
    """创建修复任务"""
    task_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().isoformat() + "Z"

    # 将 dataclass 转换为 dict
    finding_dict = asdict(cleaned)

    # 构建任务记录
    item = {
        "PK": f"TASK#{task_id}",
        "SK": "METADATA",
        "task_id": task_id,
        "finding_id": cleaned.finding_id,
        "control_id": cleaned.control_id,
        "status": "PENDING",
        "severity": cleaned.severity,
        "severity_score": int(cleaned.severity_score),
        "title": cleaned.title,
        "resource_arn": cleaned.resource.arn,
        "resource_type": cleaned.resource.type,
        "resource_id": cleaned.resource.id,
        "aws_account_id": cleaned.aws_account_id,
        "region": cleaned.region,
        # 清洗后的完整 Finding (供 Agent 使用)
        "cleaned_finding": finding_dict,
        # 时间戳
        "created_at": timestamp,
        "updated_at": timestamp,
    }

    tasks_table.put_item(Item=item)

    # 记录事件
    record_event(task_id, "TASK_CREATED", {
        "control_id": cleaned.control_id,
        "severity": cleaned.severity,
        "resource_type": cleaned.resource.type,
    })

    return task_id


def record_event(task_id: str, event_type: str, data: dict) -> None:
    """记录任务事件"""
    timestamp = datetime.utcnow().isoformat() + "Z"

    item = {
        "PK": f"TASK#{task_id}",
        "SK": f"EVENT#{timestamp}#{event_type}",
        "task_id": task_id,
        "event_type": event_type,
        "timestamp": timestamp,
        "data": data,
    }

    events_table.put_item(Item=item)


# ============================================
# API Gateway Handler
# ============================================

def handle_api_event(event: dict) -> dict:
    """处理 API Gateway 事件"""
    http_method = event.get("httpMethod", "")
    path = event.get("path", "")
    path_params = event.get("pathParameters") or {}

    logger.info(f"API request: {http_method} {path}")

    # GET /tasks - 列出任务
    if http_method == "GET" and path == "/tasks":
        return list_tasks(event)

    # GET /tasks/{task_id} - 获取任务详情
    if http_method == "GET" and path.startswith("/tasks/"):
        task_id = path_params.get("task_id", "")
        return get_task(task_id)

    # POST /findings - 提交 Finding
    if http_method == "POST" and path == "/findings":
        body = json.loads(event.get("body", "{}"))
        return submit_finding(body)

    return {
        "statusCode": 404,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": "Not found"}),
    }


def list_tasks(event: dict) -> dict:
    """列出任务"""
    query_params = event.get("queryStringParameters") or {}
    status_filter = query_params.get("status", "PENDING")
    limit = int(query_params.get("limit", "50"))

    response = tasks_table.query(
        IndexName="status-index",
        KeyConditionExpression="status = :status",
        ExpressionAttributeValues={":status": status_filter},
        ScanIndexForward=False,
        Limit=limit,
        # 不返回完整的 cleaned_finding，减少响应大小
        ProjectionExpression="task_id, finding_id, control_id, #s, severity, title, resource_arn, resource_type, created_at",
        ExpressionAttributeNames={"#s": "status"},
    )

    tasks = response.get("Items", [])

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"tasks": tasks, "count": len(tasks)}, default=str),
    }


def get_task(task_id: str) -> dict:
    """获取任务详情"""
    response = tasks_table.get_item(Key={"PK": f"TASK#{task_id}", "SK": "METADATA"})

    item = response.get("Item")
    if not item:
        return {
            "statusCode": 404,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Task not found"}),
        }

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(item, default=str),
    }


def submit_finding(body: dict) -> dict:
    """手动提交 Finding 进行处理"""
    finding_id = body.get("finding_id", "")
    raw_finding = body.get("finding", {})

    if not finding_id and not raw_finding:
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "finding_id or finding object required"}),
        }

    # 如果提供了完整的 Finding，进行清洗
    if raw_finding:
        cleaned = extract_cleaned_finding(raw_finding)
        task_id = create_task(cleaned)
    else:
        # TODO: 根据 finding_id 从 Security Hub 获取 Finding
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "finding object required for now"}),
        }

    return {
        "statusCode": 201,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "task_id": task_id,
            "message": "Finding submitted for processing",
        }),
    }
