variable "project_name" {
  description = "项目名称"
  type        = string
}

variable "environment" {
  description = "环境名称"
  type        = string
}

variable "user_pool_name" {
  description = "Cognito User Pool 名称"
  type        = string
}

variable "callback_urls" {
  description = "OAuth 回调 URL 列表"
  type        = list(string)
}

variable "logout_urls" {
  description = "OAuth 登出 URL 列表"
  type        = list(string)
}

variable "ses_email_address" {
  description = "SES 发送邮件地址"
  type        = string
}
