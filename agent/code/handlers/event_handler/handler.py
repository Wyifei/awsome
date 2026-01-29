"""
Event Handler Lambda - 处理 Security Hub 事件并触发修复工作流
"""
import json
import logging
import os

logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))


def lambda_handler(event, context):
    """
    Lambda 入口函数

    Args:
        event: EventBridge 或 API Gateway 事件
        context: Lambda 上下文

    Returns:
        dict: 响应结果
    """
    logger.info(f"Received event: {json.dumps(event)}")

    # TODO: 实现事件处理逻辑

    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Event received successfully',
            'event_id': context.aws_request_id
        })
    }
