"""
Approval Handler Lambda

处理审批回调请求:
- 验证审批令牌
- 执行或拒绝修复操作
- 更新任务状态
"""

import json
import logging
import os
import hashlib
from datetime import datetime
from typing import Any, Optional
from urllib.parse import parse_qs

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


def lambda_handler(event: dict, context: Any) -> dict:
    """
    Lambda 入口点

    处理:
    1. GET /approve?token=xxx&action=approve|reject (邮件链接)
    2. POST /approve (程序化审批)
    """
    logger.info(f"Received event: {json.dumps(event, default=str)}")

    try:
        http_method = event.get("httpMethod", "")

        if http_method == "GET":
            return handle_email_approval(event)
        elif http_method == "POST":
            return handle_api_approval(event)
        else:
            return {
                "statusCode": 405,
                "body": json.dumps({"error": "Method not allowed"}),
            }

    except Exception as e:
        logger.exception(f"Error processing approval: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }


def handle_email_approval(event: dict) -> dict:
    """处理邮件中的审批链接"""
    query_params = event.get("queryStringParameters") or {}

    token = query_params.get("token", "")
    action = query_params.get("action", "").lower()

    if not token:
        return error_page("Missing token")

    if action not in ["approve", "reject"]:
        return error_page("Invalid action. Must be 'approve' or 'reject'")

    # 验证令牌
    token_data = verify_token(token)
    if not token_data:
        return error_page("Invalid or expired token")

    task_id = token_data.get("task_id", "")

    # 处理审批
    if action == "approve":
        result = approve_task(task_id, approved_by=token_data.get("approver", ""))
    else:
        result = reject_task(task_id, rejected_by=token_data.get("approver", ""))

    # 返回 HTML 页面
    return success_page(action, task_id, result)


def handle_api_approval(event: dict) -> dict:
    """处理程序化审批请求"""
    body = json.loads(event.get("body", "{}"))

    task_id = body.get("task_id", "")
    action = body.get("action", "").lower()
    approver = body.get("approver", "api")
    reason = body.get("reason", "")

    if not task_id:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "task_id required"}),
        }

    if action not in ["approve", "reject"]:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "action must be 'approve' or 'reject'"}),
        }

    # 处理审批
    if action == "approve":
        result = approve_task(task_id, approved_by=approver)
    else:
        result = reject_task(task_id, rejected_by=approver, reason=reason)

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(result, default=str),
    }


def verify_token(token: str) -> Optional[dict]:
    """
    验证审批令牌

    TODO: 实现实际的令牌验证逻辑
    - 查询 tokens 表
    - 检查是否过期
    - 检查是否已使用
    """
    # 简化实现：直接从令牌解析信息
    # 生产环境应查询数据库验证
    try:
        # 假设令牌格式: base64(task_id:approver:timestamp:signature)
        import base64

        decoded = base64.urlsafe_b64decode(token + "==").decode("utf-8")
        parts = decoded.split(":")

        if len(parts) >= 3:
            return {
                "task_id": parts[0],
                "approver": parts[1],
                "timestamp": parts[2],
            }
    except Exception as e:
        logger.error(f"Token verification failed: {e}")

    return None


def approve_task(task_id: str, approved_by: str) -> dict:
    """
    批准任务执行

    流程:
    1. 更新任务状态为 APPROVED
    2. 记录审批事件
    3. 触发修复执行 (TODO)
    """
    timestamp = datetime.utcnow().isoformat() + "Z"

    # 更新任务状态
    tasks_table.update_item(
        Key={"PK": f"TASK#{task_id}", "SK": "METADATA"},
        UpdateExpression="SET #status = :status, approved_by = :approver, approved_at = :timestamp, updated_at = :timestamp",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":status": "APPROVED",
            ":approver": approved_by,
            ":timestamp": timestamp,
        },
    )

    # 记录事件
    record_event(task_id, "TASK_APPROVED", {
        "approved_by": approved_by,
        "timestamp": timestamp,
    })

    # TODO: 触发 Agent 执行修复
    # 这里可以:
    # 1. 调用另一个 Lambda 执行修复
    # 2. 发送消息到 SQS 队列
    # 3. 调用 AgentCore Runtime

    logger.info(f"Task {task_id} approved by {approved_by}")

    return {
        "success": True,
        "task_id": task_id,
        "status": "APPROVED",
        "approved_by": approved_by,
        "message": "Remediation approved and queued for execution",
    }


def reject_task(task_id: str, rejected_by: str, reason: str = "") -> dict:
    """
    拒绝任务执行

    流程:
    1. 更新任务状态为 REJECTED
    2. 记录拒绝事件
    """
    timestamp = datetime.utcnow().isoformat() + "Z"

    # 更新任务状态
    tasks_table.update_item(
        Key={"PK": f"TASK#{task_id}", "SK": "METADATA"},
        UpdateExpression="SET #status = :status, rejected_by = :rejector, rejected_at = :timestamp, rejection_reason = :reason, updated_at = :timestamp",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":status": "REJECTED",
            ":rejector": rejected_by,
            ":timestamp": timestamp,
            ":reason": reason,
        },
    )

    # 记录事件
    record_event(task_id, "TASK_REJECTED", {
        "rejected_by": rejected_by,
        "reason": reason,
        "timestamp": timestamp,
    })

    logger.info(f"Task {task_id} rejected by {rejected_by}: {reason}")

    return {
        "success": True,
        "task_id": task_id,
        "status": "REJECTED",
        "rejected_by": rejected_by,
        "reason": reason,
        "message": "Remediation rejected",
    }


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


def error_page(message: str) -> dict:
    """返回错误 HTML 页面"""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>SHARA - Approval Error</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .error {{ color: #d32f2f; padding: 20px; background: #ffebee; border-radius: 4px; }}
        </style>
    </head>
    <body>
        <h1>SHARA Security Remediation</h1>
        <div class="error">
            <h2>Error</h2>
            <p>{message}</p>
        </div>
        <p>Please contact your security administrator if you believe this is an error.</p>
    </body>
    </html>
    """
    return {
        "statusCode": 400,
        "headers": {"Content-Type": "text/html"},
        "body": html,
    }


def success_page(action: str, task_id: str, result: dict) -> dict:
    """返回成功 HTML 页面"""
    if action == "approve":
        title = "Remediation Approved"
        message = "The security remediation has been approved and will be executed shortly."
        color = "#4caf50"
        bg_color = "#e8f5e9"
    else:
        title = "Remediation Rejected"
        message = "The security remediation has been rejected. No changes will be made."
        color = "#ff9800"
        bg_color = "#fff3e0"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>SHARA - {title}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .result {{ color: {color}; padding: 20px; background: {bg_color}; border-radius: 4px; }}
            .details {{ margin-top: 20px; padding: 15px; background: #f5f5f5; border-radius: 4px; }}
        </style>
    </head>
    <body>
        <h1>SHARA Security Remediation</h1>
        <div class="result">
            <h2>{title}</h2>
            <p>{message}</p>
        </div>
        <div class="details">
            <h3>Details</h3>
            <p><strong>Task ID:</strong> {task_id}</p>
            <p><strong>Status:</strong> {result.get('status', 'Unknown')}</p>
            <p><strong>Processed by:</strong> {result.get('approved_by', result.get('rejected_by', 'Unknown'))}</p>
        </div>
        <p>You can close this window.</p>
    </body>
    </html>
    """
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/html"},
        "body": html,
    }
