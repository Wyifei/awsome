#!/bin/bash
###############################################################################
# SHARA Agent - Build and Push to ECR Script
# Builds Podman image and pushes to AWS ECR in one step
###############################################################################

set -e

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
AGENTS_DIR="${PROJECT_ROOT}/agents"

# Default values
AWS_REGION="${AWS_REGION:-ap-northeast-1}"
AGENT_TYPE="${1:-all}"
IMAGE_TAG="${2:-latest}"
STAGE="${STAGE:-dev}"
PROJECT_NAME="${PROJECT_NAME:-shara}"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

usage() {
    echo "Usage: $0 [AGENT_TYPE] [IMAGE_TAG]"
    echo ""
    echo "Arguments:"
    echo "  AGENT_TYPE   Agent type to build (analyzer|remediator|validator|all). Default: all"
    echo "  IMAGE_TAG    Container image tag. Default: latest"
    echo ""
    echo "Environment variables:"
    echo "  AWS_REGION    AWS region (default: ap-northeast-1)"
    echo "  STAGE         Deployment stage (default: dev)"
    echo "  PROJECT_NAME  Project name (default: shara)"
    echo ""
    echo "Examples:"
    echo "  $0 all latest           # Build and push all agents"
    echo "  $0 analyzer v1.0.0      # Build and push analyzer only"
    echo "  STAGE=prod $0 all       # Build for production"
}

# Get AWS account ID
get_account_id() {
    aws sts get-caller-identity --query Account --output text
}

# Get ECR repository URI
get_ecr_uri() {
    local agent_type="$1"
    local account_id="$2"
    local repo_name="${PROJECT_NAME}-${STAGE}-${agent_type}-agent"
    echo "${account_id}.dkr.ecr.${AWS_REGION}.amazonaws.com/${repo_name}"
}

# Login to ECR
ecr_login() {
    local account_id="$1"
    log_info "Logging in to ECR..."
    aws ecr get-login-password --region "${AWS_REGION}" | \
        podman login --username AWS --password-stdin \
        "${account_id}.dkr.ecr.${AWS_REGION}.amazonaws.com"
}

# Build and push single agent
build_and_push_agent() {
    local agent_type="$1"
    local account_id="$2"
    local ecr_uri
    local full_image_tag
    local agent_dir="${AGENTS_DIR}/${agent_type}"
    local dockerfile_path="${agent_dir}/Dockerfile"

    ecr_uri=$(get_ecr_uri "$agent_type" "$account_id")
    full_image_tag="${ecr_uri}:${IMAGE_TAG}"

    log_step "=========================================="
    log_step "Building ${agent_type} agent..."
    log_step "=========================================="

    # Check if Dockerfile exists
    if [[ ! -f "$dockerfile_path" ]]; then
        log_error "Dockerfile not found: ${dockerfile_path}"
        return 1
    fi

    # Navigate to agents directory (context for shared modules)
    cd "${AGENTS_DIR}"

    # Build the container image for ARM64
    log_info "Building container image: ${full_image_tag}"
    log_info "Dockerfile: ${dockerfile_path}"
    log_info "Context: ${AGENTS_DIR}"

    # Check if running on ARM64 Mac (M1/M2/M3) - can use native build
    if [[ "$(uname -m)" == "arm64" ]]; then
        log_info "Detected ARM64 architecture, using native build..."
        podman build \
            --build-arg AGENT_TYPE="${agent_type}" \
            -t "${full_image_tag}" \
            -t "${ecr_uri}:${agent_type}-${IMAGE_TAG}" \
            -f "${dockerfile_path}" \
            .
    else
        log_info "Cross-compiling for ARM64..."
        podman build \
            --platform linux/arm64 \
            --build-arg AGENT_TYPE="${agent_type}" \
            -t "${full_image_tag}" \
            -t "${ecr_uri}:${agent_type}-${IMAGE_TAG}" \
            -f "${dockerfile_path}" \
            .
    fi

    log_info "Build completed for ${agent_type}"

    # Push the image
    log_step "Pushing ${agent_type} agent to ECR..."
    podman push "${full_image_tag}"
    podman push "${ecr_uri}:${agent_type}-${IMAGE_TAG}"

    log_info "Push completed for ${agent_type}"
    echo ""
}

# Main function
main() {
    local account_id
    local agents_to_build=()

    # Parse arguments
    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
        usage
        exit 0
    fi

    # Determine which agents to build
    case "$AGENT_TYPE" in
        all)
            agents_to_build=(analyzer remediator validator)
            ;;
        analyzer|remediator|validator)
            agents_to_build=("$AGENT_TYPE")
            ;;
        *)
            log_error "Invalid agent type: $AGENT_TYPE"
            log_error "Valid types: analyzer, remediator, validator, all"
            exit 1
            ;;
    esac

    log_step "=========================================="
    log_step "SHARA Agent Build & Push"
    log_step "=========================================="
    log_info "Agents: ${agents_to_build[*]}"
    log_info "Tag: ${IMAGE_TAG}"
    log_info "Stage: ${STAGE}"
    log_info "Region: ${AWS_REGION}"
    echo ""

    # Get AWS account ID
    log_info "Fetching AWS account ID..."
    account_id=$(get_account_id)
    log_info "Account ID: ${account_id}"

    # Check if Podman is running
    if ! podman info > /dev/null 2>&1; then
        log_error "Podman is not running. Please start Podman and try again."
        exit 1
    fi

    # Login to ECR
    ecr_login "$account_id"

    # Build and push each agent
    for agent in "${agents_to_build[@]}"; do
        build_and_push_agent "$agent" "$account_id"
    done

    # Summary
    echo ""
    log_step "=========================================="
    log_step "BUILD & PUSH COMPLETE"
    log_step "=========================================="
    echo ""
    echo "Images pushed:"
    for agent in "${agents_to_build[@]}"; do
        ecr_uri=$(get_ecr_uri "$agent" "$account_id")
        echo "  - ${ecr_uri}:${IMAGE_TAG}"
    done
    echo ""
    log_info "Next step: Deploy to AgentCore Runtime"
    log_info "  ./scripts/deploy_agentcore.sh <agent_type> ${IMAGE_TAG}"
    echo ""
}

main "$@"
