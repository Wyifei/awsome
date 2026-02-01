"""
Validator Agent - Phase 2 验证智能体

负责验证修复效果、更新 Security Hub Finding 状态、保存修复经验。
"""
import logging
from typing import Optional

from strands import Agent
from strands.models import BedrockModel

from shared.config import get_config, VALIDATOR_MODEL_CONFIG
from shared.tools.security_hub import update_security_hub_finding, verify_resource_state
from shared.tools.memory_tools import save_experience_to_ltm, set_memory_session, get_remediation_result, get_rollback_from_memory
from shared.tools.execution import save_task_event
from shared.tools.aws_resources import get_resource_config
from shared.tools.validator_tools import review_code_security, trigger_result_email

logger = logging.getLogger(__name__)

# Validator Agent System Prompt
VALIDATOR_SYSTEM_PROMPT = """# 角色
你是 SHARA (Security Hub Auto-Remediation Agent) 的验证智能体。
你通过 A2A (Agent-to-Agent) 协议被 Remediator Agent 调用。
你的任务是审查修复代码安全性、验证修复结果、更新 Security Hub、保存经验并触发结果邮件。

# 重要约束
- 你在 Remediator 执行代码后被调用
- 你需要从 Memory 获取 Remediator 保存的代码和执行结果
- 你需要审查代码安全性并验证执行结果
- 修复结果邮件包含回滚链接（回滚结果邮件不包含）

# ⚠️ 关键：修复 vs 回滚验证的区别
你会收到 is_rollback 参数来区分操作类型：

## 修复验证 (is_rollback=False)
- **验证目标**: 确认资源已达到 Security Hub 要求的安全配置状态
- **期望状态**: 由 Control ID 定义的安全配置（如 S3.1 要求 Block Public Access = True）
- **成功标准**: 资源配置符合安全标准
- **结果邮件**: 包含回滚链接

## 回滚验证 (is_rollback=True)
- **验证目标**: 确认资源已恢复到修复前的原始状态
- **期望状态**: 由 prompt 中提供的 pre_state 定义（修复前的配置）
- **成功标准**: 资源配置恢复到原始状态（即使该状态不符合安全标准）
- **结果邮件**: 不包含回滚链接

**示例**:
- S3 存储桶修复后 Block Public Access = True
- 如果用户回滚，期望状态是修复前的配置（可能 Block Public Access = False）
- 回滚验证应该检查资源是否恢复到 False，而不是 True

# 验证流程
按以下步骤执行：

## 步骤 0: 从 Memory 获取修复结果
使用 get_remediation_result 工具从 Memory 获取：
- generated_code: Remediator 生成的代码
- execution_result: 代码执行结果
**注意**: 这些数据不再通过 A2A 参数传递，而是从 Memory 获取

## 步骤 1: 代码安全审查
使用 review_code_security 工具审查 Remediator 生成的代码：
- 检查危险操作（删除、终止、销毁）
- 检查敏感信息泄露（硬编码密钥）
- 检查权限提升风险
- 检查代码质量问题

## 步骤 2: 执行结果验证
分析 Remediator 传递的 execution_result：
- 检查 exit_code 是否为 0
- 检查 stdout 中的结果是否表示成功
- 检查 stderr 是否有错误信息

## 步骤 3: 资源状态验证
使用 verify_resource_state 和 get_resource_config 工具验证资源状态：
- 确认资源配置已按预期修改
- 交叉验证当前资源配置
- resource_arn: 直接使用任务中的完整资源 ARN
- resource_type: 直接使用任务中的资源类型 (如 AwsS3Bucket, AwsSnsTopic)
- **关键**: expected_state 的值取决于操作类型（见上方说明）

## 步骤 4: 更新 Security Hub
- **修复验证**: 如果验证通过，更新为 RESOLVED
- **回滚验证**: 如果验证通过，更新为 NEW（因为资源恢复到不合规状态）

## 步骤 5: 保存修复经验
如果验证通过，使用 save_experience_to_ltm 工具：
- 保存成功的修复方案供将来参考
- 包含 control_id、resource_type、修复代码等信息
- **回滚成功时不保存经验**（回滚不是值得复用的修复方案）

## 步骤 6: 触发结果邮件
使用 trigger_result_email 工具发送结果邮件：
- 传递代码审查结果和验证结果
- **重要**: is_rollback 参数决定邮件是否包含回滚链接
  - is_rollback=False（正常修复）: 邮件包含回滚链接
  - is_rollback=True（回滚操作）: 邮件不包含回滚链接

# 验证标准（仅用于修复验证）
针对每种资源类型，验证以下内容：

## S3 存储桶 (AwsS3Bucket)
- BlockPublicAcls: true
- IgnorePublicAcls: true
- BlockPublicPolicy: true
- RestrictPublicBuckets: true

## 安全组 (AwsEc2SecurityGroup)
- 入站规则中没有 0.0.0.0/0 CIDR（除了必要的端口如 443）
- 适当限制源 IP 范围

## IAM 角色 (AwsIamRole)
- 信任策略中没有通配符 (*) 主体
- 权限范围适当

# 输出格式
返回以下结构的 JSON 对象：

{
  "code_review": {
    "status": "passed",
    "issues": [],
    "risk_level": "low",
    "recommendations": ["Code passed security review"]
  },
  "execution_analysis": {
    "exit_code": 0,
    "success": true,
    "stdout_analysis": "修复成功完成"
  },
  "validation": {
    "passed": true,
    "checks": [
      {
        "name": "BlockPublicAcls",
        "expected": true,
        "actual": true,
        "passed": true
      }
    ],
    "summary": "4 项检查全部通过"
  },
  "security_hub_update": {
    "updated": true,
    "finding_id": "arn:aws:securityhub:...",
    "new_status": "RESOLVED"
  },
  "experience_saved": {
    "saved": true,
    "namespace": "/remediation/S3_1/task-xxx",
    "experience_id": "USER_S3_1_abc123"
  },
  "result_email": {
    "sent": true,
    "includes_rollback_link": true
  }
}

# 重要指南
- **始终执行代码安全审查** - 这是第一步
- 仅在所有验证检查通过时保存经验（回滚成功不保存）
- 为每个验证标准包含详细的检查结果
- 使用适当的工作流状态更新 Security Hub
- 如果验证失败，报告哪些检查失败以及原因
- 如果验证失败，不要将 Security Hub 更新为 RESOLVED
- **始终触发结果邮件** - 无论成功失败都要通知用户
- **回滚操作的邮件不能有回滚链接** - 避免无限回滚循环
- **回滚验证使用 pre_state 作为期望状态，不是安全标准**
"""


