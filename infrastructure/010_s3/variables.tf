variable "project_name" {
  description = "项目名称"
  type        = string
}

variable "environment" {
  description = "环境名称"
  type        = string
}

variable "kms_key_arn" {
  description = "KMS Key ARN"
  type        = string
}
