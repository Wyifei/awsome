# Amazon Bedrock AgentCore 集成指南

## 1. 概述

本文档介绍如何在 SHARA 系统中集成 Amazon Bedrock AgentCore，包括 Runtime、Gateway、Memory、Policy 等核心功能的使用方式。

### 1.1 AgentCore 简介

Amazon Bedrock AgentCore 是一个用于构建、部署和运营 AI Agent 的企业级平台，提供以下核心服务：

| 服务 | 功能 | SHARA 应用场景 |
|------|------|---------------|
| **Runtime** | Serverless Agent 运行环境 | 部署 Orchestrator/Analyzer/Remediator/Validator |
| **Gateway** | API/Lambda/MCP 转换为 Agent 工具 | 接入 AWS 安全服务 API |
| **Memory** | 短期/长期记忆管理 | 任务状态跟踪、学习历史修复模式 |
| **Policy** | Cedar 策略控制 Agent 行为 | 控制修复操作授权 |
| **Identity** | Agent 身份和访问管理 | 安全访问 AWS 资源 |
| **Observability** | 追踪、调试、监控 | 生产环境监控 |
| **Evaluations** | Agent 质量评估 | 测试修复方案准确性 |

### 1.2 整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Amazon Bedrock AgentCore                              │
│                                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │   Runtime   │  │   Gateway   │  │   Memory    │  │   Policy    │    │
│  │ (部署运行)  │  │ (工具接入)  │  │ (上下文)    │  │ (访问控制)  │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
│                                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │  Identity   │  │Observability│  │ Evaluations │  │   Browser   │    │
│  │ (身份认证)  │  │  (可观测)   │  │  (评估)     │  │ Code Interp │    │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 开发工具

### 2.1 工具选择

| 工具 | 用途 | 推荐场景 |
|------|------|----------|
| **AgentCore Starter Toolkit** | CLI + 高级抽象 | 快速创建、部署、管理 |
| **AgentCore Python SDK** | Python 原生支持 | 代码中集成 Runtime/Memory/Tools |
| **AWS SDK (Boto3)** | 完整 API 访问 | Starter Toolkit 不支持的操作 |
| **AgentCore MCP Server** | IDE 集成 | Cursor/Claude Code/Kiro 中开发 |

### 2.2 安装依赖

```bash
# AgentCore Starter Toolkit
pip install bedrock-agentcore-starter-toolkit

# AgentCore Python SDK
pip install bedrock-agentcore

# Strands Agent Framework
pip install strands-agents strands-agents-tools

# AWS SDK
pip install boto3
```

### 2.3 SDK 对比

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         SDK 层次结构                                      │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │              AgentCore Starter Toolkit (CLI)                         │ │
│  │         agentcore create / launch / gateway / memory                 │ │
│  └───────────────────────────┬─────────────────────────────────────────┘ │
│                              │                                            │
│  ┌───────────────────────────▼─────────────────────────────────────────┐ │
│  │              AgentCore Python SDK                                    │ │
│  │    BedrockAgentCoreApp, MemoryClient, GatewayClient, PolicyClient   │ │
│  └───────────────────────────┬─────────────────────────────────────────┘ │
│                              │                                            │
│  ┌───────────────────────────▼─────────────────────────────────────────┐ │
│  │                    AWS SDK (Boto3)                                   │ │
│  │              bedrock-agentcore / bedrock-agentcore-control           │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Runtime - 部署和运行 Agent

### 3.1 功能概述

AgentCore Runtime 提供：
- **Serverless 运行环境**: 无需管理服务器，自动扩缩容
- **会话隔离**: 每个会话独立运行，互不干扰
- **双向流式通信**: 支持 WebSocket 实时交互
- **多框架支持**: Strands、LangGraph、CrewAI 等

### 3.2 使用 Strands 创建 Agent

```python
from strands import Agent
from strands.models import BedrockModel
from bedrock_agentcore import BedrockAgentCoreApp

# 创建 Bedrock 模型客户端
model = BedrockModel(
    model_id="anthropic.claude-sonnet-4-20250514-v1:0",
    temperature=0.3,
    max_tokens=4096
)

# 创建 Agent
agent = Agent(
    model=model,
    system_prompt="""
    You are the Orchestrator Agent for SHARA system.
    Your role is to coordinate security finding analysis and remediation.
    """
)

# 包装为 AgentCore App
app = BedrockAgentCoreApp()

@app.entrypoint
async def handler(payload, context):
    """AgentCore Runtime 入口点"""
    user_message = payload.get("prompt", "")
    session_id = payload.get("session_id", "default")

    # 流式响应
    async for event in agent.stream_async(user_message):
        yield event
```

### 3.3 部署到 AgentCore Runtime

**方式一：使用 Starter Toolkit CLI**

```bash
# 创建 Agent 项目
agentcore create shara-orchestrator --framework strands

# 本地测试
agentcore dev shara-orchestrator

# 部署到云端
agentcore launch shara-orchestrator
```

**方式二：使用 Python SDK**

```python
from bedrock_agentcore_starter_toolkit.operations.runtime.client import RuntimeClient

client = RuntimeClient(region_name="us-east-1")

# 创建 Runtime
runtime = client.create_runtime(
    name="shara-orchestrator",
    agent_code_path="./src/agents/orchestrator",
    framework="strands",
    memory_size=2048,
    timeout_seconds=900
)

print(f"Runtime ID: {runtime['runtimeId']}")
print(f"Endpoint: {runtime['endpointUrl']}")
```

### 3.4 调用已部署的 Agent

