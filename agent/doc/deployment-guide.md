# Security Hub Auto-Remediation Agent 部署指南

## 1. 概述

本文档提供 SHARA 系统的完整部署指南，包括先决条件、基础设施部署、配置和验证步骤。

---

## 2. 先决条件

### 2.1 AWS 账户要求

| 要求 | 说明 |
|------|------|
| AWS 账户 | 具有足够权限的 AWS 账户 |
| Security Hub | 已启用并配置 |
| Bedrock 访问 | Claude 模型访问权限已申请 |
| SES 验证 | 已验证发送域名或邮箱 |

### 2.2 权限要求

部署用户需要以下权限：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudformation:*",
        "lambda:*",
        "dynamodb:*",
        "s3:*",
        "iam:*",
        "events:*",
        "apigateway:*",
        "ses:*",
        "logs:*",
        "secretsmanager:*",
        "ssm:*",
        "bedrock:*",
        "securityhub:*"
      ],
      "Resource": "*"
    }
  ]
}
```

### 2.3 开发环境

| 工具 | 版本 | 说明 |
|------|------|------|
| AWS CLI | >= 2.x | AWS 命令行工具 |
| Python | >= 3.11 | Lambda 运行时 |
| Node.js | >= 18.x | CDK 运行时 |
| AWS CDK | >= 2.x | 基础设施即代码 |
| Docker | >= 24.x | Lambda 容器构建 |

### 2.4 区域支持

确保目标区域支持以下服务：

- Amazon Bedrock (Claude models)
- AWS Security Hub
- Amazon EventBridge
- AWS Lambda
- Amazon DynamoDB
- Amazon SES

---

## 3. 快速开始

### 3.1 克隆代码

```bash
git clone https://github.com/your-org/shara-agent.git
cd shara-agent
```

### 3.2 安装依赖

```bash
# 安装 CDK 依赖
npm install

# 安装 Python 依赖
cd src
pip install -r requirements.txt
cd ..
```

### 3.3 配置环境

```bash
# 复制配置模板
cp config/config.example.yaml config/config.yaml

# 编辑配置
vi config/config.yaml
```

### 3.4 部署

```bash
# 引导 CDK (首次部署)
cdk bootstrap aws://ACCOUNT_ID/REGION

# 部署所有堆栈
cdk deploy --all
```

---

## 4. 详细部署步骤

### 4.1 Step 1: 准备配置文件

创建 `config/config.yaml`:

```yaml
# SHARA Configuration
environment: production

# AWS Account Settings
aws:
  account_id: "123456789012"
  region: "us-east-1"

# Security Hub Settings
security_hub:
  enabled: true
  severity_filter:
    - HIGH
    - CRITICAL
  sources:
    - AWS Config
    - GuardDuty
    - Inspector

# Agent Settings
agent:
  orchestrator:
    model_id: anthropic.claude-3-5-sonnet-20241022-v2:0
    temperature: 0.3
    max_tokens: 4096
  analyzer:
    model_id: anthropic.claude-3-5-sonnet-20241022-v2:0
    temperature: 0.2
    max_tokens: 8192
  remediator:
    model_id: anthropic.claude-3-opus-20240229-v1:0
    temperature: 0.1
    max_tokens: 8192
  validator:
    model_id: anthropic.claude-3-5-sonnet-20241022-v2:0
    temperature: 0.1
    max_tokens: 4096

# Notification Settings
notification:
  admin_emails:
    - security-team@example.com
    - soc@example.com
  ses_sender: shara-noreply@example.com
  approval_timeout_hours: 24

# DynamoDB Settings
dynamodb:
  tasks_table: shara-tasks
  events_table: shara-task-events
  tokens_table: shara-approval-tokens
  billing_mode: PAY_PER_REQUEST

# S3 Settings
s3:
  knowledge_base_bucket: shara-knowledge-base
  reports_bucket: shara-reports

# API Gateway Settings
api:
  stage_name: v1
  throttle_rate: 100
  throttle_burst: 200

# Logging Settings
logging:
  level: INFO
  retention_days: 30

# Feature Flags
features:
  dry_run_mode: false
  auto_remediate: false
  enable_rollback: true
```

### 4.2 Step 2: 配置 SES

```bash
# 验证发送邮箱
aws ses verify-email-identity --email-address shara-noreply@example.com

# 或验证域名
aws ses verify-domain-identity --domain example.com

# 检查验证状态
aws ses get-identity-verification-attributes \
  --identities shara-noreply@example.com
```

### 4.3 Step 3: 配置 Bedrock

```bash
# 检查模型访问权限
aws bedrock list-foundation-models --query 'modelSummaries[?modelId==`anthropic.claude-3-5-sonnet-20241022-v2:0`]'

