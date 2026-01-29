# ==============================================================================
# 主模块编排
# ==============================================================================
# 部署顺序:
#   001_vpc        - VPC、子网、NAT Gateway、VPC Endpoints
#   002_security   - 安全组、WAF
#   003_iam        - KMS 密钥、Secrets Manager
#   004_ecr        - ECR 镜像仓库
#   005_cognito    - Cognito User Pool (使用默认域名)
#   006_monitoring - AWS Managed Prometheus & Grafana
#   007_eks        - EKS 集群及节点组
#   008_rds        - Aurora PostgreSQL 集群
#   009_kubernetes - AWS Load Balancer Controller, NGINX Ingress, ALB, Prometheus
#   010_s3         - S3 存储桶
#   011_cloudfront - CloudFront CDN (S3 + ALB origins)
# ==============================================================================

locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# ==============================================================================
# 001. VPC 网络层
# ==============================================================================

module "vpc" {
  source = "./001_vpc"

  project_name          = var.project_name
  environment           = var.environment
  vpc_cidr              = var.vpc_cidr
  availability_zones    = var.availability_zones
  public_subnet_cidrs   = var.public_subnet_cidrs
  private_subnet_cidrs  = var.private_subnet_cidrs
  database_subnet_cidrs = var.database_subnet_cidrs
}

# ==============================================================================
# 002. 安全组
# ==============================================================================

module "security" {
  source = "./002_security"

  project_name = var.project_name
  environment  = var.environment
  vpc_id       = module.vpc.vpc_id
  vpc_cidr     = var.vpc_cidr
}

# ==============================================================================
# 003. KMS 密钥 & Secrets Manager
# ==============================================================================

module "iam" {
  source = "./003_iam"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region
}

# ==============================================================================
# 004. ECR 镜像仓库
# ==============================================================================

module "ecr" {
  source = "./004_ecr"

  project_name = var.project_name
  environment  = var.environment
}

# ==============================================================================
# WAF Web ACL (在 us-east-1 创建，用于 CloudFront)
# ==============================================================================

module "waf" {
  source = "./002_security/waf"

  providers = {
    aws = aws.us_east_1
  }

  project_name       = var.project_name
  environment        = var.environment
  rate_limit         = var.waf_rate_limit
  cognito_rate_limit = var.waf_cognito_rate_limit
}

# ==============================================================================
# 005. Cognito 身份认证 (使用 Cognito 默认域名)
# ==============================================================================

module "cognito" {
  source = "./005_cognito"

  project_name      = var.project_name
  environment       = var.environment
  user_pool_name    = var.cognito_user_pool_name
  callback_urls     = var.cognito_callback_urls
  logout_urls       = var.cognito_logout_urls
  ses_email_address = var.ses_email_address
}

# ==============================================================================
# 006. Monitoring (AWS Managed Prometheus & Grafana)
# ==============================================================================

module "monitoring" {
  source = "./006_monitoring"
  count  = var.enable_monitoring ? 1 : 0

  project_name      = var.project_name
  environment       = var.environment
  oidc_provider_arn = module.eks.oidc_provider_arn

  depends_on = [module.eks]
}

# ==============================================================================
# 007. EKS 集群
# ==============================================================================

module "eks" {
  source = "./007_eks"

  project_name       = var.project_name
  environment        = var.environment
  aws_region         = var.aws_region
  cluster_version    = var.eks_cluster_version
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids

  node_instance_types = var.eks_node_instance_types
  node_desired_size   = var.eks_node_desired_size
  node_min_size       = var.eks_node_min_size
  node_max_size       = var.eks_node_max_size
  node_disk_size      = var.eks_node_disk_size

  kms_key_arn           = module.iam.eks_kms_key_arn
  eks_security_group_id = module.security.eks_worker_security_group_id

  # ADOT Collector IAM Role (使用通配符 ARN 避免循环依赖)
  prometheus_workspace_arn = ""

  depends_on = [module.vpc, module.security, module.iam]
}

# ==============================================================================
# 008. Aurora PostgreSQL
# ==============================================================================

module "rds" {
  source = "./008_rds"

  project_name             = var.project_name
  environment              = var.environment
  vpc_id                   = module.vpc.vpc_id
  db_subnet_group_name     = module.vpc.db_subnet_group_name
  aurora_security_group_id = module.security.aurora_security_group_id

  engine_version          = var.aurora_engine_version
  instance_class          = var.aurora_instance_class
  database_name           = var.aurora_database_name
  master_username         = var.aurora_master_username
  backup_retention_period = var.aurora_backup_retention_period
  kms_key_arn             = module.iam.rds_kms_key_arn

