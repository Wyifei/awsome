###############################################################################
# API Gateway
###############################################################################

#------------------------------------------------------------------------------
# REST API
#------------------------------------------------------------------------------

resource "aws_api_gateway_rest_api" "main" {
  name        = "${local.name_prefix}-api"
  description = "SHARA Security Hub Auto-Remediation API"

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = {
    Name = "${local.name_prefix}-api"
  }
}

#------------------------------------------------------------------------------
# CloudWatch Log Group for API Gateway
#------------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = "/aws/apigateway/${local.name_prefix}"
  retention_in_days = var.log_retention_days

  tags = {
    Name = "${local.name_prefix}-api-logs"
  }
}

#------------------------------------------------------------------------------
# /api Resource (API 前缀)
#------------------------------------------------------------------------------

resource "aws_api_gateway_resource" "api" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "api"
}

resource "aws_api_gateway_resource" "v1" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.api.id
  path_part   = "v1"
}

#------------------------------------------------------------------------------
# /api/v1/approvals - 审批回调 API (Token-based 认证)
#------------------------------------------------------------------------------

resource "aws_api_gateway_resource" "approvals" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.v1.id
  path_part   = "approvals"
}

# /api/v1/approvals/{taskId}
resource "aws_api_gateway_resource" "approval_task" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.approvals.id
  path_part   = "{taskId}"
}

# /api/v1/approvals/{taskId}/respond
resource "aws_api_gateway_resource" "approval_respond" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.approval_task.id
  path_part   = "respond"
}

# POST /api/v1/approvals/{taskId}/respond - 审批响应
resource "aws_api_gateway_method" "approval_respond_post" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.approval_respond.id
  http_method   = "POST"
  authorization = "NONE"

  request_parameters = {
    "method.request.path.taskId"           = true
    "method.request.querystring.token"     = true
    "method.request.querystring.action"    = true
  }
}

resource "aws_api_gateway_integration" "approval_respond_post" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.approval_respond.id
  http_method             = aws_api_gateway_method.approval_respond_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.approval_handler.invoke_arn
}

# GET /api/v1/approvals/{taskId}/respond - 邮件链接点击 (简化审批)
resource "aws_api_gateway_method" "approval_respond_get" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.approval_respond.id
  http_method   = "GET"
  authorization = "NONE"

  request_parameters = {
    "method.request.path.taskId"           = true
    "method.request.querystring.token"     = true
    "method.request.querystring.action"    = true
  }
}

resource "aws_api_gateway_integration" "approval_respond_get" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.approval_respond.id
  http_method             = aws_api_gateway_method.approval_respond_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.approval_handler.invoke_arn
}

# /api/v1/approvals/{taskId}/status
resource "aws_api_gateway_resource" "approval_status" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.approval_task.id
  path_part   = "status"
}

# GET /api/v1/approvals/{taskId}/status - 获取审批状态
resource "aws_api_gateway_method" "approval_status_get" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.approval_status.id
  http_method   = "GET"
  authorization = "NONE"

  request_parameters = {
    "method.request.path.taskId"        = true
    "method.request.querystring.token"  = true
  }
}

resource "aws_api_gateway_integration" "approval_status_get" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.approval_status.id
  http_method             = aws_api_gateway_method.approval_status_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.approval_handler.invoke_arn
}

#------------------------------------------------------------------------------
# /api/v1/admin - 管理 API (IAM 认证)
#------------------------------------------------------------------------------

resource "aws_api_gateway_resource" "admin" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.v1.id
  path_part   = "admin"
}

# /api/v1/admin/tasks
resource "aws_api_gateway_resource" "admin_tasks" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.admin.id
  path_part   = "tasks"
}

# GET /api/v1/admin/tasks - 任务列表
resource "aws_api_gateway_method" "admin_tasks_get" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.admin_tasks.id
  http_method   = "GET"
  authorization = "AWS_IAM"

  request_parameters = {
    "method.request.querystring.status"    = false
    "method.request.querystring.severity"  = false
    "method.request.querystring.startDate" = false
    "method.request.querystring.endDate"   = false
    "method.request.querystring.limit"     = false
    "method.request.querystring.nextToken" = false
  }
}

resource "aws_api_gateway_integration" "admin_tasks_get" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.admin_tasks.id
  http_method             = aws_api_gateway_method.admin_tasks_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.event_handler.invoke_arn
}

