# SHARA Infrastructure

基于 Terraform 的 SHARA 基础设施代码。

## 目录结构

```
infra/
├── 000_main.tf              # Provider 和后端配置
├── 001_vpc.tf               # VPC、子网、NAT、VPC Endpoints
├── 002_storage.tf           # DynamoDB 表、S3 桶
├── 003_iam.tf               # IAM 角色和策略
├── 004_lambda.tf            # Lambda 函数
├── 005_api_gateway.tf       # API Gateway
├── 006_eventbridge.tf       # EventBridge 规则
├── variables.tf             # 输入变量
├── outputs.tf               # 输出值
├── terraform.tfvars.example # 变量示例文件
├── modules/
│   └── cors/                # CORS 模块
│       └── main.tf
└── README.md                # 本文档
```

## Stack 依赖关系

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SHARA Infrastructure                            │
│                                                                         │
│  ┌─────────────────┐     ┌─────────────────┐                           │
│  │   001_vpc.tf    │     │  002_storage.tf │                           │
│  │                 │     │                 │                           │
│  │  - VPC          │     │  - DynamoDB     │                           │
│  │  - Subnets      │     │  - S3           │                           │
│  │  - NAT Gateway  │     │                 │                           │
│  │  - Endpoints    │     │                 │                           │
│  └────────┬────────┘     └────────┬────────┘                           │
│           │                       │                                     │
│           └───────────┬───────────┘                                     │
│                       │                                                 │
│                       ▼                                                 │
│           ┌─────────────────────┐                                       │
│           │    003_iam.tf       │                                       │
│           │                     │                                       │
│           │  - Lambda Role      │                                       │
│           │  - Policies         │                                       │
│           └──────────┬──────────┘                                       │
│                      │                                                  │
│                      ▼                                                  │
│           ┌─────────────────────┐                                       │
│           │    004_lambda.tf    │                                       │
│           │                     │                                       │
│           │  - Event Handler    │                                       │
│           │  - Approval Handler │                                       │
│           └──────────┬──────────┘                                       │
│                      │                                                  │
│           ┌──────────┴──────────┐                                       │
│           │                     │                                       │
│           ▼                     ▼                                       │
│  ┌─────────────────┐   ┌─────────────────┐                             │
│  │005_api_gateway  │   │006_eventbridge  │                             │
│  │                 │   │                 │                             │
│  │  - REST API     │   │  - SecurityHub  │                             │
│  │  - Endpoints    │   │    Rule         │                             │
│  └─────────────────┘   └─────────────────┘                             │
└─────────────────────────────────────────────────────────────────────────┘
```

## 快速开始

### 1. 安装 Terraform

```bash
# macOS
brew tap hashicorp/tap
brew install hashicorp/tap/terraform

# 验证安装
terraform version
```

### 2. 配置 AWS 凭证

```bash
aws configure
# 或设置环境变量
export AWS_PROFILE=your-profile
export AWS_REGION=ap-northeast-1
```

### 3. 初始化 Terraform

```bash
cd infra
terraform init
```

### 4. 配置变量

```bash
# 复制示例文件
cp terraform.tfvars.example terraform.tfvars

# 编辑变量
vim terraform.tfvars
```

### 5. 预览变更

```bash
terraform plan
```

### 6. 部署

```bash
terraform apply
```

### 7. 清理

```bash
# 删除所有资源 (开发环境)
terraform destroy
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `project_name` | `shara` | 项目名称 |
| `stage` | `dev` | 部署环境 (dev/staging/prod) |
| `aws_region` | `ap-northeast-1` | AWS 区域 |

## 资源说明

### VPC (001_vpc.tf)

- VPC (10.0.0.0/16)
- 公有子网 (2 AZ)
- 私有子网 (2 AZ)
- NAT Gateway
- VPC Endpoints:
  - S3 (Gateway)
  - DynamoDB (Gateway)
  - Bedrock Runtime (Interface)
  - Security Hub (Interface)
  - SES (Interface)
  - CloudWatch Logs (Interface)

### Storage (002_storage.tf)

DynamoDB 表:
- **shara-tasks**: 任务主表
  - GSI: status-index, resource-index, finding-index
