"""
Event Handler Lambda - 处理 Security Hub 事件并触发 Phase 1 分析

Phase 1: 接收 Finding → 创建任务 → 调用 Analyzer Agent → 发送审批邮件
"""
import json
import logging
import os
import re
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
APPROVAL_EMAIL = os.environ.get('APPROVAL_EMAIL', '')  # 审批者邮箱
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', '')  # 发件人邮箱
API_GATEWAY_URL = os.environ.get('API_GATEWAY_URL', '')  # API Gateway URL
APPROVAL_EXPIRY_HOURS = int(os.environ.get('APPROVAL_EXPIRY_HOURS', '24'))

# DynamoDB 资源
dynamodb = boto3.resource('dynamodb', region_name=REGION)
tasks_table = dynamodb.Table(TASKS_TABLE)
tokens_table = dynamodb.Table(TOKENS_TABLE)

# SES 客户端
ses_client = boto3.client('ses', region_name=REGION)


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

    # 提取 Control ID
    control_id = extract_control_id(finding)
    if not control_id:
        logger.warning(f"Could not extract control ID from finding {finding_id}")
        return {
            'finding_id': finding_id,
            'status': 'skipped',
            'reason': 'Could not extract control ID'
        }

    # 创建任务
    task_id = str(uuid.uuid4())
    memory_session_id = f"session-task-{task_id}"

    # 提取资源信息
    resources = finding.get('Resources', [])
    resource = resources[0] if resources else {}

    now = datetime.now(timezone.utc).isoformat()

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
        'traceId': context.aws_request_id if context else None
    }

    # 设置初始状态为 analyzing
    task_item['status'] = 'analyzing'
    task_item['GSI1PK'] = 'STATUS#analyzing'

    # 保存任务
    tasks_table.put_item(Item=task_item)
    logger.info(f"Created task {task_id} for finding {finding_id}")

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

    # 发送审批邮件（使用完整的 analysis_data，不存储到 DynamoDB）
    # 验证 analysis_data 是否有效，避免发送全 N/A 的邮件
    if not analysis.get('control_id') and not analysis.get('finding_type'):
        logger.error(f"Task {task_id}: Skipping email - analysis data is invalid or empty")
        logger.error(f"analysis_data keys: {list(analysis_data.keys()) if analysis_data else 'None'}")
        # 仍然更新任务状态，但不发送邮件
        return

    email_sent = send_approval_email(task_id, {'response': analysis_data})
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


