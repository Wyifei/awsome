# ==============================================================================
# Prometheus Server (Remote Write to AWS Managed Prometheus)
# ==============================================================================
# 注意: 如果微服务需要被自动发现，请确保它们的 Pod 或 Service 带有以下注解:
#   prometheus.io/scrape: "true"
#   prometheus.io/port: "<metrics-port>"
#   prometheus.io/path: "/metrics"

# ------------------------------------------------------------------------------
# Monitoring Namespace
# ------------------------------------------------------------------------------

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

# ------------------------------------------------------------------------------
# Prometheus Server
# ------------------------------------------------------------------------------

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
