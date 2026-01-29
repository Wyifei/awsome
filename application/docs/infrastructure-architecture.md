# 基础设施架构文档

## 1. 概述

本文档描述电动自行车统一身份认证平台的 AWS 基础设施架构设计。

### 1.1 设计原则

- 高可用：多可用区部署，消除单点故障
- 安全性：纵深防御，最小权限原则
- 可扩展：支持水平扩展，应对业务增长
- 成本优化：使用托管服务减少运维成本
- 简化架构：使用 AWS Cognito 作为身份认证服务

### 1.2 架构总览

```
                                    ┌─────────────┐
                                    │  Route 53   │
                                    │ auth.xxx.com│
                                    └──────┬──────┘
                                           │
                                    ┌──────▼──────┐
                                    │   AWS WAF   │
                                    └──────┬──────┘
                                           │
                                    ┌──────▼──────┐     ┌─────────────┐
                                    │ CloudFront  │────▶│  S3 (前端)   │
                                    │    (CDN)    │     │ React 静态文件│
                                    └──────┬──────┘     └─────────────┘
                                           │
              ┌────────────────────────────┼────────────────────────────┐
              │                            │                            │
              ▼                            ▼                            │
┌──────────────────────┐          ┌───────────────┐                     │
│   Amazon Cognito     │          │  Public ALB   │                     │
│                      │          └───────┬───────┘                     │
│ • User Pool          │                  │                             │
│ • Hosted UI / 自定义  │                  │                             │
│ • OIDC Provider      │                  │                             │
│ • 邮件 OTP           │                  │                             │
└──────────────────────┘                  │                             │
                                          │                             │
┌─────────────────────────────────────────┼─────────────────────────────┼─────────────┐
│ VPC (10.0.0.0/16)                       │                             │             │
│  ┌──────────────────────────────────────┼───────────────────────────────────────┐   │
│  │ Public Subnet                        │                                       │   │
│  │ AZ-a: 10.0.1.0/24           ┌────────▼────────┐       AZ-b: 10.0.2.0/24      │   │
│  │                             │   Public ALB    │                              │   │
│  │    ┌───────────┐            │   (ACM 证书)    │            ┌───────────┐     │   │
│  │    │ NAT GW    │            └────────┬────────┘            │  NAT GW   │     │   │
│  │    └─────┬─────┘                     │                     └─────┬─────┘     │   │
│  └──────────┼───────────────────────────┼───────────────────────────┼───────────┘   │
│             │                           │                           │               │
│  ┌──────────┼───────────────────────────┼───────────────────────────┼───────────┐   │
│  │ Private Subnet (Compute)             │                           │           │   │
│  │ AZ-a: 10.0.11.0/24                   │            AZ-b: 10.0.12.0/24         │   │
│  │          │                   ┌───────▼───────┐                   │           │   │
│  │          ▼                   │   EKS Cluster │                   ▼           │   │
│  │    ┌───────────┐             │   (Control)   │            ┌───────────┐      │   │
│  │    │  Worker   │◀───────────▶│               │◀──────────▶│  Worker   │      │   │
│  │    │  Node     │             └───────────────┘            │  Node     │      │   │
│  │    │ (EC2)     │                                          │ (EC2)     │      │   │
│  │    │           │                                          │           │      │   │
│  │    │ ┌───────┐ │                                          │ ┌───────┐ │      │   │
│  │    │ │account│ │                                          │ │account│ │      │   │
│  │    │ │service│ │                                          │ │service│ │      │   │
│  │    │ └───────┘ │                                          │ └───────┘ │      │   │
│  │    └───────────┘                                          └───────────┘      │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │ Private Subnet (Database)                                                    │   │
│  │ AZ-a: 10.0.21.0/24                                    AZ-b: 10.0.22.0/24     │   │
│  │                         ┌───────────────┐                                    │   │
│  │    ┌───────────┐        │    Aurora     │        ┌───────────┐               │   │
│  │    │  Aurora   │◀──────▶│   Cluster     │◀──────▶│  Aurora   │               │   │
│  │    │  Writer   │        │   Endpoint    │        │  Reader   │               │   │
│  │    └───────────┘        └───────────────┘        └───────────┘               │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌──────────────────────────────────────────────────────────────────────────────┐   │
│  │ VPC Endpoints                                                                │   │
│  │  • S3 Gateway Endpoint                                                       │   │
│  │  • ECR API/DKR Interface Endpoint                                            │   │
│  │  • CloudWatch Logs Interface Endpoint                                        │   │
│  │  • Secrets Manager Interface Endpoint                                        │   │
│  │  • STS Interface Endpoint                                                    │   │
│  └──────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────┘

                                          │
                                          ▼
                                 ┌─────────────────┐
                                 │   Amazon SES    │
                                 │ (Cognito 集成)   │
                                 └─────────────────┘
```

