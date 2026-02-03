# AWS 基础设施实现任务

## 任务概述

本文档列出 Auth Platform AWS 基础设施的实现任务。所有任务已完成实现。

## 任务列表

- [x] 1. VPC 网络层 (001_vpc)
  - [x] 1.1 创建 VPC 和 DNS 配置
  - [x] 1.2 创建公有子网 (2 个可用区)
  - [x] 1.3 创建私有子网 (2 个可用区)
  - [x] 1.4 创建数据库子网 (2 个可用区)
  - [x] 1.5 创建 Internet Gateway
  - [x] 1.6 创建 NAT Gateway (每个可用区)
  - [x] 1.7 配置路由表
  - [x] 1.8 创建 VPC Endpoints (S3, ECR, CloudWatch, Secrets Manager, STS)
  - [x] 1.9 创建数据库子网组

- [x] 2. 安全组配置 (002_security)
  - [x] 2.1 创建 ALB 安全组
  - [x] 2.2 创建 EKS 控制平面安全组
  - [x] 2.3 创建 EKS Worker 安全组
  - [x] 2.4 创建 Aurora 安全组
  - [x] 2.5 配置安全组规则

- [x] 3. WAF 配置 (002_security/waf)
  - [x] 3.1 创建 WAF Web ACL (us-east-1)
  - [x] 3.2 配置 AWS 托管规则集
  - [x] 3.3 配置速率限制规则
  - [x] 3.4 配置 Cognito Token 端点速率限制

- [x] 4. IAM 和密钥管理 (003_iam)
  - [x] 4.1 创建 RDS 加密 KMS 密钥
  - [x] 4.2 创建 EKS Secrets 加密 KMS 密钥
  - [x] 4.3 创建 S3 加密 KMS 密钥

- [x] 5. ECR 镜像仓库 (004_ecr)
  - [x] 5.1 创建 user-service 仓库
  - [x] 5.2 创建 profile-service 仓库
  - [x] 5.3 创建 notification-service 仓库
  - [x] 5.4 配置镜像生命周期策略

- [x] 6. Cognito 身份认证 (005_cognito)
  - [x] 6.1 创建 Cognito User Pool
  - [x] 6.2 配置密码策略
  - [x] 6.3 配置邮箱验证
  - [x] 6.4 创建 App Client
  - [x] 6.5 配置 OAuth 流程
  - [x] 6.6 配置 SES 邮件集成

- [x] 7. 监控服务 (006_monitoring)
  - [x] 7.1 创建 AWS Managed Prometheus Workspace
  - [x] 7.2 配置 Remote Write 端点
  - [x] 7.3 创建 Prometheus Remote Write IAM 角色
  - [x] 7.4 创建 Grafana IAM 角色

- [x] 8. EKS 集群 (007_eks)
  - [x] 8.1 创建 EKS 集群 IAM 角色
  - [x] 8.2 创建 EKS 集群
  - [x] 8.3 配置集群日志
  - [x] 8.4 配置 Secrets 加密
  - [x] 8.5 创建节点组 IAM 角色
  - [x] 8.6 创建托管节点组
  - [x] 8.7 配置 OIDC Provider
  - [x] 8.8 创建应用服务 IRSA 角色
  - [x] 8.9 创建 AWS Load Balancer Controller IRSA 角色
  - [x] 8.10 创建 ADOT Collector IRSA 角色

- [x] 9. Aurora PostgreSQL (008_rds)
  - [x] 9.1 创建 Aurora 集群参数组
  - [x] 9.2 创建 Aurora 集群
  - [x] 9.3 配置 RDS 托管密码
  - [x] 9.4 创建 Writer 实例
  - [x] 9.5 创建 Reader 实例 (生产环境)
  - [x] 9.6 配置备份策略
  - [x] 9.7 启用删除保护

- [x] 10. Kubernetes 资源 (009_kubernetes)
  - [x] 10.1 安装 AWS Load Balancer Controller
  - [x] 10.2 安装 NGINX Ingress Controller
  - [x] 10.3 创建 ALB Ingress 资源
  - [x] 10.4 配置 Grafana Helm Release
  - [x] 10.5 配置 ADOT Collector (可选)
  - [x] 10.6 配置 Prometheus Helm Release (可选)
  - [x] 10.7 创建 PostgreSQL 客户端 Pod (可选)
  - [x] 10.8 配置 EBS CSI Driver StorageClass

- [x] 11. S3 存储桶 (010_s3)
  - [x] 11.1 创建前端存储桶
  - [x] 11.2 配置前端存储桶版本控制
  - [x] 11.3 配置前端存储桶加密
  - [x] 11.4 阻止前端存储桶公开访问

- [x] 12. CloudFront CDN (011_cloudfront)
  - [x] 12.1 创建 CloudFront OAC
  - [x] 12.2 创建 CloudFront Distribution
  - [x] 12.3 配置 S3 Origin
  - [x] 12.4 配置 ALB Origin
  - [x] 12.5 配置默认缓存行为 (S3)
  - [x] 12.6 配置 API 缓存行为 (ALB)
  - [x] 12.7 配置自定义错误响应 (SPA)
  - [x] 12.8 关联 WAF Web ACL

- [x] 13. 资源关联
  - [x] 13.1 配置 S3 存储桶策略 (允许 CloudFront)
  - [x] 13.2 添加 Aurora 安全组规则 (允许 EKS 节点组)

## 文件引用

- 主模块编排: #[[file:application/infrastructure/main.tf]]
- VPC 模块: #[[file:application/infrastructure/001_vpc/main.tf]]
- 安全模块: #[[file:application/infrastructure/002_security/main.tf]]
- IAM 模块: #[[file:application/infrastructure/003_iam/main.tf]]
- ECR 模块: #[[file:application/infrastructure/004_ecr/main.tf]]
- Cognito 模块: #[[file:application/infrastructure/005_cognito/main.tf]]
- 监控模块: #[[file:application/infrastructure/006_monitoring/main.tf]]
- EKS 模块: #[[file:application/infrastructure/007_eks/main.tf]]
- RDS 模块: #[[file:application/infrastructure/008_rds/main.tf]]
- Kubernetes 模块: #[[file:application/infrastructure/009_kubernetes/main.tf]]
- S3 模块: #[[file:application/infrastructure/010_s3/main.tf]]
- CloudFront 模块: #[[file:application/infrastructure/011_cloudfront/main.tf]]
