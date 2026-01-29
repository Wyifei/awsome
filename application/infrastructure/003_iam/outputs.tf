output "rds_kms_key_arn" {
  description = "RDS KMS Key ARN"
  value       = aws_kms_key.rds.arn
}

output "rds_kms_key_id" {
  description = "RDS KMS Key ID"
  value       = aws_kms_key.rds.key_id
}

output "eks_kms_key_arn" {
  description = "EKS KMS Key ARN"
  value       = aws_kms_key.eks.arn
}

output "eks_kms_key_id" {
  description = "EKS KMS Key ID"
  value       = aws_kms_key.eks.key_id
}

output "secrets_kms_key_arn" {
  description = "Secrets Manager KMS Key ARN"
  value       = aws_kms_key.secrets.arn
}

output "secrets_kms_key_id" {
  description = "Secrets Manager KMS Key ID"
  value       = aws_kms_key.secrets.key_id
}

output "s3_kms_key_arn" {
  description = "S3 KMS Key ARN"
  value       = aws_kms_key.s3.arn
}

output "s3_kms_key_id" {
  description = "S3 KMS Key ID"
  value       = aws_kms_key.s3.key_id
}

output "db_credentials_secret_arn" {
  description = "Database credentials secret ARN"
  value       = aws_secretsmanager_secret.db_credentials.arn
}

output "internal_api_key_secret_arn" {
  description = "Internal API key secret ARN"
  value       = aws_secretsmanager_secret.internal_api_key.arn
}