### 1.3 与自研方案对比

| 组件 | 自研方案 | Cognito 方案 |
|------|---------|-------------|
| 认证服务 | Spring Authorization Server | Cognito User Pool |
| Session 存储 | ElastiCache Redis | Cognito 托管 |
| OTP 生成/存储 | 自研 + Redis | Cognito 内置 |
| 邮件发送 | notification-service | Cognito + SES |
| 用户目录 | Aurora | Cognito User Pool |
| EKS 服务数 | 3 个微服务 | 1 个 (account-service) |

**移除的组件：**
- ~~ElastiCache Redis~~ - Cognito 自行管理 token/session
- ~~auth-service~~ - Cognito 替代
- ~~notification-service~~ - Cognito 内置邮件功能

---

## 2. 外部层与安全

### 2.1 Route 53

| 配置项 | 值 |
|-------|-----|
| 托管区域 | xxx.com |
| 记录类型 | A (Alias) |
| 目标 | CloudFront Distribution |
| 路由策略 | Simple |
| TTL | 300s |

**DNS 记录规划：**

| 域名 | 类型 | 目标 | 说明 |
|------|------|------|------|
| auth.xxx.com | A (Alias) | CloudFront | 主域名 |
| api.xxx.com | A (Alias) | CloudFront | API 域名 |
| www.xxx.com | A (Alias) | CloudFront | 官网 |
| cognito.xxx.com | CNAME | Cognito Domain | Cognito 自定义域名 |

### 2.2 AWS WAF

**规则配置：**

| 规则名称 | 类型 | 动作 | 说明 |
|---------|------|------|------|
| AWSManagedRulesCommonRuleSet | 托管规则 | Block | 通用防护 |
| AWSManagedRulesKnownBadInputsRuleSet | 托管规则 | Block | 已知恶意输入 |
| AWSManagedRulesSQLiRuleSet | 托管规则 | Block | SQL 注入防护 |
| RateLimitRule | 自定义 | Block | 速率限制 (2000/5min) |
| GeoBlockRule | 自定义 | Block | 地理位置限制 (可选) |

**Cognito 专用 WAF 规则：**

```json
{
  "Name": "CognitoRateLimit",
  "Priority": 1,
  "Statement": {
    "RateBasedStatement": {
      "Limit": 100,
      "AggregateKeyType": "IP",
      "ScopeDownStatement": {
        "ByteMatchStatement": {
          "SearchString": "/oauth2/token",
          "FieldToMatch": { "UriPath": {} },
          "TextTransformations": [{ "Priority": 0, "Type": "LOWERCASE" }],
          "PositionalConstraint": "CONTAINS"
        }
      }
    }
  },
  "Action": { "Block": {} }
}
```

### 2.3 CloudFront

**Distribution 配置：**

| 配置项 | 值 |
|-------|-----|
| Price Class | PriceClass_200 |
| SSL Certificate | ACM (us-east-1) |
| Minimum Protocol Version | TLSv1.2_2021 |
| HTTP Version | HTTP/2 and HTTP/3 |
| Default Root Object | index.html |

**行为配置：**

| 路径模式 | Origin | 缓存策略 | 说明 |
|---------|--------|---------|------|
| `/api/*` | ALB | CachingDisabled | 后端 API |
| `*` (默认) | S3 | CachingOptimized | 前端静态资源 |

> **注意**: Cognito 端点不通过 CloudFront，前端直接访问 Cognito 域名

**自定义错误响应 (SPA 支持)：**

