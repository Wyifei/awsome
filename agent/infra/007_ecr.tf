###############################################################################
# ECR Resources - Container Registry for AgentCore Runtime
###############################################################################

#------------------------------------------------------------------------------
# ECR Repository for Analyzer Agent
#------------------------------------------------------------------------------

resource "aws_ecr_repository" "analyzer_agent" {
  name                 = "${local.name_prefix}-analyzer-agent"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name  = "${local.name_prefix}-analyzer-agent"
    Agent = "analyzer"
  }
}

resource "aws_ecr_lifecycle_policy" "analyzer_agent" {
  repository = aws_ecr_repository.analyzer_agent.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 1 images"
        selection = {
          tagStatus     = "any"
          countType     = "imageCountMoreThan"
          countNumber   = 1
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

#------------------------------------------------------------------------------
# ECR Repository for Remediator Agent
#------------------------------------------------------------------------------

resource "aws_ecr_repository" "remediator_agent" {
  name                 = "${local.name_prefix}-remediator-agent"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name  = "${local.name_prefix}-remediator-agent"
    Agent = "remediator"
  }
}

resource "aws_ecr_lifecycle_policy" "remediator_agent" {
  repository = aws_ecr_repository.remediator_agent.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus     = "any"
          countType     = "imageCountMoreThan"
          countNumber   = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

#------------------------------------------------------------------------------
# ECR Repository for Validator Agent
#------------------------------------------------------------------------------

resource "aws_ecr_repository" "validator_agent" {
  name                 = "${local.name_prefix}-validator-agent"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = {
    Name  = "${local.name_prefix}-validator-agent"
    Agent = "validator"
  }
}

resource "aws_ecr_lifecycle_policy" "validator_agent" {
  repository = aws_ecr_repository.validator_agent.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 10 images"
        selection = {
          tagStatus     = "any"
          countType     = "imageCountMoreThan"
          countNumber   = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

#------------------------------------------------------------------------------
# IAM Role for AgentCore Runtime Execution
#------------------------------------------------------------------------------

resource "aws_iam_role" "agentcore_runtime" {
  name = "${local.name_prefix}-agentcore-runtime"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = [
            "bedrock.amazonaws.com",
            "bedrock-agentcore.amazonaws.com"
          ]
        }
      }
    ]
  })

  tags = {
    Name = "${local.name_prefix}-agentcore-runtime"
  }
}

# ECR Pull Policy
resource "aws_iam_role_policy" "agentcore_ecr" {
  name = "${local.name_prefix}-agentcore-ecr"
  role = aws_iam_role.agentcore_runtime.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:BatchCheckLayerAvailability"
        ]
        Resource = [
          aws_ecr_repository.analyzer_agent.arn,
          aws_ecr_repository.remediator_agent.arn,
          aws_ecr_repository.validator_agent.arn
        ]
      },
      {
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      }
    ]
  })
}

# Bedrock Model Access Policy
resource "aws_iam_role_policy" "agentcore_bedrock" {
  name = "${local.name_prefix}-agentcore-bedrock"
  role = aws_iam_role.agentcore_runtime.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = [
          "arn:aws:bedrock:*:*:inference-profile/*",
          "arn:aws:bedrock:*::foundation-model/*"
        ]
      }
    ]
  })
}

# DynamoDB Access Policy
resource "aws_iam_role_policy" "agentcore_dynamodb" {
  name = "${local.name_prefix}-agentcore-dynamodb"
  role = aws_iam_role.agentcore_runtime.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.tasks.arn,
          "${aws_dynamodb_table.tasks.arn}/index/*",
          aws_dynamodb_table.tokens.arn,
          "${aws_dynamodb_table.tokens.arn}/index/*"
        ]
      }
    ]
  })
}

# S3 Access Policy
resource "aws_iam_role_policy" "agentcore_s3" {
  name = "${local.name_prefix}-agentcore-s3"
  role = aws_iam_role.agentcore_runtime.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ASRPlaybooksRead"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.asr_playbooks.arn,
          "${aws_s3_bucket.asr_playbooks.arn}/*"
        ]
      },
      {
        Sid    = "RemediationAuditWrite"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.remediation_audit.arn,
          "${aws_s3_bucket.remediation_audit.arn}/*"
        ]
      }
    ]
  })
}

# Security Hub Access Policy
resource "aws_iam_role_policy" "agentcore_securityhub" {
  name = "${local.name_prefix}-agentcore-securityhub"
  role = aws_iam_role.agentcore_runtime.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "securityhub:GetFindings",
          "securityhub:UpdateFindings",
          "securityhub:BatchUpdateFindings"
        ]
        Resource = "*"
      }
    ]
  })
}

# AgentCore Memory Access Policy
# IMPORTANT: AgentCore Memory uses bedrock-agentcore: namespace for Memory API
# but may also use bedrock: namespace for Knowledge Base retrieval internally
resource "aws_iam_role_policy" "agentcore_memory" {
  name = "${local.name_prefix}-agentcore-memory"
  role = aws_iam_role.agentcore_runtime.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AgentCoreMemoryAccess"
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:CreateEvent",
          "bedrock-agentcore:ListEvents",
          "bedrock-agentcore:GetMemory",
          "bedrock-agentcore:CreateSession",
          "bedrock-agentcore:DeleteSession",
          "bedrock-agentcore:GetSession",
          "bedrock-agentcore:ListSessions",
          "bedrock-agentcore:RetrieveMemory",
          "bedrock-agentcore:SearchMemory"
        ]
        Resource = "*"
      },
      {
        Sid    = "BedrockKnowledgeBaseAccess"
        Effect = "Allow"
        Action = [
          "bedrock:RetrieveAndGenerate",
          "bedrock:Retrieve"
        ]
        Resource = "*"
      }
    ]
  })
}

