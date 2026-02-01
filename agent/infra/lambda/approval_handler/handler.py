"""
Approval Handler Lambda - 处理审批回调并执行 Phase 2 修复

Phase 2: 审批通过 → 调用 Remediator Agent → 执行修复
Remediator 通过 A2A 协议直接调用 Validator Agent 完成验证
"""
import json
import logging
import os
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
# Email Configuration
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', '')
RESULT_EMAIL = os.environ.get('RESULT_EMAIL', '')
API_GATEWAY_URL = os.environ.get('API_GATEWAY_URL', '')
ROLLBACK_TOKEN_EXPIRY_HOURS = int(os.environ.get('ROLLBACK_TOKEN_EXPIRY_HOURS', '72'))

# AWS 客户端
dynamodb = boto3.resource('dynamodb', region_name=REGION)
tasks_table = dynamodb.Table(TASKS_TABLE)
tokens_table = dynamodb.Table(TOKENS_TABLE)
ses_client = boto3.client('ses', region_name=REGION)


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
        # 旧格式兼容: /approve, /reject, /rollback 路径
        elif '/approve' in path:
            return handle_approval(event, context, action='approve')
        elif '/reject' in path:
            return handle_approval(event, context, action='reject')
        elif '/rollback' in path:
            return handle_rollback_request(event, context)
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

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({
            'task_id': task_id,
            'status': 'rejected',
            'message': 'Remediation request rejected'
        })
    }


def handle_rollback_request(event: dict, context) -> dict:
    """处理回滚请求

    用户点击结果邮件中的回滚链接时触发。
    回滚流程: Remediator (rollback) → A2A → Validator → 结果邮件（无回滚链接）

    Args:
        event: API Gateway 事件
        context: Lambda 上下文

    Returns:
        dict: 响应结果
    """
    # 获取参数
    query_params = event.get('queryStringParameters') or {}
    path_params = event.get('pathParameters') or {}

    token = query_params.get('token', '')
    task_id = path_params.get('taskId', '') or query_params.get('task_id', '')

    if not token or not task_id:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Missing token or task_id'})
        }

    # 验证 Token (可能需要不同的 token 类型)
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

    # 检查任务状态 - 只有已完成的修复才能回滚
    current_status = task.get('status')
    if current_status not in ['completed', 'validated']:
        return {
            'statusCode': 400,
            'body': json.dumps({
                'error': f'Task cannot be rolled back (current status: {current_status}). Only completed tasks can be rolled back.'
            })
        }

    # 标记 Token 已使用
    mark_token_used(token, task_id, 'rollback')

    return handle_rollback(task, context)


def handle_rollback(task: dict, context) -> dict:
    """处理回滚 - 异步触发回滚

    Args:
        task: 任务数据
        context: Lambda 上下文

    Returns:
        dict: 响应结果
    """
    task_id = task.get('taskId')
    memory_session_id = task.get('memorySessionId')
    actor_id = task.get('actorId', '')
    finding_id = task.get('findingId')
    resource_id = task.get('resourceId')
    resource_type = task.get('resourceType')
    control_id = task.get('controlId')

    logger.info(f"Rollback requested for task {task_id}")

    # 更新状态为 rollback_requested
    update_task_status(task_id, 'rollback_requested')

    try:
        # 异步调用 Lambda 执行回滚
        async_event = {
            'eventType': 'ASYNC_ROLLBACK',
            'task_id': task_id,
            'memory_session_id': memory_session_id,
            'actor_id': actor_id,
            'finding_id': finding_id,
            'resource_arn': resource_id,
            'resource_type': resource_type,
            'control_id': control_id
        }

        lambda_client = boto3.client('lambda', region_name=REGION)
        function_name = context.function_name

        logger.info(f"Invoking async rollback for task {task_id}")

        lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='Event',
            Payload=json.dumps(async_event)
        )

        update_task_status(task_id, 'rollback_started')

        return {
            'statusCode': 202,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'task_id': task_id,
                'status': 'rollback_started',
                'message': 'Rollback has been started. Check /status endpoint for progress.'
            })
        }

    except Exception as e:
        logger.exception(f"Failed to trigger async rollback for task {task_id}: {e}")
        update_task_status(task_id, 'rollback_failed', {'error': str(e)})
        return {
            'statusCode': 500,
            'body': json.dumps({
                'task_id': task_id,
                'status': 'rollback_failed',
                'error': str(e)
            })
        }


