###############################################################################
# Outputs
###############################################################################

#------------------------------------------------------------------------------
# VPC
#------------------------------------------------------------------------------

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "vpc_cidr" {
  description = "VPC CIDR block"
  value       = aws_vpc.main.cidr_block
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = aws_subnet.private[*].id
}

#------------------------------------------------------------------------------
# DynamoDB
#------------------------------------------------------------------------------

output "tasks_table_name" {
  description = "Tasks DynamoDB table name"
  value       = aws_dynamodb_table.tasks.name
}

output "tasks_table_arn" {
  description = "Tasks DynamoDB table ARN"
  value       = aws_dynamodb_table.tasks.arn
}

output "tokens_table_name" {
  description = "Tokens DynamoDB table name"
  value       = aws_dynamodb_table.tokens.name
}

#------------------------------------------------------------------------------
# S3
#------------------------------------------------------------------------------

output "asr_playbooks_bucket_name" {
  description = "ASR Playbooks S3 bucket name"
  value       = aws_s3_bucket.asr_playbooks.id
}

output "asr_playbooks_bucket_arn" {
  description = "ASR Playbooks S3 bucket ARN"
  value       = aws_s3_bucket.asr_playbooks.arn
}

output "remediation_audit_bucket_name" {
  description = "Remediation Audit S3 bucket name"
  value       = aws_s3_bucket.remediation_audit.id
}

output "remediation_audit_bucket_arn" {
  description = "Remediation Audit S3 bucket ARN"
  value       = aws_s3_bucket.remediation_audit.arn
}

#------------------------------------------------------------------------------
# Lambda
#------------------------------------------------------------------------------

output "event_handler_function_name" {
  description = "Event handler Lambda function name"
  value       = aws_lambda_function.event_handler.function_name
}

output "event_handler_function_arn" {
  description = "Event handler Lambda function ARN"
  value       = aws_lambda_function.event_handler.arn
}

output "approval_handler_function_name" {
  description = "Approval handler Lambda function name"
  value       = aws_lambda_function.approval_handler.function_name
}

output "approval_handler_function_arn" {
  description = "Approval handler Lambda function ARN"
  value       = aws_lambda_function.approval_handler.arn
}

output "lambda_execution_role_arn" {
  description = "Lambda execution role ARN"
  value       = aws_iam_role.lambda_execution.arn
}

#------------------------------------------------------------------------------
# API Gateway
#------------------------------------------------------------------------------

output "api_gateway_id" {
  description = "API Gateway REST API ID"
  value       = aws_api_gateway_rest_api.main.id
}

output "api_gateway_url" {
  description = "API Gateway invoke URL"
  value       = aws_api_gateway_stage.main.invoke_url
}

output "api_gateway_stage_name" {
  description = "API Gateway stage name"
  value       = aws_api_gateway_stage.main.stage_name
}

output "tasks_endpoint" {
  description = "Tasks API endpoint"
  value       = "${aws_api_gateway_stage.main.invoke_url}tasks"
}

output "approve_endpoint" {
  description = "Approval API endpoint"
  value       = "${aws_api_gateway_stage.main.invoke_url}approve"
}

output "health_endpoint" {
  description = "Health check API endpoint"
  value       = "${aws_api_gateway_stage.main.invoke_url}health"
}

#------------------------------------------------------------------------------
# EventBridge
#------------------------------------------------------------------------------

output "securityhub_rule_name" {
  description = "Security Hub EventBridge rule name"
  value       = aws_cloudwatch_event_rule.securityhub.name
}

output "securityhub_rule_arn" {
  description = "Security Hub EventBridge rule ARN"
  value       = aws_cloudwatch_event_rule.securityhub.arn
}

#------------------------------------------------------------------------------
# ECR
#------------------------------------------------------------------------------

output "analyzer_agent_ecr_url" {
  description = "Analyzer Agent ECR repository URL"
  value       = aws_ecr_repository.analyzer_agent.repository_url
}

output "remediator_agent_ecr_url" {
  description = "Remediator Agent ECR repository URL"
  value       = aws_ecr_repository.remediator_agent.repository_url
}

output "validator_agent_ecr_url" {
  description = "Validator Agent ECR repository URL"
  value       = aws_ecr_repository.validator_agent.repository_url
}

output "agentcore_runtime_role_arn" {
  description = "AgentCore Runtime IAM role ARN"
  value       = aws_iam_role.agentcore_runtime.arn
}

#------------------------------------------------------------------------------
# AgentCore Configuration
#------------------------------------------------------------------------------

output "agentcore_memory_id" {
  description = "AgentCore Memory ID for session management"
  value       = var.agentcore_memory_id
}

#------------------------------------------------------------------------------
# AgentCore Runtime Security Group
#------------------------------------------------------------------------------

output "agentcore_runtime_security_group_id" {
  description = "Security Group ID for AgentCore Runtime (VPC mode)"
  value       = aws_security_group.agentcore_runtime.id
}

output "agentcore_runtime_security_group_name" {
  description = "Security Group name for AgentCore Runtime"
  value       = aws_security_group.agentcore_runtime.name
}
