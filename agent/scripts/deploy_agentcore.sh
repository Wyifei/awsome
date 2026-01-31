#!/bin/bash
###############################################################################
# SHARA Agent - Deploy to AgentCore Runtime
# Uses agentcore CLI (bedrock-agentcore-starter-toolkit)
###############################################################################

set -e

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
AGENTS_DIR="${PROJECT_ROOT}/agents"
INFRA_DIR="${PROJECT_ROOT}/infra"

# Default values
AWS_REGION="${AWS_REGION:-ap-northeast-1}"
AGENT_TYPE="${1:-all}"
IMAGE_TAG="${2:-latest}"
STAGE="${STAGE:-dev}"
PROJECT_NAME="${PROJECT_NAME:-shara}"
# Deploy mode: "cli" uses agentcore CLI (rebuilds), "api" uses Python API (uses existing image)
DEPLOY_MODE="${DEPLOY_MODE:-api}"

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
    echo "  AGENT_TYPE   Agent type to deploy (analyzer|remediator|validator|all). Default: all"
    echo "  IMAGE_TAG    Docker image tag. Default: latest"
    echo ""
    echo "Environment variables:"
    echo "  AWS_REGION    AWS region (default: ap-northeast-1)"
    echo "  STAGE         Deployment stage (default: dev)"
    echo "  PROJECT_NAME  Project name (default: shara)"
    echo "  LOG_LEVEL     Log level for agents (default: INFO)"
    echo "  DEPLOY_MODE   Deploy mode: 'api' or 'cli' (default: api)"
    echo "                - api: Use Python API to deploy existing ECR image (no rebuild)"
    echo "                - cli: Use agentcore CLI (will rebuild image locally)"
    echo ""
    echo "The following are auto-detected from Terraform outputs or terraform.tfvars:"
    echo "  - TASKS_TABLE           DynamoDB tasks table"
    echo "  - TOKENS_TABLE          DynamoDB approval tokens table"
    echo "  - ASR_PLAYBOOKS_BUCKET  S3 bucket for ASR playbooks"
    echo "  - AGENTCORE_MEMORY_ID   AgentCore Memory ID for session management"
    echo ""
    echo "Examples:"
    echo "  $0 analyzer latest              # Deploy analyzer with existing 'latest' image"
    echo "  $0 all v1.0.0                   # Deploy all agents with v1.0.0 tag"
    echo "  STAGE=prod $0 all               # Deploy to prod stage"
    echo "  DEPLOY_MODE=cli $0 analyzer     # Deploy with CLI (rebuilds image)"
    echo "  LOG_LEVEL=DEBUG $0 analyzer     # Deploy with DEBUG logging"
}

# Get AWS account ID
get_account_id() {
    aws sts get-caller-identity --query Account --output text
}

# Get Terraform output
get_terraform_output() {
    local output_name="$1"
    if [[ -d "${INFRA_DIR}" ]]; then
        cd "${INFRA_DIR}"
        terraform output -raw "$output_name" 2>/dev/null || echo ""
        cd - > /dev/null
    fi
}

# Get ECR URI for agent type
get_ecr_uri() {
    local agent_type="$1"
    local output_name="${agent_type}_agent_ecr_url"
    local uri=$(get_terraform_output "$output_name")

    if [[ -z "$uri" ]]; then
        local account_id=$(get_account_id)
        uri="${account_id}.dkr.ecr.${AWS_REGION}.amazonaws.com/${PROJECT_NAME}-${STAGE}-${agent_type}-agent"
    fi
    echo "$uri"
}

# Get runtime role ARN
get_runtime_role_arn() {
    local role_arn=$(get_terraform_output "agentcore_runtime_role_arn")

    if [[ -z "$role_arn" ]]; then
        local account_id=$(get_account_id)
        role_arn="arn:aws:iam::${account_id}:role/${PROJECT_NAME}-${STAGE}-agentcore-runtime"
    fi
    echo "$role_arn"
}

