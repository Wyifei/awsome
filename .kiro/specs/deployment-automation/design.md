# 部署自动化设计文档

## 概述

本文档描述 Auth Platform 部署自动化脚本的设计，包括后端构建、后端部署和前端部署三个主要脚本。

## 脚本架构

```
scripts/
├── build-backend.sh          # 后端构建脚本
├── deploy-backend.sh         # 后端部署脚本
├── deploy-frontend.sh        # 前端部署脚本
└── generate-frontend-env.sh  # 前端环境变量生成脚本
```

## 1. 后端构建脚本 (build-backend.sh)

### 1.1 功能流程

```
┌─────────────────┐
│   解析参数       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  检查前置条件    │
│  (Java, Maven,  │
│   Docker, AWS)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  遍历服务列表    │◀──────────────────┐
└────────┬────────┘                   │
         │                            │
         ▼                            │
┌─────────────────┐                   │
│  Maven 构建      │                   │
│  (clean package)│                   │
└────────┬────────┘                   │
         │                            │
         ▼                            │
┌─────────────────┐                   │
│  Docker 构建     │ (如果启用 -d)     │
└────────┬────────┘                   │
         │                            │
         ▼                            │
┌─────────────────┐                   │
│  ECR 推送        │ (如果启用 -p)     │
└────────┬────────┘                   │
         │                            │
         ▼                            │
┌─────────────────┐                   │
│  下一个服务?     │───── Yes ─────────┘
└────────┬────────┘
         │ No
         ▼
┌─────────────────┐
│  打印摘要        │
└─────────────────┘
```

### 1.2 命令行参数

| 参数 | 长参数 | 说明 | 默认值 |
|------|--------|------|--------|
| -h | --help | 显示帮助 | - |
| -c | --clean | 执行 clean | false |
| -s | --skip-tests | 跳过测试 | false |
| -d | --docker | 构建 Docker 镜像 | false |
| -p | --push | 推送到 ECR | false |
| -e | --env | 环境名称 | production |
| -t | --tag | 镜像标签 | latest |
| -r | --registry | AWS Account ID | - |

### 1.3 ECR 仓库命名

```
{AWS_ACCOUNT_ID}.dkr.ecr.{REGION}.amazonaws.com/{PROJECT}-{ENV}/{SERVICE}:{TAG}

示例:
123456789012.dkr.ecr.ap-northeast-1.amazonaws.com/auth-platform-production/user-service:v1.0.0
```

### 1.4 核心函数

```bash
# 前置条件检查
check_prerequisites() {
  # 检查 Java (需要 21)
  # 检查 Maven (需要 3.8+)
  # 检查 Docker (如果 -d)
  # 检查 AWS CLI (如果 -p)
}

# 构建单个服务
build_service() {
  local service=$1
  cd "$SERVICES_DIR/$service"
  
  local mvn_cmd="mvn"
  [ "$CLEAN" = true ] && mvn_cmd="$mvn_cmd clean"
  mvn_cmd="$mvn_cmd package"
  [ "$SKIP_TESTS" = true ] && mvn_cmd="$mvn_cmd -DskipTests"
  
  $mvn_cmd
}

# 构建 Docker 镜像
build_docker_image() {
  local service=$1
  local ecr_repo="${PROJECT_NAME}-${ENVIRONMENT}/${service}"
  local local_tag="${service}:${DOCKER_TAG}"
  
  docker build -t "$local_tag" .
  
  if [ -n "$ECR_REGISTRY" ]; then
    local ecr_tag="${ECR_REGISTRY}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ecr_repo}:${DOCKER_TAG}"
    docker tag "$local_tag" "$ecr_tag"
  fi
}

# 推送到 ECR
push_docker_image() {
  local service=$1
  local ecr_url="${ECR_REGISTRY}.dkr.ecr.${AWS_REGION}.amazonaws.com"
  
  # ECR 登录
  aws ecr get-login-password --region "$AWS_REGION" | \
    docker login --username AWS --password-stdin "$ecr_url"
  
  docker push "$ecr_tag"
}
```

## 2. 后端部署脚本 (deploy-backend.sh)

### 2.1 功能流程

