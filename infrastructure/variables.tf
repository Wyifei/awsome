# ==============================================================================
# 通用变量
# ==============================================================================

variable "aws_region" {
  description = "AWS 区域"
  type        = string
  default     = "ap-northeast-1"
}

variable "project_name" {
  description = "项目名称"
  type        = string
  default     = "auth-platform"
}

variable "environment" {
  description = "环境名称"
  type        = string
  default     = "production"
}

# ==============================================================================
# VPC 变量
# ==============================================================================

variable "vpc_cidr" {
  description = "VPC CIDR 块"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "可用区列表"
  type        = list(string)
  default     = ["ap-northeast-1a", "ap-northeast-1c"]
}

variable "public_subnet_cidrs" {
  description = "公有子网 CIDR 列表"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "私有子网 (计算) CIDR 列表"
  type        = list(string)
  default     = ["10.0.11.0/24", "10.0.12.0/24"]
}

variable "database_subnet_cidrs" {
  description = "数据库子网 CIDR 列表"
  type        = list(string)
  default     = ["10.0.21.0/24", "10.0.22.0/24"]
}

# ==============================================================================
# EKS 变量
# ==============================================================================

variable "eks_cluster_version" {
  description = "EKS Kubernetes 版本"
  type        = string
  default     = "1.31"
}

variable "eks_node_instance_types" {
  description = "EKS Worker 节点实例类型"
  type        = list(string)
  default     = ["m6i.large"]
}

variable "eks_node_desired_size" {
  description = "EKS Worker 节点期望数量"
  type        = number
  default     = 2
}

variable "eks_node_min_size" {
  description = "EKS Worker 节点最小数量"
  type        = number
  default     = 2
}

variable "eks_node_max_size" {
  description = "EKS Worker 节点最大数量"
  type        = number
  default     = 6
}

variable "eks_node_disk_size" {
  description = "EKS Worker 节点磁盘大小 (GB)"
  type        = number
  default     = 50
}

# ==============================================================================
# Aurora 变量
# ==============================================================================

variable "aurora_engine_version" {
  description = "Aurora PostgreSQL 引擎版本"
  type        = string
  default     = "16.4"
}

variable "aurora_instance_class" {
  description = "Aurora 实例类型"
  type        = string
  default     = "db.r6g.large"
}

variable "aurora_database_name" {
  description = "Aurora 数据库名称"
  type        = string
  default     = "auth_platform"
}

variable "aurora_master_username" {
  description = "Aurora 主用户名"
  type        = string
  default     = "admin"
}

variable "aurora_backup_retention_period" {
  description = "Aurora 备份保留天数"
  type        = number
  default     = 7
}

# ==============================================================================
# Cognito 变量
# ==============================================================================

variable "cognito_user_pool_name" {
  description = "Cognito User Pool 名称"
  type        = string
  default     = "auth-platform-users"
}

variable "cognito_callback_urls" {
  description = "Cognito OAuth 回调 URL 列表"
  type        = list(string)
  default     = []
}

variable "cognito_logout_urls" {
  description = "Cognito OAuth 登出 URL 列表"
  type        = list(string)
  default     = []
}

variable "ses_email_address" {
  description = "SES 发送邮件地址"
  type        = string
}

# ==============================================================================
# WAF 变量
# ==============================================================================

variable "waf_rate_limit" {
  description = "WAF 速率限制 (每 5 分钟)"
  type        = number
  default     = 2000
}

variable "waf_cognito_rate_limit" {
  description = "Cognito Token 端点速率限制 (每 5 分钟)"
  type        = number
  default     = 100
}

# ==============================================================================
# Kubernetes 变量
# ==============================================================================

variable "enable_nginx_ingress" {
  description = "是否启用 NGINX Ingress Controller"
  type        = bool
  default     = true
}

variable "nginx_ingress_replica_count" {
  description = "NGINX Ingress Controller 副本数"
  type        = number
  default     = 2
}
