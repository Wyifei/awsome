#!/usr/bin/env python3
"""
SHARA Memory 资源创建脚本

创建 AgentCore Memory 资源，配置：
- STM (Short-Term Memory): 用于三个智能体在同一任务中共享信息
- LTM (Long-Term Memory): 使用 Episodic 策略存储修复经验

使用 Built-in Strategy with Override 模式，自定义 Extraction/Consolidation/Reflection prompts
"""
import argparse
import json
import logging
import os
import sys
import time
from typing import Optional

import boto3
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# Configuration
# ============================================================================

DEFAULT_REGION = "ap-northeast-1"
DEFAULT_MEMORY_NAME = "shara_remediation_memory"
DEFAULT_EVENT_EXPIRY_DAYS = 30

# Model for extraction/consolidation/reflection
# 不同区域可能需要使用不同的模型 ID 或 inference profile
# us-east-1: 使用基础模型 ID
# ap-northeast-1: 使用 APAC inference profile
REGION_MODEL_MAP = {
    "us-east-1": "anthropic.claude-3-sonnet-20240229-v1:0",
    "us-west-2": "anthropic.claude-3-sonnet-20240229-v1:0",
    "ap-northeast-1": "apac.anthropic.claude-3-sonnet-20240229-v1:0",
    "ap-southeast-1": "apac.anthropic.claude-3-sonnet-20240229-v1:0",
    "eu-west-1": "anthropic.claude-3-sonnet-20240229-v1:0",
}
DEFAULT_MODEL_ID = "anthropic.claude-3-sonnet-20240229-v1:0"

# Namespace 设计
# 重要：使用 actor 级别而非 session 级别存储 Episodes
# 这样同一 actor (AWS 账户) 的所有修复经验可以跨 session 检索
#
# 原配置 (存在问题):
#   Episodes: /remediation/actors/{actorId}/sessions/{sessionId}/
#   问题: 每个 session 的经验被隔离，无法跨 session 检索
#
# 新配置 (推荐):
#   Episodes: /remediation/actors/{actorId}/
#   好处: 同一 actor 的所有 session 的 episodes 存储在同一 namespace，可共享检索
#
# 参考 AWS 文档:
# https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/episodic-memory-strategy.html
# "Store all episodes at the actor level. Episodes that come from different sessions,
#  but that belong to the same actor, are stored in the same namespace."
EPISODE_NAMESPACES = ["/remediation/actors/{actorId}/"]
REFLECTION_NAMESPACES = ["/remediation/actors/{actorId}/"]

# ============================================================================
# Custom Prompts for SHARA Security Remediation
# ============================================================================
#
# SHARA (Security Hub Auto-Remediation Agent) 系统架构:
#
# 1. 工作流程 (两阶段):
#    Phase 1 (分析): Security Hub Finding → Analyzer Agent → 审批邮件 → 人工审批
#    Phase 2 (执行): 审批通过 → Remediator Agent → Validator Agent → 结果邮件
#
# 2. 三个 Agent 的职责:
#    - Analyzer: 分析 Finding，匹配 ASR Playbook，生成修复方案描述，评估风险
#    - Remediator: 生成 boto3 修复代码，保存回滚数据，执行修复
#    - Validator: 代码安全审查，验证修复结果，更新 Security Hub 状态
#
# 3. Memory 用途:
#    - STM: 同一任务中三个 Agent 共享信息 (分析结果、回滚数据、执行结果)
#    - LTM: 跨任务存储修复经验，供 Analyzer 在新任务中检索相似经验
#
# 4. 关键数据结构:
#    - Control ID: Security Hub 控制 ID (如 S3.1, EC2.19, IAM.4)
#    - Resource Type: AWS 资源类型 (如 AwsS3Bucket, AwsEc2SecurityGroup)
#    - ASR Playbook: 预定义的自动化修复方案
#    - Finding: ASFF 格式的安全发现
#
# ============================================================================

