"""
Approval Handler Lambda - 处理审批回调并执行 Phase 2 修复

Phase 2: 审批通过 → 调用 Remediator Agent → 执行修复
Remediator 通过 A2A 协议直接调用 Validator Agent 完成验证
"""
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import boto3
from botocore.exceptions import ClientError

# 配置日志
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# 环境变量
TASKS_TABLE = os.environ.get('TASKS_TABLE', 'shara-dev-tasks')
TOKENS_TABLE = os.environ.get('TOKENS_TABLE', 'shara-dev-approval-tokens')
ASR_PLAYBOOKS_BUCKET = os.environ.get('ASR_PLAYBOOKS_BUCKET', 'shara-dev-asr-playbooks-870414140965')
MEMORY_ID = os.environ.get('AGENTCORE_MEMORY_ID', '')
# Remediator Agent Runtime ARN (Remediator 通过 A2A 调用 Validator)
REMEDIATOR_RUNTIME_ARN = os.environ.get('REMEDIATOR_RUNTIME_ARN', '')
STAGE = os.environ.get('STAGE', 'dev')
REGION = os.environ.get('AWS_REGION', 'us-east-1')

# DynamoDB 资源
dynamodb = boto3.resource('dynamodb', region_name=REGION)
tasks_table = dynamodb.Table(TASKS_TABLE)
tokens_table = dynamodb.Table(TOKENS_TABLE)


def lambda_handler(event: dict, context) -> dict:
    """
    Lambda 入口函数

    Args:
        event: API Gateway 审批回调事件 或 异步修复事件
        context: Lambda 上下文

    Returns:
        dict: 响应结果
    """
    logger.info(f"Received event: {json.dumps(event)}")

    try:
        # 检查特殊事件类型（来自 Lambda 自调用或其他 Lambda）
        event_type = event.get('eventType') or event.get('action')

        if event_type == 'ASYNC_REMEDIATION':
            return handle_async_remediation(event, context)

        if event_type == 'ASYNC_ROLLBACK':
            return handle_async_rollback(event, context)

        if event_type == 'send_result_email':
            return handle_send_result_email(event, context)

        http_method = event.get('httpMethod', '')
        path = event.get('path', '')
        query_params = event.get('queryStringParameters') or {}

        # 新格式: /api/v1/approvals/{taskId}/respond?token=xxx&action=approve|reject|rollback
        if '/respond' in path:
            action = query_params.get('action', '')
            if action in ['approve', 'reject']:
                return handle_approval(event, context, action=action)
            elif action == 'rollback':
                return handle_rollback_request(event, context)
            else:
                return {
                    'statusCode': 400,
                    'body': json.dumps({'error': 'Invalid or missing action parameter. Use action=approve, reject, or rollback'})
                }
        # 旧格式兼容: /approve 或 /reject 路径
        elif '/approve' in path:
            return handle_approval(event, context, action='approve')
        elif '/reject' in path:
            return handle_approval(event, context, action='reject')
        elif '/status' in path:
            return get_approval_status(event)
        else:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Not found'})
            }

    except Exception as e:
        logger.exception(f"Error processing event: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def handle_approval(event: dict, context, action: str) -> dict:
    """处理审批请求

    Args:
        event: API Gateway 事件
        context: Lambda 上下文
        action: 操作类型 (approve/reject)

    Returns:
        dict: 响应结果
    """
    # 获取参数
    # token 从 query params 获取，task_id 从 path params 获取
    query_params = event.get('queryStringParameters') or {}
    path_params = event.get('pathParameters') or {}

    token = query_params.get('token', '')
    # task_id 可能在 path params (API Gateway 格式) 或 query params (兼容旧链接)
    task_id = path_params.get('taskId', '') or query_params.get('task_id', '')

    if not token or not task_id:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Missing token or task_id'})
        }

    # 验证 Token
    token_valid = validate_token(token, task_id)
    if not token_valid:
        return {
            'statusCode': 403,
            'body': json.dumps({'error': 'Invalid or expired token'})
        }

    # 获取任务
    task = get_task(task_id)
    if not task:
        return {
            'statusCode': 404,
            'body': json.dumps({'error': 'Task not found'})
        }

    # 检查任务状态
    current_status = task.get('status')
    if current_status != 'waiting_approval':
        return {
            'statusCode': 400,
            'body': json.dumps({
                'error': f'Task is not waiting for approval (current status: {current_status})'
            })
        }

    # 标记 Token 已使用
    mark_token_used(token, task_id, action)

    if action == 'approve':
        return handle_approve(task, context)
    else:
        return handle_reject(task, context)


