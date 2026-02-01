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

from shared.config import get_config

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
def execute_code(
    code: str,
    timeout_seconds: int = 300,
    target_region: str = None
) -> dict:
    """通过 Code Interpreter 在沙盒环境中执行 Python 代码。

    执行生成的修复代码。代码将在隔离的沙盒环境中运行，
    确保安全性和可控性。

    Args:
        code: 要执行的 Python 代码
        timeout_seconds: 执行超时时间（秒），默认 300 秒
        target_region: 目标 AWS Region (如 ap-northeast-1)，用于修复代码执行。
                       如果不指定，则使用默认 region。
                       建议从 get_analysis_context 获取 finding_region 并传入此参数。

    Returns:
        dict: 执行结果
            - success: bool - 执行是否成功
            - status: str - 状态 (success/failed)
            - exit_code: int - 退出码
            - stdout: str - 标准输出
            - stderr: str - 标准错误
            - execution_time_ms: int - 执行耗时（毫秒）
            - error: str - 错误信息（如有）
    """
    import os
    import time

    config = get_config()

    # 使用 target_region 如果提供，否则使用 config.region
    execution_region = target_region or config.region

    logger.info(f"="*50)
    logger.info(f"[EXECUTE_CODE CALLED] timeout={timeout_seconds}s")
    logger.info(f"[EXECUTE_CODE] Target region: {execution_region} (from {'parameter' if target_region else 'config'})")
    logger.info(f"[EXECUTE_CODE] Code length: {len(code)} chars")
    logger.info(f"[EXECUTE_CODE] First 300 chars:\n{code[:300]}...")
    logger.info(f"="*50)

    try:
        # 尝试使用 AgentCore Code Interpreter
        from bedrock_agentcore.tools import CodeInterpreterClient

        client = CodeInterpreterClient(region_name=config.region)

        start_time = time.time()

        result = client.execute(
            code=code,
            timeout=timeout_seconds,
            environment={
                "AWS_REGION": execution_region,
                "AWS_DEFAULT_REGION": execution_region,
                "TARGET_REGION": execution_region  # 额外提供 TARGET_REGION 方便代码使用
            }
        )

        execution_time_ms = int((time.time() - start_time) * 1000)

        logger.info(f"Code Interpreter execution completed with exit_code={result.exit_code}")

        return {
            "success": result.exit_code == 0,
            "status": "success" if result.exit_code == 0 else "failed",
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "execution_time_ms": execution_time_ms
        }

    except ImportError:
        logger.warning("AgentCore Code Interpreter SDK not available, using direct boto3 execution")
        # Fallback: 使用 boto3 直接执行
        # 这是临时方案，生产环境应使用 Code Interpreter
        return _execute_with_boto3(code, timeout_seconds, execution_region)

    except Exception as e:
        logger.exception(f"Code execution failed: {e}")
        return {
            "success": False,
            "status": "failed",
            "error": str(e)
        }


def _execute_with_boto3(code: str, timeout_seconds: int, region: str) -> dict:
    """使用 boto3 直接执行代码（备用方案）。

    注意：此方法不提供沙盒隔离，仅用于开发测试。
    生产环境应使用 AgentCore Code Interpreter。
    """
    import time

    logger.warning("Using direct execution (no sandbox) - for development only")
    logger.info(f"Code length: {len(code)} chars")
    logger.info(f"Region for execution: {region}")
    logger.info(f"=== Code to execute ===\n{code}\n=== End of code ===")

    try:
        start_time = time.time()

        # 准备执行环境 - 需要导入常用模块
        import boto3
        import botocore
        import botocore.exceptions
        import os
        import json as json_module
        import time as time_module

        # 设置环境变量，让 boto3 自动使用正确的 region
        os.environ['AWS_DEFAULT_REGION'] = region
        os.environ['AWS_REGION'] = region

        # 检查 AWS 凭证来源
        has_env_creds = bool(os.environ.get('AWS_ACCESS_KEY_ID'))
        has_file_creds = os.path.exists(os.path.expanduser('~/.aws/credentials')) or os.path.exists('/root/.aws/credentials')
        logger.info(f"AWS credentials check - env vars: {has_env_creds}, file: {has_file_creds}")

        exec_globals = {
            '__builtins__': __builtins__,
            '__name__': '__main__',  # 关键：让 if __name__ == "__main__" 能够执行
            'boto3': boto3,
            'botocore': botocore,
            'os': os,
            'json': json_module,
            'time': time_module,  # 添加 time 模块
            'AWS_REGION': region,
            'print': print,
        }
        exec_locals = {}

        # 捕获输出
        import io
        import sys
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()

        try:
            # 执行代码
            exec(code, exec_globals, exec_locals)
            stdout = sys.stdout.getvalue()
            stderr = sys.stderr.getvalue()
            exit_code = 0
        except Exception as e:
            stdout = sys.stdout.getvalue()
            stderr = sys.stderr.getvalue() + f"\nException: {str(e)}"
            exit_code = 1
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        execution_time_ms = int((time.time() - start_time) * 1000)

        logger.info(f"=== Execution Result ===")
        logger.info(f"Exit code: {exit_code}")
        logger.info(f"Stdout: {stdout[:1000] if stdout else '(empty)'}")
        logger.info(f"Stderr: {stderr[:1000] if stderr else '(empty)'}")
        logger.info(f"Execution time: {execution_time_ms}ms")

        return {
            "success": exit_code == 0,
            "status": "success" if exit_code == 0 else "failed",
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "execution_time_ms": execution_time_ms,
            "warning": "Executed without sandbox isolation (development mode)"
        }

    except Exception as e:
        return {
            "success": False,
            "status": "failed",
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