```python
import boto3

# 创建 AgentCore 客户端
client = boto3.client('bedrock-agentcore', region_name='us-east-1')

# 调用 Agent
response = client.invoke_agent_runtime(
    agentRuntimeId='your-runtime-id',
    agentEndpointId='your-endpoint-id',
    sessionId='task-12345678',
    payload={
        'prompt': 'Analyze this security finding...',
        'finding': finding_data
    }
)

# 处理响应
for event in response['body']:
    print(event)
```

### 3.5 SHARA Agent 部署架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    AgentCore Runtime 部署                                │
│                                                                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐         │
│  │  Orchestrator   │  │    Analyzer     │  │   Remediator    │         │
│  │    Runtime      │  │    Runtime      │  │    Runtime      │         │
│  │                 │  │                 │  │                 │         │
│  │ - 任务分发      │  │ - Finding 分析  │  │ - 方案生成      │         │
│  │ - 流程协调      │  │ - 风险评估      │  │ - 执行修复      │         │
│  │ - 状态管理      │  │ - 上下文收集    │  │ - 代码生成      │         │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘         │
│           │                    │                    │                   │
│           └────────────────────┼────────────────────┘                   │
│                                │                                         │
│                    ┌───────────▼───────────┐                            │
│                    │     Validator         │                            │
│                    │     Runtime           │                            │
│                    │                       │                            │
│                    │ - 状态验证            │                            │
│                    │ - Finding 更新        │                            │
│                    └───────────────────────┘                            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Gateway - 工具和 API 接入

### 4.1 功能概述

AgentCore Gateway 提供：
- **API 转换**: 将 REST API、OpenAPI 规范转换为 MCP 工具
- **Lambda 集成**: 将 Lambda 函数转换为 Agent 可调用工具
- **MCP 支持**: 原生支持 Model Context Protocol
- **语义搜索**: Agent 可通过自然语言发现工具
- **安全认证**: OAuth 2.0、IAM、JWT 认证

### 4.2 创建 Gateway

```python
from bedrock_agentcore_starter_toolkit.operations.gateway.client import GatewayClient

gateway_client = GatewayClient(region_name="us-east-1")

# 创建 OAuth 授权器 (使用 Cognito)
auth_response = gateway_client.create_oauth_authorizer_with_cognito(
    name="SHARAGateway"
)

# 创建 Gateway
gateway = gateway_client.create_mcp_gateway(
    name="shara-tools-gateway",
    role_arn=None,  # 自动创建 IAM Role
    authorizer_config=auth_response["authorizer_config"],
    enable_semantic_search=True  # 启用语义搜索
)

print(f"Gateway URL: {gateway['gatewayUrl']}")
print(f"Gateway ID: {gateway['gatewayId']}")
```

### 4.3 添加 Lambda 工具

```python
# 定义 Lambda 函数代码
lambda_code = """
import boto3

def lambda_handler(event, context):
    bucket_name = event.get('bucket_name')
    s3 = boto3.client('s3')

    # 启用 Block Public Access
    s3.put_public_access_block(
        Bucket=bucket_name,
        PublicAccessBlockConfiguration={
            'BlockPublicAcls': True,
            'IgnorePublicAcls': True,
            'BlockPublicPolicy': True,
            'RestrictPublicBuckets': True
        }
    )

    return {
        'status': 'success',
        'message': f'Public access blocked for {bucket_name}'
    }
"""

# 创建 Lambda 并添加为 Gateway Target
from bedrock_agentcore_starter_toolkit.utils.lambda_utils import create_lambda_function

lambda_arn = create_lambda_function(
    session=boto3.Session(region_name="us-east-1"),
    logger=gateway_client.logger,
    function_name="S3BlockPublicAccess",
    lambda_code=lambda_code,
    runtime="python3.13",
    handler="lambda_function.lambda_handler",
    gateway_role_arn=gateway["roleArn"],
    description="Block public access for S3 bucket"
)

# 添加为 Gateway Target
lambda_target = gateway_client.create_mcp_gateway_target(
    gateway=gateway,
    name="S3RemediationTools",
    target_type="lambda",
    target_payload={
        "lambdaArn": lambda_arn,
        "toolSchema": {
            "inlinePayload": [
                {
                    "name": "block_public_access",
                    "description": "Block public access for an S3 bucket",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "bucket_name": {
                                "type": "string",
                                "description": "Name of the S3 bucket"
                            }
                        },
                        "required": ["bucket_name"]
                    }
                }
            ]
        }
    }
)
```

### 4.4 添加 OpenAPI 目标

```python
# 从 OpenAPI 规范导入 API
openapi_target = gateway_client.create_mcp_gateway_target(
    gateway=gateway,
    name="AWSSecurityAPIs",
    target_type="openapi",
    target_payload={
        "openApiSpecification": {
            "s3Location": {
                "bucket": "shara-specs-bucket",
                "key": "openapi/security-hub-api.yaml"
            }
        },
        "baseUrl": "https://securityhub.us-east-1.amazonaws.com"
    },
    credentials={
        "credentialProviderType": "IAM"
    }
)
```

### 4.5 Agent 连接 Gateway

```python
from strands import Agent
from strands.tools.mcp import MCPClient

# 获取访问令牌
access_token = get_oauth_token(
    client_id=auth_response["client_info"]["client_id"],
    client_secret=auth_response["client_info"]["client_secret"],
    token_url=auth_response["client_info"]["token_url"]
)

# 创建 MCP 客户端连接 Gateway
mcp_client = MCPClient(
    gateway_url=gateway["gatewayUrl"],
    auth_token=access_token
)

# 创建使用 Gateway 工具的 Agent
agent = Agent(
    model=model,
    tools=[mcp_client],  # Gateway 作为工具源
    system_prompt="""
    You are a security remediation agent.
    Use the available tools to fix security issues.
    """
)

# Agent 会自动发现 Gateway 中的所有工具
response = agent("Block public access for bucket 'my-insecure-bucket'")
```

### 4.6 SHARA 工具架构设计

