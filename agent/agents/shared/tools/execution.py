"""
Execution Tools - 代码执行和回滚管理工具
"""
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from strands import tool

from shared.config import get_config

logger = logging.getLogger(__name__)


#------------------------------------------------------------------------------
# Audit Logging - 审计日志上传到 S3
#------------------------------------------------------------------------------

def _upload_audit_log(
    task_id: str,
    code: str,
    execution_result: dict,
    control_id: str = "",
    resource_arn: str = "",
    resource_type: str = "",
    is_rollback: bool = False
):
    """上传审计日志到 S3。

    将执行的代码和日志上传到 S3 审计 bucket，用于未来的审计和 troubleshooting。

    S3 结构:
    s3://bucket/tasks/{task_id}/
      - code.py          - 执行的修复/回滚代码
      - execution.log    - 执行日志 (stdout, stderr, timing)
      - metadata.json    - 元数据 (task_id, resource_arn, control_id, timestamp 等)

    Args:
        task_id: 任务 ID
        code: 执行的代码
        execution_result: execute_code 返回的执行结果
        control_id: Security Hub Control ID
        resource_arn: 资源 ARN
        resource_type: 资源类型
        is_rollback: 是否为回滚操作
    """
    config = get_config()

    # 如果审计 bucket 未配置，跳过
    if not config.remediation_audit_bucket:
        logger.warning("[AUDIT] Remediation audit bucket not configured, skipping audit log upload")
        return

    try:
        s3 = boto3.client('s3', region_name=config.region)
        timestamp = datetime.now(timezone.utc)
        timestamp_str = timestamp.strftime('%Y%m%d_%H%M%S')

        # 确定操作类型
        operation_type = "rollback" if is_rollback else "remediation"

        # S3 前缀: tasks/{task_id}/{operation_type}_{timestamp}/
        prefix = f"tasks/{task_id}/{operation_type}_{timestamp_str}"

        # 1. 上传代码文件
        code_key = f"{prefix}/code.py"
        s3.put_object(
            Bucket=config.remediation_audit_bucket,
            Key=code_key,
            Body=code.encode('utf-8'),
            ContentType='text/x-python',
            Metadata={
                'task-id': task_id,
                'operation-type': operation_type,
                'control-id': control_id or 'unknown'
            }
        )
        logger.info(f"[AUDIT] Uploaded code to s3://{config.remediation_audit_bucket}/{code_key}")

        # 2. 上传执行日志
        log_content = f"""=== SHARA Remediation Execution Log ===
Task ID: {task_id}
Operation: {operation_type}
Control ID: {control_id}
Resource ARN: {resource_arn}
Timestamp: {timestamp.isoformat()}

=== Execution Result ===
Success: {execution_result.get('success', False)}
Status: {execution_result.get('status', 'unknown')}
Execution Time: {execution_result.get('execution_time_ms', 0)}ms
Session ID: {execution_result.get('session_id', 'N/A')}
Session Closed: {execution_result.get('session_closed', 'N/A')}

=== STDOUT ===
{execution_result.get('stdout', '(empty)')}

=== STDERR ===
{execution_result.get('stderr', '(empty)')}

=== ERROR ===
{execution_result.get('error', '(none)')}
"""
        log_key = f"{prefix}/execution.log"
        s3.put_object(
            Bucket=config.remediation_audit_bucket,
            Key=log_key,
            Body=log_content.encode('utf-8'),
            ContentType='text/plain'
        )
        logger.info(f"[AUDIT] Uploaded execution log to s3://{config.remediation_audit_bucket}/{log_key}")

        # 3. 上传元数据 JSON
        metadata = {
            "task_id": task_id,
            "operation_type": operation_type,
            "control_id": control_id,
            "resource_arn": resource_arn,
            "resource_type": resource_type,
            "timestamp": timestamp.isoformat(),
            "execution_result": {
                "success": execution_result.get('success', False),
                "status": execution_result.get('status', 'unknown'),
                "execution_time_ms": execution_result.get('execution_time_ms', 0),
                "session_id": execution_result.get('session_id'),
                "session_closed": execution_result.get('session_closed'),
                "has_error": bool(execution_result.get('error') or execution_result.get('stderr'))
            },
            "code_length": len(code),
            "stdout_length": len(execution_result.get('stdout', '')),
            "stderr_length": len(execution_result.get('stderr', ''))
        }

        metadata_key = f"{prefix}/metadata.json"
        s3.put_object(
            Bucket=config.remediation_audit_bucket,
            Key=metadata_key,
            Body=json.dumps(metadata, indent=2, ensure_ascii=False).encode('utf-8'),
            ContentType='application/json'
        )
        logger.info(f"[AUDIT] Uploaded metadata to s3://{config.remediation_audit_bucket}/{metadata_key}")

        logger.info(f"[AUDIT] Successfully uploaded audit logs for task {task_id} ({operation_type})")

    except Exception as e:
        # 审计日志上传失败不应该影响主流程
        logger.error(f"[AUDIT] Failed to upload audit logs: {e}")


