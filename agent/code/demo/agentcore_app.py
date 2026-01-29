#!/usr/bin/env python3
"""
AgentCore Runtime 应用示例

展示如何创建可部署到 AgentCore Runtime 的 Agent 应用

部署方式:
1. 使用 Starter Toolkit CLI:
   agentcore launch .

2. 使用 Python SDK:
   见 deploy_to_agentcore() 函数

认证说明:
- 在 AgentCore Runtime 中，IAM Role 由 Runtime 自动提供
- 无需手动配置凭证，Runtime 会注入临时凭证到环境
"""

import os
import logging
from strands import Agent
from strands.models import BedrockModel

# 尝试导入 AgentCore SDK
try:
    from bedrock_agentcore import BedrockAgentCoreApp
    AGENTCORE_AVAILABLE = True
except ImportError:
    AGENTCORE_AVAILABLE = False
    print("Warning: bedrock-agentcore not installed. Install with: pip install bedrock-agentcore")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================
# 配置
# ============================================

# AgentCore Runtime 会自动设置这些环境变量
REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "apac.anthropic.claude-sonnet-4-20250514-v1:0")


# ============================================
# Agent 定义
# ============================================

def create_agent() -> Agent:
    """
    创建 Agent

    在 AgentCore Runtime 中:
    - Runtime 自动提供 IAM Role 临时凭证
    - 凭证通过 AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN 注入
    - boto3 自动从环境变量获取凭证
    """
    logger.info(f"Creating agent with model={MODEL_ID}, region={REGION}")

    # BedrockModel 会自动使用环境中的 AWS 凭证
    # 在 AgentCore Runtime 中，这些凭证来自 Runtime 的 IAM Role
    model = BedrockModel(
        model_id=MODEL_ID,
        region_name=REGION,
        temperature=0.3,
        max_tokens=4096
    )

    agent = Agent(
        model=model,
        system_prompt="""
        You are a helpful AWS security assistant deployed on AgentCore Runtime.
        You help users understand and fix AWS security issues.
        Be concise and actionable in your responses.
        """
    )

    return agent


# ============================================
# AgentCore Runtime 入口点
# ============================================

if AGENTCORE_AVAILABLE:
    # 创建 AgentCore 应用
    app = BedrockAgentCoreApp()

    # Agent 实例 (延迟初始化)
    _agent = None

    def get_agent() -> Agent:
        """获取或创建 Agent 实例"""
        global _agent
        if _agent is None:
            _agent = create_agent()
        return _agent

    @app.entrypoint
    async def handler(payload: dict, context: dict):
        """
        AgentCore Runtime 入口点

        Args:
            payload: 请求数据，包含:
                - prompt: 用户输入
                - session_id: 会话 ID
                - finding: (可选) Security Hub Finding 数据
            context: Runtime 上下文，包含:
                - runtime_id: Runtime ID
                - session_id: 会话 ID
                - invocation_id: 调用 ID

        Yields:
            流式响应事件
        """
        logger.info(f"Received request: {payload}")

        # 获取 Agent
        agent = get_agent()

        # 获取用户输入
        prompt = payload.get("prompt", "")
        if not prompt:
            yield {"error": "No prompt provided"}
            return

        # 流式调用 Agent
        try:
            async for event in agent.stream_async(prompt):
                yield event
        except Exception as e:
            logger.error(f"Agent error: {e}")
            yield {"error": str(e)}


# ============================================
# 本地测试
# ============================================

def local_test():
    """本地测试 Agent"""
    print("=" * 60)
    print("AgentCore App - Local Test")
    print("=" * 60)

    print(f"\nEnvironment:")
    print(f"  Region: {REGION}")
    print(f"  Model: {MODEL_ID}")
    print(f"  AgentCore SDK: {'Available' if AGENTCORE_AVAILABLE else 'Not installed'}")

    print("\nCreating agent...")
    agent = create_agent()
    print("Agent created successfully!")

    # 测试调用
    test_prompt = "What is AWS Security Hub?"
    print(f"\nTest prompt: {test_prompt}")
    print("-" * 40)

    response = agent(test_prompt)
    print(f"Response: {response}")


# ============================================
# 部署到 AgentCore
# ============================================

def deploy_to_agentcore():
    """
    部署 Agent 到 AgentCore Runtime (示例代码)

    实际部署时需要:
    1. 配置 IAM Role，包含 bedrock:InvokeModel 权限
    2. 使用 agentcore CLI 或 SDK 部署
    """
    try:
        from bedrock_agentcore_starter_toolkit.operations.runtime.client import RuntimeClient
    except ImportError:
        print("Please install: pip install bedrock-agentcore-starter-toolkit")
        return

    print("Deploying to AgentCore Runtime...")

    client = RuntimeClient(region_name=REGION)

    # 创建 Runtime
    runtime = client.create_runtime(
        name="shara-security-agent",
        agent_code_path=".",  # 当前目录
        framework="strands",
        memory_size=2048,
        timeout_seconds=900,
        # IAM Role 会自动创建，包含 Bedrock 访问权限
    )

    print(f"Runtime created:")
    print(f"  Runtime ID: {runtime['runtimeId']}")
    print(f"  Endpoint: {runtime['endpointUrl']}")

    return runtime


