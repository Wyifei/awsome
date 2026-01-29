# ==============================================================================
# NGINX Ingress Controller
# ==============================================================================
# NGINX Ingress 作为 ClusterIP 服务，前端通过 ALB Ingress 暴露

# ------------------------------------------------------------------------------
# Namespace
# ------------------------------------------------------------------------------

resource "kubernetes_namespace" "ingress_nginx" {
  count = var.enable_nginx_ingress ? 1 : 0

  metadata {
    name = "ingress-nginx"

    labels = {
      "app.kubernetes.io/name"       = "ingress-nginx"
      "app.kubernetes.io/instance"   = "ingress-nginx"
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }
}

# ------------------------------------------------------------------------------
# NGINX Ingress Controller (内部服务，通过 ALB 访问)
# ------------------------------------------------------------------------------

resource "helm_release" "nginx_ingress" {
  count = var.enable_nginx_ingress ? 1 : 0

  name       = "ingress-nginx"
  repository = "https://kubernetes.github.io/ingress-nginx"
  chart      = "ingress-nginx"
  version    = var.nginx_ingress_version
  namespace  = kubernetes_namespace.ingress_nginx[0].metadata[0].name

  # 副本数
  set {
    name  = "controller.replicaCount"
    value = var.nginx_ingress_replica_count
  }

  # 使用 NodePort 服务类型，供 ALB Target Group 使用
  set {
    name  = "controller.service.type"
    value = "NodePort"
  }

  # 固定 NodePort 端口 (HTTP)
  set {
    name  = "controller.service.nodePorts.http"
    value = "30080"
  }

  # 固定 NodePort 端口 (HTTPS)
  set {
    name  = "controller.service.nodePorts.https"
    value = "30443"
  }

  # 启用健康检查端口并暴露为 NodePort
  set {
    name  = "controller.healthCheckPath"
    value = "/healthz"
  }

  # Ingress Class 配置
  set {
    name  = "controller.ingressClassResource.name"
    value = "nginx"
  }

  set {
    name  = "controller.ingressClassResource.enabled"
    value = "true"
  }

  set {
    name  = "controller.ingressClassResource.default"
    value = "false"
  }

  set {
    name  = "controller.ingressClass"
    value = "nginx"
  }

  # 资源配置
  set {
    name  = "controller.resources.requests.cpu"
    value = "100m"
  }

  set {
    name  = "controller.resources.requests.memory"
    value = "128Mi"
  }

  set {
    name  = "controller.resources.limits.cpu"
    value = "500m"
  }

  set {
    name  = "controller.resources.limits.memory"
    value = "512Mi"
  }

  # 启用 Prometheus 指标
  set {
    name  = "controller.metrics.enabled"
    value = "true"
  }

  set {
    name  = "controller.metrics.serviceMonitor.enabled"
    value = "false"
  }

  # Pod 反亲和性 - 确保分布在不同节点
  set {
    name  = "controller.affinity.podAntiAffinity.preferredDuringSchedulingIgnoredDuringExecution[0].weight"
    value = "100"
  }

  set {
    name  = "controller.affinity.podAntiAffinity.preferredDuringSchedulingIgnoredDuringExecution[0].podAffinityTerm.labelSelector.matchExpressions[0].key"
    value = "app.kubernetes.io/name"
  }

  set {
    name  = "controller.affinity.podAntiAffinity.preferredDuringSchedulingIgnoredDuringExecution[0].podAffinityTerm.labelSelector.matchExpressions[0].operator"
    value = "In"
  }

  set {
    name  = "controller.affinity.podAntiAffinity.preferredDuringSchedulingIgnoredDuringExecution[0].podAffinityTerm.labelSelector.matchExpressions[0].values[0]"
    value = "ingress-nginx"
  }

  set {
    name  = "controller.affinity.podAntiAffinity.preferredDuringSchedulingIgnoredDuringExecution[0].podAffinityTerm.topologyKey"
    value = "kubernetes.io/hostname"
  }

  # 配置 ConfigMap - 处理来自 ALB 的流量
  set {
    name  = "controller.config.use-forwarded-headers"
    value = "true"
  }

  set {
    name  = "controller.config.compute-full-forwarded-for"
    value = "true"
  }

  set {
    name  = "controller.config.use-proxy-protocol"
    value = "false"
  }

  # 真实客户端 IP (来自 ALB X-Forwarded-For)
  set {
    name  = "controller.config.forwarded-for-header"
    value = "X-Forwarded-For"
  }

  # 日志格式
  set {
    name  = "controller.config.log-format-upstream"
    value = "$remote_addr - $request_id [$time_local] $request $status $body_bytes_sent $request_time $upstream_response_time $proxy_host $upstream_addr"
  }

  # 安全配置
  set {
    name  = "controller.config.ssl-protocols"
    value = "TLSv1.2 TLSv1.3"
  }

  set {
    name  = "controller.config.ssl-ciphers"
    value = "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384"
  }

  # 默认后端 - 使用 ARM64 兼容镜像
  set {
    name  = "defaultBackend.enabled"
    value = "true"
  }

  set {
    name  = "defaultBackend.replicaCount"
    value = "1"
  }

  # 使用 ARM64 兼容的 defaultBackend 镜像
  set {
    name  = "defaultBackend.image.registry"
    value = "registry.k8s.io"
  }

  set {
    name  = "defaultBackend.image.image"
    value = "defaultbackend-arm64"
  }

  set {
    name  = "defaultBackend.image.tag"
    value = "1.5"
  }

  depends_on = [helm_release.aws_load_balancer_controller]
}

# ------------------------------------------------------------------------------
# ALB Ingress - 对外暴露 NGINX Ingress Controller (可选)
# ------------------------------------------------------------------------------
# 使用 ALB Ingress Class 创建 Public ALB，将流量路由到 NGINX Ingress
# 如果 create_alb_ingress = false，请使用 kubectl apply -f manifests/alb-ingress.yaml

resource "kubernetes_ingress_v1" "alb_to_nginx" {
  count = var.enable_nginx_ingress && var.create_alb_ingress ? 1 : 0

  metadata {
    name      = "alb-ingress"
    namespace = kubernetes_namespace.ingress_nginx[0].metadata[0].name

    annotations = {
      # 使用 ALB Ingress Class
      "kubernetes.io/ingress.class" = "alb"

      # ALB 配置 - instance 类型，流量发送到 EC2 节点的 NodePort
      "alb.ingress.kubernetes.io/scheme"      = "internet-facing"
      "alb.ingress.kubernetes.io/target-type" = "instance"

      # 监听 HTTP 80 端口 (HTTPS 由 CloudFront 处理)
      "alb.ingress.kubernetes.io/listen-ports" = jsonencode([
        { HTTP = 80 }
      ])

      # 后端协议
      "alb.ingress.kubernetes.io/backend-protocol" = "HTTP"

      # 健康检查配置 - 使用 NodePort 30080
      "alb.ingress.kubernetes.io/healthcheck-path"             = "/"
      "alb.ingress.kubernetes.io/healthcheck-port"             = "traffic-port"
      "alb.ingress.kubernetes.io/healthcheck-protocol"         = "HTTP"
      "alb.ingress.kubernetes.io/healthcheck-interval-seconds" = "15"
      "alb.ingress.kubernetes.io/healthcheck-timeout-seconds"  = "5"
      "alb.ingress.kubernetes.io/healthy-threshold-count"      = "2"
      "alb.ingress.kubernetes.io/unhealthy-threshold-count"    = "2"
      "alb.ingress.kubernetes.io/success-codes"                = "200,404"

      # 目标组配置
      "alb.ingress.kubernetes.io/target-group-attributes" = "deregistration_delay.timeout_seconds=30"

      # 负载均衡属性
      "alb.ingress.kubernetes.io/load-balancer-attributes" = "idle_timeout.timeout_seconds=60"

      # 标签
      "alb.ingress.kubernetes.io/tags" = "Environment=${var.environment},Project=${var.project_name},ManagedBy=terraform"
    }
  }

  spec {
    ingress_class_name = "alb"

    # 所有路径路由到 NGINX Ingress Controller (使用 NodePort 30080)
    rule {
      http {
        path {
          path      = "/"
          path_type = "Prefix"
          backend {
            service {
              name = "ingress-nginx-controller"
              port {
                number = 80
              }
            }
          }
        }
      }
    }
  }

  depends_on = [helm_release.nginx_ingress]
}

# ------------------------------------------------------------------------------
# 获取 ALB DNS 名称 (仅当通过 Terraform 创建 ALB Ingress 时)
# ------------------------------------------------------------------------------

data "kubernetes_ingress_v1" "alb_ingress" {
  count = var.enable_nginx_ingress && var.create_alb_ingress ? 1 : 0

  metadata {
    name      = kubernetes_ingress_v1.alb_to_nginx[0].metadata[0].name
    namespace = kubernetes_namespace.ingress_nginx[0].metadata[0].name
  }

  depends_on = [kubernetes_ingress_v1.alb_to_nginx]
}
