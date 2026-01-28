# ==============================================================================
# Kubernetes Resources Variables
# ==============================================================================

variable "project_name" {
  description = "项目名称"
  type        = string
}

variable "environment" {
  description = "环境名称"
  type        = string
}

variable "aws_region" {
  description = "AWS 区域"
  type        = string
}

variable "cluster_name" {
  description = "EKS 集群名称"
  type        = string
}

variable "cluster_endpoint" {
  description = "EKS 集群端点"
  type        = string
}

variable "cluster_certificate_authority_data" {
  description = "EKS 集群 CA 证书数据"
  type        = string
}

variable "oidc_provider_arn" {
  description = "OIDC Provider ARN"
  type        = string
}

variable "aws_lb_controller_role_arn" {
  description = "AWS Load Balancer Controller IAM Role ARN"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

# ==============================================================================
# AWS Load Balancer Controller
# ==============================================================================

variable "aws_lb_controller_version" {
  description = "AWS Load Balancer Controller Helm Chart 版本"
  type        = string
  default     = "1.7.1"
}

# ==============================================================================
# NGINX Ingress Controller
# ==============================================================================

variable "nginx_ingress_version" {
  description = "NGINX Ingress Controller Helm Chart 版本"
  type        = string
  default     = "4.9.1"
}

variable "nginx_ingress_replica_count" {
  description = "NGINX Ingress Controller 副本数"
  type        = number
  default     = 2
}

variable "enable_nginx_ingress" {
  description = "是否启用 NGINX Ingress Controller"
  type        = bool
  default     = true
}

variable "create_alb_ingress" {
  description = "是否通过 Terraform 创建 ALB Ingress (设为 false 则使用 kubectl apply manifest)"
  type        = bool
  default     = false
}
