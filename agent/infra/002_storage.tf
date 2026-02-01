###############################################################################
# Storage Resources - DynamoDB Tables and S3 Buckets
###############################################################################

#------------------------------------------------------------------------------
# DynamoDB Tables
#------------------------------------------------------------------------------

# Tasks Table - 任务主表（单表设计）
# 使用复合键模式存储多种实体类型：
# - PK: TASK#<taskId>, SK: METADATA           -> 任务元数据
# - PK: TASK#<taskId>, SK: ROLLBACK#<arn>     -> 回滚数据
# - PK: TASK#<taskId>, SK: EVENT#<ts>#<id>    -> 事件历史
resource "aws_dynamodb_table" "tasks" {
  name         = "${local.name_prefix}-tasks"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  # 主键
  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  # GSI1 复合键: 按状态查询 (STATUS#<status>, <createdAt>)
  attribute {
    name = "GSI1PK"
    type = "S"
  }

  attribute {
    name = "GSI1SK"
    type = "S"
  }

  # GSI2 复合键: 按 Finding 查询 (FINDING#<findingId>, <createdAt>)
  attribute {
    name = "GSI2PK"
    type = "S"
  }

  attribute {
    name = "GSI2SK"
    type = "S"
  }

  # GSI3 复合键: 按账户查询 (ACCOUNT#<accountId>, <createdAt>)
  attribute {
    name = "GSI3PK"
    type = "S"
  }

  attribute {
    name = "GSI3SK"
    type = "S"
  }

  # GSI1: 按状态查询任务 (e.g., STATUS#waiting_approval)
  global_secondary_index {
    name            = "GSI1"
    hash_key        = "GSI1PK"
    range_key       = "GSI1SK"
    projection_type = "ALL"
  }

  # GSI2: 按 Finding ID 查询 (e.g., FINDING#arn:aws:securityhub:...)
  global_secondary_index {
    name            = "GSI2"
    hash_key        = "GSI2PK"
    range_key       = "GSI2SK"
    projection_type = "ALL"
  }

  # GSI3: 按账户查询 (e.g., ACCOUNT#123456789012)
  global_secondary_index {
    name            = "GSI3"
    hash_key        = "GSI3PK"
    range_key       = "GSI3SK"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Name = "${local.name_prefix}-tasks"
  }
}

# Tokens Table - 审批令牌表
resource "aws_dynamodb_table" "tokens" {
  name         = "${local.name_prefix}-approval-tokens"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  attribute {
    name = "task_id"
    type = "S"
  }

  # GSI: 按任务 ID 查询令牌
  global_secondary_index {
    name            = "task-index"
    hash_key        = "task_id"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Name = "${local.name_prefix}-approval-tokens"
  }
}

#------------------------------------------------------------------------------
# S3 Buckets
#------------------------------------------------------------------------------

# ASR Playbooks Bucket - ASR 预置修复方案存储桶
# 存储从 AWS Automated Security Response 转换的预置修复脚本
# Analyzer Agent 通过 Control ID 精确匹配获取
resource "aws_s3_bucket" "asr_playbooks" {
  bucket = "${local.name_prefix}-asr-playbooks-${local.account_id}"

  tags = {
    Name = "${local.name_prefix}-asr-playbooks"
  }
}

resource "aws_s3_bucket_versioning" "asr_playbooks" {
  bucket = aws_s3_bucket.asr_playbooks.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "asr_playbooks" {
  bucket = aws_s3_bucket.asr_playbooks.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "asr_playbooks" {
  bucket = aws_s3_bucket.asr_playbooks.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

#------------------------------------------------------------------------------
# Remediation Audit Bucket - 修复审计日志存储桶
# 存储 Remediator Agent 执行的代码和日志，用于审计和 troubleshooting
# 结构: s3://bucket/tasks/{task_id}/
#   - code.py          - 执行的修复代码
#   - execution.log    - 执行日志 (stdout, stderr, exit_code)
#   - metadata.json    - 元数据 (timestamp, resource_arn, control_id 等)
#------------------------------------------------------------------------------

resource "aws_s3_bucket" "remediation_audit" {
  bucket = "${local.name_prefix}-remediation-audit-${local.account_id}"

  tags = {
    Name = "${local.name_prefix}-remediation-audit"
  }
}

resource "aws_s3_bucket_versioning" "remediation_audit" {
  bucket = aws_s3_bucket.remediation_audit.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "remediation_audit" {
  bucket = aws_s3_bucket.remediation_audit.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "remediation_audit" {
  bucket = aws_s3_bucket.remediation_audit.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# 生命周期策略 - 审计日志保留 90 天，之后转移到 Glacier，1 年后删除
resource "aws_s3_bucket_lifecycle_configuration" "remediation_audit" {
  bucket = aws_s3_bucket.remediation_audit.id

  rule {
    id     = "audit-retention"
    status = "Enabled"

    transition {
      days          = 90
      storage_class = "GLACIER"
    }

    expiration {
      days = 365
    }

    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

