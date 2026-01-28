# Security Hub Auto-Remediation Agent 架构设计文档

## 1. 架构概述

### 1.1 设计原则

| 原则 | 说明 |
|------|------|
| **事件驱动** | 基于 EventBridge 的异步事件处理架构 |
| **松耦合** | 各组件通过消息/事件通信，独立部署和扩展 |
| **最小权限** | 每个组件仅拥有必要的 IAM 权限 |
| **可观测性** | 全链路日志、指标、追踪 |
| **故障隔离** | 单个 Finding 处理失败不影响其他任务 |

### 1.2 高层架构图

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│                                   AWS Cloud                                         │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                          Security Services Layer                             │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │   │
│  │  │  Config  │ │GuardDuty │ │Inspector │ │  Macie   │ │IAM Anlzr │          │   │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘          │   │
│  │       └────────────┴────────────┼────────────┴────────────┘                │   │
│  │                                 ▼                                           │   │
│  │                    ┌────────────────────────┐                               │   │
│  │                    │    Security Hub        │                               │   │
│  │                    │  (Finding Aggregator)  │                               │   │
│  │                    └───────────┬────────────┘                               │   │
│  └────────────────────────────────┼────────────────────────────────────────────┘   │
│                                   │                                                 │
│  ┌────────────────────────────────┼────────────────────────────────────────────┐   │
│  │                     Event Processing Layer                                   │   │
│  │                                ▼                                             │   │
│  │           ┌────────────────────────────────────┐                            │   │
│  │           │         Amazon EventBridge         │                            │   │
│  │           │  Rule: severity IN [HIGH,CRITICAL] │                            │   │
│  │           └─────────────────┬──────────────────┘                            │   │
│  │                             │                                                │   │
│  │                             ▼                                                │   │
│  │           ┌────────────────────────────────────┐                            │   │
│  │           │      Lambda: Event Processor       │                            │   │
│  │           │  - Validate & Enrich Finding       │                            │   │
│  │           │  - Deduplicate                     │                            │   │
│  │           │  - Invoke Agent                    │                            │   │
│  │           └─────────────────┬──────────────────┘                            │   │
│  └─────────────────────────────┼───────────────────────────────────────────────┘   │
│                                │                                                    │
│  ┌─────────────────────────────┼───────────────────────────────────────────────┐   │
│  │                    Agent Layer (AgentCore + Strands)                         │   │
│  │                             ▼                                                │   │
│  │  ┌──────────────────────────────────────────────────────────────────────┐   │   │
│  │  │                     Orchestrator Agent                                │   │   │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                   │   │   │
│  │  │  │   Router    │  │   Planner   │  │   Monitor   │                   │   │   │
│  │  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                   │   │   │
│  │  └─────────┼────────────────┼────────────────┼──────────────────────────┘   │   │
│  │            │                │                │                               │   │
│  │            ▼                ▼                ▼                               │   │
│  │  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐               │   │
│  │  │  Analyzer Agent │ │ Remediator Agent│ │ Validator Agent │               │   │
│  │  │                 │ │                 │ │                 │               │   │
│  │  │ - Parse Finding │ │ - Gen Solution  │ │ - Verify Fix    │               │   │
│  │  │ - Get Context   │ │ - Gen Code      │ │ - Run Tests     │               │   │
│  │  │ - Risk Assess   │ │ - Execute Fix   │ │ - Update Status │               │   │
│  │  └────────┬────────┘ └────────┬────────┘ └────────┬────────┘               │   │
│  │           │                   │                   │                         │   │
│  │           └───────────────────┴───────────────────┘                         │   │
│  │                               │                                              │   │
│  │  ┌────────────────────────────┴─────────────────────────────────────────┐   │   │
│  │  │                        Shared Services                                │   │   │
│  │  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────┐  │   │   │
│  │  │  │ Tool Registry│ │Knowledge Base│ │ State Store  │ │ LLM Client  │  │   │   │
│  │  │  │  (AWS APIs)  │ │ (Playbooks)  │ │ (DynamoDB)   │ │ (Bedrock)   │  │   │   │
│  │  │  └──────────────┘ └──────────────┘ └──────────────┘ └─────────────┘  │   │   │
│  │  └──────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         Approval & Execution Layer                           │   │
│  │                                                                               │   │
│  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │   │
│  │  │  Amazon SES  │───▶│ Admin Email  │───▶│ API Gateway  │                   │   │
│  │  │  (Notify)    │    │ (Review)     │    │ (Callback)   │                   │   │
│  │  └──────────────┘    └──────────────┘    └───────┬──────┘                   │   │
│  │                                                   │                          │   │
│  │                                                   ▼                          │   │
│  │                                          ┌──────────────┐                   │   │
│  │                                          │   Lambda:    │                   │   │
│  │                                          │  Approval    │                   │   │
│  │                                          │  Handler     │                   │   │
│  │                                          └──────────────┘                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                           Data & Storage Layer                               │   │
│  │                                                                               │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │   │
│  │  │  DynamoDB    │  │     S3       │  │  Secrets     │  │  Parameter   │     │   │
│  │  │ - Tasks      │  │ - Playbooks  │  │  Manager     │  │   Store      │     │   │
│  │  │ - Approvals  │  │ - Templates  │  │ - API Keys   │  │ - Configs    │     │   │
│  │  │ - Audit Log  │  │ - Reports    │  └──────────────┘  └──────────────┘     │   │
│  │  └──────────────┘  └──────────────┘                                          │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         Observability Layer                                  │   │
│  │                                                                               │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │   │
│  │  │  CloudWatch  │  │  CloudWatch  │  │   X-Ray      │  │  CloudTrail  │     │   │
│  │  │    Logs      │  │   Metrics    │  │   Tracing    │  │    Audit     │     │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘     │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 组件详细设计

