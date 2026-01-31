# Security Hub Auto-Remediation Agent 智能体设计文档

## 1. 概述

本文档详细描述 SHARA 系统中各智能体（Agent）的设计，包括职责、能力、工具集、Prompt 设计以及协作方式。**此文档是后续 Agent 开发的主要依据。**

---

## 2. 技术栈

### 2.1 框架选型

| 组件 | 技术选型 | 用途 |
|------|----------|------|
| Agent 框架 | Strands Agent SDK | Agent 开发、工具注册、对话管理 |
| 运行环境 | AgentCore Runtime | 安全隔离的生产执行环境 |
| 记忆服务 | AgentCore Memory | 短期记忆 (STM) + 长期记忆 (LTM) |
| 代码执行 | AgentCore Code Interpreter | 沙盒执行修复代码 |
| LLM | Amazon Bedrock (Claude) | 智能推理和代码生成 |

### 2.2 依赖安装

```bash
pip install strands-agents strands-agents-tools  # Strands SDK
pip install bedrock-agentcore                    # AgentCore SDK
```

### 2.3 核心类库

```python
# Strands Agent
from strands import Agent, tool
from strands.models import BedrockModel

# AgentCore Memory
from bedrock_agentcore.memory import MemorySessionManager
from bedrock_agentcore.memory.constants import ConversationalMessage, MessageRole

# AgentCore Memory + Strands 集成
from bedrock_agentcore.memory.integrations.strands import (
    AgentCoreMemorySessionManager,
    AgentCoreMemoryConfig,
    RetrievalConfig
)

# AgentCore Runtime
from bedrock_agentcore import BedrockAgentCoreApp
```

---

## 3. 两阶段架构

### 3.1 架构概览

SHARA 采用 **Lambda 调度 + Agent 执行** 的两阶段混合架构：

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              SHARA 两阶段架构                                     │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                     PHASE 1: 审批前 (分析阶段)                               │ │
│  │                                                                             │ │
│  │   EventBridge ──▶ Lambda (Event Handler) ──▶ Analyzer Agent                │ │
│  │                          │                        │                         │ │
│  │                          │                        ├─ 从 S3 获取 ASR Playbook │ │
│  │                          │                        ├─ 从 Memory LTM 搜索经验  │ │
│  │                          │                        ├─ 风险评估               │ │
│  │                          │                        └─ 生成修复描述 (无代码)   │ │
│  │                          │                                                  │ │
│  │                          ▼                                                  │ │
│  │                   发送审批邮件 (只包含描述，无代码)                           │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                             │
│                                    ▼ 管理员审批                                  │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                     PHASE 2: 审批后 (执行阶段)                               │ │
│  │                                                                             │ │
│  │   API Gateway ──▶ Lambda (Approval Handler) ──▶ Remediator Agent           │ │
│  │                                                      │                      │ │
│  │                                                      ├─ 从 Memory STM 获取  │ │
│  │                                                      │   Phase 1 上下文     │ │
│  │                                                      ├─ 生成修复代码        │ │
│  │                                                      └─ Code Interpreter    │ │
│  │                                                           执行代码          │ │
│  │                                                            │                │ │
│  │                                                            │                │ │
│  │                                                      (A2A Protocol)         │ │
│  │                                                            │                │ │
│  │                                                            ▼                │ │
│  │                                                    Validator Agent          │ │
│  │                                                      │                      │ │
│  │                                                      ├─ 审查代码安全性      │ │
│  │                                                      ├─ 验证执行结果        │ │
│  │                                                      ├─ 更新 Finding 状态   │ │
│  │                                                      ├─ 保存经验到 LTM      │ │
│  │                                                      └─ 触发结果邮件        │ │
│  │                                                            │                │ │
│  │                                                            ▼                │ │
│  │                                                   Lambda (Result Email)     │ │
│  │                                                   (含 Rollback 链接)        │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 组件职责

| 组件 | 阶段 | 职责 |
|------|------|------|
| **Event Handler Lambda** | Phase 1 | 接收 Finding、创建 Memory Session、调用 Analyzer、发送审批邮件 |
| **Analyzer Agent** | Phase 1 | 分析 Finding、ASR 匹配、Memory LTM 搜索、生成修复描述 |
| **Approval Handler Lambda** | Phase 2 | 处理审批、调用 Remediator |
| **Remediator Agent** | Phase 2 | 从 Memory 获取上下文、生成代码、执行修复、保存回滚数据、通过 A2A 调用 Validator |
| **Validator Agent** | Phase 2 | 审查代码安全、验证执行结果、更新 Security Hub、保存经验到 LTM、触发结果邮件 |
| **Feedback Handler Lambda** | Phase 2 | 处理回滚请求、调用 Remediator 执行回滚 |

### 3.3 数据流

| 阶段 | 输入 | Agent | 输出 |
|------|------|-------|------|
| Phase 1 | Security Hub Finding | Analyzer | 修复描述（文字） |
| Phase 2 | 审批通过 + Memory 上下文 | Remediator | 修复代码 + 执行结果 |
| Phase 2 | 执行结果 | Validator | 验证报告 + 经验 |

---

## 4. Memory 架构

### 4.1 Memory 用途

| 类型 | 用途 | 生命周期 |
|------|------|----------|
| **Session (STM)** | Phase 1 → Phase 2 上下文传递 | 任务周期 |
| **LTM** | 存储和检索修复经验 | 永久 |

### 4.2 Session (STM) 设计

