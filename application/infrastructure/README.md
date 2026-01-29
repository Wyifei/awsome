# 基础设施 Terraform 代码

电动自行车统一身份认证平台 AWS 基础设施的 Terraform 代码。

## 特点

- **无需自定义域名**: 使用 CloudFront 默认域名 (`*.cloudfront.net`) 和 Cognito 默认域名 (`*.auth.region.amazoncognito.com`)
- **简化部署**: 无需配置 ACM 证书和 Route 53 DNS
- **无 Lambda Triggers**: 用户档案创建由 User Service 微服务负责

## 目录结构

```
infrastructure/
├── main.tf                      # 主模块编排
├── variables.tf                 # 变量定义
├── outputs.tf                   # 输出值
├── versions.tf                  # Provider 版本配置
├── terraform.tfvars             # 变量配置
├── README.md                    # 本文档
│
├── 001_vpc/                     # VPC 网络层
│   ├── main.tf                  # VPC、子网、NAT Gateway、VPC Endpoints
│   ├── variables.tf
│   └── outputs.tf
│
├── 002_security/                # 安全组
│   ├── main.tf                  # ALB、EKS、Aurora、Lambda 安全组
│   ├── variables.tf
│   ├── outputs.tf
│   └── waf/                     # WAF Web ACL (CloudFront 用)
│       ├── main.tf
│       ├── variables.tf
│       └── outputs.tf
│
├── 003_iam/                     # IAM & KMS
│   ├── main.tf                  # KMS 密钥、Secrets Manager
│   ├── variables.tf
│   └── outputs.tf
│
├── 004_ecr/                     # ECR 镜像仓库
│   ├── main.tf                  # ECR Repositories for microservices
│   ├── variables.tf
│   └── outputs.tf
│
├── 005_cognito/                 # Cognito 身份认证
│   ├── main.tf                  # User Pool、App Client、Domain (使用默认域名)
│   ├── variables.tf
│   └── outputs.tf
│
├── 007_eks/                     # EKS 集群 (使用官方 EKS Module)
│   ├── main.tf                  # EKS Cluster、Node Group、Add-ons、IRSA
│   ├── variables.tf
│   └── outputs.tf
│
├── 008_rds/                     # Aurora PostgreSQL
│   ├── main.tf                  # Aurora Cluster、Instances
│   ├── variables.tf
│   └── outputs.tf
│
├── 009_s3/                      # S3 存储桶
│   ├── main.tf                  # Frontend、Avatars 存储桶
│   ├── variables.tf
│   └── outputs.tf
│
└── 010_cloudfront/              # CloudFront CDN
    ├── main.tf                  # Distribution 配置 (使用默认证书)
    ├── variables.tf
    └── outputs.tf
```

## 部署顺序

Terraform 会自动处理依赖关系，但模块的逻辑部署顺序为：

1. **001_vpc** - VPC、子网、NAT Gateway、VPC Endpoints
2. **002_security** - 安全组、WAF Web ACL
3. **003_iam** - KMS 密钥、Secrets Manager
4. **004_ecr** - ECR 镜像仓库 (user-service, profile-service, notification-service)
5. **005_cognito** - Cognito User Pool (使用 Cognito 默认域名)
6. **007_eks** - EKS 集群及节点组 (使用 terraform-aws-modules/eks)
7. **008_rds** - Aurora PostgreSQL 集群
8. **009_s3** - S3 存储桶
9. **010_cloudfront** - CloudFront CDN (使用 CloudFront 默认域名)

## 前置条件

1. **AWS CLI** 已配置且有足够权限
2. **Terraform** >= 1.5.0
3. **SES** 邮件地址已验证

## 使用方法

### 1. 配置变量

```bash
cd infrastructure
# 编辑 terraform.tfvars 填写实际值 (如 SES 邮件地址)
vim terraform.tfvars
```

### 2. 初始化 Terraform

```bash
terraform init
```

### 3. 预览变更

```bash
terraform plan
```

### 4. 应用变更

```bash
terraform apply
```

### 5. 获取部署输出

部署完成后，重要的输出包括：

```bash
# 获取所有输出
terraform output

# 获取 CloudFront 域名 (前端访问地址)
terraform output cloudfront_domain_name

# 获取 Cognito 域名 (OAuth 认证地址)
terraform output cognito_domain

# 获取 EKS 配置命令
terraform output eks_update_kubeconfig_command
```

### 6. 更新 Cognito 回调 URL

部署完成后，需要更新 `terraform.tfvars` 中的 Cognito 回调 URL：

```hcl
# 将 CloudFront 域名添加到回调 URL
cognito_callback_urls = [
  "https://<cloudfront-distribution-id>.cloudfront.net/callback",
  "http://localhost:3000/callback"
]

cognito_logout_urls = [
  "https://<cloudfront-distribution-id>.cloudfront.net",
  "http://localhost:3000"
]
```

然后重新运行:

```bash
terraform apply
```

### 7. 配置 kubectl

```bash
aws eks update-kubeconfig --name auth-platform-production --region ap-northeast-1
```

## 访问应用

部署完成后：

- **前端应用**: `https://<cloudfront-id>.cloudfront.net`
- **Cognito 登录**: `https://<cognito-domain>.auth.ap-northeast-1.amazoncognito.com`

## 用户档案创建

用户注册后的档案创建由 **User Service** 微服务负责：

1. 前端完成 Cognito 注册/登录
2. 前端调用 User Service API 创建/获取用户档案
3. User Service 将用户信息存储到 Aurora PostgreSQL

## 成本预估

| 组件 | 月费用 (USD) |
|------|-------------|
| EKS 集群 | $73 |
| EC2 Worker (2 x m6i.large) | $138 |
| Aurora PostgreSQL | $350 |
| NAT Gateway | $100 |
| Cognito (10K MAU) | $0 |
| 其他 | ~$44 |
| **总计** | **~$705** |

## 销毁资源

```bash
terraform destroy
```

**警告**: 这将删除所有资源，包括数据库数据。生产环境请谨慎操作。