# ============================================
# 认证流程说明
# ============================================

AUTH_FLOW_DIAGRAM = """
AgentCore Runtime 认证流程:

┌─────────────────────────────────────────────────────────────────────────┐
│                    AgentCore Runtime 部署                                │
│                                                                          │
│  1. 部署时配置                                                           │
│     ┌─────────────────────────────────────────────────────────────────┐ │
│     │  agentcore launch shara-agent                                    │ │
│     │                                                                  │ │
│     │  自动创建:                                                       │ │
│     │  - Lambda 函数 (运行 Agent 代码)                                 │ │
│     │  - IAM Role (包含 Bedrock 权限)                                  │ │
│     │  - API Gateway (接收请求)                                        │ │
│     └─────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  2. 运行时认证                                                           │
│     ┌─────────────────────────────────────────────────────────────────┐ │
│     │  请求到达                                                        │ │
│     │       │                                                          │ │
│     │       ▼                                                          │ │
│     │  Lambda 执行环境                                                 │ │
│     │  ┌─────────────────────────────────────────────────────────┐   │ │
│     │  │ 环境变量 (由 Runtime 自动注入):                          │   │ │
│     │  │   AWS_ACCESS_KEY_ID=ASIA...                             │   │ │
│     │  │   AWS_SECRET_ACCESS_KEY=xxx                             │   │ │
│     │  │   AWS_SESSION_TOKEN=xxx  (临时凭证)                     │   │ │
│     │  │   AWS_REGION=ap-northeast-1                             │   │ │
│     │  └─────────────────────────────────────────────────────────┘   │ │
│     │       │                                                          │ │
│     │       ▼                                                          │ │
│     │  Agent 代码                                                      │ │
│     │  ┌─────────────────────────────────────────────────────────┐   │ │
│     │  │ model = BedrockModel(model_id=..., region_name=...)     │   │ │
│     │  │                                                          │   │ │
│     │  │ # boto3 自动从环境变量获取凭证                           │   │ │
│     │  │ # 无需任何额外认证配置!                                  │   │ │
│     │  └─────────────────────────────────────────────────────────┘   │ │
│     │       │                                                          │ │
│     │       ▼                                                          │ │
│     │  Bedrock API 调用                                                │ │
│     │  ┌─────────────────────────────────────────────────────────┐   │ │
│     │  │ POST bedrock-runtime.ap-northeast-1.amazonaws.com       │   │ │
│     │  │ Authorization: AWS4-HMAC-SHA256 ... (自动 SigV4 签名)   │   │ │
│     │  └─────────────────────────────────────────────────────────┘   │ │
│     └─────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  3. IAM Role 权限配置                                                    │
│     ┌─────────────────────────────────────────────────────────────────┐ │
│     │  {                                                               │ │
│     │    "Version": "2012-10-17",                                     │ │
│     │    "Statement": [                                                │ │
│     │      {                                                           │ │
│     │        "Effect": "Allow",                                        │ │
│     │        "Action": [                                               │ │
│     │          "bedrock:InvokeModel",                                  │ │
│     │          "bedrock:InvokeModelWithResponseStream"                 │ │
│     │        ],                                                        │ │
│     │        "Resource": "*"                                           │ │
│     │      }                                                           │ │
│     │    ]                                                             │ │
│     │  }                                                               │ │
│     └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘

本地开发 vs AgentCore Runtime:

┌─────────────────────────────────┬─────────────────────────────────────┐
│         本地开发                 │         AgentCore Runtime           │
├─────────────────────────────────┼─────────────────────────────────────┤
│ 凭证来源:                        │ 凭证来源:                           │
│ - ~/.aws/credentials            │ - Runtime IAM Role (自动)           │
│ - 环境变量                       │ - 临时凭证 (自动轮换)               │
│ - Bearer Token                   │                                     │
├─────────────────────────────────┼─────────────────────────────────────┤
│ 配置方式:                        │ 配置方式:                           │
│ - 手动配置                       │ - 自动配置                          │
│ - auth_config.py                │ - 无需额外代码                      │
├─────────────────────────────────┼─────────────────────────────────────┤
│ 代码:                            │ 代码:                               │
│ from auth_config import          │ model = BedrockModel(...)           │
│     create_model                 │ # 就这么简单！                      │
│ model = create_model()           │                                     │
└─────────────────────────────────┴─────────────────────────────────────┘
"""


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--deploy":
        deploy_to_agentcore()
    elif len(sys.argv) > 1 and sys.argv[1] == "--auth-flow":
        print(AUTH_FLOW_DIAGRAM)
    else:
        local_test()
