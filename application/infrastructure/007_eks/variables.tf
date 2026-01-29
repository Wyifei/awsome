variable "project_name" {
  description = "项目名称"
  type        = string
}

variable "environment" {
  description = "环境名称"
  type        = string
}

variable "cluster_version" {
  description = "EKS Kubernetes 版本"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "private_subnet_ids" {
  description = "私有子网 ID 列表"
  type        = list(string)
}

variable "node_instance_types" {
  description = "Worker 节点实例类型"
  type        = list(string)
}

variable "node_desired_size" {
  description = "Worker 节点期望数量"
  type        = number
}

variable "node_min_size" {
  description = "Worker 节点最小数量"
  type        = number
}

variable "node_max_size" {
  description = "Worker 节点最大数量"
  type        = number
}

variable "node_disk_size" {
  description = "Worker 节点磁盘大小 (GB)"
  type        = number
}

variable "kms_key_arn" {
  description = "KMS Key ARN (用于 Secrets 加密)"
  type        = string
}

variable "eks_security_group_id" {
  description = "EKS Worker 安全组 ID"
  type        = string
}

variable "aws_region" {
  description = "AWS 区域"
  type        = string
  default     = "ap-northeast-1"
}

variable "prometheus_workspace_arn" {
  description = "AWS Managed Prometheus Workspace ARN (用于 ADOT Collector)"
  type        = string
  default     = ""
}