每个任务创建一个独立的 Memory Session，用于跨阶段传递上下文：

```python
# Session ID 命名规则
session_id = f"session-task-{task_id}"

# Session 内容
{
    "phase1_analysis": {
        "finding_summary": "...",
        "control_id": "S3.1",
        "asr_playbook_matched": true,
        "risk_assessment": {...},
        "remediation_description": "..."
    },
    "phase2_execution": {
        "generated_code": "...",
        "execution_result": {...},
        "rollback_data": {...}
    }
}
```

### 4.3 LTM Namespace 设计

```
/remediation/
├── /remediation/{controlId}/           # 按 Control ID 分类
│   ├── /remediation/S3.1/user-123     # 用户验证的经验
│   └── /remediation/S3.1/user-456
└── /remediation/{resourceType}/        # 按资源类型分类
    ├── /remediation/AwsS3Bucket/...
    └── /remediation/AwsEc2SecurityGroup/...
```

### 4.4 Memory 操作流程

| 阶段 | Agent | 操作 | API |
|------|-------|------|-----|
| Phase 1 | Analyzer | 搜索相似经验 | `search_long_term_memories()` |
| Phase 1 | Analyzer | 保存分析结果 | `add_turns()` |
| Phase 2 | Remediator | 获取 Phase 1 结果 | `get_last_k_turns()` |
| Phase 2 | Remediator | 保存执行结果 | `add_turns()` |
| Phase 2 | Validator | 保存经验到 LTM | Memory LTM API |

---

## 5. Analyzer Agent (Phase 1)

### 5.1 职责

| 职责 | 描述 |
|------|------|
| Finding 解析 | 解析 ASFF 格式，提取 Control ID |
| ASR Playbook 匹配 | 从 S3 精确匹配 ASR 预置方案 |
| Memory LTM 搜索 | 语义搜索相似修复经验 |
| 资源上下文收集 | 获取资源当前配置 |
| 风险评估 | 评估 Finding 的实际风险 |
| **生成修复描述** | 生成文字描述（**不生成代码**） |

### 5.2 System Prompt

```markdown
# Role
You are the Analyzer Agent for SHARA (Security Hub Auto-Remediation Agent).
Your job is to analyze AWS Security Hub findings and generate remediation descriptions.

# IMPORTANT
- You ONLY generate text descriptions, NOT executable code
- Code generation happens in Phase 2 after human approval
- Your output will be sent to administrators for approval

# Analysis Process
1. **Parse Finding**: Extract Control ID and resource information from ASFF
2. **Fetch ASR Playbook**: Use fetch_asr_playbook tool to get predefined remediation approach
3. **Search Similar Experiences**: Use search_similar_findings tool to find past successful fixes
4. **Gather Context**: Query AWS APIs to get current resource configuration
5. **Risk Assessment**: Evaluate actual risk considering data sensitivity and exposure
6. **Generate Description**: Create detailed remediation description in plain text

# Output Format
{
  "analysis": {
    "control_id": "S3.1",
    "finding_type": "S3 Block Public Access disabled",
    "resource_type": "AwsS3Bucket",
    "resource_id": "arn:aws:s3:::my-bucket",
    "risk_assessment": {
      "level": "HIGH",
      "factors": ["Contains sensitive data", "Public exposure"],
      "justification": "..."
    }
  },
  "asr_match": {
    "matched": true,
    "playbook_id": "ASR_S3_1",
    "confidence": 0.95
  },
  "similar_experiences": [...],
  "remediation": {
    "summary": "Enable S3 Block Public Access",
    "description": "This remediation will configure bucket-level block public access settings...",
    "steps": [
      "Step 1: Enable BlockPublicAcls",
      "Step 2: Enable IgnorePublicAcls",
      "Step 3: Enable BlockPublicPolicy",
      "Step 4: Enable RestrictPublicBuckets"
    ],
    "estimated_impact": "LOW",
    "rollback_available": true,
    "is_destructive": false
  }
}

# Important Notes
- ALWAYS try to match ASR playbook first
- Include risk assessment factors
- Provide clear step-by-step description
- Mark if the operation is destructive
```

### 5.3 工具集

