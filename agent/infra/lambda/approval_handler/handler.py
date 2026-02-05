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
ROLLBACK_TOKEN_EXPIRY_HOURS = int(os.environ.get('ROLLBACK_TOKEN_EXPIRY_HOURS', '24'))
# GitHub 配置 (容器漏洞修复)
GITHUB_OWNER = os.environ.get('GITHUB_OWNER', 'Wyifei')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'awsome')

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

    # 验证 task 存在
    task = get_task(task_id)
    if not task:
        logger.error(f"Task {task_id} not found, cannot perform remediation")
        return {
            'success': False,
            'task_id': task_id,
            'error': f'Task {task_id} not found'
        }

    # 从 task 元数据获取修复类型
    remediation_type = task.get('remediationType', 'aws_api')
    logger.info(f"Task {task_id} remediation_type: {remediation_type}")

    try:
        # Phase 2: 执行修复 (Remediator 会通过 A2A 调用 Validator)
        remediation_result = run_phase2_remediation(
            task_id=task_id,
            memory_session_id=memory_session_id,
            actor_id=actor_id,
            finding_id=finding_id,
            resource_arn=resource_arn,
            resource_type=resource_type,
            control_id=control_id,
            remediation_type=remediation_type,
            github_owner=GITHUB_OWNER,
            github_repo=GITHUB_REPO
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
    # 也允许状态为 executing 但邮件已发送的情况（解决邮件发送与状态更新之间的时序问题）
    current_status = task.get('status')
    result_email_sent = task.get('resultEmailSent', False)

    can_rollback = (
        current_status in ['completed', 'validated'] or
        (current_status == 'executing' and result_email_sent)
    )

    if not can_rollback:
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

    # 验证 task 存在
    task = get_task(task_id)
    if not task:
        logger.error(f"Task {task_id} not found, cannot perform rollback")
        return {
            'success': False,
            'task_id': task_id,
            'error': f'Task {task_id} not found'
        }

    # 从 task 元数据获取修复类型
    remediation_type = task.get('remediationType', 'aws_api')
    logger.info(f"Task {task_id} remediation_type: {remediation_type}")

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
            is_rollback=True,  # 重要: 这会让 Validator 发送不带回滚链接的邮件
            remediation_type=remediation_type,
            github_owner=GITHUB_OWNER,
            github_repo=GITHUB_REPO
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
    支持两种修复类型:
    - aws_api: AWS 配置修复，显示代码审查和验证结果
    - github_pr: 容器漏洞修复，显示 PR 信息和文件变更

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
    remediation_type = event.get('remediation_type', 'aws_api')
    is_rollback = event.get('is_rollback', False)
    rollback_failed = event.get('rollback_failed', False)
    include_rollback_link = event.get('include_rollback_link', not is_rollback)
    error_message = event.get('error_message')
    code_review = event.get('code_review', {})
    validation = event.get('validation', {})
    # GitHub PR mode specific fields
    pr_info = event.get('pr_info', {})
    vulnerabilities = event.get('vulnerabilities', [])  # 漏洞列表从 Memory 获取，通过 event 传递

    logger.info(f"Sending result email for task {task_id}, email_type={email_type}, remediation_type={remediation_type}, is_rollback={is_rollback}")

    # 防重复检查: 根据操作类型检查对应的邮件发送状态
    if task_id:
        task = get_task(task_id)
        if task:
            if is_rollback:
                # 回滚邮件检查 rollbackEmailSent
                if task.get('rollbackEmailSent'):
                    logger.warning(f"Rollback email already sent for task {task_id}, skipping duplicate send")
                    return {
                        'success': True,
                        'sent': False,
                        'task_id': task_id,
                        'message': 'Rollback email already sent, skipping duplicate',
                        'already_sent': True
                    }
            else:
                # 修复结果邮件检查 resultEmailSent
                if task.get('resultEmailSent'):
                    logger.warning(f"Result email already sent for task {task_id}, skipping duplicate send")
                    return {
                        'success': True,
                        'sent': False,
                        'task_id': task_id,
                        'message': 'Email already sent, skipping duplicate',
                        'already_sent': True
                    }

    # 在发送邮件前，标记邮件已发送（用于回滚检查）
    # 注意: 不更新 status，只设置邮件发送标记，避免触发状态变更相关的事件
    if task_id and not rollback_failed:
        try:
            _mark_email_sent(task_id, is_rollback=is_rollback)
            email_type_desc = "rollback" if is_rollback else "result"
            logger.info(f"Marked {email_type_desc} email sent for task {task_id}")
        except Exception as e:
            logger.warning(f"Failed to mark email sent: {e}")

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

        # 格式化邮件内容 - 根据 remediation_type 使用不同模板
        if remediation_type == 'github_pr':
            # GitHub PR 修复邮件
            email_body = format_github_pr_result_email(
                task_id=task_id,
                resource_arn=resource_arn,
                pr_info=pr_info,
                validation=validation,
                error_message=error_message,
                vulnerabilities=vulnerabilities  # 从 Memory 获取，通过 event 传递
            )
            # GitHub PR 邮件主题
            pr_number = pr_info.get('pr_number', 'N/A')
            pr_state = pr_info.get('state', 'open')
            if error_message:
                subject = f'[SHARA] ❌ 容器漏洞修复失败 - PR #{pr_number}'
            elif validation.get('pr_verified', False):
                subject = f'[SHARA] ✅ 容器漏洞修复 PR 已创建 - #{pr_number}'
            else:
                subject = f'[SHARA] ⚠️ 容器漏洞修复 PR 待审核 - #{pr_number}'
        else:
            # AWS API 修复邮件 (原有逻辑)
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
            # AWS API 邮件主题
            if rollback_failed:
                subject = f'[SHARA] ❌ 回滚失败 - {control_id}'
            elif is_rollback:
                subject = f'[SHARA] ↩️ 回滚完成 - {control_id}'
            elif validation.get('passed', False):
                subject = f'[SHARA] ✅ 修复成功 - {control_id}'
            else:
                subject = f'[SHARA] ⚠️ 修复完成(需验证) - {control_id}'

        # 发送邮件 (HTML 格式)
        ses_client.send_email(
            Source=SENDER_EMAIL,
            Destination={'ToAddresses': [RESULT_EMAIL]},
            Message={
                'Subject': {
                    'Data': subject,
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
    """格式化结果邮件内容 (HTML 格式)"""

    # 确定操作类型和状态
    if rollback_failed:
        operation = "回滚"
        status_icon = "❌"
        status_text = "失败"
        header_color = "#dc3545"
    elif is_rollback:
        operation = "回滚"
        status_icon = "✅"
        status_text = "成功"
        header_color = "#17a2b8"
    else:
        operation = "修复"
        validation_passed = validation.get('passed', False)
        code_review_passed = code_review.get('status') == 'passed'
        if validation_passed and code_review_passed:
            status_icon = "✅"
            status_text = "成功"
            header_color = "#28a745"
        else:
            status_icon = "⚠️"
            status_text = "完成(需验证)"
            header_color = "#ffc107"

    # 代码审查结果
    code_status = code_review.get('status', 'unknown')
    code_status_colors = {
        'passed': ('#28a745', '#fff'),
        'warning': ('#ffc107', '#000'),
        'rejected': ('#dc3545', '#fff')
    }
    code_bg, code_fg = code_status_colors.get(code_status, ('#6c757d', '#fff'))
    risk_level = code_review.get('risk_level', 'unknown')
    risk_colors = {
        'low': ('#28a745', '#fff'),
        'medium': ('#ffc107', '#000'),
        'high': ('#dc3545', '#fff'),
        'critical': ('#dc3545', '#fff')
    }
    risk_bg, risk_fg = risk_colors.get(risk_level.lower(), ('#6c757d', '#fff'))
    issues_count = code_review.get('issues_count', 0)
    code_issues = code_review.get('issues', [])
    code_recommendations = code_review.get('recommendations', [])

    # 验证结果
    validation_passed = validation.get('passed', False)
    checks_count = validation.get('checks_count', 0)
    validation_checks = validation.get('checks', [])
    validation_summary = validation.get('summary', '')

    # HTML 模板
    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 700px; margin: 0 auto; padding: 20px; }}
        .header {{ background: {header_color}; color: white; padding: 20px; border-radius: 8px 8px 0 0; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 22px; }}
        .content {{ background: #fff; border: 1px solid #e0e0e0; border-top: none; padding: 20px; border-radius: 0 0 8px 8px; }}
        .section {{ margin-bottom: 24px; }}
        .section-title {{ font-size: 15px; font-weight: 600; color: #333; border-bottom: 2px solid #1a73e8; padding-bottom: 8px; margin-bottom: 12px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        td {{ padding: 8px 12px; vertical-align: top; }}
        .label {{ font-weight: 500; color: #666; width: 120px; }}
        .value {{ color: #333; }}
        .badge {{ display: inline-block; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: 600; }}
        .result-box {{ background: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 6px; padding: 16px; margin-top: 8px; }}
        .result-row {{ margin-bottom: 12px; }}
        .result-row:last-child {{ margin-bottom: 0; }}
        .result-label {{ font-weight: 500; color: #666; display: inline-block; width: 100px; }}
        .btn {{ display: inline-block; padding: 12px 32px; border-radius: 6px; text-decoration: none; font-weight: 600; }}
        .btn-rollback {{ background: #ffc107; color: #000 !important; }}
        .btn-container {{ text-align: center; margin: 24px 0; }}
        .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 24px; padding-top: 16px; border-top: 1px solid #e0e0e0; }}
        .error-box {{ background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 6px; padding: 12px; margin: 16px 0; color: #721c24; }}
        .info-box {{ background: #d1ecf1; border: 1px solid #bee5eb; border-radius: 6px; padding: 12px; margin: 16px 0; color: #0c5460; }}
        code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-family: monospace; font-size: 13px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{status_icon} SHARA {operation}结果通知 - {status_text}</h1>
    </div>
    <div class="content">
        <!-- 任务信息 -->
        <div class="section">
            <div class="section-title">📋 任务信息</div>
            <table>
                <tr><td class="label">任务 ID</td><td class="value"><code>{task_id}</code></td></tr>
                <tr><td class="label">Control ID</td><td class="value"><strong>{control_id}</strong></td></tr>
                <tr><td class="label">资源</td><td class="value"><code style="word-break: break-all;">{resource_arn}</code></td></tr>
                <tr><td class="label">操作类型</td><td class="value">{operation}</td></tr>
            </table>
        </div>
'''

    # 错误信息 (如果有)
    if error_message:
        html += f'''
        <!-- 错误信息 -->
        <div class="section">
            <div class="section-title">❌ 错误信息</div>
            <div class="error-box">
                {error_message}
            </div>
        </div>
'''

    # 代码审查结果
    html += f'''
        <!-- 代码审查结果 -->
        <div class="section">
            <div class="section-title">🔍 代码审查结果</div>
            <div class="result-box">
                <div class="result-row">
                    <span class="result-label">状态</span>
                    <span class="badge" style="background:{code_bg};color:{code_fg}">{code_status.upper()}</span>
                </div>
                <div class="result-row">
                    <span class="result-label">风险等级</span>
                    <span class="badge" style="background:{risk_bg};color:{risk_fg}">{risk_level.upper()}</span>
                </div>
                <div class="result-row">
                    <span class="result-label">问题数量</span>
                    <span>{issues_count}</span>
                </div>
            </div>
'''

    # 代码审查问题明细
    if code_issues:
        html += '''            <div style="margin-top: 12px;">
                <strong>发现的问题:</strong>
                <table style="width:100%;border-collapse:collapse;margin-top:8px;font-size:13px;">
                    <tr style="background:#f8f9fa;">
                        <th style="padding:8px;text-align:left;border:1px solid #e0e0e0;">类型</th>
                        <th style="padding:8px;text-align:left;border:1px solid #e0e0e0;">描述</th>
                        <th style="padding:8px;text-align:left;border:1px solid #e0e0e0;">严重程度</th>
                    </tr>
'''
        for issue in code_issues[:5]:  # 最多显示5个问题
            issue_type = issue.get('type', 'unknown')
            issue_msg = issue.get('message', '')
            issue_severity = issue.get('severity', 'unknown')
            severity_colors = {'high': '#dc3545', 'medium': '#ffc107', 'low': '#28a745'}
            severity_color = severity_colors.get(issue_severity, '#6c757d')
            html += f'''                    <tr>
                        <td style="padding:8px;border:1px solid #e0e0e0;">{issue_type}</td>
                        <td style="padding:8px;border:1px solid #e0e0e0;">{issue_msg}</td>
                        <td style="padding:8px;border:1px solid #e0e0e0;"><span style="color:{severity_color};font-weight:600;">{issue_severity.upper()}</span></td>
                    </tr>
'''
        html += '''                </table>
            </div>
'''
        if len(code_issues) > 5:
            html += f'            <p style="color:#666;font-size:12px;margin-top:4px;">... 还有 {len(code_issues) - 5} 个问题未显示</p>\n'
    else:
        html += '''            <div style="margin-top: 12px;">
                <span style="color:#28a745;">✅ 未发现安全问题</span>
            </div>
'''

    # 代码审查建议
    if code_recommendations:
        html += '            <div style="margin-top: 12px;"><strong>建议:</strong><ul style="margin:4px 0;padding-left:20px;">\n'
        for rec in code_recommendations[:3]:
            html += f'                <li style="color:#555;">{rec}</li>\n'
        html += '            </ul></div>\n'

    html += '        </div>\n'

    # 验证结果
    html += f'''
        <!-- 验证结果 -->
        <div class="section">
            <div class="section-title">✓ 验证结果</div>
            <div class="result-box">
                <div class="result-row">
                    <span class="result-label">验证状态</span>
                    <span class="badge" style="background:{'#28a745' if validation_passed else '#dc3545'};color:#fff">{'✅ 通过' if validation_passed else '❌ 未通过'}</span>
                </div>
                <div class="result-row">
                    <span class="result-label">检查项数</span>
                    <span>{checks_count}</span>
                </div>
            </div>
'''

    # 验证检查项明细
    if validation_checks:
        html += '''            <div style="margin-top: 12px;">
                <strong>检查项明细:</strong>
                <table style="width:100%;border-collapse:collapse;margin-top:8px;font-size:13px;">
                    <tr style="background:#f8f9fa;">
                        <th style="padding:8px;text-align:left;border:1px solid #e0e0e0;">检查项</th>
                        <th style="padding:8px;text-align:left;border:1px solid #e0e0e0;">期望值</th>
                        <th style="padding:8px;text-align:left;border:1px solid #e0e0e0;">实际值</th>
                        <th style="padding:8px;text-align:center;border:1px solid #e0e0e0;">结果</th>
                    </tr>
'''
        for check in validation_checks:
            check_name = check.get('name', 'unknown')
            check_expected = check.get('expected', 'N/A')
            check_actual = check.get('actual', 'N/A')
            check_passed = check.get('passed', False)
            result_icon = '✅' if check_passed else '❌'
            result_color = '#28a745' if check_passed else '#dc3545'
            # 格式化布尔值显示
            expected_display = 'True' if check_expected is True else ('False' if check_expected is False else str(check_expected))
            actual_display = 'True' if check_actual is True else ('False' if check_actual is False else str(check_actual))
            html += f'''                    <tr>
                        <td style="padding:8px;border:1px solid #e0e0e0;"><code>{check_name}</code></td>
                        <td style="padding:8px;border:1px solid #e0e0e0;">{expected_display}</td>
                        <td style="padding:8px;border:1px solid #e0e0e0;">{actual_display}</td>
                        <td style="padding:8px;border:1px solid #e0e0e0;text-align:center;"><span style="color:{result_color};">{result_icon}</span></td>
                    </tr>
'''
        html += '''                </table>
            </div>
'''
    else:
        html += '''            <div style="margin-top: 12px;">
                <span style="color:#666;">暂无检查项明细</span>
            </div>
'''

    # 验证摘要
    if validation_summary:
        html += f'            <div style="margin-top: 12px;color:#555;"><strong>摘要:</strong> {validation_summary}</div>\n'

    html += '        </div>\n'
    html += '''
'''

    # 回滚链接 (仅正常修复时显示)
    if rollback_url and not is_rollback:
        html += f'''
        <!-- 回滚操作 -->
        <div class="section">
            <div class="section-title">↩️ 回滚操作</div>
            <p>如果此修复造成问题，您可以点击以下按钮回滚:</p>
            <div class="btn-container">
                <a href="{rollback_url}" class="btn btn-rollback">↩️ 回滚此修复</a>
            </div>
            <p style="text-align: center; color: #666; font-size: 12px;">⏰ 此回滚链接将在 {ROLLBACK_TOKEN_EXPIRY_HOURS} 小时后过期</p>
        </div>
'''
    elif is_rollback:
        html += '''
        <!-- 备注 -->
        <div class="section">
            <div class="section-title">📝 备注</div>
            <div class="info-box">
                <p style="margin: 0;">此为回滚操作结果通知。</p>
                <p style="margin: 8px 0 0 0;">回滚操作不提供二次回滚链接。</p>
            </div>
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


def format_github_pr_result_email(
    task_id: str,
    resource_arn: str,
    pr_info: dict,
    validation: dict,
    error_message: Optional[str],
    vulnerabilities: list = None
) -> str:
    """格式化 GitHub PR 结果邮件内容 (HTML 格式)

    用于容器漏洞修复的 PR 结果通知邮件。
    漏洞信息从 Memory 获取，通过 event 传递。

    Args:
        task_id: 任务 ID
        resource_arn: 资源 ARN (ECR 镜像)
        pr_info: PR 信息
            - pr_number: PR 编号
            - pr_url: PR 链接
            - title: PR 标题
            - state: PR 状态
            - files_changed: 变更的文件列表
        validation: 验证结果
            - pr_verified: PR 是否已验证
            - files_verified: 文件是否已验证
            - summary: 验证摘要
        error_message: 错误信息 (如果有)
        task: 任务详情 (可选)

    Returns:
        str: HTML 格式的邮件内容
    """
    # 提取 PR 信息
    pr_number = pr_info.get('pr_number', 'N/A')
    pr_url = pr_info.get('pr_url', '#')
    pr_title = pr_info.get('title', '容器漏洞修复')
    pr_state = pr_info.get('state', 'open')
    files_changed = pr_info.get('files_changed', [])

    # 验证状态
    pr_verified = validation.get('pr_verified', False)
    files_verified = validation.get('files_verified', False)
    validation_summary = validation.get('summary', '')

    # 确定状态和颜色
    if error_message:
        status_icon = "❌"
        status_text = "失败"
        header_color = "#dc3545"
    elif pr_verified and files_verified:
        status_icon = "✅"
        status_text = "成功"
        header_color = "#28a745"
    else:
        status_icon = "⚠️"
        status_text = "待审核"
        header_color = "#ffc107"

    # PR 状态显示
    pr_state_display = {
        'open': ('🟢 Open', '#28a745'),
        'closed': ('🔴 Closed', '#dc3545'),
        'merged': ('🟣 Merged', '#6f42c1')
    }
    pr_state_text, pr_state_color = pr_state_display.get(pr_state, ('⚪ Unknown', '#6c757d'))

    # HTML 模板
    html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 700px; margin: 0 auto; padding: 20px; }}
        .header {{ background: {header_color}; color: white; padding: 20px; border-radius: 8px 8px 0 0; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 22px; }}
        .content {{ background: #fff; border: 1px solid #e0e0e0; border-top: none; padding: 20px; border-radius: 0 0 8px 8px; }}
        .section {{ margin-bottom: 24px; }}
        .section-title {{ font-size: 15px; font-weight: 600; color: #333; border-bottom: 2px solid #1a73e8; padding-bottom: 8px; margin-bottom: 12px; }}
        table {{ width: 100%; border-collapse: collapse; }}
        td {{ padding: 8px 12px; vertical-align: top; }}
        .label {{ font-weight: 500; color: #666; width: 120px; }}
        .value {{ color: #333; }}
        .badge {{ display: inline-block; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: 600; }}
        .result-box {{ background: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 6px; padding: 16px; margin-top: 8px; }}
        .result-row {{ margin-bottom: 12px; }}
        .result-row:last-child {{ margin-bottom: 0; }}
        .result-label {{ font-weight: 500; color: #666; display: inline-block; width: 100px; }}
        .btn {{ display: inline-block; padding: 12px 32px; border-radius: 6px; text-decoration: none; font-weight: 600; }}
        .btn-pr {{ background: #28a745; color: #fff !important; }}
        .btn-container {{ text-align: center; margin: 24px 0; }}
        .footer {{ text-align: center; color: #666; font-size: 12px; margin-top: 24px; padding-top: 16px; border-top: 1px solid #e0e0e0; }}
        .error-box {{ background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 6px; padding: 12px; margin: 16px 0; color: #721c24; }}
        .info-box {{ background: #d1ecf1; border: 1px solid #bee5eb; border-radius: 6px; padding: 12px; margin: 16px 0; color: #0c5460; }}
        code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-family: monospace; font-size: 13px; }}
        .file-list {{ background: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 6px; padding: 12px; margin-top: 8px; }}
        .file-item {{ padding: 6px 0; border-bottom: 1px solid #e0e0e0; font-family: monospace; font-size: 13px; }}
        .file-item:last-child {{ border-bottom: none; }}
        .file-icon {{ margin-right: 8px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{status_icon} SHARA 容器漏洞修复通知 - {status_text}</h1>
    </div>
    <div class="content">
        <!-- 任务信息 -->
        <div class="section">
            <div class="section-title">📋 任务信息</div>
            <table>
                <tr><td class="label">任务 ID</td><td class="value"><code>{task_id}</code></td></tr>
                <tr><td class="label">修复类型</td><td class="value">🐳 容器漏洞修复 (GitHub PR)</td></tr>
                <tr><td class="label">镜像</td><td class="value"><code style="word-break: break-all;">{resource_arn}</code></td></tr>
            </table>
        </div>
'''

    # 错误信息 (如果有)
    if error_message:
        html += f'''
        <!-- 错误信息 -->
        <div class="section">
            <div class="section-title">❌ 错误信息</div>
            <div class="error-box">
                {error_message}
            </div>
        </div>
'''

    # PR 信息
    html += f'''
        <!-- Pull Request 信息 -->
        <div class="section">
            <div class="section-title">🔀 Pull Request 信息</div>
            <div class="result-box">
                <div class="result-row">
                    <span class="result-label">PR 编号</span>
                    <span><strong>#{pr_number}</strong></span>
                </div>
                <div class="result-row">
                    <span class="result-label">标题</span>
                    <span>{pr_title}</span>
                </div>
                <div class="result-row">
                    <span class="result-label">状态</span>
                    <span class="badge" style="background:{pr_state_color};color:#fff">{pr_state_text}</span>
                </div>
            </div>
'''

    # PR 链接按钮
    if pr_url and pr_url != '#':
        html += f'''
            <div class="btn-container">
                <a href="{pr_url}" class="btn btn-pr" target="_blank">🔗 查看 Pull Request</a>
            </div>
'''

    html += '        </div>\n'

    # 漏洞列表 (从 Memory 获取，通过 vulnerabilities 参数传递)
    vuln_list = vulnerabilities or []

    if vuln_list:
        # 按严重程度分组
        critical_vulns = [v for v in vuln_list if v.get('severity') == 'CRITICAL']
        high_vulns = [v for v in vuln_list if v.get('severity') == 'HIGH']
        total_count = len(vuln_list)
        critical_count = len(critical_vulns)
        high_count = len(high_vulns)

        html += f'''
        <!-- 漏洞列表 -->
        <div class="section">
            <div class="section-title">🔒 修复的漏洞 (共 {total_count} 个)</div>
            <div style="margin-bottom: 12px;">
                <span class="badge" style="background:#dc3545;color:#fff">CRITICAL: {critical_count}</span>
                <span class="badge" style="background:#fd7e14;color:#fff;margin-left:8px">HIGH: {high_count}</span>
            </div>
            <div class="result-box" style="max-height: 300px; overflow-y: auto;">
'''
        # 显示 CRITICAL 漏洞
        if critical_vulns:
            html += '                <div style="margin-bottom: 16px;"><strong style="color:#dc3545;">CRITICAL</strong></div>\n'
            for vuln in critical_vulns[:5]:  # 最多显示 5 个
                cve_id = vuln.get('cve_id', 'Unknown')
                pkg_name = vuln.get('package_name', 'Unknown')
                installed = vuln.get('installed_version', 'Unknown')
                fixed = vuln.get('fixed_version', 'Unknown')
                html += f'''                <div style="margin-bottom: 8px; padding: 8px; background: #fff; border-left: 3px solid #dc3545; border-radius: 4px;">
                    <div><strong>{cve_id}</strong></div>
                    <div style="font-size: 13px; color: #666;">{pkg_name}: {installed} → {fixed}</div>
                </div>
'''
            if len(critical_vulns) > 5:
                html += f'                <div style="color:#666;font-size:12px;margin-bottom:16px;">... 还有 {len(critical_vulns) - 5} 个 CRITICAL 漏洞</div>\n'

        # 显示 HIGH 漏洞
        if high_vulns:
            html += '                <div style="margin-bottom: 16px;"><strong style="color:#fd7e14;">HIGH</strong></div>\n'
            for vuln in high_vulns[:5]:  # 最多显示 5 个
                cve_id = vuln.get('cve_id', 'Unknown')
                pkg_name = vuln.get('package_name', 'Unknown')
                installed = vuln.get('installed_version', 'Unknown')
                fixed = vuln.get('fixed_version', 'Unknown')
                html += f'''                <div style="margin-bottom: 8px; padding: 8px; background: #fff; border-left: 3px solid #fd7e14; border-radius: 4px;">
                    <div><strong>{cve_id}</strong></div>
                    <div style="font-size: 13px; color: #666;">{pkg_name}: {installed} → {fixed}</div>
                </div>
'''
            if len(high_vulns) > 5:
                html += f'                <div style="color:#666;font-size:12px;">... 还有 {len(high_vulns) - 5} 个 HIGH 漏洞</div>\n'

        html += '''            </div>
        </div>
'''

    # 变更文件列表
    if files_changed:
        html += '''
        <!-- 变更文件 -->
        <div class="section">
            <div class="section-title">📁 变更文件</div>
            <div class="file-list">
'''
        for file_path in files_changed[:10]:  # 最多显示10个文件
            # 根据文件类型显示不同图标
            if file_path.endswith('.yaml') or file_path.endswith('.yml'):
                file_icon = '📄'
            elif file_path.endswith('.json'):
                file_icon = '📋'
            elif file_path.endswith('Dockerfile'):
                file_icon = '🐳'
            elif file_path.endswith('.tf'):
                file_icon = '🏗️'
            else:
                file_icon = '📝'
            html += f'''                <div class="file-item"><span class="file-icon">{file_icon}</span>{file_path}</div>
'''
        html += '''            </div>
'''
        if len(files_changed) > 10:
            html += f'            <p style="color:#666;font-size:12px;margin-top:4px;">... 还有 {len(files_changed) - 10} 个文件未显示</p>\n'
        html += '        </div>\n'

    # 验证结果
    html += f'''
        <!-- 验证结果 -->
        <div class="section">
            <div class="section-title">✓ 验证结果</div>
            <div class="result-box">
                <div class="result-row">
                    <span class="result-label">PR 验证</span>
                    <span class="badge" style="background:{'#28a745' if pr_verified else '#ffc107'};color:#fff">{'✅ 已验证' if pr_verified else '⏳ 待验证'}</span>
                </div>
                <div class="result-row">
                    <span class="result-label">文件验证</span>
                    <span class="badge" style="background:{'#28a745' if files_verified else '#ffc107'};color:#fff">{'✅ 已验证' if files_verified else '⏳ 待验证'}</span>
                </div>
            </div>
'''

    # 验证摘要
    if validation_summary:
        html += f'            <div style="margin-top: 12px;color:#555;"><strong>摘要:</strong> {validation_summary}</div>\n'

    html += '        </div>\n'

    # 下一步说明
    html += '''
        <!-- 下一步 -->
        <div class="section">
            <div class="section-title">📝 下一步</div>
            <div class="info-box">
                <p style="margin: 0;"><strong>请执行以下操作:</strong></p>
                <ol style="margin: 8px 0 0 0; padding-left: 20px;">
                    <li>点击上方按钮查看 Pull Request</li>
                    <li>审核代码变更是否符合预期</li>
                    <li>如无问题，合并 PR 以应用修复</li>
                    <li>合并后，重新构建并部署容器镜像</li>
                </ol>
            </div>
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


def run_phase2_remediation(
    task_id: str,
    memory_session_id: str,
    actor_id: str,
    finding_id: str,
    resource_arn: str,
    resource_type: str,
    control_id: str,
    is_rollback: bool = False,
    remediation_type: str = "aws_api",
    github_owner: str = "",
    github_repo: str = ""
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
        remediation_type: 修复类型 ("aws_api" 或 "github_pr")
        github_owner: GitHub Owner (github_pr 模式需要)
        github_repo: GitHub Repo (github_pr 模式需要)

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
            'is_rollback': is_rollback,
            'remediation_type': remediation_type
        }

        # GitHub PR 模式需要额外参数
        if remediation_type == 'github_pr':
            agent_input['github_owner'] = github_owner or GITHUB_OWNER
            agent_input['github_repo'] = github_repo or GITHUB_REPO
            logger.info(f"GitHub PR mode: owner={agent_input['github_owner']}, repo={agent_input['github_repo']}")

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


def _mark_email_sent(task_id: str, is_rollback: bool = False):
    """标记邮件已发送

    根据操作类型设置不同的字段:
    - 修复结果邮件: resultEmailSent, resultEmailSentAt
    - 回滚结果邮件: rollbackEmailSent, rollbackEmailSentAt

    只更新邮件发送标记，不更新 status。
    这样可以避免触发状态变更相关的事件/流，同时允许回滚检查通过。

    Args:
        task_id: 任务 ID
        is_rollback: 是否为回滚邮件
    """
    now = datetime.now(timezone.utc).isoformat()

    if is_rollback:
        sent_field = 'rollbackEmailSent'
        sent_at_field = 'rollbackEmailSentAt'
    else:
        sent_field = 'resultEmailSent'
        sent_at_field = 'resultEmailSentAt'

    try:
        tasks_table.update_item(
            Key={'PK': f'TASK#{task_id}', 'SK': 'METADATA'},
            UpdateExpression=f'SET {sent_field} = :sent, {sent_at_field} = :sentAt',
            ExpressionAttributeValues={
                ':sent': True,
                ':sentAt': now
            },
            ConditionExpression='attribute_exists(PK)'
        )
    except tasks_table.meta.client.exceptions.ConditionalCheckFailedException:
        logger.warning(f"Task {task_id} does not exist, cannot mark email sent")
    except Exception as e:
        logger.exception(f"Error marking {sent_field}: {e}")


def update_task_status(task_id: str, status: str, extra_data: dict = None):
    """更新任务状态

    注意: 只更新已存在的记录，不会创建新记录。
    如果记录不存在，会抛出 ConditionalCheckFailedException。
    """
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

    try:
        tasks_table.update_item(
            Key={'PK': f'TASK#{task_id}', 'SK': 'METADATA'},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values,
            ExpressionAttributeNames=expr_names,
            ConditionExpression='attribute_exists(PK)'  # 确保记录已存在
        )
    except tasks_table.meta.client.exceptions.ConditionalCheckFailedException:
        logger.warning(f"Task {task_id} does not exist, skipping status update to '{status}'")
        raise ValueError(f"Task {task_id} does not exist")


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