# Get ASR Playbooks S3 bucket
get_asr_playbooks_bucket() {
    local bucket=$(get_terraform_output "asr_playbooks_bucket_id")

    if [[ -z "$bucket" ]]; then
        local account_id=$(get_account_id)
        bucket="${PROJECT_NAME}-${STAGE}-asr-playbooks-${account_id}"
    fi
    echo "$bucket"
}

# Get AgentCore Memory ID
get_memory_id() {
    local memory_id=$(get_terraform_output "agentcore_memory_id")

    if [[ -z "$memory_id" ]]; then
        # Try to read from terraform.tfvars
        if [[ -f "${INFRA_DIR}/terraform.tfvars" ]]; then
            memory_id=$(grep -E "^agentcore_memory_id" "${INFRA_DIR}/terraform.tfvars" | sed 's/.*= *"\([^"]*\)".*/\1/' || echo "")
        fi
    fi
    echo "$memory_id"
}

# Deploy agent using Python API (uses existing ECR image, no rebuild)
deploy_agent_api() {
    local agent_type="$1"
    local ecr_uri="$2"
    local runtime_role_arn="$3"
    local asr_bucket="$4"
    local memory_id="$5"
    local runtime_name="${PROJECT_NAME}_${STAGE}_${agent_type}"
    local full_image_uri="${ecr_uri}:${IMAGE_TAG}"

    log_step "Deploying ${agent_type} agent via API (using existing image)..."
    log_info "Runtime name: ${runtime_name}"
    log_info "Image URI: ${full_image_uri}"
    log_info "Role ARN: ${runtime_role_arn}"

    # Build environment variables JSON
    local env_vars_json="{"
    env_vars_json+="\"AGENT_TYPE\": \"${agent_type}\","
    env_vars_json+="\"STAGE\": \"${STAGE}\","
    env_vars_json+="\"AWS_REGION\": \"${AWS_REGION}\","
    env_vars_json+="\"LOG_LEVEL\": \"${LOG_LEVEL:-INFO}\","
    env_vars_json+="\"TASKS_TABLE\": \"${PROJECT_NAME}-${STAGE}-tasks\","
    env_vars_json+="\"TOKENS_TABLE\": \"${PROJECT_NAME}-${STAGE}-approval-tokens\","
    env_vars_json+="\"ASR_PLAYBOOKS_BUCKET\": \"${asr_bucket}\""
    if [[ -n "$memory_id" ]]; then
        env_vars_json+=",\"AGENTCORE_MEMORY_ID\": \"${memory_id}\""
    fi
    # OpenTelemetry configuration for observability
    env_vars_json+=",\"OTEL_PYTHON_DISTRO\": \"aws_distro\""
    env_vars_json+=",\"OTEL_PYTHON_CONFIGURATOR\": \"aws_configurator\""
    env_vars_json+=",\"OTEL_EXPORTER_OTLP_PROTOCOL\": \"http/protobuf\""
    env_vars_json+=",\"OTEL_RESOURCE_ATTRIBUTES\": \"service.name=${PROJECT_NAME}-${agent_type}\""
    env_vars_json+="}"

    # Deploy using Python script
    python3 << EOF
import json
import sys
from bedrock_agentcore_starter_toolkit.services.runtime import BedrockAgentCoreClient

region = "${AWS_REGION}"
runtime_name = "${runtime_name}"
image_uri = "${full_image_uri}"
role_arn = "${runtime_role_arn}"
env_vars = json.loads('${env_vars_json}')

print(f"Connecting to AgentCore in {region}...")
client = BedrockAgentCoreClient(region)

# Network configuration (PUBLIC mode)
network_config = {"networkMode": "PUBLIC"}

# Protocol configuration (HTTP)
protocol_config = {"serverProtocol": "HTTP"}

print(f"Creating/updating agent runtime: {runtime_name}")
try:
    result = client.create_or_update_agent(
        agent_id=None,  # Will be looked up by name if exists
        agent_name=runtime_name,
        execution_role_arn=role_arn,
        deployment_type="container",
        image_uri=image_uri,
        network_config=network_config,
        protocol_config=protocol_config,
        env_vars=env_vars,
        auto_update_on_conflict=True,
    )
    print(f"Success! Agent ID: {result['id']}")
    print(f"Agent ARN: {result['arn']}")

    # Wait for endpoint to be ready
    print("Waiting for endpoint to be ready...")
    endpoint_result = client.wait_for_agent_endpoint_ready(result['id'], max_wait=300)
    if "taking longer" in str(endpoint_result):
        print(f"Warning: {endpoint_result}")
    else:
        print(f"Endpoint ready: {endpoint_result}")

except Exception as e:
    print(f"Error: {e}", file=sys.stderr)
    sys.exit(1)
EOF

    log_info "${agent_type} agent deployed successfully!"
}

