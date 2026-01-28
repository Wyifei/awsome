# Auth Platform 部署指南

本文档描述了 Auth Platform 微服务的构建、打包和部署流程。

## 目录

- [概述](#概述)
- [前置条件](#前置条件)
- [部署脚本概览](#部署脚本概览)
- [后端服务部署](#后端服务部署)
- [前端部署](#前端部署)
- [环境变量设置](#环境变量设置)
- [Kubernetes 部署详解](#kubernetes-部署详解)
- [环境配置](#环境配置)
- [CI/CD 集成](#cicd-集成)
- [故障排除](#故障排除)

## 概述

### 微服务列表

| 服务 | 描述 | 端口 |
|------|------|------|
| user-service | 用户管理、认证集成 | 8080 |
| profile-service | 用户资料、头像管理 | 8080 |
| notification-service | 邮件通知服务 | 8080 |

### 技术栈

- **运行时**: Java 21, Spring Boot 3.2
- **构建工具**: Maven 3.8+
- **容器化**: Docker
- **编排**: Kubernetes (EKS 1.31)
- **镜像仓库**: Amazon ECR
- **配置管理**: Kustomize

### 环境信息

| 配置项 | 值 |
|--------|-----|
| AWS 区域 | `ap-northeast-1` |
| 项目名称 | `auth-platform` |
| 环境 | `production` / `dev` |
| EKS 集群名称 | `auth-platform-production` |
| Kubernetes 命名空间 | `auth-platform` |

## 前置条件

### 本地开发环境

```bash
# Java 21 (必须使用 Java 21，Lombok 依赖此版本)
java -version

# Maven 3.8+
mvn -version

# Docker
docker --version

# kubectl
kubectl version --client

# AWS CLI v2
aws --version

# kustomize (可选，kubectl 已内置)
kustomize version

# jq (JSON 解析)
jq --version

# envsubst (变量替换)
envsubst --version
```

### AWS 配置

```bash
# 配置 AWS 凭证
aws configure

# 验证身份并获取 Account ID
aws sts get-caller-identity
```

## 部署脚本概览

项目在 `scripts/` 目录下提供了以下部署脚本：

| 脚本 | 用途 | 说明 |
|------|------|------|
| `build-backend.sh` | 构建后端服务 | Maven 构建、Docker 镜像构建和推送到 ECR |
| `deploy-backend.sh` | 部署后端服务 | 从 Terraform 获取配置、创建 Secrets、部署到 EKS |
| `deploy-frontend.sh` | 部署前端 | 生成环境变量、构建 React 应用、部署到 S3 + CloudFront |
| `generate-frontend-env.sh` | 生成前端环境变量 | 单独生成 `.env.production` 文件（已集成到 deploy-frontend.sh） |

### 快速部署命令

```bash
# 后端：构建并推送镜像
./scripts/build-backend.sh -d -p --skip-tests -r $(aws sts get-caller-identity --query Account --output text) all

# 后端：部署到 EKS（包含构建）
./scripts/deploy-backend.sh -b --skip-tests all

# 后端：仅部署（不构建）
./scripts/deploy-backend.sh all

# 前端：构建并部署
./scripts/deploy-frontend.sh
```

## 后端服务部署

### 使用 build-backend.sh 构建

`build-backend.sh` 用于构建后端微服务的 JAR 包和 Docker 镜像。

#### 完整参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-h, --help` | 显示帮助信息 | - |
| `-c, --clean` | 构建前执行 clean | false |
| `-s, --skip-tests` | 跳过单元测试 | false |
| `-d, --docker` | 构建 Docker 镜像 | false |
| `-p, --push` | 推送镜像到 ECR (需要 -d) | false |
| `-e, --env ENV` | 环境 (dev/production) | production |
| `-t, --tag TAG` | Docker 镜像标签 | latest |
| `-r, --registry ID` | AWS Account ID | - |

#### 常用命令

```bash
# 仅构建 JAR
./scripts/build-backend.sh all

# 构建并创建 Docker 镜像（本地）
./scripts/build-backend.sh -d all

# 构建并推送到 ECR
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
./scripts/build-backend.sh -d -p --skip-tests -r $AWS_ACCOUNT_ID all

# 构建单个服务
./scripts/build-backend.sh -d -p --skip-tests -r $AWS_ACCOUNT_ID user-service

# 使用 Git commit hash 作为标签
./scripts/build-backend.sh -d -p -r $AWS_ACCOUNT_ID -t $(git rev-parse --short HEAD) all
```

### 使用 deploy-backend.sh 部署

`deploy-backend.sh` 用于部署后端服务到 EKS，支持自动获取 Terraform 配置和创建 Kubernetes Secrets。

#### 完整参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-h, --help` | 显示帮助信息 | - |
| `-b, --build` | 部署前构建并推送镜像 | false |
| `-t, --tag TAG` | Docker 镜像标签 | latest |
| `-e, --env ENV` | 环境 (dev/production) | production |
| `-s, --skip-secrets` | 跳过创建 Secrets | false |
| `-c, --create-secrets` | 仅创建 Secrets | false |
| `-n, --dry-run` | 预览模式 | false |
| `--skip-tests` | 构建时跳过测试 (需要 -b) | false |
| `--region REGION` | AWS 区域 | ap-northeast-1 |

#### 常用命令

```bash
# 部署所有服务（使用已有镜像）
./scripts/deploy-backend.sh all

# 构建并部署所有服务
./scripts/deploy-backend.sh -b --skip-tests all

# 部署单个服务
./scripts/deploy-backend.sh user-service

# 仅创建/更新 Secrets
./scripts/deploy-backend.sh -c

# 预览部署（不实际执行）
./scripts/deploy-backend.sh -n all

# 跳过 Secrets 创建（使用已有 Secrets）
./scripts/deploy-backend.sh -s all
```

#### 部署流程

`deploy-backend.sh` 会自动执行以下步骤：

1. **获取 AWS 配置** - 从 AWS CLI 获取 Account ID、Region 等
2. **获取 Terraform 输出** - 自动从 `infrastructure/` 目录获取：
   - Aurora 数据库端点
   - Cognito User Pool ID
   - S3 头像存储桶
   - CloudFront 域名
   - IRSA 角色 ARN
   - SES 发件人邮箱
3. **获取数据库密码** - 从 Secrets Manager (RDS 管理的 Secret) 获取
4. **创建 Kubernetes Secrets** - 为每个服务创建配置 Secret
5. **构建镜像** (可选) - 如果指定了 `-b` 参数
6. **部署到 EKS** - 使用 Kustomize 部署服务

## 前端部署

### 使用 deploy-frontend.sh 部署

`deploy-frontend.sh` 用于构建 React 前端应用并部署到 S3 + CloudFront。

#### 完整参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-h, --help` | 显示帮助信息 | - |
| `-s, --skip-build` | 跳过构建，直接上传 dist | false |
| `-n, --no-invalidate` | 跳过 CloudFront 缓存失效 | false |
| `-d, --dry-run` | 预览模式 | false |

#### 常用命令

```bash
# 完整部署（构建 + 上传 + 缓存失效）
./scripts/deploy-frontend.sh

# 仅上传已构建的文件
./scripts/deploy-frontend.sh --skip-build

# 预览部署操作
./scripts/deploy-frontend.sh --dry-run
```

#### 部署流程

`deploy-frontend.sh` 会自动执行以下步骤：

1. **获取基础设施信息** - 从 Terraform 输出获取 S3 Bucket、CloudFront Distribution、Cognito 配置
2. **生成环境变量** - 自动生成 `.env.production` 文件（包含 Cognito 和 API 配置）
3. **安装依赖** - `npm install`
4. **构建应用** - `npm run build`
5. **上传到 S3** - 使用 `aws s3 sync` 同步 `dist/` 目录
6. **清除 CDN 缓存** - 创建 CloudFront 缓存失效

### 单独生成环境变量（可选）

如果只需要生成环境变量文件而不部署：

```bash
./scripts/generate-frontend-env.sh
```

生成的 `.env.production` 文件包含：
- `VITE_COGNITO_USER_POOL_ID` - Cognito 用户池 ID
- `VITE_COGNITO_CLIENT_ID` - Cognito 客户端 ID
- `VITE_COGNITO_DOMAIN` - Cognito 域名
- `VITE_API_BASE_URL` - API 基础 URL（通过 CloudFront 代理）

## 环境变量设置

### 步骤 1: 从 Terraform 获取基础设施值

```bash
cd infrastructure

# 获取所有需要的输出值
terraform output -json > /tmp/tf-outputs.json

# 或者单独获取
terraform output aurora_cluster_endpoint
terraform output cognito_user_pool_id
terraform output s3_avatars_bucket
terraform output cloudfront_domain_name
terraform output app_service_role_arn
```

### 步骤 2: 设置环境变量

```bash
# 获取 AWS Account ID
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "AWS Account ID: $AWS_ACCOUNT_ID"

# 基本配置
export AWS_REGION="ap-northeast-1"
export PROJECT_NAME="auth-platform"
export ENVIRONMENT="production"
export EKS_CLUSTER_NAME="auth-platform-production"

# IRSA 角色 ARN
export APP_SERVICE_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/auth-platform-production-app-service-role"

# ECR Registry
export ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

# 从 Terraform 输出获取 (在 infrastructure 目录执行)
cd infrastructure
export AURORA_CLUSTER_ENDPOINT=$(terraform output -raw aurora_cluster_endpoint)
export COGNITO_USER_POOL_ID=$(terraform output -raw cognito_user_pool_id)
export S3_AVATARS_BUCKET=$(terraform output -raw s3_avatars_bucket)
export CLOUDFRONT_DOMAIN=$(terraform output -raw cloudfront_domain_name)
cd ..

# 数据库用户名 (Aurora 默认用户名是 postgres)
export DB_USERNAME="postgres"

# 需要手动设置的值
export DB_PASSWORD="<从 Secrets Manager 获取>"
export SES_FROM_ADDRESS="noreply@your-domain.com"

# 验证变量
echo "Aurora Endpoint: $AURORA_CLUSTER_ENDPOINT"
echo "Cognito User Pool: $COGNITO_USER_POOL_ID"
echo "S3 Avatars Bucket: $S3_AVATARS_BUCKET"
echo "CloudFront Domain: $CLOUDFRONT_DOMAIN"
```

### 步骤 3: 保存环境变量文件（可选）

> **推荐**: 使用 `deploy-backend.sh` 脚本会自动获取所有配置，无需手动设置环境变量。

如需手动设置环境变量：

```bash
cat > ~/.auth-platform-env << EOF
# AWS 基本配置
export AWS_ACCOUNT_ID=\$(aws sts get-caller-identity --query Account --output text)
export AWS_REGION="ap-northeast-1"
export PROJECT_NAME="auth-platform"
export ENVIRONMENT="production"
export EKS_CLUSTER_NAME="auth-platform-production"

# ECR 和 IRSA
export ECR_REGISTRY="\${AWS_ACCOUNT_ID}.dkr.ecr.\${AWS_REGION}.amazonaws.com"
export APP_SERVICE_ROLE_ARN="arn:aws:iam::\${AWS_ACCOUNT_ID}:role/auth-platform-production-app-service-role"

# 基础设施值 (从 terraform output 获取后填入实际值)
export AURORA_CLUSTER_ENDPOINT="${AURORA_CLUSTER_ENDPOINT}"
export COGNITO_USER_POOL_ID="${COGNITO_USER_POOL_ID}"
export S3_AVATARS_BUCKET="${S3_AVATARS_BUCKET}"
export CLOUDFRONT_DOMAIN="${CLOUDFRONT_DOMAIN}"

# Secrets (请替换为实际值)
export DB_PASSWORD="<your-db-password>"
export SES_FROM_ADDRESS="${SES_FROM_ADDRESS:-noreply@example.com}"
EOF

# 加载环境变量
source ~/.auth-platform-env
```

### 从 Secrets Manager 获取数据库密码

Aurora 使用 RDS 自动管理的 Secret，需要先获取 Secret ARN：

```bash
# 方法 1: 从 Terraform 输出获取 RDS Secret ARN
cd infrastructure
RDS_SECRET_ARN=$(terraform output -raw aurora_master_secret_arn)
cd ..

# 方法 2: 通过 AWS CLI 查找 RDS 管理的 Secret
RDS_SECRET_ARN=$(aws secretsmanager list-secrets \
  --region ap-northeast-1 \
  --query "SecretList[?contains(Name, 'rds!cluster')].ARN | [0]" \
  --output text)

echo "RDS Secret ARN: $RDS_SECRET_ARN"

# 获取 Aurora 凭证
DB_PASSWORD=$(aws secretsmanager get-secret-value \
  --secret-id "$RDS_SECRET_ARN" \
  --region ap-northeast-1 \
  --query SecretString \
  --output text | jq -r '.password')

DB_USERNAME=$(aws secretsmanager get-secret-value \
  --secret-id "$RDS_SECRET_ARN" \
  --region ap-northeast-1 \
  --query SecretString \
  --output text | jq -r '.username')

echo "DB_USERNAME: $DB_USERNAME"
echo "DB_PASSWORD: $DB_PASSWORD"
```

> **注意**: RDS 自动管理的 Secret (格式为 `rds!cluster-*`) 中的密码才是正确的。
> 请勿使用 `auth-platform-production/aurora-credentials` Secret，该 Secret 中的密码可能与实际密码不同步。

> **注意**: 数据库密码可能包含特殊字符 (`|`, `]`, `<`, `>`, `&` 等)。
> 在创建 Kubernetes Secret 时，建议使用 `kubectl create secret` 命令而不是通过 kustomize 的 envsubst 替换，
> 以避免 shell 转义问题。

## 手动构建

如果需要手动构建（不使用脚本）：

```bash
# 进入服务目录
cd services/user-service

# Maven 构建
mvn clean package -DskipTests

# 构建 Docker 镜像
docker build -t user-service:latest .
```

## Docker 镜像

### ECR 仓库命名规范

| 环境 | 仓库名称 | 完整 URL |
|------|----------|----------|
| Production | `auth-platform-production/user-service` | `${ECR_REGISTRY}/auth-platform-production/user-service` |
| Production | `auth-platform-production/profile-service` | `${ECR_REGISTRY}/auth-platform-production/profile-service` |
| Production | `auth-platform-production/notification-service` | `${ECR_REGISTRY}/auth-platform-production/notification-service` |
| Dev | `auth-platform-dev/user-service` | `${ECR_REGISTRY}/auth-platform-dev/user-service` |

### 手动推送镜像

```bash
# 加载环境变量
source ~/.auth-platform-env

# 设置镜像标签
IMAGE_TAG="v1.0.0"

# ECR 登录
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $ECR_REGISTRY

# 推送 user-service
docker tag user-service:$IMAGE_TAG $ECR_REGISTRY/auth-platform-production/user-service:$IMAGE_TAG
docker push $ECR_REGISTRY/auth-platform-production/user-service:$IMAGE_TAG

# 推送 profile-service
docker tag profile-service:$IMAGE_TAG $ECR_REGISTRY/auth-platform-production/profile-service:$IMAGE_TAG
docker push $ECR_REGISTRY/auth-platform-production/profile-service:$IMAGE_TAG

# 推送 notification-service
docker tag notification-service:$IMAGE_TAG $ECR_REGISTRY/auth-platform-production/notification-service:$IMAGE_TAG
docker push $ECR_REGISTRY/auth-platform-production/notification-service:$IMAGE_TAG
```

### 查看 ECR 镜像

```bash
# 加载环境变量
source ~/.auth-platform-env

# 列出所有镜像
aws ecr describe-images --repository-name auth-platform-production/user-service --region $AWS_REGION

# 列出最新 5 个镜像
aws ecr describe-images \
  --repository-name auth-platform-production/user-service \
  --region $AWS_REGION \
  --query 'sort_by(imageDetails,&imagePushedAt)[-5:].{Tag:imageTags[0],Pushed:imagePushedAt,Size:imageSizeInBytes}' \
  --output table
```

## Kubernetes 部署详解

### 配置 kubectl

```bash
# 加载环境变量
source ~/.auth-platform-env

# 更新 kubeconfig
aws eks update-kubeconfig --name $EKS_CLUSTER_NAME --region $AWS_REGION

# 验证连接
kubectl get nodes
kubectl get ns
```

### Kustomize 目录结构

```
services/{service}/kustomize/
├── base/
│   ├── kustomization.yaml
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   └── servicemonitor.yaml
└── overlays/
    ├── dev/
    │   ├── kustomization.yaml
    │   └── patches/
    └── production/
        ├── kustomization.yaml
        ├── ingress.yaml
        ├── hpa.yaml
        ├── pdb.yaml
        └── patches/
```

### 部署到 Production

```bash
# 加载环境变量
source ~/.auth-platform-env

# 设置镜像标签
IMAGE_TAG="v1.0.0"

# 使用 envsubst 进行变量替换 (支持密码中的特殊字符)
# 定义需要替换的变量列表
export ENVSUBST_VARS='${AWS_ACCOUNT_ID} ${APP_SERVICE_ROLE_ARN} ${AURORA_CLUSTER_ENDPOINT} ${DB_PASSWORD} ${COGNITO_USER_POOL_ID} ${S3_AVATARS_BUCKET} ${CLOUDFRONT_DOMAIN} ${SES_FROM_ADDRESS}'

# 部署所有服务
for SERVICE in user-service profile-service notification-service; do
  echo "Deploying $SERVICE..."

  kustomize build services/${SERVICE}/kustomize/overlays/production | \
    envsubst "$ENVSUBST_VARS" | \
    kubectl apply -f -
done

# 等待部署完成
kubectl rollout status deployment/user-service -n auth-platform
kubectl rollout status deployment/profile-service -n auth-platform
kubectl rollout status deployment/notification-service -n auth-platform
```

### 部署单个服务

```bash
# 加载环境变量
source ~/.auth-platform-env

# 定义需要替换的变量列表
export ENVSUBST_VARS='${AWS_ACCOUNT_ID} ${APP_SERVICE_ROLE_ARN} ${AURORA_CLUSTER_ENDPOINT} ${DB_PASSWORD} ${COGNITO_USER_POOL_ID} ${S3_AVATARS_BUCKET} ${CLOUDFRONT_DOMAIN} ${SES_FROM_ADDRESS}'

# 部署 user-service
kustomize build services/user-service/kustomize/overlays/production | \
  envsubst "$ENVSUBST_VARS" | \
  kubectl apply -f -

# 等待部署完成
kubectl rollout status deployment/user-service -n auth-platform
```

### 更新镜像版本

```bash
# 加载环境变量
source ~/.auth-platform-env

# 方法 1: 使用 kubectl set image (快速更新)
kubectl set image deployment/user-service \
  user-service=$ECR_REGISTRY/auth-platform-production/user-service:v1.1.0 \
  -n auth-platform

# 方法 2: 使用 kustomize (推荐)
cd services/user-service/kustomize/overlays/production
kustomize edit set image user-service=$ECR_REGISTRY/auth-platform-production/user-service:v1.1.0
kustomize build . | envsubst "$ENVSUBST_VARS" | kubectl apply -f -
cd -
```

### 部署到 Dev 环境

```bash
# 加载环境变量
source ~/.auth-platform-env

# 定义需要替换的变量列表
export ENVSUBST_VARS='${AWS_ACCOUNT_ID} ${AURORA_CLUSTER_ENDPOINT} ${DB_PASSWORD} ${COGNITO_USER_POOL_ID} ${S3_AVATARS_BUCKET} ${CLOUDFRONT_DOMAIN} ${SES_FROM_ADDRESS}'

# 部署所有服务到 dev
for SERVICE in user-service profile-service notification-service; do
  echo "Deploying $SERVICE to dev..."

  kustomize build services/${SERVICE}/kustomize/overlays/dev | \
    envsubst "$ENVSUBST_VARS" | \
    kubectl apply -f -
done
```

### 验证部署

```bash
# 查看所有资源
kubectl get all -n auth-platform

# 检查 Pod 状态
kubectl get pods -n auth-platform -o wide

# 检查服务
kubectl get svc -n auth-platform

# 检查 Ingress
kubectl get ingress -n auth-platform

# 检查 HPA 状态
kubectl get hpa -n auth-platform

# 查看 Pod 日志
kubectl logs -n auth-platform -l app=user-service --tail=100 -f

# 检查 Pod 详情
kubectl describe pod -n auth-platform -l app=user-service
```

### 测试服务

```bash
# 端口转发 user-service
kubectl port-forward -n auth-platform svc/user-service 8080:8080 &

# 测试健康检查
curl http://localhost:8080/api/actuator/health

# 测试 Prometheus metrics
curl http://localhost:8080/api/actuator/prometheus

# 停止端口转发
pkill -f "port-forward.*user-service"
```

## 环境配置

### Dev 环境

| 配置项 | 值 |
|--------|-----|
| 副本数 | 1 |
| CPU Request | 50m |
| Memory Request | 128Mi |
| 日志级别 | DEBUG |
| HPA | 禁用 |

### Production 环境

| 配置项 | 值 |
|--------|-----|
| 副本数 | 2-10 (HPA) |
| CPU Request | 250m |
| Memory Request | 512Mi |
| 日志级别 | INFO |
| HPA | 启用 (CPU 70%, Memory 80%) |
| PDB | minAvailable: 1 |

### Secrets 管理

生产环境使用 Kubernetes Secrets，建议后续迁移到 External Secrets Operator。

> **重要**: 由于数据库密码可能包含特殊字符，**强烈建议**使用 `kubectl create secret` 命令直接创建 Secrets，
> 而不是通过 kustomize 的变量替换 (envsubst)。

#### 推荐方式：使用 deploy-backend.sh 自动创建 Secrets

推荐使用 `deploy-backend.sh` 脚本自动创建 Secrets：

```bash
# 仅创建/更新 Secrets
./scripts/deploy-backend.sh -c
```

脚本会自动从 Terraform 输出和 Secrets Manager 获取所有必要的配置值。

#### 手动创建 Secrets

如需手动创建 Secrets：

```bash
# 首先从 RDS 管理的 Secret 获取凭证
RDS_SECRET_ARN=$(aws secretsmanager list-secrets \
  --region ap-northeast-1 \
  --query "SecretList[?contains(Name, 'rds!cluster')].ARN | [0]" \
  --output text)

DB_PASSWORD=$(aws secretsmanager get-secret-value \
  --secret-id "$RDS_SECRET_ARN" \
  --region ap-northeast-1 \
  --query SecretString --output text | jq -r '.password')

# 创建 user-service Secret
kubectl delete secret user-service-secret -n auth-platform 2>/dev/null || true
kubectl create secret generic user-service-secret -n auth-platform \
  --from-literal=DB_HOST='auth-platform-production-aurora.cluster-xxxxxx.ap-northeast-1.rds.amazonaws.com' \
  --from-literal=DB_USERNAME='postgres' \
  --from-literal=DB_PASSWORD="$DB_PASSWORD" \
  --from-literal=COGNITO_USER_POOL_ID='ap-northeast-1_xxxxxxxx'

# 创建 profile-service Secret
kubectl delete secret profile-service-secret -n auth-platform 2>/dev/null || true
kubectl create secret generic profile-service-secret -n auth-platform \
  --from-literal=DB_HOST='auth-platform-production-aurora.cluster-xxxxxx.ap-northeast-1.rds.amazonaws.com' \
  --from-literal=DB_USERNAME='postgres' \
  --from-literal=DB_PASSWORD="$DB_PASSWORD" \
  --from-literal=COGNITO_USER_POOL_ID='ap-northeast-1_xxxxxxxx' \
  --from-literal=S3_AVATAR_BUCKET='auth-platform-production-avatars-xxxxxx' \
  --from-literal=CLOUDFRONT_DOMAIN='xxxxxx.cloudfront.net'

# 获取 SES 发件人邮箱 (从 terraform.tfvars)
SES_FROM_ADDRESS=$(grep -E "^ses_email_address\s*=" ../infrastructure/terraform.tfvars 2>/dev/null | cut -d'=' -f2 | tr -d ' "'"'" | head -1)
echo "SES From Address: $SES_FROM_ADDRESS"

# 创建 notification-service Secret
kubectl delete secret notification-service-secret -n auth-platform 2>/dev/null || true
kubectl create secret generic notification-service-secret -n auth-platform \
  --from-literal=SES_FROM_ADDRESS="$SES_FROM_ADDRESS" \
  --from-literal=SES_FROM_NAME='Auth Platform'

# 查看 Secret
kubectl get secret -n auth-platform
```

## CI/CD 集成

### GitHub Actions 示例

创建 `.github/workflows/deploy.yml`:

```yaml
name: Build and Deploy

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  AWS_REGION: ap-northeast-1
  EKS_CLUSTER_NAME: auth-platform-production

jobs:
  build:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        service: [user-service, profile-service, notification-service]

    steps:
      - uses: actions/checkout@v4

      - name: Set up JDK 21
        uses: actions/setup-java@v4
        with:
          java-version: '21'
          distribution: 'corretto'
          cache: maven

      - name: Build with Maven
        run: |
          cd services/${{ matrix.service }}
          mvn clean package -DskipTests

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push Docker image
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          cd services/${{ matrix.service }}
          docker build -t $ECR_REGISTRY/auth-platform-production/${{ matrix.service }}:$IMAGE_TAG .
          docker push $ECR_REGISTRY/auth-platform-production/${{ matrix.service }}:$IMAGE_TAG

  deploy:
    needs: build
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Update kubeconfig
        run: |
          aws eks update-kubeconfig --name ${{ env.EKS_CLUSTER_NAME }} --region ${{ env.AWS_REGION }}

      - name: Deploy to EKS
        env:
          AWS_ACCOUNT_ID: ${{ secrets.AWS_ACCOUNT_ID }}
          IMAGE_TAG: ${{ github.sha }}
        run: |
          export APP_SERVICE_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/auth-platform-production-app-service-role"
          export ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${{ env.AWS_REGION }}.amazonaws.com"

          for SERVICE in user-service profile-service notification-service; do
            # 更新镜像
            cd services/${SERVICE}/kustomize/overlays/production
            kustomize edit set image ${SERVICE}=${ECR_REGISTRY}/auth-platform-production/${SERVICE}:${IMAGE_TAG}

            # 部署
            kustomize build . | \
              sed "s|\${AWS_ACCOUNT_ID}|${AWS_ACCOUNT_ID}|g" | \
              sed "s|\${APP_SERVICE_ROLE_ARN}|${APP_SERVICE_ROLE_ARN}|g" | \
              kubectl apply -f -

            cd -
          done

          # 等待部署完成
          for SERVICE in user-service profile-service notification-service; do
            kubectl rollout status deployment/${SERVICE} -n auth-platform --timeout=300s
          done
```

### GitHub Secrets 配置

在 GitHub Repository Settings > Secrets 中添加：

| Secret 名称 | 说明 |
|-------------|------|
| `AWS_ACCESS_KEY_ID` | AWS Access Key |
| `AWS_SECRET_ACCESS_KEY` | AWS Secret Key |
| `AWS_ACCOUNT_ID` | AWS Account ID |

## 故障排除

### 常见问题

#### 1. Pod 无法拉取镜像

```bash
# 加载环境变量
source ~/.auth-platform-env

# 检查 ECR 登录
aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $ECR_REGISTRY

# 检查镜像是否存在
aws ecr describe-images \
  --repository-name auth-platform-production/user-service \
  --region $AWS_REGION

# 检查 Node 的 ECR 权限
kubectl describe node | grep -A 5 "System Info"
```

#### 2. IRSA 权限问题

```bash
# 检查 ServiceAccount 注解
kubectl get sa -n auth-platform user-service-sa -o yaml | grep -A 3 annotations

# 验证 IAM 角色
aws iam get-role --role-name auth-platform-production-app-service-role

# 验证角色信任关系
aws iam get-role --role-name auth-platform-production-app-service-role \
  --query 'Role.AssumeRolePolicyDocument' --output json
```

#### 3. Pod 启动失败

```bash
# 查看 Pod 事件
kubectl describe pod -n auth-platform -l app=user-service

# 查看容器日志
kubectl logs -n auth-platform -l app=user-service --previous

# 查看所有容器日志
kubectl logs -n auth-platform -l app=user-service --all-containers=true
```

#### 4. 健康检查失败

```bash
# 进入 Pod 测试端点
kubectl exec -it -n auth-platform deploy/user-service -- \
  curl -s localhost:8080/api/actuator/health | jq .

# 检查 readiness probe 配置
kubectl get deployment user-service -n auth-platform -o yaml | grep -A 10 readinessProbe
```

#### 4.1 健康检查返回 401 Unauthorized

如果探针失败并显示 `HTTP probe failed with statuscode: 401`，说明 Spring Security 配置未正确放行 actuator 端点。

**解决方案**: 修改 `SecurityConfig.java`，确保 actuator 端点允许匿名访问：

```java
@Bean
public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            // 允许所有 actuator 端点匿名访问
            .requestMatchers("/actuator/**").permitAll()
            .anyRequest().authenticated()
        )
        // ... 其他配置
    return http.build();
}
```

修改后需要重新构建并推送镜像。

#### 4.2 Spring Profile 配置错误

如果启动时出现类似以下错误：
```
Property 'spring.profiles.active' imported from location 'class path resource [application-production.yml]' is invalid
```

**原因**: `spring.profiles.active` 不能在 profile-specific 配置文件 (如 `application-production.yml`) 中定义。

**解决方案**: 从 `application-production.yml` 中删除 `spring.profiles.active` 配置，该值应通过环境变量 `SPRING_PROFILES_ACTIVE` 设置。

#### 5. SES 邮件发送失败

**错误信息**: `SesException: Local address contains control or whitespace`

**原因**: `SES_FROM_ADDRESS` 配置值包含无效字符（空格、等号或其他控制字符）。通常是因为从 terraform.tfvars 解析邮箱地址时，误将整行内容（如 `ses_email_address = xxx@example.com`）作为值。

**解决方案**:

```bash
# 检查当前配置值
kubectl get secret notification-service-secret -n auth-platform \
  -o jsonpath='{.data.SES_FROM_ADDRESS}' | base64 -d && echo ""

# 如果值不正确，修复 Secret
kubectl patch secret notification-service-secret -n auth-platform \
  --type='json' \
  -p='[{"op": "replace", "path": "/data/SES_FROM_ADDRESS", "value": "'$(echo -n "your-email@example.com" | base64)'"}]'

# 重启 notification-service 使配置生效
kubectl rollout restart deployment/notification-service -n auth-platform
```

**预防**: 确保 `infrastructure/terraform.tfvars` 中的邮箱配置格式正确：
```hcl
ses_email_address = "noreply@your-domain.com"
```

#### 6. 数据库连接问题

```bash
# 检查 Pod 环境变量
kubectl exec -it -n auth-platform deploy/user-service -- env | grep DB_

# 测试数据库连接 (从 Pod 内部)
kubectl exec -it -n auth-platform deploy/user-service -- \
  nc -zv auth-platform-production-aurora.cluster-xxxxxx.ap-northeast-1.rds.amazonaws.com 5432
```

**常见原因:**

1. **密码认证失败 (28P01)**
   - 检查 DB_USERNAME 是否正确 (应为 `postgres` 而非 `admin`)
   - 检查 DB_PASSWORD 是否包含特殊字符并被正确传递
   - 使用 `kubectl create secret` 重新创建 Secret

2. **连接超时**
   - 检查 Aurora 安全组是否允许来自 EKS 节点安全组的入站连接
   - EKS 模块会创建自己的节点安全组，需要在 Terraform 中添加额外的安全组规则
   - 参考 infrastructure/main.tf 中的 `aws_security_group_rule.aurora_from_eks_nodes`

3. **DNS 解析失败**
   - 检查 VPC DNS 设置
   - 确保 Aurora 端点主机名正确

### 回滚部署

```bash
# 查看部署历史
kubectl rollout history deployment/user-service -n auth-platform

# 回滚到上一版本
kubectl rollout undo deployment/user-service -n auth-platform

# 回滚到指定版本
kubectl rollout undo deployment/user-service -n auth-platform --to-revision=2

# 检查回滚状态
kubectl rollout status deployment/user-service -n auth-platform
```

### 日志查看

```bash
# 实时日志 (所有 Pod)
kubectl logs -n auth-platform -l app=user-service -f --tail=100

# 查看特定 Pod 日志
kubectl logs -n auth-platform user-service-xxx-yyy -f

# 导出日志到文件
kubectl logs -n auth-platform -l app=user-service --since=1h > user-service.log

# 使用 stern 查看多服务日志 (需要安装 stern)
stern -n auth-platform ".*-service" --tail=50
```

### 资源监控

```bash
# 查看 Pod 资源使用
kubectl top pods -n auth-platform

# 查看节点资源使用
kubectl top nodes

# 查看 HPA 状态
kubectl get hpa -n auth-platform -w
```

## 附录

### 相关文档

- [应用架构](./application-architecture.md)
- [基础设施架构](./infrastructure-architecture.md)
- [可观测性指南](./observability-guide.md)

### Terraform Outputs

部署 infrastructure 后，可通过以下命令获取关键信息：

```bash
cd infrastructure

# 获取 EKS 集群信息
terraform output eks_cluster_name
terraform output eks_update_kubeconfig_command

# 获取 ECR URLs
terraform output ecr_repository_urls

# 获取 IRSA 角色
terraform output app_service_role_arn

# 获取数据库信息
terraform output aurora_cluster_endpoint
terraform output aurora_secret_arn

# 获取 Cognito 信息
terraform output cognito_user_pool_id
terraform output cognito_user_pool_client_id
```

### 快速参考

#### 一键部署所有后端服务

```bash
# 使用 deploy-backend.sh 构建并部署所有服务
./scripts/deploy-backend.sh -b --skip-tests all
```

#### 一键部署前端

```bash
./scripts/deploy-frontend.sh
```

#### 完整部署流程

```bash
# 1. 部署后端（构建镜像 + 创建 Secrets + 部署到 EKS）
./scripts/deploy-backend.sh -b --skip-tests all

# 2. 部署前端（构建 + 上传 S3 + 清除 CDN 缓存）
./scripts/deploy-frontend.sh

# 3. 验证部署
kubectl get pods -n auth-platform
```

### 环境变量完整列表

| 变量名 | 来源 | 说明 |
|--------|------|------|
| `AWS_ACCOUNT_ID` | `aws sts get-caller-identity` | AWS 账户 ID |
| `AWS_REGION` | 固定值 | `ap-northeast-1` |
| `APP_SERVICE_ROLE_ARN` | `terraform output app_service_role_arn` | IRSA 角色 ARN |
| `AURORA_CLUSTER_ENDPOINT` | `terraform output aurora_cluster_endpoint` | Aurora 数据库端点 |
| `DB_PASSWORD` | Secrets Manager | 数据库密码 |
| `COGNITO_USER_POOL_ID` | `terraform output cognito_user_pool_id` | Cognito User Pool ID |
| `S3_AVATARS_BUCKET` | `terraform output s3_avatars_bucket` | 头像存储桶名称 |
| `CLOUDFRONT_DOMAIN` | `terraform output cloudfront_domain_name` | CloudFront 域名 |
| `SES_FROM_ADDRESS` | terraform.tfvars | SES 发件人邮箱（必须是有效的邮箱格式） |

> **注意**: 头像现在存储在 PostgreSQL 数据库中，不再使用 S3。`S3_AVATARS_BUCKET` 配置已废弃。
