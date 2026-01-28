output "cluster_name" {
  description = "EKS 集群名称"
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "EKS 集群端点"
  value       = module.eks.cluster_endpoint
}

output "cluster_certificate_authority_data" {
  description = "EKS 集群 CA 证书"
  value       = module.eks.cluster_certificate_authority_data
}

output "cluster_arn" {
  description = "EKS 集群 ARN"
  value       = module.eks.cluster_arn
}

output "cluster_security_group_id" {
  description = "EKS 集群安全组 ID"
  value       = module.eks.cluster_security_group_id
}

output "node_security_group_id" {
  description = "EKS 节点安全组 ID"
  value       = module.eks.node_security_group_id
}

output "oidc_provider_arn" {
  description = "OIDC Provider ARN (用于 IRSA)"
  value       = module.eks.oidc_provider_arn
}

output "oidc_provider_url" {
  description = "OIDC Provider URL"
  value       = module.eks.cluster_oidc_issuer_url
}

output "aws_lb_controller_role_arn" {
  description = "AWS Load Balancer Controller IAM Role ARN"
  value       = module.aws_lb_controller_irsa_role.iam_role_arn
}

output "app_service_role_arn" {
  description = "Application Service IAM Role ARN"
  value       = module.app_service_irsa_role.iam_role_arn
}

output "alb_dns_name" {
  description = "ALB DNS 名称 (由 AWS Load Balancer Controller 创建)"
  value       = "" # 将由 Ingress 资源创建后填充
}