#### 4.6.1 设计原则：动态代码生成 vs 预定义工具

**核心思路**：智能体应该动态生成解决问题的代码，而不是简单调用预定义的 Lambda 函数。

| 方案 | 预定义 Lambda 工具 | 动态代码生成 + 沙盒执行 |
|------|-------------------|----------------------|
| **本质** | 工具调用（RPA 思维） | 代码生成（Agent 思维） |
| **灵活性** | 只能处理预定义场景 | 可处理任意场景 |
| **可扩展性** | 新场景需开发新 Lambda | LLM 自动适应 |
| **LLM 价值** | 仅用于决策"调用哪个工具" | 充分发挥代码生成能力 |
| **安全控制** | 简单（预定义操作） | 需要沙盒 + 人工审批 |

#### 4.6.2 工具分类

| 工具类型 | 实现方式 | 用途 | 是否需要审批 |
|----------|---------|------|-------------|
| **只读工具** | Gateway (Lambda/OpenAPI) | 获取资源状态、查询 Finding | 否 |
| **通知工具** | Gateway (Lambda) | 发送邮件、更新状态 | 否 |
| **修复执行** | Code Interpreter 沙盒 | 执行 Agent 生成的 boto3 代码 | **是** |
| **IaC 变更** | GitHub/CodeCommit PR | 生成 CloudFormation/Terraform | **是** |

#### 4.6.3 架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SHARA 工具架构                                        │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                    只读工具 (Gateway)                                ││
│  │                    无需审批，用于信息收集                             ││
│  │                                                                      ││
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐     ││
│  │  │ SecurityHub API │  │  Config API     │  │  资源查询 API   │     ││
│  │  │  (OpenAPI)      │  │  (OpenAPI)      │  │  (Lambda)       │     ││
│  │  │                 │  │                 │  │                 │     ││
│  │  │ - get_findings  │  │ - get_resource  │  │ - get_s3_config │     ││
│  │  │ - get_controls  │  │ - get_compliance│  │ - get_sg_rules  │     ││
│  │  │ - list_members  │  │ - get_history   │  │ - get_iam_policy│     ││
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘     ││
│  └─────────────────────────────────────────────────────────────────────┘│
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                    修复执行 (动态代码生成)                            ││
│  │                    需要人工审批后执行                                 ││
│  │                                                                      ││
│  │  ┌─────────────────────────────────────────────────────────────┐   ││
│  │  │                 Remediator Agent                             │   ││
│  │  │                                                              │   ││
│  │  │  输入: Finding + 上下文                                      │   ││
│  │  │  输出: Python/boto3 修复代码 或 IaC 模板                     │   ││
│  │  └──────────────────────┬──────────────────────────────────────┘   ││
│  │                         │                                          ││
│  │                         ▼                                          ││
│  │  ┌─────────────────────────────────────────────────────────────┐   ││
│  │  │                 人工审批                                      │   ││
│  │  │                                                              │   ││
│  │  │  审批邮件包含:                                               │   ││
│  │  │  - Finding 详情和风险评估                                    │   ││
│  │  │  - Agent 生成的修复代码                                      │   ││
│  │  │  - 预期影响说明                                              │   ││
│  │  │                                                              │   ││
│  │  │  [同意执行] [创建PR] [拒绝]                                  │   ││
│  │  └───────┬─────────────┬─────────────────────┬─────────────────┘   ││
│  │          │             │                     │                     ││
│  │          ▼             ▼                     ▼                     ││
│  │  ┌─────────────┐ ┌─────────────┐     ┌─────────────┐              ││
│  │  │ Code        │ │ GitHub PR   │     │   拒绝      │              ││
│  │  │ Interpreter │ │ (IaC 变更)  │     │   记录原因  │              ││
│  │  │ (沙盒执行)  │ │             │     │             │              ││
│  │  └─────────────┘ └─────────────┘     └─────────────┘              ││
│  └─────────────────────────────────────────────────────────────────────┘│
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                    通知工具 (Gateway)                                ││
│  │                                                                      ││
│  │  ┌─────────────────┐  ┌─────────────────┐                          ││
│  │  │  SES 邮件       │  │ SecurityHub     │                          ││
│  │  │  (Lambda)       │  │  状态更新       │                          ││
│  │  │                 │  │  (Lambda)       │                          ││
│  │  │ - send_approval │  │                 │                          ││
│  │  │ - send_result   │  │ - update_status │                          ││
│  │  └─────────────────┘  └─────────────────┘                          ││
│  └─────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

#### 4.6.4 修复代码生成示例

Remediator Agent 动态生成的代码示例：

```python
# Agent 生成的修复代码 (待审批)
# Finding: S3 bucket 'my-bucket' has public access enabled
# Risk Level: HIGH
# Generated by: Remediator Agent

import boto3

def remediate_s3_public_access(bucket_name: str) -> dict:
    """
    修复 S3 bucket 公开访问问题

    操作:
    1. 启用 Block Public Access
    2. 验证配置生效

    回滚方案:
    aws s3api delete-public-access-block --bucket {bucket_name}
    """
    s3 = boto3.client('s3')

    # 启用 Block Public Access
    s3.put_public_access_block(
        Bucket=bucket_name,
        PublicAccessBlockConfiguration={
            'BlockPublicAcls': True,
            'IgnorePublicAcls': True,
            'BlockPublicPolicy': True,
            'RestrictPublicBuckets': True
        }
    )

    # 验证配置
    response = s3.get_public_access_block(Bucket=bucket_name)
    config = response['PublicAccessBlockConfiguration']

    if all([
        config['BlockPublicAcls'],
        config['IgnorePublicAcls'],
        config['BlockPublicPolicy'],
        config['RestrictPublicBuckets']
    ]):
        return {'status': 'success', 'message': f'Public access blocked for {bucket_name}'}
    else:
        return {'status': 'failed', 'message': 'Configuration verification failed'}

# 执行修复
if __name__ == "__main__":
    result = remediate_s3_public_access("my-bucket")
    print(result)
```

