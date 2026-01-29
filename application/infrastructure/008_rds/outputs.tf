output "cluster_endpoint" {
  description = "Aurora 集群写入端点"
  value       = module.aurora.cluster_endpoint
}

output "cluster_reader_endpoint" {
  description = "Aurora 集群只读端点"
  value       = module.aurora.cluster_reader_endpoint
}

output "cluster_id" {
  description = "Aurora 集群 ID"
  value       = module.aurora.cluster_id
}

output "cluster_arn" {
  description = "Aurora 集群 ARN"
  value       = module.aurora.cluster_arn
}

output "cluster_database_name" {
  description = "Aurora 数据库名称"
  value       = module.aurora.cluster_database_name
}

output "cluster_port" {
  description = "Aurora 集群端口"
  value       = module.aurora.cluster_port
}

output "secret_arn" {
  description = "Aurora 凭证 Secret ARN"
  value       = aws_secretsmanager_secret.aurora.arn
}