def handle_approve(task: dict, context) -> dict:
    """处理审批通过 - 异步触发修复

    为了避免 API Gateway 29秒超时限制，此函数立即返回并异步触发修复。
    修复工作由 handle_async_remediation 处理。

    Args:
        task: 任务数据
        context: Lambda 上下文

    Returns:
        dict: 响应结果（立即返回）
    """
    task_id = task.get('taskId')
    memory_session_id = task.get('memorySessionId')
    actor_id = task.get('actorId', '')
    finding_id = task.get('findingId')
    resource_id = task.get('resourceId')
    resource_type = task.get('resourceType')
    control_id = task.get('controlId')

    logger.info(f"Approval received for task {task_id}")

    # 更新状态为 approved
    update_task_status(task_id, 'approved')
    save_task_event(task_id, 'approval_received', {'action': 'approve'})

    try:
        # 异步调用 Lambda 执行修复（避免 API Gateway 超时）
        async_event = {
            'eventType': 'ASYNC_REMEDIATION',
            'task_id': task_id,
            'memory_session_id': memory_session_id,
            'actor_id': actor_id,
            'finding_id': finding_id,
            'resource_arn': resource_id,
            'resource_type': resource_type,
            'control_id': control_id
        }

        lambda_client = boto3.client('lambda', region_name=REGION)

        # 获取当前 Lambda 函数名
        function_name = context.function_name

        logger.info(f"Invoking async remediation for task {task_id}")

        # 异步调用 Lambda（InvocationType='Event' 表示异步）
        lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='Event',  # 异步调用，不等待响应
            Payload=json.dumps(async_event)
        )

        # 更新状态为 remediation_started
        update_task_status(task_id, 'remediation_started')

        # 立即返回响应
        return {
            'statusCode': 202,  # 202 Accepted
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'task_id': task_id,
                'status': 'remediation_started',
                'message': 'Remediation has been started. Check /status endpoint for progress.'
            })
        }

    except Exception as e:
        logger.exception(f"Failed to trigger async remediation for task {task_id}: {e}")
        update_task_status(task_id, 'execution_failed', {'error': str(e)})
        return {
            'statusCode': 500,
            'body': json.dumps({
                'task_id': task_id,
                'status': 'execution_failed',
                'error': str(e)
            })
        }


def handle_async_remediation(event: dict, context) -> dict:
    """处理异步修复事件

    此函数由 Lambda 异步调用执行，不受 API Gateway 超时限制。

    Args:
        event: 异步修复事件
        context: Lambda 上下文

    Returns:
        dict: 执行结果
    """
    task_id = event.get('task_id')
    memory_session_id = event.get('memory_session_id')
    actor_id = event.get('actor_id', '')
    finding_id = event.get('finding_id')
    resource_arn = event.get('resource_arn')
    resource_type = event.get('resource_type')
    control_id = event.get('control_id')

    logger.info(f"Starting async remediation for task {task_id}")

    try:
        # Phase 2: 执行修复 (Remediator 会通过 A2A 调用 Validator)
        remediation_result = run_phase2_remediation(
            task_id=task_id,
            memory_session_id=memory_session_id,
            actor_id=actor_id,
            finding_id=finding_id,
            resource_arn=resource_arn,
            resource_type=resource_type,
            control_id=control_id
        )

        if not remediation_result.get('success'):
            update_task_status(task_id, 'execution_failed', {
                'error': remediation_result.get('error', 'Unknown error')
            })
            logger.error(f"Remediation failed for task {task_id}: {remediation_result.get('error')}")
            return {
                'success': False,
                'task_id': task_id,
                'error': remediation_result.get('error')
            }

        # Remediator 返回的结果已包含验证状态
        final_status = remediation_result.get('status', 'completed')
        update_task_status(task_id, final_status)

        logger.info(f"Remediation completed for task {task_id}, status: {final_status}")

        return {
            'success': True,
            'task_id': task_id,
            'status': final_status,
            'response': remediation_result.get('response')
        }

    except Exception as e:
        logger.exception(f"Async remediation failed for task {task_id}: {e}")
        update_task_status(task_id, 'execution_failed', {'error': str(e)})
        return {
            'success': False,
            'task_id': task_id,
            'error': str(e)
        }


