#!/bin/bash

# ==============================================================================
# Auth Platform Deployment Script
# ==============================================================================
# This script automates the deployment of all microservices to EKS.
# It handles environment setup, secrets creation, and Kubernetes deployment.
#
# Usage:
#   ./scripts/deploy.sh [OPTIONS] [SERVICE...]
#
# Options:
#   -h, --help              Show this help message
#   -b, --build             Build and push Docker images before deploying
#   -t, --tag TAG           Docker image tag (default: latest)
#   -e, --env ENV           Environment (dev/production, default: production)
#   -s, --skip-secrets      Skip creating/updating Kubernetes secrets
#   -c, --create-secrets    Only create secrets, don't deploy services
#   -n, --dry-run           Show what would be deployed without applying
#   --skip-tests            Skip tests when building (only with -b)
#   --region REGION         AWS region (default: ap-northeast-1)
#
# Services:
#   user-service, profile-service, notification-service, all (default)
#
# Prerequisites:
#   - AWS CLI v2 configured with appropriate permissions
#   - kubectl configured for EKS cluster
#   - kustomize (or kubectl with kustomize support)
#   - jq for JSON parsing
#   - envsubst for variable substitution
#
# Examples:
#   ./scripts/deploy.sh                          # Deploy all services
#   ./scripts/deploy.sh -b all                   # Build and deploy all
#   ./scripts/deploy.sh user-service             # Deploy only user-service
#   ./scripts/deploy.sh -c                       # Only create secrets
#   ./scripts/deploy.sh -n all                   # Dry run deployment
#   ./scripts/deploy.sh -b -t v1.0.0 all         # Build with tag and deploy
# ==============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SERVICES_DIR="$PROJECT_ROOT/services"
INFRA_DIR="$PROJECT_ROOT/infrastructure"

# Default values
BUILD_IMAGES=false
SKIP_SECRETS=false
CREATE_SECRETS_ONLY=false
DRY_RUN=false
SKIP_TESTS=false
DOCKER_TAG="latest"
ENVIRONMENT="production"
PROJECT_NAME="auth-platform"
AWS_REGION="ap-northeast-1"
NAMESPACE="auth-platform"

# Available services
AVAILABLE_SERVICES=("user-service" "profile-service" "notification-service")

# Services to deploy
SERVICES_TO_DEPLOY=()

# Environment variables (will be populated)
AWS_ACCOUNT_ID=""
ECR_REGISTRY=""
APP_SERVICE_ROLE_ARN=""
AURORA_CLUSTER_ENDPOINT=""
DB_USERNAME=""
DB_PASSWORD=""
COGNITO_USER_POOL_ID=""
S3_AVATARS_BUCKET=""
CLOUDFRONT_DOMAIN=""
SES_FROM_ADDRESS=""

# ==============================================================================
# Helper Functions
# ==============================================================================

print_header() {
    echo -e "\n${BLUE}================================================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}================================================================${NC}\n"
}