def create_validator_agent(
    task_id: str,
    memory_session_id: str,
    memory_id: str,
    region: Optional[str] = None,
    actor_id: Optional[str] = None
) -> Agent:
    """创建 Validator Agent 实例。

    Args:
        task_id: 任务 ID
        memory_session_id: Memory Session ID
        memory_id: AgentCore Memory ID
        region: AWS Region (可选)
        actor_id: Actor ID (可选，需要与 Analyzer/Remediator 使用相同的值)

    Returns:
        Agent: 配置好的 Validator Agent
    """
    config = get_config()
    region = region or config.region

    # 使用与 Analyzer/Remediator 相同的 actor_id
    # actor_id 应该是 AWS 账户 ID，以便跨 session 共享修复经验
    if not actor_id:
        logger.warning("actor_id not provided, using task_id as fallback. "
                      "For better LTM retrieval, pass AWS account ID as actor_id.")
        actor_id = f"task-{task_id}"

    # 连接到 Memory Session
    session_manager = None

    if not memory_id:
        logger.warning("AGENTCORE_MEMORY_ID 未配置，将跳过 Memory 功能")
    else:
        try:
            from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager
            from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig

            memory_config = AgentCoreMemoryConfig(
                memory_id=memory_id,
                actor_id=actor_id,  # 使用与 Analyzer/Remediator 相同的 actor_id
                session_id=memory_session_id  # 复用 Phase 1 的 Session
            )

            session_manager = AgentCoreMemorySessionManager(
                agentcore_memory_config=memory_config,
                region_name=region
            )

            # 设置全局 memory session 供工具使用
            # 传入 session_manager，会自动从中提取 memory_client 和 config
            set_memory_session(session_manager)

            logger.info(f"已连接 Memory session: session_id={memory_session_id}, actor_id={actor_id}")

        except ImportError:
            logger.warning("AgentCore Memory SDK 未安装，将跳过 Memory 功能")
        except Exception as e:
            logger.warning(f"连接 Memory session 失败: {e}")

    # 配置 LLM
    # streaming=False 用于绕过 strands SDK 1.24.0 中的流式处理 bug
    model = BedrockModel(
        model_id=VALIDATOR_MODEL_CONFIG.model_id,
        temperature=VALIDATOR_MODEL_CONFIG.temperature,
        max_tokens=VALIDATOR_MODEL_CONFIG.max_tokens,
        region_name=region,
        streaming=False
    )

    # 创建 Agent
    agent = Agent(
        model=model,
        system_prompt=VALIDATOR_SYSTEM_PROMPT,
        tools=[
            # Memory - Get remediation result from Remediator
            get_remediation_result,
            get_rollback_from_memory,  # Get pre_state for rollback validation
            # Code Security Review (A2A enhanced)
            review_code_security,
            # Resource Verification
            verify_resource_state,
            get_resource_config,
            # Security Hub
            update_security_hub_finding,
            # Experience & Memory
            save_experience_to_ltm,
            save_task_event,
            # Result Email (A2A enhanced)
            trigger_result_email,
        ],
        session_manager=session_manager,
    )

    logger.info(f"Created Validator Agent for task {task_id}")
    return agent


