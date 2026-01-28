# ==============================================================================
# 输出值
# ==============================================================================

# ------------------------------------------------------------------------------
# VPC
# ------------------------------------------------------------------------------

output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "私有子网 ID 列表"
  value       = module.vpc.private_subnet_ids
}

output "database_subnet_ids" {
  description = "数据库子网 ID 列表"
  value       = module.vpc.database_subnet_ids
}

# ------------------------------------------------------------------------------
# EKS
# ------------------------------------------------------------------------------

output "eks_cluster_name" {
  description = "EKS 集群名称"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "EKS 集群端点"
  value       = module.eks.cluster_endpoint
}

output "eks_update_kubeconfig_command" {
  description = "更新 kubeconfig 命令"
  value       = "aws eks update-kubeconfig --name ${module.eks.cluster_name} --region ${var.aws_region}"
}

# ------------------------------------------------------------------------------
# Aurora
# ------------------------------------------------------------------------------

output "aurora_cluster_endpoint" {
  description = "Aurora 集群写入端点"
  value       = module.rds.cluster_endpoint
}

output "aurora_cluster_reader_endpoint" {
  description = "Aurora 集群只读端点"
  value       = module.rds.cluster_reader_endpoint
}

output "aurora_secret_arn" {
  description = "Aurora 凭证 Secret ARN"
  value       = module.rds.secret_arn
}

# ------------------------------------------------------------------------------
# Cognito
# ------------------------------------------------------------------------------

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = module.cognito.user_pool_id
}

output "cognito_user_pool_client_id" {
  description = "Cognito User Pool Client ID"
  value       = module.cognito.user_pool_client_id
}

output "cognito_domain" {
  description = "Cognito 域名 (默认 Amazon Cognito 域名)"
  value       = module.cognito.cognito_hosted_ui_url
}

output "cognito_oauth_authorize_url" {
  description = "Cognito OAuth 授权 URL"
  value       = module.cognito.oauth_authorize_url
}

# ------------------------------------------------------------------------------
# CloudFront
# ------------------------------------------------------------------------------

output "cloudfront_distribution_id" {
  description = "CloudFront Distribution ID"
  value       = module.cloudfront.distribution_id
}

output "cloudfront_domain_name" {
  description = "CloudFront Domain Name (访问前端应用的域名)"
  value       = module.cloudfront.distribution_domain_name
}

# ------------------------------------------------------------------------------
# S3
# ------------------------------------------------------------------------------

output "s3_frontend_bucket" {
  description = "Frontend S3 存储桶名称"
  value       = module.s3.frontend_bucket_id
}

output "s3_avatars_bucket" {
  description = "Avatars S3 存储桶名称"
  value       = module.s3.avatars_bucket_id
}

# ------------------------------------------------------------------------------
# IAM Roles (IRSA)
# ------------------------------------------------------------------------------

output "app_service_role_arn" {
  description = "Application Service IAM Role ARN (用于 IRSA)"
  value       = module.eks.app_service_role_arn
}

output "aws_lb_controller_role_arn" {
  description = "AWS Load Balancer Controller IAM Role ARN"
  value       = module.eks.aws_lb_controller_role_arn
}

# ------------------------------------------------------------------------------
# ECR
# ------------------------------------------------------------------------------

output "ecr_repository_urls" {
  description = "ECR Repository URLs"
  value       = module.ecr.repository_urls
}

output "ecr_user_service_url" {
  description = "User Service ECR URL"
  value       = module.ecr.user_service_url
}

output "ecr_profile_service_url" {
  description = "Profile Service ECR URL"
  value       = module.ecr.profile_service_url
}

output "ecr_notification_service_url" {
  description = "Notification Service ECR URL"
  value       = module.ecr.notification_service_url
}

# ------------------------------------------------------------------------------
# Kubernetes / Ingress
# ------------------------------------------------------------------------------

output "alb_dns_name" {
  description = "Public ALB DNS 名称 (访问入口)"
  value       = module.kubernetes.alb_dns_name
}

output "nginx_ingress_class_name" {
  description = "NGINX Ingress Class 名称 (用于应用 Ingress 资源)"
  value       = module.kubernetes.nginx_ingress_class_name
}

output "alb_ingress_class_name" {
  description = "ALB Ingress Class 名称"
  value       = module.kubernetes.alb_ingress_class_name
}