### 2.1 Event Processing Layer

#### 2.1.1 EventBridge Rule

```json
{
  "source": ["aws.securityhub"],
  "detail-type": ["Security Hub Findings - Imported"],
  "detail": {
    "findings": {
      "Severity": {
        "Label": ["HIGH", "CRITICAL"]
      },
      "Workflow": {
        "Status": ["NEW"]
      },
      "RecordState": ["ACTIVE"]
    }
  }
}
```

#### 2.1.2 Event Processor Lambda

**职责：**
- 验证 Finding 格式
- 去重处理（检查是否已处理）
- 丰富 Finding 上下文
- 调用 Agent 系统

**伪代码：**
```python
def handler(event, context):
    findings = event['detail']['findings']

    for finding in findings:
        # 1. 去重检查
        if is_duplicate(finding['Id']):
            continue

        # 2. 丰富上下文
        enriched = enrich_finding(finding)

        # 3. 创建任务记录
        task_id = create_task(enriched)

        # 4. 异步调用 Agent
        invoke_agent_async(task_id, enriched)

    return {'statusCode': 200}
```

### 2.2 Agent Layer

#### 2.2.1 Agent 通信模式

```
┌─────────────────────────────────────────────────────────────────┐
│                    Agent Communication Flow                      │
│                                                                  │
│   Event Processor                                                │
│         │                                                        │
│         ▼                                                        │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│   │Orchestrator │────▶│  Analyzer   │────▶│ Remediator  │       │
│   │   Agent     │     │   Agent     │     │   Agent     │       │
│   └──────┬──────┘     └─────────────┘     └──────┬──────┘       │
│          │                                        │              │
│          │         ┌─────────────┐               │              │
│          └────────▶│  Validator  │◀──────────────┘              │
│                    │   Agent     │                               │
│                    └─────────────┘                               │
│                                                                  │
│   Communication: Direct invocation via Strands Agent SDK        │
│   State Sharing: DynamoDB (task context)                        │
│   Message Format: Structured JSON with ASFF extensions          │
└─────────────────────────────────────────────────────────────────┘
```

#### 2.2.2 Orchestrator Agent

**核心职责：**
- 接收处理请求
- 规划执行步骤
- 协调子 Agent 执行
- 管理整体状态

