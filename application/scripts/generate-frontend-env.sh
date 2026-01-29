#!/bin/bash
# ==============================================================================
# 生成前端环境变量文件
# 从 Terraform 输出自动生成 .env.production
# ==============================================================================

set -e

# 颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 路径配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."
FRONTEND_DIR="${PROJECT_ROOT}/services/frontend"
INFRA_DIR="${PROJECT_ROOT}/infrastructure"

log_info "从 Terraform 获取配置..."

cd "$INFRA_DIR"

# 检查 Terraform 是否初始化
if [ ! -d ".terraform" ]; then
    log_error "Terraform 未初始化，请先运行: terraform init && terraform apply"
    exit 1
fi

# 获取 Cognito 配置
USER_POOL_ID=$(terraform output -raw cognito_user_pool_id 2>/dev/null || echo "")
CLIENT_ID=$(terraform output -raw cognito_user_pool_client_id 2>/dev/null || echo "")
COGNITO_DOMAIN=$(terraform output -raw cognito_domain 2>/dev/null || echo "")

# 获取 CloudFront 配置
CF_DOMAIN=$(terraform output -raw cloudfront_domain_name 2>/dev/null || echo "")

if [ -z "$USER_POOL_ID" ] || [ -z "$CLIENT_ID" ]; then
    log_error "无法获取 Cognito 配置，请确认基础设施已部署"
    exit 1
fi

# 生成 .env.production 文件
ENV_FILE="${FRONTEND_DIR}/.env.production"

log_info "生成 ${ENV_FILE}..."

cat > "$ENV_FILE" << EOF
# ==============================================================================
# 生产环境配置 (自动生成)
# 生成时间: $(date '+%Y-%m-%d %H:%M:%S')
# ==============================================================================

# Cognito Configuration
VITE_COGNITO_USER_POOL_ID=${USER_POOL_ID}
VITE_COGNITO_CLIENT_ID=${CLIENT_ID}
VITE_COGNITO_DOMAIN=${COGNITO_DOMAIN}

# API Configuration (通过 CloudFront 代理)
VITE_API_BASE_URL=https://${CF_DOMAIN}/api
EOF

log_success "环境变量文件已生成: ${ENV_FILE}"
echo ""
echo "内容如下:"
echo "----------------------------------------"
cat "$ENV_FILE"
echo "----------------------------------------"
