# Auth Platform 部署指南

本文档描述了 Auth Platform 微服务的构建、打包和部署流程。

## 目录

- [概述](#概述)
- [前置条件](#前置条件)
- [环境变量设置](#环境变量设置)
- [构建流程](#构建流程)
- [Docker 镜像](#docker-镜像)
- [Kubernetes 部署](#kubernetes-部署)
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

- **运行时**: Java 17, Spring Boot 3.2
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
# Java 17
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
```

### AWS 配置

```bash
# 配置 AWS 凭证
aws configure

# 验证身份并获取 Account ID
aws sts get-caller-identity
```

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

# 需要手动设置的值
export DB_PASSWORD="<从 Secrets Manager 获取或设置>"
export INTERNAL_API_KEY="<生成一个安全的 API Key>"
export SES_FROM_EMAIL="noreply@your-domain.com"

# 验证变量
echo "Aurora Endpoint: $AURORA_CLUSTER_ENDPOINT"
echo "Cognito User Pool: $COGNITO_USER_POOL_ID"
echo "S3 Avatars Bucket: $S3_AVATARS_BUCKET"
echo "CloudFront Domain: $CLOUDFRONT_DOMAIN"
```

### 步骤 3: 保存环境变量文件

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
export INTERNAL_API_KEY="<your-internal-api-key>"
export SES_FROM_EMAIL="${SES_FROM_EMAIL:-noreply@example.com}"
EOF

# 加载环境变量
source ~/.auth-platform-env
```

### 从 Secrets Manager 获取数据库密码

```bash
# 获取 Aurora 凭证
aws secretsmanager get-secret-value \
  --secret-id auth-platform-production/aurora-credentials \
  --query SecretString \
  --output text | jq -r '.password'
```

## 构建流程

### 使用构建脚本

项目提供了统一的构建脚本 `scripts/build.sh`。

#### 基本用法

```bash
# 加载环境变量
source ~/.auth-platform-env

# 构建所有服务
./scripts/build.sh

# 构建指定服务
./scripts/build.sh user-service

# 清理后构建，跳过测试
./scripts/build.sh -c -s all
```

#### 完整参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-h, --help` | 显示帮助信息 | - |
| `-c, --clean` | 构建前执行 clean | false |
| `-s, --skip-tests` | 跳过单元测试 | false |
| `-d, --docker` | 构建 Docker 镜像 | false |
| `-p, --push` | 推送镜像到 ECR | false |
| `-e, --env` | 环境 (dev/production) | production |
| `-t, --tag` | Docker 镜像标签 | latest |
| `-r, --registry` | AWS Account ID | - |
| `--region` | AWS 区域 | ap-northeast-1 |

#### 常用命令

```bash
# 加载环境变量
source ~/.auth-platform-env

# 仅构建 JAR
./scripts/build.sh -c all

# 构建并创建 Docker 镜像 (本地)
./scripts/build.sh -d -t v1.0.0 all

# 构建并推送到 ECR (Production)
./scripts/build.sh -d -p -e production -r $AWS_ACCOUNT_ID -t v1.0.0 all

# 构建并推送到 ECR (Dev)
./scripts/build.sh -d -p -e dev -r $AWS_ACCOUNT_ID -t dev-latest all

# 使用 Git commit hash 作为标签
./scripts/build.sh -d -p -e production -r $AWS_ACCOUNT_ID -t $(git rev-parse --short HEAD) all
```

### 手动构建

```bash
# 加载环境变量
source ~/.auth-platform-env

# 进入服务目录
cd services/user-service

# Maven 构建
mvn clean package -DskipTests

# 构建 Docker 镜像
docker build -t user-service:v1.0.0 .
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

## Kubernetes 部署

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

# 创建变量替换函数
substitute_vars() {
  sed "s|\${AWS_ACCOUNT_ID}|${AWS_ACCOUNT_ID}|g" | \
  sed "s|\${APP_SERVICE_ROLE_ARN}|${APP_SERVICE_ROLE_ARN}|g" | \
  sed "s|\${AURORA_CLUSTER_ENDPOINT}|${AURORA_CLUSTER_ENDPOINT}|g" | \
  sed "s|\${DB_PASSWORD}|${DB_PASSWORD}|g" | \
  sed "s|\${COGNITO_USER_POOL_ID}|${COGNITO_USER_POOL_ID}|g" | \
  sed "s|\${S3_AVATARS_BUCKET}|${S3_AVATARS_BUCKET}|g" | \
  sed "s|\${CLOUDFRONT_DOMAIN}|${CLOUDFRONT_DOMAIN}|g" | \
  sed "s|\${INTERNAL_API_KEY}|${INTERNAL_API_KEY}|g" | \
  sed "s|\${SES_FROM_EMAIL}|${SES_FROM_EMAIL}|g"
}

# 部署所有服务
for SERVICE in user-service profile-service notification-service; do
  echo "Deploying $SERVICE..."

  kustomize build services/${SERVICE}/kustomize/overlays/production | \
    substitute_vars | \
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

# 定义变量替换
substitute_vars() {
  sed "s|\${AWS_ACCOUNT_ID}|${AWS_ACCOUNT_ID}|g" | \
  sed "s|\${APP_SERVICE_ROLE_ARN}|${APP_SERVICE_ROLE_ARN}|g" | \
  sed "s|\${AURORA_CLUSTER_ENDPOINT}|${AURORA_CLUSTER_ENDPOINT}|g" | \
  sed "s|\${DB_PASSWORD}|${DB_PASSWORD}|g" | \
  sed "s|\${COGNITO_USER_POOL_ID}|${COGNITO_USER_POOL_ID}|g" | \
  sed "s|\${S3_AVATARS_BUCKET}|${S3_AVATARS_BUCKET}|g" | \
  sed "s|\${CLOUDFRONT_DOMAIN}|${CLOUDFRONT_DOMAIN}|g" | \
  sed "s|\${INTERNAL_API_KEY}|${INTERNAL_API_KEY}|g" | \
  sed "s|\${SES_FROM_EMAIL}|${SES_FROM_EMAIL}|g"
}

# 部署 user-service
kustomize build services/user-service/kustomize/overlays/production | \
  substitute_vars | \
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
kustomize build . | substitute_vars | kubectl apply -f -
cd -
```

### 部署到 Dev 环境

```bash
# 加载环境变量
source ~/.auth-platform-env

# Dev 环境变量替换函数
substitute_vars_dev() {
  sed "s|\${AWS_ACCOUNT_ID}|${AWS_ACCOUNT_ID}|g" | \
  sed "s|\${AURORA_CLUSTER_ENDPOINT}|${AURORA_CLUSTER_ENDPOINT}|g" | \
  sed "s|\${DB_PASSWORD}|${DB_PASSWORD}|g" | \
  sed "s|\${COGNITO_USER_POOL_ID}|${COGNITO_USER_POOL_ID}|g" | \
  sed "s|\${S3_AVATARS_BUCKET}|${S3_AVATARS_BUCKET}|g" | \
  sed "s|\${CLOUDFRONT_DOMAIN}|${CLOUDFRONT_DOMAIN}|g" | \
  sed "s|\${INTERNAL_API_KEY}|${INTERNAL_API_KEY}|g" | \
  sed "s|\${SES_FROM_EMAIL}|${SES_FROM_EMAIL}|g"
}

# 部署所有服务到 dev
for SERVICE in user-service profile-service notification-service; do
  echo "Deploying $SERVICE to dev..."

  kustomize build services/${SERVICE}/kustomize/overlays/dev | \
    substitute_vars_dev | \
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

生产环境使用 Kubernetes Secrets，建议后续迁移到 External Secrets Operator：

```bash
# 创建数据库密码 Secret
kubectl create secret generic user-service-secret \
  -n auth-platform \
  --from-literal=DB_PASSWORD='your-db-password' \
  --from-literal=COGNITO_USER_POOL_ID='ap-northeast-1_xxxxxxxx' \
  --from-literal=INTERNAL_API_KEY='your-internal-api-key'

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

      - name: Set up JDK 17
        uses: actions/setup-java@v4
        with:
          java-version: '17'
          distribution: 'temurin'
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

#### 5. 数据库连接问题

```bash
# 检查 Pod 环境变量
kubectl exec -it -n auth-platform deploy/user-service -- env | grep DB_

# 测试数据库连接
kubectl exec -it -n auth-platform deploy/user-service -- \
  nc -zv $DB_HOST $DB_PORT
```

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

```bash
# 一键部署脚本
cat > deploy-all.sh << 'EOF'
#!/bin/bash
set -e

# 加载环境变量
source ~/.auth-platform-env

# 变量替换函数
substitute_vars() {
  sed "s|\${AWS_ACCOUNT_ID}|${AWS_ACCOUNT_ID}|g" | \
  sed "s|\${APP_SERVICE_ROLE_ARN}|${APP_SERVICE_ROLE_ARN}|g" | \
  sed "s|\${AURORA_CLUSTER_ENDPOINT}|${AURORA_CLUSTER_ENDPOINT}|g" | \
  sed "s|\${DB_PASSWORD}|${DB_PASSWORD}|g" | \
  sed "s|\${COGNITO_USER_POOL_ID}|${COGNITO_USER_POOL_ID}|g" | \
  sed "s|\${S3_AVATARS_BUCKET}|${S3_AVATARS_BUCKET}|g" | \
  sed "s|\${CLOUDFRONT_DOMAIN}|${CLOUDFRONT_DOMAIN}|g" | \
  sed "s|\${INTERNAL_API_KEY}|${INTERNAL_API_KEY}|g" | \
  sed "s|\${SES_FROM_EMAIL}|${SES_FROM_EMAIL}|g"
}

echo "Building and pushing images..."
./scripts/build.sh -d -p -e production -r $AWS_ACCOUNT_ID -t $(git rev-parse --short HEAD) all

echo "Deploying to EKS..."
for SERVICE in user-service profile-service notification-service; do
  echo "  - Deploying $SERVICE..."
  kustomize build services/${SERVICE}/kustomize/overlays/production | \
    substitute_vars | \
    kubectl apply -f -
done

echo "Waiting for rollout..."
for SERVICE in user-service profile-service notification-service; do
  kubectl rollout status deployment/${SERVICE} -n auth-platform --timeout=300s
done

echo "Deployment complete!"
kubectl get pods -n auth-platform
EOF

chmod +x deploy-all.sh
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
| `INTERNAL_API_KEY` | 手动生成 | 服务间通信 API Key |
| `SES_FROM_EMAIL` | terraform.tfvars | SES 发件人邮箱 |