# 如需申请访问权限，通过控制台操作
# Bedrock Console -> Model access -> Request access
```

### 4.4 Step 4: 部署基础设施

```bash
# 查看将要部署的资源
cdk diff

# 部署网络基础设施
cdk deploy SharaNetworkStack

# 部署存储层
cdk deploy SharaStorageStack

# 部署 Agent 层
cdk deploy SharaAgentStack

# 部署 API 层
cdk deploy SharaApiStack

# 部署事件处理层
cdk deploy SharaEventStack

# 或一次性部署所有
cdk deploy --all --require-approval never
```

### 4.5 Step 5: 上传知识库

```bash
# 同步 Playbooks 到 S3
aws s3 sync knowledge-base/ s3://shara-knowledge-base-123456789012-us-east-1/

# 更新 Bedrock Knowledge Base 索引
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id KNOWLEDGE_BASE_ID \
  --data-source-id DATA_SOURCE_ID
```

### 4.6 Step 6: 配置 EventBridge 规则

EventBridge 规则通过 CDK 自动创建，但可手动验证：

```bash
# 查看规则
aws events describe-rule --name shara-security-hub-findings

# 查看规则目标
aws events list-targets-by-rule --rule shara-security-hub-findings
```

---

## 5. CDK 堆栈详解

### 5.1 堆栈结构

```
shara-cdk/
├── bin/
│   └── shara.ts                 # CDK 应用入口
├── lib/
│   ├── network-stack.ts         # VPC、子网、端点
│   ├── storage-stack.ts         # DynamoDB、S3
│   ├── agent-stack.ts           # Lambda、Agent 配置
│   ├── api-stack.ts             # API Gateway
│   └── event-stack.ts           # EventBridge
├── config/
│   └── config.yaml              # 配置文件
└── cdk.json                     # CDK 配置
```

### 5.2 Network Stack

```typescript
// lib/network-stack.ts
export class SharaNetworkStack extends Stack {
  public readonly vpc: ec2.Vpc;

  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    // 创建 VPC
    this.vpc = new ec2.Vpc(this, 'SharaVpc', {
      maxAzs: 2,
      natGateways: 1,
      subnetConfiguration: [
        {
          name: 'Public',
          subnetType: ec2.SubnetType.PUBLIC,
          cidrMask: 24,
        },
        {
          name: 'Private',
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
          cidrMask: 24,
        },
      ],
    });

    // VPC Endpoints
    this.vpc.addInterfaceEndpoint('BedrockEndpoint', {
      service: ec2.InterfaceVpcEndpointAwsService.BEDROCK_RUNTIME,
    });

    this.vpc.addInterfaceEndpoint('SecretsManagerEndpoint', {
      service: ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER,
    });

    this.vpc.addGatewayEndpoint('DynamoDBEndpoint', {
      service: ec2.GatewayVpcEndpointAwsService.DYNAMODB,
    });