def handle_reject(task: dict, context) -> dict:
    """处理审批拒绝

    Args:
        task: 任务数据
        context: Lambda 上下文

    Returns:
        dict: 响应结果
    """
    task_id = task.get('taskId')

    logger.info(f"Rejection received for task {task_id}")

    # 更新状态为 rejected
    update_task_status(task_id, 'rejected')
    save_task_event(task_id, 'approval_received', {'action': 'reject'})

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({
            'task_id': task_id,
            'status': 'rejected',
            'message': 'Remediation request rejected'
        })
    }


def run_phase2_remediation(
    task_id: str,
    memory_session_id: str,
    actor_id: str,
    finding_id: str,
    resource_arn: str,
    resource_type: str,
    control_id: str
) -> dict:
    """运行 Phase 2 修复 - 通过 AgentCore Runtime 调用 Remediator Agent

    Remediator Agent 会通过 A2A 协议直接调用 Validator Agent 完成验证。

    Args:
        task_id: 任务 ID
        memory_session_id: Memory Session ID
        actor_id: Actor ID (AWS Account ID，用于 Memory 共享)
        finding_id: Finding ID
        resource_arn: 资源 ARN
        resource_type: 资源类型
        control_id: Control ID

    Returns:
        dict: 修复和验证结果
    """
    if not REMEDIATOR_RUNTIME_ARN:
        logger.error("REMEDIATOR_RUNTIME_ARN not configured")
        return {
            'success': False,
            'error': 'Remediator Runtime ARN not configured'
        }

    try:
        # 更新状态
        update_task_status(task_id, 'generating_code')
        save_task_event(task_id, 'code_generation_started')

        # 构建 Agent 输入 (包含所有信息供 Remediator 传递给 Validator)
        agent_input = {
            'task_id': task_id,
            'memory_session_id': memory_session_id,
            'actor_id': actor_id,
            'finding_id': finding_id,
            'resource_arn': resource_arn,
            'resource_type': resource_type,
            'control_id': control_id
        }

        update_task_status(task_id, 'executing')
        save_task_event(task_id, 'execution_started')

        # 调用 AgentCore Runtime (Remediator 会通过 A2A 调用 Validator)
        response_data = _invoke_runtime(
            runtime_arn=REMEDIATOR_RUNTIME_ARN,
            session_id=memory_session_id,
            agent_input=agent_input,
            timeout=900  # 增加超时时间，因为包含验证步骤
        )

        save_task_event(task_id, 'execution_completed', {
            'resource_arn': resource_arn
        })

        return {
            'success': True,
            'task_id': task_id,
            'response': response_data.get('output', response_data)
        }

    except Exception as e:
        logger.exception(f"Failed to run remediation: {e}")
        return {
            'success': False,
            'error': str(e)
        }


def _invoke_runtime(
    runtime_arn: str,
    session_id: str,
    agent_input: dict,
    timeout: int = 300
) -> dict:
    """调用 AgentCore Runtime

    使用 boto3 bedrock-agentcore 客户端调用 InvokeAgentRuntime API

    Args:
        runtime_arn: Agent Runtime ARN
        session_id: Session ID
        agent_input: Agent 输入
        timeout: 超时时间（秒）

    Returns:
        dict: Runtime 响应
    """
    from botocore.config import Config

    # 配置超时
    config = Config(
        read_timeout=timeout,
        connect_timeout=30,
        retries={'max_attempts': 2}
    )

    # 创建 bedrock-agentcore 客户端
    client = boto3.client('bedrock-agentcore', region_name=REGION, config=config)

    # 构建 payload
    payload = json.dumps({
        'prompt': json.dumps(agent_input)
    }).encode('utf-8')

    logger.info(f"Calling AgentCore Runtime: {runtime_arn}")
    logger.info(f"Session ID: {session_id}")
    logger.debug(f"Payload: {payload}")

    # 调用 InvokeAgentRuntime API
    response = client.invoke_agent_runtime(
        agentRuntimeArn=runtime_arn,
        runtimeSessionId=session_id,
        payload=payload
    )

    logger.info(f"AgentCore Runtime response received, content-type: {response.get('contentType', 'unknown')}")

    # 处理响应
    content_type = response.get('contentType', '')
    result_content = []

    if 'text/event-stream' in content_type:
        # 处理流式响应
        for line in response['response'].iter_lines(chunk_size=1024):
            if line:
                line_str = line.decode('utf-8')
                if line_str.startswith('data: '):
                    result_content.append(line_str[6:])
                else:
                    result_content.append(line_str)
        output = '\n'.join(result_content)
    elif content_type == 'application/json':
        # 处理 JSON 响应
        chunks = []
        for chunk in response.get('response', []):
            chunks.append(chunk.decode('utf-8'))
        output = ''.join(chunks)
        try:
            output = json.loads(output)
        except json.JSONDecodeError:
            pass
    else:
        # 处理其他类型响应
        output = str(response)

    logger.info(f"AgentCore Runtime output processed")
    return {'output': output}


