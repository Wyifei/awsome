"""
Remediator Agent - Phase 2 修复智能体

负责生成修复代码并通过 Code Interpreter 执行，然后通过 A2A 协议调用 Validator Agent。
"""
import logging
from typing import Optional

from strands import Agent
from strands.models import BedrockModel

from shared.config import get_config, REMEDIATOR_MODEL_CONFIG
from shared.tools.memory_tools import (
    get_analysis_context,
    set_memory_session,
    save_rollback_to_memory,
    get_rollback_from_memory,
    save_remediation_result,
)
from shared.tools.execution import execute_code, set_audit_context
from shared.tools.aws_resources import get_resource_config
from shared.tools.a2a_tools import invoke_validator_agent
from shared.tools.code_check import pre_execution_check

logger = logging.getLogger(__name__)

# Remediator Agent System Prompt
REMEDIATOR_SYSTEM_PROMPT = """# 角色
你是 SHARA (Security Hub Auto-Remediation Agent) 的修复智能体。
你的任务是根据第一阶段的分析结果生成并执行修复代码，然后通过 A2A 协议调用 Validator Agent 进行验证。

# 重要约束
- 你在人工审批通过后执行
- 始终优先获取第一阶段的分析上下文
- 在进行任何更改前必须保存回滚数据
- 必须通过 execute_code 工具在沙盒环境中执行代码
- **执行完成后必须调用 Validator Agent 进行代码审查和结果验证**

# ⚠️ 关键规则：只执行 agent_actions
第一阶段分析结果中的修复步骤分为三类：
- **prerequisites**: 审批前人工需要确认的前置条件 → **不要执行**
- **agent_actions**: Agent 需要执行的 AWS API 操作 → **只执行这些**
- **post_actions**: 修复后人工需要处理的后续操作 → **不要执行**

你**只能**为 `agent_actions` 列表中的步骤生成和执行代码。
prerequisites 和 post_actions 是给人工处理的，不在你的职责范围内。

# 执行流程
严格按以下步骤执行，**不要跳过任何步骤**：

## Phase A: 准备
1. **获取分析上下文**: 使用 get_analysis_context 工具
   - 返回值包含完整的 Finding 数据、分析结果、ASR Playbook、历史经验等
   - 你需要从中提取修复所需的信息（Region、资源 ARN、配置等）
2. **获取当前状态**: 使用 get_resource_config 工具获取 pre_state

## Phase B: 代码生成 (两个代码都必须生成)
3. **生成修复代码**:
   - **优先使用 ASR 代码模板**: 如果 get_analysis_context 返回了 asr_playbook.code_template，
     **必须基于该模板生成代码**，只需根据实际资源信息调整参数
   - 如果没有 ASR 模板，则根据 agent_actions 创建 Python/Boto3 代码
4. **[必须] 生成回滚代码**: 根据 pre_state 生成能恢复原始状态的代码
   - **不执行回滚代码**，只生成备用

## Phase C: 保存回滚数据 (执行前必须完成)
5. **[必须] 保存回滚数据**: 使用 save_rollback_to_memory 工具
   - task_id, resource_arn, resource_type, pre_state, rollback_code
   - **如果跳过此步骤，用户无法回滚！**

## Phase D: 执行修复 (含错误重试机制，同一沙箱 Session)
6. **验证修复代码**: 使用 pre_execution_check 工具
7. **执行修复代码**: 使用 execute_code 工具
   - 从 Finding 中提取 Region，传递给 `target_region` 参数
   - **首次执行时设置 `close_session=False`**，保持 session 用于可能的重试
   - 沙盒环境会设置 AWS_REGION 和 TARGET_REGION 环境变量

8. **[重要] 错误分析与重试** (最多重试 2 次，在同一沙箱 Session 中):
   如果 execute_code 返回 success=False:
   a. **分析错误原因**: 仔细阅读 stderr 中的错误信息
   b. **诊断问题**: 常见问题包括:
      - 变量作用域问题 (如 `name 'xxx' is not defined`)
      - 导入缺失
      - API 参数错误
      - 权限不足
   c. **修复代码**: 根据错误原因修改代码
   d. **重新执行**: 使用返回的 `session_id` 在同一沙箱中重试
      - 第一次重试: `execute_code(fixed_code, session_id=xxx, close_session=False)`
      - 第二次重试(最后): `execute_code(fixed_code, session_id=xxx, close_session=True)`

   **Session 复用示例**:
   ```
   # 首次执行 (保持 session)
   result1 = execute_code(code, target_region="ap-northeast-1", close_session=False)
   # result1 = {"success": False, "stderr": "name 'region' is not defined", "session_id": "abc123"}

   # 分析错误: 变量 region 在函数内使用但定义在外部
   # 修复: 将 region 定义移到函数内部

   # 第一次重试 (复用 session)
   result2 = execute_code(fixed_code, session_id="abc123", close_session=False)
   # 如果仍然失败，继续修复...

   # 第二次重试 (最后一次，关闭 session)
   result3 = execute_code(fixed_code2, session_id="abc123", close_session=True)
   ```

9. **关闭沙箱 Session**:
   - 如果执行成功且未关闭 session，调用 `execute_code(code="", session_id=xxx, close_session=True)` 关闭
   - 如果最后一次重试，设置 `close_session=True` 自动关闭

## Phase E: 保存和通知 (无论成功失败都执行)
9. **保存修复结果**: 使用 save_remediation_result 工具
10. **调用 Validator**: 使用 invoke_validator_agent 工具

# 代码生成指南

## ⭐ ASR 代码模板优先
如果 get_analysis_context 返回的数据中包含 `asr_playbook.code_template`：
- **这是经过 AWS 验证的标准修复代码**
- **必须以此模板为基础**，只替换资源标识符（如 bucket name、ARN 等）
- 不要从头重写，只做必要的参数调整

## 📖 参考历史经验
如果 get_analysis_context 返回的数据中包含 `top_experience`：
- 这是之前成功修复类似问题的经验
- 参考其中的 `situation` 了解类似场景
- 参考其中的 `key_insights` 获取修复经验教训
- 避免重复之前遇到的问题

## 通用指南
- 所有 AWS 操作使用 boto3
- 包含适当的 try/except 错误处理
- 添加注释说明每个步骤
- 尽可能使代码具有幂等性
- 代码最后必须打印 JSON 格式的结果
- 记录重要操作以便调试
- **重要**: 生成的代码会被发送给 Validator 进行安全审查

## 🔧 代码健壮性要求 (避免执行失败)
- **变量定义在函数内部**: 所有变量（包括 region、资源名称等）都应在函数内部定义，避免作用域问题
- **导入语句在顶部**: 确保所有需要的模块都已导入
- **避免全局变量**: 沙盒环境可能有变量作用域限制

# 代码模板
```python
import boto3
import os
import json

def remediate():
    \"\"\"执行修复\"\"\"
    # Region 从环境变量获取 (execute_code 的 target_region 参数会设置这些变量)
    region = os.environ.get('AWS_REGION', 'ap-northeast-1')

    # 初始化客户端
    client = boto3.client('service_name', region_name=region)

    try:
        # 步骤 1: 描述操作
        # ... 实现 ...

        # 步骤 2: 描述操作
        # ... 实现 ...

        return {
            'success': True,
            'message': '修复成功完成',
            'details': {...}  # 修复详情
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# 执行并输出结果
result = remediate()
print(json.dumps(result, default=str))
```

**环境变量说明**:
- `execute_code(code, target_region="ap-northeast-1")` 会在沙盒中设置:
  - `AWS_REGION` = target_region
  - `AWS_DEFAULT_REGION` = target_region
  - `TARGET_REGION` = target_region
- 代码中使用 `os.environ.get('AWS_REGION')` 获取

# 输出格式
返回以下结构的 JSON 对象：

{
  "phase1_context_retrieved": true,
  "agent_actions_executed": [
    "调用 API 修改配置",
    "验证配置生效"
  ],
  "skipped_steps": {
    "prerequisites": ["人工需要确认的前置条件..."],
    "post_actions": ["人工需要处理的后续操作..."]
  },
  "rollback_data_saved": true,
  "generated_code": {
    "language": "python",
    "code": "import boto3..."
  },
  "pre_execution_check": {
    "safe_to_execute": true,
    "blocked_reasons": [],
    "warnings": []
  },
  "execution": {
    "status": "success",
    "exit_code": 0,
    "stdout": "...",
    "stderr": "",
    "execution_time_ms": 1234
  },
  "validator_response": {
    "success": true,
    "code_review": {
      "status": "passed",
      "issues": [],
      "risk_level": "low"
    },
    "verification": {
      "passed": true,
      "checks": [...]
    },
    "result_email": {
      "sent": true,
      "includes_rollback_link": true
    }
  }
}

# 重要安全规则
- 绝不在保存回滚数据之前执行 execute_code
- **绝不在 pre_execution_check 通过之前执行 execute_code**
- 如果 pre_execution_check 返回 safe_to_execute=False，必须停止并重新生成代码
- 遇到任何错误立即停止 - 不要继续进行部分更改
- 记录所有操作以便审计
- 如果第一阶段上下文表明操作具有破坏性，需要额外确认
- **只执行 agent_actions，忽略 prerequisites 和 post_actions**
- **代码执行后必须调用 Validator Agent 进行审查和验证**
"""


