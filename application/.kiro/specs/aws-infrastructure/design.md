# AWS 基础设施设计文档

## 概述

本文档描述 Auth Platform 的 AWS 基础设施设计，采用模块化 Terraform 架构，支持多环境部署。

## 架构设计

### 1. 模块化架构

基础设施采用 11 个独立模块，按部署顺序编号：

```
infrastructure/
├── main.tf                 # 主模块编排
├── variables.tf            # 全局变量
├── outputs.tf              # 全局输出
├── versions.tf             # Provider 配置
├── terraform.tfvars        # 环境变量值
├── 001_vpc/                # VPC 网络层
├── 002_security/           # 安全组和 WAF
├── 003_iam/                # KMS 和 Secrets Manager
├── 004_ecr/                # ECR 镜像仓库
├── 005_cognito/            # Cognito 身份认证
├── 006_monitoring/         # Prometheus 和 Grafana
├── 007_eks/                # EKS 集群
├── 008_rds/                # Aurora PostgreSQL
├── 009_kubernetes/         # Kubernetes 资源
├── 010_s3/                 # S3 存储桶
└── 011_cloudfront/         # CloudFront CDN
```

### 2. 模块依赖关系

```
001_vpc ─────────────────────────────────────────────────────────────┐
    │                                                                │
    ▼                                                                │
002_security ────────────────────────────────────────────────────────┤
    │                                                                │
    ▼                                                                │
003_iam ─────────────────────────────────────────────────────────────┤
    │                                                                │
    ├──────────────────┬──────────────────┬──────────────────┐       │
    ▼                  ▼                  ▼                  ▼       │
004_ecr          005_cognito        007_eks            010_s3        │
                      │                  │                  │        │
                      │                  ▼                  │        │
                      │             008_rds                 │        │
                      │                  │                  │        │
                      └──────────────────┼──────────────────┘        │
                                         ▼                           │
                                   006_monitoring                    │
                                         │                           │
                                         ▼                           │
                                   009_kubernetes                    │
                                         │                           │
                                         ▼                           │
                                   011_cloudfront ◀──────────────────┘
                                         │
                                         ▼
                                   002_security/waf (us-east-1)
```

## 模块设计详情

### 3.1 VPC 模块 (001_vpc)

**职责**: 创建 VPC、子网、Internet Gateway、NAT Gateway、路由表

**输入变量**:
| 变量 | 类型 | 说明 |
|------|------|------|
| vpc_cidr | string | VPC CIDR 块 |
| availability_zones | list(string) | 可用区列表 |
| public_subnet_cidrs | list(string) | 公有子网 CIDR |
| private_subnet_cidrs | list(string) | 私有子网 CIDR |
| database_subnet_cidrs | list(string) | 数据库子网 CIDR |

**输出**:
| 输出 | 说明 |
|------|------|
| vpc_id | VPC ID |
| public_subnet_ids | 公有子网 ID 列表 |
| private_subnet_ids | 私有子网 ID 列表 |
| database_subnet_ids | 数据库子网 ID 列表 |
| db_subnet_group_name | 数据库子网组名称 |

### 3.2 安全模块 (002_security)

**职责**: 创建安全组、WAF Web ACL

**安全组设计**:

```hcl
# ALB 安全组
resource "aws_security_group" "alb" {
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]  # CloudFront IP 范围
  }
}

# EKS Worker 安全组
resource "aws_security_group" "eks_worker" {
  ingress {
    from_port       = 10250
    to_port         = 10250
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_control.id]
  }
  ingress {
    from_port       = 30000
    to_port         = 32767
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
}

# Aurora 安全组
resource "aws_security_group" "aurora" {
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_worker.id]
  }
}
```

**WAF 规则设计** (002_security/waf):
- AWSManagedRulesCommonRuleSet
- AWSManagedRulesKnownBadInputsRuleSet
- AWSManagedRulesSQLiRuleSet
- 自定义速率限制规则 (2000/5min)
- Cognito Token 端点速率限制 (100/5min)

### 3.3 IAM 模块 (003_iam)

**职责**: 创建 KMS 密钥、Secrets Manager 密钥

**KMS 密钥**:
| 密钥别名 | 用途 |
|---------|------|
| alias/{project}-{env}/rds | Aurora 加密 |
| alias/{project}-{env}/eks | EKS Secrets 加密 |
| alias/{project}-{env}/s3 | S3 存储桶加密 |

### 3.4 ECR 模块 (004_ecr)

**职责**: 创建 ECR 镜像仓库

**仓库列表**:
- {project}-{env}/user-service
- {project}-{env}/profile-service
- {project}-{env}/notification-service

