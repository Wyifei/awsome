"""
Remediator Agent - Phase 2 修复智能体

负责生成修复代码并通过 Code Interpreter 执行，然后通过 A2A 协议调用 Validator Agent。

支持两种修复类型:
- aws_api: AWS 配置类问题，通过 execute_code 执行 boto3 代码
- github_pr: 容器漏洞，通过 GitHub MCP 创建 Pull Request
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
    save_pr_result,
)
from shared.tools.execution import execute_code, set_audit_context
from shared.tools.aws_resources import get_resource_config
from shared.tools.a2a_tools import invoke_validator_agent
from shared.tools.code_check import pre_execution_check
from shared.tools.github_mcp_client import (
    read_github_file,
    create_github_branch,
    push_files_to_github,
    create_pull_request,
)

logger = logging.getLogger(__name__)

# ============================================================
# AWS API 模式 System Prompt (标准 Security Hub 修复)
# ============================================================
AWS_API_REMEDIATOR_SYSTEM_PROMPT = """# 角色
你是 SHARA (Security Hub Auto-Remediation Agent) 的修复智能体。
你的任务是根据第一阶段的分析结果生成并执行修复代码，然后通过 A2A 协议调用 Validator Agent 进行验证。

# 重要约束
- 你在人工审批通过后执行
- 始终优先获取第一阶段的分析上下文
- 在进行任何更改前必须保存回滚数据
- 必须通过 execute_code 工具在沙盒环境中执行代码
- **执行完成后必须调用 Validator Agent 进行代码审查和结果验证**

# ⚠️ 关键规则：只执行 agent_actions
- **prerequisites**: 审批前人工需要确认 → **不要执行**
- **agent_actions**: Agent 需要执行的 AWS API 操作 → **只执行这些**
- **post_actions**: 修复后人工需要处理 → **不要执行**

# 执行流程

## Phase A: 准备
1. **获取分析上下文**: 使用 get_analysis_context 工具
2. **获取当前状态**: 使用 get_resource_config 工具获取 pre_state

## Phase B: 代码生成
3. **生成修复代码**: 优先使用 ASR 代码模板
4. **[必须] 生成回滚代码**: 根据 pre_state 生成

## Phase C: 保存回滚数据
5. **[必须] 保存回滚数据**: 使用 save_rollback_to_memory 工具

## Phase D: 执行修复
6. **验证修复代码**: 使用 pre_execution_check 工具
7. **执行修复代码**: 使用 execute_code 工具
   - 首次执行设置 `close_session=False`
8. **错误分析与重试**: 最多重试 2 次
9. **关闭沙箱 Session**

## Phase E: 保存和通知
10. **保存修复结果**: 使用 save_remediation_result 工具
11. **调用 Validator**: 使用 invoke_validator_agent 工具

# 代码模板
```python
import boto3
import os
import json

def remediate():
    region = os.environ.get('AWS_REGION', 'ap-northeast-1')
    client = boto3.client('service_name', region_name=region)
    try:
        # 执行修复...
        return {'success': True, 'message': '修复成功完成'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

result = remediate()
print(json.dumps(result, default=str))
```

# 重要安全规则
- 绝不在保存回滚数据之前执行 execute_code
- 绝不在 pre_execution_check 通过之前执行 execute_code
- 只执行 agent_actions
- 代码执行后必须调用 Validator Agent
"""

# ============================================================
# GitHub PR 模式 System Prompt (容器漏洞修复)
# ============================================================
GITHUB_PR_REMEDIATOR_SYSTEM_PROMPT = """# 角色
你是 SHARA (Security Hub Auto-Remediation Agent) 的修复智能体。
你的任务是根据第一阶段的分析结果创建 GitHub Pull Request 修复容器漏洞。

# 重要约束
- 你在人工审批通过后执行
- **不执行代码**，只创建 GitHub PR
- 所有漏洞将在一个 PR 中统一修复
- **执行完成后必须调用 Validator Agent**

# 可用工具
- **get_analysis_context**: 获取 Phase 1 分析结果
- **read_github_file**: 读取 GitHub 仓库中的文件
- **create_github_branch**: 创建修复分支
- **push_files_to_github**: 推送文件变更
- **create_pull_request**: 创建 Pull Request
- **save_pr_result**: 保存 PR 结果到 Memory
- **invoke_validator_agent**: 调用 Validator Agent

# 执行流程

## Phase A: 获取分析上下文
1. **获取 Phase 1 分析结果**: 使用 get_analysis_context 工具
   - 返回值包含 file_changes, pr_metadata, service_info, vulnerabilities

## Phase B: 读取当前文件内容
2. **读取需要修改的文件**: 使用 read_github_file 工具

## Phase C: 创建分支和推送变更
3. **创建修复分支**: 使用 create_github_branch 工具
4. **推送文件变更**: 使用 push_files_to_github 工具
   - commit message 根据漏洞数量生成

