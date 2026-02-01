###############################################################################
# Code Interpreter IAM Role and Resource
# 用于 SHARA Remediator Agent 在沙盒环境中执行修复代码
###############################################################################

#------------------------------------------------------------------------------
# Code Interpreter Execution Role
#------------------------------------------------------------------------------

# Trust policy - 允许 Bedrock AgentCore 服务 assume 此角色
data "aws_iam_policy_document" "code_interpreter_assume_role" {
  statement {
    effect = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "code_interpreter_execution" {
  name               = "${local.name_prefix}-code-interpreter-role"
  assume_role_policy = data.aws_iam_policy_document.code_interpreter_assume_role.json
  description        = "Execution role for SHARA Code Interpreter - security finding remediation"

  tags = {
    Name      = "${local.name_prefix}-code-interpreter-role"
    Component = "CodeInterpreter"
  }
}

#------------------------------------------------------------------------------
# S3 Remediation Permissions
# 修复: S3.1-S3.14 (公开访问、加密、版本控制、日志等)
#------------------------------------------------------------------------------

data "aws_iam_policy_document" "code_interpreter_s3" {
  statement {
    sid    = "S3BucketRemediation"
    effect = "Allow"
    actions = [
      # Block Public Access (S3.1, S3.2, S3.3)
      "s3:GetBucketPublicAccessBlock",
      "s3:PutBucketPublicAccessBlock",
      # Encryption (S3.4)
      "s3:GetBucketEncryption",
      "s3:PutBucketEncryption",
      # Versioning (S3.14)
      "s3:GetBucketVersioning",
      "s3:PutBucketVersioning",
      # Logging (S3.9)
      "s3:GetBucketLogging",
      "s3:PutBucketLogging",
      # Lifecycle (S3.13)
      "s3:GetLifecycleConfiguration",
      "s3:PutLifecycleConfiguration",
      # SSL/TLS Policy (S3.5)
      "s3:GetBucketPolicy",
      "s3:PutBucketPolicy",
      # ACL (S3.12)
      "s3:GetBucketAcl",
      "s3:PutBucketAcl",
      # Cross-Region Replication (S3.7)
      "s3:GetReplicationConfiguration",
      "s3:PutReplicationConfiguration",
      # Event Notifications
      "s3:GetBucketNotification",
      "s3:PutBucketNotification",
    ]
    # 限制只能操作特定账户的 S3 bucket
    resources = [
      "arn:aws:s3:::*"
    ]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role_policy" "code_interpreter_s3" {
  name   = "s3-remediation"
  role   = aws_iam_role.code_interpreter_execution.id
  policy = data.aws_iam_policy_document.code_interpreter_s3.json
}

#------------------------------------------------------------------------------
# EC2 Security Group Remediation Permissions
# 修复: EC2.2, EC2.18, EC2.19 (开放端口、安全组规则)
#------------------------------------------------------------------------------

data "aws_iam_policy_document" "code_interpreter_ec2" {
  statement {
    sid    = "EC2SecurityGroupRemediation"
    effect = "Allow"
    actions = [
      # 查询安全组
      "ec2:DescribeSecurityGroups",
      "ec2:DescribeSecurityGroupRules",
      # 修改入站规则 (EC2.18, EC2.19)
      "ec2:AuthorizeSecurityGroupIngress",
      "ec2:RevokeSecurityGroupIngress",
      # 修改出站规则
      "ec2:AuthorizeSecurityGroupEgress",
      "ec2:RevokeSecurityGroupEgress",
      # 查询实例 (用于确认影响)
      "ec2:DescribeInstances",
      "ec2:DescribeNetworkInterfaces",
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }

  statement {
    sid    = "EC2InstanceRemediation"
    effect = "Allow"
    actions = [
      # IMDSv2 (EC2.8)
      "ec2:ModifyInstanceMetadataOptions",
      # EBS Encryption (EC2.3)
      "ec2:ModifyInstanceAttribute",
    ]
    resources = [
      "arn:aws:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:instance/*"
    ]
  }
}

resource "aws_iam_role_policy" "code_interpreter_ec2" {
  name   = "ec2-remediation"
  role   = aws_iam_role.code_interpreter_execution.id
  policy = data.aws_iam_policy_document.code_interpreter_ec2.json
}

#------------------------------------------------------------------------------
# SNS Remediation Permissions
# 修复: SNS.1, SNS.2 (加密、访问策略)
#------------------------------------------------------------------------------

data "aws_iam_policy_document" "code_interpreter_sns" {
  statement {
    sid    = "SNSRemediation"
    effect = "Allow"
    actions = [
      "sns:GetTopicAttributes",
      "sns:SetTopicAttributes",
      "sns:ListTopics",
    ]
    resources = [
      "arn:aws:sns:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"
    ]
  }
}

resource "aws_iam_role_policy" "code_interpreter_sns" {
  name   = "sns-remediation"
  role   = aws_iam_role.code_interpreter_execution.id
  policy = data.aws_iam_policy_document.code_interpreter_sns.json
}

#------------------------------------------------------------------------------
# RDS Remediation Permissions
# 修复: RDS.1-RDS.13 (加密、公开访问、日志等)
#------------------------------------------------------------------------------

data "aws_iam_policy_document" "code_interpreter_rds" {
  statement {
    sid    = "RDSRemediation"
    effect = "Allow"
    actions = [
      # 查询
      "rds:DescribeDBInstances",
      "rds:DescribeDBClusters",
      "rds:DescribeDBClusterSnapshots",
      "rds:DescribeDBSnapshots",
      # 修改实例配置 (RDS.2, RDS.3, RDS.4)
      "rds:ModifyDBInstance",
      "rds:ModifyDBCluster",
      # 快照加密 (RDS.7)
      "rds:ModifyDBSnapshotAttribute",
      "rds:ModifyDBClusterSnapshotAttribute",
    ]
    resources = [
      "arn:aws:rds:${var.aws_region}:${data.aws_caller_identity.current.account_id}:db:*",
      "arn:aws:rds:${var.aws_region}:${data.aws_caller_identity.current.account_id}:cluster:*",
      "arn:aws:rds:${var.aws_region}:${data.aws_caller_identity.current.account_id}:snapshot:*",
      "arn:aws:rds:${var.aws_region}:${data.aws_caller_identity.current.account_id}:cluster-snapshot:*",
    ]
  }
}

resource "aws_iam_role_policy" "code_interpreter_rds" {
  name   = "rds-remediation"
  role   = aws_iam_role.code_interpreter_execution.id
  policy = data.aws_iam_policy_document.code_interpreter_rds.json
}

#------------------------------------------------------------------------------
# Lambda Remediation Permissions
# 修复: Lambda.1, Lambda.2, Lambda.3 (公开访问、VPC、运行时)
#------------------------------------------------------------------------------

data "aws_iam_policy_document" "code_interpreter_lambda" {
  statement {
    sid    = "LambdaRemediation"
    effect = "Allow"
    actions = [
      "lambda:GetFunction",
      "lambda:GetFunctionConfiguration",
      "lambda:GetPolicy",
      "lambda:RemovePermission",
      "lambda:AddPermission",
      "lambda:UpdateFunctionConfiguration",
    ]
    resources = [
      "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:*"
    ]
  }
}

resource "aws_iam_role_policy" "code_interpreter_lambda" {
  name   = "lambda-remediation"
  role   = aws_iam_role.code_interpreter_execution.id
  policy = data.aws_iam_policy_document.code_interpreter_lambda.json
}

#------------------------------------------------------------------------------
# IAM Remediation Permissions (受限)
# 修复: IAM.1-IAM.8 (密码策略、MFA、访问密钥轮换)
# 注意: IAM 修改需要格外谨慎，只允许特定操作
#------------------------------------------------------------------------------

data "aws_iam_policy_document" "code_interpreter_iam" {
  statement {
    sid    = "IAMPasswordPolicy"
    effect = "Allow"
    actions = [
      # 账户密码策略 (IAM.10, IAM.11, IAM.12, IAM.13, IAM.14, IAM.15, IAM.16, IAM.17)
      "iam:GetAccountPasswordPolicy",
      "iam:UpdateAccountPasswordPolicy",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "IAMUserRemediation"
    effect = "Allow"
    actions = [
      # 只读查询
      "iam:GetUser",
      "iam:ListMFADevices",
      "iam:ListAccessKeys",
      "iam:GetAccessKeyLastUsed",
      # 停用未使用的访问密钥 (IAM.3)
      "iam:UpdateAccessKey",
      # 删除过期凭证 (IAM.6)
      "iam:DeleteAccessKey",
    ]
    resources = [
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:user/*"
    ]
  }

  # 明确禁止危险操作
  statement {
    sid    = "DenyDangerousIAMActions"
    effect = "Deny"
    actions = [
      "iam:CreateUser",
      "iam:DeleteUser",
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:AttachUserPolicy",
      "iam:AttachRolePolicy",
      "iam:PutUserPolicy",
      "iam:PutRolePolicy",
      "iam:CreatePolicy",
      "iam:DeletePolicy",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "code_interpreter_iam" {
  name   = "iam-remediation"
  role   = aws_iam_role.code_interpreter_execution.id
  policy = data.aws_iam_policy_document.code_interpreter_iam.json
}

#------------------------------------------------------------------------------
# CloudTrail Remediation Permissions
# 修复: CloudTrail.1, CloudTrail.2 (日志启用、加密)
#------------------------------------------------------------------------------

data "aws_iam_policy_document" "code_interpreter_cloudtrail" {
  statement {
    sid    = "CloudTrailRemediation"
    effect = "Allow"
    actions = [
      "cloudtrail:DescribeTrails",
      "cloudtrail:GetTrailStatus",
      "cloudtrail:UpdateTrail",
      "cloudtrail:StartLogging",
    ]
    resources = [
      "arn:aws:cloudtrail:${var.aws_region}:${data.aws_caller_identity.current.account_id}:trail/*"
    ]
  }
}

resource "aws_iam_role_policy" "code_interpreter_cloudtrail" {
  name   = "cloudtrail-remediation"
  role   = aws_iam_role.code_interpreter_execution.id
  policy = data.aws_iam_policy_document.code_interpreter_cloudtrail.json
}

#------------------------------------------------------------------------------
# KMS Permissions (用于加密修复)
# 修复: KMS.1, KMS.4 (密钥轮换)
#------------------------------------------------------------------------------

data "aws_iam_policy_document" "code_interpreter_kms" {
  statement {
    sid    = "KMSRemediation"
    effect = "Allow"
    actions = [
      "kms:DescribeKey",
      "kms:GetKeyRotationStatus",
      "kms:EnableKeyRotation",
      "kms:ListAliases",
      "kms:ListKeys",
    ]
    resources = [
      "arn:aws:kms:${var.aws_region}:${data.aws_caller_identity.current.account_id}:key/*"
    ]
  }
}

resource "aws_iam_role_policy" "code_interpreter_kms" {
  name   = "kms-remediation"
  role   = aws_iam_role.code_interpreter_execution.id
  policy = data.aws_iam_policy_document.code_interpreter_kms.json
}

#------------------------------------------------------------------------------
# AWS Config Remediation Permissions
# 修复: Config.1 (配置记录器)
#------------------------------------------------------------------------------

data "aws_iam_policy_document" "code_interpreter_config" {
  statement {
    sid    = "ConfigRemediation"
    effect = "Allow"
    actions = [
      # 查询配置记录器
      "config:DescribeConfigurationRecorders",
      "config:DescribeConfigurationRecorderStatus",
      "config:DescribeDeliveryChannels",
      "config:DescribeDeliveryChannelStatus",
      # 修改配置记录器 (Config.1)
      "config:PutConfigurationRecorder",
      "config:StartConfigurationRecorder",
      "config:StopConfigurationRecorder",
      # 配置交付通道
      "config:PutDeliveryChannel",
    ]
    resources = ["*"]
  }

  # IAM PassRole - Config 记录器可能需要 service-linked role
  statement {
    sid    = "ConfigPassRole"
    effect = "Allow"
    actions = [
      "iam:PassRole"
    ]
    resources = [
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/aws-service-role/config.amazonaws.com/*"
    ]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["config.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "code_interpreter_config" {
  name   = "config-remediation"
  role   = aws_iam_role.code_interpreter_execution.id
  policy = data.aws_iam_policy_document.code_interpreter_config.json
}

#------------------------------------------------------------------------------
# CloudWatch Logs (用于 Code Interpreter 日志)
#------------------------------------------------------------------------------

data "aws_iam_policy_document" "code_interpreter_logs" {
  statement {
    sid    = "CloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/*"
    ]
  }
}

resource "aws_iam_role_policy" "code_interpreter_logs" {
  name   = "cloudwatch-logs"
  role   = aws_iam_role.code_interpreter_execution.id
  policy = data.aws_iam_policy_document.code_interpreter_logs.json
}

#------------------------------------------------------------------------------
# SQS Remediation Permissions
# 修复: SQS.1 (加密)
#------------------------------------------------------------------------------

data "aws_iam_policy_document" "code_interpreter_sqs" {
  statement {
    sid    = "SQSRemediation"
    effect = "Allow"
    actions = [
      "sqs:GetQueueAttributes",
      "sqs:SetQueueAttributes",
    ]
    resources = [
      "arn:aws:sqs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"
    ]
  }
}

resource "aws_iam_role_policy" "code_interpreter_sqs" {
  name   = "sqs-remediation"
  role   = aws_iam_role.code_interpreter_execution.id
  policy = data.aws_iam_policy_document.code_interpreter_sqs.json
}

#------------------------------------------------------------------------------
# Secrets Manager Remediation Permissions
# 修复: SecretsManager.1, SecretsManager.2 (轮换、未使用)
#------------------------------------------------------------------------------

data "aws_iam_policy_document" "code_interpreter_secretsmanager" {
  statement {
    sid    = "SecretsManagerRemediation"
    effect = "Allow"
    actions = [
      "secretsmanager:DescribeSecret",
      "secretsmanager:RotateSecret",
      "secretsmanager:GetResourcePolicy",
      "secretsmanager:PutResourcePolicy",
    ]
    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:*"
    ]
  }
}

resource "aws_iam_role_policy" "code_interpreter_secretsmanager" {
  name   = "secretsmanager-remediation"
  role   = aws_iam_role.code_interpreter_execution.id
  policy = data.aws_iam_policy_document.code_interpreter_secretsmanager.json
}

#------------------------------------------------------------------------------
# ELB/ALB Remediation Permissions
# 修复: ELB.3, ELB.4 (访问日志、HTTPS)
#------------------------------------------------------------------------------

data "aws_iam_policy_document" "code_interpreter_elb" {
  statement {
    sid    = "ELBRemediation"
    effect = "Allow"
    actions = [
      "elasticloadbalancing:DescribeLoadBalancers",
      "elasticloadbalancing:DescribeLoadBalancerAttributes",
      "elasticloadbalancing:ModifyLoadBalancerAttributes",
      "elasticloadbalancing:DescribeListeners",
      "elasticloadbalancing:ModifyListener",
    ]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "aws:ResourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role_policy" "code_interpreter_elb" {
  name   = "elb-remediation"
  role   = aws_iam_role.code_interpreter_execution.id
  policy = data.aws_iam_policy_document.code_interpreter_elb.json
}

#------------------------------------------------------------------------------
# Code Interpreter Resource
# 注意: Code Interpreter 需要通过 AWS Console 手动创建
# AWS CLI 目前只提供 Data Plane API (start/stop/invoke session)
# 不提供 Control Plane API (create/delete code interpreter)
#
# Console 创建步骤:
# 1. 打开 Amazon Bedrock AgentCore Console
# 2. 导航到 Code Interpreter
# 3. 创建新的 Code Interpreter，选择上面创建的 IAM Role
# 4. 记录 Code Interpreter ID，配置到 .env 文件的 CODE_INTERPRETER_ID
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
# Outputs
#------------------------------------------------------------------------------

output "code_interpreter_role_arn" {
  description = "ARN of the Code Interpreter execution role"
  value       = aws_iam_role.code_interpreter_execution.arn
}

output "code_interpreter_role_name" {
  description = "Name of the Code Interpreter execution role"
  value       = aws_iam_role.code_interpreter_execution.name
}