def run_validator(
    agent: Agent,
    task_id: str,
    finding_id: str,
    resource_arn: str,
    resource_type: str,
    control_id: str,
    is_rollback: bool = False,
    rollback_failed: bool = False,
    error_message: str = ""
) -> dict:
    """运行 Validator Agent 验证修复结果。

    通过 A2A 协议被 Remediator Agent 调用，执行以下任务：
    0. 从 Memory 获取 Remediator 保存的代码和执行结果
    1. 审查代码安全性
    2. 分析代码执行结果
    3. 验证资源状态
    4. 更新 Security Hub
    5. 保存修复经验到 LTM
    6. 触发结果邮件（正常修复包含回滚链接，回滚操作不包含）

    NOTE: generated_code and execution_result are retrieved from Memory (not passed as args).

    Args:
        agent: Validator Agent 实例
        task_id: 任务 ID
        finding_id: Security Hub Finding ID
        resource_arn: 资源 ARN
        resource_type: 资源类型
        control_id: Control ID
        is_rollback: 是否为回滚操作 (回滚邮件不包含回滚链接)
        rollback_failed: 是否回滚失败 (如回滚数据未找到)
        error_message: 错误信息 (用于邮件通知)

    Returns:
        dict: 验证结果，包含 code_review, validation, security_hub_update, experience_saved, result_email
    """
    import json

    # Handle rollback_failed case - skip normal validation, just send error email
    if rollback_failed:
        logger.warning(f"Rollback failed for task {task_id}: {error_message}")

        prompt = f"""
Rollback operation FAILED for task {task_id}.

**Task ID:** {task_id}
**Finding ID:** {finding_id}
**Control ID:** {control_id}
**Resource ARN:** {resource_arn}
**Error:** {error_message or "Rollback data not found in Memory"}

Since the rollback failed, you need to:
1. **Trigger Result Email**: Use trigger_result_email tool to notify the user
   - task_id: {task_id}
   - resource_arn: {resource_arn}
   - control_id: {control_id}
   - code_review_result: {{"status": "skipped", "issues": [], "risk_level": "unknown"}}
   - validation_result: {{"passed": false, "checks": []}}
   - is_rollback: True
   - rollback_failed: True
   - error_message: "{error_message or 'Rollback data not found in Memory. Manual rollback may be required.'}"

**IMPORTANT:**
- This is a FAILURE notification - the rollback could not be completed
- The user needs to be informed to take manual action
- Do NOT attempt normal validation or Security Hub update

Return a JSON summary indicating the rollback failure and email notification result.
"""
        logger.info(f"Running Validator Agent for rollback failure notification, task {task_id}")

        try:
            result = agent(prompt)
            response_text = str(result.message) if hasattr(result, 'message') else str(result)
            email_sent = '"sent": true' in response_text.lower()

            return {
                "success": False,
                "task_id": task_id,
                "finding_id": finding_id,
                "is_rollback": True,
                "rollback_failed": True,
                "code_review_passed": False,
                "validation_passed": False,
                "email_sent": email_sent,
                "error": error_message or "Rollback data not found",
                "response": response_text
            }
        except Exception as e:
            logger.exception(f"Validator failed to send rollback failure notification: {e}")
            return {
                "success": False,
                "task_id": task_id,
                "is_rollback": True,
                "rollback_failed": True,
                "error": str(e)
            }

    # 构建 A2A 验证 prompt - 根据操作类型区分验证逻辑
    if is_rollback:
        # 回滚验证：使用 pre_state 作为期望状态
        prompt = f"""
Validate the ROLLBACK operation for task {task_id}:

**Task ID:** {task_id}
**Finding ID:** {finding_id}
**Control ID:** {control_id}
**Resource ARN:** {resource_arn}
**Resource Type:** {resource_type}
**Operation Type:** ROLLBACK

⚠️ **IMPORTANT - ROLLBACK VALIDATION LOGIC:**
This is a ROLLBACK operation. The goal is to verify that the resource has been restored
to its ORIGINAL state (before remediation), NOT the security-compliant state.

**Instructions - Execute ALL steps in order:**

0. **Get Rollback Data from Memory**: Use get_rollback_from_memory tool FIRST
   - task_id: {task_id}
   - resource_arn: {resource_arn}
   - This retrieves the pre_state (original configuration before remediation)
   - **CRITICAL**: Use pre_state as the expected state for validation

1. **Get Remediation Result from Memory**: Use get_remediation_result tool
   - task_id: {task_id}
   - resource_arn: {resource_arn}
   - This retrieves generated_code and execution_result

2. **Code Security Review**: Use review_code_security tool
   - Review the rollback code for safety

3. **Execution Result Analysis**: Analyze the execution_result
   - Check if exit_code is 0
   - Check if stdout indicates successful restoration

4. **Resource State Verification**: Use verify_resource_state tool
   - **CRITICAL**: Use the pre_state from step 0 as expected_state
   - Example: If pre_state shows BlockPublicAcls=False, verify it's now False
   - The goal is to confirm the resource matches the ORIGINAL state, not security standards
   - Also use get_resource_config to cross-verify

5. **Update Security Hub**: If rollback verification passes
   - Set finding status to NEW (resource is back to non-compliant state)
   - finding_id: {finding_id}

6. **Skip Experience Save**: Do NOT save rollback as experience
   - Rollback is not a remediation pattern worth reusing

7. **Trigger Result Email**: Use trigger_result_email tool - ALWAYS do this
   - task_id: {task_id}
   - resource_arn: {resource_arn}
   - control_id: {control_id}
   - code_review_result: results from step 2
   - validation_result: results from step 4
   - is_rollback: True (NO rollback link in email)

**CRITICAL REMINDERS:**
- For ROLLBACK: expected state = pre_state (original configuration)
- If pre_state shows BlockPublicAcls=False, that's CORRECT for rollback validation
- Do NOT use security standards (True) as expected state for rollback
- Rollback success means restoring to original state, even if non-compliant

Return a JSON summary with code_review, execution_analysis, validation, security_hub_update, and result_email results.
"""
    else:
        # 修复验证：使用安全标准作为期望状态
        expected_state = _get_expected_state(resource_type, control_id)
        prompt = f"""
Validate the REMEDIATION for task {task_id}:

**Task ID:** {task_id}
**Finding ID:** {finding_id}
**Control ID:** {control_id}
**Resource ARN:** {resource_arn}
**Resource Type:** {resource_type}
**Operation Type:** REMEDIATION

**Expected State After Remediation (Security Standards):**
```json
{json.dumps(expected_state, indent=2)}
```

**Instructions - Execute ALL steps in order:**

0. **Get Remediation Result from Memory**: Use get_remediation_result tool FIRST
   - task_id: {task_id}
   - resource_arn: {resource_arn}
   - This retrieves generated_code and execution_result saved by Remediator

1. **Code Security Review**: Use review_code_security tool to review the generated code
   - Pass the generated_code (from step 0) to the tool
   - Check for dangerous operations, sensitive info leakage, code quality issues

2. **Execution Result Analysis**: Analyze the execution_result (from step 0)
   - Check if exit_code is 0
   - Check if stdout indicates success
   - Check stderr for any errors

3. **Resource State Verification**: Use verify_resource_state and get_resource_config tools
   - Verify the resource configuration matches the security standards above
   - Use resource_arn: {resource_arn}
   - Use resource_type: {resource_type}

4. **Update Security Hub**: If verification passes, use update_security_hub_finding tool
   - Set finding status to RESOLVED
   - finding_id: {finding_id}

5. **Save Experience**: If verification passes, use save_experience_to_ltm tool
   - Save this remediation experience for future reference

6. **Trigger Result Email**: Use trigger_result_email tool - ALWAYS do this step
   - task_id: {task_id}
   - resource_arn: {resource_arn}
   - control_id: {control_id}
   - code_review_result: results from step 1
   - validation_result: results from step 3
   - is_rollback: False (email INCLUDES rollback link)
   - If remediation failed, set error_message accordingly

**IMPORTANT:**
- ALWAYS start with step 0 to get the code and execution result from Memory
- Execute ALL steps regardless of intermediate results
- The result email MUST be triggered even if verification fails

Return a JSON summary with code_review, execution_analysis, validation, security_hub_update, experience_saved, and result_email results.
"""

    logger.info(f"Running Validator Agent for task {task_id}, is_rollback={is_rollback}")

    try:
        result = agent(prompt)

        response_text = str(result.message) if hasattr(result, 'message') else str(result)

        # 解析验证结果
        validation_passed = False
        code_review_passed = False
        email_sent = False

        if '"passed": true' in response_text.lower():
            validation_passed = True
        if '"status": "passed"' in response_text.lower():
            code_review_passed = True
        if '"sent": true' in response_text.lower():
            email_sent = True

        logger.info(f"Validator completed for task {task_id}: validation_passed={validation_passed}, code_review_passed={code_review_passed}, email_sent={email_sent}")

        return {
            "success": validation_passed and code_review_passed,
            "task_id": task_id,
            "finding_id": finding_id,
            "is_rollback": is_rollback,
            "code_review_passed": code_review_passed,
            "validation_passed": validation_passed,
            "email_sent": email_sent,
            "response": response_text
        }

    except Exception as e:
        logger.exception(f"Validator failed for task {task_id}: {e}")
        return {
            "success": False,
            "task_id": task_id,
            "is_rollback": is_rollback,
            "error": str(e)
        }


def _get_expected_state(resource_type: str, control_id: str) -> dict:
    """根据资源类型和 Control ID 获取预期状态。

    Args:
        resource_type: 资源类型
        control_id: Control ID

    Returns:
        dict: 预期的安全配置状态
    """
    # S3 相关的 Controls
    s3_block_public_access_controls = ['S3.1', 'S3.2', 'S3.3']

    if resource_type == 'AwsS3Bucket':
        if control_id in s3_block_public_access_controls:
            return {
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True
            }

    elif resource_type == 'AwsEc2SecurityGroup':
        return {
            "no_unrestricted_inbound": True
        }

    elif resource_type == 'AwsIamRole':
        return {
            "no_wildcard_principal": True
        }

    # 默认返回空，让 Agent 根据 Control ID 判断
    return {}
