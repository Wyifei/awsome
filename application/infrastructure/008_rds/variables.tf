variable "project_name" {
  description = "项目名称"
  type        = string
}

variable "environment" {
  description = "环境名称"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "db_subnet_group_name" {
  description = "数据库子网组名称"
  type        = string
}

variable "aurora_security_group_id" {
  description = "Aurora 安全组 ID"
  type        = string
}

variable "engine_version" {
  description = "Aurora PostgreSQL 引擎版本"
  type        = string
}

variable "instance_class" {
  description = "Aurora 实例类型"
  type        = string
}

variable "database_name" {
  description = "数据库名称"
  type        = string
}

variable "master_username" {
  description = "主用户名"
  type        = string
}

variable "backup_retention_period" {
  description = "备份保留天数"
  type        = number
}

variable "kms_key_arn" {
  description = "KMS Key ARN"
  type        = string
}