```python
from strands import tool
import boto3

# ============ ASR Playbook 工具 ============

@tool
def fetch_asr_playbook(control_id: str) -> dict:
    """从 S3 获取 ASR 预置修复方案。

    Args:
        control_id: Security Hub Control ID (如 S3.1, EC2.19)

    Returns:
        ASR Playbook 内容，包含修复方案和代码模板
    """
    s3 = boto3.client('s3')

    # 1. 读取索引文件
    index_obj = s3.get_object(
        Bucket=ASR_BUCKET,
        Key="index.json"
    )
    index = json.loads(index_obj['Body'].read())

    # 2. 查找匹配的 Control
    control_key = control_id.replace('.', '_')
    match = next(
        (c for c in index['controls'] if c['control_id'] == control_id),
        None
    )

    if not match:
        return {"matched": False, "control_id": control_id}

    # 3. 获取 Playbook 详情
    playbook_obj = s3.get_object(
        Bucket=ASR_BUCKET,
        Key=f"{match['path']}/{match['experience_id']}.json"
    )
    playbook = json.loads(playbook_obj['Body'].read())

    return {
        "matched": True,
        "playbook_id": match['experience_id'],
        "playbook": playbook,
        "is_destructive": match.get('is_destructive', False)
    }


@tool
def search_similar_findings(
    control_id: str,
    finding_title: str,
    resource_type: str,
    top_k: int = 5
) -> list:
    """从 Memory LTM 搜索相似的修复经验。

    Args:
        control_id: Security Hub Control ID
        finding_title: Finding 标题用于语义搜索
        resource_type: AWS 资源类型
        top_k: 返回的最大结果数

    Returns:
        相似修复经验列表
    """
    # 使用 AgentCore Memory 搜索
    query = f"Control: {control_id}, Finding: {finding_title}, Resource: {resource_type}"

    memories = memory_session.search_long_term_memories(
        query=query,
        namespace_prefix=f"/remediation/{control_id.replace('.', '_')}/",
        top_k=top_k
    )

    return memories


@tool
def save_analysis_result(
    task_id: str,
    analysis: dict,
    remediation_description: str
) -> dict:
    """保存分析结果到 Memory Session (供 Phase 2 使用)。

    Args:
        task_id: 任务 ID
        analysis: 分析结果
        remediation_description: 修复方案描述

    Returns:
        保存结果
    """
    from bedrock_agentcore.memory.constants import ConversationalMessage, MessageRole

    # 保存为对话记录
    memory_session.add_turns([
        ConversationalMessage(
            json.dumps({
                "type": "phase1_analysis",
                "task_id": task_id,
                "analysis": analysis,
                "remediation_description": remediation_description
            }),
            MessageRole.ASSISTANT
        )
    ])

    return {"success": True, "task_id": task_id}


# ============ 资源信息获取工具 ============

@tool
def get_s3_bucket_info(bucket_name: str) -> dict:
    """获取 S3 bucket 的完整配置信息。

    Args:
        bucket_name: S3 bucket 名称

    Returns:
        Bucket 配置信息
    """
    s3 = boto3.client('s3')

    info = {
        "bucket_name": bucket_name,
        "public_access_block": None,
        "bucket_policy": None,
        "bucket_acl": None,
        "encryption": None
    }

    try:
        info["public_access_block"] = s3.get_public_access_block(
            Bucket=bucket_name
        )["PublicAccessBlockConfiguration"]
    except s3.exceptions.NoSuchPublicAccessBlockConfiguration:
        info["public_access_block"] = None

    try:
        info["bucket_policy"] = s3.get_bucket_policy(Bucket=bucket_name)["Policy"]
    except s3.exceptions.NoSuchBucketPolicy:
        info["bucket_policy"] = None

    try:
        info["bucket_acl"] = s3.get_bucket_acl(Bucket=bucket_name)
    except Exception:
        pass

    try:
        info["encryption"] = s3.get_bucket_encryption(Bucket=bucket_name)
    except s3.exceptions.ServerSideEncryptionConfigurationNotFoundError:
        info["encryption"] = None

    return info


@tool
def get_security_group_rules(security_group_id: str) -> dict:
    """获取安全组规则详情。

    Args:
        security_group_id: 安全组 ID

    Returns:
        安全组规则信息
    """
    ec2 = boto3.client('ec2')

    response = ec2.describe_security_groups(
        GroupIds=[security_group_id]
    )

    if not response['SecurityGroups']:
        return {"error": "Security group not found"}

    sg = response['SecurityGroups'][0]
    return {
        "group_id": sg['GroupId'],
        "group_name": sg['GroupName'],
        "vpc_id": sg.get('VpcId'),
        "inbound_rules": sg['IpPermissions'],
        "outbound_rules": sg['IpPermissionsEgress'],
        "tags": sg.get('Tags', [])
    }


@tool
def get_iam_role_info(role_name: str) -> dict:
    """获取 IAM Role 详情。

    Args:
        role_name: IAM Role 名称

    Returns:
        Role 信息
    """
    iam = boto3.client('iam')

    role = iam.get_role(RoleName=role_name)['Role']

    # 获取内联策略
    inline_policies = iam.list_role_policies(RoleName=role_name)['PolicyNames']

    # 获取附加的托管策略
    attached_policies = iam.list_attached_role_policies(RoleName=role_name)['AttachedPolicies']

    return {
        "role_name": role['RoleName'],
        "role_arn": role['Arn'],
        "assume_role_policy": role['AssumeRolePolicyDocument'],
        "inline_policies": inline_policies,
        "attached_policies": attached_policies
    }
```

### 5.4 Agent 实例化

```python
from strands import Agent
from strands.models import BedrockModel
from bedrock_agentcore.memory.integrations.strands import (
    AgentCoreMemorySessionManager,
    AgentCoreMemoryConfig,
    RetrievalConfig
)

def create_analyzer_agent(task_id: str, memory_id: str) -> Agent:
    """创建 Analyzer Agent 实例"""

    # 配置 Memory
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
        region_name="us-east-1"
    )

    # 创建 Agent
    agent = Agent(
        model=BedrockModel(
            model_id="anthropic.claude-sonnet-4-20250514-v1:0",
            temperature=0.2,
            max_tokens=8192
        ),
        system_prompt=ANALYZER_SYSTEM_PROMPT,
        tools=[
            fetch_asr_playbook,
            search_similar_findings,
            save_analysis_result,
            get_s3_bucket_info,
            get_security_group_rules,
            get_iam_role_info,
        ],
        session_manager=session_manager
    )

    return agent
```

---

## 6. Remediator Agent (Phase 2)

### 6.1 职责