- **shara-task-events**: 任务事件表
- **shara-approval-tokens**: 审批令牌表
- **shara-configuration**: 配置表

S3 桶:
- **shara-knowledge-{account}**: 知识库存储桶（存储修复经验，用于 Bedrock Knowledge Base）
- **shara-artifacts-{account}**: 工件存储桶

### Lambda (004_lambda.tf)

- **Event Handler**: 处理 Security Hub 事件
- **Approval Handler**: 处理审批回调

### API Gateway (005_api_gateway.tf)

- `GET /tasks` - 列出任务
- `POST /tasks` - 创建任务
- `GET /tasks/{task_id}` - 获取任务详情
- `GET /approve?token=xxx&action=approve|reject` - 审批回调
- `POST /approve` - 程序化审批
- `POST /findings` - 提交 Finding
- `GET /health` - 健康检查

### EventBridge (006_eventbridge.tf)

- Security Hub Finding 事件 → Event Handler
  - 仅触发: Severity = CRITICAL/HIGH 且 Workflow.Status = NEW

## 经验学习流程

SHARA 采用"经验学习"模式，通过用户反馈持续优化修复质量：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         修复经验学习流程                                  │
│                                                                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                 │
│  │  修复完成    │───▶│  发送邮件   │───▶│  用户评价    │                 │
│  └─────────────┘    │ (含评价链接) │    └──────┬──────┘                 │
│                     └─────────────┘           │                         │
│                                               │                         │
│                           ┌───────────────────┴───────────────────┐     │
│                           │                                       │     │
│                           ▼                                       ▼     │
│                  ┌─────────────────┐                    ┌─────────────┐ │
│                  │  评价"有效"     │                    │ 评价"无效"  │ │
│                  └────────┬────────┘                    └─────────────┘ │
│                           │                                             │
│                           ▼                                             │
│                  ┌─────────────────┐                                    │
│                  │  保存修复经验    │                                    │
│                  │  到 Knowledge   │                                    │
│                  │  Bucket         │                                    │
│                  └────────┬────────┘                                    │
│                           │                                             │
│                           ▼                                             │
│                  ┌─────────────────┐                                    │
│                  │  Bedrock KB     │                                    │
│                  │  自动向量化     │                                    │
│                  └────────┬────────┘                                    │
│                           │                                             │
│                           ▼                                             │
│                  ┌─────────────────┐                                    │
│                  │  未来修复时     │                                    │
│                  │  检索相似经验   │                                    │
│                  └─────────────────┘                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

### 知识库存储结构

```
s3://shara-knowledge-{stage}-{account}/
├── experiences/
│   ├── S3.1/                          # 按 Control ID 分类
│   │   ├── {task_id}.json             # 修复经验（思路、步骤）
│   │   └── {task_id}_code.py          # 修复代码
│   ├── EC2.19/
│   │   └── ...
│   └── IAM.4/
│       └── ...
```

### Bedrock Knowledge Base 配置

部署后需要在 AWS 控制台创建 Bedrock Knowledge Base：
1. 数据源：指向 `shara-knowledge-{stage}-{account}` S3 桶
2. 嵌入模型：Amazon Titan Embeddings
3. 向量数据库：Amazon OpenSearch Serverless

## 输出

部署后可通过以下命令查看输出：

```bash
terraform output
```

主要输出：
- `api_gateway_url`: API Gateway 端点 URL
- `tasks_table_name`: DynamoDB 任务表名
- `knowledge_bucket_name`: S3 知识库存储桶名

## 常用命令

```bash
# 初始化
terraform init

# 格式化代码
terraform fmt

# 验证配置
terraform validate

# 预览变更
terraform plan

# 应用变更
terraform apply

# 仅应用特定资源
terraform apply -target=aws_lambda_function.event_handler

# 查看状态
terraform state list

# 删除所有资源
terraform destroy

# 刷新状态
terraform refresh
```

## 后端配置 (可选)

如需使用 S3 作为状态后端，取消 `000_main.tf` 中的注释并创建对应资源：

```bash
# 创建状态存储桶
aws s3 mb s3://shara-terraform-state --region ap-northeast-1

# 创建锁表
aws dynamodb create-table \
  --table-name shara-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region ap-northeast-1
```
