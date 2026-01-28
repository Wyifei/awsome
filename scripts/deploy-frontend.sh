#!/bin/bash
# ==============================================================================
# Frontend 部署脚本
# 将前端应用构建并部署到 S3 + CloudFront
# ==============================================================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 路径配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."
FRONTEND_DIR="${PROJECT_ROOT}/services/frontend"
INFRA_DIR="${PROJECT_ROOT}/infrastructure"

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 显示帮助
show_help() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -h, --help          显示帮助信息"
    echo "  -s, --skip-build    跳过构建步骤，直接上传现有的 dist 目录"
    echo "  -n, --no-invalidate 跳过 CloudFront 缓存失效"
    echo "  -d, --dry-run       仅显示将要执行的操作，不实际执行"
    echo ""
    echo "Examples:"
    echo "  $0                  # 完整部署流程"
    echo "  $0 --skip-build     # 仅上传已构建的文件"
    echo "  $0 --dry-run        # 预览部署操作"
}

# 参数解析
SKIP_BUILD=false
NO_INVALIDATE=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -s|--skip-build)
            SKIP_BUILD=true
            shift
            ;;
        -n|--no-invalidate)
            NO_INVALIDATE=true
            shift
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            log_error "未知选项: $1"
            show_help
            exit 1
            ;;
    esac
done

# ==============================================================================
# 主流程
# ==============================================================================

echo ""
echo "=============================================="
echo "       Frontend 部署到 S3 + CloudFront"
echo "=============================================="
echo ""

# ------------------------------------------------------------------------------
# 1. 检查必要工具
# ------------------------------------------------------------------------------

log_info "检查必要工具..."

if ! command -v aws &> /dev/null; then
    log_error "AWS CLI 未安装，请先安装: https://aws.amazon.com/cli/"
    exit 1
fi

if ! command -v terraform &> /dev/null; then
    log_error "Terraform 未安装，请先安装: https://www.terraform.io/downloads"
    exit 1
fi

if ! command -v npm &> /dev/null; then
    log_error "npm 未安装，请先安装 Node.js"
    exit 1
fi

log_success "工具检查通过"

# ------------------------------------------------------------------------------
# 2. 获取 Terraform 输出
# ------------------------------------------------------------------------------

log_info "获取基础设施信息..."

cd "$INFRA_DIR"

# 检查 Terraform 状态
if [ ! -f "terraform.tfstate" ] && [ ! -d ".terraform" ]; then
    log_error "Terraform 未初始化，请先运行: cd infrastructure && terraform init && terraform apply"
    exit 1
fi

# 获取输出值
BUCKET_NAME=$(terraform output -raw s3_frontend_bucket 2>/dev/null || echo "")
DISTRIBUTION_ID=$(terraform output -raw cloudfront_distribution_id 2>/dev/null || echo "")
CF_DOMAIN=$(terraform output -raw cloudfront_domain_name 2>/dev/null || echo "")

if [ -z "$BUCKET_NAME" ]; then
    log_error "S3 存储桶未找到，请先运行: cd infrastructure && terraform apply"
    exit 1
fi

echo ""
log_info "基础设施信息:"
echo "  - S3 Bucket:    ${BUCKET_NAME}"
echo "  - CloudFront:   ${CF_DOMAIN}"
echo "  - Distribution: ${DISTRIBUTION_ID}"
echo ""

# ------------------------------------------------------------------------------
# 3. 生成环境变量文件
# ------------------------------------------------------------------------------

log_info "生成前端环境变量..."

# 获取 Cognito 配置
COGNITO_USER_POOL_ID=$(terraform output -raw cognito_user_pool_id 2>/dev/null || echo "")
COGNITO_CLIENT_ID=$(terraform output -raw cognito_user_pool_client_id 2>/dev/null || echo "")
COGNITO_DOMAIN=$(terraform output -raw cognito_domain 2>/dev/null || echo "")

if [ -z "$COGNITO_USER_POOL_ID" ] || [ -z "$COGNITO_CLIENT_ID" ]; then
    log_error "无法获取 Cognito 配置，请确认基础设施已部署"
    exit 1
fi

# 生成 .env.production 文件
ENV_FILE="${FRONTEND_DIR}/.env.production"

if [ "$DRY_RUN" = true ]; then
    log_info "[DRY-RUN] 将生成 ${ENV_FILE}"