EXTRACTION_APPEND_PROMPT = """
## SHARA Security Remediation Episode Extraction

You are extracting security remediation episodes from SHARA agent conversations. SHARA is a Security Hub Auto-Remediation Agent system with three agents working in two phases.

### System Context

**Phase 1 (Analysis):**
- Analyzer Agent receives Security Hub Finding
- Matches ASR (Automated Security Response) Playbook
- Searches LTM for similar past experiences
- Generates remediation description (no code)
- Sends approval email to administrator

**Phase 2 (Execution - after human approval):**
- Remediator Agent generates boto3 remediation code
- Saves rollback data (pre_state + rollback_code) to Memory
- Executes remediation code via Code Interpreter
- Validator Agent reviews code security
- Validator verifies remediation success
- Validator updates Security Hub finding status

### Episode Detection

An episode is COMPLETE when you observe:
1. A Security Hub Finding was processed (has Control ID and resource info)
2. Analysis was performed (risk assessment, ASR matching)
3. Remediation was attempted (code generated and executed)
4. Validation occurred (success/failure determined)

Mark episode as INCOMPLETE if:
- Only Phase 1 analysis exists (waiting for approval)
- Execution started but no validation result yet
- Conversation ends abruptly without clear outcome

### Episodic Structure to Extract

**Scenario (What happened):**
- Control ID (e.g., S3.1, EC2.19, SNS.1)
- Resource Type (e.g., AwsS3Bucket, AwsEc2SecurityGroup)
- Resource ARN
- Finding severity and title
- Current resource state before remediation

**Intent (What was the goal):**
- Specific compliance requirement being addressed
- Expected resource state after remediation
- ASR Playbook matched (if any)

**Actions (What was done):**
- Remediation approach description
- AWS APIs called (boto3 methods)
- Key code patterns used
- Rollback data saved (yes/no)
- Pre-checks performed

**Outcomes (What was the result):**
- Execution result (success/failure)
- Validation result (RESOLVED/FAILED)
- Security Hub status update
- Error messages (if failed)
- Rollback triggered (if any)

### Extraction Priority

HIGH PRIORITY (always extract):
- Control ID and resource type combination
- Successful remediation code patterns
- Error messages and how they were resolved
- Timing/propagation delay insights

MEDIUM PRIORITY:
- ASR Playbook effectiveness
- Pre-check recommendations
- Resource dependency discoveries

LOW PRIORITY:
- Routine successful remediations with no new insights
- Duplicate Control ID patterns already well-documented

### Key Identifiers to Preserve

Always preserve exact values for:
- Control IDs: S3.1, EC2.19, IAM.4, RDS.2, etc.
- Resource ARNs: arn:aws:s3:::bucket-name, etc.
- boto3 API calls: put_public_access_block, revoke_security_group_ingress, etc.
- Error codes: AccessDenied, InvalidParameterValue, etc.
"""

CONSOLIDATION_APPEND_PROMPT = """
## SHARA Security Remediation Knowledge Consolidation

You are consolidating security remediation episodes into a knowledge base for SHARA agents. This knowledge helps Analyzer Agent provide better recommendations and helps Remediator Agent generate more reliable code.

### Knowledge Base Purpose

The consolidated knowledge is used by:
1. **Analyzer Agent**: Searches LTM when analyzing new findings to find similar past experiences
2. **Remediator Agent**: References successful code patterns for similar Control IDs
3. **Validator Agent**: Knows common failure modes to watch for

### Consolidation Decision Matrix

#### AddMemory - New Knowledge

**Add when discovering:**
- First successful remediation for a Control ID
- New resource type variant (e.g., S3.1 on bucket with versioning enabled)
- Novel error scenario with resolution
- Cross-region or cross-account specific handling
- New pre-check that improved success rate
- Timing insight (propagation delay discovered)

**Example - Add:**
```
Existing: (none for S3.8)
New Episode: S3.8 remediation for bucket with SSE-KMS encryption
Action: AddMemory - first pattern for this control
```

#### UpdateMemory - Enhance Existing

**Update when:**
- Adding complementary approach to existing Control ID
- Recording validation timing requirements
- Adding error handling for edge case
- Improving code pattern based on new success

**Example - Update:**
```
Existing: "S3.1: Use put_public_access_block to enable all four settings"
New Episode: "S3.1 failed when bucket has public policy, need to remove policy first"
Action: UpdateMemory - add prerequisite step
```

#### SkipMemory - No Action Needed

**Skip when:**
- Routine successful remediation matching existing pattern exactly
- Same Control ID + resource type with no new insights
- Failed remediation due to transient issue (timeout, throttling)

### Knowledge Quality Guidelines

**Preserve:**
- Complete boto3 code snippets that work
- Exact API parameter combinations
- Error message → resolution mappings
- Validation wait times

**Summarize:**
- Verbose log output
- Repeated status checks
- Standard success confirmations

**Never Discard:**
- Failed remediation root causes
- Rollback scenarios and triggers
- Resource dependency requirements
- Security implications noted

### Service Family Grouping

Group related Control IDs for pattern recognition:
- S3.*: Bucket security (S3.1-S3.20)
- EC2.*: Compute security (EC2.1-EC2.30)
- IAM.*: Identity security (IAM.1-IAM.25)
- RDS.*: Database security (RDS.1-RDS.25)
- Lambda.*: Serverless security
- EKS/ECS.*: Container security

### Index Keywords

Ensure these are prominently included for search retrieval:
- Control ID (exact match needed)
- Resource Type (for type-specific code)
- "remediation", "fix", "resolve" (for intent matching)
- AWS service name (S3, EC2, IAM, etc.)
"""