| HTTP 错误码 | 响应页面路径 | HTTP 响应码 | 缓存 TTL |
|------------|-------------|------------|---------|
| 403 | /index.html | 200 | 300s |
| 404 | /index.html | 200 | 300s |

### 2.4 ACM (Certificate Manager)

| 证书 | 区域 | 域名 | 用途 |
|------|------|------|------|
| CloudFront 证书 | us-east-1 | *.xxx.com, xxx.com | CloudFront HTTPS |
| ALB 证书 | ap-northeast-1 | *.xxx.com | ALB HTTPS |
| Cognito 证书 | us-east-1 | cognito.xxx.com | Cognito 自定义域名 |

---

## 3. 身份认证层 (Amazon Cognito)

### 3.1 Cognito User Pool 配置

| 配置项 | 值 | 说明 |
|-------|-----|------|
| User Pool 名称 | auth-platform-users | 用户池 |
| 登录标识符 | email | 使用邮箱登录 |
| 密码策略 | 8位以上，包含大小写和数字 | 强密码要求 |
| MFA | Optional | 可选 MFA |
| 邮箱验证 | Required | 必须验证邮箱 |
| 自助注册 | Enabled | 允许用户自行注册 |

**属性配置：**

| 属性 | 类型 | 必填 | 说明 |
|------|------|------|------|
| email | Standard | Yes | 邮箱地址 |
| given_name | Standard | No | 名 |
| family_name | Standard | No | 姓 |
| custom:user_type | Custom | No | 用户类型 |

### 3.2 App Client 配置

| 配置项 | 值 |
|-------|-----|
| Client 名称 | web-app |
| Client Secret | 不生成 (公开客户端) |
| Auth Flows | ALLOW_USER_SRP_AUTH, ALLOW_REFRESH_TOKEN_AUTH |
| OAuth Flows | Authorization code grant |
| OAuth Scopes | openid, profile, email |
| Callback URLs | https://www.xxx.com/callback |
| Logout URLs | https://www.xxx.com |

**Token 配置：**

| Token 类型 | 有效期 |
|-----------|--------|
| Access Token | 1 小时 |
| ID Token | 1 小时 |
| Refresh Token | 30 天 |

### 3.3 Cognito Domain

| 配置项 | 值 |
|-------|-----|
| 域名类型 | Custom domain |
| 域名 | cognito.xxx.com |
| 证书 | ACM (us-east-1) |

**Hosted UI 端点：**

| 端点 | URL |
|------|-----|
| 授权 | https://cognito.xxx.com/oauth2/authorize |
| Token | https://cognito.xxx.com/oauth2/token |
| UserInfo | https://cognito.xxx.com/oauth2/userInfo |
| 登出 | https://cognito.xxx.com/logout |
| JWKS | https://cognito-idp.{region}.amazonaws.com/{userPoolId}/.well-known/jwks.json |

### 3.4 Lambda Triggers (可选)

| Trigger | 用途 | 说明 |
|---------|------|------|
| Pre Sign-up | 注册验证 | 验证邮箱域名、阻止特定用户 |
| Post Confirmation | 注册后处理 | 同步用户到 Aurora 业务表 |
| Pre Token Generation | Token 定制 | 添加自定义 claims |
| Custom Message | 邮件定制 | 自定义邮件模板 |

### 3.5 邮件配置 (SES 集成)

| 配置项 | 值 |
|-------|-----|
| 邮件发送方式 | Amazon SES |
| FROM 地址 | noreply@xxx.com |
| SES 区域 | ap-northeast-1 |

**邮件模板配置：**

| 邮件类型 | 用途 |
|---------|------|
| Verification | 邮箱验证 |
| Forgot Password | 密码重置 |
| MFA Code | MFA 验证码 |

---

## 4. 网络层

### 4.1 VPC 配置

| 配置项 | 值 |
|-------|-----|
| VPC CIDR | 10.0.0.0/16 |
| DNS Hostnames | Enabled |
| DNS Resolution | Enabled |
| Tenancy | Default |

### 4.2 子网规划