# POST /api/v1/admin/tasks - 手动创建任务
resource "aws_api_gateway_method" "admin_tasks_post" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.admin_tasks.id
  http_method   = "POST"
  authorization = "AWS_IAM"
}

resource "aws_api_gateway_integration" "admin_tasks_post" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.admin_tasks.id
  http_method             = aws_api_gateway_method.admin_tasks_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.event_handler.invoke_arn
}

# /api/v1/admin/tasks/{taskId}
resource "aws_api_gateway_resource" "admin_task" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.admin_tasks.id
  path_part   = "{taskId}"
}

# GET /api/v1/admin/tasks/{taskId} - 任务详情
resource "aws_api_gateway_method" "admin_task_get" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.admin_task.id
  http_method   = "GET"
  authorization = "AWS_IAM"

  request_parameters = {
    "method.request.path.taskId" = true
  }
}

resource "aws_api_gateway_integration" "admin_task_get" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.admin_task.id
  http_method             = aws_api_gateway_method.admin_task_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.event_handler.invoke_arn
}

# /api/v1/admin/tasks/{taskId}/retry
resource "aws_api_gateway_resource" "admin_task_retry" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.admin_task.id
  path_part   = "retry"
}

# POST /api/v1/admin/tasks/{taskId}/retry - 重试任务
resource "aws_api_gateway_method" "admin_task_retry_post" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.admin_task_retry.id
  http_method   = "POST"
  authorization = "AWS_IAM"

  request_parameters = {
    "method.request.path.taskId" = true
  }
}

resource "aws_api_gateway_integration" "admin_task_retry_post" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.admin_task_retry.id
  http_method             = aws_api_gateway_method.admin_task_retry_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.event_handler.invoke_arn
}

# /api/v1/admin/tasks/{taskId}/cancel
resource "aws_api_gateway_resource" "admin_task_cancel" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.admin_task.id
  path_part   = "cancel"
}

# POST /api/v1/admin/tasks/{taskId}/cancel - 取消任务
resource "aws_api_gateway_method" "admin_task_cancel_post" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.admin_task_cancel.id
  http_method   = "POST"
  authorization = "AWS_IAM"

  request_parameters = {
    "method.request.path.taskId" = true
  }
}

resource "aws_api_gateway_integration" "admin_task_cancel_post" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.admin_task_cancel.id
  http_method             = aws_api_gateway_method.admin_task_cancel_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.event_handler.invoke_arn
}

# /api/v1/admin/statistics
resource "aws_api_gateway_resource" "admin_statistics" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.admin.id
  path_part   = "statistics"
}

# GET /api/v1/admin/statistics - 统计数据
resource "aws_api_gateway_method" "admin_statistics_get" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.admin_statistics.id
  http_method   = "GET"
  authorization = "AWS_IAM"

  request_parameters = {
    "method.request.querystring.period" = false
  }
}

resource "aws_api_gateway_integration" "admin_statistics_get" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.admin_statistics.id
  http_method             = aws_api_gateway_method.admin_statistics_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.event_handler.invoke_arn
}

#------------------------------------------------------------------------------
# /health Resource (健康检查，无认证)
#------------------------------------------------------------------------------

resource "aws_api_gateway_resource" "health" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "health"
}

# GET /health - Health check
resource "aws_api_gateway_method" "health_get" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.health.id
  http_method   = "GET"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "health_get" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.health.id
  http_method = aws_api_gateway_method.health_get.http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "health_get_200" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.health.id
  http_method = aws_api_gateway_method.health_get.http_method
  status_code = "200"

  response_models = {
    "application/json" = "Empty"
  }
}

resource "aws_api_gateway_integration_response" "health_get" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.health.id
  http_method = aws_api_gateway_method.health_get.http_method
  status_code = aws_api_gateway_method_response.health_get_200.status_code

  response_templates = {
    "application/json" = "{\"status\": \"healthy\", \"service\": \"shara\"}"
  }

  depends_on = [aws_api_gateway_integration.health_get]
}

#------------------------------------------------------------------------------
# CORS Configuration
#------------------------------------------------------------------------------

# Enable CORS for /api/v1/approvals/{taskId}/respond
module "cors_approval_respond" {
  source = "./modules/cors"

  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.approval_respond.id
}

