"""
Analyzer Agent - Phase 1 分析智能体

负责分析 Security Hub Finding 并生成修复方案描述（不生成代码）。
"""
import logging
from typing import Optional

from strands import Agent
from strands.models import BedrockModel

from agents.config import get_config, ANALYZER_MODEL_CONFIG
from agents.tools.asr_playbook import fetch_asr_playbook
from agents.tools.memory_tools import (
    search_similar_findings,
    save_analysis_result,
    set_memory_session,
)
from agents.tools.aws_resources import (
    get_s3_bucket_info,
    get_security_group_rules,
    get_iam_role_info,
    get_rds_instance_info,
)

logger = logging.getLogger(__name__)

# Analyzer Agent System Prompt
ANALYZER_SYSTEM_PROMPT = """# Role
You are the Analyzer Agent for SHARA (Security Hub Auto-Remediation Agent).
Your job is to analyze AWS Security Hub findings and generate remediation descriptions.

# CRITICAL CONSTRAINTS
- You ONLY generate text descriptions, NOT executable code
- Code generation happens in Phase 2 after human approval
- Your output will be sent to administrators for approval via email

# Analysis Process
Follow these steps in order:

1. **Parse Finding**: Extract Control ID, resource information, and severity from ASFF format
2. **Fetch ASR Playbook**: Use fetch_asr_playbook tool to get predefined remediation approach
3. **Search Similar Experiences**: Use search_similar_findings tool to find past successful fixes from Memory LTM
4. **Gather Resource Context**: Use appropriate tools (get_s3_bucket_info, get_security_group_rules, etc.) to get current resource configuration
5. **Risk Assessment**: Evaluate actual risk considering:
   - Data sensitivity
   - Exposure level
   - Potential impact of remediation
   - Whether the operation is destructive
6. **Generate Description**: Create detailed remediation description in plain text (NO CODE)
7. **Save Results**: Use save_analysis_result tool to save analysis for Phase 2

# Output Format
You MUST return a JSON object with this structure:

{
  "analysis": {
    "control_id": "S3.1",
    "finding_type": "S3 Block Public Access disabled",
    "resource_type": "AwsS3Bucket",
    "resource_id": "arn:aws:s3:::my-bucket",
    "current_state": {
      "BlockPublicAcls": false,
      "IgnorePublicAcls": false,
      "BlockPublicPolicy": false,
      "RestrictPublicBuckets": false
    },
    "risk_assessment": {
      "level": "HIGH",
      "factors": ["Contains sensitive data", "Public exposure risk"],
      "justification": "Bucket contains configuration files that could expose credentials"
    }
  },
  "asr_match": {
    "matched": true,
    "playbook_id": "ASR_S3_1",
    "confidence": 0.95
  },
  "similar_experiences": [
    {
      "experience_id": "...",
      "relevance": 0.85
    }
  ],
  "remediation": {
    "summary": "Enable S3 Block Public Access",
    "description": "This remediation will configure bucket-level block public access settings to prevent any public access. The settings will block public ACLs, ignore existing public ACLs, block public bucket policies, and restrict public bucket access.",
    "steps": [
      "Step 1: Enable BlockPublicAcls - Prevents new public ACLs from being applied",
      "Step 2: Enable IgnorePublicAcls - Ignores any existing public ACLs",
      "Step 3: Enable BlockPublicPolicy - Prevents new public bucket policies",
      "Step 4: Enable RestrictPublicBuckets - Restricts public access via any policy"
    ],
    "estimated_impact": "LOW",
    "rollback_available": true,
    "is_destructive": false
  }
}

# Important Guidelines
- ALWAYS try to match ASR playbook first - these are tested remediation approaches
- Include ALL risk assessment factors
- Provide clear, step-by-step description that non-technical administrators can understand
- Mark if the operation is destructive (could cause data loss)
- NEVER include actual code in your response - only descriptions
- Save your analysis using save_analysis_result before finishing
"""


