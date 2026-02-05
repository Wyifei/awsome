###############################################################################
# Lambda Functions
###############################################################################

#------------------------------------------------------------------------------
# Lambda Security Group
#------------------------------------------------------------------------------

resource "aws_security_group" "lambda" {
  name        = "${local.name_prefix}-lambda-sg"
  description = "Security group for SHARA Lambda functions"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound traffic"
  }

  tags = {
    Name = "${local.name_prefix}-lambda-sg"
  }
}

#------------------------------------------------------------------------------
# Lambda Code Packaging
#------------------------------------------------------------------------------

# Event Handler Lambda package
data "archive_file" "event_handler" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/event_handler"
  output_path = "${path.module}/.terraform/tmp/event_handler.zip"
}

# Approval Handler Lambda package
data "archive_file" "approval_handler" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/approval_handler"
  output_path = "${path.module}/.terraform/tmp/approval_handler.zip"
}

#------------------------------------------------------------------------------
# CloudWatch Log Groups
#------------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "event_handler" {
  name              = "/aws/lambda/${local.name_prefix}-event-handler"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${local.name_prefix}-event-handler-logs"
  }
}

resource "aws_cloudwatch_log_group" "approval_handler" {
  name              = "/aws/lambda/${local.name_prefix}-approval-handler"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${local.name_prefix}-approval-handler-logs"
  }
}

#------------------------------------------------------------------------------
# Event Handler Lambda
#------------------------------------------------------------------------------

resource "aws_lambda_function" "event_handler" {
  function_name = "${local.name_prefix}-event-handler"
  description   = "Handles Security Hub events and triggers remediation workflow"

  filename         = data.archive_file.event_handler.output_path
  source_code_hash = data.archive_file.event_handler.output_base64sha256
  handler          = "handler.lambda_handler"
  runtime          = var.lambda_runtime

  role        = aws_iam_role.lambda_execution.arn
  timeout     = var.event_handler_timeout
  memory_size = var.event_handler_memory

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      TASKS_TABLE            = aws_dynamodb_table.tasks.name
      TOKENS_TABLE           = aws_dynamodb_table.tokens.name
      ASR_PLAYBOOKS_BUCKET   = aws_s3_bucket.asr_playbooks.id
      AGENTCORE_MEMORY_ID    = var.agentcore_memory_id
      ANALYZER_RUNTIME_ARN   = var.analyzer_runtime_arn
      APPROVAL_EMAIL         = var.approval_email
      SENDER_EMAIL           = var.sender_email
      API_GATEWAY_URL        = "https://${aws_api_gateway_rest_api.main.id}.execute-api.${local.region}.amazonaws.com/${var.stage}/"
      APPROVAL_EXPIRY_HOURS  = tostring(var.approval_expiry_hours)
      STAGE                  = var.stage
      LOG_LEVEL              = var.stage == "prod" ? "INFO" : "DEBUG"
      # GitHub 配置 (容器漏洞修复)
      GITHUB_OWNER           = var.github_owner
      GITHUB_REPO            = var.github_repo
    }
  }

  tracing_config {
    mode = var.enable_xray_tracing ? "Active" : "PassThrough"
  }

  depends_on = [
    aws_cloudwatch_log_group.event_handler,
    aws_iam_role_policy.dynamodb_access,
    aws_iam_role_policy.s3_asr_playbooks_access,
  ]

  tags = {
    Name = "${local.name_prefix}-event-handler"
  }
}

#------------------------------------------------------------------------------
# Approval Handler Lambda
#------------------------------------------------------------------------------

resource "aws_lambda_function" "approval_handler" {
  function_name = "${local.name_prefix}-approval-handler"
  description   = "Handles approval callbacks and executes remediation"

  filename         = data.archive_file.approval_handler.output_path
  source_code_hash = data.archive_file.approval_handler.output_base64sha256
  handler          = "handler.lambda_handler"
  runtime          = var.lambda_runtime

  role        = aws_iam_role.lambda_execution.arn
  timeout     = var.approval_handler_timeout
  memory_size = var.approval_handler_memory

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      TASKS_TABLE              = aws_dynamodb_table.tasks.name
      TOKENS_TABLE             = aws_dynamodb_table.tokens.name
      ASR_PLAYBOOKS_BUCKET     = aws_s3_bucket.asr_playbooks.id
      AGENTCORE_MEMORY_ID      = var.agentcore_memory_id
      REMEDIATOR_RUNTIME_ARN   = var.remediator_runtime_arn
      STAGE                    = var.stage
      LOG_LEVEL                = var.stage == "prod" ? "INFO" : "DEBUG"
      # Email Configuration
      SENDER_EMAIL             = var.sender_email
      RESULT_EMAIL             = coalesce(var.result_email, var.approval_email)
      API_GATEWAY_URL          = "https://${aws_api_gateway_rest_api.main.id}.execute-api.${var.aws_region}.amazonaws.com/${var.stage}/"
      # GitHub 配置 (容器漏洞修复)
      GITHUB_OWNER             = var.github_owner
      GITHUB_REPO              = var.github_repo
    }
  }

  tracing_config {
    mode = var.enable_xray_tracing ? "Active" : "PassThrough"
  }

  depends_on = [
    aws_cloudwatch_log_group.approval_handler,
    aws_iam_role_policy.dynamodb_access,
    aws_iam_role_policy.s3_asr_playbooks_access,
  ]

  tags = {
    Name = "${local.name_prefix}-approval-handler"
  }
}

#------------------------------------------------------------------------------
# Lambda Permissions for EventBridge
#------------------------------------------------------------------------------

resource "aws_lambda_permission" "eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.event_handler.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.securityhub.arn
}

#------------------------------------------------------------------------------
# Lambda Permissions for API Gateway
#------------------------------------------------------------------------------

resource "aws_lambda_permission" "api_gateway_event_handler" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.event_handler.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

resource "aws_lambda_permission" "api_gateway_approval_handler" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.approval_handler.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}
