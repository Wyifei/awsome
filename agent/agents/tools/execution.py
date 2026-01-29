"""
Execution Tools - 代码执行和回滚管理工具
"""
import json
import logging
import time
from datetime import datetime
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from strands import tool

from agents.config import get_config

logger = logging.getLogger(__name__)


@tool
def save_rollback_data(
    task_id: str,
    resource_arn: str,
    resource_type: str,
    current_state: dict
) -> dict:
    """保存资源当前状态用于回滚。

    在执行修复操作前，保存资源的当前配置状态。
    如果修复失败或需要回滚，可以使用此数据恢复原始状态。

    Args:
        task_id: 任务 ID
        resource_arn: 资源 ARN
        resource_type: 资源类型 (如 AwsS3Bucket)
        current_state: 当前资源配置状态

    Returns:
        dict: 保存结果
            - success: bool - 是否成功
            - resource_arn: str - 资源 ARN
            - error: str - 错误信息 (如有)
    """
    config = get_config()
    dynamodb = boto3.resource('dynamodb', region_name=config.region)
    table = dynamodb.Table(config.tasks_table)

    try:
        # TTL: 30 天后过期
        ttl = int(time.time()) + (30 * 24 * 60 * 60)

        item = {
            'PK': f'TASK#{task_id}',
            'SK': f'ROLLBACK#{resource_arn}',
            'task_id': task_id,
            'resource_arn': resource_arn,
            'resource_type': resource_type,
            'pre_state': current_state,
            'created_at': datetime.utcnow().isoformat(),
            'ttl': ttl
        }

        table.put_item(Item=item)

        logger.info(f"Saved rollback data for task {task_id}, resource {resource_arn}")
        return {
            "success": True,
            "task_id": task_id,
            "resource_arn": resource_arn
        }

    except ClientError as e:
        logger.error(f"Error saving rollback data: {e}")
        return {
            "success": False,
            "resource_arn": resource_arn,
            "error": str(e)
        }