REFLECTION_APPEND_PROMPT = """
## SHARA Security Remediation Cross-Episode Reflection

Analyze multiple remediation episodes to extract high-level insights that improve SHARA system performance. Reflections help agents make better decisions by learning from accumulated experience.

### Reflection Purpose

Reflections are retrieved when:
1. Analyzer encounters a new finding and wants strategic guidance
2. Remediator needs to choose between multiple approaches
3. Validator assesses risk level of a remediation

### Analysis Dimensions

#### 1. Control ID Success Patterns

For each AWS service family, identify:
- Which Control IDs have highest success rate?
- Which require special handling?
- Common failure modes by Control ID?

**Output Format:**
```
Service: S3
High Success: S3.1, S3.2, S3.5 (95%+ success with standard approach)
Moderate: S3.8, S3.9 (may need KMS key handling)
Complex: S3.11 (requires lifecycle policy changes)
```

#### 2. Resource Type Patterns

Identify resource-specific considerations:
- AwsS3Bucket: Check for public policies before modifying access blocks
- AwsEc2SecurityGroup: Verify no dependent ENIs before rule changes
- AwsIamRole: Consider trust policy implications
- AwsRdsDbInstance: Account for maintenance windows

#### 3. Code Pattern Reliability

Rank remediation code patterns:
- Which boto3 API sequences are most reliable?
- Which parameter combinations work best?
- When is waiter pattern needed vs. simple polling?

**Example:**
```
Pattern: put_public_access_block with all four settings = True
Reliability: HIGH (98% success across 50+ remediations)
Note: Always verify bucket exists first, handle NoSuchBucket gracefully
```

#### 4. Failure Mode Catalog

Document common failures and resolutions:
```
Failure: AccessDenied on put_public_access_block
Cause: Bucket has conflicting bucket policy with public read
Resolution: Remove s3:GetObject Allow for * principal first
Prevention: Pre-check bucket policy for public statements
```

#### 5. Timing Insights

Document propagation and consistency delays:
- S3 Block Public Access: 10-30 seconds before validation
- Security Group rules: 15-60 seconds for ENI propagation
- IAM policy changes: Up to 60 seconds for global propagation
- RDS parameter groups: May require instance restart

#### 6. Rollback Patterns

Identify when rollbacks are needed:
- High rollback rate Control IDs
- Common rollback triggers
- Successful rollback approaches

### Reflection Output Guidelines

**Be Actionable:**
- "For S3.1, always check bucket policy for public access statements before applying Block Public Access"
- NOT: "S3.1 can sometimes fail"

**Be Specific:**
- "Wait 30 seconds after put_public_access_block before validation"
- NOT: "Some operations need time to propagate"

**Be Quantified:**
- "EC2.19 has 15% failure rate when security group has more than 50 rules"
- NOT: "Large security groups may have issues"

### Cross-Episode Pattern Recognition

Look for patterns across episodes:
1. Same Control ID, different resource states → variant handling
2. Same error, different Control IDs → common root cause
3. Same resource type, different controls → shared prerequisites
4. Sequential failures → systemic issues

### Strategic Recommendations

Generate recommendations for system improvement:
- ASR Playbook updates needed
- New pre-checks to add
- Validation timing adjustments
- Risk level reclassifications

**Example Reflection Output:**
```
## S3 Service Family Insights

### Success Pattern
S3.1/S3.2/S3.3 Block Public Access findings resolve reliably with:
1. Pre-check: get_public_access_block (handle NoSuchPublicAccessBlockConfiguration)
2. Pre-check: get_bucket_policy (identify public statements)
3. If public policy exists: delete_bucket_policy or modify to remove public access
4. Apply: put_public_access_block with all four settings True
5. Validate: Wait 20 seconds, then get_public_access_block to confirm

### Failure Pattern
When bucket has Object Lock enabled, Block Public Access may fail.
Resolution: Use get_object_lock_configuration first, adjust approach if enabled.

### Timing Insight
S3 Block Public Access changes are eventually consistent.
Recommended validation delay: 20-30 seconds.
Retry validation up to 3 times with 10-second intervals.
```
"""