#### 4.6.5 IaC 代码生成示例

对于需要版本控制的变更，Agent 生成 IaC 代码并创建 PR：

```yaml
# Agent 生成的 CloudFormation 模板 (待 PR 审批)
# Finding: S3 bucket 'my-bucket' missing encryption
# Generated by: Remediator Agent

AWSTemplateFormatVersion: '2010-09-09'
Description: Enable S3 bucket encryption for my-bucket

Resources:
  S3BucketEncryption:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: my-bucket
      BucketEncryption:
        ServerSideEncryptionConfiguration:
          - ServerSideEncryptionByDefault:
              SSEAlgorithm: AES256
            BucketKeyEnabled: true

Outputs:
  BucketArn:
    Description: ARN of the encrypted bucket
    Value: !GetAtt S3BucketEncryption.Arn
```

---

## 5. Memory - 上下文记忆

### 5.1 功能概述

AgentCore Memory 提供两种记忆类型：

| 类型 | 功能 | 应用场景 |
|------|------|----------|
| **短期记忆** | 会话内上下文保持 | 单次任务处理过程 |
| **长期记忆** | 跨会话知识提取和存储 | 学习修复模式、用户偏好 |

### 5.2 长期记忆策略

| 策略 | 功能 | SHARA 应用 |
|------|------|-----------|
| **SEMANTIC** | 语义信息提取 | 提取安全修复模式 |
| **SUMMARY** | 会话总结 | 总结修复任务结果 |
| **USER_PREFERENCE** | 用户偏好学习 | 记录审批人偏好 |

### 5.3 创建 Memory

```python
from bedrock_agentcore_starter_toolkit.operations.memory.client import MemoryClient

memory_client = MemoryClient(region_name="us-east-1")

# 创建带长期记忆策略的 Memory
memory = memory_client.create_memory(
    name="shara-agent-memory",
    short_term_memory_ttl_days=7,
    description="Memory for SHARA security remediation agents",
    strategies=[
        {
            "strategyType": "SEMANTIC",
            "description": "Extract security patterns and remediation knowledge"
        },
        {
            "strategyType": "SUMMARY",
            "description": "Summarize remediation sessions for future reference"
        },
        {
            "strategyType": "USER_PREFERENCE",
            "description": "Learn approver preferences and common decisions"
        }
    ]
)

print(f"Memory ID: {memory['memoryId']}")
```

### 5.4 使用 Strands SDK 集成 Memory

```python
from strands import Agent
from strands.memory import AgentCoreMemory

# 配置 Memory
memory = AgentCoreMemory(
    memory_id="your-memory-id",
    region="us-east-1"
)

# 创建带记忆的 Agent
agent = Agent(
    model=model,
    memory=memory,
    system_prompt="""
    You are a security analyst with memory of past incidents.
    Use your memory to provide context-aware recommendations.
    """
)

# Agent 会自动:
# 1. 从 Memory 检索相关上下文
# 2. 在对话结束后存储重要信息
response = agent("What similar S3 issues have we fixed before?")
```

### 5.5 手动操作 Memory

```python
import boto3

client = boto3.client('bedrock-agentcore', region_name='us-east-1')

# 添加短期记忆事件
client.create_memory_event(
    memoryId='your-memory-id',
    actorId='orchestrator-agent',
    sessionId='task-12345678',
    event={
        'type': 'remediation_completed',
        'finding_type': 'S3PublicAccess',
        'resource_id': 'arn:aws:s3:::my-bucket',
        'action_taken': 'block_public_access',
        'result': 'success',
        'timestamp': '2025-01-28T10:30:00Z'
    }
)

# 检索长期记忆
response = client.retrieve_memories(
    memoryId='your-memory-id',
    actorId='orchestrator-agent',
    query='S3 public access remediation patterns',
    maxResults=10
)

for memory in response['memories']:
    print(f"Memory: {memory['content']}")
    print(f"Relevance: {memory['score']}")
```

### 5.6 SHARA Memory 应用架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SHARA Memory 架构                                     │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                    shara-agent-memory                                ││
│  │                                                                      ││
│  │  ┌───────────────────────────────────────────────────────────────┐  ││
│  │  │                    Short-Term Memory                           │  ││
│  │  │                                                                │  ││
│  │  │  Session: task-12345678                                        │  ││
│  │  │  ├── finding_received: S3 public access detected               │  ││
│  │  │  ├── analysis_completed: risk=HIGH, impact=data_exposure       │  ││
│  │  │  ├── remediation_planned: block_public_access                  │  ││
│  │  │  ├── approval_requested: sent to admin@example.com            │  ││
│  │  │  └── ...                                                       │  ││
│  │  │                                                                │  ││
│  │  │  TTL: 7 days                                                   │  ││
│  │  └───────────────────────────────────────────────────────────────┘  ││
│  │                                                                      ││
│  │  ┌───────────────────────────────────────────────────────────────┐  ││
│  │  │                    Long-Term Memory                            │  ││
│  │  │                                                                │  ││
│  │  │  Semantic Memories:                                            │  ││
│  │  │  ├── "S3 buckets with 'data' prefix are high priority"         │  ││
│  │  │  ├── "Block public access is preferred over policy changes"    │  ││
│  │  │  └── "Production buckets require manager approval"             │  ││
│  │  │                                                                │  ││
│  │  │  Session Summaries:                                            │  ││
│  │  │  ├── "Jan 28: Fixed 5 S3 public access issues, 100% success"   │  ││
│  │  │  └── "Jan 27: Handled 3 security group issues, 1 rejected"     │  ││
│  │  │                                                                │  ││
│  │  │  User Preferences:                                             │  ││
│  │  │  ├── "admin@example.com prefers detailed impact analysis"      │  ││
│  │  │  └── "security-team prefers CLI commands over CloudFormation"  │  ││
│  │  └───────────────────────────────────────────────────────────────┘  ││
│  └─────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Policy - 访问控制

