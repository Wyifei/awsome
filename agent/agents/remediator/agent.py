"""
Remediator Agent - Phase 2 修复智能体

负责生成修复代码并通过 Code Interpreter 执行。
"""
import logging
from typing import Optional

from strands import Agent
from strands.models import BedrockModel

from agents.config import get_config, REMEDIATOR_MODEL_CONFIG
from agents.tools.memory_tools import get_analysis_context, set_memory_session
from agents.tools.execution import save_rollback_data, get_rollback_data, save_task_event
from agents.tools.aws_resources import (
    get_s3_bucket_info,
    get_security_group_rules,
    get_iam_role_info,
)

logger = logging.getLogger(__name__)

# Remediator Agent System Prompt
REMEDIATOR_SYSTEM_PROMPT = """# Role
You are the Remediator Agent for SHARA (Security Hub Auto-Remediation Agent).
Your job is to generate and execute remediation code based on the analysis from Phase 1.

# CRITICAL CONSTRAINTS
- You operate AFTER human approval has been received
- ALWAYS retrieve Phase 1 analysis context first
- ALWAYS save rollback data before making ANY changes
- Execute code through the provided execution mechanism

# Execution Process
Follow these steps strictly in order:

1. **Get Phase 1 Context**: Use get_analysis_context tool to retrieve the analysis results from Phase 1
2. **Gather Current State**: Get the current resource configuration using appropriate tools
3. **Save Rollback Data**: Use save_rollback_data tool to save current state BEFORE any changes
4. **Generate Code**: Create Python/Boto3 remediation code based on the analysis
5. **Execute Code**: The code will be executed in a sandboxed environment
6. **Report Results**: Return execution status, outputs, and any errors

# Code Generation Guidelines
- Use boto3 for all AWS operations
- Include proper error handling with try/except blocks
- Add comments explaining each step
- Make code idempotent when possible
- Use environment variables for region configuration
- Log important actions for debugging

# Code Template
```python
import boto3
import os

# Configuration
region = os.environ.get('AWS_REGION', 'us-east-1')

def remediate():
    \"\"\"Execute remediation\"\"\"
    # Initialize client
    client = boto3.client('service_name', region_name=region)

    try:
        # Step 1: Describe action
        # ... implementation ...

        # Step 2: Describe action
        # ... implementation ...

        return {
            'success': True,
            'message': 'Remediation completed successfully'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# Execute
result = remediate()
print(result)
```

# Output Format
Return a JSON object with this structure:

{
  "phase1_context_retrieved": true,
  "rollback_data_saved": true,
  "generated_code": {
    "language": "python",
    "code": "import boto3..."
  },
  "execution": {
    "status": "success",
    "started_at": "2025-01-29T10:00:00Z",
    "completed_at": "2025-01-29T10:00:05Z",
    "output": {...},
    "error": null
  }
}

# Important Safety Rules
- NEVER execute without saving rollback data first
- Stop immediately on any error - do not continue with partial changes
- Log all actions for audit purposes
- If the Phase 1 context indicates the operation is destructive, add extra confirmation
"""