# ============================================================================
# IAM Role Management
# ============================================================================

MEMORY_EXECUTION_ROLE_NAME = "shara-memory-execution-role"

MEMORY_EXECUTION_ROLE_TRUST_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "",
            "Effect": "Allow",
            "Principal": {
                "Service": [
                    "bedrock-agentcore.amazonaws.com"
                ]
            },
            "Action": "sts:AssumeRole",
            "Condition": {
                "StringEquals": {
                    "aws:SourceAccount": "${AWS_ACCOUNT_ID}"
                },
                "ArnLike": {
                    "aws:SourceArn": "arn:aws:bedrock-agentcore:${AWS_REGION}:${AWS_ACCOUNT_ID}:*"
                }
            }
        }
    ]
}

MEMORY_EXECUTION_ROLE_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "BedrockInvokeModel",
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream"
            ],
            "Resource": [
                "arn:aws:bedrock:*::foundation-model/*",
                "arn:aws:bedrock:*:*:inference-profile/*"
            ],
            "Condition": {
                "StringEquals": {
                    "aws:ResourceAccount": "${AWS_ACCOUNT_ID}"
                }
            }
        }
    ]
}


def get_or_create_execution_role(region: str) -> str:
    """获取或创建 Memory Execution Role。

    Args:
        region: AWS Region

    Returns:
        str: Role ARN
    """
    iam = boto3.client('iam', region_name=region)
    sts = boto3.client('sts', region_name=region)

    account_id = sts.get_caller_identity()['Account']
    role_arn = f"arn:aws:iam::{account_id}:role/{MEMORY_EXECUTION_ROLE_NAME}"

    # Check if role exists
    try:
        response = iam.get_role(RoleName=MEMORY_EXECUTION_ROLE_NAME)
        logger.info(f"Using existing IAM role: {role_arn}")

        # 更新信任策略以确保包含当前 region
        # 因为用户可能在不同 region 创建 memory
        trust_policy = json.loads(
            json.dumps(MEMORY_EXECUTION_ROLE_TRUST_POLICY)
            .replace("${AWS_ACCOUNT_ID}", account_id)
            .replace("${AWS_REGION}", "*")  # 使用通配符支持所有 region
        )

        try:
            iam.update_assume_role_policy(
                RoleName=MEMORY_EXECUTION_ROLE_NAME,
                PolicyDocument=json.dumps(trust_policy)
            )
            logger.info("Updated trust policy for existing role")
        except Exception as e:
            logger.warning(f"Could not update trust policy: {e}")

        return response['Role']['Arn']
    except iam.exceptions.NoSuchEntityException:
        pass

    logger.info(f"Creating IAM role: {MEMORY_EXECUTION_ROLE_NAME}")

    # Update trust policy with account ID and region (use wildcard for region)
    trust_policy = json.loads(
        json.dumps(MEMORY_EXECUTION_ROLE_TRUST_POLICY)
        .replace("${AWS_ACCOUNT_ID}", account_id)
        .replace("${AWS_REGION}", "*")  # 使用通配符支持所有 region
    )

    # Update permissions policy with account ID
    permissions_policy = json.loads(
        json.dumps(MEMORY_EXECUTION_ROLE_POLICY)
        .replace("${AWS_ACCOUNT_ID}", account_id)
    )

    # Create role
    response = iam.create_role(
        RoleName=MEMORY_EXECUTION_ROLE_NAME,
        AssumeRolePolicyDocument=json.dumps(trust_policy),
        Description="Execution role for SHARA AgentCore Memory to invoke Bedrock models",
        Tags=[
            {"Key": "Project", "Value": "SHARA"},
            {"Key": "Purpose", "Value": "AgentCore Memory Execution"}
        ]
    )

    role_arn = response['Role']['Arn']

    # Attach inline policy
    iam.put_role_policy(
        RoleName=MEMORY_EXECUTION_ROLE_NAME,
        PolicyName="BedrockInvokeModelPolicy",
        PolicyDocument=json.dumps(permissions_policy)
    )

    logger.info(f"Created IAM role: {role_arn}")

    # Wait for role to propagate
    logger.info("Waiting for IAM role to propagate...")
    time.sleep(10)

    return role_arn


