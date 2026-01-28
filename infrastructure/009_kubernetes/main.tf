# ==============================================================================
# Kubernetes Resources (AWS Load Balancer Controller & NGINX Ingress)
# ==============================================================================
# 架构: Internet → ALB (Public) → NGINX Ingress Controller → Apps
# ==============================================================================

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

# ==============================================================================
# AWS Load Balancer Controller
# ==============================================================================
# 用于创建和管理 AWS ALB/NLB，支持 Kubernetes Ingress 和 Service

resource "helm_release" "aws_load_balancer_controller" {
  name       = "aws-load-balancer-controller"
  repository = "https://aws.github.io/eks-charts"
  chart      = "aws-load-balancer-controller"
  version    = var.aws_lb_controller_version
  namespace  = "kube-system"

  set {
    name  = "clusterName"
    value = var.cluster_name
  }

  set {
    name  = "serviceAccount.create"
    value = "true"
  }

  set {
    name  = "serviceAccount.name"
    value = "aws-load-balancer-controller"
  }

  set {
    name  = "serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn"
    value = var.aws_lb_controller_role_arn
  }

  set {
    name  = "region"
    value = var.aws_region
  }

  set {
    name  = "vpcId"
    value = var.vpc_id
  }

  # 高可用配置
  set {
    name  = "replicaCount"
    value = "2"
  }

  # 资源限制
  set {
    name  = "resources.requests.cpu"
    value = "100m"
  }

  set {
    name  = "resources.requests.memory"
    value = "128Mi"
  }

  set {
    name  = "resources.limits.cpu"
    value = "200m"
  }

  set {
    name  = "resources.limits.memory"
    value = "256Mi"
  }

  set {
    name  = "podDisruptionBudget.minAvailable"
    value = "1"
  }

  # 启用 WAFv2 集成
  set {
    name  = "enableShield"
    value = "false"
  }

  set {
    name  = "enableWaf"
    value = "false"
  }

  set {
    name  = "enableWafv2"
    value = "true"
  }
}

# ==============================================================================
# NGINX Ingress Controller Namespace
# ==============================================================================

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

# ==============================================================================
# NGINX Ingress Controller (内部服务，通过 ALB 访问)
# ==============================================================================
# NGINX Ingress 作为 ClusterIP 服务，前端通过 ALB Ingress 暴露

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

# ==============================================================================
# ALB Ingress - 对外暴露 NGINX Ingress Controller (可选)
# ==============================================================================
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

# ==============================================================================
# 获取 ALB DNS 名称 (仅当通过 Terraform 创建 ALB Ingress 时)
# ==============================================================================

data "kubernetes_ingress_v1" "alb_ingress" {
  count = var.enable_nginx_ingress && var.create_alb_ingress ? 1 : 0

  metadata {
    name      = kubernetes_ingress_v1.alb_to_nginx[0].metadata[0].name
    namespace = kubernetes_namespace.ingress_nginx[0].metadata[0].name
  }

  depends_on = [kubernetes_ingress_v1.alb_to_nginx]
}

# ==============================================================================
# GP3 StorageClass (默认存储类)
# ==============================================================================

resource "kubernetes_storage_class" "gp3" {
  metadata {
    name = "gp3"

    annotations = {
      "storageclass.kubernetes.io/is-default-class" = "true"
    }
  }

  storage_provisioner    = "ebs.csi.aws.com"
  reclaim_policy         = "Delete"
  volume_binding_mode    = "WaitForFirstConsumer"
  allow_volume_expansion = true

  parameters = {
    type      = "gp3"
    fsType    = "ext4"
    encrypted = "true"
  }
}

# ==============================================================================
# Prometheus Namespace
# ==============================================================================

resource "kubernetes_namespace" "monitoring" {
  count = var.enable_prometheus ? 1 : 0

  metadata {
    name = "monitoring"

    labels = {
      "app.kubernetes.io/name"       = "monitoring"
      "app.kubernetes.io/managed-by" = "terraform"
    }
  }
}