print_step() {
    echo -e "\n${CYAN}>>> $1${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

show_help() {
    head -40 "$0" | tail -37
    exit 0
}

check_prerequisites() {
    print_header "Checking Prerequisites"

    local failed=false

    # Check AWS CLI
    if command -v aws &> /dev/null; then
        print_success "AWS CLI found: $(aws --version 2>&1 | head -1)"
    else
        print_error "AWS CLI not found. Please install AWS CLI v2."
        failed=true
    fi

    # Check kubectl
    if command -v kubectl &> /dev/null; then
        print_success "kubectl found: $(kubectl version --client --short 2>/dev/null || kubectl version --client 2>&1 | head -1)"
    else
        print_error "kubectl not found. Please install kubectl."
        failed=true
    fi

    # Check kustomize (or kubectl kustomize)
    if command -v kustomize &> /dev/null; then
        print_success "kustomize found: $(kustomize version --short 2>/dev/null || kustomize version 2>&1 | head -1)"
    elif kubectl kustomize --help &> /dev/null; then
        print_success "kubectl kustomize available"
    else
        print_error "kustomize not found. Please install kustomize or use kubectl with kustomize support."
        failed=true
    fi

    # Check jq
    if command -v jq &> /dev/null; then
        print_success "jq found: $(jq --version)"
    else
        print_error "jq not found. Please install jq."
        failed=true
    fi

    # Check envsubst
    if command -v envsubst &> /dev/null; then
        print_success "envsubst found"
    else
        print_error "envsubst not found. Please install gettext package."
        failed=true
    fi

    # Check terraform (optional, for fetching outputs)
    if command -v terraform &> /dev/null; then
        print_success "terraform found: $(terraform version -json 2>/dev/null | jq -r '.terraform_version' 2>/dev/null || terraform version 2>&1 | head -1)"
    else
        print_warning "terraform not found. Will use manual environment variable setup."
    fi

    if [ "$failed" = true ]; then
        print_error "Prerequisites check failed. Please install missing tools."
        exit 1
    fi
}

validate_service() {
    local service=$1
    for valid_service in "${AVAILABLE_SERVICES[@]}"; do
        if [ "$service" = "$valid_service" ]; then
            return 0
        fi
    done
    return 1
}

# ==============================================================================
# Environment Setup Functions
# ==============================================================================

setup_aws_credentials() {
    print_step "Setting up AWS credentials"

    # Get AWS Account ID
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
    if [ -z "$AWS_ACCOUNT_ID" ]; then
        print_error "Failed to get AWS Account ID. Please configure AWS CLI."
        exit 1
    fi
    print_success "AWS Account ID: $AWS_ACCOUNT_ID"

    # Set ECR Registry
    ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
    print_info "ECR Registry: $ECR_REGISTRY"

    # Set IRSA Role ARN
    APP_SERVICE_ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/${PROJECT_NAME}-${ENVIRONMENT}-app-service-role"
    print_info "App Service Role ARN: $APP_SERVICE_ROLE_ARN"
}

fetch_terraform_outputs() {
    print_step "Fetching infrastructure values from Terraform"

    if [ ! -d "$INFRA_DIR" ]; then
        print_warning "Infrastructure directory not found: $INFRA_DIR"
        return 1
    fi

    cd "$INFRA_DIR"

    # Check if terraform state exists
    if ! terraform state list &> /dev/null; then
        print_warning "Terraform state not found. Using environment variables or manual setup."
        cd "$PROJECT_ROOT"
        return 1
    fi

    # Fetch outputs
    local tf_outputs
    tf_outputs=$(terraform output -json 2>/dev/null)

    if [ -n "$tf_outputs" ]; then
        AURORA_CLUSTER_ENDPOINT=$(echo "$tf_outputs" | jq -r '.aurora_cluster_endpoint.value // empty' 2>/dev/null)
        COGNITO_USER_POOL_ID=$(echo "$tf_outputs" | jq -r '.cognito_user_pool_id.value // empty' 2>/dev/null)
        S3_AVATARS_BUCKET=$(echo "$tf_outputs" | jq -r '.s3_avatars_bucket.value // empty' 2>/dev/null)
        CLOUDFRONT_DOMAIN=$(echo "$tf_outputs" | jq -r '.cloudfront_domain_name.value // empty' 2>/dev/null)

        # Try to get SES email from terraform.tfvars (only if not already set via env var)
        if [ -z "$SES_FROM_ADDRESS" ] && [ -f "terraform.tfvars" ]; then
            local ses_email
            # Support both ses_email_address and ses_from_email variable names
            # Extract value after '=' sign, remove quotes and whitespace
            ses_email=$(grep -E "^ses_email_address\s*=" terraform.tfvars 2>/dev/null | cut -d'=' -f2 | tr -d ' "'"'" | head -1)
            if [ -z "$ses_email" ]; then
                ses_email=$(grep -E "^ses_from_email\s*=" terraform.tfvars 2>/dev/null | cut -d'=' -f2 | tr -d ' "'"'" | head -1)
            fi
            # Validate email format (basic check)
            if [[ "$ses_email" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
                SES_FROM_ADDRESS="$ses_email"
            elif [ -n "$ses_email" ]; then
                print_warning "Invalid SES email format in terraform.tfvars: $ses_email"
            fi
        fi

        print_success "Aurora Endpoint: $AURORA_CLUSTER_ENDPOINT"
        print_success "Cognito User Pool ID: $COGNITO_USER_POOL_ID"
        print_success "S3 Avatars Bucket: $S3_AVATARS_BUCKET"
        print_success "CloudFront Domain: $CLOUDFRONT_DOMAIN"
        [ -n "$SES_FROM_ADDRESS" ] && print_success "SES From Email: $SES_FROM_ADDRESS"
    else
        print_warning "Could not fetch terraform outputs"
        cd "$PROJECT_ROOT"
        return 1
    fi

    cd "$PROJECT_ROOT"
    return 0
}

fetch_database_credentials() {
    print_step "Fetching database credentials from Secrets Manager"

    # Find RDS managed secret
    local rds_secret_arn
    rds_secret_arn=$(aws secretsmanager list-secrets \
        --region "$AWS_REGION" \
        --query "SecretList[?contains(Name, 'rds!cluster')].ARN | [0]" \
        --output text 2>/dev/null)

    if [ -z "$rds_secret_arn" ] || [ "$rds_secret_arn" = "None" ]; then
        print_error "RDS managed secret not found. Please check Aurora cluster configuration."
        exit 1
    fi

    print_info "RDS Secret ARN: $rds_secret_arn"

    # Get credentials
    local secret_value
    secret_value=$(aws secretsmanager get-secret-value \
        --secret-id "$rds_secret_arn" \
        --region "$AWS_REGION" \
        --query SecretString \
        --output text 2>/dev/null)

    if [ -z "$secret_value" ]; then
        print_error "Failed to retrieve database credentials from Secrets Manager."
        exit 1
    fi

    DB_USERNAME=$(echo "$secret_value" | jq -r '.username')
    DB_PASSWORD=$(echo "$secret_value" | jq -r '.password')

    if [ -z "$DB_USERNAME" ] || [ -z "$DB_PASSWORD" ]; then
        print_error "Failed to parse database credentials."
        exit 1
    fi

    print_success "Database username: $DB_USERNAME"
    print_success "Database password: [RETRIEVED]"
}

validate_environment_variables() {
    print_step "Validating environment variables"

    local missing=()

    [ -z "$AWS_ACCOUNT_ID" ] && missing+=("AWS_ACCOUNT_ID")
    [ -z "$AURORA_CLUSTER_ENDPOINT" ] && missing+=("AURORA_CLUSTER_ENDPOINT")
    [ -z "$DB_USERNAME" ] && missing+=("DB_USERNAME")
    [ -z "$DB_PASSWORD" ] && missing+=("DB_PASSWORD")
    [ -z "$COGNITO_USER_POOL_ID" ] && missing+=("COGNITO_USER_POOL_ID")
    [ -z "$S3_AVATARS_BUCKET" ] && missing+=("S3_AVATARS_BUCKET")
    [ -z "$CLOUDFRONT_DOMAIN" ] && missing+=("CLOUDFRONT_DOMAIN")

    if [ ${#missing[@]} -gt 0 ]; then
        print_error "Missing required environment variables:"
        for var in "${missing[@]}"; do
            echo "  - $var"
        done
        print_info "Please set these variables manually or ensure Terraform outputs are available."
        exit 1
    fi

    # Set defaults for optional variables
    SES_FROM_ADDRESS="${SES_FROM_ADDRESS:-noreply@example.com}"

    print_success "All required environment variables are set"
}

# ==============================================================================
# Kubernetes Functions
# ==============================================================================

configure_kubectl() {
    print_step "Configuring kubectl for EKS"

    local cluster_name="${PROJECT_NAME}-${ENVIRONMENT}"

    aws eks update-kubeconfig \
        --name "$cluster_name" \
        --region "$AWS_REGION" \
        2>/dev/null

    # Verify connection
    if kubectl get nodes &> /dev/null; then
        print_success "kubectl configured for cluster: $cluster_name"
        kubectl get nodes
    else
        print_error "Failed to connect to EKS cluster: $cluster_name"
        exit 1
    fi
}

create_namespace() {
    print_step "Ensuring namespace exists: $NAMESPACE"

    if kubectl get namespace "$NAMESPACE" &> /dev/null; then
        print_info "Namespace $NAMESPACE already exists"
    else
        if [ "$DRY_RUN" = true ]; then
            print_info "[DRY RUN] Would create namespace: $NAMESPACE"
        else
            kubectl create namespace "$NAMESPACE"
            print_success "Created namespace: $NAMESPACE"
        fi
    fi
}

create_kubernetes_secrets() {
    print_step "Creating Kubernetes Secrets"

    if [ "$DRY_RUN" = true ]; then
        print_info "[DRY RUN] Would create the following secrets:"
        echo "  - user-service-secret"
        echo "  - profile-service-secret"
        echo "  - notification-service-secret"
        return 0
    fi

    # user-service Secret
    print_info "Creating user-service-secret..."
    kubectl delete secret user-service-secret -n "$NAMESPACE" 2>/dev/null || true
    kubectl create secret generic user-service-secret -n "$NAMESPACE" \
        --from-literal=DB_HOST="$AURORA_CLUSTER_ENDPOINT" \
        --from-literal=DB_USERNAME="$DB_USERNAME" \
        --from-literal=DB_PASSWORD="$DB_PASSWORD" \
        --from-literal=COGNITO_USER_POOL_ID="$COGNITO_USER_POOL_ID"
    print_success "Created user-service-secret"

    # profile-service Secret
    print_info "Creating profile-service-secret..."
    kubectl delete secret profile-service-secret -n "$NAMESPACE" 2>/dev/null || true
    kubectl create secret generic profile-service-secret -n "$NAMESPACE" \
        --from-literal=DB_HOST="$AURORA_CLUSTER_ENDPOINT" \
        --from-literal=DB_USERNAME="$DB_USERNAME" \
        --from-literal=DB_PASSWORD="$DB_PASSWORD" \
        --from-literal=COGNITO_USER_POOL_ID="$COGNITO_USER_POOL_ID" \
        --from-literal=S3_AVATAR_BUCKET="$S3_AVATARS_BUCKET" \
        --from-literal=CLOUDFRONT_DOMAIN="$CLOUDFRONT_DOMAIN"
    print_success "Created profile-service-secret"

    # notification-service Secret
    print_info "Creating notification-service-secret..."
    kubectl delete secret notification-service-secret -n "$NAMESPACE" 2>/dev/null || true
    kubectl create secret generic notification-service-secret -n "$NAMESPACE" \
        --from-literal=SES_FROM_ADDRESS="$SES_FROM_ADDRESS" \
        --from-literal=SES_FROM_NAME="Auth Platform"
    print_success "Created notification-service-secret"

    print_success "All secrets created successfully"
}

# ==============================================================================
# Build and Deploy Functions
# ==============================================================================

build_and_push_images() {
    print_step "Building and pushing Docker images"

    local build_args="-d -p -e $ENVIRONMENT -r $AWS_ACCOUNT_ID -t $DOCKER_TAG"

    if [ "$SKIP_TESTS" = true ]; then
        build_args="$build_args -s"
    fi

    local services_arg=""
    if [ ${#SERVICES_TO_DEPLOY[@]} -eq ${#AVAILABLE_SERVICES[@]} ]; then
        services_arg="all"
    else
        services_arg="${SERVICES_TO_DEPLOY[*]}"
    fi

    print_info "Running: ./scripts/build.sh $build_args $services_arg"

    if [ "$DRY_RUN" = true ]; then
        print_info "[DRY RUN] Would run: ./scripts/build.sh $build_args $services_arg"
        return 0
    fi

    "$SCRIPT_DIR/build.sh" $build_args $services_arg
}

deploy_service() {
    local service=$1
    local service_dir="$SERVICES_DIR/$service/kustomize/overlays/$ENVIRONMENT"

    if [ ! -d "$service_dir" ]; then
        print_error "Kustomize overlay not found: $service_dir"
        return 1
    fi

    print_info "Deploying $service..."

    # Export variables for envsubst
    export AWS_ACCOUNT_ID
    export APP_SERVICE_ROLE_ARN
    export AURORA_CLUSTER_ENDPOINT
    export DB_PASSWORD
    export COGNITO_USER_POOL_ID
    export S3_AVATARS_BUCKET
    export CLOUDFRONT_DOMAIN
    export SES_FROM_ADDRESS

    # Define envsubst variables
    local envsubst_vars='${AWS_ACCOUNT_ID} ${APP_SERVICE_ROLE_ARN} ${AURORA_CLUSTER_ENDPOINT} ${DB_PASSWORD} ${COGNITO_USER_POOL_ID} ${S3_AVATARS_BUCKET} ${CLOUDFRONT_DOMAIN} ${SES_FROM_ADDRESS}'

    if [ "$DRY_RUN" = true ]; then
        print_info "[DRY RUN] Would deploy:"
        kustomize build "$service_dir" | envsubst "$envsubst_vars" | head -50
        echo "..."
        return 0
    fi

    # Build and apply
    kustomize build "$service_dir" | \
        envsubst "$envsubst_vars" | \
        kubectl apply -f -

    print_success "$service deployed"
}

deploy_services() {
    print_step "Deploying services to Kubernetes"

    for service in "${SERVICES_TO_DEPLOY[@]}"; do
        deploy_service "$service"
    done
}

wait_for_rollouts() {
    print_step "Waiting for rollouts to complete"

    if [ "$DRY_RUN" = true ]; then
        print_info "[DRY RUN] Would wait for rollouts"
        return 0
    fi

    local failed=false

    for service in "${SERVICES_TO_DEPLOY[@]}"; do
        print_info "Waiting for $service rollout..."
        if kubectl rollout status deployment/"$service" -n "$NAMESPACE" --timeout=300s; then
            print_success "$service rollout complete"
        else
            print_error "$service rollout failed"
            failed=true
        fi
    done

    if [ "$failed" = true ]; then
        print_error "Some rollouts failed. Check pod status with: kubectl get pods -n $NAMESPACE"
        return 1
    fi
}

# ==============================================================================
# Verification Functions
# ==============================================================================

verify_deployment() {
    print_step "Verifying deployment"

    if [ "$DRY_RUN" = true ]; then
        print_info "[DRY RUN] Would verify deployment"
        return 0
    fi

    echo ""
    print_info "Pod status:"
    kubectl get pods -n "$NAMESPACE" -o wide

    echo ""
    print_info "Service status:"
    kubectl get svc -n "$NAMESPACE"

    echo ""
    print_info "Ingress status:"
    kubectl get ingress -n "$NAMESPACE"

    echo ""
    print_info "HPA status:"
    kubectl get hpa -n "$NAMESPACE" 2>/dev/null || print_info "No HPA configured"
}

# ==============================================================================
# Summary Function
# ==============================================================================

print_summary() {
    print_header "Deployment Summary"

    echo -e "Services deployed: ${GREEN}${SERVICES_TO_DEPLOY[*]}${NC}"
    echo -e "Environment: ${BLUE}$ENVIRONMENT${NC}"
    echo -e "AWS Region: ${BLUE}$AWS_REGION${NC}"
    echo -e "Namespace: ${BLUE}$NAMESPACE${NC}"

    if [ "$BUILD_IMAGES" = true ]; then
        echo -e "Docker images: ${GREEN}Built and pushed${NC}"
        echo -e "Image tag: ${BLUE}$DOCKER_TAG${NC}"
    fi

    echo ""
    print_success "Deployment completed successfully!"

    echo ""
    print_info "Useful commands:"
    echo "  kubectl get pods -n $NAMESPACE                    # View pod status"
    echo "  kubectl logs -n $NAMESPACE -l app=<service> -f    # View service logs"
    echo "  kubectl describe pod -n $NAMESPACE -l app=<service>  # Pod details"
}

# ==============================================================================
# Parse Arguments
# ==============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            ;;
        -b|--build)
            BUILD_IMAGES=true
            shift
            ;;
        -t|--tag)
            DOCKER_TAG="$2"
            shift 2
            ;;
        -e|--env)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -s|--skip-secrets)
            SKIP_SECRETS=true
            shift
            ;;
        -c|--create-secrets)
            CREATE_SECRETS_ONLY=true
            shift
            ;;
        -n|--dry-run)
            DRY_RUN=true
            shift
            ;;
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        --region)
            AWS_REGION="$2"
            shift 2
            ;;
        all)
            SERVICES_TO_DEPLOY=("${AVAILABLE_SERVICES[@]}")
            shift
            ;;
        *)
            if validate_service "$1"; then
                SERVICES_TO_DEPLOY+=("$1")
            else
                print_error "Unknown option or service: $1"
                echo "Use -h for help"
                exit 1
            fi
            shift
            ;;
    esac