| 职责 | 描述 |
|------|------|
| **获取 Phase 1 上下文** | 从 Memory Session 读取分析结果 |
| **生成修复代码** | 基于分析结果生成 Python/Boto3 代码 |
| **保存回滚数据** | 执行前保存资源当前状态 |
| **执行修复** | 通过 Code Interpreter 执行代码 |
| **调用 Validator** | 通过 A2A 协议调用 Validator Agent 进行代码审查和结果验证 |
| **执行回滚** | 当用户点击回滚链接时执行回滚操作 |

### 6.2 System Prompt

```markdown
# Role
You are the Remediator Agent for SHARA. Your job is to generate and execute
remediation code based on the analysis from Phase 1, then invoke Validator Agent.

# IMPORTANT
- You operate AFTER human approval has been received
- Always retrieve Phase 1 analysis context first
- Always save rollback data before making changes
- Execute code through Code Interpreter for sandboxed execution
- After execution, call Validator Agent via A2A protocol

# Execution Process
1. **Get Phase 1 Context**: Use get_analysis_context tool to retrieve analysis results
2. **Save Rollback Data**: Save current resource state before any changes
3. **Generate Code**: Create Python/Boto3 remediation code
4. **Execute Code**: Use execute_code tool (Code Interpreter) to run the code
5. **Invoke Validator**: Use invoke_validator_agent tool to call Validator via A2A
   - Pass: generated code, execution result, task_id, resource info
   - Validator will: review code security, verify results, trigger result email
6. **Report Results**: Return execution status and Validator response

# Code Generation Guidelines
- Use boto3 for all AWS operations
- Include proper error handling
- Add comments explaining each step
- Make code idempotent when possible
- IMPORTANT: The generated code will be sent to Validator for security review

# Output Format
{
  "phase1_context_retrieved": true,
  "rollback_data_saved": true,
  "generated_code": {
    "language": "python",
    "code": "import boto3\n..."
  },
  "execution": {
    "status": "success|failed",
    "started_at": "...",
    "completed_at": "...",
    "output": {...},
    "error": null
  },
  "validator_response": {
    "code_review": "passed|warning|failed",
    "verification": "passed|failed",
    "email_sent": true
  }
}

# Important Notes
- NEVER execute without saving rollback data first
- Stop immediately on any error
- Log all actions for audit
- Always invoke Validator after execution (success or failure)
```

### 6.3 工具集

```python
from strands import tool
import boto3
import json

@tool
def get_analysis_context(task_id: str) -> dict:
    """从 Memory Session 获取 Phase 1 分析结果。

    Args:
        task_id: 任务 ID

    Returns:
        Phase 1 分析结果，包含修复描述和 ASR 匹配信息
    """
    # 获取最近的对话记录
    turns = memory_session.get_last_k_turns(k=10)

    # 查找 Phase 1 分析结果
    for turn in reversed(turns):
        content = turn.get('content', '')
        if isinstance(content, str) and 'phase1_analysis' in content:
            data = json.loads(content)
            if data.get('type') == 'phase1_analysis':
                return {
                    "success": True,
                    "analysis": data.get('analysis'),
                    "remediation_description": data.get('remediation_description')
                }

    return {"success": False, "error": "Phase 1 analysis not found"}


@tool
def save_rollback_data(
    task_id: str,
    resource_arn: str,
    resource_type: str,
    current_state: dict
) -> dict:
    """保存资源当前状态用于回滚。

    Args:
        task_id: 任务 ID
        resource_arn: 资源 ARN
        resource_type: 资源类型
        current_state: 当前资源配置状态

    Returns:
        保存结果
    """
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('shara-tasks')

    import time
    ttl = int(time.time()) + (30 * 24 * 60 * 60)  # 30 天

    table.put_item(Item={
        'PK': f'TASK#{task_id}',
        'SK': f'ROLLBACK#{resource_arn}',
        'task_id': task_id,
        'resource_arn': resource_arn,
        'resource_type': resource_type,
        'pre_state': current_state,
        'created_at': datetime.utcnow().isoformat(),
        'ttl': ttl
    })

    return {"success": True, "resource_arn": resource_arn}


@tool
def execute_code(code: str, timeout_seconds: int = 300) -> dict:
    """通过 Code Interpreter 执行 Python 代码。

    Args:
        code: 要执行的 Python 代码
        timeout_seconds: 执行超时时间

    Returns:
        执行结果，包含输出和错误信息
    """
    # 使用 AgentCore Code Interpreter
    from bedrock_agentcore.tools import CodeInterpreterClient

    client = CodeInterpreterClient()

    result = client.execute(
        code=code,
        timeout=timeout_seconds,
        environment={
            "AWS_REGION": os.environ.get("AWS_REGION", "us-east-1")
        }
    )

    return {
        "status": "success" if result.exit_code == 0 else "failed",
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "execution_time_ms": result.execution_time_ms
    }


@tool
def get_rollback_data(task_id: str, resource_arn: str) -> dict:
    """获取保存的回滚数据。

    Args:
        task_id: 任务 ID
        resource_arn: 资源 ARN

    Returns:
        回滚数据，包含资源修复前的状态
    """
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('shara-tasks')

    response = table.get_item(Key={
        'PK': f'TASK#{task_id}',
        'SK': f'ROLLBACK#{resource_arn}'
    })

    if 'Item' not in response:
        return {"success": False, "error": "Rollback data not found"}

    return {
        "success": True,
        "pre_state": response['Item']['pre_state'],
        "resource_type": response['Item']['resource_type']
    }


@tool
def execute_rollback(task_id: str, resource_arn: str) -> dict:
    """执行回滚操作，恢复资源到修复前状态。

    Args:
        task_id: 任务 ID
        resource_arn: 资源 ARN

    Returns:
        回滚执行结果
    """
    # 1. 获取回滚数据
    rollback_data = get_rollback_data(task_id, resource_arn)
    if not rollback_data.get('success'):
        return rollback_data

    pre_state = rollback_data['pre_state']
    resource_type = rollback_data['resource_type']

    # 2. 根据资源类型生成回滚代码
    if resource_type == 'AwsS3Bucket':
        bucket_name = resource_arn.split(':')[-1]
        rollback_code = f"""
import boto3
s3 = boto3.client('s3')
s3.put_public_access_block(
    Bucket='{bucket_name}',
    PublicAccessBlockConfiguration={json.dumps(pre_state.get('PublicAccessBlockConfiguration', {}))}
)
print("Rollback completed successfully")
"""
    else:
        return {"success": False, "error": f"Unsupported resource type: {resource_type}"}

    # 3. 执行回滚代码
    result = execute_code(rollback_code)

    return {
        "success": result['status'] == 'success',
        "rollback_result": result
    }


@tool
def invoke_validator_agent(
    task_id: str,
    resource_arn: str,
    resource_type: str,
    generated_code: str,
    execution_result: dict,
    is_rollback: bool = False
) -> dict:
    """通过 A2A 协议调用 Validator Agent。

    Args:
        task_id: 任务 ID
        resource_arn: 资源 ARN
        resource_type: 资源类型
        generated_code: 生成的修复代码
        execution_result: 代码执行结果
        is_rollback: 是否为回滚操作（回滚邮件不含 Rollback 链接）

    Returns:
        Validator Agent 的响应，包含代码审查结果、验证结果、邮件发送状态
    """
    import httpx
    import os

    validator_url = os.environ.get('VALIDATOR_RUNTIME_URL')
    if not validator_url:
        return {"success": False, "error": "VALIDATOR_RUNTIME_URL not configured"}

    # A2A JSON-RPC 2.0 请求
    a2a_request = {
        "jsonrpc": "2.0",
        "method": "tasks/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{
                    "type": "text",
                    "text": json.dumps({
                        "task_id": task_id,
                        "resource_arn": resource_arn,
                        "resource_type": resource_type,
                        "generated_code": generated_code,
                        "execution_result": execution_result,
                        "is_rollback": is_rollback
                    })
                }]
            }
        },
        "id": task_id
    }

    try:
        response = httpx.post(
            f"{validator_url}/a2a",
            json=a2a_request,
            timeout=300.0
        )
        response.raise_for_status()

        result = response.json()
        return {
            "success": True,
            "validator_response": result.get("result", {})
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"A2A call failed: {str(e)}"
        }
```