# 全局审计上下文 - 由调用方设置，用于 execute_code 上传审计日志
_audit_context = {
    "task_id": None,
    "control_id": None,
    "resource_arn": None,
    "resource_type": None,
    "is_rollback": False
}


def set_audit_context(
    task_id: str,
    control_id: str = "",
    resource_arn: str = "",
    resource_type: str = "",
    is_rollback: bool = False
):
    """设置审计上下文，供 execute_code 使用。

    在调用 execute_code 之前设置此上下文，
    execute_code 会自动将代码和执行结果上传到审计 bucket。

    Args:
        task_id: 任务 ID
        control_id: Security Hub Control ID
        resource_arn: 资源 ARN
        resource_type: 资源类型
        is_rollback: 是否为回滚操作
    """
    global _audit_context
    _audit_context = {
        "task_id": task_id,
        "control_id": control_id,
        "resource_arn": resource_arn,
        "resource_type": resource_type,
        "is_rollback": is_rollback
    }
    logger.info(f"[AUDIT] Set audit context: task_id={task_id}, control_id={control_id}, is_rollback={is_rollback}")


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


# 全局 session 管理器 - 用于在多次工具调用间复用 session
_active_sessions = {}


@tool
def execute_code(
    code: str,
    timeout_seconds: int = 300,
    target_region: str = None,
    session_id: str = None,
    close_session: bool = True
) -> dict:
    """通过 AgentCore Code Interpreter 在沙盒环境中执行 Python 代码。

    执行生成的修复代码。代码将在隔离的沙盒环境中运行，确保安全性和可控性。

    **Session 复用机制**:
    - 首次调用: 不传 session_id，会创建新 session
    - 重试时: 传入上次返回的 session_id，复用同一个 session
    - 最后一次调用: 设置 close_session=True（默认），关闭 session

    **推荐用法 (最多重试 2 次)**:
    1. 第一次执行: execute_code(code, close_session=False)
       - 如果成功: 再调用 execute_code(code="", session_id=xxx, close_session=True) 关闭 session
       - 如果失败: 修改代码后继续步骤 2
    2. 第二次执行(重试1): execute_code(fixed_code, session_id=xxx, close_session=False)
       - 如果成功: 关闭 session
       - 如果失败: 修改代码后继续步骤 3
    3. 第三次执行(重试2): execute_code(fixed_code, session_id=xxx, close_session=True)
       - 无论成功失败，都关闭 session

    Args:
        code: 要执行的 Python 代码
        timeout_seconds: 执行超时时间（秒），默认 300 秒
        target_region: 目标 AWS Region (如 ap-northeast-1)，用于修复代码执行
        session_id: 复用的 session ID。如果提供，将在现有 session 中执行代码
        close_session: 是否在执行后关闭 session。默认 True。
                       设置为 False 可保持 session 用于后续重试

    Returns:
        dict: 执行结果
            - success: bool - 执行是否成功
            - status: str - 状态 (success/failed)
            - stdout: str - 标准输出
            - stderr: str - 标准错误
            - execution_time_ms: int - 执行耗时（毫秒）
            - session_id: str - Session ID，用于后续重试
            - session_closed: bool - Session 是否已关闭
            - error: str - 错误信息（如有）
    """
    import uuid

    config = get_config()
    global _active_sessions

    # 使用 target_region 如果提供，否则使用 config.region
    execution_region = target_region or config.region

    logger.info(f"="*50)
    logger.info(f"[EXECUTE_CODE] Using AgentCore Code Interpreter: {config.code_interpreter_id}")
    logger.info(f"[EXECUTE_CODE] Target region: {execution_region}")
    logger.info(f"[EXECUTE_CODE] Session ID: {session_id or '(new)'}")
    logger.info(f"[EXECUTE_CODE] Close session: {close_session}")
    logger.info(f"[EXECUTE_CODE] Code length: {len(code)} chars")
    if code:
        logger.info(f"[EXECUTE_CODE] First 500 chars:\n{code[:500]}...")
    logger.info(f"="*50)

    client = None
    current_session_id = session_id
    created_new_session = False

    try:
        start_time = time.time()

        # 使用 boto3 调用 AgentCore Code Interpreter
        client = boto3.client('bedrock-agentcore', region_name=config.region)

        # Step 1: 获取或创建 Session
        if current_session_id and current_session_id in _active_sessions:
            # 复用现有 session
            logger.info(f"[EXECUTE_CODE] Reusing existing session: {current_session_id}")
        elif current_session_id:
            # 尝试使用传入的 session_id（可能来自之前的调用）
            logger.info(f"[EXECUTE_CODE] Using provided session: {current_session_id}")
            _active_sessions[current_session_id] = True
        else:
            # 创建新 session
            session_response = client.start_code_interpreter_session(
                codeInterpreterIdentifier=config.code_interpreter_id,
                name=f"shara-session-{uuid.uuid4().hex[:8]}",
                sessionTimeoutSeconds=timeout_seconds
            )
            current_session_id = session_response['sessionId']
            _active_sessions[current_session_id] = True
            created_new_session = True
            logger.info(f"[EXECUTE_CODE] Created new session: {current_session_id}")

        # 如果只是要关闭 session（空代码）
        if not code or not code.strip():
            if close_session:
                _close_session(client, config.code_interpreter_id, current_session_id)
            return {
                "success": True,
                "status": "session_closed",
                "session_id": current_session_id,
                "session_closed": close_session,
                "message": "Session closed successfully" if close_session else "No code to execute"
            }

        # 在代码开头注入环境变量设置
        code_with_env = f"""
import os
os.environ['AWS_REGION'] = '{execution_region}'
os.environ['AWS_DEFAULT_REGION'] = '{execution_region}'
os.environ['TARGET_REGION'] = '{execution_region}'

{code}
"""

        # Step 2: 执行代码
        execute_response = client.invoke_code_interpreter(
            codeInterpreterIdentifier=config.code_interpreter_id,
            sessionId=current_session_id,
            name='executeCode',
            arguments={
                'language': 'python',
                'code': code_with_env
            }
        )

        # 解析 streaming response
        stdout_parts = []
        stderr_parts = []

        for event in execute_response.get('stream', []):
            if 'result' in event:
                result = event['result']
                if 'content' in result:
                    for content_item in result['content']:
                        if content_item.get('type') == 'text':
                            stdout_parts.append(content_item.get('text', ''))
                if 'error' in result:
                    stderr_parts.append(result['error'])

        execution_time_ms = int((time.time() - start_time) * 1000)

        stdout = '\n'.join(stdout_parts)
        stderr = '\n'.join(stderr_parts)
        success = not stderr

        logger.info(f"[EXECUTE_CODE] Completed in {execution_time_ms}ms, success={success}")
        logger.info(f"[EXECUTE_CODE] stdout: {stdout[:500]}...")
        if stderr:
            logger.error(f"[EXECUTE_CODE] stderr: {stderr}")

        # Step 3: 根据 close_session 决定是否关闭
        session_closed = False
        if close_session:
            _close_session(client, config.code_interpreter_id, current_session_id)
            session_closed = True

        result = {
            "success": success,
            "status": "success" if success else "failed",
            "stdout": stdout,
            "stderr": stderr,
            "execution_time_ms": execution_time_ms,
            "session_id": current_session_id,
            "session_closed": session_closed,
            "hint": None if success or close_session else
                    f"代码执行失败。你可以修改代码后使用 session_id='{current_session_id}' 重试，最后设置 close_session=True 关闭 session。"
        }

        # Step 4: 上传审计日志到 S3
        if _audit_context.get("task_id"):
            _upload_audit_log(
                task_id=_audit_context["task_id"],
                code=code,
                execution_result=result,
                control_id=_audit_context.get("control_id", ""),
                resource_arn=_audit_context.get("resource_arn", ""),
                resource_type=_audit_context.get("resource_type", ""),
                is_rollback=_audit_context.get("is_rollback", False)
            )

        return result

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_msg = e.response.get('Error', {}).get('Message', str(e))
        logger.error(f"[EXECUTE_CODE] ClientError: {error_code} - {error_msg}")

        # 如果是配置问题，fallback 到直接执行（仅开发环境）
        if error_code in ['ResourceNotFoundException', 'ValidationException', 'UnrecognizedClientException']:
            logger.warning("[EXECUTE_CODE] Code Interpreter not available, falling back to direct execution")
            return _execute_with_boto3(code, timeout_seconds, execution_region)

        # 出错时也尝试关闭 session
        if close_session and current_session_id and client:
            _close_session(client, config.code_interpreter_id, current_session_id)

        return {
            "success": False,
            "status": "failed",
            "error": f"{error_code}: {error_msg}",
            "session_id": current_session_id,
            "session_closed": close_session
        }

    except Exception as e:
        logger.exception(f"[EXECUTE_CODE] Unexpected error: {e}")

        # 出错时也尝试关闭 session
        if close_session and current_session_id and client:
            _close_session(client, config.code_interpreter_id, current_session_id)

        return {
            "success": False,
            "status": "failed",
            "error": str(e),
            "session_id": current_session_id,
            "session_closed": close_session
        }


def _close_session(client, code_interpreter_id: str, session_id: str):
    """关闭 Code Interpreter Session"""
    global _active_sessions

    try:
        client.stop_code_interpreter_session(
            codeInterpreterIdentifier=code_interpreter_id,
            sessionId=session_id
        )
        logger.info(f"[EXECUTE_CODE] Stopped session: {session_id}")
    except Exception as e:
        logger.warning(f"[EXECUTE_CODE] Failed to stop session: {e}")
    finally:
        # 从活跃 session 列表中移除
        _active_sessions.pop(session_id, None)


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
