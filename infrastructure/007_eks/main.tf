# ==============================================================================
# Amazon EKS Cluster (使用官方 EKS Module)
# ==============================================================================

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

data "aws_caller_identity" "current" {}

# ==============================================================================
# EKS Cluster (使用 terraform-aws-modules/eks/aws)
# ==============================================================================

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = local.name_prefix
  cluster_version = var.cluster_version

  # 网络配置
  vpc_id     = var.vpc_id
  subnet_ids = var.private_subnet_ids

  # 集群端点访问
  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true

  # 禁用模块内部 KMS 创建，使用外部 KMS key
  create_kms_key = false
  cluster_encryption_config = {
    provider_key_arn = var.kms_key_arn
    resources        = ["secrets"]
  }

  # 集群日志
  cluster_enabled_log_types = [
    "api",
    "audit",
    "authenticator",
    "controllerManager",
    "scheduler"
  ]

  # 集群安全组
  cluster_additional_security_group_ids = [var.eks_security_group_id]

  # EKS Managed Node Group
  eks_managed_node_groups = {
    main = {
      name           = "${local.name_prefix}-ng"
      instance_types = var.node_instance_types
      capacity_type  = "ON_DEMAND"
      ami_type       = "AL2023_ARM_64_STANDARD"
      disk_size      = var.node_disk_size

      min_size     = var.node_min_size
      max_size     = var.node_max_size
      desired_size = var.node_desired_size

      labels = {
        role = "worker"
      }

      # 使用完整名称而非前缀，避免超过 38 字符限制
      iam_role_use_name_prefix = false
      iam_role_name            = "${local.name_prefix}-ng-role"

      # 节点 IAM 策略
      iam_role_additional_policies = {
        ssm = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
      }

      tags = {
        Name = "${local.name_prefix}-eks-node"
      }
    }
  }

  # EKS Add-ons
  cluster_addons = {
    coredns = {
      most_recent = true
      configuration_values = jsonencode({
        replicaCount = 2
      })
    }
    kube-proxy = {
      most_recent = true
    }
    vpc-cni = {
      most_recent = true
    }
    aws-ebs-csi-driver = {
      most_recent              = true
      service_account_role_arn = module.ebs_csi_irsa_role.iam_role_arn
    }
  }

  # OIDC Provider (用于 IRSA)
  enable_irsa = true

  tags = {
    Name = "${local.name_prefix}-eks-cluster"
  }
}

# ==============================================================================
# EBS CSI Driver IAM Role (IRSA)
# ==============================================================================

module "ebs_csi_irsa_role" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name             = "${local.name_prefix}-ebs-csi-driver-role"
  attach_ebs_csi_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:ebs-csi-controller-sa"]
    }
  }

  tags = {
    Name = "${local.name_prefix}-ebs-csi-driver-role"
  }
}

# ==============================================================================
# AWS Load Balancer Controller IAM Role (IRSA)
# ==============================================================================

module "aws_lb_controller_irsa_role" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name                              = "${local.name_prefix}-aws-lb-controller-role"
  attach_load_balancer_controller_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:aws-load-balancer-controller"]
    }
  }

  tags = {
    Name = "${local.name_prefix}-aws-lb-controller-role"
  }
}

# ==============================================================================
# Application Service IAM Role (IRSA)
# ==============================================================================

module "app_service_irsa_role" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "~> 5.0"

  role_name = "${local.name_prefix}-app-service-role"

  oidc_providers = {
    main = {
      provider_arn = module.eks.oidc_provider_arn
      namespace_service_accounts = [
        "auth-platform:user-service-sa",
        "auth-platform:profile-service-sa",
        "auth-platform:notification-service-sa"
      ]
    }
  }

  role_policy_arns = {
    app_service_policy = aws_iam_policy.app_service.arn
  }

  tags = {
    Name = "${local.name_prefix}-app-service-role"
  }
}

# Application Service IAM Policy
resource "aws_iam_policy" "app_service" {
  name        = "${local.name_prefix}-app-service-policy"
  description = "IAM policy for application service"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SecretsManagerAccess"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = "arn:aws:secretsmanager:*:${data.aws_caller_identity.current.account_id}:secret:${var.project_name}/*"
      },
      {
        Sid    = "CognitoAccess"
        Effect = "Allow"
        Action = [
          "cognito-idp:AdminGetUser",
          "cognito-idp:AdminUpdateUserAttributes",
          "cognito-idp:AdminDisableUser",
          "cognito-idp:AdminEnableUser",
          "cognito-idp:AdminDeleteUser",
          "cognito-idp:AdminCreateUser",
          "cognito-idp:AdminSetUserPassword",
          "cognito-idp:ListUsers"
        ]
        Resource = "arn:aws:cognito-idp:*:${data.aws_caller_identity.current.account_id}:userpool/*"
      },
      {
        Sid    = "SESAccess"
        Effect = "Allow"
        Action = [
          "ses:SendEmail",
          "ses:SendRawEmail"
        ]
        Resource = "*"
      },
      {
        Sid    = "S3AvatarBucketAccess"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject"
        ]
        Resource = "arn:aws:s3:::${var.project_name}-${var.environment}-avatars/*"
      },
      {
        Sid    = "S3AvatarBucketList"
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = "arn:aws:s3:::${var.project_name}-${var.environment}-avatars"
      }
    ]
  })

  tags = {
    Name = "${local.name_prefix}-app-service-policy"
  }
}
