# ==============================================================================
# AWS Managed Prometheus
# ==============================================================================
# 架构:
#   - ADOT Collector / Prometheus (EKS) → Remote Write → AWS Managed Prometheus
#   - Self-hosted Grafana (EKS) → Query → AWS Managed Prometheus
# ==============================================================================

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ==============================================================================
# AWS Managed Prometheus Workspace
# ==============================================================================

resource "aws_prometheus_workspace" "main" {
  alias = "${local.name_prefix}-prometheus"

  logging_configuration {
    log_group_arn = "${aws_cloudwatch_log_group.prometheus.arn}:*"
  }

  tags = {
    Name = "${local.name_prefix}-prometheus"
  }
}

resource "aws_cloudwatch_log_group" "prometheus" {
  name              = "/aws/prometheus/${local.name_prefix}"
  retention_in_days = 30

  tags = {
    Name = "${local.name_prefix}-prometheus-logs"
  }
}

# ==============================================================================
# IAM Role for Prometheus Remote Write (from EKS)
# ==============================================================================

resource "aws_iam_role" "prometheus_remote_write" {
  name = "${local.name_prefix}-prometheus-remote-write"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = var.oidc_provider_arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${replace(var.oidc_provider_arn, "/^arn:aws:iam::[0-9]+:oidc-provider\\//", "")}:sub" = "system:serviceaccount:monitoring:prometheus-server"
            "${replace(var.oidc_provider_arn, "/^arn:aws:iam::[0-9]+:oidc-provider\\//", "")}:aud" = "sts.amazonaws.com"
          }
        }
      }
    ]
  })

  tags = {
    Name = "${local.name_prefix}-prometheus-remote-write"
  }
}

resource "aws_iam_role_policy" "prometheus_remote_write" {
  name = "prometheus-remote-write"
  role = aws_iam_role.prometheus_remote_write.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "aps:RemoteWrite",
          "aps:GetSeries",
          "aps:GetLabels",
          "aps:GetMetricMetadata"
        ]
        Resource = aws_prometheus_workspace.main.arn
      }
    ]
  })
}

# ==============================================================================
# IAM Role for Grafana (查询 AWS Managed Prometheus)
# ==============================================================================

resource "aws_iam_role" "grafana" {
  name = "${local.name_prefix}-grafana-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = var.oidc_provider_arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "${replace(var.oidc_provider_arn, "/^arn:aws:iam::[0-9]+:oidc-provider\\//", "")}:sub" = "system:serviceaccount:monitoring:grafana"
            "${replace(var.oidc_provider_arn, "/^arn:aws:iam::[0-9]+:oidc-provider\\//", "")}:aud" = "sts.amazonaws.com"
          }
        }
      }
    ]
  })

  tags = {
    Name = "${local.name_prefix}-grafana-role"
  }
}

resource "aws_iam_role_policy" "grafana_prometheus" {
  name = "grafana-prometheus-access"
  role = aws_iam_role.grafana.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "aps:ListWorkspaces",
          "aps:DescribeWorkspace",
          "aps:QueryMetrics",
          "aps:GetLabels",
          "aps:GetSeries",
          "aps:GetMetricMetadata"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "grafana_cloudwatch" {
  name = "grafana-cloudwatch-access"
  role = aws_iam_role.grafana.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:DescribeAlarmsForMetric",
          "cloudwatch:DescribeAlarmHistory",
          "cloudwatch:DescribeAlarms",
          "cloudwatch:ListMetrics",
          "cloudwatch:GetMetricData",
          "cloudwatch:GetInsightRuleReport"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:DescribeLogGroups",
          "logs:GetLogGroupFields",
          "logs:StartQuery",
          "logs:StopQuery",
          "logs:GetQueryResults",
          "logs:GetLogEvents"
        ]
        Resource = "*"
      }
    ]
  })
}