@tool
def get_rollback_data(task_id: str, resource_arn: str) -> dict:
    """获取保存的回滚数据。

    获取之前保存的资源原始状态，用于执行回滚操作。

    Args:
        task_id: 任务 ID
        resource_arn: 资源 ARN

    Returns:
        dict: 回滚数据
            - success: bool - 是否成功获取
            - pre_state: dict - 资源修复前的状态
            - resource_type: str - 资源类型
            - error: str - 错误信息 (如有)
    """
    config = get_config()
    dynamodb = boto3.resource('dynamodb', region_name=config.region)
    table = dynamodb.Table(config.tasks_table)

    try:
        response = table.get_item(Key={
            'PK': f'TASK#{task_id}',
            'SK': f'ROLLBACK#{resource_arn}'
        })

        if 'Item' not in response:
            logger.warning(f"Rollback data not found for task {task_id}, resource {resource_arn}")
            return {
                "success": False,
                "error": "Rollback data not found"
            }

        item = response['Item']
        logger.info(f"Retrieved rollback data for task {task_id}")

        return {
            "success": True,
            "task_id": task_id,
            "resource_arn": resource_arn,
            "pre_state": item.get('pre_state', {}),
            "resource_type": item.get('resource_type'),
            "created_at": item.get('created_at')
        }

    except ClientError as e:
        logger.error(f"Error getting rollback data: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@tool
def execute_rollback(task_id: str, resource_arn: str) -> dict:
    """执行回滚操作，恢复资源到修复前状态。

    获取保存的原始状态并执行回滚，将资源恢复到修复前的配置。

    Args:
        task_id: 任务 ID
        resource_arn: 资源 ARN

    Returns:
        dict: 回滚执行结果
            - success: bool - 是否成功
            - rollback_result: dict - 回滚详情
            - error: str - 错误信息 (如有)
    """
    config = get_config()

    # 1. 获取回滚数据
    rollback_data = get_rollback_data(task_id, resource_arn)
    if not rollback_data.get('success'):
        return rollback_data

    pre_state = rollback_data['pre_state']
    resource_type = rollback_data['resource_type']

    try:
        # 2. 根据资源类型执行回滚
        if resource_type == 'AwsS3Bucket':
            result = _rollback_s3_bucket(resource_arn, pre_state, config.region)
        elif resource_type == 'AwsEc2SecurityGroup':
            result = _rollback_security_group(resource_arn, pre_state, config.region)
        else:
            return {
                "success": False,
                "error": f"Unsupported resource type for rollback: {resource_type}"
            }

        if result.get('success'):
            logger.info(f"Successfully rolled back {resource_arn} to pre-state")
        else:
            logger.error(f"Failed to rollback {resource_arn}: {result.get('error')}")

        return {
            "success": result.get('success', False),
            "task_id": task_id,
            "resource_arn": resource_arn,
            "resource_type": resource_type,
            "rollback_result": result
        }

    except Exception as e:
        logger.exception(f"Error executing rollback: {e}")
        return {
            "success": False,
            "task_id": task_id,
            "resource_arn": resource_arn,
            "error": str(e)
        }


def _rollback_s3_bucket(resource_arn: str, pre_state: dict, region: str) -> dict:
    """回滚 S3 Bucket 配置"""
    s3 = boto3.client('s3', region_name=region)
    bucket_name = resource_arn.split(':')[-1]

    try:
        # 恢复 Public Access Block 配置
        if 'PublicAccessBlockConfiguration' in pre_state:
            s3.put_public_access_block(
                Bucket=bucket_name,
                PublicAccessBlockConfiguration=pre_state['PublicAccessBlockConfiguration']
            )
            logger.info(f"Rolled back PublicAccessBlock for {bucket_name}")

        return {
            "success": True,
            "message": f"Successfully rolled back S3 bucket {bucket_name}"
        }

    except ClientError as e:
        return {
            "success": False,
            "error": str(e)
        }


def _rollback_security_group(resource_arn: str, pre_state: dict, region: str) -> dict:
    """回滚 Security Group 配置"""
    ec2 = boto3.client('ec2', region_name=region)
    sg_id = resource_arn.split('/')[-1]

    try:
        # 恢复入站规则
        if 'IpPermissions' in pre_state:
            # 先移除当前规则，再添加原始规则
            # 这里简化处理，实际可能需要更精细的差异对比
            current = ec2.describe_security_groups(GroupIds=[sg_id])
            if current.get('SecurityGroups'):
                current_rules = current['SecurityGroups'][0].get('IpPermissions', [])
                if current_rules:
                    ec2.revoke_security_group_ingress(
                        GroupId=sg_id,
                        IpPermissions=current_rules
                    )

            if pre_state['IpPermissions']:
                ec2.authorize_security_group_ingress(
                    GroupId=sg_id,
                    IpPermissions=pre_state['IpPermissions']
                )

            logger.info(f"Rolled back security group rules for {sg_id}")

        return {
            "success": True,
            "message": f"Successfully rolled back security group {sg_id}"
        }

    except ClientError as e:
        return {
            "success": False,
            "error": str(e)
        }


@tool
def save_task_event(
    task_id: str,
    event_type: str,
    data: Optional[dict] = None,
    actor_type: str = "agent",
    actor_id: Optional[str] = None
) -> dict:
    """保存任务事件到 DynamoDB。

    记录任务处理过程中的各种事件，用于审计和追踪。

    Args:
        task_id: 任务 ID
        event_type: 事件类型 (如 analysis_started, execution_completed)
        data: 事件相关数据
        actor_type: 执行者类型 (system, agent, user, lambda)
        actor_id: 执行者 ID

    Returns:
        dict: 保存结果
    """
    import uuid

    config = get_config()
    dynamodb = boto3.resource('dynamodb', region_name=config.region)
    table = dynamodb.Table(config.tasks_table)

    try:
        timestamp = datetime.utcnow().isoformat()
        event_id = str(uuid.uuid4())[:8]

        # TTL: 90 天后过期
        ttl = int(time.time()) + (90 * 24 * 60 * 60)

        item = {
            'PK': f'TASK#{task_id}',
            'SK': f'EVENT#{timestamp}#{event_id}',
            'task_id': task_id,
            'event_id': event_id,
            'event_type': event_type,
            'timestamp': timestamp,
            'actor': {
                'type': actor_type,
                'id': actor_id or 'unknown'
            },
            'data': data or {},
            'ttl': ttl
        }

        table.put_item(Item=item)

        logger.info(f"Saved event {event_type} for task {task_id}")
        return {
            "success": True,
            "event_id": event_id,
            "event_type": event_type
        }

    except ClientError as e:
        logger.error(f"Error saving task event: {e}")
        return {
            "success": False,
            "error": str(e)
        }
