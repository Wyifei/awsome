# 部署自动化需求文档

## 概述

本文档描述 Auth Platform 的构建和部署自动化需求。部署脚本支持后端微服务和前端应用的自动化构建、打包和部署。

## 用户故事

### 1. 后端构建

#### 1.1 Maven 构建
作为开发者，我需要一键构建所有后端微服务的 JAR 包，以便快速验证代码变更。

**验收标准：**
- 支持构建单个服务或所有服务
- 支持 clean 构建选项
- 支持跳过测试选项
- 显示构建进度和结果
- 构建失败时提供清晰的错误信息

#### 1.2 Docker 镜像构建
作为运维工程师，我需要将微服务打包为 Docker 镜像，以便部署到 Kubernetes 集群。

**验收标准：**
- 基于 Maven 构建产物创建 Docker 镜像
- 支持自定义镜像标签
- 镜像命名遵循 ECR 仓库命名规范
- 显示镜像大小和构建时间

#### 1.3 ECR 镜像推送
作为运维工程师，我需要将 Docker 镜像推送到 ECR，以便 EKS 集群拉取部署。

**验收标准：**
- 自动登录 ECR
- 支持指定 AWS Account ID
- 支持指定 AWS Region
- 推送成功后显示镜像 URL

### 2. 后端部署

#### 2.1 环境配置获取
作为运维工程师，我需要自动从 Terraform 输出获取基础设施配置，以减少手动配置错误。

**验收标准：**
- 自动获取 Aurora 数据库端点
- 自动获取 Cognito User Pool ID
- 自动获取 S3 前端存储桶名称
- 自动获取 CloudFront 域名
- 自动获取 IRSA 角色 ARN
- 自动获取 SES 发件人邮箱

> **注意**: 用户头像存储在 Aurora PostgreSQL 数据库中，不再需要获取头像存储桶配置。

#### 2.2 数据库凭证获取
作为运维工程师，我需要自动从 Secrets Manager 获取数据库凭证，以确保安全性。

**验收标准：**
- 自动查找 RDS 托管的 Secret
- 解析 Secret 获取用户名和密码
- 不在日志中显示敏感信息

#### 2.3 Kubernetes Secrets 创建
作为运维工程师，我需要自动创建 Kubernetes Secrets，以便应用安全地访问配置。

**验收标准：**
- 为每个服务创建独立的 Secret
- user-service-secret: 数据库连接、Cognito 配置
- profile-service-secret: 数据库连接、Cognito、CloudFront 配置
- notification-service-secret: SES 配置
- 支持更新已存在的 Secret

> **注意**: 用户头像存储在 Aurora PostgreSQL 数据库中，profile-service 不再需要 S3 配置。

#### 2.4 Kustomize 部署
作为运维工程师，我需要使用 Kustomize 部署服务到 EKS，以支持多环境配置管理。

**验收标准：**
- 支持 production 和 dev 环境
- 使用 envsubst 进行变量替换
- 支持部署单个服务或所有服务
- 等待 Rollout 完成
- 显示部署状态

#### 2.5 部署验证
作为运维工程师，我需要验证部署结果，以确保服务正常运行。

**验收标准：**
- 显示 Pod 状态
- 显示 Service 状态
- 显示 Ingress 状态
- 显示 HPA 状态

### 3. 前端部署

#### 3.1 环境变量生成
作为前端开发者，我需要自动生成 .env.production 文件，以便前端应用连接正确的后端服务。

**验收标准：**
- 从 Terraform 输出获取 Cognito 配置
- 生成 VITE_COGNITO_USER_POOL_ID
- 生成 VITE_COGNITO_CLIENT_ID
- 生成 VITE_COGNITO_DOMAIN
- 生成 VITE_API_BASE_URL

#### 3.2 前端构建
作为前端开发者，我需要构建 React 应用，生成优化的静态资源。

**验收标准：**
- 执行 npm install 安装依赖
- 执行 npm run build 构建应用
- 生成 dist 目录

#### 3.3 S3 上传
作为运维工程师，我需要将前端资源上传到 S3，以便通过 CloudFront 分发。

**验收标准：**
- 使用 aws s3 sync 同步文件
- 删除 S3 中不存在于本地的文件
- HTML 文件设置 no-cache
- 其他文件设置长期缓存 (max-age=31536000)

#### 3.4 CloudFront 缓存失效
作为运维工程师，我需要清除 CloudFront 缓存，以确保用户获取最新版本。

**验收标准：**
- 创建缓存失效请求
- 失效路径为 /*
- 显示失效请求 ID

### 4. 脚本通用功能

#### 4.1 前置条件检查
作为运维工程师，我需要脚本自动检查前置条件，以避免因环境问题导致部署失败。

**验收标准：**
- 检查 Java 版本 (需要 Java 21)
- 检查 Maven 版本
- 检查 Docker 是否安装
- 检查 AWS CLI 是否配置
- 检查 kubectl 是否配置
- 检查 kustomize 是否可用
- 检查 jq 是否安装
- 检查 envsubst 是否可用

#### 4.2 帮助信息
作为运维工程师，我需要查看脚本的使用帮助，以了解可用选项。

**验收标准：**
- 使用 -h 或 --help 显示帮助
- 显示所有可用选项
- 显示使用示例

#### 4.3 Dry Run 模式
作为运维工程师，我需要预览部署操作，以在实际执行前确认配置正确。

**验收标准：**
- 使用 -n 或 --dry-run 启用预览模式
- 显示将要执行的操作
- 不实际执行任何变更

#### 4.4 彩色输出
作为运维工程师，我需要清晰的彩色输出，以快速识别成功、警告和错误信息。

**验收标准：**
- 成功信息显示绿色
- 警告信息显示黄色
- 错误信息显示红色
- 信息提示显示蓝色

## 技术约束

1. **Shell**: Bash (兼容 zsh)
2. **Java 版本**: Java 21 (Lombok 依赖)
3. **Maven 版本**: 3.8+
4. **AWS CLI 版本**: v2
5. **kubectl 版本**: 与 EKS 集群版本兼容
6. **Node.js 版本**: 18+ (前端构建)

## 文件引用

- 后端构建脚本: #[[file:application/scripts/build-backend.sh]]
- 后端部署脚本: #[[file:application/scripts/deploy-backend.sh]]
- 前端部署脚本: #[[file:application/scripts/deploy-frontend.sh]]
- 环境变量生成脚本: #[[file:application/scripts/generate-frontend-env.sh]]
- 部署指南: #[[file:application/docs/deployment-guide.md]]