### 6.1 功能概述

AgentCore Policy 使用 Cedar 策略语言控制 Agent 行为：

- **细粒度授权**: 控制 Agent 可执行的具体操作
- **实时拦截**: 在 Gateway 层拦截并验证每个工具调用
- **自然语言转换**: 支持自然语言描述转换为 Cedar 策略
- **审计日志**: 记录所有策略决策

### 6.2 Cedar 策略语言

```cedar
// 允许操作
permit(
    principal,                                    // 执行者
    action == AgentCore::Action::"tool_name",    // 操作
    resource                                      // 资源
) when {
    condition                                     // 条件
};

// 禁止操作
forbid(
    principal,
    action == AgentCore::Action::"dangerous_action",
    resource
);
```

### 6.3 创建 Policy Engine

```python
from bedrock_agentcore_starter_toolkit.operations.policy.client import PolicyClient

policy_client = PolicyClient(region_name="us-east-1")

# 创建策略引擎
engine = policy_client.create_or_get_policy_engine(
    name="SHARAPolicyEngine",
    description="Policy engine for security remediation governance"
)

print(f"Policy Engine ID: {engine['policyEngineId']}")
print(f"Policy Engine ARN: {engine['policyEngineArn']}")
```

### 6.4 创建 Cedar 策略

```python
# 定义 SHARA 策略
cedar_policies = """
// ============================================
// SHARA Security Remediation Policies
// ============================================

// 允许所有读取/分析操作
permit(
    principal,
    action in [
        AgentCore::Action::"SecurityHub___get_findings",
        AgentCore::Action::"S3Tools___get_bucket_policy",
        AgentCore::Action::"EC2Tools___describe_security_groups",
        AgentCore::Action::"IAMTools___get_role"
    ],
    resource
);

// 允许低风险修复操作 (无需审批)
permit(
    principal,
    action in [
        AgentCore::Action::"S3Tools___block_public_access",
        AgentCore::Action::"S3Tools___put_bucket_encryption"
    ],
    resource
) when {
    context.risk_level == "LOW"
};

// 高风险修复操作需要审批
permit(
    principal,
    action in [
        AgentCore::Action::"S3Tools___put_bucket_policy",
        AgentCore::Action::"EC2Tools___revoke_security_group_ingress",
        AgentCore::Action::"IAMTools___put_role_policy"
    ],
    resource
) when {
    context.approval_status == "approved" &&
    context.approved_by != ""
};

// 禁止删除操作
forbid(
    principal,
    action in [
        AgentCore::Action::"S3Tools___delete_bucket",
        AgentCore::Action::"EC2Tools___delete_security_group",
        AgentCore::Action::"IAMTools___delete_role"
    ],
    resource
);

// 禁止修改生产环境关键资源 (除非紧急)
forbid(
    principal,
    action,
    resource
) when {
    resource.tags.environment == "production" &&
    resource.tags.critical == "true" &&
    context.emergency_override != true
};
"""

# 创建策略
policy = policy_client.create_or_get_policy(
    policy_engine_id=engine["policyEngineId"],
    name="shara_remediation_governance",
    description="Governance policies for SHARA remediation actions",
    definition={"cedar": {"statement": cedar_policies}}
)

print(f"Policy ID: {policy['policyId']}")
```

### 6.5 将 Policy Engine 绑定到 Gateway

```python
# 绑定策略到 Gateway
gateway_client.update_gateway_policy_engine(
    gateway_identifier=gateway["gatewayId"],
    policy_engine_arn=engine["policyEngineArn"],
    mode="ENFORCE"  # ENFORCE | MONITOR
)
```

### 6.6 策略执行模式

| 模式 | 行为 | 适用场景 |
|------|------|----------|
| **ENFORCE** | 阻止违反策略的操作 | 生产环境 |
| **MONITOR** | 仅记录，不阻止 | 测试、策略验证 |

### 6.7 SHARA Policy 架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SHARA Policy 执行流程                                 │
│                                                                          │
│  Agent Request                                                           │
│       │                                                                  │
│       ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                    AgentCore Gateway                                 ││
│  │                         │                                            ││
│  │                         ▼                                            ││
│  │  ┌─────────────────────────────────────────────────────────────┐   ││
│  │  │              Policy Engine (Cedar)                           │   ││
│  │  │                                                              │   ││
│  │  │  Request Context:                                            │   ││
│  │  │  {                                                           │   ││
│  │  │    "action": "S3Tools___put_bucket_policy",                  │   ││
│  │  │    "resource": "arn:aws:s3:::my-bucket",                     │   ││
│  │  │    "context": {                                              │   ││
│  │  │      "approval_status": "approved",                          │   ││
│  │  │      "approved_by": "admin@example.com",                     │   ││
│  │  │      "risk_level": "HIGH"                                    │   ││
│  │  │    }                                                         │   ││
│  │  │  }                                                           │   ││
│  │  │                                                              │   ││
│  │  │  Policy Evaluation: ✅ ALLOW                                 │   ││
│  │  └─────────────────────────────────────────────────────────────┘   ││
│  │                         │                                            ││
│  │                         ▼                                            ││
│  │                   Execute Tool                                       ││
│  └─────────────────────────────────────────────────────────────────────┘│
│                         │                                                │
│                         ▼                                                │
│                   Tool Response                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Code Interpreter - 沙盒执行

### 7.1 功能概述