def create_analyzer_agent(
    task_id: str,
    memory_id: str,
    region: Optional[str] = None
) -> Agent:
    """创建 Analyzer Agent 实例。

    Args:
        task_id: 任务 ID
        memory_id: AgentCore Memory ID
        region: AWS Region (可选，默认从环境变量获取)

    Returns:
        Agent: 配置好的 Analyzer Agent
    """
    config = get_config()
    region = region or config.region

    # 配置 Memory Session Manager
    try:
        from bedrock_agentcore.memory.integrations.strands import (
            AgentCoreMemorySessionManager,
            AgentCoreMemoryConfig,
            RetrievalConfig,
        )

        memory_config = AgentCoreMemoryConfig(
            memory_id=memory_id,
            actor_id=f"task-{task_id}",
            session_id=f"session-task-{task_id}",
            retrieval_config={
                # 搜索相似修复经验
                "remediation/{controlId}": RetrievalConfig(
                    top_k=5,
                    relevance_score=0.5
                )
            }
        )

        session_manager = AgentCoreMemorySessionManager(
            agentcore_memory_config=memory_config,
            region_name=region
        )

        # 设置全局 memory session 供工具使用
        set_memory_session(session_manager.get_session())

        logger.info(f"Initialized Memory session for task {task_id}")

    except ImportError:
        logger.warning("AgentCore Memory SDK not available, running without memory")
        session_manager = None
    except Exception as e:
        logger.warning(f"Failed to initialize Memory session: {e}")
        session_manager = None

    # 配置 LLM
    model = BedrockModel(
        model_id=ANALYZER_MODEL_CONFIG.model_id,
        temperature=ANALYZER_MODEL_CONFIG.temperature,
        max_tokens=ANALYZER_MODEL_CONFIG.max_tokens,
        top_p=ANALYZER_MODEL_CONFIG.top_p,
        region_name=region
    )

    # 创建 Agent
    agent = Agent(
        model=model,
        system_prompt=ANALYZER_SYSTEM_PROMPT,
        tools=[
            fetch_asr_playbook,
            search_similar_findings,
            save_analysis_result,
            get_s3_bucket_info,
            get_security_group_rules,
            get_iam_role_info,
            get_rds_instance_info,
        ],
        session_manager=session_manager,
    )

    logger.info(f"Created Analyzer Agent for task {task_id}")
    return agent


def run_analyzer(
    agent: Agent,
    finding: dict,
    control_id: str,
    task_id: str
) -> dict:
    """运行 Analyzer Agent 分析 Finding。

    Args:
        agent: Analyzer Agent 实例
        finding: Security Hub Finding (ASFF 格式)
        control_id: Control ID
        task_id: 任务 ID

    Returns:
        dict: 分析结果
    """
    import json

    prompt = f"""
Analyze this Security Hub Finding and generate a remediation description:

**Task ID:** {task_id}
**Control ID:** {control_id}

**Finding (ASFF Format):**
```json
{json.dumps(finding, indent=2, default=str)}
```

**Instructions:**
1. First, fetch the ASR playbook for Control ID: {control_id}
2. Search for similar past experiences in Memory LTM
3. Get current resource configuration using the appropriate tool
4. Assess the risk level
5. Generate a detailed remediation description (NO CODE)
6. Save the analysis result using save_analysis_result tool

Remember: Generate DESCRIPTIONS only, not executable code. Code will be generated in Phase 2 after approval.
"""

    logger.info(f"Running Analyzer Agent for task {task_id}, control {control_id}")

    try:
        result = agent(prompt)

        # 解析结果
        response_text = str(result.message) if hasattr(result, 'message') else str(result)

        logger.info(f"Analyzer completed for task {task_id}")

        return {
            "success": True,
            "task_id": task_id,
            "response": response_text
        }

    except Exception as e:
        logger.exception(f"Analyzer failed for task {task_id}: {e}")
        return {
            "success": False,
            "task_id": task_id,
            "error": str(e)
        }
