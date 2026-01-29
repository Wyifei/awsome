# ==============================================================================
# Amazon Aurora PostgreSQL (使用官方 RDS Aurora Module)
# ==============================================================================

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

# ==============================================================================
# Random Password for Aurora
# ==============================================================================

resource "random_password" "aurora" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

# ==============================================================================
# Aurora PostgreSQL Cluster (使用 terraform-aws-modules/rds-aurora/aws)
# ==============================================================================

module "aurora" {
  source  = "terraform-aws-modules/rds-aurora/aws"
  version = "~> 9.0"

  name           = "${local.name_prefix}-aurora"
  engine         = "aurora-postgresql"
  engine_version = var.engine_version
  instance_class = var.instance_class

  instances = {
    writer = {
      identifier = "${local.name_prefix}-aurora-writer"
    }
    reader = {
      identifier = "${local.name_prefix}-aurora-reader"
    }
  }

  # 数据库配置
  database_name   = var.database_name
  master_username = var.master_username
  master_password = random_password.aurora.result

  # 网络配置
  vpc_id               = var.vpc_id
  db_subnet_group_name = var.db_subnet_group_name

  # 使用已存在的安全组，禁用模块内部创建
  create_security_group  = false
  vpc_security_group_ids = [var.aurora_security_group_id]

  # 存储加密
  storage_encrypted = true
  kms_key_id        = var.kms_key_arn

  # 备份配置
  backup_retention_period      = var.backup_retention_period
  preferred_backup_window      = "03:00-04:00"
  preferred_maintenance_window = "sun:04:00-sun:05:00"

  # 保护配置
  deletion_protection       = false # 测试环境设为 false，生产环境改为 true
  skip_final_snapshot       = true  # 测试环境设为 true，生产环境改为 false
  final_snapshot_identifier = "${local.name_prefix}-aurora-final-snapshot"

  # 监控配置
  performance_insights_enabled    = true
  performance_insights_kms_key_id = var.kms_key_arn
  monitoring_interval             = 60
  create_monitoring_role          = true
  iam_role_name                   = "${local.name_prefix}-rds-monitoring-role"
  iam_role_use_name_prefix        = false

  # CloudWatch 日志
  enabled_cloudwatch_logs_exports = ["postgresql"]

  # 参数组
  create_db_cluster_parameter_group = true
  db_cluster_parameter_group_family = "aurora-postgresql16"
  db_cluster_parameter_group_parameters = [
    {
      name  = "timezone"
      value = "Asia/Tokyo"
    },
    {
      name  = "log_statement"
      value = "all"
    },
    {
      name  = "log_min_duration_statement"
      value = "1000"
    }
  ]

  create_db_parameter_group = true
  db_parameter_group_family = "aurora-postgresql16"
  db_parameter_group_parameters = [
    {
      name         = "max_connections"
      value        = "500"
      apply_method = "pending-reboot" # 静态参数需要重启后生效
    }
  ]

  # 自动小版本升级
  auto_minor_version_upgrade = true

  tags = {
    Name = "${local.name_prefix}-aurora"
  }
}

# ==============================================================================
# Secrets Manager - Aurora Credentials
# ==============================================================================

resource "aws_secretsmanager_secret" "aurora" {
  name       = "${local.name_prefix}/aurora-credentials"
  kms_key_id = var.kms_key_arn

  tags = {
    Name = "${local.name_prefix}-aurora-credentials"
  }
}

resource "aws_secretsmanager_secret_version" "aurora" {
  secret_id = aws_secretsmanager_secret.aurora.id
  secret_string = jsonencode({
    username = var.master_username
    password = random_password.aurora.result
    engine   = "postgresql"
    host     = module.aurora.cluster_endpoint
    port     = 5432
    dbname   = var.database_name
  })
}