def validate_token(token: str, task_id: str) -> bool:
    """验证审批 Token

    Args:
        token: Token 值
        task_id: 任务 ID

    Returns:
        bool: Token 是否有效
    """
    import hashlib

    try:
        # 计算 token hash
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        # 查询 token
        response = tokens_table.get_item(
            Key={
                'PK': f'TOKEN#{token_hash}',
                'SK': f'TASK#{task_id}'
            }
        )

        if 'Item' not in response:
            logger.warning(f"Token not found for task {task_id}")
            return False

        item = response['Item']

        # 检查是否已使用
        if item.get('used', False):
            logger.warning(f"Token already used for task {task_id}")
            return False

        # 检查是否过期
        expires_at = item.get('expiresAt', '')
        if expires_at:
            expires_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            if expires_dt.tzinfo is None:
                expires_dt = expires_dt.replace(tzinfo=timezone.utc)
            if expires_dt < datetime.now(timezone.utc):
                logger.warning(f"Token expired for task {task_id}")
                return False

        return True

    except Exception as e:
        logger.exception(f"Error validating token: {e}")
        return False


def mark_token_used(token: str, task_id: str, action: str):
    """标记 Token 已使用

    Args:
        token: Token 值
        task_id: 任务 ID
        action: 使用的操作
    """
    import hashlib

    try:
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        tokens_table.update_item(
            Key={
                'PK': f'TOKEN#{token_hash}',
                'SK': f'TASK#{task_id}'
            },
            UpdateExpression='SET used = :used, usedAt = :usedAt, usedAction = :action',
            ExpressionAttributeValues={
                ':used': True,
                ':usedAt': datetime.now(timezone.utc).isoformat(),
                ':action': action
            }
        )
    except Exception as e:
        logger.exception(f"Error marking token as used: {e}")


def get_task(task_id: str) -> Optional[dict]:
    """获取任务

    Args:
        task_id: 任务 ID

    Returns:
        dict: 任务数据或 None
    """
    try:
        response = tasks_table.get_item(
            Key={'PK': f'TASK#{task_id}', 'SK': 'METADATA'}
        )
        return response.get('Item')
    except Exception as e:
        logger.exception(f"Error getting task: {e}")
        return None


def update_task_status(task_id: str, status: str, extra_data: dict = None):
    """更新任务状态"""
    now = datetime.now(timezone.utc).isoformat()

    update_expr = 'SET #status = :status, updatedAt = :updated, GSI1PK = :gsi1pk, phase = :phase'
    expr_values = {
        ':status': status,
        ':updated': now,
        ':gsi1pk': f'STATUS#{status}',
        ':phase': 'post_approval'
    }
    expr_names = {'#status': 'status'}

    if extra_data:
        for key, value in extra_data.items():
            # 使用 ExpressionAttributeNames 处理保留关键字（如 error, name, status 等）
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


def save_task_event(task_id: str, event_type: str, data: dict = None):
    """保存任务事件"""
    event_id = str(uuid.uuid4())[:8]
    timestamp = datetime.now(timezone.utc).isoformat()
    ttl = int(time.time()) + (90 * 24 * 60 * 60)

    item = {
        'PK': f'TASK#{task_id}',
        'SK': f'EVENT#{timestamp}#{event_id}',
        'taskId': task_id,
        'eventId': event_id,
        'eventType': event_type,
        'timestamp': timestamp,
        'actor': {'type': 'lambda', 'id': 'approval-handler'},
        'data': data or {},
        'ttl': ttl
    }

    tasks_table.put_item(Item=item)


def get_approval_status(event: dict) -> dict:
    """获取审批状态

    Args:
        event: API Gateway 事件

    Returns:
        dict: 审批状态响应
    """
    query_params = event.get('queryStringParameters') or {}
    path_params = event.get('pathParameters') or {}
    # task_id 可能在 path params (API Gateway 格式) 或 query params (兼容旧链接)
    task_id = path_params.get('taskId', '') or query_params.get('task_id', '')

    if not task_id:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Missing task_id'})
        }

    task = get_task(task_id)
    if not task:
        return {
            'statusCode': 404,
            'body': json.dumps({'error': 'Task not found'})
        }

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({
            'task_id': task_id,
            'status': task.get('status'),
            'phase': task.get('phase'),
            'updated_at': task.get('updatedAt')
        }, default=str)
    }