def send_approval_email(task_id: str, analysis_result: dict) -> bool:
    """发送审批邮件

    Args:
        task_id: 任务 ID
        analysis_result: Analyzer Agent 的分析结果

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

        # 检查是否可以自动修复
        can_remediate = response.get('remediation', {}).get('can_remediate', True)

        # 格式化邮件内容
        email_body = format_approval_email(task_id, response, approve_url, reject_url)

        # 根据是否可修复设置邮件主题
        control_id = response.get("analysis", {}).get("control_id", task_id)
        if can_remediate:
            email_subject = f'[SHARA] 安全修复审批请求 - {control_id}'
        else:
            email_subject = f'[SHARA] 安全发现通知 (无法自动修复) - {control_id}'

        # 发送邮件
        ses_client.send_email(
            Source=SENDER_EMAIL,
            Destination={'ToAddresses': [APPROVAL_EMAIL]},
            Message={
                'Subject': {
                    'Data': email_subject,
                    'Charset': 'UTF-8'
                },
                'Body': {
                    'Text': {
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


def get_display_width(s: str) -> int:
    """计算字符串的显示宽度（考虑中文字符和 emoji）

    中文字符和大多数 emoji 占用 2 个显示宽度，ASCII 字符占用 1 个。

    Args:
        s: 输入字符串

    Returns:
        int: 显示宽度
    """
    import unicodedata
    width = 0
    for char in s:
        # emoji 和中文字符占 2 个宽度
        if unicodedata.east_asian_width(char) in ('F', 'W'):
            width += 2
        elif ord(char) >= 0x1F300:  # emoji 范围
            width += 2
        else:
            width += 1
    return width


def pad_to_width(s: str, target_width: int) -> str:
    """将字符串填充到指定的显示宽度

    Args:
        s: 输入字符串
        target_width: 目标显示宽度

    Returns:
        str: 填充后的字符串
    """
    current_width = get_display_width(s)
    padding = target_width - current_width
    if padding > 0:
        return s + ' ' * padding
    return s


def format_approval_email(
    task_id: str,
    analysis_data: dict,
    approve_url: str,
    reject_url: str
) -> str:
    """格式化审批邮件内容

    Args:
        task_id: 任务 ID
        analysis_data: 分析结果数据
        approve_url: 批准链接
        reject_url: 拒绝链接

    Returns:
        str: 格式化的邮件内容
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

    # 风险等级图标
    risk_icons = {
        'HIGH': '🔴 HIGH',
        'CRITICAL': '🔴 CRITICAL',
        'MEDIUM': '🟡 MEDIUM',
        'LOW': '🟢 LOW'
    }
    risk_level = risk_assessment.get('level', 'UNKNOWN')
    risk_display = risk_icons.get(risk_level, f'⚪ {risk_level}')

    # 影响等级图标
    impact_icons = {
        'HIGH': '🔴 HIGH',
        'MEDIUM': '🟡 MEDIUM',
        'LOW': '🟢 LOW'
    }
    impact_level = remediation.get('estimated_impact', 'UNKNOWN')
    impact_display = impact_icons.get(impact_level, f'⚪ {impact_level}')

    # 布尔值显示
    rollback_display = '✅ 是' if remediation.get('rollback_available') else '❌ 否'
    destructive_display = '❌ 是 (请谨慎!)' if remediation.get('is_destructive') else '✅ 否'

    # 构建邮件内容
    lines = [
        '═' * 70,
        '                  🔐 SHARA 安全修复审批请求',
        '═' * 70,
        '',
        '📋 基本信息',
        '─' * 70,
        f'  任务 ID:        {task_id}',
        f'  Control ID:     {analysis.get("control_id", "N/A")}',
        f'  问题类型:       {analysis.get("finding_type", "N/A")}',
        f'  资源类型:       {analysis.get("resource_type", "N/A")}',
        f'  资源 ID:        {analysis.get("resource_id", "N/A")}',
        '',
        '⚠️ 风险评估',
        '─' * 70,
        f'  风险等级:       {risk_display}',
        '',
        '  风险因素:',
    ]

    # 风险因素
    factors = risk_assessment.get('factors', [])
    if factors:
        for factor in factors:
            lines.append(f'    • {factor}')
    else:
        lines.append('    • 未提供风险因素')

    lines.extend([
        '',
        '  评估说明:',
        f'    {risk_assessment.get("justification", "N/A")}',
        '',
        '📊 当前状态',
        '─' * 70,
    ])

    # 当前状态
    if current_state:
        # 检查是否是资源不存在的情况
        if current_state.get('status') == 'RESOURCE_NOT_FOUND':
            lines.extend([
                f'  状态:           ⚠️ {current_state.get("status")}',
                f'  错误信息:       {current_state.get("error", "N/A")}',
                '',
                '  可能原因:',
            ])
            for reason in current_state.get('possible_reasons', []):
                lines.append(f'    • {reason}')
        else:
            # 正常显示当前状态
            for key, value in current_state.items():
                if isinstance(value, bool):
                    value_display = '✅ 已启用' if value else '❌ 未启用'
                else:
                    value_display = str(value)
                lines.append(f'  {key}:  {value_display}')
    else:
        lines.append('  (无状态信息)')

    lines.extend([
        '',
        '🔧 修复方案',
        '─' * 70,
        f'  方案名称:     {remediation.get("summary", "N/A")}',
        '',
        '  方案描述:',
        f'    {remediation.get("description", "N/A")}',
    ])

    # 前置条件（人工确认）
    prerequisites = remediation.get('prerequisites', [])
    if prerequisites:
        lines.extend([
            '',
            '  📋 前置条件（审批前请确认）:',
        ])
        for item in prerequisites:
            lines.append(f'    □ {item}')

    # Agent 执行步骤
    agent_actions = remediation.get('agent_actions', [])
    if agent_actions:
        lines.extend([
            '',
            '  🤖 Agent 将执行:',
        ])
        for i, step in enumerate(agent_actions, 1):
            lines.append(f'    {i}. {step}')

    # 后续操作（人工处理）
    post_actions = remediation.get('post_actions', [])
    if post_actions:
        lines.extend([
            '',
            '  📝 后续操作（修复后请处理）:',
        ])
        for item in post_actions:
            lines.append(f'    □ {item}')

    # 兼容旧格式：如果没有新字段，使用 steps 字段
    if not prerequisites and not agent_actions and not post_actions:
        steps = remediation.get('steps', [])
        if steps:
            lines.extend([
                '',
                '  修复步骤:',
            ])
            for i, step in enumerate(steps, 1):
                if step.startswith('步骤') or step.startswith('Step'):
                    lines.append(f'    {step}')
                else:
                    lines.append(f'    {i}. {step}')

    # 构建影响评估框（使用 HTML 表格样式更清晰）
    box_width = 56  # 内容区域宽度
    lines.extend([
        '',
        '  ┌' + '─' * box_width + '┐',
        '  │' + pad_to_width(f'  预计影响:     {impact_display}', box_width) + '│',
        '  │' + pad_to_width(f'  可回滚:       {rollback_display}', box_width) + '│',
        '  │' + pad_to_width(f'  破坏性操作:   {destructive_display}', box_width) + '│',
        '  └' + '─' * box_width + '┘',
    ])

    # 特别注意事项
    special_considerations = remediation.get('special_considerations', [])
    if special_considerations:
        lines.extend([
            '',
            '  ⚠️ 特别注意事项:',
        ])
        for item in special_considerations:
            lines.append(f'    • {item}')

    # 建议操作
    recommended_actions = remediation.get('recommended_actions', {})
    if recommended_actions:
        lines.extend([
            '',
            '  📌 建议操作:',
        ])
        if recommended_actions.get('immediate'):
            lines.append(f'    • 立即:   {recommended_actions["immediate"]}')
        if recommended_actions.get('short_term'):
            lines.append(f'    • 短期:   {recommended_actions["short_term"]}')
        if recommended_actions.get('long_term'):
            lines.append(f'    • 长期:   {recommended_actions["long_term"]}')

    lines.extend([
        '',
        '📚 ASR Playbook 匹配',
        '─' * 70,
    ])

    # ASR 匹配状态
    if asr_match.get('matched'):
        confidence = asr_match.get('confidence', 0)
        confidence_pct = int(confidence * 100) if confidence <= 1 else confidence
        lines.extend([
            '  匹配状态:     ✅ 已匹配',
            f'  Playbook ID:  {asr_match.get("playbook_id", "N/A")}',
            f'  置信度:       {confidence_pct}%',
            '',
            '  💡 此修复方案基于 AWS 官方 ASR (Automated Security Response)',
            '     预定义的 Playbook，已经过充分测试。',
        ])
    else:
        lines.extend([
            '  匹配状态:     ❌ 未匹配',
            '',
            f'  说明: {asr_match.get("message", "没有找到匹配的 ASR Playbook")}',
            '',
            '  ⚠️ 此修复将使用 AI 生成的修复策略，请仔细审核修复步骤。',
        ])

    lines.extend([
        '',
        '📖 相似修复经验',
        '─' * 70,
    ])

    # 相似经验 - 简洁显示
    if similar_experiences:
        lines.append(f'  找到 {len(similar_experiences)} 条相关历史经验:')
        for i, exp in enumerate(similar_experiences, 1):
            relevance = exp.get('relevance', exp.get('similarity_score', 0))
            relevance_pct = int(relevance * 100) if relevance <= 1 else relevance

            # 从 content 中提取标题或摘要
            content = exp.get('content', '')
            title = ''
            if isinstance(content, str) and content.startswith('{'):
                try:
                    content_data = json.loads(content)
                    # 尝试获取 title 或 situation 的前 60 个字符
                    title = content_data.get('title', '') or content_data.get('situation', '')[:60]
                except:
                    pass
            if not title:
                title = exp.get('type', 'experience')

            # 截断过长的标题
            if len(title) > 50:
                title = title[:47] + '...'

            lines.append(f'  • [{relevance_pct}%] {title}')
    else:
        lines.append('  暂无相关历史修复经验')

    lines.extend([
        '',
        '═' * 70,
        '',
    ])

    # 根据 can_remediate 决定是否显示审批按钮
    if can_remediate:
        lines.extend([
            '                        请选择您的操作:',
            '',
            '    [ ✅ 批准修复 ]              [ ❌ 拒绝修复 ]',
            '',
            f'    批准链接: {approve_url}',
            '',
            f'    拒绝链接: {reject_url}',
            '',
            f'    ⏰ 此审批链接将在 {APPROVAL_EXPIRY_HOURS} 小时后过期',
        ])
    else:
        lines.extend([
            '                    ⚠️ 此 Finding 无法自动修复',
            '',
            f'    原因: {cannot_remediate_reason or "需要手动处理"}',
            '',
            '    建议操作:',
            '    • 如果资源已删除，请在 Security Hub 中归档此 Finding',
            '    • 如果是软件漏洞，请通知开发团队更新相关组件',
            '    • 如果需要手动配置，请按照上述修复步骤手动操作',
            '',
            '    此邮件仅供参考，无需审批操作。',
        ])

    lines.extend([
        '',
        '═' * 70,
        '                    SHARA - Security Hub Auto-Remediation Agent',
        '                              Powered by AWS Bedrock',
        '═' * 70,
    ])

    return '\n'.join(lines)