# Deploy agent using CLI (rebuilds image)
deploy_agent_cli() {
    local agent_type="$1"
    local ecr_uri="$2"
    local runtime_role_arn="$3"
    local asr_bucket="$4"
    local memory_id="$5"
    # AgentCore requires names with underscores only (no hyphens)
    local runtime_name="${PROJECT_NAME}_${STAGE}_${agent_type}"

    log_step "Deploying ${agent_type} agent via CLI (will rebuild)..."
    log_info "Runtime name: ${runtime_name}"
    log_info "ECR URI: ${ecr_uri}:${IMAGE_TAG}"
    log_info "Role ARN: ${runtime_role_arn}"

    cd "${AGENTS_DIR}"

    # Configure agent
    log_info "Configuring agent..."
    agentcore configure \
        --create \
        --name "${runtime_name}" \
        --entrypoint runtime.py \
        --execution-role "${runtime_role_arn}" \
        --ecr "${ecr_uri}" \
        --region "${AWS_REGION}" \
        --deployment-type container \
        --non-interactive

    # Build environment variables array
    local env_args=(
        --env "AGENT_TYPE=${agent_type}"
        --env "STAGE=${STAGE}"
        --env "AWS_REGION=${AWS_REGION}"
        --env "LOG_LEVEL=${LOG_LEVEL:-INFO}"
        --env "TASKS_TABLE=${PROJECT_NAME}-${STAGE}-tasks"
        --env "TOKENS_TABLE=${PROJECT_NAME}-${STAGE}-approval-tokens"
        --env "ASR_PLAYBOOKS_BUCKET=${asr_bucket}"
    )

    # Add Memory ID if configured
    if [[ -n "$memory_id" ]]; then
        env_args+=(--env "AGENTCORE_MEMORY_ID=${memory_id}")
    fi

    # Add OpenTelemetry configuration for observability
    env_args+=(--env "OTEL_PYTHON_DISTRO=aws_distro")
    env_args+=(--env "OTEL_PYTHON_CONFIGURATOR=aws_configurator")
    env_args+=(--env "OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf")
    env_args+=(--env "OTEL_RESOURCE_ATTRIBUTES=service.name=${PROJECT_NAME}-${agent_type}")

    # Deploy agent with environment variables
    log_info "Deploying to AgentCore Runtime..."
    agentcore deploy \
        --agent "${runtime_name}" \
        --image-tag "${IMAGE_TAG}" \
        --local-build \
        --auto-update-on-conflict \
        "${env_args[@]}"

    log_info "${agent_type} agent deployed successfully!"

    cd - > /dev/null
}

# Configure and deploy single agent (dispatcher)
deploy_agent() {
    local agent_type="$1"
    local ecr_uri="$2"
    local runtime_role_arn="$3"
    local asr_bucket="$4"
    local memory_id="$5"

    log_info "ASR Bucket: ${asr_bucket}"
    log_info "Memory ID: ${memory_id:-'(not configured)'}"
    log_info "Deploy Mode: ${DEPLOY_MODE}"

    if [[ "$DEPLOY_MODE" == "api" ]]; then
        deploy_agent_api "$agent_type" "$ecr_uri" "$runtime_role_arn" "$asr_bucket" "$memory_id"
    else
        deploy_agent_cli "$agent_type" "$ecr_uri" "$runtime_role_arn" "$asr_bucket" "$memory_id"
    fi
}

