# AWS 基础设施需求文档

## 概述

本文档描述电动自行车统一身份认证平台 (Auth Platform) 的 AWS 基础设施需求。基础设施采用 Terraform 进行基础设施即代码 (IaC) 管理，支持多可用区高可用部署。

## 用户故事

### 1. 网络基础设施

#### 1.1 VPC 网络隔离
作为运维工程师，我需要一个隔离的 VPC 网络环境，以便安全地部署和运行应用服务。

**验收标准：**
- VPC CIDR 为 10.0.0.0/16，提供足够的 IP 地址空间
- 启用 DNS Hostnames 和 DNS Resolution
- 支持多可用区部署 (ap-northeast-1a, ap-northeast-1c)

#### 1.2 子网分层
作为架构师，我需要将网络分为公有子网、私有子网和数据库子网，以实现网络安全分层。

**验收标准：**
- 公有子网 (10.0.1.0/24, 10.0.2.0/24) 用于 NAT Gateway 和 ALB
- 私有子网 (10.0.11.0/24, 10.0.12.0/24) 用于 EKS Worker 节点
- 数据库子网 (10.0.21.0/24, 10.0.22.0/24) 用于 Aurora 数据库
- 每个子网类型跨两个可用区部署

#### 1.3 NAT Gateway 高可用
作为运维工程师，我需要每个可用区都有独立的 NAT Gateway，以确保私有子网的出站流量高可用。

**验收标准：**
- 每个可用区部署一个 NAT Gateway
- 私有子网路由表指向同可用区的 NAT Gateway
- NAT Gateway 故障不影响其他可用区

#### 1.4 VPC Endpoints
作为安全工程师，我需要通过 VPC Endpoints 访问 AWS 服务，以减少数据通过公网传输。

**验收标准：**
- S3 Gateway Endpoint (免费)
- ECR API/DKR Interface Endpoint
- CloudWatch Logs Interface Endpoint
- Secrets Manager Interface Endpoint
- STS Interface Endpoint (用于 IRSA)

### 2. 安全组配置

#### 2.1 ALB 安全组
作为安全工程师，我需要配置 ALB 安全组，仅允许来自 CloudFront 的 HTTPS 流量。

**验收标准：**
- 入站规则：仅允许 CloudFront IP 范围的 443 端口
- 出站规则：允许所有出站流量

#### 2.2 EKS Worker 安全组
作为安全工程师，我需要配置 EKS Worker 节点安全组，控制节点间和服务间通信。

**验收标准：**
- 允许 EKS 控制平面访问 Kubelet API (10250)
- 允许 ALB 访问 NodePort 范围 (30000-32767)
- 允许 Worker 节点间通信
- 允许所有出站流量

#### 2.3 Aurora 安全组
作为安全工程师，我需要配置 Aurora 安全组，仅允许来自 EKS Worker 的数据库连接。

**验收标准：**
- 入站规则：仅允许 EKS Worker 安全组的 5432 端口
- 出站规则：允许所有出站流量

### 3. 身份认证服务

#### 3.1 Cognito User Pool
作为产品经理，我需要使用 AWS Cognito 作为身份认证服务，以简化用户管理和认证流程。

**验收标准：**
- 使用邮箱作为登录标识符
- 密码策略：8位以上，包含大小写和数字
- 必须验证邮箱
- 允许用户自助注册

#### 3.2 Cognito App Client
作为开发者，我需要配置 Cognito App Client，支持 OAuth 2.0 授权码流程。

**验收标准：**
- 支持 Authorization Code Grant 流程
- OAuth Scopes: openid, profile, email
- Access Token 有效期 1 小时
- Refresh Token 有效期 30 天
- 配置回调 URL 和登出 URL

#### 3.3 SES 邮件集成
作为运维工程师，我需要配置 Cognito 使用 SES 发送验证邮件。

**验收标准：**
- 配置 SES 发件人邮箱
- 支持邮箱验证邮件
- 支持密码重置邮件

### 4. 容器编排

#### 4.1 EKS 集群
作为运维工程师，我需要一个托管的 Kubernetes 集群来运行微服务应用。

**验收标准：**
- Kubernetes 版本 1.31
- 启用控制平面日志 (api, audit, authenticator, controllerManager, scheduler)
- 使用 KMS 加密 Secrets
- 公开集群端点访问

#### 4.2 EKS 节点组
作为运维工程师，我需要配置 EKS 托管节点组，支持自动扩缩容。

**验收标准：**
- 使用 Amazon Linux 2023 AMI
- 实例类型：m6i.large (生产) / t3.medium (开发)
- 节点数量：最小 2，期望 2，最大 6
- 磁盘大小：50 GB (gp3)
- 部署在私有子网

#### 4.3 AWS Load Balancer Controller
作为运维工程师，我需要安装 AWS Load Balancer Controller，以支持 ALB Ingress。

