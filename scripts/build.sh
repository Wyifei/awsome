#!/bin/bash

# ==============================================================================
# Auth Platform Microservices Build Script
# ==============================================================================
# This script builds and packages all microservices for the Auth Platform.
# It supports building individual services or all services at once.
#
# Usage:
#   ./scripts/build.sh [OPTIONS] [SERVICE...]
#
# Options:
#   -h, --help          Show this help message
#   -c, --clean         Clean before build
#   -s, --skip-tests    Skip running tests
#   -d, --docker        Build Docker images after Maven build
#   -p, --push          Push Docker images to ECR (requires -d)
#   -e, --env ENV       Environment (dev/production, default: production)
#   -t, --tag TAG       Docker image tag (default: latest)
#   -r, --registry REG  ECR registry URL (AWS Account ID)
#
# Services:
#   user-service, profile-service, notification-service, all (default)
#
# Examples:
#   ./scripts/build.sh                              # Build all services
#   ./scripts/build.sh user-service                 # Build only user-service
#   ./scripts/build.sh -c -s all                    # Clean build all, skip tests
#   ./scripts/build.sh -d -t v1.0.0 all             # Build all with Docker images
#   ./scripts/build.sh -d -p -e production -r 123456789012 all  # Build and push to ECR
# ==============================================================================

set -e

# Set JAVA_HOME to Java 21 if available (required for Lombok compatibility)
if /usr/libexec/java_home -v 21 &>/dev/null; then
    export JAVA_HOME=$(/usr/libexec/java_home -v 21)
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SERVICES_DIR="$PROJECT_ROOT/services"

# Default values
CLEAN=false
SKIP_TESTS=false
BUILD_DOCKER=false
PUSH_DOCKER=false
DOCKER_TAG="latest"
ECR_REGISTRY=""
ENVIRONMENT="production"
PROJECT_NAME="auth-platform"
AWS_REGION="ap-northeast-1"

# Available services
AVAILABLE_SERVICES=("user-service" "profile-service" "notification-service")

# Services to build
SERVICES_TO_BUILD=()

# ==============================================================================
# Helper Functions
# ==============================================================================

print_header() {
    echo -e "\n${BLUE}================================================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}================================================================${NC}\n"
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
    head -35 "$0" | tail -32
    exit 0
}