# CloudWatch Logs Policy
resource "aws_iam_role_policy" "agentcore_logs" {
  name = "${local.name_prefix}-agentcore-logs"
  role = aws_iam_role.agentcore_runtime.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/bedrock/agentcore/*"
      }
    ]
  })
}

# Agent-to-Agent Communication Policy (for Remediator -> Validator A2A calls)
# IMPORTANT: In AgentCore Runtime, agents must use InvokeAgentRuntime API for A2A communication
# Direct HTTP calls between agents are not supported in AgentCore Runtime
resource "aws_iam_role_policy" "agentcore_a2a" {
  name = "${local.name_prefix}-agentcore-a2a"
  role = aws_iam_role.agentcore_runtime.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeAgentRuntime"
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:InvokeAgentRuntime"
        ]
        Resource = "arn:aws:bedrock-agentcore:${local.region}:${local.account_id}:runtime/*"
      },
      {
        Sid    = "GetWorkloadAccessToken"
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:GetWorkloadAccessToken",
          "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
          "bedrock-agentcore:GetWorkloadAccessTokenForUserId"
        ]
        Resource = [
          "arn:aws:bedrock-agentcore:${local.region}:${local.account_id}:workload-identity-directory/default",
          "arn:aws:bedrock-agentcore:${local.region}:${local.account_id}:workload-identity-directory/default/workload-identity/*"
        ]
      }
    ]
  })
}

# Cloud Control API Policy (for resource verification)
resource "aws_iam_role_policy" "agentcore_cloudcontrol" {
  name = "${local.name_prefix}-agentcore-cloudcontrol"
  role = aws_iam_role.agentcore_runtime.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "cloudcontrol:GetResource",
          "cloudcontrol:ListResources"
        ]
        Resource = "*"
      }
    ]
  })
}

# ReadOnlyAccess for Cloud Control API resource queries
resource "aws_iam_role_policy_attachment" "agentcore_readonly" {
  role       = aws_iam_role.agentcore_runtime.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# Lambda Invoke Policy (for Validator Agent to send result emails)
resource "aws_iam_role_policy" "agentcore_lambda_invoke" {
  name = "${local.name_prefix}-agentcore-lambda-invoke"
  role = aws_iam_role.agentcore_runtime.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "LambdaInvoke"
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = [
          "arn:aws:lambda:${local.region}:${local.account_id}:function:${local.name_prefix}-*"
        ]
      }
    ]
  })
}

# AWS Resource Remediation Policy (for Remediator Agent)
resource "aws_iam_role_policy" "agentcore_remediation" {
  name = "${local.name_prefix}-agentcore-remediation"
  role = aws_iam_role.agentcore_runtime.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # S3 Remediation
      {
        Effect = "Allow"
        Action = [
          "s3:PutBucketPublicAccessBlock",
          "s3:PutBucketVersioning",
          "s3:PutEncryptionConfiguration",
          "s3:PutBucketLogging",
          "s3:GetBucketPublicAccessBlock",
          "s3:GetBucketVersioning",
          "s3:GetEncryptionConfiguration"
        ]
        Resource = "*"
      },
      # Security Group Remediation
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeSecurityGroups",
          "ec2:RevokeSecurityGroupIngress",
          "ec2:RevokeSecurityGroupEgress",
          "ec2:AuthorizeSecurityGroupIngress",
          "ec2:AuthorizeSecurityGroupEgress"
        ]
        Resource = "*"
      },
      # IAM Remediation
      {
        Effect = "Allow"
        Action = [
          "iam:UpdateAccountPasswordPolicy",
          "iam:GetAccountPasswordPolicy",
          "iam:GetRole",
          "iam:UpdateAssumeRolePolicy",
          "iam:PutRolePolicy",
          "iam:DeleteRolePolicy"
        ]
        Resource = "*"
      },
      # RDS Remediation
      {
        Effect = "Allow"
        Action = [
          "rds:DescribeDBInstances",
          "rds:ModifyDBInstance",
          "rds:DescribeDBClusters",
          "rds:ModifyDBCluster"
        ]
        Resource = "*"
      },
      # EBS Remediation
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeVolumes",
          "ec2:ModifyVolume",
          "ec2:EnableEbsEncryptionByDefault"
        ]
        Resource = "*"
      },
      # CloudTrail Remediation
      {
        Effect = "Allow"
        Action = [
          "cloudtrail:DescribeTrails",
          "cloudtrail:UpdateTrail",
          "cloudtrail:StartLogging"
        ]
        Resource = "*"
      }
    ]
  })
}

# Code Interpreter Policy (for Remediator Agent to execute code in sandbox)
# IMPORTANT: These permissions are required for the Remediator agent to execute
# remediation code securely. Without these, the agent will silently fail.
resource "aws_iam_role_policy" "agentcore_code_interpreter" {
  name = "${local.name_prefix}-agentcore-code-interpreter"
  role = aws_iam_role.agentcore_runtime.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CodeInterpreterFullAccess"
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:CreateCodeInterpreter",
          "bedrock-agentcore:StartCodeInterpreterSession",
          "bedrock-agentcore:InvokeCodeInterpreter",
          "bedrock-agentcore:StopCodeInterpreterSession",
          "bedrock-agentcore:DeleteCodeInterpreter",
          "bedrock-agentcore:ListCodeInterpreters",
          "bedrock-agentcore:GetCodeInterpreter",
          "bedrock-agentcore:GetCodeInterpreterSession",
          "bedrock-agentcore:ListCodeInterpreterSessions"
        ]
        Resource = "*"
      }
    ]
  })
}
