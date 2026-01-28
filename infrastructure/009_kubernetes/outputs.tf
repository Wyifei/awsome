# ==============================================================================
# Kubernetes Resources Outputs
# ==============================================================================

output "aws_lb_controller_release_name" {
  description = "AWS Load Balancer Controller Helm Release 名称"
  value       = helm_release.aws_load_balancer_controller.name
}

output "aws_lb_controller_version" {
  description = "AWS Load Balancer Controller 版本"
  value       = helm_release.aws_load_balancer_controller.version
}

output "nginx_ingress_namespace" {
  description = "NGINX Ingress Controller 命名空间"
  value       = var.enable_nginx_ingress ? kubernetes_namespace.ingress_nginx[0].metadata[0].name : null
}

output "nginx_ingress_release_name" {
  description = "NGINX Ingress Controller Helm Release 名称"
  value       = var.enable_nginx_ingress ? helm_release.nginx_ingress[0].name : null
}

output "nginx_ingress_class_name" {
  description = "NGINX Ingress Class 名称 (用于应用 Ingress 资源)"
  value       = var.enable_nginx_ingress ? "nginx" : null
}

output "alb_ingress_class_name" {
  description = "ALB Ingress Class 名称"
  value       = "alb"
}

output "alb_dns_name" {
  description = "Public ALB DNS 名称 (访问入口) - 仅当 create_alb_ingress=true 时有效"
  value       = var.enable_nginx_ingress && var.create_alb_ingress ? try(data.kubernetes_ingress_v1.alb_ingress[0].status[0].load_balancer[0].ingress[0].hostname, null) : null
}

output "nginx_nodeport_http" {
  description = "NGINX Ingress Controller HTTP NodePort"
  value       = var.enable_nginx_ingress ? 30080 : null
}

output "nginx_nodeport_https" {
  description = "NGINX Ingress Controller HTTPS NodePort"
  value       = var.enable_nginx_ingress ? 30443 : null
}