# ==============================================================================
# Prometheus Server (Remote Write to AWS Managed Prometheus)
# ==============================================================================

resource "helm_release" "prometheus" {
  count = var.enable_prometheus ? 1 : 0

  name       = "prometheus"
  repository = "https://prometheus-community.github.io/helm-charts"
  chart      = "prometheus"
  version    = "25.11.0"
  namespace  = kubernetes_namespace.monitoring[0].metadata[0].name

  # 禁用不需要的组件 (使用 AWS Managed Prometheus 存储)
  set {
    name  = "alertmanager.enabled"
    value = "false"
  }

  set {
    name  = "prometheus-pushgateway.enabled"
    value = "false"
  }

  # Prometheus Server 配置
  set {
    name  = "server.persistentVolume.enabled"
    value = "false"
  }

  set {
    name  = "server.replicaCount"
    value = "1"
  }

  set {
    name  = "server.resources.requests.cpu"
    value = "200m"
  }

  set {
    name  = "server.resources.requests.memory"
    value = "512Mi"
  }

  set {
    name  = "server.resources.limits.cpu"
    value = "500m"
  }

  set {
    name  = "server.resources.limits.memory"
    value = "1Gi"
  }

  # Service Account for IRSA
  set {
    name  = "server.serviceAccount.create"
    value = "true"
  }

  set {
    name  = "server.serviceAccount.name"
    value = "prometheus-server"
  }

  set {
    name  = "server.serviceAccount.annotations.eks\\.amazonaws\\.com/role-arn"
    value = var.prometheus_remote_write_role_arn
  }

  # Remote Write to AWS Managed Prometheus
  set {
    name  = "server.remoteWrite[0].url"
    value = var.prometheus_remote_write_url
  }

  set {
    name  = "server.remoteWrite[0].sigv4.region"
    value = var.aws_region
  }

  set {
    name  = "server.remoteWrite[0].queue_config.max_samples_per_send"
    value = "1000"
  }

  set {
    name  = "server.remoteWrite[0].queue_config.max_shards"
    value = "200"
  }

  set {
    name  = "server.remoteWrite[0].queue_config.capacity"
    value = "2500"
  }

  # 数据保留 (本地只保留少量数据，主要依靠远程存储)
  set {
    name  = "server.retention"
    value = "2h"
  }

  # 全局 scrape 配置
  set {
    name  = "server.global.scrape_interval"
    value = "30s"
  }

  set {
    name  = "server.global.evaluation_interval"
    value = "30s"
  }

  # kube-state-metrics 配置
  set {
    name  = "kube-state-metrics.enabled"
    value = "true"
  }

  # prometheus-node-exporter 配置
  set {
    name  = "prometheus-node-exporter.enabled"
    value = "true"
  }

  set {
    name  = "prometheus-node-exporter.tolerations[0].operator"
    value = "Exists"
  }

  depends_on = [helm_release.aws_load_balancer_controller]
}

# ==============================================================================
# ServiceMonitor CRDs (如果需要使用 Prometheus Operator 风格的配置)
# ==============================================================================
# 注意: 如果微服务需要被自动发现，请确保它们的 Pod 或 Service 带有以下注解:
#   prometheus.io/scrape: "true"
#   prometheus.io/port: "<metrics-port>"
#   prometheus.io/path: "/metrics"

# ==============================================================================
# ADOT Collector (AWS Distro for OpenTelemetry)
# ==============================================================================
# 使用 ADOT Collector 替代 Prometheus Server 抓取指标并发送到 AWS Managed Prometheus
# ADOT addon 需要在 EKS 模块中安装

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

# ADOT Collector ClusterRole
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