**生命周期策略**:
```json
{
  "rules": [{
    "rulePriority": 1,
    "selection": {
      "tagStatus": "untagged",
      "countType": "sinceImagePushed",
      "countUnit": "days",
      "countNumber": 7
    },
    "action": { "type": "expire" }
  }]
}
```

### 3.5 Cognito 模块 (005_cognito)

**职责**: 创建 Cognito User Pool、App Client、Domain

**User Pool 配置**:
```hcl
resource "aws_cognito_user_pool" "main" {
  name = var.user_pool_name
  
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]
  
  password_policy {
    minimum_length    = 8
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = false
  }
  
  email_configuration {
    email_sending_account = "DEVELOPER"
    source_arn           = var.ses_email_arn
  }
}
```

**App Client 配置**:
```hcl
resource "aws_cognito_user_pool_client" "web" {
  name         = "web-app"
  user_pool_id = aws_cognito_user_pool.main.id
  
  generate_secret = false
  
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH"
  ]
  
  allowed_oauth_flows = ["code"]
  allowed_oauth_scopes = ["openid", "profile", "email"]
  
  access_token_validity  = 1   # hours
  id_token_validity      = 1   # hours
  refresh_token_validity = 30  # days
}
```

### 3.6 监控模块 (006_monitoring)

**职责**: 创建 AWS Managed Prometheus Workspace、配置 IRSA

**条件部署**:
```hcl
module "monitoring" {
  source = "./006_monitoring"
  count  = var.enable_monitoring ? 1 : 0
  # ...
}
```

### 3.7 EKS 模块 (007_eks)

**职责**: 创建 EKS 集群、托管节点组、IRSA 角色

**集群配置**:
```hcl
resource "aws_eks_cluster" "main" {
  name     = "${var.project_name}-${var.environment}"
  version  = var.cluster_version
  role_arn = aws_iam_role.cluster.arn
  
  vpc_config {
    subnet_ids              = var.private_subnet_ids
    endpoint_private_access = true
    endpoint_public_access  = true
  }
  
  encryption_config {
    provider {
      key_arn = var.kms_key_arn
    }
    resources = ["secrets"]
  }
  
  enabled_cluster_log_types = [
    "api", "audit", "authenticator", 
    "controllerManager", "scheduler"
  ]
}
```

**IRSA 角色**:
| 角色 | 用途 |
|------|------|
| app-service-role | 应用服务访问 AWS 资源 |
| aws-lb-controller-role | AWS Load Balancer Controller |
| adot-collector-role | ADOT Collector |

### 3.8 RDS 模块 (008_rds)

**职责**: 创建 Aurora PostgreSQL 集群

**集群配置**:
```hcl
resource "aws_rds_cluster" "main" {
  cluster_identifier = "${var.project_name}-${var.environment}-aurora"
  engine             = "aurora-postgresql"
  engine_version     = var.engine_version
  database_name      = var.database_name
  master_username    = var.master_username
  
  manage_master_user_password = true  # RDS 托管密码
  
  db_subnet_group_name   = var.db_subnet_group_name
  vpc_security_group_ids = [var.aurora_security_group_id]
  
  storage_encrypted = true
  kms_key_id        = var.kms_key_arn
  
  backup_retention_period = var.backup_retention_period
  deletion_protection     = true
}
```

### 3.9 Kubernetes 模块 (009_kubernetes)

**职责**: 部署 Kubernetes 资源 (AWS LB Controller, NGINX Ingress, Grafana, ADOT)

**组件**:
| 组件 | Helm Chart | 说明 |
|------|-----------|------|
| AWS Load Balancer Controller | aws-load-balancer-controller | ALB/NLB 管理 |
| NGINX Ingress Controller | ingress-nginx | 集群内反向代理 |
| Grafana | grafana | 监控可视化 |
| ADOT Collector | adot-exporter-for-eks-on-ec2 | 指标收集 |
| Prometheus | prometheus | 指标存储 (可选) |

### 3.10 S3 模块 (010_s3)

**职责**: 创建 S3 存储桶

**存储桶**:
| 存储桶 | 用途 | 加密 |
|-------|------|------|
| {project}-{env}-frontend | 前端静态资源 | SSE-S3 |

> **注意**: 用户头像存储在 Aurora PostgreSQL 数据库中，不使用 S3。

### 3.11 CloudFront 模块 (011_cloudfront)

**职责**: 创建 CloudFront Distribution