**状态机：**
```
                    ┌─────────┐
                    │ CREATED │
                    └────┬────┘
                         │
                         ▼
                    ┌─────────┐
              ┌─────│ANALYZING│─────┐
              │     └────┬────┘     │
              │          │          │
              │ (error)  │(success) │(skip)
              │          ▼          │
              │     ┌─────────┐     │
              │     │PLANNING │     │
              │     └────┬────┘     │
              │          │          │
              │          ▼          │
              │     ┌─────────┐     │
              │     │PENDING_ │     │
              │     │APPROVAL │     │
              │     └────┬────┘     │
              │          │          │
              │  ┌───────┼───────┐  │
              │  │       │       │  │
              │  ▼       ▼       ▼  │
              │┌────┐ ┌─────┐ ┌────┐│
              ││APPR│ │REJEC│ │TIME││
              ││OVED│ │TED  │ │OUT ││
              │└──┬─┘ └──┬──┘ └──┬─┘│
              │   │      │      │   │
              │   ▼      │      │   │
              │┌─────────┐      │   │
              ││EXECUTING│      │   │
              │└────┬────┘      │   │
              │     │           │   │
              │  ┌──┴──┐        │   │
              │  ▼     ▼        │   │
              │┌────┐┌────┐     │   │
              ││DONE││FAIL│     │   │
              │└────┘└──┬─┘     │   │
              │         │       │   │
              └─────────┴───────┴───┘
                        │
                        ▼
                   ┌─────────┐
                   │COMPLETED│
                   └─────────┘
```

#### 2.2.3 Analyzer Agent

**核心职责：**
- 解析 Finding 结构
- 收集相关资源上下文
- 评估安全风险
- 确定修复优先级

**工具集：**
```python
ANALYZER_TOOLS = [
    # 资源信息获取
    "ec2:DescribeInstances",
    "ec2:DescribeSecurityGroups",
    "s3:GetBucketPolicy",
    "s3:GetBucketAcl",
    "iam:GetRole",
    "iam:GetPolicy",
    "rds:DescribeDBInstances",

    # Security Hub 操作
    "securityhub:GetFindings",
    "securityhub:BatchGetSecurityControls",

    # 配置检查
    "config:GetResourceConfigHistory",
    "config:GetComplianceDetailsByResource",
]
```

#### 2.2.4 Remediator Agent

**核心职责：**
- 查询修复知识库
- 生成修复方案
- 生成可执行代码
- 执行修复操作

**工具集：**
```python
REMEDIATOR_TOOLS = [
    # S3 修复
    "s3:PutBucketPolicy",
    "s3:PutPublicAccessBlock",
    "s3:PutBucketEncryption",

    # EC2/网络修复
    "ec2:AuthorizeSecurityGroupIngress",
    "ec2:RevokeSecurityGroupIngress",
    "ec2:ModifyInstanceAttribute",

    # IAM 修复
    "iam:UpdateAssumeRolePolicy",
    "iam:PutRolePolicy",
    "iam:DeleteRolePolicy",

    # 加密修复
    "kms:CreateKey",
    "kms:EnableKeyRotation",

    # Security Hub 更新
    "securityhub:BatchUpdateFindings",
]
```

#### 2.2.5 Validator Agent

**核心职责：**
- 验证修复效果
- 运行合规检查
- 更新 Finding 状态

---

## 3. 数据流详细设计

### 3.1 Finding 处理流程

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         Finding Processing Flow                               │
│                                                                               │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    │
│  │Security │    │Event    │    │Lambda   │    │DynamoDB │    │Agent    │    │
│  │Hub      │    │Bridge   │    │Processor│    │         │    │System   │    │
│  └────┬────┘    └────┬────┘    └────┬────┘    └────┬────┘    └────┬────┘    │
│       │              │              │              │              │          │
│       │ 1.Publish    │              │              │              │          │
│       │─────────────▶│              │              │              │          │
│       │              │              │              │              │          │
│       │              │ 2.Trigger    │              │              │          │
│       │              │─────────────▶│              │              │          │
│       │              │              │              │              │          │
│       │              │              │ 3.Check Dup  │              │          │
│       │              │              │─────────────▶│              │          │
│       │              │              │◀─────────────│              │          │
│       │              │              │              │              │          │
│       │              │              │ 4.Create Task│              │          │
│       │              │              │─────────────▶│              │          │
│       │              │              │              │              │          │
│       │              │              │ 5.Invoke     │              │          │
│       │              │              │─────────────────────────────▶          │
│       │              │              │              │              │          │
│       │              │              │              │ 6.Process    │          │
│       │              │              │              │◀─────────────│          │
│       │              │              │              │─────────────▶│          │
│       │              │              │              │              │          │
│  └────┴────┘    └────┴────┘    └────┴────┘    └────┴────┘    └────┴────┘    │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 审批流程

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           Approval Flow                                       │
│                                                                               │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    │
│  │Agent    │    │SES      │    │Admin    │    │API GW   │    │Lambda   │    │
│  │System   │    │         │    │         │    │         │    │Approval │    │
│  └────┬────┘    └────┬────┘    └────┬────┘    └────┬────┘    └────┬────┘    │
│       │              │              │              │              │          │
│       │ 1.Send Email │              │              │              │          │
│       │─────────────▶│              │              │              │          │
│       │              │              │              │              │          │
│       │              │ 2.Deliver    │              │              │          │
│       │              │─────────────▶│              │              │          │
│       │              │              │              │              │          │
│       │              │              │ 3.Review     │              │          │
│       │              │              │─────────────▶│              │          │
│       │              │              │ (Click Link) │              │          │
│       │              │              │              │              │          │
│       │              │              │              │ 4.Callback   │          │
│       │              │              │              │─────────────▶│          │
│       │              │              │              │              │          │
│       │              │              │              │ 5.Validate   │          │
│       │              │              │              │   Token      │          │
│       │              │              │              │              │          │
│       │ 6.Notify     │              │              │              │          │
│       │◀─────────────────────────────────────────────────────────│          │
│       │ (via Event)  │              │              │              │          │
│       │              │              │              │              │          │
│  └────┴────┘    └────┴────┘    └────┴────┘    └────┴────┘    └────┴────┘    │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 安全设计