### 6.4 Agent 实例化

```python
def create_remediator_agent(task_id: str, memory_session_id: str) -> Agent:
    """创建 Remediator Agent 实例"""

    # 复用 Phase 1 创建的 Memory Session
    memory_config = AgentCoreMemoryConfig(
        memory_id=MEMORY_ID,
        actor_id=f"task-{task_id}",
        session_id=memory_session_id  # 使用同一个 Session
    )

    session_manager = AgentCoreMemorySessionManager(
        agentcore_memory_config=memory_config,
        region_name="us-east-1"
    )

    agent = Agent(
        model=BedrockModel(
            model_id="anthropic.claude-sonnet-4-20250514-v1:0",
            temperature=0.1,  # 低温度确保代码生成稳定
            max_tokens=8192
        ),
        system_prompt=REMEDIATOR_SYSTEM_PROMPT,
        tools=[
            get_analysis_context,
            save_rollback_data,
            execute_code,
            get_rollback_data,
            execute_rollback,
            invoke_validator_agent,  # A2A 调用 Validator
        ],
        session_manager=session_manager
    )

    return agent
```

---

## 7. Validator Agent (Phase 2)

### 7.1 职责

| 职责 | 描述 |
|------|------|
| **代码安全审查** | 检查 Remediator 生成的代码是否存在安全风险（危险操作、敏感信息泄露等） |
| **执行结果验证** | 检查资源状态是否符合预期 |
| **更新 Security Hub** | 将 Finding 状态更新为 RESOLVED |
| **保存修复经验** | 将验证通过的经验保存到 Memory LTM |
| **触发结果邮件** | 调用 Lambda 发送结果邮件（含 Rollback 链接，回滚邮件除外） |

### 7.1.1 触发方式

Validator Agent 通过 A2A 协议被 Remediator Agent 调用：

```
Remediator Agent ──(A2A Protocol)──▶ Validator Agent
                   传递:
                   - task_id
                   - generated_code
                   - execution_result
                   - resource_arn
                   - is_rollback (是否为回滚操作)
```

### 7.2 System Prompt