| 子网名称 | CIDR | 可用区 | 类型 | 用途 |
|---------|------|--------|------|------|
| public-subnet-a | 10.0.1.0/24 | ap-northeast-1a | 公有 | NAT GW, ALB |
| public-subnet-b | 10.0.2.0/24 | ap-northeast-1c | 公有 | NAT GW, ALB |
| private-subnet-a | 10.0.11.0/24 | ap-northeast-1a | 私有 | EKS Worker |
| private-subnet-b | 10.0.12.0/24 | ap-northeast-1c | 私有 | EKS Worker |
| db-subnet-a | 10.0.21.0/24 | ap-northeast-1a | 私有 | Aurora |
| db-subnet-b | 10.0.22.0/24 | ap-northeast-1c | 私有 | Aurora |

### 4.3 路由表

**公有子网路由表：**

| 目标 | 下一跳 |
|------|--------|
| 10.0.0.0/16 | local |
| 0.0.0.0/0 | Internet Gateway |

**私有子网路由表 (AZ-a)：**

| 目标 | 下一跳 |
|------|--------|
| 10.0.0.0/16 | local |
| 0.0.0.0/0 | NAT Gateway (AZ-a) |

**私有子网路由表 (AZ-b)：**

| 目标 | 下一跳 |
|------|--------|
| 10.0.0.0/16 | local |
| 0.0.0.0/0 | NAT Gateway (AZ-b) |

### 4.4 安全组

**ALB 安全组 (sg-alb)：**

| 类型 | 协议 | 端口 | 来源 | 说明 |
|------|------|------|------|------|
| 入站 | HTTPS | 443 | CloudFront IP 范围 | CloudFront 流量 |
| 出站 | All | All | 0.0.0.0/0 | 允许所有出站 |

**EKS Worker 安全组 (sg-eks-worker)：**

| 类型 | 协议 | 端口 | 来源 | 说明 |
|------|------|------|------|------|
| 入站 | TCP | 10250 | sg-eks-control | Kubelet API |
| 入站 | TCP | 30000-32767 | sg-alb | NodePort 服务 |
| 入站 | All | All | sg-eks-worker | Worker 间通信 |
| 出站 | All | All | 0.0.0.0/0 | 允许所有出站 |

**Aurora 安全组 (sg-aurora)：**

| 类型 | 协议 | 端口 | 来源 | 说明 |
|------|------|------|------|------|
| 入站 | TCP | 3306 | sg-eks-worker | 来自 EKS |
| 入站 | TCP | 3306 | sg-lambda | 来自 Lambda Triggers |
| 出站 | All | All | 0.0.0.0/0 | 允许所有出站 |

### 4.5 VPC Endpoints

| 端点名称 | 类型 | 服务 | 说明 |
|---------|------|------|------|
| s3-endpoint | Gateway | com.amazonaws.ap-northeast-1.s3 | S3 访问 (免费) |
| ecr-api-endpoint | Interface | com.amazonaws.ap-northeast-1.ecr.api | ECR API |
| ecr-dkr-endpoint | Interface | com.amazonaws.ap-northeast-1.ecr.dkr | ECR Docker |
| logs-endpoint | Interface | com.amazonaws.ap-northeast-1.logs | CloudWatch Logs |
| secretsmanager-endpoint | Interface | com.amazonaws.ap-northeast-1.secretsmanager | Secrets Manager |
| sts-endpoint | Interface | com.amazonaws.ap-northeast-1.sts | STS (IRSA) |

---

## 5. 计算层

### 5.1 Amazon EKS

**集群配置：**

| 配置项 | 值 |
|-------|-----|
| Kubernetes 版本 | 1.34 |
| 集群端点访问 | Public |
| 日志类型 | api, audit, authenticator, controllerManager, scheduler |
| 加密 | AWS KMS (Secrets 加密) |

**节点组配置：**

| 配置项 | 值 |
|-------|-----|
| 节点组名称 | auth-platform-ng |
| AMI 类型 | Amazon Linux 2023 (AL2023_x86_64_STANDARD) |
| 实例类型 | m6i.large (生产) / t3.medium (开发) |
| 磁盘大小 | 50 GB (gp3) |
| 最小节点数 | 2 |
| 期望节点数 | 2 |
| 最大节点数 | 6 |
| 子网 | private-subnet-a, private-subnet-b |

> **注意**: 使用 Cognito 后，EKS 只运行 account-service，节点需求减少