else
    cat > "$ENV_FILE" << EOF
# ==============================================================================
# 生产环境配置 (自动生成)
# 生成时间: $(date '+%Y-%m-%d %H:%M:%S')
# ==============================================================================

# Cognito Configuration
VITE_COGNITO_USER_POOL_ID=${COGNITO_USER_POOL_ID}
VITE_COGNITO_CLIENT_ID=${COGNITO_CLIENT_ID}
VITE_COGNITO_DOMAIN=${COGNITO_DOMAIN}

# API Configuration (通过 CloudFront 代理)
VITE_API_BASE_URL=https://${CF_DOMAIN}/api
EOF
    log_success "环境变量文件已生成"
fi

# ------------------------------------------------------------------------------
# 4. 构建前端
# ------------------------------------------------------------------------------

if [ "$SKIP_BUILD" = false ]; then
    log_info "构建前端应用..."

    cd "$FRONTEND_DIR"

    # 检查 package.json
    if [ ! -f "package.json" ]; then
        log_error "未找到 package.json，请确认前端项目路径正确"
        exit 1
    fi

    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] 将执行: npm install && npm run build"
    else
        # 安装依赖
        log_info "安装依赖..."
        npm install --silent

        # 构建
        log_info "执行构建..."
        npm run build

        log_success "构建完成"
    fi
else
    log_warn "跳过构建步骤"
    cd "$FRONTEND_DIR"
fi

# 检查 dist 目录
if [ ! -d "dist" ]; then
    log_error "dist 目录不存在，请先执行构建"
    exit 1
fi

# ------------------------------------------------------------------------------
# 5. 上传到 S3
# ------------------------------------------------------------------------------

log_info "上传文件到 S3..."

cd "$FRONTEND_DIR"

if [ "$DRY_RUN" = true ]; then
    log_info "[DRY-RUN] 将执行: aws s3 sync dist/ s3://${BUCKET_NAME}/ --delete"

    # 显示将要上传的文件
    echo ""
    log_info "将要上传的文件:"
    find dist -type f | head -20
    echo "..."
else
    # 同步文件到 S3
    aws s3 sync dist/ "s3://${BUCKET_NAME}/" \
        --delete \
        --cache-control "max-age=31536000" \
        --exclude "*.html"

    # HTML 文件不缓存
    aws s3 sync dist/ "s3://${BUCKET_NAME}/" \
        --exclude "*" \
        --include "*.html" \
        --cache-control "no-cache, no-store, must-revalidate"

    log_success "文件上传完成"
fi

# ------------------------------------------------------------------------------
# 6. 清除 CloudFront 缓存
# ------------------------------------------------------------------------------

if [ "$NO_INVALIDATE" = false ] && [ -n "$DISTRIBUTION_ID" ]; then
    log_info "清除 CloudFront 缓存..."

    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY-RUN] 将执行: aws cloudfront create-invalidation --distribution-id ${DISTRIBUTION_ID} --paths '/*'"
    else
        INVALIDATION_ID=$(aws cloudfront create-invalidation \
            --distribution-id "$DISTRIBUTION_ID" \
            --paths "/*" \
            --query 'Invalidation.Id' \
            --output text)

        log_success "缓存失效已创建: ${INVALIDATION_ID}"
    fi
else
    if [ "$NO_INVALIDATE" = true ]; then
        log_warn "跳过 CloudFront 缓存失效"
    fi
fi

# ------------------------------------------------------------------------------
# 7. 完成
# ------------------------------------------------------------------------------

echo ""
echo "=============================================="
log_success "部署完成!"
echo "=============================================="
echo ""
echo "访问地址: https://${CF_DOMAIN}"
echo ""

# 提示更新 Cognito 回调 URL
log_warn "提示: 如果这是首次部署，请更新 Cognito 回调 URL:"
echo ""
echo "  1. 编辑 infrastructure/terraform.tfvars"
echo "  2. 更新以下配置:"
echo ""
echo "     cognito_callback_urls = ["
echo "       \"https://${CF_DOMAIN}/callback\","
echo "       \"http://localhost:3000/callback\""
echo "     ]"
echo ""
echo "     cognito_logout_urls = ["
echo "       \"https://${CF_DOMAIN}\","
echo "       \"http://localhost:3000\""
echo "     ]"
echo ""
echo "  3. 运行: cd infrastructure && terraform apply"
echo ""
