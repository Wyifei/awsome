# ==============================================================================
# Outputs for Monitoring Module
# ==============================================================================

# ------------------------------------------------------------------------------
# AWS Managed Prometheus
# ------------------------------------------------------------------------------

output "prometheus_workspace_id" {
  description = "AWS Managed Prometheus Workspace ID"
  value       = aws_prometheus_workspace.main.id
}

output "prometheus_workspace_arn" {
  description = "AWS Managed Prometheus Workspace ARN"
  value       = aws_prometheus_workspace.main.arn
}

output "prometheus_endpoint" {
  description = "AWS Managed Prometheus Remote Write Endpoint"
  value       = aws_prometheus_workspace.main.prometheus_endpoint
}

output "prometheus_remote_write_url" {
  description = "Prometheus Remote Write URL"
  value       = "${aws_prometheus_workspace.main.prometheus_endpoint}api/v1/remote_write"
}

output "prometheus_query_url" {
  description = "Prometheus Query URL (for Grafana data source)"
  value       = aws_prometheus_workspace.main.prometheus_endpoint
}

output "prometheus_remote_write_role_arn" {
  description = "IAM Role ARN for Prometheus Remote Write"
  value       = aws_iam_role.prometheus_remote_write.arn
}

# ------------------------------------------------------------------------------
# Grafana IAM Role (for self-hosted Grafana in EKS)
# ------------------------------------------------------------------------------

output "grafana_role_arn" {
  description = "IAM Role ARN for Grafana (IRSA)"
  value       = aws_iam_role.grafana.arn
}