**已安装的 Add-ons：**

| Add-on | 版本 | 说明 |
|--------|------|------|
| vpc-cni | 最新 | VPC CNI 网络插件 |
| coredns | 最新 | DNS 服务 |
| kube-proxy | 最新 | 网络代理 |
| aws-ebs-csi-driver | 最新 | EBS 存储驱动 |

**AWS Load Balancer Controller：**

```yaml
# Ingress 配置示例
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: auth-platform-ingress
  annotations:
    kubernetes.io/ingress.class: alb
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:ap-northeast-1:xxx:certificate/xxx
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTPS":443}]'
    alb.ingress.kubernetes.io/ssl-redirect: '443'
    alb.ingress.kubernetes.io/healthcheck-path: /actuator/health
spec:
  rules:
    - host: api.xxx.com
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: account-service
                port:
                  number: 8080
```

### 5.2 Amazon S3 (前端托管)

| 配置项 | 值 |
|-------|-----|
| 存储桶名称 | auth-platform-frontend-xxx |
| 区域 | ap-northeast-1 |
| 版本控制 | 启用 |
| 加密 | SSE-S3 |
| 公开访问 | 全部阻止 |
| 访问方式 | CloudFront OAC |

**存储桶策略 (仅允许 CloudFront)：**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowCloudFrontServicePrincipal",
      "Effect": "Allow",
      "Principal": {
        "Service": "cloudfront.amazonaws.com"
      },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::auth-platform-frontend-xxx/*",
      "Condition": {
        "StringEquals": {
          "AWS:SourceArn": "arn:aws:cloudfront::ACCOUNT_ID:distribution/DISTRIBUTION_ID"
        }
      }
    }
  ]
}
```

### 5.3 Lambda Functions (Cognito Triggers)

| Function | Runtime | 内存 | 超时 | 用途 |
|----------|---------|------|------|------|
| cognito-pre-signup | Python 3.12 | 128MB | 5s | 注册前验证 |
| cognito-post-confirmation | Python 3.12 | 256MB | 10s | 同步用户到 Aurora |
| cognito-pre-token | Python 3.12 | 128MB | 5s | 自定义 Token Claims |
| cognito-custom-message | Python 3.12 | 128MB | 5s | 自定义邮件内容 |

---

## 6. 存储与数据库层

### 6.1 Amazon Aurora MySQL

**集群配置：**

| 配置项 | 值 |
|-------|-----|
| 引擎 | Aurora MySQL 3.x (MySQL 8.0 兼容) |
| 集群标识符 | auth-platform-db |
| 实例类型 | db.r6g.large (生产) / db.t3.medium (开发) |
| Writer 实例数 | 1 |
| Reader 实例数 | 1 (生产) / 0 (开发) |
| 存储加密 | 启用 (AWS KMS) |
| 备份保留期 | 7 天 |
| 删除保护 | 启用 |

> **注意**: Aurora 现在只存储业务数据，用户认证数据在 Cognito

**参数组优化：**

| 参数 | 值 | 说明 |
|------|-----|------|
| character_set_server | utf8mb4 | 字符集 |
| collation_server | utf8mb4_unicode_ci | 排序规则 |
| max_connections | 500 | 最大连接数 (减少) |
| slow_query_log | 1 | 慢查询日志 |
| long_query_time | 1 | 慢查询阈值 (秒) |

**连接端点：**

| 端点类型 | 用途 | DNS |
|---------|------|-----|
| Cluster Endpoint | 读写操作 | auth-platform-db.cluster-xxx.ap-northeast-1.rds.amazonaws.com |
| Reader Endpoint | 只读操作 | auth-platform-db.cluster-ro-xxx.ap-northeast-1.rds.amazonaws.com |

### 6.2 已移除：ElastiCache Redis

~~使用 Cognito 后不再需要 ElastiCache：~~

| 原用途 | Cognito 替代方案 |
|-------|-----------------|
| Session 存储 | Cognito 托管 |
| OTP 缓存 | Cognito 内置 |
| Token 黑名单 | Cognito Token Revocation |
| 速率限制 | WAF + Cognito Advanced Security |

> **如果未来有其他缓存需求**（如业务数据缓存），可按需添加 ElastiCache

---

## 7. 安全与密钥管理

### 7.1 AWS Secrets Manager

| 密钥名称 | 用途 | 轮换 |
|---------|------|------|
| auth-platform/db-credentials | Aurora 数据库密码 | 30 天 |

> **已移除**: JWT 密钥、OAuth Secrets (由 Cognito 管理)

### 7.2 AWS KMS

| 密钥别名 | 用途 |
|---------|------|
| alias/auth-platform/rds | Aurora 加密 |
| alias/auth-platform/secrets | Secrets Manager 加密 |
| alias/auth-platform/eks | EKS Secrets 加密 |
| alias/auth-platform/s3 | S3 存储桶加密 |

### 7.3 IAM 角色

**EKS Node Role：**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage"
      ],
      "Resource": "*"
    }
  ]
}
```

**Pod IAM Role (IRSA) - account-service：**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:ap-northeast-1:*:secret:auth-platform/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "cognito-idp:AdminGetUser",
        "cognito-idp:AdminUpdateUserAttributes",
        "cognito-idp:AdminDisableUser",
        "cognito-idp:AdminEnableUser",
        "cognito-idp:ListUsers"
      ],
      "Resource": "arn:aws:cognito-idp:ap-northeast-1:*:userpool/*"
    }
  ]
}
```

**Lambda Trigger Role：**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "rds-db:connect"
      ],
      "Resource": "arn:aws:rds-db:ap-northeast-1:*:dbuser:*/lambda_user"
    }
  ]
}
```

### 7.4 Cognito Advanced Security (可选)

| 功能 | 说明 |
|------|------|
| 自适应认证 | 根据风险等级要求额外验证 |
| 被盗凭证检测 | 检测泄露的密码 |
| IP 地址阻止 | 阻止可疑 IP |
| 设备跟踪 | 识别已知设备 |

---

## 8. 监控与日志

### 8.1 CloudWatch

**日志组：**

| 日志组 | 保留期 | 来源 |
|-------|--------|------|
| /aws/eks/auth-platform/cluster | 30 天 | EKS 控制平面 |
| /aws/containerinsights/auth-platform/application | 14 天 | 应用日志 |
| /aws/lambda/cognito-triggers | 14 天 | Lambda Triggers |
| /aws/cognito/auth-platform-users | 30 天 | Cognito 用户活动 |
| /aws/rds/cluster/auth-platform-db/slowquery | 7 天 | 慢查询日志 |

**告警配置：**

| 告警名称 | 指标 | 阈值 | 说明 |
|---------|------|------|------|
| HighCPUUtilization | CPUUtilization | > 80% 5min | EKS 节点 CPU |
| HighMemoryUtilization | MemoryUtilization | > 85% 5min | EKS 节点内存 |
| DatabaseConnections | DatabaseConnections | > 400 | Aurora 连接数 |
| ALB5xxErrors | HTTPCode_Target_5XX_Count | > 10/min | ALB 5xx 错误 |
| CognitoSignInFailures | SignInSuccesses | < 90% | Cognito 登录失败率 |
| LambdaErrors | Errors | > 5/min | Lambda 错误 |

### 8.2 Cognito Metrics

| 指标 | 说明 |
|------|------|
| SignUpSuccesses | 注册成功数 |
| SignInSuccesses | 登录成功数 |
| TokenRefreshSuccesses | Token 刷新成功数 |
| FederationSuccesses | 联合登录成功数 |
| AccountTakeoverRisk | 账号接管风险 |

---

## 9. 成本估算

### 9.1 月度成本估算 (生产环境)

| 服务 | 规格 | 预估月费用 (USD) |
|------|------|-----------------|
| EKS 集群 | 1 集群 | $73 |
| EC2 (Worker) | 2 x m6i.large | $138 |
| Aurora MySQL | 1 Writer + 1 Reader (db.r6g.large) | $350 |
| NAT Gateway | 2 个 + 数据传输 | $100 |
| CloudFront | 100GB 传输 | $15 |
| S3 | 10GB 存储 | $0.25 |
| WAF | 100 万请求 | $6 |
| Route 53 | 1 托管区 + 100 万查询 | $1 |
| Secrets Manager | 2 密钥 | $1 |
| CloudWatch | 日志 + 指标 | $20 |
| **Cognito** | 10,000 MAU | **$0** (免费层) |
| **Cognito** | 50,000 MAU | **$275** |
| Lambda | Triggers (低频) | $1 |
| **总计 (10K MAU)** | | **~$705/月** |
| **总计 (50K MAU)** | | **~$980/月** |

### 9.2 与自研方案成本对比

| 项目 | 自研方案 | Cognito 方案 | 节省 |
|------|---------|-------------|------|
| EKS Worker | 3 x m6i.large ($207) | 2 x m6i.large ($138) | $69 |
| ElastiCache | cache.r6g.large ($300) | 不需要 ($0) | $300 |
| Secrets Manager | 5 密钥 ($2) | 2 密钥 ($1) | $1 |
| Cognito | - | 10K MAU ($0) | - |
| **总计** | **~$1,100/月** | **~$705/月** | **~$395/月 (36%)** |

### 9.3 Cognito 定价

| MAU | 价格 (USD) |
|-----|-----------|
| 0 - 10,000 | 免费 |
| 10,001 - 100,000 | $0.0055/MAU |
| 100,001 - 1,000,000 | $0.0046/MAU |
| 1,000,001+ | $0.00325/MAU |

> MAU = Monthly Active Users (每月活跃用户)

---

## 10. 灾难恢复

### 10.1 备份策略

| 资源 | 备份方式 | 频率 | 保留期 |
|------|---------|------|--------|
| Aurora | 自动快照 | 每日 | 7 天 |
| Aurora | 手动快照 | 每周 | 30 天 |
| Cognito | 无需备份 | - | AWS 托管 |
| S3 | 版本控制 | 实时 | 30 天 |
| Secrets | 版本控制 | 自动 | 所有版本 |

### 10.2 RTO/RPO

| 场景 | RTO | RPO |
|------|-----|-----|
| 单 AZ 故障 | < 5 分钟 | 0 |
| 数据库故障 | < 10 分钟 | < 1 分钟 |
| Cognito 故障 | N/A | N/A (AWS SLA 99.9%) |
| 区域故障 | < 4 小时 | < 1 小时 |

---

## 11. 部署清单

### 11.1 基础设施创建顺序

1. VPC 及子网
2. Internet Gateway 和 NAT Gateway
3. 路由表配置
4. 安全组创建
5. VPC Endpoints
6. **Cognito User Pool** ← 新增
7. **Cognito App Client** ← 新增
8. **Cognito Domain** ← 新增
9. **Lambda Triggers** ← 新增
10. EKS 集群
11. EKS 节点组
12. Aurora 集群
13. ~~ElastiCache 集群~~ ← 移除
14. S3 存储桶
15. Secrets Manager 密钥
16. ACM 证书
17. CloudFront Distribution
18. WAF Web ACL
19. Route 53 记录

### 11.2 IaC 工具推荐

- **Terraform**: 推荐用于整体基础设施管理
- **AWS CDK**: 如果团队熟悉 TypeScript/Python
- **eksctl**: EKS 集群快速创建
- **Helm**: Kubernetes 应用部署

### 11.3 Cognito Terraform 示例

```hcl
resource "aws_cognito_user_pool" "main" {
  name = "auth-platform-users"

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
    source_arn           = aws_ses_email_identity.main.arn
    from_email_address   = "noreply@xxx.com"
  }

  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true
  }

  lambda_config {
    pre_sign_up       = aws_lambda_function.pre_signup.arn
    post_confirmation = aws_lambda_function.post_confirmation.arn
    pre_token_generation = aws_lambda_function.pre_token.arn
  }
}

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
  allowed_oauth_flows_user_pool_client = true

  callback_urls = ["https://www.xxx.com/callback"]
  logout_urls   = ["https://www.xxx.com"]

  access_token_validity  = 1   # hours
  id_token_validity      = 1   # hours
  refresh_token_validity = 30  # days
}

resource "aws_cognito_user_pool_domain" "main" {
  domain          = "cognito"
  certificate_arn = aws_acm_certificate.cognito.arn
  user_pool_id    = aws_cognito_user_pool.main.id
}
```
