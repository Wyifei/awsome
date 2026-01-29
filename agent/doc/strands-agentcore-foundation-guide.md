# Strands Agent & AgentCore 基础知识文档

> 本文档总结了 Strands Agent SDK 和 AWS Bedrock AgentCore 的核心概念和工作方法，用于指导 SHARA 项目中智能体的开发。

## 目录

- [1. 概述](#1-概述)
- [2. Strands Agent SDK](#2-strands-agent-sdk)
  - [2.1 核心架构](#21-核心架构)
  - [2.2 Agent 基本用法](#22-agent-基本用法)
  - [2.3 工具系统](#23-工具系统)
  - [2.4 Session 管理](#24-session-管理)
  - [2.5 Hooks 系统](#25-hooks-系统)
  - [2.6 可观测性 (Telemetry)](#26-可观测性-telemetry)
- [3. AWS Bedrock AgentCore](#3-aws-bedrock-agentcore)
  - [3.1 服务概览](#31-服务概览)
  - [3.2 Runtime 服务](#32-runtime-服务)
  - [3.3 Memory 服务](#33-memory-服务)
  - [3.4 Gateway 服务](#34-gateway-服务)
  - [3.5 Identity 服务](#35-identity-服务)
  - [3.6 可观测性](#36-可观测性)
  - [3.7 Policy 服务 (Cedar)](#37-policy-服务-cedar)
  - [3.8 Code Interpreter 服务](#38-code-interpreter-服务)
- [4. Strands + AgentCore 集成](#4-strands--agentcore-集成)
- [5. SHARA 项目应用指南](#5-shara-项目应用指南)

---

## 1. 概述

### Strands Agent SDK
Strands Agents 是一个轻量级、模型驱动的 AI Agent 框架，支持用几行代码构建从简单对话助手到复杂自主工作流的各类智能体。

### AWS Bedrock AgentCore
AgentCore 提供企业级的 Agent 部署和运维能力，包括安全的运行时环境、持久化记忆、API 网关、身份认证等服务。

**核心理念**：使用 Strands 开发 Agent 逻辑，使用 AgentCore 部署到生产环境。

### 开发工具选择

| 工具 | 用途 | 推荐场景 |
|------|------|----------|
| **Strands Agent SDK** | Agent 开发框架 | 开发 Agent 逻辑 |
| **AgentCore Python SDK** | AgentCore 服务集成 | Runtime/Memory/Gateway 操作 |
| **AgentCore Starter Toolkit** | CLI + 高级抽象 | 快速创建、部署、管理 |
| **AWS SDK (Boto3)** | 完整 API 访问 | 底层操作 |

```bash
# 安装依赖
pip install strands-agents strands-agents-tools  # Strands
pip install bedrock-agentcore                    # AgentCore SDK
pip install bedrock-agentcore-starter-toolkit    # Starter Toolkit (可选)
```

### 快速示例

```python
# 本地开发
from strands import Agent
agent = Agent(tools=[my_tools])
agent("处理用户请求")

# 部署到 AgentCore
from bedrock_agentcore import BedrockAgentCoreApp
app = BedrockAgentCoreApp()

@app.entrypoint
def production_agent(request):
    return agent(request.get("prompt"))

app.run()
```

---

## 2. Strands Agent SDK

### 2.1 核心架构

```
src/strands/
├── agent/                    # Agent 核心实现
│   ├── agent.py             # Agent 主类
│   ├── agent_result.py      # 结果封装
│   └── conversation_manager.py
├── event_loop/              # Agent 事件循环
├── models/                  # 模型提供商
│   ├── bedrock.py          # Amazon Bedrock
│   ├── anthropic.py        # Anthropic API
│   ├── openai.py           # OpenAI
│   └── ...
├── tools/                   # 工具系统
│   ├── decorator.py        # @tool 装饰器
│   ├── registry.py         # 工具注册
│   └── mcp/                # MCP 协议支持
├── session/                 # Session 管理
│   ├── session_manager.py
│   ├── file_session_manager.py
│   ├── s3_session_manager.py
│   └── repository_session_manager.py
├── hooks/                   # Hook 系统
│   ├── events.py           # 事件定义
│   └── registry.py         # Hook 注册
├── telemetry/              # 可观测性
│   ├── tracer.py           # OpenTelemetry 追踪
│   ├── metrics.py          # 指标收集
│   └── config.py
└── multiagent/             # 多智能体
    ├── swarm.py
    └── graph.py
```

### 2.2 Agent 基本用法

```python
from strands import Agent
from strands.models import BedrockModel

# 创建 Agent
agent = Agent(
    model=BedrockModel(model_id="anthropic.claude-sonnet-4-20250514-v1:0"),
    system_prompt="你是一个安全运维专家",
    tools=[my_tool_1, my_tool_2],
)

# 调用 Agent
result = agent("分析这个安全告警")

# 获取结果
print(result.message)           # 最终回复
print(result.stop_reason)       # 停止原因
print(result.metrics)           # 性能指标
```

### 2.3 工具系统

#### 使用装饰器定义工具

```python
from strands import tool

@tool
def analyze_security_finding(
    finding_id: str,
    resource_arn: str,
    severity: str
) -> dict:
    """分析安全发现并生成修复建议。

    Args:
        finding_id: Security Hub 发现 ID
        resource_arn: 受影响资源的 ARN
        severity: 严重程度 (CRITICAL/HIGH/MEDIUM/LOW)

    Returns:
        包含分析结果和修复建议的字典
    """
    # 工具实现
    return {
        "analysis": "...",
        "remediation_steps": [...]
    }
```

#### MCP 工具集成

```python
from strands.tools.mcp import MCPClient
from mcp import stdio_client, StdioServerParameters

# 连接 MCP 服务器
mcp_client = MCPClient(
    lambda: stdio_client(StdioServerParameters(
        command="uvx",
        args=["awslabs.aws-documentation-mcp-server@latest"]
    ))
)

with mcp_client:
    agent = Agent(tools=mcp_client.list_tools_sync())
```

### 2.4 Session 管理

Session 管理负责持久化对话历史和上下文。

#### Session Manager 类型

| 类型 | 用途 | 存储位置 |
|------|------|----------|
| `FileSessionManager` | 本地开发 | 本地文件系统 |
| `S3SessionManager` | 云端存储 | Amazon S3 |
| `RepositorySessionManager` | 自定义后端 | 可插拔 |
| `AgentCoreMemorySessionManager` | AgentCore 集成 | AgentCore Memory |

#### 基本用法

```python
from strands import Agent
from strands.session import FileSessionManager

# 本地 Session
session_manager = FileSessionManager(
    session_id="user-123-session",
    storage_dir="./sessions"
)

agent = Agent(
    session_manager=session_manager,
    tools=[...]
)
```

#### AgentCore Memory 集成

```python
from bedrock_agentcore.memory.integrations.strands import (
    AgentCoreMemorySessionManager,
    AgentCoreMemoryConfig,
    RetrievalConfig
)

# 配置 AgentCore Memory
config = AgentCoreMemoryConfig(
    memory_id="my-memory-id",
    actor_id="user-123",
    session_id="session-456",
    retrieval_config={
        "security/findings/{actorId}": RetrievalConfig(top_k=5, relevance_score=0.3),
        "remediation/history/{sessionId}": RetrievalConfig(top_k=3, relevance_score=0.5)
    }
)

session_manager = AgentCoreMemorySessionManager(
    agentcore_memory_config=config,
    region_name="us-east-1"
)

agent = Agent(session_manager=session_manager)
```

### 2.5 Hooks 系统

Hooks 提供事件驱动的扩展机制，用于在 Agent 执行流程的关键点注入自定义逻辑。

#### 事件类型

| 事件 | 触发时机 |
|------|----------|
| `BeforeModelInvokeEvent` | 模型调用前 |
| `AfterModelInvokeEvent` | 模型调用后 |
| `BeforeToolCallEvent` | 工具调用前 |
| `AfterToolCallEvent` | 工具调用后 |
| `MessageAddedEvent` | 消息添加时 |

#### 命名约定

- 所有事件以 `Event` 结尾
- 配对事件使用 `Before{Action}Event` 和 `After{Action}Event`
- 每个 `Before` 事件都有对应的 `After` 事件

#### 用法示例

```python
from strands.hooks import HookProvider, BeforeToolCallEvent, AfterToolCallEvent

class SecurityHookProvider(HookProvider):
    def register_hooks(self, registry):
        registry.add_callback(BeforeToolCallEvent, self.before_tool_call)
        registry.add_callback(AfterToolCallEvent, self.after_tool_call)

    def before_tool_call(self, event: BeforeToolCallEvent):
        # 记录工具调用
        print(f"调用工具: {event.selected_tool.name}")

        # 可修改工具选择
        # event.selected_tool = alternative_tool

    def after_tool_call(self, event: AfterToolCallEvent):
        # 记录结果
        print(f"工具结果: {event.result}")
```

### 2.6 可观测性 (Telemetry)

Strands 使用 OpenTelemetry 实现追踪和指标收集。

#### 配置环境变量

```bash
# 启用 OTLP 导出
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"

# 启用最新 GenAI 语义约定
export OTEL_SEMCONV_STABILITY_OPT_IN="gen_ai_latest_experimental,gen_ai_tool_definitions"
```

#### Tracer 核心功能

```python
from strands.telemetry import get_tracer

tracer = get_tracer()

# Agent 调用追踪
span = tracer.start_agent_span(
    messages=messages,
    agent_name="SecurityAnalyzer",
    model_id="claude-sonnet",
    tools=["analyze_finding", "apply_remediation"]
)

# 工具调用追踪
tool_span = tracer.start_tool_call_span(
    tool=tool_use,
    parent_span=span
)

# 结束追踪
tracer.end_tool_call_span(tool_span, tool_result)
tracer.end_agent_span(span, response)
```

#### 追踪属性

| 属性 | 说明 |
|------|------|
| `gen_ai.operation.name` | 操作名称 |
| `gen_ai.agent.name` | Agent 名称 |
| `gen_ai.tool.name` | 工具名称 |
| `gen_ai.usage.input_tokens` | 输入 token 数 |
| `gen_ai.usage.output_tokens` | 输出 token 数 |

---

## 3. AWS Bedrock AgentCore

### 3.1 服务概览

| 服务 | 功能 | 用途 |
|------|------|------|
| **Runtime** | 安全隔离计算 | Agent 部署和执行 |
| **Memory** | 持久化记忆 | 短期/长期记忆存储 |
| **Gateway** | API 转 MCP 工具 | 外部服务集成 |
| **Identity** | 身份认证 | OAuth/API Key 管理 |
| **Code Interpreter** | 沙盒代码执行 | 安全执行代码 |
| **Browser** | 云端浏览器 | Web 自动化 |

### 3.2 Runtime 服务

Runtime 提供安全的 Agent 执行环境，支持 HTTP 和 WebSocket 协议。

#### 应用定义

```python
from bedrock_agentcore import BedrockAgentCoreApp

app = BedrockAgentCoreApp(debug=False)

@app.entrypoint
def my_agent(request, context):
    """Agent 入口点

    Args:
        request: 请求数据 (dict)
        context: 请求上下文 (RequestContext)
    """
    prompt = request.get("prompt")
    session_id = context.session_id

    # Agent 处理逻辑
    return {"response": "处理结果"}

# 启动服务
app.run(port=8080)
```

#### WebSocket 支持

```python
@app.websocket
async def ws_handler(websocket, context):
    await websocket.accept()

    async for message in websocket.iter_text():
        result = process_message(message)
        await websocket.send_text(result)
```

#### 客户端连接

```python
from bedrock_agentcore.runtime import AgentCoreRuntimeClient

client = AgentCoreRuntimeClient(region="us-west-2")

# SigV4 认证 (后端服务)
ws_url, headers = client.generate_ws_connection(
    runtime_arn="arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/my-runtime"
)

# Presigned URL (前端客户端)
presigned_url = client.generate_presigned_url(
    runtime_arn="...",
    expires=300  # 5分钟
)

# OAuth 认证
ws_url, headers = client.generate_ws_connection_oauth(
    runtime_arn="...",
    bearer_token="eyJhbGciOiJSUzI1NiIs..."
)
```

#### 健康检查和任务管理

```python
# 自定义健康检查
@app.ping
def custom_ping():
    if is_busy():
        return PingStatus.HEALTHY_BUSY
    return PingStatus.HEALTHY

# 异步任务装饰器
@app.async_task
async def long_running_task():
    # 自动设置状态为 HEALTHY_BUSY
    await do_work()
    # 完成后自动恢复为 HEALTHY
```

### 3.3 Memory 服务

Memory 提供分层记忆管理：短期记忆（对话事件）和长期记忆（语义检索）。

#### 架构层次

```
Memory (顶层容器)
├── Actor (用户/实体)
│   └── Session (对话上下文)
│       └── Events (对话事件)
│           └── Branches (分支对话)
└── Long-term Memory (语义记忆)
    └── Namespace (命名空间组织)
```

#### MemorySessionManager 用法

```python
from bedrock_agentcore.memory import MemorySessionManager
from bedrock_agentcore.memory.constants import ConversationalMessage, MessageRole

# 初始化
manager = MemorySessionManager(
    memory_id="my-memory-id",
    region_name="us-east-1"
)

# 创建 Session
session = manager.create_memory_session(
    actor_id="user-123",
    session_id="session-456"
)

# 添加对话
session.add_turns([
    ConversationalMessage("我需要分析安全告警", MessageRole.USER),
    ConversationalMessage("好的，让我帮您分析", MessageRole.ASSISTANT),
])

# 搜索长期记忆
memories = session.search_long_term_memories(
    query="之前的安全修复方案",
    namespace_prefix="/security/findings/user-123",
    top_k=5
)
```

#### LLM 集成模式

```python
from bedrock_agentcore.memory.constants import RetrievalConfig

def my_llm(user_input: str, memories: list) -> str:
    context = "\n".join([m.get('content', {}).get('text', '') for m in memories])
    # 调用你的 LLM
    return llm_response

# 配置检索
retrieval_config = {
    "security/findings/{sessionId}": RetrievalConfig(top_k=5, relevance_score=0.3),
    "user/preferences/{actorId}": RetrievalConfig(top_k=3, relevance_score=0.5)
}

# 自动检索+LLM处理+存储
memories, response, event = session.process_turn_with_llm(
    user_input="分析最新的安全告警",
    llm_callback=my_llm,
    retrieval_config=retrieval_config
)
```

#### 分支管理

```python
# Fork 对话分支
branch_event = session.fork_conversation(
    root_event_id="event-123",
    branch_name="alternative-fix",
    messages=[
        ConversationalMessage("尝试另一种修复方案", MessageRole.USER),
        ConversationalMessage("好的，让我提供替代方案", MessageRole.ASSISTANT)
    ]
)

# 列出所有分支
branches = session.list_branches()

# 获取特定分支事件
branch_events = session.list_events(branch_name="alternative-fix")
```

### 3.4 Gateway 服务

Gateway 将外部 API 转换为 MCP 工具，使 Agent 能够安全访问外部服务。

#### 核心概念

- **API Schema**: OpenAPI/Swagger 格式的 API 定义
- **Tool Transformation**: 自动将 API 端点转换为 MCP 工具
- **Authentication**: 支持 OAuth、API Key 等认证方式
- **Rate Limiting**: 内置流量控制

#### 典型工作流

1. 注册外部 API Schema 到 Gateway
2. 配置认证方式
3. Gateway 自动生成 MCP 工具
4. Agent 通过 MCP 协议调用工具
5. Gateway 转发请求到外部 API

### 3.5 Identity 服务

Identity 管理 Agent 访问外部服务的凭证。

#### 装饰器用法

```python
from bedrock_agentcore.identity import requires_access_token, requires_api_key

@tool
@requires_access_token(
    provider_name="github",
    scopes=["repo", "user"],
    auth_flow="USER_FEDERATION",
    into="access_token"
)
def create_github_issue(title: str, body: str, *, access_token: str):
    """创建 GitHub Issue"""
    import requests
    response = requests.post(
        "https://api.github.com/repos/owner/repo/issues",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"title": title, "body": body}
    )
    return response.json()

@tool
@requires_api_key(
    provider_name="openai",
    into="api_key"
)
def call_openai(prompt: str, *, api_key: str):
    """调用 OpenAI API"""
    # 使用 api_key 调用 OpenAI
    pass
```

#### IAM JWT 认证

```python
from bedrock_agentcore.identity import requires_iam_access_token

@tool
@requires_iam_access_token(
    audience=["https://api.example.com"],
    signing_algorithm="ES384",
    duration_seconds=300
)
def call_external_api(query: str, *, access_token: str):
    """使用 AWS 签名的 JWT 调用外部 API"""
    import requests
    response = requests.get(
        "https://api.example.com/data",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"q": query}
    )
    return response.text
```

### 3.6 可观测性

AgentCore 通过 OpenTelemetry 提供完整的可观测性支持。

#### CloudWatch 集成

- Agent 调用追踪
- Token 使用统计
- 工具调用指标
- 延迟和错误监控

#### 日志格式

```python
class RequestContextFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "requestId": BedrockAgentCoreContext.get_request_id(),
            "sessionId": BedrockAgentCoreContext.get_session_id(),
        }
        return json.dumps(log_entry)
```

### 3.7 Policy 服务 (Cedar)

Policy 使用 Cedar 策略语言控制 Agent 行为，实现细粒度的操作授权。

#### Cedar 策略语法

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

#### SHARA Policy 示例

```cedar
// 允许所有读取/分析操作
permit(
    principal,
    action in [
        AgentCore::Action::"SecurityHub___get_findings",
        AgentCore::Action::"S3Tools___get_bucket_policy",
        AgentCore::Action::"EC2Tools___describe_security_groups"
    ],
    resource
);

// 高风险修复操作需要审批
permit(
    principal,
    action in [
        AgentCore::Action::"S3Tools___put_bucket_policy",
        AgentCore::Action::"EC2Tools___revoke_security_group_ingress"
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
        AgentCore::Action::"EC2Tools___delete_security_group"
    ],
    resource
);

// 禁止修改生产环境关键资源
forbid(
    principal,
    action,
    resource
) when {
    resource.tags.environment == "production" &&
    resource.tags.critical == "true" &&
    context.emergency_override != true
};
```

#### 策略执行模式

| 模式 | 行为 | 适用场景 |
|------|------|----------|
| **ENFORCE** | 阻止违反策略的操作 | 生产环境 |
| **MONITOR** | 仅记录，不阻止 | 测试、策略验证 |

### 3.8 Code Interpreter 服务

Code Interpreter 提供安全的沙盒执行环境，让 Agent 可以动态生成并执行代码。

#### 功能特性

| 功能 | 描述 | SHARA 应用 |
|------|------|-----------|
| **沙盒隔离** | 每次执行在隔离容器中运行 | 安全执行修复代码 |
| **预装环境** | Python 3.x + boto3 等库 | 直接执行 AWS SDK 代码 |
| **执行超时** | 可配置时间限制 | 防止失控代码 |
| **输出捕获** | 捕获 stdout/stderr | 获取修复结果 |

#### 预定义工具 vs Code Interpreter

| 方案 | 预定义 Lambda 工具 | Code Interpreter |
|------|-------------------|------------------|
| **本质** | 工具调用（RPA 思维） | 代码生成（Agent 思维） |
| **灵活性** | 只能处理预定义场景 | 可处理任意场景 |
| **可扩展性** | 新场景需开发新 Lambda | LLM 自动适应 |
| **安全控制** | 简单（预定义操作） | 需要沙盒 + 人工审批 |

#### 在 Strands Agent 中使用

```python
from strands import Agent
from strands.tools import CodeInterpreterTool

code_interpreter = CodeInterpreterTool(
    timeout_seconds=300,
    sandbox_config={
        "memory_mb": 1024,
        "environment": {"AWS_REGION": "us-east-1"}
    }
)

agent = Agent(
    model=model,
    tools=[code_interpreter],
    system_prompt="""
    你是安全修复 Agent。
    需要修复 AWS 资源时，生成 Python/boto3 代码并使用 code_interpreter 执行。
    """
)
```

#### SHARA 执行流程

```
1. Remediator Agent 生成修复代码
         │
         ▼
2. 发送审批邮件（包含代码摘要）
         │
    ┌────┴────┐
    ▼         ▼
审批通过    审批拒绝
    │         │
    ▼         ▼
3. Code     记录原因
Interpreter
执行代码
    │
    ▼
4. Validator 验证结果
```

---

## 4. Strands + AgentCore 集成

### AgentCoreMemorySessionManager

这是 Strands 与 AgentCore Memory 的深度集成，提供：

- 对话历史自动同步到 AgentCore Memory
- Agent 初始化时加载历史
- 长期记忆的上下文注入
- 支持自定义检索配置

```python
from strands import Agent
from bedrock_agentcore.memory.integrations.strands import (
    AgentCoreMemorySessionManager,
    AgentCoreMemoryConfig,
    RetrievalConfig
)

# 配置
config = AgentCoreMemoryConfig(
    memory_id="shara-memory",
    actor_id="security-user-123",
    session_id="remediation-session",
    retrieval_config={
        # 检索安全发现上下文
        "security/findings/{actorId}": RetrievalConfig(top_k=10, relevance_score=0.4),
        # 检索历史修复方案
        "remediation/history/{sessionId}": RetrievalConfig(top_k=5, relevance_score=0.5)
    }
)

# 创建 Session Manager
session_manager = AgentCoreMemorySessionManager(
    agentcore_memory_config=config,
    region_name="us-east-1"
)

# 创建 Agent
agent = Agent(
    system_prompt="你是安全运维专家",
    tools=[analyze_finding, apply_remediation, validate_fix],
    session_manager=session_manager
)

# Agent 会自动:
# 1. 加载历史对话
# 2. 在用户消息时检索相关长期记忆
# 3. 将新对话同步到 Memory
result = agent("分析并修复这个安全告警")
```

### Hook 集成

```python
# AgentCoreMemorySessionManager 内部实现
def register_hooks(self, registry: HookRegistry, **kwargs):
    # 注册父类 hooks
    RepositorySessionManager.register_hooks(self, registry, **kwargs)

    # 添加长期记忆检索 hook
    registry.add_callback(
        MessageAddedEvent,
        lambda event: self.retrieve_customer_context(event)
    )

def retrieve_customer_context(self, event: MessageAddedEvent):
    """在处理用户消息前检索相关长期记忆"""
    messages = event.agent.messages

    # 只对用户消息检索
    if messages[-1].get("role") != "user":
        return

    user_query = messages[-1]["content"][0]["text"]

    # 并行检索所有命名空间
    all_context = []
    for namespace, config in self.config.retrieval_config.items():
        memories = self.memory_client.retrieve_memories(
            memory_id=self.config.memory_id,
            namespace=namespace.format(actorId=..., sessionId=...),
            query=user_query,
            top_k=config.top_k
        )
        all_context.extend([m.get('content', {}).get('text', '') for m in memories])

    # 注入上下文
    if all_context:
        context_text = "\n".join(all_context)
        event.agent.messages.append({
            "role": "assistant",
            "content": [{"text": f"<user_context>{context_text}</user_context>"}]
        })
```

---

## 5. SHARA 项目应用指南

### 推荐架构

```
┌─────────────────────────────────────────────────────────────┐
│                    AgentCore Runtime                         │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                  BedrockAgentCoreApp                   │  │
│  │  ┌─────────┐  ┌─────────────┐  ┌─────────────────┐   │  │
│  │  │Analyzer │→ │Remediator   │→ │Validator        │   │  │
│  │  │Agent    │  │Agent        │  │Agent            │   │  │
│  │  └────┬────┘  └──────┬──────┘  └────────┬────────┘   │  │
│  │       │              │                   │            │  │
│  │       └──────────────┼───────────────────┘            │  │
│  │                      ▼                                │  │
│  │       ┌──────────────────────────────┐               │  │
│  │       │ AgentCoreMemorySessionManager │               │  │
│  │       └──────────────┬───────────────┘               │  │
│  └──────────────────────┼────────────────────────────────┘  │
└─────────────────────────┼────────────────────────────────────┘
                          ▼
              ┌───────────────────────┐
              │   AgentCore Memory    │
              ├───────────────────────┤
              │ 短期记忆: 对话历史     │
              │ 长期记忆: ASR经验/方案 │
              └───────────────────────┘
```

### Memory 命名空间设计

```python
retrieval_config = {
    # ASR 经验库 - 按控制ID组织
    "asr/playbooks/{controlId}": RetrievalConfig(top_k=3, relevance_score=0.7),

    # 历史修复方案 - 按用户组织
    "remediation/history/{actorId}": RetrievalConfig(top_k=5, relevance_score=0.5),

    # 资源上下文 - 按会话组织
    "context/resources/{sessionId}": RetrievalConfig(top_k=10, relevance_score=0.4),
}
```

### Agent 工具定义

```python
from strands import tool

@tool
def fetch_asr_playbook(control_id: str, resource_type: str) -> dict:
    """获取 ASR 修复方案

    Args:
        control_id: Security Hub 控制 ID (如 S3.1, EC2.19)
        resource_type: AWS 资源类型

    Returns:
        包含分析和修复步骤的方案
    """
    # 从 S3 或 Memory 长期记忆获取
    pass

@tool
def apply_remediation(
    resource_arn: str,
    remediation_steps: list,
    dry_run: bool = True
) -> dict:
    """执行修复操作

    Args:
        resource_arn: 目标资源 ARN
        remediation_steps: 修复步骤列表
        dry_run: 是否仅模拟执行
    """
    pass

@tool
def validate_remediation(
    resource_arn: str,
    control_id: str
) -> dict:
    """验证修复结果

    Args:
        resource_arn: 资源 ARN
        control_id: 控制 ID

    Returns:
        验证结果和合规状态
    """
    pass
```

### 可观测性配置

```python
import os

# 配置 OpenTelemetry
os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "https://your-collector:4317"
os.environ["OTEL_SEMCONV_STABILITY_OPT_IN"] = "gen_ai_latest_experimental"

# Agent 自定义追踪属性
agent = Agent(
    custom_trace_attributes={
        "shara.finding_id": finding_id,
        "shara.control_id": control_id,
        "shara.resource_arn": resource_arn,
    }
)
```

### 最佳实践

1. **Session 管理**
   - 使用 AgentCoreMemorySessionManager 统一管理
   - 合理设计命名空间便于检索
   - 定期清理过期 Session

2. **Memory 使用**
   - 短期记忆用于对话上下文
   - 长期记忆存储 ASR 经验和历史方案
   - 使用 relevance_score 过滤低相关结果

3. **工具设计**
   - 每个工具职责单一
   - 提供详细的 docstring
   - 支持 dry_run 模式

4. **错误处理**
   - 使用 try-catch 包装 AWS API 调用
   - 实现重试逻辑
   - 记录详细日志

5. **可观测性**
   - 启用 OpenTelemetry 追踪
   - 添加自定义追踪属性
   - 监控 Token 使用和延迟

---

## 参考资料

- [Strands Agents 文档](https://strandsagents.com/)
- [AWS Bedrock AgentCore 文档](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/)
- [OpenTelemetry GenAI 语义约定](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/)
