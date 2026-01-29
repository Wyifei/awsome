variable "project_name" {
  description = "项目名称"
  type        = string
}

variable "environment" {
  description = "环境名称"
  type        = string
}

variable "rate_limit" {
  description = "速率限制 (每 5 分钟)"
  type        = number
  default     = 2000
}

variable "cognito_rate_limit" {
  description = "Cognito Token 端点速率限制 (每 5 分钟)"
  type        = number
  default     = 100
}