```
┌─────────────────┐
│   解析参数       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  检查前置条件    │
│  (AWS, kubectl, │
│   kustomize, jq)│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  获取 AWS 配置   │
│  (Account ID,   │
│   Region)       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  获取 Terraform │
│  输出值         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  获取数据库凭证  │
│  (Secrets Mgr)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  配置 kubectl   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  创建 Namespace │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  创建 Secrets   │ (如果未跳过)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  构建镜像       │ (如果启用 -b)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  部署服务       │
│  (Kustomize)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  等待 Rollout   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  验证部署       │
└─────────────────┘
```

### 2.2 命令行参数

| 参数 | 长参数 | 说明 | 默认值 |
|------|--------|------|--------|
| -h | --help | 显示帮助 | - |
| -b | --build | 构建并推送镜像 | false |
| -t | --tag | 镜像标签 | latest |
| -e | --env | 环境名称 | production |
| -s | --skip-secrets | 跳过创建 Secrets | false |
| -c | --create-secrets | 仅创建 Secrets | false |
| -n | --dry-run | 预览模式 | false |
| | --skip-tests | 构建时跳过测试 | false |
| | --region | AWS 区域 | ap-northeast-1 |

### 2.3 环境变量获取

```bash
# 从 Terraform 输出获取
fetch_terraform_outputs() {
  cd "$INFRA_DIR"
  
  local tf_outputs=$(terraform output -json)
  
  AURORA_CLUSTER_ENDPOINT=$(echo "$tf_outputs" | jq -r '.aurora_cluster_endpoint.value')
  COGNITO_USER_POOL_ID=$(echo "$tf_outputs" | jq -r '.cognito_user_pool_id.value')
  CLOUDFRONT_DOMAIN=$(echo "$tf_outputs" | jq -r '.cloudfront_domain_name.value')
  
  # 从 terraform.tfvars 获取 SES 邮箱
  SES_FROM_ADDRESS=$(grep -E "^ses_email_address" terraform.tfvars | cut -d'=' -f2 | tr -d ' "')
}

# 从 Secrets Manager 获取数据库凭证
fetch_database_credentials() {
  # 查找 RDS 托管的 Secret
  local rds_secret_arn=$(aws secretsmanager list-secrets \
    --query "SecretList[?contains(Name, 'rds!cluster')].ARN | [0]" \
    --output text)
  
  local secret_value=$(aws secretsmanager get-secret-value \
    --secret-id "$rds_secret_arn" \
    --query SecretString --output text)
  
  DB_USERNAME=$(echo "$secret_value" | jq -r '.username')
  DB_PASSWORD=$(echo "$secret_value" | jq -r '.password')
}
```

### 2.4 Kubernetes Secrets 设计

```bash
# user-service-secret
kubectl create secret generic user-service-secret -n auth-platform \
  --from-literal=DB_HOST="$AURORA_CLUSTER_ENDPOINT" \
  --from-literal=DB_USERNAME="$DB_USERNAME" \
  --from-literal=DB_PASSWORD="$DB_PASSWORD" \
  --from-literal=COGNITO_USER_POOL_ID="$COGNITO_USER_POOL_ID"

# profile-service-secret
kubectl create secret generic profile-service-secret -n auth-platform \
  --from-literal=DB_HOST="$AURORA_CLUSTER_ENDPOINT" \
  --from-literal=DB_USERNAME="$DB_USERNAME" \
  --from-literal=DB_PASSWORD="$DB_PASSWORD" \
  --from-literal=COGNITO_USER_POOL_ID="$COGNITO_USER_POOL_ID" \
  --from-literal=CLOUDFRONT_DOMAIN="$CLOUDFRONT_DOMAIN"

# notification-service-secret
kubectl create secret generic notification-service-secret -n auth-platform \
  --from-literal=SES_FROM_ADDRESS="$SES_FROM_ADDRESS" \
  --from-literal=SES_FROM_NAME="Auth Platform"
```

### 2.5 Kustomize 部署

```bash
deploy_service() {
  local service=$1
  local service_dir="$SERVICES_DIR/$service/kustomize/overlays/$ENVIRONMENT"
  
  # 定义需要替换的变量
  local envsubst_vars='${AWS_ACCOUNT_ID} ${APP_SERVICE_ROLE_ARN} ${AURORA_CLUSTER_ENDPOINT} ...'
  
  # 构建并应用
  kustomize build "$service_dir" | \
    envsubst "$envsubst_vars" | \
    kubectl apply -f -
}
```

## 3. 前端部署脚本 (deploy-frontend.sh)