## Phase D: 创建 Pull Request
5. **创建 PR**: 使用 create_pull_request 工具

## Phase E: 保存结果和通知
6. **保存 PR 结果**: 使用 save_pr_result 工具
7. **调用 Validator**: 使用 invoke_validator_agent 工具
   - 传递 remediation_type: "github_pr"

# 输出格式
```json
{
  "phase1_context_retrieved": true,
  "remediation_type": "github_pr",
  "branch_created": "security/fix-my-service-cve-20240204",
  "files_pushed": [...],
  "pull_request": {
    "number": 42,
    "url": "https://github.com/owner/repo/pull/42",
    "title": "[Security] 修复容器镜像漏洞",
    "state": "open"
  },
  "pr_result_saved": true,
  "validator_response": {...}
}
```

# 注意事项
- **不使用 execute_code**: PR 工作流不执行代码
- **不使用 save_rollback_to_memory**: PR 可以通过关闭来回滚
- **不使用 pre_execution_check**: PR 内容由人工 Review
- **必须保存 PR 结果**: 使用 save_pr_result
- **必须调用 Validator**: 使用 invoke_validator_agent
"""

# 向后兼容
REMEDIATOR_SYSTEM_PROMPT = AWS_API_REMEDIATOR_SYSTEM_PROMPT


def create_remediator_agent(
    task_id: str,
    memory_session_id: str,
    memory_id: str,
    region: Optional[str] = None,
    actor_id: Optional[str] = None,
    remediation_type: str = "aws_api"
) -> Agent:
    """创建 Remediator Agent 实例。

    Args:
        task_id: 任务 ID
        memory_session_id: Memory Session ID (复用 Phase 1 的 Session)
        memory_id: AgentCore Memory ID
        region: AWS Region (可选)
        actor_id: Actor ID (可选，需要与 Analyzer 使用相同的值)
        remediation_type: 修复类型 ("aws_api" 或 "github_pr")，决定使用哪个 System Prompt

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

            # NOTE: 由于 bedrock-agentcore SDK 1.2.0 与 strands-agents SDK 1.24.0 的兼容性问题，
            # AgentCoreMemorySessionManager.list_messages() 在处理旧格式数据时会报错：
            # "SessionMessage.__init__() missing 2 required positional arguments: 'message' and 'message_id'"
            # 因此我们不将 session_manager 传给 Agent，而是只用它来设置 _memory_session。
            # 这样 Agent 仍然可以通过 Memory 工具使用 Memory，
            # 但 Agent 不会尝试自动加载历史消息（避免触发这个 bug）。
            session_manager = None  # 不传给 Agent，避免 list_messages bug

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

    # 根据 remediation_type 选择 System Prompt 和工具
    if remediation_type == "github_pr":
        # GitHub PR 模式 - 容器漏洞修复
        system_prompt = GITHUB_PR_REMEDIATOR_SYSTEM_PROMPT
        tools = [
            get_analysis_context,  # 获取分析上下文
            read_github_file,  # 读取 GitHub 文件
            create_github_branch,  # 创建分支
            push_files_to_github,  # 推送文件
            create_pull_request,  # 创建 PR
            save_pr_result,  # 保存 PR 结果
            invoke_validator_agent,  # 调用 Validator
        ]
        logger.info("Using GitHub PR mode - container vulnerability remediation")
    else:
        # AWS API 模式 - 标准 Security Hub 修复
        system_prompt = AWS_API_REMEDIATOR_SYSTEM_PROMPT
        tools = [
            get_analysis_context,
            save_rollback_to_memory,  # 保存回滚数据
            get_rollback_from_memory,  # 获取回滚数据
            save_remediation_result,  # 保存修复结果
            pre_execution_check,  # 执行前安全检查
            execute_code,  # Code Interpreter 执行
            get_resource_config,
            invoke_validator_agent,  # 调用 Validator
        ]
        logger.info("Using AWS API mode - standard Security Hub remediation")

    # 创建 Agent
    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        tools=tools,
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


