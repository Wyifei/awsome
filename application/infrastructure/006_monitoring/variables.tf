# ==============================================================================
# Variables for Monitoring Module
# ==============================================================================

variable "project_name" {
  description = "项目名称"
  type        = string
}

variable "environment" {
  description = "环境名称"
  type        = string
}

variable "oidc_provider_arn" {
  description = "EKS OIDC Provider ARN (用于 IRSA)"
  type        = string
}