### 4.1 IAM 权限设计

#### 4.1.1 最小权限原则

```yaml
# Event Processor Lambda Role
EventProcessorRole:
  Policies:
    - SecurityHubReadOnly
    - DynamoDBTaskTableWrite
    - LambdaInvokeAgent
    - CloudWatchLogsWrite

# Agent Execution Role
AgentExecutionRole:
  Policies:
    - BedrockInvokeModel
    - DynamoDBTaskTableReadWrite
    - S3KnowledgeBaseRead
    - SecurityServicesRead  # Config, GuardDuty, Inspector 只读

# Remediation Execution Role (需要审批后才能 assume)
RemediationRole:
  Policies:
    - SecurityRemediationActions  # 具体修复操作权限
    - SecurityHubUpdateFindings
  Conditions:
    - RequireApprovalToken
```

#### 4.1.2 权限边界

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Deny",
      "Action": [
        "iam:CreateUser",
        "iam:DeleteUser",
        "iam:CreateAccessKey",
        "organizations:*",
        "account:*"
      ],
      "Resource": "*"
    }
  ]
}
```

### 4.2 数据安全

| 数据类型 | 加密方式 | 访问控制 |
|----------|----------|----------|
| DynamoDB 数据 | AWS managed KMS | IAM + Resource Policy |
| S3 知识库 | SSE-S3 | Bucket Policy |
| 审批 Token | JWT (RS256) | 时效性验证 |
| API 调用 | TLS 1.2+ | API Gateway Auth |

### 4.3 审批 Token 设计

```python
# Token 结构
{
    "task_id": "uuid",
    "finding_id": "arn:aws:...",
    "action": "approve|reject",
    "expires_at": "ISO8601",
    "issued_at": "ISO8601",
    "issuer": "shara-agent",
    "signature": "..."
}