# ADOT Collector ConfigMap
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
      }
      receivers = {
        prometheus = {
          config = {
            global = {
              scrape_interval     = "30s"
              evaluation_interval = "30s"
            }
            scrape_configs = [
              # 抓取带有 prometheus.io 注解的 Pods
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
                  # 使用 prometheus.io/scheme 注解配置 scheme
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
          timeout       = "30s"
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
        extensions = ["sigv4auth"]
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

# ADOT Collector Deployment
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

# ==============================================================================
# Grafana (Self-hosted with Cognito OAuth)
# ==============================================================================

resource "helm_release" "grafana" {
  count = var.enable_grafana ? 1 : 0

  name       = "grafana"
  repository = "https://grafana.github.io/helm-charts"
  chart      = "grafana"
  version    = "8.8.2"
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

  # Subpath 配置 (通过 /grafana 路径访问)
  set {
    name  = "grafana\\.ini.server.root_url"
    value = var.grafana_root_url
  }

  set {
    name  = "grafana\\.ini.server.serve_from_sub_path"
    value = "true"
  }

  # AWS Managed Prometheus 数据源
  set {
    name  = "datasources.datasources\\.yaml.apiVersion"
    value = "1"
  }

  set {
    name  = "datasources.datasources\\.yaml.datasources[0].name"
    value = "Amazon Managed Prometheus"
  }

  set {
    name  = "datasources.datasources\\.yaml.datasources[0].type"
    value = "prometheus"
  }

  set {
    name  = "datasources.datasources\\.yaml.datasources[0].url"
    value = var.prometheus_query_url
  }

  set {
    name  = "datasources.datasources\\.yaml.datasources[0].access"
    value = "proxy"
  }

  set {
    name  = "datasources.datasources\\.yaml.datasources[0].isDefault"
    value = "true"
  }

  set {
    name  = "datasources.datasources\\.yaml.datasources[0].jsonData.sigV4Auth"
    value = "true"
  }

  set {
    name  = "datasources.datasources\\.yaml.datasources[0].jsonData.sigV4AuthType"
    value = "default"
  }

  set {
    name  = "datasources.datasources\\.yaml.datasources[0].jsonData.sigV4Region"
    value = var.aws_region
  }

  # 预装 Dashboard
  set {
    name  = "dashboardProviders.dashboardproviders\\.yaml.apiVersion"
    value = "1"
  }

  set {
    name  = "dashboardProviders.dashboardproviders\\.yaml.providers[0].name"
    value = "default"
  }

  set {
    name  = "dashboardProviders.dashboardproviders\\.yaml.providers[0].orgId"
    value = "1"
  }

  set {
    name  = "dashboardProviders.dashboardproviders\\.yaml.providers[0].folder"
    value = ""
  }

  set {
    name  = "dashboardProviders.dashboardproviders\\.yaml.providers[0].type"
    value = "file"
  }

  set {
    name  = "dashboardProviders.dashboardproviders\\.yaml.providers[0].disableDeletion"
    value = "false"
  }

  set {
    name  = "dashboardProviders.dashboardproviders\\.yaml.providers[0].editable"
    value = "true"
  }

  set {
    name  = "dashboardProviders.dashboardproviders\\.yaml.providers[0].options.path"
    value = "/var/lib/grafana/dashboards/default"
  }

  # Kubernetes Cluster Dashboard
  set {
    name  = "dashboards.default.kubernetes-cluster.gnetId"
    value = "7249"
  }

  set {
    name  = "dashboards.default.kubernetes-cluster.revision"
    value = "1"
  }

  set {
    name  = "dashboards.default.kubernetes-cluster.datasource"
    value = "Amazon Managed Prometheus"
  }

  # Node Exporter Dashboard
  set {
    name  = "dashboards.default.node-exporter.gnetId"
    value = "1860"
  }

  set {
    name  = "dashboards.default.node-exporter.revision"
    value = "37"
  }

  set {
    name  = "dashboards.default.node-exporter.datasource"
    value = "Amazon Managed Prometheus"
  }
}

# ==============================================================================
# Grafana Ingress (通过 NGINX Ingress 访问，路径 /grafana)
# ==============================================================================

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

