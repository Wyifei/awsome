# Strands Agent Demo

基于 Strands Agent 框架的示例代码，用于测试和学习 Agent 开发。

## 环境准备

### 1. 安装依赖

```bash
cd /Users/yifeiwf/Code/awsome2/agent/code
pip install -r requirements.txt
```

### 2. 配置认证

支持两种认证方式：

**方式 1: Bearer Token (推荐用于本地开发)**

```bash
# 使用 aws-bedrock-token-generator 生成 token
pip install aws-bedrock-token-generator

# 生成并设置 token
export AWS_BEARER_TOKEN_BEDROCK=$(python -c "from aws_bedrock_token_generator import provide_token; print(provide_token())")

# 或者手动设置已有的 token
export AWS_BEARER_TOKEN_BEDROCK="your-token-here"
```

**方式 2: IAM 凭证**

```bash
# 使用 AWS CLI 配置
aws configure

# 或设置环境变量
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=ap-northeast-1
```

### 3. 诊断认证配置

```bash
# 运行诊断工具，检查认证状态
python auth_config.py
```

### 4. 模型配置 (可选)

```bash
# 默认配置 (ap-northeast-1 + APAC 跨区域)
export AWS_DEFAULT_REGION=ap-northeast-1
export BEDROCK_MODEL_ID=apac.anthropic.claude-sonnet-4-20250514-v1:0
```

**跨区域推理配置文件**：
- `apac.anthropic.xxx` - APAC 区域 (ap-northeast-1, ap-southeast-1)
- `us.anthropic.xxx` - US 区域 (us-east-1, us-west-2)
- `eu.anthropic.xxx` - EU 区域 (eu-west-1)

## 示例代码

### 1. simple_agent.py - 基础 Agent

最简单的 Agent 示例，无工具调用。

```bash
python simple_agent.py
```

功能：
- 创建基础 Agent
- 简单问答交互
- 展示 system_prompt 配置

### 2. agent_with_tools.py - 带工具的 Agent

展示如何定义和使用自定义工具。

```bash
python agent_with_tools.py
```

功能：
- 使用 `@tool` 装饰器定义工具
- S3 bucket 信息查询
- Security Group 规则查询
- IAM 用户列表查询
- 交互式对话

### 3. streaming_agent.py - 流式输出

展示异步流式输出。

```bash
python streaming_agent.py
```

功能：
- 异步 Agent 调用
- 流式响应输出
- 实时显示生成内容

### 4. shara_demo.py - SHARA 简化演示

模拟 SHARA 系统的多 Agent 协作流程。

```bash
python shara_demo.py
```

功能：
- 模拟 Security Finding 处理
- 动态代码生成
- 审批流程模拟
- 展示 Orchestrator 工作流

示例交互：
```
Security Admin: Show me all pending security findings
Security Admin: Analyze finding-001 and generate remediation
Security Admin: Process the highest severity finding
```

## 代码结构

```
code/
├── README.md              # 本文档
├── requirements.txt       # Python 依赖
├── auth_config.py         # 🔐 统一认证配置模块
├── simple_agent.py        # 基础 Agent 示例
├── agent_with_tools.py    # 带工具的 Agent
├── streaming_agent.py     # 流式输出示例
├── shara_demo.py          # SHARA 系统演示
└── agentcore_app.py       # 🚀 AgentCore Runtime 部署示例
```

## 认证架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         认证方式选择                                     │
│                                                                          │
│  ┌─────────────────────┐     ┌─────────────────────┐                   │
│  │    本地开发环境      │     │   AgentCore Runtime │                   │
│  │                     │     │                     │                   │
│  │  ┌───────────────┐  │     │  ┌───────────────┐  │                   │
│  │  │ Bearer Token  │  │     │  │  IAM Role     │  │                   │
│  │  │ (优先)        │  │     │  │  (自动提供)   │  │                   │
│  │  └───────────────┘  │     │  └───────────────┘  │                   │
│  │         │           │     │         │           │                   │
│  │         ▼           │     │         ▼           │                   │
│  │  ┌───────────────┐  │     │  临时凭证自动注入   │                   │
│  │  │ IAM 凭证      │  │     │  到环境变量         │                   │
│  │  │ (备选)        │  │     │                     │                   │
│  │  └───────────────┘  │     │                     │                   │
│  └─────────────────────┘     └─────────────────────┘                   │
│                                                                          │
│  使用: auth_config.py        使用: agentcore_app.py                    │
└─────────────────────────────────────────────────────────────────────────┘
```

### auth_config.py - 统一认证模块

```python
from auth_config import create_model, diagnose_auth

# 诊断认证配置
diagnose_auth()

# 创建已认证的模型 (自动选择最佳认证方式)
model = create_model()
agent = Agent(model=model, ...)
```

### agentcore_app.py - AgentCore 部署

```bash
# 查看认证流程图
python agentcore_app.py --auth-flow

# 本地测试
python agentcore_app.py

# 部署到 AgentCore (需要安装 starter-toolkit)
python agentcore_app.py --deploy
```

## 注意事项

1. **模型费用**: 调用 Bedrock Claude 模型会产生费用
2. **权限要求**: agent_with_tools.py 需要 S3/EC2/IAM 读取权限
3. **模拟数据**: shara_demo.py 使用模拟数据，不会修改真实资源

## 常见问题

### Q: 提示 "Could not find model"
确保已在 Bedrock Console 申请模型访问权限。

### Q: 提示 "Access Denied"
检查 IAM 权限是否包含 `bedrock:InvokeModel`。

### Q: 工具调用失败
检查是否有对应 AWS 服务的读取权限。
