# SHARA AWS 基础设施架构

> **SHARA**: Security Hub Auto-Remediation Agent

## 1. 整体架构概览

SHARA 是一个基于 AWS Bedrock AgentCore 的安全自动修复智能体系统，采用事件驱动架构，通过两阶段审批流程实现 Security Hub 发现的自动修复。

## 2. AWS 服务组件

### 2.1 事件驱动层

| 服务 | 用途 | 配置 |
|------|------|------|
| **Amazon EventBridge** | 接收 Security Hub 事件 | 规则过滤 HIGH/CRITICAL 级别 Finding |
| **AWS Security Hub** | 安全发现来源 | FSBP 控制项检测 |

### 2.2 计算层

| 服务 | 组件 | 用途 |
|------|------|------|
| **AWS Lambda** | Event Handler | Phase 1 入口，接收事件并调用 Analyzer |
| **AWS Lambda** | Approval Handler | Phase 2 入口，处理审批/回滚请求 |
| **AWS Lambda** | Result Email Handler | 发送结果邮件 |
| **Bedrock AgentCore Runtime** | Analyzer Agent | 分析 Finding，生成修复方案 |
| **Bedrock AgentCore Runtime** | Remediator Agent | 生成并执行修复代码 |
| **Bedrock AgentCore Runtime** | Validator Agent | 验证修复结果，保存经验 |
| **Bedrock AgentCore Code Interpreter** | 代码沙盒 | 隔离执行修复/回滚代码 |

### 2.3 AI/ML 层

| 服务 | 用途 | 模型 |
|------|------|------|
| **Amazon Bedrock** | LLM 推理 | Claude Opus 4.5 |
| **Bedrock AgentCore Memory** | STM - 短期记忆 | 任务内数据共享 |
| **Bedrock AgentCore Memory** | LTM - 长期记忆 | 跨任务经验积累 |

### 2.4 存储层

| 服务 | 用途 | 数据 |
|------|------|------|
| **Amazon DynamoDB** | Tasks 表 | 任务状态管理 |
| **Amazon DynamoDB** | Tokens 表 | 审批/回滚 Token |
| **Amazon S3** | ASR Playbooks | 预定义修复方案 |
| **Amazon S3** | Audit Logs | 执行审计日志 |

### 2.5 网络与 API 层

| 服务 | 用途 | 端点 |
|------|------|------|
| **Amazon API Gateway** | REST API | /approvals/{taskId}/respond |
| **Amazon VPC** | 网络隔离 | Lambda 私有子网部署 |
| **NAT Gateway** | 出站访问 | Lambda 访问 AWS 服务 |

### 2.6 通知层

| 服务 | 用途 | 类型 |
|------|------|------|
| **Amazon SES** | 审批邮件 | HTML 格式，含审批链接 |
| **Amazon SES** | 结果邮件 | HTML 格式，含回滚链接 |

### 2.7 安全与身份

| 服务 | 用途 |
|------|------|
| **AWS IAM** | Lambda 执行角色 |
| **AWS IAM** | Code Interpreter 执行角色 |
| **AWS KMS** | DynamoDB 加密 |

### 2.8 可观测性

| 服务 | 用途 |
|------|------|
| **Amazon CloudWatch Logs** | Lambda 日志 |
| **Amazon CloudWatch Logs** | Agent 执行日志 |
| **Amazon CloudWatch Metrics** | 自定义指标 |

## 3. 架构流程

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AWS Cloud                                       │
│                                                                             │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐                │
│  │ Security Hub │────▶│ EventBridge  │────▶│    Lambda    │                │
│  │   Finding    │     │     Rule     │     │Event Handler │                │
│  └──────────────┘     └──────────────┘     └──────┬───────┘                │
│                                                   │                         │
│                       ┌───────────────────────────┼───────────────────────┐ │
│                       │    Bedrock AgentCore      │                       │ │
│                       │                           ▼                       │ │
│                       │  ┌─────────────────────────────────────────────┐  │ │
│                       │  │              Agent Runtime                  │  │ │
│                       │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐    │  │ │
│                       │  │  │ Analyzer │ │Remediator│ │Validator │    │  │ │
│                       │  │  └────┬─────┘ └────┬─────┘ └────┬─────┘    │  │ │
│                       │  │       │            │ A2A        │          │  │ │
│                       │  └───────┼────────────┼────────────┼──────────┘  │ │
│                       │          │            │            │             │ │
│                       │          ▼            ▼            ▼             │ │
│                       │  ┌─────────────────────────────────────────────┐ │ │
│                       │  │               Memory                        │ │ │
│                       │  │  ┌──────────────┐  ┌──────────────┐        │ │ │
│                       │  │  │     STM      │  │     LTM      │        │ │ │
│                       │  │  │ (Session)    │  │ (Experience) │        │ │ │
│                       │  │  └──────────────┘  └──────────────┘        │ │ │
│                       │  └─────────────────────────────────────────────┘ │ │
│                       │                                                   │ │
│                       │  ┌─────────────────────────────────────────────┐ │ │
│                       │  │           Code Interpreter                  │ │ │
│                       │  │  (Sandboxed Python Execution)               │ │ │
│                       │  └─────────────────────────────────────────────┘ │ │
│                       └───────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐                │
│  │  API Gateway │◀────│    Lambda    │     │     SES      │                │
│  │  /approvals  │     │  Approval    │────▶│   Emails     │                │
│  └──────────────┘     │   Handler    │     └──────────────┘                │
│         ▲             └──────────────┘                                      │
│         │                                                                   │
│  ┌──────┴───────┐                                                          │
│  │    User      │     ┌──────────────┐     ┌──────────────┐                │
│  │  (Browser)   │     │   DynamoDB   │     │      S3      │                │
│  └──────────────┘     │  Tasks/Tokens│     │ ASR Playbooks│                │
│                       └──────────────┘     └──────────────┘                │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                            VPC                                       │   │
│  │  ┌───────────────────┐     ┌───────────────────┐                    │   │
│  │  │   Private Subnet  │     │   Public Subnet   │                    │   │
│  │  │   (Lambda)        │────▶│   (NAT Gateway)   │────▶ Internet      │   │
│  │  └───────────────────┘     └───────────────────┘                    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 4. 数据流向