# Enable CORS for /api/v1/approvals/{taskId}/status
module "cors_approval_status" {
  source = "./modules/cors"

  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.approval_status.id
}

# Enable CORS for /api/v1/admin/tasks
module "cors_admin_tasks" {
  source = "./modules/cors"

  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.admin_tasks.id
}

# Enable CORS for /api/v1/admin/tasks/{taskId}
module "cors_admin_task" {
  source = "./modules/cors"

  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.admin_task.id
}

# Enable CORS for /api/v1/admin/statistics
module "cors_admin_statistics" {
  source = "./modules/cors"

  rest_api_id = aws_api_gateway_rest_api.main.id
  resource_id = aws_api_gateway_resource.admin_statistics.id
}

#------------------------------------------------------------------------------
# Deployment
#------------------------------------------------------------------------------

resource "aws_api_gateway_deployment" "main" {
  rest_api_id = aws_api_gateway_rest_api.main.id

  triggers = {
    redeployment = sha1(jsonencode([
      # API structure
      aws_api_gateway_resource.api.id,
      aws_api_gateway_resource.v1.id,
      # Approvals API
      aws_api_gateway_resource.approvals.id,
      aws_api_gateway_resource.approval_task.id,
      aws_api_gateway_resource.approval_respond.id,
      aws_api_gateway_resource.approval_status.id,
      aws_api_gateway_method.approval_respond_post.id,
      aws_api_gateway_method.approval_respond_get.id,
      aws_api_gateway_method.approval_status_get.id,
      aws_api_gateway_integration.approval_respond_post.id,
      aws_api_gateway_integration.approval_respond_get.id,
      aws_api_gateway_integration.approval_status_get.id,
      # Admin API
      aws_api_gateway_resource.admin.id,
      aws_api_gateway_resource.admin_tasks.id,
      aws_api_gateway_resource.admin_task.id,
      aws_api_gateway_resource.admin_task_retry.id,
      aws_api_gateway_resource.admin_task_cancel.id,
      aws_api_gateway_resource.admin_statistics.id,
      aws_api_gateway_method.admin_tasks_get.id,
      aws_api_gateway_method.admin_tasks_post.id,
      aws_api_gateway_method.admin_task_get.id,
      aws_api_gateway_method.admin_task_retry_post.id,
      aws_api_gateway_method.admin_task_cancel_post.id,
      aws_api_gateway_method.admin_statistics_get.id,
      aws_api_gateway_integration.admin_tasks_get.id,
      aws_api_gateway_integration.admin_tasks_post.id,
      aws_api_gateway_integration.admin_task_get.id,
      aws_api_gateway_integration.admin_task_retry_post.id,
      aws_api_gateway_integration.admin_task_cancel_post.id,
      aws_api_gateway_integration.admin_statistics_get.id,
      # Health
      aws_api_gateway_resource.health.id,
      aws_api_gateway_method.health_get.id,
      aws_api_gateway_integration.health_get.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_api_gateway_stage" "main" {
  deployment_id = aws_api_gateway_deployment.main.id
  rest_api_id   = aws_api_gateway_rest_api.main.id
  stage_name    = var.stage

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      requestId         = "$context.requestId"
      ip                = "$context.identity.sourceIp"
      caller            = "$context.identity.caller"
      user              = "$context.identity.user"
      requestTime       = "$context.requestTime"
      httpMethod        = "$context.httpMethod"
      resourcePath      = "$context.resourcePath"
      status            = "$context.status"
      protocol          = "$context.protocol"
      responseLength    = "$context.responseLength"
      integrationStatus = "$context.integrationStatus"
    })
  }

  xray_tracing_enabled = var.enable_xray_tracing

  tags = {
    Name = "${local.name_prefix}-api-stage"
  }
}

#------------------------------------------------------------------------------
# API Gateway Account Settings (for CloudWatch logging)
#------------------------------------------------------------------------------

resource "aws_api_gateway_account" "main" {
  cloudwatch_role_arn = aws_iam_role.api_gateway_cloudwatch.arn
}

resource "aws_iam_role" "api_gateway_cloudwatch" {
  name = "${local.name_prefix}-api-gateway-cloudwatch"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "apigateway.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "api_gateway_cloudwatch" {
  role       = aws_iam_role.api_gateway_cloudwatch.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs"
}
