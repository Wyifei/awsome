###############################################################################
# EventBridge Rules
###############################################################################

#------------------------------------------------------------------------------
# Security Hub Finding Rule
# 仅触发 CRITICAL/HIGH 严重级别且状态为 NEW 的 Finding
#------------------------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "securityhub" {
  name        = "${local.name_prefix}-securityhub-critical-high"
  description = "Capture CRITICAL/HIGH severity Security Hub findings for auto-remediation"

  event_pattern = jsonencode({
    source      = ["aws.securityhub"]
    detail-type = ["Security Hub Findings - Imported"]
    detail = {
      findings = {
        Severity = {
          Label = ["CRITICAL", "HIGH"]
        }
        Workflow = {
          Status = ["NEW"]
        }
        RecordState = ["ACTIVE"]
      }
    }
  })

  tags = {
    Name = "${local.name_prefix}-securityhub-rule"
  }
}

#------------------------------------------------------------------------------
# EventBridge Target - Lambda
#------------------------------------------------------------------------------

resource "aws_cloudwatch_event_target" "securityhub" {
  rule      = aws_cloudwatch_event_rule.securityhub.name
  target_id = "event-handler"
  arn       = aws_lambda_function.event_handler.arn

  retry_policy {
    maximum_retry_attempts       = 2
    maximum_event_age_in_seconds = 3600
  }
}

#------------------------------------------------------------------------------
# Dead Letter Queue (Optional)
#------------------------------------------------------------------------------

resource "aws_sqs_queue" "eventbridge_dlq" {
  count = var.enable_dlq ? 1 : 0

  name                       = "${local.name_prefix}-eventbridge-dlq"
  message_retention_seconds  = 1209600 # 14 days
  visibility_timeout_seconds = 300

  tags = {
    Name = "${local.name_prefix}-eventbridge-dlq"
  }
}

resource "aws_sqs_queue_policy" "eventbridge_dlq" {
  count = var.enable_dlq ? 1 : 0

  queue_url = aws_sqs_queue.eventbridge_dlq[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "events.amazonaws.com"
      }
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.eventbridge_dlq[0].arn
      Condition = {
        ArnEquals = {
          "aws:SourceArn" = aws_cloudwatch_event_rule.securityhub.arn
        }
      }
    }]
  })
}