### 4.1 Phase 1: 分析流程

```
Security Hub → EventBridge → Lambda (Event Handler) → AgentCore Runtime (Analyzer)
                                    │                         │
                                    ▼                         ▼
                               DynamoDB                  Memory (STM)
                              (创建任务)              (保存分析结果)
                                    │                         │
                                    ▼                         ▼
                                  SES ◀─────────────── S3 (ASR Playbook)
                             (审批邮件)              (获取修复方案)
```

### 4.2 Phase 2: 修复流程

```
User (Browser) → API Gateway → Lambda (Approval Handler) → AgentCore Runtime (Remediator)
                                       │                           │
                                       ▼                           ▼
                                  DynamoDB                   Code Interpreter
                               (验证 Token)               (执行修复代码)
                                       │                           │
                                       │                           ▼
                                       │                    Memory (STM)
                                       │               (保存执行结果)
                                       │                           │
                                       │                           ▼ A2A
                                       │                 AgentCore Runtime (Validator)
                                       │                           │
                                       ▼                           ▼
                                     SES ◀─────────────── Memory (LTM)
                                (结果邮件)             (保存修复经验)
```

## 5. 资源命名规范

| 资源类型 | 命名模式 | 示例 |
|----------|----------|------|
| Lambda | shara-{stage}-{function} | shara-dev-event-handler |
| DynamoDB | shara-{stage}-{table} | shara-dev-tasks |
| S3 | shara-{stage}-{purpose}-{account} | shara-dev-asr-playbooks-123456789 |
| API Gateway | shara-{stage}-api | shara-dev-api |
| VPC | shara-{stage}-vpc | shara-dev-vpc |

## 6. 环境变量配置

### Lambda 环境变量

```bash
# DynamoDB
TASKS_TABLE=shara-{stage}-tasks
TOKENS_TABLE=shara-{stage}-approval-tokens

# S3
ASR_PLAYBOOKS_BUCKET=shara-{stage}-asr-playbooks-{accountId}
REMEDIATION_AUDIT_BUCKET=shara-{stage}-remediation-audit-{accountId}

# AgentCore (控制台配置后获取)
AGENTCORE_MEMORY_ID=memory-xxx
CODE_INTERPRETER_ID=interpreter-xxx
ANALYZER_RUNTIME_ARN=arn:aws:bedrock-agentcore:...
REMEDIATOR_RUNTIME_ARN=arn:aws:bedrock-agentcore:...
VALIDATOR_RUNTIME_ARN=arn:aws:bedrock-agentcore:...

# Email
APPROVAL_EMAIL=admin@example.com
SENDER_EMAIL=shara@example.com
APPROVAL_EXPIRY_HOURS=24

# API
API_GATEWAY_URL=https://api-id.execute-api.{region}.amazonaws.com/{stage}/
```

## 7. 基础设施即代码 (Terraform)

### 目录结构

```
infra/
├── main.tf                 # Provider 配置
├── vpc.tf                  # VPC, Subnet, NAT Gateway
├── storage.tf              # DynamoDB, S3
├── lambda.tf               # Lambda Functions
├── api_gateway.tf          # API Gateway
├── eventbridge.tf          # EventBridge Rule
├── iam.tf                  # IAM Roles & Policies
├── ecr.tf                  # ECR Repository (Agent 镜像)
└── code_interpreter.tf     # Code Interpreter IAM
```

### 手动配置项

以下资源需要在 AWS 控制台配置：

1. **Bedrock AgentCore Runtime** - 部署三个 Agent
2. **Bedrock AgentCore Memory** - 创建 Memory 资源
3. **Bedrock AgentCore Code Interpreter** - 创建执行环境
4. **SES 邮箱验证** - 验证发送/接收邮箱
5. **S3 ASR Playbook** - 上传 Playbook 文件