**Origin 配置**:
| Origin | 类型 | 路径模式 |
|--------|------|---------|
| S3 | OAC | * (默认) |
| ALB | Custom | /api/* |

**行为配置**:
```hcl
# 默认行为 (S3 前端)
default_cache_behavior {
  target_origin_id       = "s3-frontend"
  viewer_protocol_policy = "redirect-to-https"
  allowed_methods        = ["GET", "HEAD", "OPTIONS"]
  cached_methods         = ["GET", "HEAD"]
  cache_policy_id        = data.aws_cloudfront_cache_policy.caching_optimized.id
}

# API 行为 (ALB 后端)
ordered_cache_behavior {
  path_pattern           = "/api/*"
  target_origin_id       = "alb-api"
  viewer_protocol_policy = "https-only"
  allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
  cache_policy_id        = data.aws_cloudfront_cache_policy.caching_disabled.id
}
```

## 变量设计

### 全局变量

| 变量 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| aws_region | string | ap-northeast-1 | AWS 区域 |
| project_name | string | auth-platform | 项目名称 |
| environment | string | production | 环境名称 |

### VPC 变量

| 变量 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| vpc_cidr | string | 10.0.0.0/16 | VPC CIDR |
| availability_zones | list | [ap-northeast-1a, ap-northeast-1c] | 可用区 |

### EKS 变量

| 变量 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| eks_cluster_version | string | 1.31 | K8s 版本 |
| eks_node_instance_types | list | [m6i.large] | 节点实例类型 |
| eks_node_desired_size | number | 2 | 期望节点数 |
| eks_node_min_size | number | 2 | 最小节点数 |
| eks_node_max_size | number | 6 | 最大节点数 |

### Aurora 变量

| 变量 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| aurora_engine_version | string | 16.4 | PostgreSQL 版本 |
| aurora_instance_class | string | db.r6g.large | 实例类型 |
| aurora_database_name | string | auth_platform | 数据库名 |

### 功能开关

| 变量 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| enable_monitoring | bool | false | 启用监控 |
| use_adot_collector | bool | true | 使用 ADOT |
| enable_nginx_ingress | bool | true | 启用 NGINX Ingress |
| enable_db_client | bool | false | 启用数据库客户端 Pod |

## 输出设计

### 网络输出

| 输出 | 说明 |
|------|------|
| vpc_id | VPC ID |
| private_subnet_ids | 私有子网 ID 列表 |
| database_subnet_ids | 数据库子网 ID 列表 |

### EKS 输出

| 输出 | 说明 |
|------|------|
| eks_cluster_name | EKS 集群名称 |
| eks_cluster_endpoint | EKS 集群端点 |
| eks_update_kubeconfig_command | 更新 kubeconfig 命令 |

### 数据库输出

| 输出 | 说明 |
|------|------|
| aurora_cluster_endpoint | Aurora 写入端点 |
| aurora_cluster_reader_endpoint | Aurora 只读端点 |
| aurora_secret_arn | Aurora 凭证 Secret ARN |

### 认证输出

| 输出 | 说明 |
|------|------|
| cognito_user_pool_id | Cognito User Pool ID |
| cognito_user_pool_client_id | Cognito Client ID |
| cognito_domain | Cognito 域名 |

### CDN 输出

| 输出 | 说明 |
|------|------|
| cloudfront_distribution_id | CloudFront Distribution ID |
| cloudfront_domain_name | CloudFront 域名 |

### ECR 输出

| 输出 | 说明 |
|------|------|
| ecr_repository_urls | ECR 仓库 URL 映射 |
| ecr_user_service_url | User Service ECR URL |
| ecr_profile_service_url | Profile Service ECR URL |
| ecr_notification_service_url | Notification Service ECR URL |

## 正确性属性

### P1: VPC 网络隔离
**属性**: 私有子网中的资源无法直接从公网访问
**验证**: 私有子网路由表不包含指向 Internet Gateway 的路由

### P2: 数据库访问控制
**属性**: Aurora 数据库仅接受来自 EKS Worker 安全组的连接
**验证**: Aurora 安全组入站规则仅包含 EKS Worker 安全组

### P3: 加密存储
**属性**: 所有敏感数据存储都启用加密
**验证**: Aurora、S3、EKS Secrets 都配置了 KMS 加密

### P4: 高可用部署
**属性**: 关键组件跨多可用区部署
**验证**: EKS 节点、Aurora 实例、NAT Gateway 分布在至少 2 个可用区

### P5: IRSA 最小权限
**属性**: Pod 仅获得执行任务所需的最小 IAM 权限
**验证**: IRSA 角色策略遵循最小权限原则

## 文件引用

- 主模块编排: #[[file:application/infrastructure/main.tf]]
- 变量定义: #[[file:application/infrastructure/variables.tf]]
- 输出定义: #[[file:application/infrastructure/outputs.tf]]
- 架构文档: #[[file:application/docs/infrastructure-architecture.md]]