# Token 验证流程
1. 检查签名有效性
2. 检查是否过期
3. 检查任务状态是否为 PENDING_APPROVAL
4. 检查是否已被使用（防止重放）
```

---

## 5. 可观测性设计

### 5.1 日志设计

```json
{
  "timestamp": "2025-01-28T10:30:00Z",
  "level": "INFO",
  "service": "shara-agent",
  "component": "orchestrator",
  "trace_id": "1-abc123",
  "span_id": "def456",
  "task_id": "task-789",
  "finding_id": "arn:aws:securityhub:...",
  "action": "analyze_finding",
  "duration_ms": 1234,
  "status": "success",
  "metadata": {
    "finding_type": "Software and Configuration Checks",
    "resource_type": "AwsS3Bucket"
  }
}
```

### 5.2 指标设计

| 指标名称 | 类型 | 维度 | 说明 |
|----------|------|------|------|
| FindingsReceived | Counter | severity, source | 接收的 Finding 数量 |
| FindingsProcessed | Counter | severity, status | 处理完成的 Finding |
| ProcessingDuration | Timer | stage | 各阶段处理时长 |
| ApprovalLatency | Timer | - | 审批响应时间 |
| RemediationSuccess | Counter | finding_type | 修复成功数量 |
| RemediationFailure | Counter | finding_type, error | 修复失败数量 |
| AgentInvocations | Counter | agent_type | Agent 调用次数 |
| LLMTokenUsage | Counter | model, agent | Token 消耗 |

### 5.3 告警设计

| 告警名称 | 条件 | 严重级别 | 通知方式 |
|----------|------|----------|----------|
| HighProcessingLatency | P95 > 5min | WARNING | SNS |
| ProcessingFailureRate | > 10% in 5min | CRITICAL | SNS + PagerDuty |
| ApprovalTimeout | Pending > 24h | WARNING | SNS |
| AgentError | Any error | WARNING | SNS |
| LLMQuotaWarning | Usage > 80% | WARNING | SNS |

---

## 6. 部署架构

### 6.1 基础设施

```
┌─────────────────────────────────────────────────────────────────────┐
│                              VPC                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                      Private Subnet                            │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │  │
│  │  │   Lambda    │  │   Lambda    │  │  AgentCore  │           │  │
│  │  │  Processor  │  │  Approval   │  │   Runtime   │           │  │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘           │  │
│  │         │                │                │                   │  │
│  │         └────────────────┼────────────────┘                   │  │
│  │                          │                                     │  │
│  │                          ▼                                     │  │
│  │              ┌─────────────────────┐                          │  │
│  │              │    VPC Endpoints    │                          │  │
│  │              │  - DynamoDB         │                          │  │
│  │              │  - S3               │                          │  │
│  │              │  - Secrets Manager  │                          │  │
│  │              │  - Bedrock          │                          │  │
│  │              │  - Security Hub     │                          │  │
│  │              └─────────────────────┘                          │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                      Public Subnet                             │  │
│  │  ┌─────────────┐                                              │  │
│  │  │ NAT Gateway │ (用于 SES 发送邮件)                          │  │
│  │  └─────────────┘                                              │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 多区域部署（可选）

```
┌──────────────────┐     ┌──────────────────┐
│   us-east-1      │     │   eu-west-1      │
│  (Primary)       │     │  (Secondary)     │
│                  │     │                  │
│  ┌────────────┐  │     │  ┌────────────┐  │
│  │ Security   │  │     │  │ Security   │  │
│  │ Hub        │──┼─────┼──│ Hub        │  │
│  │ (Aggr)     │  │     │  │ (Member)   │  │
│  └────────────┘  │     │  └────────────┘  │
│                  │     │                  │
│  ┌────────────┐  │     │                  │
│  │ Agent      │  │     │                  │
│  │ System     │  │     │                  │
│  └────────────┘  │     │                  │
└──────────────────┘     └──────────────────┘
```

---

## 7. 扩展性设计

### 7.1 插件式 Finding Handler

```python
# Finding Handler 接口
class FindingHandler(ABC):
    @abstractmethod
    def can_handle(self, finding: dict) -> bool:
        """判断是否能处理该类型 Finding"""
        pass

    @abstractmethod
    def analyze(self, finding: dict) -> AnalysisResult:
        """分析 Finding"""
        pass

    @abstractmethod
    def generate_remediation(self, analysis: AnalysisResult) -> RemediationPlan:
        """生成修复方案"""
        pass

    @abstractmethod
    def execute_remediation(self, plan: RemediationPlan) -> ExecutionResult:
        """执行修复"""
        pass

# 注册新的 Handler
handler_registry.register(S3PublicAccessHandler())
handler_registry.register(SecurityGroupOpenHandler())
handler_registry.register(IAMOverprivilegedHandler())
```

### 7.2 知识库扩展

```
knowledge-base/
├── playbooks/
│   ├── s3/
│   │   ├── public-access.md
│   │   ├── encryption.md
│   │   └── logging.md
│   ├── ec2/
│   │   ├── security-group.md
│   │   └── instance-metadata.md
│   ├── iam/
│   │   ├── overprivileged-role.md
│   │   └── access-key-rotation.md
│   └── ...
├── templates/
│   ├── cloudformation/
│   └── terraform/
└── policies/
    ├── remediation-policies.json
    └── exclusion-rules.json
```

---

## 8. 文档版本

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| 1.0 | 2025-01-28 | - | 初始版本 |
