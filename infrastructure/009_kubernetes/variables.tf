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

# ==============================================================================
# Prometheus (Metrics Collection)
# ==============================================================================

variable "enable_prometheus" {
  description = "是否启用 Prometheus 指标收集"
  type        = bool
  default     = false
}

variable "prometheus_remote_write_url" {
  description = "AWS Managed Prometheus Remote Write URL"
  type        = string
  default     = ""
}

variable "prometheus_remote_write_role_arn" {
  description = "Prometheus Remote Write IAM Role ARN"
  type        = string
  default     = ""
}

# ==============================================================================
# ADOT Collector (AWS Distro for OpenTelemetry)
# ==============================================================================

variable "enable_adot_collector" {
  description = "是否启用 ADOT Collector (用于抓取 Prometheus 指标)"
  type        = bool
  default     = false
}

variable "adot_collector_role_arn" {
  description = "ADOT Collector IAM Role ARN (用于 Remote Write 到 AMP)"
  type        = string
  default     = ""
}

# ==============================================================================
# Grafana (Self-hosted with Cognito OAuth)
# ==============================================================================

variable "enable_grafana" {
  description = "是否启用 Grafana"
  type        = bool
  default     = false
}

variable "grafana_role_arn" {
  description = "Grafana IAM Role ARN (用于查询 AMP)"
  type        = string
  default     = ""
}

variable "grafana_admin_password" {
  description = "Grafana 管理员密码"
  type        = string
  default     = "admin123!"
  sensitive   = true
}

variable "grafana_root_url" {
  description = "Grafana Root URL (用于 OAuth 回调，例如: http://your-alb-dns/grafana/)"
  type        = string
  default     = "%(protocol)s://%(domain)s:%(http_port)s/grafana/"
}

variable "prometheus_query_url" {
  description = "AWS Managed Prometheus Query URL"
  type        = string
  default     = ""
}