    this.vpc.addGatewayEndpoint('S3Endpoint', {
      service: ec2.GatewayVpcEndpointAwsService.S3,
    });
  }
}
```

### 5.3 Storage Stack

```typescript
// lib/storage-stack.ts
export class SharaStorageStack extends Stack {
  public readonly tasksTable: dynamodb.Table;
  public readonly eventsTable: dynamodb.Table;
  public readonly tokensTable: dynamodb.Table;
  public readonly knowledgeBaseBucket: s3.Bucket;

  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    // Tasks Table
    this.tasksTable = new dynamodb.Table(this, 'TasksTable', {
      tableName: 'shara-tasks',
      partitionKey: { name: 'PK', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'SK', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      pointInTimeRecovery: true,
      encryption: dynamodb.TableEncryption.AWS_MANAGED,
    });

    // GSI for status queries
    this.tasksTable.addGlobalSecondaryIndex({
      indexName: 'GSI1',
      partitionKey: { name: 'GSI1PK', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'GSI1SK', type: dynamodb.AttributeType.STRING },
    });

    // Events Table with TTL
    this.eventsTable = new dynamodb.Table(this, 'EventsTable', {
      tableName: 'shara-task-events',
      partitionKey: { name: 'PK', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'SK', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: 'ttl',
    });

    // Tokens Table with TTL
    this.tokensTable = new dynamodb.Table(this, 'TokensTable', {
      tableName: 'shara-approval-tokens',
      partitionKey: { name: 'PK', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'SK', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: 'ttl',
    });

    // Knowledge Base Bucket
    this.knowledgeBaseBucket = new s3.Bucket(this, 'KnowledgeBaseBucket', {
      bucketName: `shara-knowledge-base-${this.account}-${this.region}`,
      encryption: s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      versioned: true,
    });
  }
}
```

### 5.4 Agent Stack

```typescript
// lib/agent-stack.ts
export class SharaAgentStack extends Stack {
  constructor(
    scope: Construct,
    id: string,
    props: {
      vpc: ec2.Vpc;
      tasksTable: dynamodb.Table;
      knowledgeBaseBucket: s3.Bucket;
    }
  ) {
    super(scope, id);

    // Agent Lambda Layer
    const agentLayer = new lambda.LayerVersion(this, 'AgentLayer', {
      code: lambda.Code.fromAsset('layers/agent'),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_11],
      description: 'SHARA Agent dependencies',
    });

    // Event Processor Lambda
    const eventProcessor = new lambda.Function(this, 'EventProcessor', {
      functionName: 'shara-event-processor',
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'handler.lambda_handler',
      code: lambda.Code.fromAsset('src/event_processor'),
      layers: [agentLayer],
      vpc: props.vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      timeout: Duration.minutes(5),
      memorySize: 1024,
      environment: {
        TASKS_TABLE: props.tasksTable.tableName,
        LOG_LEVEL: 'INFO',
      },
    });

    // Orchestrator Lambda
    const orchestrator = new lambda.Function(this, 'OrchestratorAgent', {
      functionName: 'shara-orchestrator-agent',
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'handler.lambda_handler',
      code: lambda.Code.fromAsset('src/agents/orchestrator'),
      layers: [agentLayer],
      vpc: props.vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      timeout: Duration.minutes(15),
      memorySize: 2048,
      environment: {
        TASKS_TABLE: props.tasksTable.tableName,
        KNOWLEDGE_BASE_BUCKET: props.knowledgeBaseBucket.bucketName,
        MODEL_ID: 'anthropic.claude-3-5-sonnet-20241022-v2:0',
      },
    });

    // Grant permissions
    props.tasksTable.grantReadWriteData(eventProcessor);
    props.tasksTable.grantReadWriteData(orchestrator);
    props.knowledgeBaseBucket.grantRead(orchestrator);

    // Bedrock permissions
    orchestrator.addToRolePolicy(new iam.PolicyStatement({
      actions: [
        'bedrock:InvokeModel',
        'bedrock:Retrieve',
      ],
      resources: ['*'],
    }));
  }
}
```

---

## 6. 配置验证

### 6.1 验证部署

```bash
# 验证 Lambda 函数
aws lambda list-functions --query 'Functions[?starts_with(FunctionName, `shara-`)].[FunctionName, Runtime, State]' --output table

# 验证 DynamoDB 表
aws dynamodb list-tables --query 'TableNames[?starts_with(@, `shara-`)]'

# 验证 EventBridge 规则
aws events list-rules --name-prefix shara

# 验证 API Gateway
aws apigateway get-rest-apis --query 'items[?name==`shara-api`]'
```

### 6.2 测试 Finding 处理

```bash
# 创建测试 Finding (通过 Security Hub)
aws securityhub batch-import-findings --findings '[
  {
    "SchemaVersion": "2018-10-08",
    "Id": "test-finding-001",
    "ProductArn": "arn:aws:securityhub:us-east-1:123456789012:product/123456789012/default",
    "GeneratorId": "test-generator",
    "AwsAccountId": "123456789012",
    "Types": ["Software and Configuration Checks/AWS Security Best Practices"],
    "CreatedAt": "2025-01-28T00:00:00.000Z",
    "UpdatedAt": "2025-01-28T00:00:00.000Z",
    "Severity": {"Label": "HIGH"},
    "Title": "Test Finding - S3 Bucket Public Access",
    "Description": "Test finding for SHARA system validation",
    "Resources": [{
      "Type": "AwsS3Bucket",
      "Id": "arn:aws:s3:::test-bucket",
      "Region": "us-east-1"
    }],
    "RecordState": "ACTIVE"
  }
]'

# 检查处理状态
aws dynamodb scan --table-name shara-tasks --filter-expression "contains(findingTitle, :title)" --expression-attribute-values '{":title": {"S": "Test Finding"}}'
```

### 6.3 测试审批流程

```bash
# 获取测试任务 ID
TASK_ID=$(aws dynamodb scan --table-name shara-tasks --query 'Items[0].taskId.S' --output text)

# 获取 API Gateway URL
API_URL=$(aws cloudformation describe-stacks --stack-name SharaApiStack --query 'Stacks[0].Outputs[?OutputKey==`ApiUrl`].OutputValue' --output text)

