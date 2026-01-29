# ==============================================================================
# Kubernetes Resources
# ==============================================================================
# 架构: Internet → ALB (Public) → NGINX Ingress Controller → Apps
#
# 文件结构:
#   - main.tf              : 本文件，locals 和基础配置
#   - alb-controller.tf    : AWS Load Balancer Controller
#   - nginx-ingress.tf     : NGINX Ingress Controller 和 ALB Ingress
#   - storage.tf           : StorageClass (GP3)
#   - prometheus.tf        : Prometheus Server (Remote Write to AMP)
#   - adot-collector.tf    : ADOT Collector 和相关组件
#   - grafana.tf           : Grafana 和 Ingress
#   - postgres-client.tf   : PostgreSQL Client Pod (调试用)
# ==============================================================================

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}