AgentCore Code Interpreter 提供安全的沙盒执行环境，让 Agent 可以动态生成并执行代码：

| 功能 | 描述 | SHARA 应用 |
|------|------|-----------|
| **沙盒隔离** | 每次执行在隔离容器中运行 | 安全执行 Agent 生成的修复代码 |
| **预装环境** | Python 3.x + 常用库 (boto3, pandas, etc.) | 直接执行 AWS SDK 代码 |
| **文件系统** | 临时文件系统，执行后清理 | 生成报告、处理数据 |
| **执行超时** | 可配置执行时间限制 | 防止无限循环 |
| **输出捕获** | 捕获 stdout/stderr/返回值 | 获取修复结果 |

### 7.2 为什么使用 Code Interpreter

在 SHARA 的动态代码生成架构中，Code Interpreter 是关键组件：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    预定义工具 vs Code Interpreter                        │
│                                                                          │
│  ┌───────────────────────────────┐  ┌───────────────────────────────┐  │
│  │      预定义 Lambda 工具        │  │      Code Interpreter         │  │
│  │                               │  │                               │  │
│  │  ┌─────────────────────────┐  │  │  ┌─────────────────────────┐  │  │
│  │  │ Lambda: block_s3_access │  │  │  │  Agent 生成代码:        │  │  │
│  │  │ Lambda: enable_encrypt  │  │  │  │  "根据 Finding 动态     │  │  │
│  │  │ Lambda: revoke_sg_rule  │  │  │  │   生成 boto3 代码"      │  │  │
│  │  │ Lambda: ...             │  │  │  └─────────────────────────┘  │  │
│  │  └─────────────────────────┘  │  │              │                │  │
│  │              │                │  │              ▼                │  │
│  │              ▼                │  │  ┌─────────────────────────┐  │  │
│  │  - 只能处理预定义场景         │  │  │  沙盒执行生成的代码      │  │  │
│  │  - 新场景需要开发新 Lambda    │  │  │  - 安全隔离              │  │  │
│  │  - LLM 仅做决策              │  │  │  - 可处理任意场景        │  │  │
│  │                               │  │  │  - 充分利用 LLM 能力     │  │  │
│  └───────────────────────────────┘  │  └─────────────────────────┘  │  │
│                                      └───────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 7.3 启用 Code Interpreter

**方式一：创建 Agent Runtime 时启用**

```python
from bedrock_agentcore import BedrockAgentCoreApp

app = BedrockAgentCoreApp()

# 创建带 Code Interpreter 的 Runtime
runtime_config = {
    "name": "shara-remediator",
    "framework": "strands",
    "code_interpreter": {
        "enabled": True,
        "timeout_seconds": 300,
        "memory_size_mb": 1024,
        "allowed_packages": ["boto3", "botocore", "json", "yaml"],
        "environment_variables": {
            "AWS_REGION": "us-east-1"
        }
    }
}
```

**方式二：作为工具添加到 Agent**

```python
from strands import Agent
from strands.tools import CodeInterpreterTool

# 创建 Code Interpreter 工具
code_interpreter = CodeInterpreterTool(
    timeout_seconds=300,
    sandbox_config={
        "memory_mb": 1024,
        "cpu_shares": 512
    }
)

# 添加到 Agent
agent = Agent(
    model=model,
    tools=[code_interpreter],
    system_prompt="""
    You are a security remediation agent.
    When you need to fix AWS resources, generate Python/boto3 code
    and use the code_interpreter tool to execute it.
    """
)
```

### 7.4 在 Strands Agent 中使用 Code Interpreter

```python
from strands import Agent
from strands.models import BedrockModel
from strands.tools import CodeInterpreterTool

# 配置 Agent
model = BedrockModel(
    model_id="anthropic.claude-sonnet-4-20250514-v1:0",
    temperature=0.2
)

code_interpreter = CodeInterpreterTool(
    timeout_seconds=300
)

remediator_agent = Agent(
    model=model,
    tools=[code_interpreter],
    system_prompt="""
    You are the SHARA Remediator Agent.

    Your task is to fix AWS security findings by:
    1. Analyzing the finding details
    2. Generating appropriate boto3 Python code
    3. Using code_interpreter to execute the code in a sandbox

    IMPORTANT:
    - Always include error handling in your code
    - Include verification steps to confirm the fix worked
    - Return clear success/failure status with details

    Example workflow:
    1. Receive: "S3 bucket 'my-bucket' has public access"
    2. Generate: Python code to block public access
    3. Execute: Run code via code_interpreter
    4. Verify: Check the configuration changed correctly
    5. Report: Return success/failure with evidence
    """
)

# Agent 执行示例
result = remediator_agent("""
Fix the following security finding:
- Resource: arn:aws:s3:::my-insecure-bucket
- Issue: Public access is enabled
- Severity: HIGH
""")
```

### 7.5 SHARA 审批后执行流程