**验收标准：**
- 通过 Helm 安装 AWS Load Balancer Controller
- 配置 IRSA 权限
- 支持创建 Application Load Balancer

#### 4.4 NGINX Ingress Controller
作为运维工程师，我需要安装 NGINX Ingress Controller，作为集群内部的反向代理。

**验收标准：**
- 通过 Helm 安装 NGINX Ingress Controller
- 副本数可配置 (默认 2)
- 支持 SSL 终止

### 5. 数据库服务

#### 5.1 Aurora PostgreSQL 集群
作为运维工程师，我需要一个高可用的 PostgreSQL 数据库集群来存储业务数据。

**验收标准：**
- Aurora PostgreSQL 16.4 版本
- 实例类型：db.r6g.large (生产) / db.t3.medium (开发)
- 1 个 Writer 实例 + 1 个 Reader 实例 (生产)
- 启用存储加密 (KMS)
- 备份保留期 7 天
- 启用删除保护

#### 5.2 数据库凭证管理
作为安全工程师，我需要使用 Secrets Manager 管理数据库凭证。

**验收标准：**
- Aurora 使用 RDS 托管的 Secret
- 支持自动密码轮换
- 应用通过 IRSA 访问 Secret

### 6. 存储服务

#### 6.1 ECR 镜像仓库
作为运维工程师，我需要 ECR 仓库来存储微服务的 Docker 镜像。

**验收标准：**
- 为每个微服务创建独立仓库
- 仓库命名格式：{project}-{environment}/{service}
- 启用镜像扫描
- 配置生命周期策略

#### 6.2 S3 前端存储桶
作为运维工程师，我需要 S3 存储桶来托管前端静态资源。

**验收标准：**
- 启用版本控制
- 使用 SSE-S3 加密
- 阻止所有公开访问
- 仅允许 CloudFront OAC 访问

### 7. CDN 和边缘服务

#### 7.1 CloudFront Distribution
作为运维工程师，我需要 CloudFront 作为 CDN，加速前端资源分发和 API 代理。

**验收标准：**
- 配置 S3 Origin (前端静态资源)
- 配置 ALB Origin (后端 API)
- 使用 ACM 证书启用 HTTPS
- 支持 HTTP/2 和 HTTP/3
- 配置自定义错误响应 (SPA 支持)

#### 7.2 WAF Web ACL
作为安全工程师，我需要 WAF 保护应用免受常见 Web 攻击。

**验收标准：**
- 启用 AWS 托管规则集 (Common, KnownBadInputs, SQLi)
- 配置速率限制规则 (2000/5min)
- 配置 Cognito Token 端点速率限制 (100/5min)
- 关联到 CloudFront Distribution

### 8. 监控和可观测性

#### 8.1 AWS Managed Prometheus
作为运维工程师，我需要托管的 Prometheus 服务来收集和存储指标数据。

**验收标准：**
- 创建 Prometheus Workspace
- 配置 Remote Write 端点
- 配置 IRSA 权限

#### 8.2 Grafana 可视化
作为运维工程师，我需要 Grafana 来可视化监控指标。

**验收标准：**
- 在 EKS 中部署 Grafana
- 配置 Prometheus 数据源
- 通过 NGINX Ingress 的 /grafana 路径访问
- 支持用户名密码登录

#### 8.3 ADOT Collector
作为运维工程师，我需要 ADOT Collector 来收集和转发指标数据。

**验收标准：**
- 可选启用 ADOT Collector (替代 Prometheus Helm chart)
- 配置 IRSA 权限
- 支持 Prometheus Remote Write

### 9. IAM 和安全

#### 9.1 KMS 密钥管理
作为安全工程师，我需要 KMS 密钥来加密敏感数据。

**验收标准：**
- RDS 加密密钥
- EKS Secrets 加密密钥
- S3 存储桶加密密钥
- Secrets Manager 加密密钥

#### 9.2 IRSA (IAM Roles for Service Accounts)
作为安全工程师，我需要配置 IRSA，让 Pod 使用 IAM 角色访问 AWS 服务。

**验收标准：**
- 配置 OIDC Provider
- 创建应用服务角色 (访问 Secrets Manager, Cognito, S3, SES)
- 创建 AWS Load Balancer Controller 角色
- 创建 ADOT Collector 角色

## 技术约束

1. **区域**: ap-northeast-1 (东京)
2. **Terraform 版本**: >= 1.0
3. **Provider 版本**: AWS Provider >= 5.0, Kubernetes Provider >= 2.0, Helm Provider >= 2.0
4. **命名规范**: {project_name}-{environment}-{resource}
5. **标签策略**: 所有资源必须包含 Project 和 Environment 标签

## 文件引用

- 主模块编排: #[[file:application/infrastructure/main.tf]]
- 变量定义: #[[file:application/infrastructure/variables.tf]]
- 输出定义: #[[file:application/infrastructure/outputs.tf]]
- 架构文档: #[[file:application/docs/infrastructure-architecture.md]]