def create_remediator_agent(
    task_id: str,
    memory_session_id: str,
    memory_id: str,
    region: Optional[str] = None
) -> Agent:
    """创建 Remediator Agent 实例。

    Args:
        task_id: 任务 ID
        memory_session_id: Memory Session ID (复用 Phase 1 的 Session)
        memory_id: AgentCore Memory ID
        region: AWS Region (可选)

    Returns:
        Agent: 配置好的 Remediator Agent
    """
    config = get_config()
    region = region or config.region

    # 复用 Phase 1 创建的 Memory Session
    try:
        from bedrock_agentcore.memory.integrations.strands import (
            AgentCoreMemorySessionManager,
            AgentCoreMemoryConfig,
        )

        memory_config = AgentCoreMemoryConfig(
            memory_id=memory_id,
            actor_id=f"task-{task_id}",
            session_id=memory_session_id  # 使用同一个 Session
        )

        session_manager = AgentCoreMemorySessionManager(
            agentcore_memory_config=memory_config,
            region_name=region
        )

        # 设置全局 memory session 供工具使用
        set_memory_session(session_manager.get_session())

        logger.info(f"Connected to Memory session {memory_session_id} for task {task_id}")

    except ImportError:
        logger.warning("AgentCore Memory SDK not available")
        session_manager = None
    except Exception as e:
        logger.warning(f"Failed to connect to Memory session: {e}")
        session_manager = None

    # 配置 LLM - 使用较低的 temperature 确保代码生成稳定
    model = BedrockModel(
        model_id=REMEDIATOR_MODEL_CONFIG.model_id,
        temperature=REMEDIATOR_MODEL_CONFIG.temperature,
        max_tokens=REMEDIATOR_MODEL_CONFIG.max_tokens,
        top_p=REMEDIATOR_MODEL_CONFIG.top_p,
        region_name=region
    )

    # 创建 Agent
    agent = Agent(
        model=model,
        system_prompt=REMEDIATOR_SYSTEM_PROMPT,
        tools=[
            get_analysis_context,
            save_rollback_data,
            get_rollback_data,
            save_task_event,
            get_s3_bucket_info,
            get_security_group_rules,
            get_iam_role_info,
        ],
        session_manager=session_manager,
    )

    logger.info(f"Created Remediator Agent for task {task_id}")
    return agent


def run_remediator(
    agent: Agent,
    task_id: str,
    resource_arn: str,
    resource_type: str
) -> dict:
    """运行 Remediator Agent 生成并执行修复代码。

    Args:
        agent: Remediator Agent 实例
        task_id: 任务 ID
        resource_arn: 资源 ARN
        resource_type: 资源类型

    Returns:
        dict: 执行结果
    """
    prompt = f"""
Execute remediation for task {task_id}:

**Resource ARN:** {resource_arn}
**Resource Type:** {resource_type}

**Instructions:**
1. Get Phase 1 analysis context from Memory using get_analysis_context tool
2. Get current resource state using the appropriate tool (get_s3_bucket_info, get_security_group_rules, etc.)
3. Save rollback data using save_rollback_data tool (CRITICAL - do this before any changes)
4. Generate Python/boto3 remediation code based on the Phase 1 analysis
5. Return the generated code for execution

IMPORTANT:
- Save rollback data BEFORE generating the remediation code
- The code should be self-contained and executable
- Include error handling in the generated code
"""

    logger.info(f"Running Remediator Agent for task {task_id}")

    try:
        result = agent(prompt)

        response_text = str(result.message) if hasattr(result, 'message') else str(result)

        logger.info(f"Remediator completed for task {task_id}")

        return {
            "success": True,
            "task_id": task_id,
            "resource_arn": resource_arn,
            "response": response_text
        }

    except Exception as e:
        logger.exception(f"Remediator failed for task {task_id}: {e}")
        return {
            "success": False,
            "task_id": task_id,
            "error": str(e)
        }


def execute_generated_code(code: str, task_id: str) -> dict:
    """执行生成的修复代码。

    通过 AgentCore Code Interpreter 在沙盒环境中执行代码。

    Args:
        code: 要执行的 Python 代码
        task_id: 任务 ID (用于日志)

    Returns:
        dict: 执行结果
    """
    import os

    try:
        # TODO: 使用 AgentCore Code Interpreter 执行
        # 当前实现为占位，需要根据实际 SDK 调整
        from bedrock_agentcore.tools import CodeInterpreterClient

        client = CodeInterpreterClient()

        result = client.execute(
            code=code,
            timeout=300,  # 5 minutes
            environment={
                "AWS_REGION": os.environ.get("AWS_REGION", "us-east-1")
            }
        )

        return {
            "success": result.exit_code == 0,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "execution_time_ms": result.execution_time_ms
        }

    except ImportError:
        logger.warning("Code Interpreter not available, using local execution")
        # Fallback: 本地执行 (仅用于开发测试)
        try:
            exec_globals = {}
            exec(code, exec_globals)
            return {
                "success": True,
                "message": "Executed locally (development mode)"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    except Exception as e:
        logger.exception(f"Code execution failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }
