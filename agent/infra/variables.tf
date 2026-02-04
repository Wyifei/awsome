###############################################################################
# Variables
###############################################################################

#------------------------------------------------------------------------------
# General
#------------------------------------------------------------------------------

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "shara"
}

variable "stage" {
  description = "Deployment stage (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.stage)
    error_message = "Stage must be one of: dev, staging, prod"
  }
}

variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "ap-northeast-1"
}

#------------------------------------------------------------------------------
# VPC Configuration
#------------------------------------------------------------------------------

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of availability zones"
  type        = list(string)
  default     = ["ap-northeast-1a", "ap-northeast-1c"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
  default     = ["10.0.11.0/24", "10.0.12.0/24"]
}

variable "enable_nat_gateway" {
  description = "Enable NAT Gateway for private subnets"
  type        = bool
  default     = true
}

variable "enable_vpc_endpoints" {
  description = "Enable VPC endpoints for AWS services"
  type        = bool
  default     = true
}

#------------------------------------------------------------------------------
# Lambda Configuration
#------------------------------------------------------------------------------

variable "lambda_runtime" {
  description = "Lambda runtime"
  type        = string
  default     = "python3.12"
}

variable "event_handler_timeout" {
  description = "Event handler Lambda timeout in seconds"
  type        = number
  default     = 300
}

variable "event_handler_memory" {
  description = "Event handler Lambda memory in MB"
  type        = number
  default     = 512
}

variable "approval_handler_timeout" {
  description = "Approval handler Lambda timeout in seconds"
  type        = number
  default     = 600
}

variable "approval_handler_memory" {
  description = "Approval handler Lambda memory in MB"
  type        = number
  default     = 1024
}

#------------------------------------------------------------------------------
# Feature Flags
#------------------------------------------------------------------------------

variable "enable_xray_tracing" {
  description = "Enable X-Ray tracing for Lambda functions"
  type        = bool
  default     = true
}

variable "enable_dlq" {
  description = "Enable Dead Letter Queue for EventBridge"
  type        = bool
  default     = false
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

#------------------------------------------------------------------------------
# AgentCore Configuration
#------------------------------------------------------------------------------

variable "agentcore_memory_id" {
  description = "AgentCore Memory ID for session management"
  type        = string
  default     = ""
}

variable "analyzer_runtime_arn" {
  description = "Analyzer Agent Runtime ARN"
  type        = string
  default     = ""
}

variable "remediator_runtime_arn" {
  description = "Remediator Agent Runtime ARN"
  type        = string
  default     = ""
}

variable "validator_runtime_arn" {
  description = "Validator Agent Runtime ARN"
  type        = string
  default     = ""
}

#------------------------------------------------------------------------------
# Email Configuration
#------------------------------------------------------------------------------

variable "approval_email" {
  description = "Email address for approval notifications"
  type        = string
  default     = ""
}

variable "sender_email" {
  description = "SES verified sender email address"
  type        = string
  default     = ""
}

variable "result_email" {
  description = "Email address to receive result notifications (defaults to approval_email if not set)"
  type        = string
  default     = ""
}

variable "approval_expiry_hours" {
  description = "Hours until approval token expires"
  type        = number
  default     = 24
}

variable "github_owner" {
  description = "GitHub owner/organization for container vulnerability remediation"
  type        = string
  default     = "Wyifei"
}

variable "github_repo" {
  description = "GitHub repository name for container vulnerability remediation"
  type        = string
  default     = "awsome"
}