done

# Default to all services if none specified
if [ ${#SERVICES_TO_DEPLOY[@]} -eq 0 ]; then
    SERVICES_TO_DEPLOY=("${AVAILABLE_SERVICES[@]}")
fi

# ==============================================================================
# Main Execution
# ==============================================================================

print_header "Auth Platform Deployment Script"
echo "Services: ${SERVICES_TO_DEPLOY[*]}"
echo "Environment: $ENVIRONMENT"
echo "Project root: $PROJECT_ROOT"

if [ "$DRY_RUN" = true ]; then
    print_warning "DRY RUN MODE - No changes will be made"
fi

# Check prerequisites
check_prerequisites

# Setup environment
setup_aws_credentials
fetch_terraform_outputs || print_warning "Terraform outputs not available, using environment variables"
fetch_database_credentials
validate_environment_variables

# Configure kubectl
configure_kubectl

# Create namespace
create_namespace

# Create secrets
if [ "$SKIP_SECRETS" != true ]; then
    create_kubernetes_secrets
fi

# Exit if only creating secrets
if [ "$CREATE_SECRETS_ONLY" = true ]; then
    print_success "Secrets creation complete"
    exit 0
fi

# Build images if requested
if [ "$BUILD_IMAGES" = true ]; then
    build_and_push_images
fi

# Deploy services
deploy_services

# Wait for rollouts
wait_for_rollouts

# Verify deployment
verify_deployment

# Print summary
print_summary
