###############################################################################
# IAM Roles and Policies
###############################################################################

#------------------------------------------------------------------------------
# Lambda Execution Role
#------------------------------------------------------------------------------

# Trust policy for Lambda
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# Lambda execution role
resource "aws_iam_role" "lambda_execution" {
  name               = "${local.name_prefix}-lambda-execution"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  description        = "Execution role for SHARA Lambda functions"

  tags = {
    Name = "${local.name_prefix}-lambda-execution"
  }
}

#------------------------------------------------------------------------------
# Lambda Basic Execution Policy (VPC + CloudWatch)
#------------------------------------------------------------------------------

resource "aws_iam_role_policy_attachment" "lambda_vpc" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

#------------------------------------------------------------------------------
# DynamoDB Access Policy
#------------------------------------------------------------------------------

data "aws_iam_policy_document" "dynamodb_access" {
  statement {
    sid    = "DynamoDBAccess"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]
    resources = [
      aws_dynamodb_table.tasks.arn,
      "${aws_dynamodb_table.tasks.arn}/index/*",
      aws_dynamodb_table.tokens.arn,
      "${aws_dynamodb_table.tokens.arn}/index/*",
    ]
  }
}

resource "aws_iam_role_policy" "dynamodb_access" {
  name   = "dynamodb-access"
  role   = aws_iam_role.lambda_execution.id
  policy = data.aws_iam_policy_document.dynamodb_access.json
}

#------------------------------------------------------------------------------
# S3 ASR Playbooks Bucket Access Policy
#------------------------------------------------------------------------------

data "aws_iam_policy_document" "s3_asr_playbooks_access" {
  statement {
    sid    = "S3ASRPlaybooksAccess"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.asr_playbooks.arn,
      "${aws_s3_bucket.asr_playbooks.arn}/*",
    ]
  }
}

resource "aws_iam_role_policy" "s3_asr_playbooks_access" {
  name   = "s3-asr-playbooks-access"
  role   = aws_iam_role.lambda_execution.id
  policy = data.aws_iam_policy_document.s3_asr_playbooks_access.json
}

#------------------------------------------------------------------------------
# Bedrock Access Policy
#------------------------------------------------------------------------------

data "aws_iam_policy_document" "bedrock_access" {
  statement {
    sid    = "BedrockInvoke"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "BedrockKnowledgeBase"
    effect = "Allow"
    actions = [
      "bedrock:Retrieve",
      "bedrock:RetrieveAndGenerate",
    ]
    resources = ["*"]
  }

  # 注：AgentCore 通过 HTTP Gateway 调用，不需要 bedrock:InvokeAgent
}

resource "aws_iam_role_policy" "bedrock_access" {
  name   = "bedrock-access"
  role   = aws_iam_role.lambda_execution.id
  policy = data.aws_iam_policy_document.bedrock_access.json
}

#------------------------------------------------------------------------------
# AgentCore Runtime Access Policy
#------------------------------------------------------------------------------

locals {
  # 收集所有配置的 Runtime ARNs
  configured_runtime_arns = compact([
    var.analyzer_runtime_arn,
    var.remediator_runtime_arn,
    var.validator_runtime_arn,
  ])
  has_runtime_arns = length(local.configured_runtime_arns) > 0
}

data "aws_iam_policy_document" "agentcore_access" {
  statement {
    sid    = "AgentCoreRuntimeInvoke"
    effect = "Allow"
    actions = [
      "bedrock-agentcore:InvokeAgentRuntime",
      "bedrock-agentcore:InvokeRuntime",
      "bedrock-agentcore:InvokeAgent",
    ]
    resources = local.has_runtime_arns ? concat(
      local.configured_runtime_arns,
      [for arn in local.configured_runtime_arns : "${arn}/*"]
    ) : [
      "arn:aws:bedrock-agentcore:${var.aws_region}:*:runtime/*",
      "arn:aws:bedrock-agentcore:${var.aws_region}:*:runtime/*/*"
    ]
  }
}

resource "aws_iam_role_policy" "agentcore_access" {
  count = local.has_runtime_arns ? 1 : 0

  name   = "agentcore-access"
  role   = aws_iam_role.lambda_execution.id
  policy = data.aws_iam_policy_document.agentcore_access.json
}

#------------------------------------------------------------------------------
# Security Hub Access Policy
#------------------------------------------------------------------------------

data "aws_iam_policy_document" "securityhub_access" {
  statement {
    sid    = "SecurityHubAccess"
    effect = "Allow"
    actions = [
      "securityhub:GetFindings",
      "securityhub:BatchUpdateFindings",
      "securityhub:UpdateFindings",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "securityhub_access" {
  name   = "securityhub-access"
  role   = aws_iam_role.lambda_execution.id
  policy = data.aws_iam_policy_document.securityhub_access.json
}

#------------------------------------------------------------------------------
# SES Access Policy (发送审批邮件)
#------------------------------------------------------------------------------

data "aws_iam_policy_document" "ses_access" {
  statement {
    sid    = "SESAccess"
    effect = "Allow"
    actions = [
      "ses:SendEmail",
      "ses:SendRawEmail",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "ses_access" {
  name   = "ses-access"
  role   = aws_iam_role.lambda_execution.id
  policy = data.aws_iam_policy_document.ses_access.json
}

#------------------------------------------------------------------------------
# Security Analysis Read Access Policy (只读权限用于分析)
#------------------------------------------------------------------------------

data "aws_iam_policy_document" "security_analysis_read" {
  statement {
    sid    = "S3ReadAnalysis"
    effect = "Allow"
    actions = [
      "s3:GetBucketPolicy",
      "s3:GetBucketPublicAccessBlock",
      "s3:GetBucketEncryption",
      "s3:GetBucketVersioning",
      "s3:GetBucketLogging",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "EC2ReadAnalysis"
    effect = "Allow"
    actions = [
      "ec2:DescribeSecurityGroups",
      "ec2:DescribeInstances",
      "ec2:DescribeVpcs",
      "ec2:DescribeSubnets",
      "ec2:DescribeNetworkInterfaces",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "IAMReadAnalysis"
    effect = "Allow"
    actions = [
      "iam:GetRole",
      "iam:GetPolicy",
      "iam:GetUser",
      "iam:ListMFADevices",
      "iam:ListAttachedRolePolicies",
      "iam:ListRolePolicies",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "ConfigReadAnalysis"
    effect = "Allow"
    actions = [
      "config:GetResourceConfigHistory",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "security_analysis_read" {
  name   = "security-analysis-read"
  role   = aws_iam_role.lambda_execution.id
  policy = data.aws_iam_policy_document.security_analysis_read.json
}

#------------------------------------------------------------------------------
# Lambda Self-Invoke Policy (for async processing)
#------------------------------------------------------------------------------

data "aws_iam_policy_document" "lambda_self_invoke" {
  statement {
    sid    = "LambdaSelfInvoke"
    effect = "Allow"
    actions = [
      "lambda:InvokeFunction",
    ]
    resources = [
      "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${local.name_prefix}-*",
    ]
  }
}

resource "aws_iam_role_policy" "lambda_self_invoke" {
  name   = "lambda-self-invoke"
  role   = aws_iam_role.lambda_execution.id
  policy = data.aws_iam_policy_document.lambda_self_invoke.json
}

#------------------------------------------------------------------------------
# X-Ray Tracing Policy
#------------------------------------------------------------------------------

resource "aws_iam_role_policy_attachment" "lambda_xray" {
  count = var.enable_xray_tracing ? 1 : 0

  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
}