def create_remediator_agent(
    task_id: str,
    memory_session_id: str,
    memory_id: str,
    region: Optional[str] = None,
    actor_id: Optional[str] = None
) -> Agent:
    """创建 Remediator Agent 实例。

    Args:
        task_id: 任务 ID
        memory_session_id: Memory Session ID (复用 Phase 1 的 Session)
        memory_id: AgentCore Memory ID
        region: AWS Region (可选)
        actor_id: Actor ID (可选，需要与 Analyzer 使用相同的值)

    Returns:
        Agent: 配置好的 Remediator Agent
    """
    config = get_config()
    region = region or config.region

    # 使用与 Analyzer 相同的 actor_id
    if not actor_id:
        logger.warning("actor_id not provided, using task_id as fallback")
        actor_id = f"task-{task_id}"

    # 复用 Phase 1 创建的 Memory Session
    session_manager = None

    # Use provided memory_id or fall back to config
    effective_memory_id = memory_id or config.memory_id

    if not effective_memory_id:
        logger.warning("AGENTCORE_MEMORY_ID 未配置，Memory 功能将不可用")
    else:
        try:
            from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager
            from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig

            memory_config = AgentCoreMemoryConfig(
                memory_id=effective_memory_id,  # 使用 effective_memory_id
                actor_id=actor_id,  # 使用与 Analyzer 相同的 actor_id
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

    # 配置 LLM - 使用较低的 temperature 确保代码生成稳定
    # streaming=False 用于绕过 strands SDK 1.24.0 中的流式处理 bug
    model = BedrockModel(
        model_id=REMEDIATOR_MODEL_CONFIG.model_id,
        temperature=REMEDIATOR_MODEL_CONFIG.temperature,
        max_tokens=REMEDIATOR_MODEL_CONFIG.max_tokens,
        region_name=region,
        streaming=False
    )

    # 创建 Agent
    agent = Agent(
        model=model,
        system_prompt=REMEDIATOR_SYSTEM_PROMPT,
        tools=[
            get_analysis_context,
            save_rollback_to_memory,  # 保存回滚数据到 Memory
            get_rollback_from_memory,  # 从 Memory 获取回滚数据
            save_remediation_result,  # 保存修复代码和执行结果到 Memory (供 Validator 获取)
            pre_execution_check,  # 执行前快速安全检查
            execute_code,  # Code Interpreter 执行
            get_resource_config,
            invoke_validator_agent,  # A2A 调用 Validator Agent
        ],
        session_manager=session_manager,
    )

    logger.info(f"Created Remediator Agent for task {task_id}")
    return agent


def run_remediator(
    agent: Agent,
    task_id: str,
    resource_arn: str,
    resource_type: str,
    control_id: str = "",
    finding_id: str = "",
    memory_session_id: str = "",
    actor_id: str = "",
    is_rollback: bool = False
) -> dict:
    """运行 Remediator Agent 生成并执行修复代码，然后调用 Validator Agent。

    Agent 会按以下步骤执行：
    1. 从 Memory 获取 Phase 1 分析结果
    2. 获取资源当前状态
    3. 保存回滚数据
    4. 生成修复代码
    5. 通过 execute_code 工具执行代码
    6. 通过 A2A 协议调用 Validator Agent 进行审查和验证

    Args:
        agent: Remediator Agent 实例
        task_id: 任务 ID
        resource_arn: 资源 ARN
        resource_type: 资源类型
        control_id: Security Hub Control ID (如 S3.8)
        finding_id: Security Hub Finding ID
        memory_session_id: Memory Session ID (用于 Validator 共享上下文)
        actor_id: Actor ID (用于 Memory 操作)
        is_rollback: 是否为回滚操作

    Returns:
        dict: 执行结果，包含 success, task_id, resource_arn, response, validator_response
    """
    if is_rollback:
        prompt = f"""
Execute ROLLBACK for task {task_id}:

**Resource ARN:** {resource_arn}
**Resource Type:** {resource_type}
**Control ID:** {control_id}
**Finding ID:** {finding_id}

This is a ROLLBACK operation. The user has requested to revert the remediation.

**Instructions:**

**PHASE A: Get Rollback Data**
1. Get rollback data using get_rollback_from_memory tool with:
   - task_id: {task_id}
   - resource_arn: {resource_arn}
   - This should return pre_state and pre-generated rollback_code

2. **CHECK THE RESULT**: If get_rollback_from_memory returns success=False:
   - Call invoke_validator_agent with is_rollback=true and rollback_failed=true
   - Return an error response indicating rollback data was not found
   - Do NOT proceed with the remaining steps

**PHASE B: Execute Rollback (if data found)**
3. If rollback data was found (success=True):
   - 获取 finding 的 Region (从 get_analysis_context 或回滚数据中)
   - **直接执行预生成的回滚代码** - 使用 execute_code 工具执行 rollback_code
   - 传递 target_region 参数给 execute_code
   - 回滚代码在修复时已经生成并验证过，直接执行即可
   - **不需要重新生成代码**
   - Record the execution result (success or failure)

**PHASE C: Save and Notify (ALWAYS execute, even if rollback execution failed)**
4. Save rollback execution result to Memory using save_remediation_result tool:
   - task_id: {task_id}
   - resource_arn: {resource_arn}
   - generated_code: the rollback_code from step 1
   - execution_result: the result from execute_code (include error info if failed)
   - **IMPORTANT**: Save even if execution failed

5. **[ALWAYS]** Call Validator Agent using invoke_validator_agent tool with:
   - task_id: {task_id}
   - resource_arn: {resource_arn}
   - resource_type: {resource_type}
   - control_id: {control_id}
   - finding_id: {finding_id}
   - memory_session_id: {memory_session_id}
   - actor_id: {actor_id}
   - is_rollback: true (IMPORTANT: this ensures the result email does NOT have a rollback link)
   - **CRITICAL**: ALWAYS call Validator regardless of execution result
   - If execution failed, Validator will send failure notification email to user

**CHECKLIST before finishing:**
- [ ] Did you get rollback data from Memory? (Step 1)
- [ ] Did you execute rollback code? (Step 3)
- [ ] Did you save execution result to Memory? (Step 4 - even if failed)
- [ ] Did you call invoke_validator_agent? (Step 5 - ALWAYS, even if failed)

**IMPORTANT**:
- Use get_rollback_from_memory (NOT get_rollback_data) to get the saved rollback data
- The rollback_code was pre-generated during remediation - execute it directly
- Do NOT generate new rollback code - use the saved one
- **Even if rollback execution fails, you MUST still call Validator**
- The user needs to be notified of the result via email

Return a JSON summary with the rollback execution result and validator response.
"""
    else:
        prompt = f"""
Execute remediation for task {task_id}:

**Resource ARN:** {resource_arn}
**Resource Type:** {resource_type}
**Control ID:** {control_id}
**Finding ID:** {finding_id}

**CRITICAL: You MUST complete ALL steps in order. Do NOT skip any step.**

**Instructions:**

**PHASE A: Preparation**
1. Get Phase 1 analysis context using get_analysis_context tool
   - 返回值包含: finding (完整 ASFF 数据), analysis, remediation_description, asr_playbook, top_experience
   - 从 finding 中提取 Region、资源 ARN 等修复所需信息
2. Get current resource state (pre_state) using get_resource_config tool
   - resource_arn: {resource_arn}
   - resource_type: {resource_type}

**PHASE B: Code Generation (BOTH codes required)**
3. Generate Python/boto3 REMEDIATION code based on the Phase 1 analysis
4. Generate Python/boto3 ROLLBACK code based on pre_state
   - Rollback code should restore the resource to the state from step 2
   - **Do NOT execute rollback code** - only generate it

**PHASE C: Save Rollback Data (MANDATORY - do this BEFORE executing)**
5. **[MANDATORY]** Save rollback data using save_rollback_to_memory tool:
   - task_id: {task_id}
   - resource_arn: {resource_arn}
   - resource_type: {resource_type}
   - pre_state: the state from step 2
   - rollback_code: the code from step 4
   - **If you skip this step, user CANNOT rollback!**

**PHASE D: Execute Remediation (with retry in same sandbox session)**
6. Validate remediation code using pre_execution_check tool
   - If safe_to_execute=False, regenerate code and repeat step 6
7. Execute remediation code using execute_code tool:
   - 从 finding.Region 提取 region，传递给 target_region 参数
   - **IMPORTANT**: Set `close_session=False` to keep session open for potential retries
   - 沙盒环境会自动设置 AWS_REGION 环境变量
8. **[IMPORTANT] If execution fails (success=False), RETRY up to 2 times in SAME session:**
   a. **Analyze the error**: Read stderr carefully to understand the root cause
      - Common errors: variable scope issues, import errors, API errors
      - Example: "name 'region' is not defined" → variable defined outside function
   b. **Fix the code**: Modify the code to address the specific error
   c. **Re-execute with session_id**: Call execute_code with the returned session_id
      - First retry: `execute_code(fixed_code, session_id=xxx, close_session=False)`
      - Last retry: `execute_code(fixed_code, session_id=xxx, close_session=True)`
   d. **Repeat if needed**: Max 2 retries, then close session

   **Session Reuse Example:**
   ```
   # First attempt (keep session open)
   result1 = execute_code(code, target_region="ap-northeast-1", close_session=False)
   # Returns: {{"success": False, "session_id": "abc123", "stderr": "..."}}

   # Fix code based on error...

   # Retry 1 (reuse session)
   result2 = execute_code(fixed_code, session_id="abc123", close_session=False)

   # Retry 2 (final, close session)
   result3 = execute_code(fixed_code2, session_id="abc123", close_session=True)
   ```

9. **Close session after success**: If execution succeeded with close_session=False:
   - Call `execute_code(code="", session_id=xxx, close_session=True)` to close the session

**PHASE E: Save and Notify (ALWAYS execute after all retries)**
10. Save remediation result using save_remediation_result tool:
    - task_id: {task_id}
    - resource_arn: {resource_arn}
    - generated_code: the FINAL remediation code (after any fixes)
    - execution_result: the result from last execution attempt
    - **IMPORTANT**: Save even if all retries failed

11. **[ALWAYS]** Call Validator using invoke_validator_agent tool:
   - task_id: {task_id}
   - resource_arn: {resource_arn}
   - resource_type: {resource_type}
   - control_id: {control_id}
   - finding_id: {finding_id}
   - memory_session_id: {memory_session_id}
   - actor_id: {actor_id}
   - is_rollback: false
   - **CRITICAL**: ALWAYS call Validator regardless of execution result
   - If execution failed, Validator will send failure notification email to user

**CHECKLIST before finishing:**
- [ ] Did you call save_rollback_to_memory? (Step 5 - MANDATORY)
- [ ] Did you pass `target_region` and `close_session=False` on first execute_code? (Step 7)
- [ ] Did you retry with `session_id` on failure? (Step 8, up to 2 retries in same session)
- [ ] Did you close the session? (Step 9, set `close_session=True` on last call)
- [ ] Did you call save_remediation_result? (Step 10 - even if all retries failed)
- [ ] Did you call invoke_validator_agent? (Step 11 - ALWAYS, even if failed)

**IMPORTANT**:
- 从 get_analysis_context 返回的 finding 中提取所需信息（Region、资源 ARN 等）
- If execution fails, analyze the error and retry with fixed code (up to 2 times)
- Even if all retries fail, you MUST still call Validator for user notification

Return a JSON summary with rollback_data_saved, execution_result, and validator_response.
"""

    logger.info(f"Running Remediator Agent for task {task_id}, is_rollback={is_rollback}")

    # 设置审计上下文，用于 execute_code 自动上传审计日志到 S3
    set_audit_context(
        task_id=task_id,
        control_id=control_id,
        resource_arn=resource_arn,
        resource_type=resource_type,
        is_rollback=is_rollback
    )

    try:
        result = agent(prompt)

        response_text = str(result.message) if hasattr(result, 'message') else str(result)

        # 尝试解析执行结果
        execution_success = False
        validator_called = False

        if 'success' in response_text.lower():
            # 简单检查是否包含成功标识
            if '"success": true' in response_text.lower() or '"status": "success"' in response_text.lower():
                execution_success = True

        # 检查是否调用了 Validator
        if 'validator_response' in response_text.lower() or 'invoke_validator' in response_text.lower():
            validator_called = True

        logger.info(f"Remediator completed for task {task_id}, execution_success={execution_success}, validator_called={validator_called}")

        return {
            "success": execution_success,
            "task_id": task_id,
            "resource_arn": resource_arn,
            "is_rollback": is_rollback,
            "validator_called": validator_called,
            "response": response_text
        }

    except Exception as e:
        logger.exception(f"Remediator failed for task {task_id}: {e}")
        return {
            "success": False,
            "task_id": task_id,
            "is_rollback": is_rollback,
            "error": str(e)
        }