```markdown
# Role
You are the Validator Agent for SHARA. You are invoked via A2A protocol by Remediator Agent.
Your job is to:
1. Review generated code for security issues
2. Verify remediation results
3. Save successful experiences
4. Trigger result email to user

# IMPORTANT
- You are called by Remediator via A2A protocol
- You receive: task_id, generated_code, execution_result, resource_arn, is_rollback
- For rollback operations (is_rollback=true), result email should NOT contain Rollback link

# Validation Process
1. **Review Code Security**: Check generated code for security risks
   - Dangerous operations (delete, destroy, etc.)
   - Sensitive information leakage
   - Privilege escalation risks
   - Environment damage potential
2. **Verify Resource State**: Check if resource matches expected secure configuration
3. **Update Security Hub**: Set finding status to RESOLVED if validation passes
4. **Save Experience**: Save successful remediation to Memory LTM for future reference
5. **Trigger Result Email**: Call trigger_result_email tool to send email via Lambda
   - Include Rollback link for normal remediation
   - Do NOT include Rollback link for rollback operations

# Output Format
{
  "code_review": {
    "status": "passed|warning|rejected",
    "issues": [],
    "risk_level": "low|medium|high"
  },
  "validation": {
    "passed": true|false,
    "checks": [
      {
        "name": "PublicAccessBlocked",
        "expected": true,
        "actual": true,
        "passed": true
      }
    ]
  },
  "security_hub_update": {
    "updated": true,
    "new_status": "RESOLVED"
  },
  "experience_saved": {
    "saved": true,
    "namespace": "/remediation/S3.1/..."
  },
  "result_email": {
    "sent": true,
    "includes_rollback_link": true|false
  }
}

# Important Notes
- Review code BEFORE reporting validation results
- Only save experience if both code review and validation pass
- Include all validation check details
- Update Security Hub with appropriate workflow status
- For rollback operations: do NOT include Rollback link in email
- For rollback failures: alert user to handle manually
```

### 7.3 工具集

```python
from strands import tool
import boto3
import re


@tool
def review_code_security(code: str) -> dict:
    """审查生成的代码是否存在安全风险。

    Args:
        code: 要审查的 Python 代码

    Returns:
        审查结果，包含状态、问题列表、风险等级
    """
    issues = []
    risk_level = "low"

    # 危险操作检测
    dangerous_patterns = [
        (r'\.delete_', "检测到删除操作"),
        (r'\.terminate_', "检测到终止操作"),
        (r'\.destroy_', "检测到销毁操作"),
        (r'iam\.create_user', "检测到创建 IAM 用户"),
        (r'iam\.create_access_key', "检测到创建访问密钥"),
        (r'sts\.assume_role', "检测到角色切换"),
    ]

    for pattern, message in dangerous_patterns:
        if re.search(pattern, code, re.IGNORECASE):
            issues.append({"type": "dangerous_operation", "message": message})
            risk_level = "high"

    # 敏感信息泄露检测
    sensitive_patterns = [
        (r'password\s*=\s*["\'][^"\']+["\']', "代码中包含硬编码密码"),
        (r'secret\s*=\s*["\'][^"\']+["\']', "代码中包含硬编码密钥"),
        (r'AKIA[0-9A-Z]{16}', "代码中包含 AWS Access Key"),
    ]

    for pattern, message in sensitive_patterns:
        if re.search(pattern, code, re.IGNORECASE):
            issues.append({"type": "sensitive_info", "message": message})
            risk_level = "high"

    # 确定状态
    if risk_level == "high":
        status = "rejected"
    elif issues:
        status = "warning"
    else:
        status = "passed"

    return {
        "status": status,
        "issues": issues,
        "risk_level": risk_level
    }


@tool
def trigger_result_email(
    task_id: str,
    resource_arn: str,
    code_review_result: dict,
    validation_result: dict,
    is_rollback: bool = False
) -> dict:
    """触发 Lambda 发送结果邮件。

    Args:
        task_id: 任务 ID
        resource_arn: 资源 ARN
        code_review_result: 代码审查结果
        validation_result: 验证结果
        is_rollback: 是否为回滚操作（回滚邮件不含 Rollback 链接）

    Returns:
        邮件发送结果
    """
    import os

    lambda_client = boto3.client('lambda')

    # 构建邮件内容
    payload = {
        "task_id": task_id,
        "resource_arn": resource_arn,
        "code_review": code_review_result,
        "validation": validation_result,
        "is_rollback": is_rollback,
        "include_rollback_link": not is_rollback  # 回滚邮件不含 Rollback 链接
    }

    result_email_lambda = os.environ.get('RESULT_EMAIL_LAMBDA_ARN')
    if not result_email_lambda:
        return {"success": False, "error": "RESULT_EMAIL_LAMBDA_ARN not configured"}

    try:
        response = lambda_client.invoke(
            FunctionName=result_email_lambda,
            InvocationType='Event',  # 异步调用
            Payload=json.dumps(payload)
        )

        return {
            "success": True,
            "sent": True,
            "includes_rollback_link": not is_rollback
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to trigger email: {str(e)}"
        }


@tool
def verify_resource_state(
    resource_arn: str,
    resource_type: str,
    expected_state: dict
) -> dict:
    """验证资源当前状态是否符合预期。

    Args:
        resource_arn: 资源 ARN
        resource_type: 资源类型
        expected_state: 预期的资源状态

    Returns:
        验证结果
    """
    checks = []

    if resource_type == 'AwsS3Bucket':
        bucket_name = resource_arn.split(':')[-1]
        s3 = boto3.client('s3')

        try:
            actual = s3.get_public_access_block(Bucket=bucket_name)
            config = actual['PublicAccessBlockConfiguration']

            for key, expected_value in expected_state.items():
                actual_value = config.get(key)
                checks.append({
                    "name": key,
                    "expected": expected_value,
                    "actual": actual_value,
                    "passed": actual_value == expected_value
                })
        except Exception as e:
            checks.append({
                "name": "PublicAccessBlock",
                "expected": "configured",
                "actual": f"error: {str(e)}",
                "passed": False
            })

    all_passed = all(c['passed'] for c in checks)

    return {
        "passed": all_passed,
        "checks": checks
    }


@tool
def update_security_hub_finding(
    finding_id: str,
    workflow_status: str = "RESOLVED",
    note: str = None
) -> dict:
    """更新 Security Hub Finding 状态。

    Args:
        finding_id: Finding ID (ARN)
        workflow_status: 新状态 (RESOLVED, NOTIFIED, SUPPRESSED)
        note: 状态说明

    Returns:
        更新结果
    """
    securityhub = boto3.client('securityhub')

    update = {
        'Id': finding_id,
        'ProductArn': finding_id.rsplit('/', 1)[0],
        'Workflow': {'Status': workflow_status}
    }

    if note:
        update['Note'] = {
            'Text': note,
            'UpdatedBy': 'SHARA'
        }

    response = securityhub.batch_update_findings(
        FindingIdentifiers=[{
            'Id': finding_id,
            'ProductArn': update['ProductArn']
        }],
        Workflow={'Status': workflow_status},
        Note={'Text': note or 'Remediated by SHARA', 'UpdatedBy': 'SHARA'}
    )

    return {
        "updated": len(response.get('ProcessedFindings', [])) > 0,
        "finding_id": finding_id,
        "new_status": workflow_status
    }


@tool
def save_experience_to_ltm(
    control_id: str,
    task_id: str,
    finding_title: str,
    resource_type: str,
    analysis_summary: str,
    remediation_approach: str,
    generated_code: str
) -> dict:
    """保存修复经验到 Memory 长期记忆。

    Args:
        control_id: Control ID
        task_id: 任务 ID
        finding_title: Finding 标题
        resource_type: 资源类型
        analysis_summary: 分析摘要
        remediation_approach: 修复方案
        generated_code: 生成的代码

    Returns:
        保存结果
    """
    from bedrock_agentcore.memory import MemorySessionManager

    manager = MemorySessionManager(
        memory_id=MEMORY_ID,
        region_name="us-east-1"
    )

    # 构建经验文档
    experience = {
        "task_id": task_id,
        "control_id": control_id,
        "finding_title": finding_title,
        "resource_type": resource_type,
        "analysis_summary": analysis_summary,
        "remediation_approach": remediation_approach,
        "generated_code": generated_code,
        "source": "user_validated",
        "created_at": datetime.utcnow().isoformat()
    }

    # 保存到 LTM
    namespace = f"/remediation/{control_id.replace('.', '_')}/{task_id}"

    # 使用 Memory API 保存
    # (具体 API 根据 AgentCore Memory LTM 文档实现)

    return {
        "saved": True,
        "namespace": namespace,
        "experience_id": task_id
    }
```