# ============================================================================
# Memory Creation
# ============================================================================

def get_model_id_for_region(region: str, override_model_id: str = None) -> str:
    """获取指定区域的模型 ID。

    Args:
        region: AWS Region
        override_model_id: 用户指定的模型 ID (如果提供则使用此值)

    Returns:
        str: 模型 ID
    """
    if override_model_id:
        return override_model_id
    return REGION_MODEL_MAP.get(region, DEFAULT_MODEL_ID)


def create_shara_memory(
    region: str,
    memory_name: str = DEFAULT_MEMORY_NAME,
    event_expiry_days: int = DEFAULT_EVENT_EXPIRY_DAYS,
    model_id: str = None,  # None = 自动选择
    dry_run: bool = False
) -> Optional[dict]:
    """创建 SHARA Memory 资源。

    使用 Episodic Strategy with Override 配置自定义 prompts。

    Args:
        region: AWS Region
        memory_name: Memory 名称
        event_expiry_days: 事件过期天数 (STM)
        model_id: 用于 extraction/consolidation/reflection 的模型 (None = 自动根据区域选择)
        dry_run: 仅打印配置，不实际创建

    Returns:
        dict: 创建的 Memory 信息
    """
    # 自动选择区域对应的模型
    actual_model_id = get_model_id_for_region(region, model_id)

    # Get or create execution role
    execution_role_arn = get_or_create_execution_role(region)

    # Build memory strategy configuration
    memory_strategies = [
        {
            "customMemoryStrategy": {
                "name": "SecurityRemediationEpisodic",
                "description": "Episodic memory strategy for AWS Security Hub remediation experiences with custom prompts",
                "namespaces": EPISODE_NAMESPACES,
                "configuration": {
                    "episodicOverride": {
                        "extraction": {
                            "appendToPrompt": EXTRACTION_APPEND_PROMPT,
                            "modelId": actual_model_id
                        },
                        "consolidation": {
                            "appendToPrompt": CONSOLIDATION_APPEND_PROMPT,
                            "modelId": actual_model_id
                        },
                        "reflection": {
                            "appendToPrompt": REFLECTION_APPEND_PROMPT,
                            "modelId": actual_model_id,
                            "namespaces": REFLECTION_NAMESPACES
                        }
                    }
                }
            }
        }
    ]

    # Build request
    request = {
        "name": memory_name,
        "description": "SHARA Security Hub Auto-Remediation Agent Memory - Stores remediation experiences using Episodic strategy with custom prompts for security-specific extraction, consolidation, and reflection.",
        "eventExpiryDuration": event_expiry_days,
        "memoryExecutionRoleArn": execution_role_arn,
        "memoryStrategies": memory_strategies,
        "tags": {
            "Project": "SHARA",
            "Purpose": "SecurityRemediation",
            "StrategyType": "EpisodicOverride"
        }
    }

    if dry_run:
        logger.info("Dry run mode - printing configuration:")
        print(json.dumps(request, indent=2))
        return None

    # Create memory using boto3
    client = boto3.client('bedrock-agentcore-control', region_name=region)

    logger.info(f"Creating Memory resource: {memory_name}")
    logger.info(f"Region: {region}")
    logger.info(f"Event Expiry: {event_expiry_days} days")
    logger.info(f"Model ID: {actual_model_id}")
    logger.info(f"Execution Role: {execution_role_arn}")

    try:
        response = client.create_memory(**request)
        memory = response.get('memory', {})

        memory_id = memory.get('id')
        memory_arn = memory.get('arn')
        status = memory.get('status')

        logger.info(f"Memory creation initiated!")
        logger.info(f"  ID: {memory_id}")
        logger.info(f"  ARN: {memory_arn}")
        logger.info(f"  Status: {status}")

        # Wait for memory to be ready
        if status != 'ACTIVE':
            logger.info("Waiting for memory to become ACTIVE...")
            memory = wait_for_memory_active(client, memory_id)

        return memory

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']

        if error_code == 'ConflictException':
            logger.warning(f"Memory '{memory_name}' already exists. Fetching existing memory...")
            return get_memory_by_name(client, memory_name)
        else:
            logger.error(f"Failed to create memory: {error_code} - {error_message}")
            raise