# 测试审批 API (需要有效 token)
curl -X POST "$API_URL/v1/approvals/$TASK_ID/respond?token=TEST_TOKEN&action=approve"
```

---

## 7. 监控设置

### 7.1 CloudWatch Dashboard

```bash
# 创建监控 Dashboard
aws cloudwatch put-dashboard --dashboard-name SHARA-Operations --dashboard-body '{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "title": "Findings Processed",
        "metrics": [
          ["SHARA", "FindingsProcessed", "Status", "Success"],
          ["SHARA", "FindingsProcessed", "Status", "Failed"]
        ],
        "period": 300,
        "stat": "Sum"
      }
    },
    {
      "type": "metric",
      "properties": {
        "title": "Agent Latency",
        "metrics": [
          ["SHARA", "ProcessingDuration", "Agent", "Orchestrator"],
          ["SHARA", "ProcessingDuration", "Agent", "Analyzer"],
          ["SHARA", "ProcessingDuration", "Agent", "Remediator"]
        ],
        "period": 300,
        "stat": "Average"
      }
    }
  ]
}'
```

### 7.2 CloudWatch Alarms

```bash
# 创建处理失败告警
aws cloudwatch put-metric-alarm \
  --alarm-name "SHARA-ProcessingFailures" \
  --alarm-description "Alert when SHARA processing failure rate exceeds 10%" \
  --metric-name "FindingsProcessed" \
  --namespace "SHARA" \
  --dimensions Name=Status,Value=Failed \
  --statistic Sum \
  --period 300 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 2 \
  --alarm-actions arn:aws:sns:us-east-1:123456789012:shara-alerts
```

---

## 8. 故障排除

### 8.1 常见问题

#### Lambda 超时

```bash
# 检查 Lambda 日志
aws logs filter-log-events \
  --log-group-name /aws/lambda/shara-orchestrator-agent \
  --filter-pattern "Task timed out"

# 解决方案：增加超时时间或优化代码
```

#### Bedrock 访问被拒

```bash
# 检查模型访问权限
aws bedrock get-model-invocation-logging-configuration

# 解决方案：在 Bedrock 控制台申请模型访问权限
```

#### EventBridge 规则未触发

```bash
# 检查规则状态
aws events describe-rule --name shara-security-hub-findings

# 检查规则匹配
aws events test-event-pattern \
  --event-pattern file://eventbridge-rule.json \
  --event file://test-event.json
```

### 8.2 日志分析

```bash
# 查询处理错误
aws logs start-query \
  --log-group-name /aws/lambda/shara-orchestrator-agent \
  --start-time $(date -d '1 hour ago' +%s) \
  --end-time $(date +%s) \
  --query-string 'fields @timestamp, @message | filter @message like /ERROR/ | sort @timestamp desc | limit 50'

# 获取查询结果
aws logs get-query-results --query-id QUERY_ID
```

---

## 9. 更新与维护

### 9.1 更新部署

```bash
# 更新代码
git pull origin main

# 更新依赖
pip install -r src/requirements.txt --upgrade

# 部署更新
cdk deploy --all
```

### 9.2 回滚部署

```bash
# 查看部署历史
aws cloudformation describe-stack-events --stack-name SharaAgentStack

# 回滚到上一版本
cdk deploy --all --rollback
```

### 9.3 知识库更新

```bash
# 更新 Playbooks
aws s3 sync knowledge-base/ s3://shara-knowledge-base-123456789012-us-east-1/ --delete

# 重新索引
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id KNOWLEDGE_BASE_ID \
  --data-source-id DATA_SOURCE_ID
```

---

## 10. 安全最佳实践

### 10.1 部署检查清单

- [ ] 所有 Lambda 函数使用最小权限 IAM Role
- [ ] DynamoDB 表启用加密
- [ ] S3 bucket 阻止公开访问
- [ ] API Gateway 启用 WAF
- [ ] 敏感配置存储在 Secrets Manager
- [ ] 启用 CloudTrail 审计
- [ ] VPC Endpoints 用于 AWS 服务访问
- [ ] Lambda 函数部署在私有子网

### 10.2 定期审查

```bash
# 检查 IAM 权限
aws iam get-role --role-name shara-orchestrator-role
aws iam list-attached-role-policies --role-name shara-orchestrator-role

# 检查安全组
aws ec2 describe-security-groups --filters "Name=group-name,Values=shara-*"

# 检查公开端点
aws apigateway get-rest-api --rest-api-id API_ID
```

---

## 11. 文档版本

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| 1.0 | 2025-01-28 | - | 初始版本 |