在 SHARA 系统中，Code Interpreter 与人工审批流程集成：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SHARA Code Interpreter 执行流程                       │
│                                                                          │
│  1. Finding 分析完成                                                     │
│           │                                                              │
│           ▼                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │  2. Remediator Agent 生成修复代码                                    ││
│  │                                                                      ││
│  │  ```python                                                           ││
│  │  import boto3                                                        ││
│  │  s3 = boto3.client('s3')                                            ││
│  │  s3.put_public_access_block(                                        ││
│  │      Bucket='my-bucket',                                            ││
│  │      PublicAccessBlockConfiguration={...}                           ││
│  │  )                                                                   ││
│  │  ```                                                                 ││
│  └─────────────────────────────────────────────────────────────────────┘│
│           │                                                              │
│           ▼                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │  3. 发送审批邮件 (包含生成的代码)                                    ││
│  │                                                                      ││
│  │  To: security-admin@example.com                                      ││
│  │  Subject: [SHARA] 待审批: S3 公开访问修复                            ││
│  │                                                                      ││
│  │  Finding: S3 bucket 'my-bucket' has public access                   ││
│  │  Risk: HIGH                                                          ││
│  │  Proposed Code: [显示上述代码]                                       ││
│  │                                                                      ││
│  │  [同意执行] [拒绝]                                                   ││
│  └─────────────────────────────────────────────────────────────────────┘│
│           │                                                              │
│           ├────────────────────────┐                                    │
│           ▼                        ▼                                    │
│  ┌─────────────────┐      ┌─────────────────┐                          │
│  │  审批通过       │      │  审批拒绝       │                          │
│  └────────┬────────┘      └────────┬────────┘                          │
│           │                        │                                    │
│           ▼                        ▼                                    │
│  ┌─────────────────┐      ┌─────────────────┐                          │
│  │  4. Code        │      │  记录拒绝原因   │                          │
│  │  Interpreter    │      │  更新任务状态   │                          │
│  │  执行代码       │      └─────────────────┘                          │
│  └────────┬────────┘                                                    │
│           │                                                              │
│           ▼                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │  5. 验证执行结果                                                     ││
│  │                                                                      ││
│  │  Validator Agent 检查:                                               ││
│  │  - 资源配置是否正确更新                                              ││
│  │  - Security Hub Finding 是否自动解决                                 ││
│  └─────────────────────────────────────────────────────────────────────┘│
│           │                                                              │
│           ▼                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │  6. 更新状态并通知                                                   ││
│  │                                                                      ││
│  │  - DynamoDB: 更新任务状态为 RESOLVED                                 ││
│  │  - Security Hub: 更新 Finding Workflow Status                        ││
│  │  - SES: 发送完成通知邮件                                             ││
│  └─────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

### 7.6 代码执行实现示例

```python
import json
from strands import Agent
from strands.tools import CodeInterpreterTool

class SHARARemediatorService:
    def __init__(self):
        self.code_interpreter = CodeInterpreterTool(
            timeout_seconds=300,
            sandbox_config={
                "memory_mb": 1024,
                "environment": {
                    "AWS_REGION": "us-east-1"
                }
            }
        )

        self.agent = Agent(
            model=BedrockModel(model_id="anthropic.claude-sonnet-4-20250514-v1:0"),
            tools=[self.code_interpreter],
            system_prompt=self._get_system_prompt()
        )

    def _get_system_prompt(self):
        return """
        You are the SHARA Remediator Agent responsible for generating
        and executing AWS security remediation code.

        When given a security finding:
        1. Analyze the issue and determine the fix
        2. Generate Python/boto3 code to remediate
        3. Execute the code using code_interpreter tool
        4. Return structured result with status and details

        Code generation guidelines:
        - Include comprehensive error handling
        - Add verification checks after each operation
        - Use descriptive variable names
        - Add comments explaining each step
        - Return JSON result with status, message, and evidence
        """

    async def execute_approved_remediation(
        self,
        task_id: str,
        finding: dict,
        generated_code: str
    ) -> dict:
        """
        执行已审批的修复代码
        """
        # 使用 Code Interpreter 执行代码
        result = await self.code_interpreter.execute(
            code=generated_code,
            context={
                "task_id": task_id,
                "finding_id": finding.get("Id"),
                "resource_arn": finding.get("Resources", [{}])[0].get("Id")
            }
        )

        return {
            "task_id": task_id,
            "execution_status": "success" if result.success else "failed",
            "output": result.stdout,
            "error": result.stderr if not result.success else None,
            "return_value": result.return_value
        }

    async def generate_remediation_code(self, finding: dict) -> str:
        """
        使用 Agent 生成修复代码 (不执行)
        """
        prompt = f"""
        Generate Python/boto3 remediation code for this security finding.
        DO NOT execute the code, just return the code.

        Finding:
        {json.dumps(finding, indent=2)}

        Return ONLY the Python code, no explanations.
        """

        response = await self.agent.generate(prompt)
        return self._extract_code_from_response(response)
```

### 7.7 安全考虑

| 安全措施 | 实现方式 | 说明 |
|----------|---------|------|
| **沙盒隔离** | 容器级隔离 | 代码在独立容器中运行 |
| **网络限制** | VPC 配置 | 只允许访问必要的 AWS 端点 |
| **权限限制** | IAM Role | 使用最小权限的执行角色 |
| **执行超时** | 硬超时限制 | 防止恶意或失控代码 |
| **代码审查** | 人工审批 | 执行前必须人工确认 |
| **审计日志** | CloudTrail | 记录所有执行操作 |

### 7.8 与 IaC PR 方式的对比

| 场景 | Code Interpreter | GitHub PR |
|------|------------------|-----------|
| **即时修复** | ✅ 直接执行 boto3 代码 | ❌ 需要 PR merge + 部署 |
| **可回滚性** | ⚠️ 需代码包含回滚逻辑 | ✅ Git revert + 重新部署 |
| **版本控制** | ❌ 无历史记录 | ✅ 完整版本历史 |
| **审批流程** | 邮件审批 | PR Review |
| **适用场景** | 紧急修复、配置变更 | 基础设施变更、持久配置 |

**建议**:
- **紧急安全问题**: Code Interpreter 直接修复
- **基础设施变更**: 生成 IaC 代码并创建 PR
- **可逆配置变更**: 两种方式均可，根据紧急程度选择

---

## 8. SHARA 系统集成架构