check_prerequisites() {
    print_header "Checking Prerequisites"

    # Check Java
    if command -v java &> /dev/null; then
        JAVA_VERSION=$(java -version 2>&1 | head -n 1 | cut -d'"' -f2)
        print_success "Java found: $JAVA_VERSION"
    else
        print_error "Java not found. Please install Java 17 or higher."
        exit 1
    fi

    # Check Maven
    if command -v mvn &> /dev/null; then
        MVN_VERSION=$(mvn -version 2>&1 | head -n 1)
        print_success "Maven found: $MVN_VERSION"
    else
        print_error "Maven not found. Please install Maven 3.8 or higher."
        exit 1
    fi

    # Check Docker (if needed)
    if [ "$BUILD_DOCKER" = true ]; then
        if command -v docker &> /dev/null; then
            DOCKER_VERSION=$(docker --version)
            print_success "Docker found: $DOCKER_VERSION"
        else
            print_error "Docker not found. Please install Docker."
            exit 1
        fi
    fi

    # Check AWS CLI (if pushing to ECR)
    if [ "$PUSH_DOCKER" = true ]; then
        if command -v aws &> /dev/null; then
            AWS_VERSION=$(aws --version)
            print_success "AWS CLI found: $AWS_VERSION"
        else
            print_error "AWS CLI not found. Please install AWS CLI."
            exit 1
        fi

        if [ -z "$ECR_REGISTRY" ]; then
            print_error "ECR registry URL is required for pushing images. Use -r option."
            exit 1
        fi
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

build_service() {
    local service=$1
    local service_dir="$SERVICES_DIR/$service"

    if [ ! -d "$service_dir" ]; then
        print_error "Service directory not found: $service_dir"
        return 1
    fi

    print_header "Building $service"

    cd "$service_dir"

    # Construct Maven command
    local mvn_cmd="mvn"

    if [ "$CLEAN" = true ]; then
        mvn_cmd="$mvn_cmd clean"
    fi

    mvn_cmd="$mvn_cmd package"

    if [ "$SKIP_TESTS" = true ]; then
        mvn_cmd="$mvn_cmd -DskipTests"
    fi

    print_info "Running: $mvn_cmd"

    if $mvn_cmd; then
        print_success "$service built successfully"

        # Show artifact info
        local jar_file=$(find target -name "*.jar" -not -name "*-sources.jar" -not -name "*-javadoc.jar" 2>/dev/null | head -1)
        if [ -n "$jar_file" ]; then
            local jar_size=$(du -h "$jar_file" | cut -f1)
            print_info "Artifact: $jar_file ($jar_size)"
        fi
    else
        print_error "$service build failed"
        return 1
    fi

    cd "$PROJECT_ROOT"
}

build_docker_image() {
    local service=$1
    local service_dir="$SERVICES_DIR/$service"

    if [ ! -f "$service_dir/Dockerfile" ]; then
        print_warning "Dockerfile not found for $service, skipping Docker build"
        return 0
    fi

    print_header "Building Docker image for $service"

    cd "$service_dir"

    # ECR repository naming: {project}-{environment}/{service}
    local ecr_repo_name="${PROJECT_NAME}-${ENVIRONMENT}/${service}"
    local local_tag="${service}:${DOCKER_TAG}"

    print_info "Building image: $local_tag"

    if docker build -t "$local_tag" .; then
        print_success "Docker image built: $local_tag"

        # Tag for ECR if registry is provided
        if [ -n "$ECR_REGISTRY" ]; then
            local ecr_url="${ECR_REGISTRY}.dkr.ecr.${AWS_REGION}.amazonaws.com"
            local ecr_tag="${ecr_url}/${ecr_repo_name}:${DOCKER_TAG}"
            docker tag "$local_tag" "$ecr_tag"
            print_info "Tagged for ECR: $ecr_tag"
        fi
    else
        print_error "Docker build failed for $service"
        return 1
    fi

    cd "$PROJECT_ROOT"
}

push_docker_image() {
    local service=$1
    local ecr_repo_name="${PROJECT_NAME}-${ENVIRONMENT}/${service}"
    local ecr_url="${ECR_REGISTRY}.dkr.ecr.${AWS_REGION}.amazonaws.com"
    local ecr_tag="${ecr_url}/${ecr_repo_name}:${DOCKER_TAG}"

    print_header "Pushing Docker image for $service"

    # Login to ECR
    print_info "Logging in to ECR..."
    aws ecr get-login-password --region "$AWS_REGION" | \
        docker login --username AWS --password-stdin "$ecr_url"

    print_info "Pushing: $ecr_tag"

    if docker push "$ecr_tag"; then
        print_success "Image pushed: $ecr_tag"
    else
        print_error "Failed to push image for $service"
        return 1
    fi
}

print_summary() {
    print_header "Build Summary"

    echo -e "Services built: ${GREEN}${SERVICES_TO_BUILD[*]}${NC}"
    echo -e "Environment: ${BLUE}${ENVIRONMENT}${NC}"
    echo -e "Clean build: $([ "$CLEAN" = true ] && echo "${GREEN}Yes${NC}" || echo "${YELLOW}No${NC}")"
    echo -e "Tests: $([ "$SKIP_TESTS" = true ] && echo "${YELLOW}Skipped${NC}" || echo "${GREEN}Executed${NC}")"
    echo -e "Docker images: $([ "$BUILD_DOCKER" = true ] && echo "${GREEN}Built${NC}" || echo "${YELLOW}Skipped${NC}")"

    if [ "$BUILD_DOCKER" = true ]; then
        echo -e "Docker tag: ${BLUE}$DOCKER_TAG${NC}"
        echo -e "ECR repo format: ${BLUE}${PROJECT_NAME}-${ENVIRONMENT}/<service>${NC}"
    fi

    if [ "$PUSH_DOCKER" = true ]; then
        echo -e "ECR push: ${GREEN}Completed${NC}"
        echo -e "ECR registry: ${BLUE}${ECR_REGISTRY}.dkr.ecr.${AWS_REGION}.amazonaws.com${NC}"
    fi

    echo ""
    print_success "Build completed successfully!"
}

# ==============================================================================
# Parse Arguments
# ==============================================================================

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            ;;
        -c|--clean)
            CLEAN=true
            shift
            ;;
        -s|--skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        -d|--docker)
            BUILD_DOCKER=true
            shift
            ;;
        -p|--push)
            PUSH_DOCKER=true
            BUILD_DOCKER=true
            shift
            ;;
        -t|--tag)
            DOCKER_TAG="$2"
            shift 2
            ;;
        -r|--registry)
            ECR_REGISTRY="$2"
            shift 2
            ;;
        -e|--env)
            ENVIRONMENT="$2"
            shift 2
            ;;
        --region)
            AWS_REGION="$2"
            shift 2
            ;;
        all)
            SERVICES_TO_BUILD=("${AVAILABLE_SERVICES[@]}")
            shift
            ;;
        *)
            if validate_service "$1"; then
                SERVICES_TO_BUILD+=("$1")
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
if [ ${#SERVICES_TO_BUILD[@]} -eq 0 ]; then
    SERVICES_TO_BUILD=("${AVAILABLE_SERVICES[@]}")
fi

# ==============================================================================
# Main Execution
# ==============================================================================

print_header "Auth Platform Build Script"
echo "Services to build: ${SERVICES_TO_BUILD[*]}"
echo "Project root: $PROJECT_ROOT"

check_prerequisites

# Build each service
BUILD_FAILED=false
for service in "${SERVICES_TO_BUILD[@]}"; do
    if ! build_service "$service"; then
        BUILD_FAILED=true
        break
    fi

    if [ "$BUILD_DOCKER" = true ]; then
        if ! build_docker_image "$service"; then
            BUILD_FAILED=true
            break
        fi
    fi

    if [ "$PUSH_DOCKER" = true ]; then
        if ! push_docker_image "$service"; then
            BUILD_FAILED=true
            break
        fi
    fi
done

if [ "$BUILD_FAILED" = true ]; then
    print_error "Build failed!"
    exit 1
fi

print_summary