# Main function
main() {
    local agents_to_deploy=()
    local account_id
    local runtime_role_arn

    # Parse arguments
    if [[ "$1" == "-h" || "$1" == "--help" ]]; then
        usage
        exit 0
    fi

    # Check if agentcore CLI is available
    if ! command -v agentcore &> /dev/null; then
        log_error "agentcore CLI not found. Please install:"
        log_error "  pip install bedrock-agentcore-starter-toolkit"
        exit 1
    fi

    # Determine which agents to deploy
    case "$AGENT_TYPE" in
        all)
            agents_to_deploy=(analyzer remediator validator)
            ;;
        analyzer|remediator|validator)
            agents_to_deploy=("$AGENT_TYPE")
            ;;
        *)
            log_error "Invalid agent type: $AGENT_TYPE"
            log_error "Valid types: analyzer, remediator, validator, all"
            exit 1
            ;;
    esac

    log_step "=========================================="
    log_step "SHARA AgentCore Deployment"
    log_step "=========================================="
    log_info "Agents: ${agents_to_deploy[*]}"
    log_info "Tag: ${IMAGE_TAG}"
    log_info "Stage: ${STAGE}"
    log_info "Region: ${AWS_REGION}"
    log_info "Deploy Mode: ${DEPLOY_MODE}"
    if [[ "$DEPLOY_MODE" == "api" ]]; then
        log_info "  (Using existing ECR images - no rebuild)"
    else
        log_info "  (Will rebuild images locally)"
    fi
    echo ""

    # Get configuration
    account_id=$(get_account_id)
    log_info "Account ID: ${account_id}"

    runtime_role_arn=$(get_runtime_role_arn)
    log_info "Runtime Role: ${runtime_role_arn}"

    local asr_bucket=$(get_asr_playbooks_bucket)
    log_info "ASR Bucket: ${asr_bucket}"

    local memory_id=$(get_memory_id)
    if [[ -n "$memory_id" ]]; then
        log_info "Memory ID: ${memory_id}"
    else
        log_warn "Memory ID: (not configured - Memory features will be disabled)"
    fi
    echo ""

    # Deploy each agent
    local success_count=0
    local failed_count=0
    local failed_agents=""
    local success_agents=""

    for agent in "${agents_to_deploy[@]}"; do
        echo ""
        log_step "=========================================="

        ecr_uri=$(get_ecr_uri "$agent")

        if deploy_agent "$agent" "$ecr_uri" "$runtime_role_arn" "$asr_bucket" "$memory_id"; then
            success_agents="${success_agents} ${agent}"
            success_count=$((success_count + 1))
        else
            failed_agents="${failed_agents} ${agent}"
            failed_count=$((failed_count + 1))
            log_error "Failed to deploy ${agent} agent"
        fi
    done

    # Summary
    echo ""
    log_step "=========================================="
    log_step "DEPLOYMENT SUMMARY"
    log_step "=========================================="
    echo ""
    echo "Results:"
    for agent in ${success_agents}; do
        echo -e "  ${GREEN}✓${NC} ${agent}"
    done
    for agent in ${failed_agents}; do
        echo -e "  ${RED}✗${NC} ${agent}"
    done
    echo ""
    log_info "Successful: ${success_count}"
    log_info "Failed: ${failed_count}"
    echo ""

    # Get runtime status
    log_info "Getting runtime status..."
    agentcore status 2>/dev/null || true

    log_step "=========================================="

    if [[ $failed_count -gt 0 ]]; then
        exit 1
    fi
}

main "$@"
