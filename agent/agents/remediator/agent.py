"""
Remediator Agent - Phase 2 修复智能体

负责生成修复代码并通过 Code Interpreter 执行，然后通过 A2A 协议调用 Validator Agent。
"""
import logging
from typing import Optional

from strands import Agent
from strands.models import BedrockModel

from shared.config import get_config, REMEDIATOR_MODEL_CONFIG
from shared.tools.memory_tools import get_analysis_context, set_memory_session
from shared.tools.execution import save_rollback_data, get_rollback_data, execute_code, save_task_event
from shared.tools.aws_resources import get_resource_config
from shared.tools.a2a_tools import invoke_validator_agent

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
严格按以下步骤执行：

1. **获取第一阶段上下文**: 使用 get_analysis_context 工具获取第一阶段的分析结果
2. **识别 agent_actions**: 从分析结果的 remediation.agent_actions 中提取需要执行的步骤
3. **获取当前状态**: 使用 get_resource_config 工具获取当前资源配置
   - resource_arn: 直接使用任务中的完整资源 ARN
   - resource_type: 直接使用任务中的资源类型 (如 AwsS3Bucket, AwsSnsTopic)
4. **保存回滚数据**: 在任何更改前使用 save_rollback_data 工具保存当前状态
5. **生成代码**: 仅针对 agent_actions 中的步骤创建 Python/Boto3 修复代码
6. **执行代码**: 使用 execute_code 工具执行生成的代码
7. **调用 Validator**: 使用 invoke_validator_agent 工具通过 A2A 协议调用 Validator Agent
   - 传递: task_id, resource_arn, resource_type, control_id, finding_id
   - 传递: 生成的代码 (generated_code), 执行结果 (execution_result)
   - 传递: memory_session_id, actor_id (用于 Memory 共享)
   - 传递: is_rollback=False (正常修复)
8. **报告结果**: 返回执行状态和 Validator 验证结果

# 代码生成指南
- 所有 AWS 操作使用 boto3
- 包含适当的 try/except 错误处理
- 添加注释说明每个步骤
- 尽可能使代码具有幂等性
- 使用环境变量配置区域 (AWS_REGION)
- 代码最后必须打印 JSON 格式的结果
- 记录重要操作以便调试
- **重要**: 生成的代码会被发送给 Validator 进行安全审查

# 代码模板
```python
import boto3
import os
import json

# 配置
region = os.environ.get('AWS_REGION', 'ap-northeast-1')

def remediate():
    \"\"\"执行修复\"\"\"
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
    actor_id = actor_id or f"task-{task_id}"

    # 复用 Phase 1 创建的 Memory Session
    session_manager = None

    if not memory_id:
        logger.warning("AGENTCORE_MEMORY_ID 未配置，将跳过 Memory 功能")
    else:
        try:
            from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager
            from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig

            memory_config = AgentCoreMemoryConfig(
                memory_id=memory_id,
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
            save_rollback_data,
            get_rollback_data,
            execute_code,  # Code Interpreter 执行
            save_task_event,
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
1. Get rollback data using get_rollback_data tool
2. Generate Python/boto3 rollback code to restore the resource to its pre-remediation state
3. Execute the rollback code using execute_code tool
4. Call Validator Agent using invoke_validator_agent tool with:
   - task_id: {task_id}
   - resource_arn: {resource_arn}
   - resource_type: {resource_type}
   - control_id: {control_id}
   - finding_id: {finding_id}
   - generated_code: the rollback code you generated
   - execution_result: the result from execute_code
   - memory_session_id: {memory_session_id}
   - actor_id: {actor_id}
   - is_rollback: true (IMPORTANT: this ensures the result email does NOT have a rollback link)

IMPORTANT:
- This is a rollback, so use get_rollback_data to get the pre-remediation state
- The rollback email should NOT contain a rollback link
- If rollback fails, Validator will alert the user to handle manually

Return a JSON summary with the rollback execution result and validator response.
"""
    else:
        prompt = f"""
Execute remediation for task {task_id}:

**Resource ARN:** {resource_arn}
**Resource Type:** {resource_type}
**Control ID:** {control_id}
**Finding ID:** {finding_id}

**Instructions:**
1. Get Phase 1 analysis context from Memory using get_analysis_context tool
2. Get current resource state using get_resource_config tool with resource_arn and resource_type
3. Save rollback data using save_rollback_data tool (CRITICAL - do this before any changes)
4. Generate Python/boto3 remediation code based on the Phase 1 analysis
5. Execute the generated code using execute_code tool
6. Call Validator Agent using invoke_validator_agent tool with:
   - task_id: {task_id}
   - resource_arn: {resource_arn}
   - resource_type: {resource_type}
   - control_id: {control_id}
   - finding_id: {finding_id}
   - generated_code: the remediation code you generated
   - execution_result: the result from execute_code
   - memory_session_id: {memory_session_id}
   - actor_id: {actor_id}
   - is_rollback: false

IMPORTANT:
- Save rollback data BEFORE generating or executing the remediation code
- The code should be self-contained and executable
- Include error handling in the generated code
- The code must print JSON result at the end
- ALWAYS call invoke_validator_agent after execute_code, whether execution succeeds or fails
- Validator will: review code security, verify results, update Security Hub, trigger result email

Return a JSON summary with:
- phase1_context_retrieved: whether you got the analysis context
- rollback_data_saved: whether rollback data was saved
- generated_code: the code you generated
- execution: the result from execute_code tool
- validator_response: the response from Validator Agent
"""

    logger.info(f"Running Remediator Agent for task {task_id}, is_rollback={is_rollback}")

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