def run_github_pr_remediator(
    agent: Agent,
    task_id: str,
    resource_arn: str,
    finding_id: str,
    memory_session_id: str,
    actor_id: str,
    github_owner: str = "Wyifei",
    github_repo: str = "awsome"
) -> dict:
    """运行 Remediator Agent 创建 GitHub PR 修复容器漏洞。

    此函数用于 github_pr 模式，不执行代码，而是创建 Pull Request。

    Args:
        agent: Remediator Agent 实例
        task_id: 任务 ID
        resource_arn: 容器镜像 ARN
        finding_id: Security Hub Finding ID
        memory_session_id: Memory Session ID
        actor_id: Actor ID
        github_owner: GitHub 用户/组织
        github_repo: GitHub 仓库名

    Returns:
        dict: 执行结果
    """
    prompt = f"""
执行容器漏洞的 GitHub PR 修复:

**任务 ID:** {task_id}
**修复类型:** github_pr
**资源 ARN:** {resource_arn}
**Finding ID:** {finding_id}
**GitHub 仓库:** {github_owner}/{github_repo}

**重要: 严格按照 GitHub PR 工作流执行。不要使用 execute_code。**

**⚠️ 语言要求: PR 标题、描述、commit message 必须使用中文！**

**执行步骤:**

**阶段 A: 获取分析上下文**
1. 使用 get_analysis_context 工具获取 Phase 1 分析结果
   - task_id: {task_id}
   - 返回内容: file_changes, service_info, vulnerabilities

**阶段 B: 验证当前文件**
2. 对于 file_changes 中的每个文件，使用 read_github_file 验证:
   - owner: {github_owner}
   - repo: {github_repo}
   - path: file_changes[].path

**阶段 C: 创建分支并推送变更**
3. 使用 create_github_branch 创建修复分支:
   - owner: {github_owner}
   - repo: {github_repo}
   - branch: 格式为 "security/fix-服务名-cve-日期" (如 "security/fix-analyzer-cve-20240204")

4. 使用 push_files_to_github 推送文件变更:
   - owner: {github_owner}
   - repo: {github_repo}
   - branch: 步骤 3 创建的分支
   - files: 使用 file_changes[].suggested_content 构建 {{path, content}} 数组
   - message: **必须中文**，格式如:
     - 单漏洞: "fix(security): 升级 PACKAGE 修复 CVE-2024-xxxxx"
     - 多漏洞: "fix(security): 升级依赖修复 N 个漏洞 (CVE-2024-xxx, CVE-2024-yyy)"

**阶段 D: 创建 Pull Request**
5. 使用 create_pull_request 创建 PR:
   - owner: {github_owner}
   - repo: {github_repo}
   - title: **必须中文**，格式: "[安全] 修复 服务名 容器镜像漏洞 (N 个 CVE)"
   - body: **必须中文**，包含以下内容:
     ```
     ## 概述
     修复 服务名 容器镜像中的 N 个安全漏洞。

     ## 修复的漏洞
     | CVE ID | 严重性 | 软件包 | 当前版本 | 修复版本 |
     |--------|--------|--------|----------|----------|
     | CVE-xxx | HIGH | package | 1.0.0 | 2.0.0 |

     ## 变更内容
     - 更新 `path/to/file` 中的依赖版本

     ## 测试建议
     - 构建镜像并运行测试
     - 验证应用功能正常

     ---
     🤖 由 SHARA 自动生成
     ```
   - head: 步骤 3 创建的分支
   - base: "master"

**阶段 E: 保存结果并通知**
6. 使用 save_pr_result 保存 PR 结果:
   - task_id: {task_id}
   - resource_arn: {resource_arn}
   - pr_info: {{pr_number, pr_url, branch_name, title, state}}
   - files_changed: {{path, change_type, description}} 列表

7. **[必须]** 使用 invoke_validator_agent 调用 Validator:
   - task_id: {task_id}
   - resource_arn: {resource_arn}
   - resource_type: "AwsEcrContainerImage"
   - control_id: ""
   - finding_id: {finding_id}
   - memory_session_id: {memory_session_id}
   - actor_id: {actor_id}
   - is_rollback: false
   - remediation_type: "github_pr"

**检查清单:**
- [ ] 获取分析上下文? (步骤 1)
- [ ] 验证文件内容? (步骤 2)
- [ ] 创建分支? (步骤 3)
- [ ] 推送文件? (步骤 4)
- [ ] 创建 PR (中文标题和描述)? (步骤 5)
- [ ] 保存 PR 结果? (步骤 6)
- [ ] 调用 invoke_validator_agent? (步骤 7 - 必须)

返回 JSON 摘要，包含 branch_created, files_pushed, pull_request, pr_result_saved, validator_response。
"""

    logger.info(f"Running GitHub PR Remediator for task {task_id}")

    try:
        result = agent(prompt)

        response_text = str(result.message) if hasattr(result, 'message') else str(result)

        # 检查 PR 是否创建成功
        pr_created = False
        validator_called = False

        if 'pull_request' in response_text.lower() and 'number' in response_text.lower():
            pr_created = True

        if 'validator_response' in response_text.lower() or 'invoke_validator' in response_text.lower():
            validator_called = True

        logger.info(f"GitHub PR Remediator completed for task {task_id}, pr_created={pr_created}, validator_called={validator_called}")

        return {
            "success": pr_created,
            "task_id": task_id,
            "resource_arn": resource_arn,
            "remediation_type": "github_pr",
            "pr_created": pr_created,
            "validator_called": validator_called,
            "response": response_text
        }

    except Exception as e:
        logger.exception(f"GitHub PR Remediator failed for task {task_id}: {e}")
        return {
            "success": False,
            "task_id": task_id,
            "remediation_type": "github_pr",
            "error": str(e)
        }