### 3.1 功能流程

```
┌─────────────────┐
│   解析参数       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  检查前置条件    │
│  (AWS, Terraform│
│   npm)          │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  获取 Terraform │
│  输出值         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  生成 .env      │
│  .production    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  npm install    │ (如果未跳过构建)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  npm run build  │ (如果未跳过构建)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  S3 同步        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  CloudFront     │
│  缓存失效       │
└─────────────────┘
```

### 3.2 命令行参数

| 参数 | 长参数 | 说明 | 默认值 |
|------|--------|------|--------|
| -h | --help | 显示帮助 | - |
| -s | --skip-build | 跳过构建 | false |
| -n | --no-invalidate | 跳过缓存失效 | false |
| -d | --dry-run | 预览模式 | false |

### 3.3 环境变量生成

```bash
# 生成 .env.production
cat > "$ENV_FILE" << EOF
# 生产环境配置 (自动生成)
# 生成时间: $(date '+%Y-%m-%d %H:%M:%S')

# Cognito Configuration
VITE_COGNITO_USER_POOL_ID=${COGNITO_USER_POOL_ID}
VITE_COGNITO_CLIENT_ID=${COGNITO_CLIENT_ID}
VITE_COGNITO_DOMAIN=${COGNITO_DOMAIN}

# API Configuration (通过 CloudFront 代理)
VITE_API_BASE_URL=https://${CF_DOMAIN}/api
EOF
```

### 3.4 S3 同步策略

```bash
# 静态资源 (长期缓存)
aws s3 sync dist/ "s3://${BUCKET_NAME}/" \
  --delete \
  --cache-control "max-age=31536000" \
  --exclude "*.html"

# HTML 文件 (不缓存)
aws s3 sync dist/ "s3://${BUCKET_NAME}/" \
  --exclude "*" \
  --include "*.html" \
  --cache-control "no-cache, no-store, must-revalidate"
```

### 3.5 CloudFront 缓存失效

```bash
INVALIDATION_ID=$(aws cloudfront create-invalidation \
  --distribution-id "$DISTRIBUTION_ID" \
  --paths "/*" \
  --query 'Invalidation.Id' \
  --output text)
```

## 4. 通用设计

### 4.1 彩色输出

```bash
# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 输出函数
print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠ $1${NC}"; }
print_info() { echo -e "${BLUE}ℹ $1${NC}"; }
```

### 4.2 错误处理

```bash
set -e  # 遇到错误立即退出

# 构建失败处理
if ! build_service "$service"; then
  print_error "$service build failed"
  exit 1
fi
```

### 4.3 帮助信息

```bash
show_help() {
  # 从脚本头部注释提取帮助信息
  head -35 "$0" | tail -32
  exit 0
}
```

## 5. 部署流程

### 5.1 完整部署流程

```bash
# 1. 后端构建并部署
./scripts/deploy-backend.sh -b --skip-tests all

# 2. 前端构建并部署
./scripts/deploy-frontend.sh

# 3. 验证部署
kubectl get pods -n auth-platform
```

### 5.2 快速更新流程

```bash
# 仅更新后端 (使用已有镜像)
./scripts/deploy-backend.sh all

# 仅更新前端 (使用已构建的 dist)
./scripts/deploy-frontend.sh --skip-build
```

### 5.3 单服务更新

```bash
# 构建并部署单个服务
./scripts/deploy-backend.sh -b --skip-tests user-service
```

## 正确性属性

### P1: 构建幂等性
**属性**: 相同代码多次构建产生相同的镜像内容
**验证**: 使用 Git commit hash 作为镜像标签

### P2: 部署原子性
**属性**: 部署失败时不影响现有服务
**验证**: Kubernetes 滚动更新策略

### P3: 配置一致性
**属性**: 部署使用的配置与 Terraform 输出一致
**验证**: 自动从 Terraform 获取配置，不使用硬编码值

### P4: 凭证安全性
**属性**: 敏感凭证不在日志中显示
**验证**: 密码变量不直接打印，使用 [RETRIEVED] 占位符

## 文件引用

- 后端构建脚本: #[[file:application/scripts/build-backend.sh]]
- 后端部署脚本: #[[file:application/scripts/deploy-backend.sh]]
- 前端部署脚本: #[[file:application/scripts/deploy-frontend.sh]]
- 部署指南: #[[file:application/docs/deployment-guide.md]]
