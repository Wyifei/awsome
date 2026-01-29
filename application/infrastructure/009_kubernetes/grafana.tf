# ==============================================================================
# Grafana (Self-hosted)
# ==============================================================================

resource "helm_release" "grafana" {
  count = var.enable_grafana ? 1 : 0

  name       = "grafana"
  repository = "https://grafana.github.io/helm-charts"
  chart      = "grafana"
  version    = "10.5.13"
  namespace  = var.enable_adot_collector ? kubernetes_namespace.adot[0].metadata[0].name : kubernetes_namespace.monitoring[0].metadata[0].name

  # 禁用敏感值泄漏检查 (我们使用 IRSA 和 Kubernetes Secrets)
  set {
    name  = "assertNoLeakedSecrets"
    value = "false"
  }

  # Service Account with IRSA
  set {
    name  = "serviceAccount.create"
    value = "true"
  }

  set {
    name  = "serviceAccount.name"
    value = "grafana"
  }

  set {
    name  = "serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn"
    value = var.grafana_role_arn
  }

  # Admin credentials
  set {
    name  = "adminUser"
    value = "admin"
  }

  set_sensitive {
    name  = "adminPassword"
    value = var.grafana_admin_password
  }

  # Service 配置 (NodePort for ALB)
  set {
    name  = "service.type"
    value = "NodePort"
  }

  set {
    name  = "service.nodePort"
    value = "30300"
  }

  # 资源配置
  set {
    name  = "resources.requests.cpu"
    value = "100m"
  }

  set {
    name  = "resources.requests.memory"
    value = "256Mi"
  }

  set {
    name  = "resources.limits.cpu"
    value = "500m"
  }

  set {
    name  = "resources.limits.memory"
    value = "512Mi"
  }

  # 持久化存储
  set {
    name  = "persistence.enabled"
    value = "true"
  }

  set {
    name  = "persistence.size"
    value = "10Gi"
  }

  set {
    name  = "persistence.storageClassName"
    value = "gp3"
  }

  # AWS 区域环境变量 (Amazon Managed Prometheus 插件需要)
  set {
    name  = "env.AWS_REGION"
    value = var.aws_region
  }

  set {
    name  = "env.AWS_DEFAULT_REGION"
    value = var.aws_region
  }

  # Subpath 配置 (通过 /grafana 路径访问)
  set {
    name  = "grafana\\.ini.server.root_url"
    value = var.grafana_root_url
  }

  set {
    name  = "grafana\\.ini.server.serve_from_sub_path"
    value = "true"
  }

  # 数据源和 Dashboard 由用户在 Grafana UI 中手动创建
}

# ------------------------------------------------------------------------------
# Grafana Ingress (通过 NGINX Ingress 访问，路径 /grafana)
# ------------------------------------------------------------------------------

resource "kubernetes_ingress_v1" "grafana" {
  count = var.enable_grafana ? 1 : 0

  metadata {
    name      = "grafana-ingress"
    namespace = var.enable_adot_collector ? kubernetes_namespace.adot[0].metadata[0].name : kubernetes_namespace.monitoring[0].metadata[0].name

    annotations = {
      # NGINX Ingress 配置
      "nginx.ingress.kubernetes.io/proxy-body-size"    = "10m"
      "nginx.ingress.kubernetes.io/proxy-read-timeout" = "120"
      "nginx.ingress.kubernetes.io/proxy-send-timeout" = "120"
      "nginx.ingress.kubernetes.io/proxy-buffer-size"  = "8k"
      # WebSocket 支持 (Grafana Live 功能)
      "nginx.ingress.kubernetes.io/proxy-http-version" = "1.1"
      "nginx.ingress.kubernetes.io/upstream-hash-by"   = "$remote_addr"
    }
  }

  spec {
    ingress_class_name = "nginx"

    rule {
      http {
        path {
          path      = "/grafana"
          path_type = "Prefix"
          backend {
            service {
              name = "grafana"
              port {
                number = 80
              }
            }
          }
        }
      }
    }
  }

  depends_on = [helm_release.grafana]
}