def handle_async_rollback(event: dict, context) -> dict:
    """处理异步回滚事件

    执行回滚: Remediator (is_rollback=True) → A2A → Validator → 结果邮件（无回滚链接）

    Args:
        event: 异步回滚事件
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

    logger.info(f"Starting async rollback for task {task_id}")

    try:
        # 调用 Remediator with is_rollback=True
        # Remediator 会通过 A2A 调用 Validator，Validator 会发送无回滚链接的结果邮件
        rollback_result = run_phase2_remediation(
            task_id=task_id,
            memory_session_id=memory_session_id,
            actor_id=actor_id,
            finding_id=finding_id,
            resource_arn=resource_arn,
            resource_type=resource_type,
            control_id=control_id,
            is_rollback=True  # 重要: 这会让 Validator 发送不带回滚链接的邮件
        )

        if not rollback_result.get('success'):
            update_task_status(task_id, 'rollback_failed', {
                'error': rollback_result.get('error', 'Unknown error')
            })
            logger.error(f"Rollback failed for task {task_id}: {rollback_result.get('error')}")
            return {
                'success': False,
                'task_id': task_id,
                'error': rollback_result.get('error')
            }

        update_task_status(task_id, 'rolled_back')

        logger.info(f"Rollback completed for task {task_id}")

        return {
            'success': True,
            'task_id': task_id,
            'status': 'rolled_back',
            'response': rollback_result.get('response')
        }

    except Exception as e:
        logger.exception(f"Async rollback failed for task {task_id}: {e}")
        update_task_status(task_id, 'rollback_failed', {'error': str(e)})
        return {
            'success': False,
            'task_id': task_id,
            'error': str(e)
        }


def handle_send_result_email(event: dict, context) -> dict:
    """处理发送结果邮件请求

    由 Validator Agent 的 trigger_result_email 工具调用。

    Args:
        event: 邮件发送请求事件
        context: Lambda 上下文

    Returns:
        dict: 发送结果
    """
    task_id = event.get('task_id')
    resource_arn = event.get('resource_arn', '')
    control_id = event.get('control_id', '')
    email_type = event.get('email_type', 'remediation_result')
    is_rollback = event.get('is_rollback', False)
    rollback_failed = event.get('rollback_failed', False)
    include_rollback_link = event.get('include_rollback_link', not is_rollback)
    error_message = event.get('error_message')
    code_review = event.get('code_review', {})
    validation = event.get('validation', {})

    logger.info(f"Sending result email for task {task_id}, email_type={email_type}, is_rollback={is_rollback}")

    # 检查邮件配置
    if not SENDER_EMAIL or not RESULT_EMAIL:
        logger.warning("SENDER_EMAIL or RESULT_EMAIL not configured")
        return {
            'success': False,
            'error': 'Email configuration missing. Set SENDER_EMAIL and RESULT_EMAIL.'
        }

    try:
        # 获取任务信息（可选，用于补充信息）
        task = get_task(task_id)

        # 生成回滚 token（如果需要）
        rollback_url = None
        if include_rollback_link and not is_rollback:
            rollback_token = generate_rollback_token(task_id)
            base_url = API_GATEWAY_URL.rstrip('/') if API_GATEWAY_URL else 'https://your-api-gateway-url'
            rollback_url = f"{base_url}/api/v1/approvals/{task_id}/respond?token={rollback_token}&action=rollback"

        # 格式化邮件内容
        email_body = format_result_email_body(
            task_id=task_id,
            resource_arn=resource_arn,
            control_id=control_id,
            email_type=email_type,
            code_review=code_review,
            validation=validation,
            rollback_url=rollback_url,
            is_rollback=is_rollback,
            rollback_failed=rollback_failed,
            error_message=error_message,
            task=task
        )

        # 确定邮件主题
        if rollback_failed:
            subject = f'[SHARA] ❌ 回滚失败 - {control_id}'
        elif is_rollback:
            subject = f'[SHARA] ↩️ 回滚完成 - {control_id}'
        elif validation.get('passed', False):
            subject = f'[SHARA] ✅ 修复成功 - {control_id}'
        else:
            subject = f'[SHARA] ⚠️ 修复完成(需验证) - {control_id}'

        # 发送邮件
        ses_client.send_email(
            Source=SENDER_EMAIL,
            Destination={'ToAddresses': [RESULT_EMAIL]},
            Message={
                'Subject': {
                    'Data': subject,
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

        logger.info(f"Result email sent for task {task_id}")

        return {
            'success': True,
            'sent': True,
            'task_id': task_id,
            'email_type': email_type,
            'includes_rollback_link': rollback_url is not None
        }

    except ClientError as e:
        logger.error(f"SES error sending email: {e}")
        return {
            'success': False,
            'error': f"Failed to send email: {str(e)}"
        }
    except Exception as e:
        logger.exception(f"Failed to send result email for task {task_id}: {e}")
        return {
            'success': False,
            'task_id': task_id,
            'error': str(e)
        }


def generate_rollback_token(task_id: str) -> str:
    """生成回滚 token"""
    import hashlib
    from datetime import timedelta

    token = str(uuid.uuid4())
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expiry_time = datetime.now(timezone.utc) + timedelta(hours=ROLLBACK_TOKEN_EXPIRY_HOURS)
    ttl = int(expiry_time.timestamp())

    try:
        tokens_table.put_item(Item={
            'PK': f'TOKEN#{token_hash}',
            'SK': f'TASK#{task_id}',
            'token': token,
            'token_hash': token_hash,
            'task_id': task_id,
            'action': 'rollback',
            'createdAt': datetime.now(timezone.utc).isoformat(),
            'expiresAt': expiry_time.isoformat(),
            'expires_at': ttl,
            'used': False
        })
        logger.info(f"Generated rollback token for task {task_id}")
    except Exception as e:
        logger.warning(f"Failed to save rollback token: {e}")

    return token


def format_result_email_body(
    task_id: str,
    resource_arn: str,
    control_id: str,
    email_type: str,
    code_review: dict,
    validation: dict,
    rollback_url: Optional[str],
    is_rollback: bool,
    rollback_failed: bool,
    error_message: Optional[str],
    task: Optional[dict]
) -> str:
    """格式化结果邮件内容"""
    import unicodedata

    def get_display_width(s: str) -> int:
        """计算字符串的显示宽度"""
        width = 0
        for char in s:
            if unicodedata.east_asian_width(char) in ('F', 'W'):
                width += 2
            elif ord(char) >= 0x1F300:
                width += 2
            else:
                width += 1
        return width

    def pad_to_width(s: str, target_width: int) -> str:
        """将字符串填充到指定的显示宽度"""
        current_width = get_display_width(s)
        padding = target_width - current_width
        if padding > 0:
            return s + ' ' * padding
        return s

    # 确定操作类型和状态
    if rollback_failed:
        operation = "回滚"
        status_icon = "❌"
        status_text = "失败"
    elif is_rollback:
        operation = "回滚"
        status_icon = "✅"
        status_text = "成功"
    else:
        operation = "修复"
        validation_passed = validation.get('passed', False)
        code_review_passed = code_review.get('status') == 'passed'
        if validation_passed and code_review_passed:
            status_icon = "✅"
            status_text = "成功"
        else:
            status_icon = "⚠️"
            status_text = "完成(需验证)"

    # 代码审查结果
    code_status = code_review.get('status', 'unknown')
    code_icons = {'passed': '✅', 'warning': '⚠️', 'rejected': '❌'}
    code_icon = code_icons.get(code_status, '❓')
    risk_level = code_review.get('risk_level', 'unknown')
    issues_count = code_review.get('issues_count', 0)

    # 验证结果
    validation_passed = validation.get('passed', False)
    validation_icon = '✅' if validation_passed else '❌'
    checks_count = validation.get('checks_count', 0)

    lines = [
        '═' * 70,
        f'           {status_icon} SHARA {operation}结果通知 - {status_text}',
        '═' * 70,
        '',
        '📋 任务信息',
        '─' * 70,
        f'  任务 ID:      {task_id}',
        f'  Control ID:   {control_id}',
        f'  资源:         {resource_arn}',
        f'  操作类型:     {operation}',
        '',
    ]

    # 错误信息 (如果有)
    if error_message:
        lines.extend([
            '❌ 错误信息',
            '─' * 70,
            f'  {error_message}',
            '',
        ])

    # 代码审查结果
    lines.extend([
        '🔍 代码审查结果',
        '─' * 70,
    ])

    box_width = 50
    lines.extend([
        '  ┌' + '─' * box_width + '┐',
        '  │' + pad_to_width(f'  状态:       {code_icon} {code_status.upper()}', box_width) + '│',
        '  │' + pad_to_width(f'  风险等级:   {risk_level.upper()}', box_width) + '│',
        '  │' + pad_to_width(f'  问题数量:   {issues_count}', box_width) + '│',
        '  └' + '─' * box_width + '┘',
        '',
    ])

    # 验证结果
    lines.extend([
        '✓ 验证结果',
        '─' * 70,
    ])

    lines.extend([
        '  ┌' + '─' * box_width + '┐',
        '  │' + pad_to_width(f'  验证状态:   {validation_icon} {"通过" if validation_passed else "未通过"}', box_width) + '│',
        '  │' + pad_to_width(f'  检查项数:   {checks_count}', box_width) + '│',
        '  └' + '─' * box_width + '┘',
        '',
    ])

    # 回滚链接 (仅正常修复时显示)
    if rollback_url and not is_rollback:
        lines.extend([
            '↩️ 回滚操作',
            '─' * 70,
            '  如果此修复造成问题，您可以点击以下链接回滚:',
            '',
            f'  回滚链接: {rollback_url}',
            '',
            f'  ⏰ 此回滚链接将在 {ROLLBACK_TOKEN_EXPIRY_HOURS} 小时后过期',
            '',
        ])
    elif is_rollback:
        lines.extend([
            '📝 备注',
            '─' * 70,
            '  此为回滚操作结果通知。',
            '  回滚操作不提供二次回滚链接。',
            '',
        ])

    lines.extend([
        '═' * 70,
        '                SHARA - Security Hub Auto-Remediation Agent',
        '                          Powered by AWS Bedrock',
        '═' * 70,
    ])

    return '\n'.join(lines)


def run_phase2_remediation(
    task_id: str,
    memory_session_id: str,
    actor_id: str,
    finding_id: str,
    resource_arn: str,
    resource_type: str,
    control_id: str,
    is_rollback: bool = False
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
        is_rollback: 是否为回滚操作 (True 时回滚邮件不包含回滚链接)

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
        if is_rollback:
            update_task_status(task_id, 'rollback_started')
        else:
            update_task_status(task_id, 'generating_code')

        # 构建 Agent 输入 (包含所有信息供 Remediator 传递给 Validator)
        agent_input = {
            'task_id': task_id,
            'memory_session_id': memory_session_id,
            'memory_id': MEMORY_ID,  # 传递 Memory ID 给 Remediator
            'actor_id': actor_id,
            'finding_id': finding_id,
            'resource_arn': resource_arn,
            'resource_type': resource_type,
            'control_id': control_id,
            'is_rollback': is_rollback
        }

        update_task_status(task_id, 'executing')

        # 调用 AgentCore Runtime (Remediator 会通过 A2A 调用 Validator)
        response_data = _invoke_runtime(
            runtime_arn=REMEDIATOR_RUNTIME_ARN,
            session_id=memory_session_id,
            agent_input=agent_input,
            timeout=900  # 增加超时时间，因为包含验证步骤
        )

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
