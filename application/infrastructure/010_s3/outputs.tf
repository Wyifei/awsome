output "frontend_bucket_id" {
  description = "Frontend S3 存储桶 ID"
  value       = aws_s3_bucket.frontend.id
}

output "frontend_bucket_arn" {
  description = "Frontend S3 存储桶 ARN"
  value       = aws_s3_bucket.frontend.arn
}

output "frontend_bucket_regional_domain_name" {
  description = "Frontend S3 存储桶区域域名"
  value       = aws_s3_bucket.frontend.bucket_regional_domain_name
}

output "avatars_bucket_id" {
  description = "Avatars S3 存储桶 ID"
  value       = aws_s3_bucket.avatars.id
}

output "avatars_bucket_arn" {
  description = "Avatars S3 存储桶 ARN"
  value       = aws_s3_bucket.avatars.arn
}