### 8.1 完整集成架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SHARA + AgentCore 完整架构                            │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                    Event Sources                                     ││
│  │  Security Hub ──► EventBridge ──► Lambda (Event Processor)          ││
│  └──────────────────────────────────────────┬──────────────────────────┘│
│                                             │                            │
│  ┌──────────────────────────────────────────▼──────────────────────────┐│
│  │                    AgentCore Runtime Layer                           ││
│  │                                                                      ││
│  │  ┌─────────────────┐                                                ││
│  │  │  Orchestrator   │◄──── Memory (任务状态)                         ││
│  │  │    Runtime      │                                                ││
│  │  └────────┬────────┘                                                ││
│  │           │                                                          ││
│  │     ┌─────┴─────┬─────────────┐                                     ││
│  │     ▼           ▼             ▼                                     ││
│  │  ┌──────┐  ┌──────────┐  ┌──────────┐                              ││
│  │  │Anlyzr│  │Remediator│  │Validator │                              ││
│  │  │Runtme│  │ Runtime  │  │ Runtime  │                              ││
│  │  └──┬───┘  └────┬─────┘  └────┬─────┘                              ││
│  │     │           │             │                                     ││
│  └─────┼───────────┼─────────────┼─────────────────────────────────────┘│
│        │           │             │                                       │
│  ┌─────▼───────────▼─────────────▼─────────────────────────────────────┐│
│  │                    AgentCore Gateway                                 ││
│  │                         │                                            ││
│  │                    Policy Engine ◄──── Cedar Policies               ││
│  │                         │                                            ││
│  │  ┌──────────┬──────────┬──────────┬──────────┬──────────┐          ││
│  │  │ S3 Tools │EC2 Tools │IAM Tools │ SH Tools │SES Tools │          ││
│  │  │ (Lambda) │ (Lambda) │ (Lambda) │ (OpenAPI)│ (Lambda) │          ││
│  │  └──────────┴──────────┴──────────┴──────────┴──────────┘          ││
│  └─────────────────────────────────────────────────────────────────────┘│
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐│
│  │                    Supporting Services                               ││
│  │                                                                      ││
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐    ││
│  │  │  DynamoDB  │  │ Bedrock KB │  │   SES      │  │ CloudWatch │    ││
│  │  │  (Tasks)   │  │ (Playbooks)│  │  (Email)   │  │  (Logs)    │    ││
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘    ││
│  └─────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

### 8.2 各 Agent 的 AgentCore 功能使用

| Agent | Runtime | Gateway | Memory | Policy |
|-------|---------|---------|--------|--------|
| **Orchestrator** | ✅ 部署运行 | ✅ 调用子 Agent | ✅ 任务状态跟踪 | - |
| **Analyzer** | ✅ 部署运行 | ✅ AWS 读取 API | ✅ 历史分析模式 | - |
| **Remediator** | ✅ 部署运行 | ✅ 修复工具 | ✅ 修复模式学习 | ✅ 操作授权 |
| **Validator** | ✅ 部署运行 | ✅ 验证工具 | - | - |

### 8.3 数据流示例

```
1. Finding 接收
   Security Hub ──► EventBridge ──► Lambda
                                      │
                                      ▼
2. 任务创建                    DynamoDB (创建任务记录)
                                      │
                                      ▼
3. Agent 处理            AgentCore Runtime (Orchestrator)
                              │
                              ├──► Memory (获取历史上下文)
                              │
                              ├──► Analyzer Runtime
                              │         │
                              │         └──► Gateway (S3/EC2/IAM 读取工具)
                              │
                              ├──► Remediator Runtime
                              │         │
                              │         ├──► Gateway (修复工具)
                              │         │         │
                              │         │         └──► Policy (验证授权)
                              │         │
                              │         └──► Memory (记录修复模式)
                              │
                              └──► Validator Runtime
                                        │
                                        └──► Gateway (验证工具)

4. 结果处理
   DynamoDB (更新任务状态) ◄──── Orchestrator
                                      │
                                      ▼
                               SES (发送通知)
```

---

## 9. 区域可用性

### 9.1 AgentCore 服务可用区域

| 区域 | Runtime | Gateway | Memory | Policy |
|------|---------|---------|--------|--------|
| us-east-1 (N. Virginia) | ✅ | ✅ | ✅ | ✅ |
| us-west-2 (Oregon) | ✅ | ✅ | ✅ | ✅ |
| eu-west-1 (Ireland) | ✅ | ✅ | ✅ | ✅ |
| ap-southeast-1 (Singapore) | ✅ | ✅ | ✅ | ✅ |
| ap-northeast-1 (Tokyo) | ✅ | ✅ | ✅ | ✅ |

### 9.2 定价模式

所有 AgentCore 服务采用**按需计费**模式：

| 服务 | 计费方式 |
|------|----------|
| Runtime | 按 CPU/Memory 使用时间 (秒) |
| Gateway | 按 API 调用次数 |
| Memory | 按事件数量 + 存储量 |
| Policy | 按授权请求次数 |

---

## 10. 参考资源

### 10.1 官方文档

- [AgentCore Developer Guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/)
- [AgentCore API Reference](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/)
- [AgentCore Pricing](https://aws.amazon.com/bedrock/agentcore/pricing/)

### 10.2 GitHub 仓库

- [AgentCore Starter Toolkit](https://github.com/aws/bedrock-agentcore-starter-toolkit)
- [AgentCore Python SDK](https://github.com/aws/bedrock-agentcore-sdk-python)
- [Strands Agents Framework](https://github.com/strands-agents/strands-agents)

### 10.3 示例代码

- [AgentCore Examples](https://github.com/aws-samples/amazon-bedrock-agentcore-samples)
- [Strands Agents Examples](https://github.com/strands-agents/strands-agents/tree/main/examples)

---

## 11. 文档版本

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| 1.0 | 2025-01-29 | - | 初始版本 |
| 1.1 | 2025-01-29 | - | 更新工具架构为动态代码生成模式，添加 Code Interpreter 章节 |
