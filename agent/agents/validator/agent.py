"""
Validator Agent - Phase 2 验证智能体

负责验证修复效果、更新 Security Hub Finding 状态、保存修复经验。
"""
import logging
from typing import Optional

from strands import Agent
from strands.models import BedrockModel

from agents.config import get_config, VALIDATOR_MODEL_CONFIG
from agents.tools.security_hub import update_security_hub_finding, verify_resource_state
from agents.tools.memory_tools import save_experience_to_ltm, set_memory_session
from agents.tools.execution import save_task_event
from agents.tools.aws_resources import (
    get_s3_bucket_info,
    get_security_group_rules,
    get_iam_role_info,
)

logger = logging.getLogger(__name__)

# Validator Agent System Prompt
VALIDATOR_SYSTEM_PROMPT = """# Role
You are the Validator Agent for SHARA (Security Hub Auto-Remediation Agent).
Your job is to verify remediation results and save successful experiences to long-term memory.

# Validation Process
Follow these steps in order:

1. **Verify Resource State**: Use verify_resource_state tool to check if the resource now matches the expected secure configuration
2. **Cross-Check with Current Config**: Use appropriate tools (get_s3_bucket_info, etc.) to get current resource state and compare
3. **Update Security Hub**: If validation passes, use update_security_hub_finding tool to set finding status to RESOLVED
4. **Save Experience**: If validation passes, use save_experience_to_ltm tool to save this remediation experience for future reference

# Validation Criteria
For each resource type, verify the following:

## S3 Bucket (AwsS3Bucket)
- BlockPublicAcls: true
- IgnorePublicAcls: true
- BlockPublicPolicy: true
- RestrictPublicBuckets: true

## Security Group (AwsEc2SecurityGroup)
- No 0.0.0.0/0 CIDR in inbound rules (except for necessary ports like 443)
- Properly restricted source IP ranges

## IAM Role (AwsIamRole)
- No wildcard (*) principals in trust policy
- Properly scoped permissions

# Output Format
Return a JSON object with this structure:

{
  "validation": {
    "passed": true,
    "checks": [
      {
        "name": "BlockPublicAcls",
        "expected": true,
        "actual": true,
        "passed": true
      },
      {
        "name": "IgnorePublicAcls",
        "expected": true,
        "actual": true,
        "passed": true
      }
    ],
    "summary": "All 4 checks passed"
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
  }
}

# Important Guidelines
- Only save experience if ALL validation checks pass
- Include detailed check results for each validation criterion
- Update Security Hub with appropriate workflow status
- If validation fails, report which checks failed and why
- Do NOT update Security Hub to RESOLVED if validation fails
"""


def create_validator_agent(
    task_id: str,
    memory_session_id: str,
    memory_id: str,
    region: Optional[str] = None
) -> Agent:
    """创建 Validator Agent 实例。

    Args:
        task_id: 任务 ID
        memory_session_id: Memory Session ID
        memory_id: AgentCore Memory ID
        region: AWS Region (可选)

    Returns:
        Agent: 配置好的 Validator Agent
    """
    config = get_config()
    region = region or config.region

    # 连接到 Memory Session
    try:
        from bedrock_agentcore.memory.integrations.strands import (
            AgentCoreMemorySessionManager,
            AgentCoreMemoryConfig,
        )

        memory_config = AgentCoreMemoryConfig(
            memory_id=memory_id,
            actor_id=f"task-{task_id}",
            session_id=memory_session_id
        )

        session_manager = AgentCoreMemorySessionManager(
            agentcore_memory_config=memory_config,
            region_name=region
        )

        set_memory_session(session_manager.get_session())

        logger.info(f"Connected to Memory session for Validator task {task_id}")

    except ImportError:
        logger.warning("AgentCore Memory SDK not available")
        session_manager = None
    except Exception as e:
        logger.warning(f"Failed to connect to Memory session: {e}")
        session_manager = None

    # 配置 LLM
    model = BedrockModel(
        model_id=VALIDATOR_MODEL_CONFIG.model_id,
        temperature=VALIDATOR_MODEL_CONFIG.temperature,
        max_tokens=VALIDATOR_MODEL_CONFIG.max_tokens,
        top_p=VALIDATOR_MODEL_CONFIG.top_p,
        region_name=region
    )

    # 创建 Agent
    agent = Agent(
        model=model,
        system_prompt=VALIDATOR_SYSTEM_PROMPT,
        tools=[
            verify_resource_state,
            update_security_hub_finding,
            save_experience_to_ltm,
            save_task_event,
            get_s3_bucket_info,
            get_security_group_rules,
            get_iam_role_info,
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
    remediation_info: dict
) -> dict:
    """运行 Validator Agent 验证修复结果。

    Args:
        agent: Validator Agent 实例
        task_id: 任务 ID
        finding_id: Security Hub Finding ID
        resource_arn: 资源 ARN
        resource_type: 资源类型
        control_id: Control ID
        remediation_info: 修复信息 (来自 Phase 1 分析)

    Returns:
        dict: 验证结果
    """
    import json

    # 根据资源类型确定预期状态
    expected_state = _get_expected_state(resource_type, control_id)

    prompt = f"""
Validate the remediation for task {task_id}:

**Finding ID:** {finding_id}
**Control ID:** {control_id}
**Resource ARN:** {resource_arn}
**Resource Type:** {resource_type}

**Expected State After Remediation:**
```json
{json.dumps(expected_state, indent=2)}
```

**Remediation Info:**
```json
{json.dumps(remediation_info, indent=2, default=str)}
```

**Instructions:**
1. Use verify_resource_state tool to check if the resource matches the expected state
2. Also use the appropriate resource info tool (get_s3_bucket_info, etc.) to cross-verify
3. If ALL checks pass:
   - Use update_security_hub_finding tool to set status to RESOLVED
   - Use save_experience_to_ltm tool to save this experience
4. If any check fails:
   - Report which checks failed
   - Do NOT update Security Hub to RESOLVED
   - Do NOT save experience

Return the validation results in the specified JSON format.
"""

    logger.info(f"Running Validator Agent for task {task_id}")

    try:
        result = agent(prompt)

        response_text = str(result.message) if hasattr(result, 'message') else str(result)

        logger.info(f"Validator completed for task {task_id}")

        return {
            "success": True,
            "task_id": task_id,
            "finding_id": finding_id,
            "response": response_text
        }

    except Exception as e:
        logger.exception(f"Validator failed for task {task_id}: {e}")
        return {
            "success": False,
            "task_id": task_id,
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
