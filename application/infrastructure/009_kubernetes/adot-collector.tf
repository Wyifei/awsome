# ==============================================================================
# ADOT Collector (AWS Distro for OpenTelemetry)
# ==============================================================================
# 使用 ADOT Collector 替代 Prometheus Server 抓取指标并发送到 AWS Managed Prometheus
# ADOT addon 需要在 EKS 模块中安装

# ------------------------------------------------------------------------------
# Namespace (如果 ADOT 启用但 Prometheus 未启用)
# ------------------------------------------------------------------------------

resource "kubernetes_namespace" "adot" {
  count = var.enable_adot_collector ? 1 : 0

  metadata {
    name = "monitoring"

    labels = {
      "app.kubernetes.io/name"       = "adot-collector"
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }
}

# ------------------------------------------------------------------------------
# Service Account
# ------------------------------------------------------------------------------

resource "kubernetes_service_account" "adot_collector" {
  count = var.enable_adot_collector ? 1 : 0

  metadata {
    name      = "adot-collector"
    namespace = kubernetes_namespace.adot[0].metadata[0].name

    annotations = {
      "eks.amazonaws.com/role-arn" = var.adot_collector_role_arn
    }

    labels = {
      "app.kubernetes.io/name"       = "adot-collector"
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }
}

# ------------------------------------------------------------------------------
# RBAC
# ------------------------------------------------------------------------------

resource "kubernetes_cluster_role" "adot_collector" {
  count = var.enable_adot_collector ? 1 : 0

  metadata {
    name = "adot-collector"
  }

  rule {
    api_groups = [""]
    resources  = ["nodes", "nodes/proxy", "nodes/metrics", "services", "endpoints", "pods"]
    verbs      = ["get", "list", "watch"]
  }

  rule {
    api_groups = ["extensions", "networking.k8s.io"]
    resources  = ["ingresses"]
    verbs      = ["get", "list", "watch"]
  }

  rule {
    non_resource_urls = ["/metrics", "/metrics/cadvisor"]
    verbs             = ["get"]
  }
}

resource "kubernetes_cluster_role_binding" "adot_collector" {
  count = var.enable_adot_collector ? 1 : 0

  metadata {
    name = "adot-collector"
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "ClusterRole"
    name      = kubernetes_cluster_role.adot_collector[0].metadata[0].name
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.adot_collector[0].metadata[0].name
    namespace = kubernetes_namespace.adot[0].metadata[0].name
  }
}

# ------------------------------------------------------------------------------
# ConfigMap
# ------------------------------------------------------------------------------

resource "kubernetes_config_map" "adot_collector" {
  count = var.enable_adot_collector ? 1 : 0

  metadata {
    name      = "adot-collector-config"
    namespace = kubernetes_namespace.adot[0].metadata[0].name
  }

  data = {
    "collector.yaml" = yamlencode({
      extensions = {
        sigv4auth = {
          region  = var.aws_region
          service = "aps"
        }
        health_check = {
          endpoint = "0.0.0.0:13133"
        }
      }
      receivers = {
        prometheus = {
          config = {
            global = {
              scrape_interval     = "30s"
              evaluation_interval = "30s"
            }
            scrape_configs = [
              # 抓取带有 prometheus.io 注解的 Pods (仅 HTTP 端点)
              {
                job_name = "kubernetes-pods"
                kubernetes_sd_configs = [
                  {
                    role = "pod"
                  }
                ]
                relabel_configs = [
                  # 只抓取带有 prometheus.io/scrape: "true" 注解的 pod
                  {
                    source_labels = ["__meta_kubernetes_pod_annotation_prometheus_io_scrape"]
                    action        = "keep"
                    regex         = "true"
                  },
                  # 排除 kube-system 命名空间 (避免 HTTPS 端点问题)
                  {
                    source_labels = ["__meta_kubernetes_namespace"]
                    action        = "drop"
                    regex         = "kube-system"
                  },
                  # 使用 prometheus.io/port 注解配置端口
                  {
                    source_labels = ["__address__", "__meta_kubernetes_pod_annotation_prometheus_io_port"]
                    action        = "replace"
                    regex         = "([^:]+)(?::\\d+)?;(\\d+)"
                    replacement   = "$$1:$$2"
                    target_label  = "__address__"
                  },
                  # 使用 prometheus.io/scheme 注解配置 scheme (默认 http)
                  {
                    source_labels = ["__meta_kubernetes_pod_annotation_prometheus_io_scheme"]
                    action        = "replace"
                    target_label  = "__scheme__"
                    regex         = "(https?)"
                  },
                  # 使用 prometheus.io/path 注解配置路径
                  {
                    source_labels = ["__meta_kubernetes_pod_annotation_prometheus_io_path"]
                    action        = "replace"
                    target_label  = "__metrics_path__"
                    regex         = "(.+)"
                  },
                  # 添加 kubernetes labels
                  {
                    action = "labelmap"
                    regex  = "__meta_kubernetes_pod_label_(.+)"
                  },
                  {
                    source_labels = ["__meta_kubernetes_namespace"]
                    action        = "replace"
                    target_label  = "namespace"
                  },
                  {
                    source_labels = ["__meta_kubernetes_pod_name"]
                    action        = "replace"
                    target_label  = "pod"
                  },
                  {
                    source_labels = ["__meta_kubernetes_pod_container_name"]
                    action        = "replace"
                    target_label  = "container"
                  }
                ]
              },
              # 抓取 kube-state-metrics (如果已部署)
              {
                job_name = "kube-state-metrics"
                kubernetes_sd_configs = [
                  {
                    role = "service"
                  }
                ]
                relabel_configs = [
                  {
                    source_labels = ["__meta_kubernetes_service_label_app_kubernetes_io_name"]
                    action        = "keep"
                    regex         = "kube-state-metrics"
                  }
                ]
              },
              # 抓取 Node Exporter
              {
                job_name = "node-exporter"
                kubernetes_sd_configs = [
                  {
                    role = "endpoints"
                  }
                ]
                relabel_configs = [
                  {
                    source_labels = ["__meta_kubernetes_endpoints_name"]
                    action        = "keep"
                    regex         = ".*node-exporter.*"
                  }
                ]
              }
            ]
          }
        }
      }
      processors = {
        batch = {
          timeout         = "30s"
          send_batch_size = 1000
        }
      }
      exporters = {
        prometheusremotewrite = {
          endpoint = var.prometheus_remote_write_url
          auth = {
            authenticator = "sigv4auth"
          }
        }
      }
      service = {
        extensions = ["sigv4auth", "health_check"]
        pipelines = {
          metrics = {
            receivers  = ["prometheus"]
            processors = ["batch"]
            exporters  = ["prometheusremotewrite"]
          }
        }
      }
    })
  }
}

# ------------------------------------------------------------------------------
# Deployment
# ------------------------------------------------------------------------------

resource "kubernetes_deployment" "adot_collector" {
  count = var.enable_adot_collector ? 1 : 0

  metadata {
    name      = "adot-collector"
    namespace = kubernetes_namespace.adot[0].metadata[0].name

    labels = {
      "app.kubernetes.io/name"       = "adot-collector"
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        "app.kubernetes.io/name" = "adot-collector"
      }
    }

    template {
      metadata {
        labels = {
          "app.kubernetes.io/name" = "adot-collector"
        }
      }

      spec {
        service_account_name = kubernetes_service_account.adot_collector[0].metadata[0].name

        container {
          name  = "adot-collector"
          image = "public.ecr.aws/aws-observability/aws-otel-collector:v0.40.0"

          args = ["--config=/etc/otel/collector.yaml"]

          port {
            container_port = 4317
            protocol       = "TCP"
          }

          port {
            container_port = 4318
            protocol       = "TCP"
          }

          resources {
            requests = {
              cpu    = "200m"
              memory = "256Mi"
            }
            limits = {
              cpu    = "500m"
              memory = "512Mi"
            }
          }

          volume_mount {
            name       = "config"
            mount_path = "/etc/otel"
          }

          liveness_probe {
            http_get {
              path = "/"
              port = 13133
            }
            initial_delay_seconds = 30
            period_seconds        = 10
          }

          readiness_probe {
            http_get {
              path = "/"
              port = 13133
            }
            initial_delay_seconds = 10
            period_seconds        = 5
          }
        }

        volume {
          name = "config"
          config_map {
            name = kubernetes_config_map.adot_collector[0].metadata[0].name
          }
        }
      }
    }
  }

  depends_on = [
    kubernetes_service_account.adot_collector,
    kubernetes_config_map.adot_collector
  ]
}

# ------------------------------------------------------------------------------
# Kube State Metrics (提供 Kubernetes 集群状态指标)
# ------------------------------------------------------------------------------

resource "helm_release" "kube_state_metrics" {
  count = var.enable_adot_collector ? 1 : 0

  name       = "kube-state-metrics"
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "kube-state-metrics"
  version    = "5.27.0"
  namespace  = kubernetes_namespace.adot[0].metadata[0].name

  # Prometheus 抓取注解
  set {
    name  = "podAnnotations.prometheus\\.io/scrape"
    value = "true"
  }

  set {
    name  = "podAnnotations.prometheus\\.io/port"
    value = "8080"
  }

  set {
    name  = "podAnnotations.prometheus\\.io/path"
    value = "/metrics"
  }

  # 资源限制
  set {
    name  = "resources.requests.cpu"
    value = "50m"
  }

  set {
    name  = "resources.requests.memory"
    value = "64Mi"
  }

  set {
    name  = "resources.limits.cpu"
    value = "100m"
  }

  set {
    name  = "resources.limits.memory"
    value = "128Mi"
  }

  depends_on = [kubernetes_namespace.adot]
}

# ------------------------------------------------------------------------------
# Prometheus Node Exporter (提供节点级别系统指标)
# ------------------------------------------------------------------------------

resource "helm_release" "prometheus_node_exporter" {
  count = var.enable_adot_collector ? 1 : 0

  name       = "prometheus-node-exporter"
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "prometheus-node-exporter"
  version    = "4.43.1"
  namespace  = kubernetes_namespace.adot[0].metadata[0].name

  # Prometheus 抓取注解
  set {
    name  = "podAnnotations.prometheus\\.io/scrape"
    value = "true"
  }

  set {
    name  = "podAnnotations.prometheus\\.io/port"
    value = "9100"
  }

  set {
    name  = "podAnnotations.prometheus\\.io/path"
    value = "/metrics"
  }

  # 允许在所有节点上运行
  set {
    name  = "tolerations[0].operator"
    value = "Exists"
  }

  # 资源限制
  set {
    name  = "resources.requests.cpu"
    value = "50m"
  }

  set {
    name  = "resources.requests.memory"
    value = "32Mi"
  }

  set {
    name  = "resources.limits.cpu"
    value = "100m"
  }

  set {
    name  = "resources.limits.memory"
    value = "64Mi"
  }

  depends_on = [kubernetes_namespace.adot]
}