### 7.4 Agent 实例化

```python
def create_validator_agent(task_id: str, memory_session_id: str) -> Agent:
    """创建 Validator Agent 实例"""

    memory_config = AgentCoreMemoryConfig(
        memory_id=MEMORY_ID,
        actor_id=f"task-{task_id}",
        session_id=memory_session_id
    )

    session_manager = AgentCoreMemorySessionManager(
        agentcore_memory_config=memory_config,
        region_name="us-east-1"
    )

    agent = Agent(
        model=BedrockModel(
            model_id="anthropic.claude-sonnet-4-20250514-v1:0",
            temperature=0.1,
            max_tokens=4096
        ),
        system_prompt=VALIDATOR_SYSTEM_PROMPT,
        tools=[
            review_code_security,      # 代码安全审查
            verify_resource_state,
            update_security_hub_finding,
            save_experience_to_ltm,
            trigger_result_email,      # 触发结果邮件
        ],
        session_manager=session_manager
    )

    return agent
```

---

## 8. 完整工作流程

### 8.1 Phase 1: 分析阶段

```python
async def phase1_analyze(finding: dict) -> dict:
    """Phase 1: 分析 Finding 并生成修复描述"""

    # 1. 创建任务
    task_id = str(uuid.uuid4())
    control_id = extract_control_id(finding)

    # 2. 创建 Memory Session
    memory_session_id = f"session-task-{task_id}"

    # 3. 创建 Analyzer Agent
    analyzer = create_analyzer_agent(task_id, MEMORY_ID)

    # 4. 构建 Prompt
    prompt = f"""
    Analyze this Security Hub Finding and generate a remediation description:

    Control ID: {control_id}
    Finding: {json.dumps(finding, indent=2)}

    Steps:
    1. Fetch ASR playbook for {control_id}
    2. Search for similar past experiences
    3. Get current resource configuration
    4. Assess risk level
    5. Generate detailed remediation description (NO CODE)
    6. Save analysis result to Memory
    """

    # 5. 执行 Agent
    result = analyzer(prompt)

    # 6. 解析结果
    analysis_result = parse_analyzer_output(result.message)

    return {
        "task_id": task_id,
        "memory_session_id": memory_session_id,
        "analysis": analysis_result,
        "approval_required": True
    }
```

### 8.2 Phase 2: 执行阶段

