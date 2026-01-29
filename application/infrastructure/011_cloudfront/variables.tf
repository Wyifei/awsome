variable "project_name" {
  description = "项目名称"
  type        = string
}

variable "environment" {
  description = "环境名称"
  type        = string
}

variable "s3_bucket_id" {
  description = "S3 存储桶 ID"
  type        = string
}

variable "s3_bucket_domain_name" {
  description = "S3 存储桶区域域名"
  type        = string
}

variable "alb_dns_name" {
  description = "ALB DNS 名称"
  type        = string
  default     = ""
}

variable "waf_web_acl_arn" {
  description = "WAF Web ACL ARN"
  type        = string
}
