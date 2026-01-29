output "repository_urls" {
  description = "ECR Repository URLs"
  value = {
    for name, repo in aws_ecr_repository.services : name => repo.repository_url
  }
}

output "repository_arns" {
  description = "ECR Repository ARNs"
  value = {
    for name, repo in aws_ecr_repository.services : name => repo.arn
  }
}

output "user_service_url" {
  description = "User Service ECR URL"
  value       = aws_ecr_repository.services["user-service"].repository_url
}

output "profile_service_url" {
  description = "Profile Service ECR URL"
  value       = aws_ecr_repository.services["profile-service"].repository_url
}

output "notification_service_url" {
  description = "Notification Service ECR URL"
  value       = aws_ecr_repository.services["notification-service"].repository_url
}