```python
async def phase2_execute(task_id: str, memory_session_id: str) -> dict:
    """Phase 2: 生成代码并执行修复"""

    # 1. 创建 Remediator Agent
    remediator = create_remediator_agent(task_id, memory_session_id)

    # 2. 执行修复
    remediation_prompt = f"""
    Execute remediation for task {task_id}:

    1. Get Phase 1 analysis context from Memory
    2. Get current resource state and save rollback data
    3. Generate Python/boto3 remediation code
    4. Execute code using execute_code tool
    """

    remediation_result = remediator(remediation_prompt)

    # 3. 如果修复成功，调用 Validator
    if remediation_result.get('success'):
        validator = create_validator_agent(task_id, memory_session_id)

        validation_prompt = f"""
        Validate remediation for task {task_id}:

        1. Verify resource state matches expected configuration
        2. Update Security Hub finding status to RESOLVED
        3. Save successful experience to Memory LTM
        """

        validation_result = validator(validation_prompt)

        return {
            "task_id": task_id,
            "remediation": remediation_result,
            "validation": validation_result
        }

    return {
        "task_id": task_id,
        "remediation": remediation_result,
        "validation": None,
        "error": "Remediation failed"
    }
```

### 8.3 状态流转

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  PHASE 1: 审批前                                                                 │
│                                                                                  │
│  PENDING ──▶ ANALYZING ──▶ WAITING_APPROVAL                                     │
│                  │              │                                                │
│                  ▼              ▼                                                │
│           ANALYSIS_FAILED   REJECTED / APPROVAL_EXPIRED                         │
│                                                                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│  PHASE 2: 审批后                                                                 │
│                                                                                  │
│  APPROVED ──▶ GENERATING_CODE ──▶ EXECUTING ──▶ VALIDATING ──▶ WAITING_FEEDBACK │
│                     │                 │              │               │          │
│                     ▼                 ▼              ▼               │          │
│                  FAILED           FAILED          FAILED             │          │
│                                                                      │          │
│                                            ┌─────────────────────────┘          │
│                                            │                                     │
│                                            ▼                                     │
│                                  ┌─────────────────────┐                        │
│                                  │                     │                        │
│                                  ▼                     ▼                        │
│                             COMPLETED             ROLLED_BACK                   │
│                        (经验已保存到 LTM)          (已回滚)                      │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 9. LLM 配置

### 9.1 模型选择

| Agent | 模型 | Temperature | 理由 |
|-------|------|-------------|------|
| Analyzer | Claude Sonnet 4 | 0.2 | 需要准确分析和推理 |
| Remediator | Claude Sonnet 4 | 0.1 | 代码生成需要高度确定性 |
| Validator | Claude Sonnet 4 | 0.1 | 验证任务需要精确 |

### 9.2 模型参数配置

```python
MODEL_CONFIGS = {
    "analyzer": {
        "model_id": "anthropic.claude-sonnet-4-20250514-v1:0",
        "temperature": 0.2,
        "max_tokens": 8192,
        "top_p": 0.9
    },
    "remediator": {
        "model_id": "anthropic.claude-sonnet-4-20250514-v1:0",
        "temperature": 0.1,
        "max_tokens": 8192,
        "top_p": 0.95
    },
    "validator": {
        "model_id": "anthropic.claude-sonnet-4-20250514-v1:0",
        "temperature": 0.1,
        "max_tokens": 4096,
        "top_p": 0.9
    }
}
```

---

## 10. 可观测性

### 10.1 追踪配置

```python
import os

# OpenTelemetry 配置
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "https://your-collector:4317"
os.environ["OTEL_SEMCONV_STABILITY_OPT_IN"] = "gen_ai_latest_experimental"

# Agent 自定义追踪属性
agent = Agent(
    custom_trace_attributes={
        "shara.task_id": task_id,
        "shara.control_id": control_id,
        "shara.phase": "phase1|phase2",
        "shara.resource_arn": resource_arn,
    }
)
```

### 10.2 日志格式

```json
{
    "timestamp": "2025-01-29T10:30:00.123Z",
    "level": "INFO",
    "logger": "shara.agent.analyzer",
    "trace_id": "1-abc123-def456",
    "task_id": "task-12345",
    "phase": "phase1",
    "agent": "analyzer",
    "action": "fetch_asr_playbook",
    "message": "ASR playbook matched",
    "context": {
        "control_id": "S3.1",
        "playbook_id": "ASR_S3_1",
        "match_confidence": 0.95
    }
}
```

### 10.3 关键指标

| 指标 | 类型 | 说明 |
|------|------|------|
| `shara.findings.received` | Counter | 接收的 Finding 数量 |
| `shara.phase1.duration_ms` | Timer | Phase 1 处理时长 |
| `shara.phase2.duration_ms` | Timer | Phase 2 处理时长 |
| `shara.asr.match_rate` | Gauge | ASR 匹配率 |
| `shara.remediation.success_rate` | Gauge | 修复成功率 |
| `shara.llm.tokens.input` | Counter | LLM 输入 Token |
| `shara.llm.tokens.output` | Counter | LLM 输出 Token |

---

## 11. 文档版本

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| 1.0 | 2025-01-28 | - | 初始版本 |
| 2.0 | 2025-01-29 | - | 重构架构：移除 Orchestrator，Lambda 负责调度 |
| 2.1 | 2025-01-29 | - | 新增知识库设计章节 |
| 3.0 | 2025-01-29 | - | 重构为两阶段架构；集成 Strands SDK 和 AgentCore Memory；Analyzer 只生成描述，Remediator 生成代码；使用 @tool 装饰器；新增 Code Interpreter 集成 |
| 4.0 | 2025-01-31 | - | A2A 协议重构：Remediator 通过 A2A 调用 Validator；新增 invoke_validator_agent 工具；Validator 增强职责：代码安全审查 (review_code_security)、触发结果邮件 (trigger_result_email)；结果邮件含 Rollback 链接，回滚邮件不含 |