  depends_on = [module.vpc, module.security, module.iam]
}

# ==============================================================================
# Aurora Security Group Rule for EKS Node Security Group
# ==============================================================================
# EKS 模块会创建自己的节点安全组，需要额外添加规则允许访问 Aurora

resource "aws_security_group_rule" "aurora_from_eks_nodes" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  source_security_group_id = module.eks.node_security_group_id
  security_group_id        = module.security.aurora_security_group_id
  description              = "PostgreSQL from EKS managed node group"

  depends_on = [module.eks, module.security]
}

# ==============================================================================
# 009. Kubernetes Resources (Load Balancer Controller & Ingress & ALB)
# ==============================================================================

module "kubernetes" {
  source = "./009_kubernetes"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  cluster_name                       = module.eks.cluster_name
  cluster_endpoint                   = module.eks.cluster_endpoint
  cluster_certificate_authority_data = module.eks.cluster_certificate_authority_data
  oidc_provider_arn                  = module.eks.oidc_provider_arn
  aws_lb_controller_role_arn         = module.eks.aws_lb_controller_role_arn
  vpc_id                             = module.vpc.vpc_id

  # 启用 NGINX Ingress 和通过 Terraform 创建 ALB Ingress
  enable_nginx_ingress        = var.enable_nginx_ingress
  nginx_ingress_replica_count = var.nginx_ingress_replica_count
  create_alb_ingress          = true

  # Prometheus 配置 (指标收集并发送到 AWS Managed Prometheus)
  # 注意: 如果使用 ADOT Collector，可以禁用 Prometheus Helm chart
  enable_prometheus                = var.enable_monitoring && !var.use_adot_collector
  prometheus_remote_write_url      = var.enable_monitoring ? module.monitoring[0].prometheus_remote_write_url : ""
  prometheus_remote_write_role_arn = var.enable_monitoring ? module.monitoring[0].prometheus_remote_write_role_arn : ""

  # ADOT Collector 配置 (替代 Prometheus Helm chart)
  enable_adot_collector   = var.enable_monitoring && var.use_adot_collector
  adot_collector_role_arn = module.eks.adot_collector_role_arn

  # Grafana 配置 (使用用户名密码登录)
  # Grafana 通过 nginx ingress 的 /grafana 路径访问
  enable_grafana         = var.enable_monitoring
  grafana_role_arn       = var.enable_monitoring ? module.monitoring[0].grafana_role_arn : ""
  grafana_admin_password = var.grafana_admin_password
  grafana_root_url       = var.grafana_url != "" ? "${var.grafana_url}/grafana/" : "%(protocol)s://%(domain)s:%(http_port)s/grafana/"
  prometheus_query_url   = var.enable_monitoring ? module.monitoring[0].prometheus_query_url : ""

  # PostgreSQL 客户端 (用于数据库调试)
  enable_db_client = var.enable_db_client
  aurora_endpoint  = module.rds.cluster_endpoint
  aurora_port      = 5432

  depends_on = [module.eks, module.monitoring, module.cognito, module.rds]
}

# ==============================================================================
# 010. S3 前端存储桶
# ==============================================================================

module "s3" {
  source = "./010_s3"

  project_name = var.project_name
  environment  = var.environment
  kms_key_arn  = module.iam.s3_kms_key_arn

  depends_on = [module.iam]
}

# ==============================================================================
# 011. CloudFront CDN (S3 前端 + ALB API origins)
# ==============================================================================

module "cloudfront" {
  source = "./011_cloudfront"

  project_name          = var.project_name
  environment           = var.environment
  s3_bucket_id          = module.s3.frontend_bucket_id
  s3_bucket_domain_name = module.s3.frontend_bucket_regional_domain_name
  alb_dns_name          = module.kubernetes.alb_dns_name
  waf_web_acl_arn       = module.waf.web_acl_arn

  depends_on = [module.s3, module.waf, module.kubernetes]
}

# ==============================================================================
# S3 Bucket Policy (在 CloudFront 创建后添加)
# ==============================================================================

resource "aws_s3_bucket_policy" "frontend" {
  bucket = module.s3.frontend_bucket_id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontServicePrincipal"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = "s3:GetObject"
        Resource = "${module.s3.frontend_bucket_arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = module.cloudfront.distribution_arn
          }
        }
      }
    ]
  })

  depends_on = [module.cloudfront]
}