def wait_for_memory_active(client, memory_id: str, timeout: int = 300) -> dict:
    """等待 Memory 变为 ACTIVE 状态。

    Args:
        client: boto3 client
        memory_id: Memory ID
        timeout: 超时时间（秒）

    Returns:
        dict: Memory 信息
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        response = client.get_memory(memoryId=memory_id)
        memory = response.get('memory', {})
        status = memory.get('status')

        if status == 'ACTIVE':
            logger.info("Memory is now ACTIVE!")
            return memory
        elif status == 'FAILED':
            failure_reason = memory.get('failureReason', 'Unknown')
            raise Exception(f"Memory creation failed: {failure_reason}")

        logger.info(f"Memory status: {status}, waiting...")
        time.sleep(10)

    raise Exception(f"Timeout waiting for memory to become ACTIVE")


def get_memory_by_name(client, memory_name: str) -> Optional[dict]:
    """通过名称获取 Memory。

    Args:
        client: boto3 client
        memory_name: Memory 名称

    Returns:
        dict: Memory 信息
    """
    try:
        response = client.list_memories()
        memories = response.get('memories', [])

        for mem in memories:
            if mem.get('name') == memory_name:
                # Get full details
                detail_response = client.get_memory(memoryId=mem['id'])
                return detail_response.get('memory', {})

        return None
    except Exception as e:
        logger.error(f"Failed to list memories: {e}")
        return None


def list_memories(region: str):
    """列出所有 Memory 资源。"""
    client = boto3.client('bedrock-agentcore-control', region_name=region)

    try:
        response = client.list_memories()
        memories = response.get('memories', [])

        if not memories:
            print("No memories found.")
            return

        print(f"\nFound {len(memories)} memory resource(s):\n")
        print("-" * 80)

        for mem in memories:
            print(f"Name: {mem.get('name')}")
            print(f"  ID: {mem.get('id')}")
            print(f"  ARN: {mem.get('arn')}")
            print(f"  Status: {mem.get('status')}")
            print(f"  Created: {mem.get('createdAt')}")
            print("-" * 80)

    except Exception as e:
        logger.error(f"Failed to list memories: {e}")
        sys.exit(1)


def get_memory_info(region: str, memory_id: str):
    """获取 Memory 详情。"""
    client = boto3.client('bedrock-agentcore-control', region_name=region)

    try:
        response = client.get_memory(memoryId=memory_id)
        memory = response.get('memory', {})

        print(f"\nMemory Details:")
        print("-" * 80)
        print(f"Name: {memory.get('name')}")
        print(f"ID: {memory.get('id')}")
        print(f"ARN: {memory.get('arn')}")
        print(f"Description: {memory.get('description')}")
        print(f"Status: {memory.get('status')}")
        print(f"Event Expiry: {memory.get('eventExpiryDuration')} days")
        print(f"Execution Role: {memory.get('memoryExecutionRoleArn')}")
        print(f"Created: {memory.get('createdAt')}")
        print(f"Updated: {memory.get('updatedAt')}")

        strategies = memory.get('strategies', [])
        if strategies:
            print(f"\nStrategies ({len(strategies)}):")
            for strat in strategies:
                print(f"  - Name: {strat.get('name')}")
                print(f"    ID: {strat.get('strategyId')}")
                print(f"    Type: {strat.get('type')}")
                print(f"    Status: {strat.get('status')}")
                print(f"    Namespaces: {strat.get('namespaces')}")

        print("-" * 80)

    except Exception as e:
        logger.error(f"Failed to get memory: {e}")
        sys.exit(1)


def delete_memory(region: str, memory_id: str, force: bool = False):
    """删除 Memory 资源。"""
    client = boto3.client('bedrock-agentcore-control', region_name=region)

    if not force:
        confirm = input(f"Are you sure you want to delete memory {memory_id}? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Cancelled.")
            return

    try:
        client.delete_memory(memoryId=memory_id)
        logger.info(f"Memory {memory_id} deleted successfully.")
    except Exception as e:
        logger.error(f"Failed to delete memory: {e}")
        sys.exit(1)


def print_env_config(memory: dict):
    """打印环境变量配置。"""
    memory_id = memory.get('id')
    memory_arn = memory.get('arn')

    print("\n" + "=" * 80)
    print("SHARA Memory 创建成功!")
    print("=" * 80)
    print("\n请将以下环境变量添加到你的配置中:\n")
    print(f"export AGENTCORE_MEMORY_ID={memory_id}")
    print(f"export AGENTCORE_MEMORY_ARN={memory_arn}")
    print("\n或者更新 agents/shared/config.py 中的默认值。")
    print("\n" + "=" * 80)

    # Print strategy info
    strategies = memory.get('strategies', [])
    if strategies:
        print("\nLTM Strategy 配置:")
        for strat in strategies:
            print(f"  - {strat.get('name')}: {strat.get('type')}")
            print(f"    Namespaces: {strat.get('namespaces')}")

    print("\n" + "=" * 80)


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="SHARA AgentCore Memory 资源管理",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 创建 Memory (使用默认配置)
  python create_shara_memory.py create

  # 创建 Memory (指定区域和名称)
  python create_shara_memory.py create --region us-east-1 --name my-shara-memory

  # 仅打印配置，不实际创建
  python create_shara_memory.py create --dry-run

  # 列出所有 Memory
  python create_shara_memory.py list --region ap-northeast-1

  # 获取 Memory 详情
  python create_shara_memory.py info --region ap-northeast-1 <memory_id>

  # 删除 Memory
  python create_shara_memory.py delete --region ap-northeast-1 <memory_id>
"""
    )

    subparsers = parser.add_subparsers(dest='command', help='命令')

    # Common argument for region (add to each subparser)
    region_kwargs = {
        'default': os.environ.get('AWS_REGION', DEFAULT_REGION),
        'help': f'AWS Region (default: {DEFAULT_REGION})'
    }

    # create command
    create_parser = subparsers.add_parser('create', help='创建 SHARA Memory 资源')
    create_parser.add_argument('--region', **region_kwargs)
    create_parser.add_argument(
        '--name',
        default=DEFAULT_MEMORY_NAME,
        help=f'Memory 名称 (default: {DEFAULT_MEMORY_NAME})'
    )
    create_parser.add_argument(
        '--expiry-days',
        type=int,
        default=DEFAULT_EVENT_EXPIRY_DAYS,
        help=f'STM 事件过期天数 (default: {DEFAULT_EVENT_EXPIRY_DAYS})'
    )
    create_parser.add_argument(
        '--model-id',
        default=None,
        help='LTM 处理模型 ID (默认: 根据区域自动选择, us-*使用基础模型, ap-*使用APAC inference profile)'
    )
    create_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='仅打印配置，不实际创建'
    )

    # list command
    list_parser = subparsers.add_parser('list', help='列出所有 Memory 资源')
    list_parser.add_argument('--region', **region_kwargs)

    # info command
    info_parser = subparsers.add_parser('info', help='获取 Memory 详情')
    info_parser.add_argument('--region', **region_kwargs)
    info_parser.add_argument('memory_id', help='Memory ID')

    # delete command
    delete_parser = subparsers.add_parser('delete', help='删除 Memory 资源')
    delete_parser.add_argument('--region', **region_kwargs)
    delete_parser.add_argument('memory_id', help='Memory ID')
    delete_parser.add_argument('--force', action='store_true', help='跳过确认')

    args = parser.parse_args()

    if args.command == 'create':
        memory = create_shara_memory(
            region=args.region,
            memory_name=args.name,
            event_expiry_days=args.expiry_days,
            model_id=args.model_id,
            dry_run=args.dry_run
        )
        if memory:
            print_env_config(memory)

    elif args.command == 'list':
        list_memories(args.region)

    elif args.command == 'info':
        get_memory_info(args.region, args.memory_id)

    elif args.command == 'delete':
        delete_memory(args.region, args.memory_id, args.force)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
