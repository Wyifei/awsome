# ==============================================================================
# Amazon ECR Repositories
# ==============================================================================

locals {
  name_prefix = "${var.project_name}-${var.environment}"

  # 微服务列表
  services = [
    "user-service",
    "profile-service",
    "notification-service"
  ]
}

# ==============================================================================
# ECR Repositories
# ==============================================================================

resource "aws_ecr_repository" "services" {
  for_each = toset(local.services)

  name                 = "${local.name_prefix}/${each.value}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name    = "${local.name_prefix}-${each.value}"
    Service = each.value
  }
}

# ==============================================================================
# ECR Lifecycle Policy (保留最近 30 个镜像)
# ==============================================================================

resource "aws_ecr_lifecycle_policy" "services" {
  for_each = aws_ecr_repository.services

  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 30 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 1
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# ==============================================================================
# ECR Repository Policy (允许 EKS 拉取镜像)
# ==============================================================================

data "aws_caller_identity" "current" {}

resource "aws_ecr_repository_policy" "services" {
  for_each = aws_ecr_repository.services

  repository = each.value.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowPull"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:BatchCheckLayerAvailability"
        ]
      }
    ]
  })
}
