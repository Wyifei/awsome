# ==============================================================================
# Amazon Cognito User Pool
# ==============================================================================

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

# ==============================================================================
# SES Email Identity
# ==============================================================================

resource "aws_ses_email_identity" "main" {
  email = var.ses_email_address
}

# ==============================================================================
# Cognito User Pool
# ==============================================================================

resource "aws_cognito_user_pool" "main" {
  name = var.user_pool_name

  # 登录配置
  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  # 密码策略
  password_policy {
    minimum_length                   = 8
    require_lowercase                = true
    require_uppercase                = true
    require_numbers                  = true
    require_symbols                  = false
    temporary_password_validity_days = 7
  }

  # MFA 配置
  mfa_configuration = "OPTIONAL"

  software_token_mfa_configuration {
    enabled = true
  }

  # 账户恢复设置
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # 用户属性模式
  schema {
    name                     = "email"
    attribute_data_type      = "String"
    required                 = true
    mutable                  = true
    developer_only_attribute = false

    string_attribute_constraints {
      min_length = 0
      max_length = 255
    }
  }

  schema {
    name                     = "given_name"
    attribute_data_type      = "String"
    required                 = false
    mutable                  = true
    developer_only_attribute = false

    string_attribute_constraints {
      min_length = 0
      max_length = 100
    }
  }

  schema {
    name                     = "family_name"
    attribute_data_type      = "String"
    required                 = false
    mutable                  = true
    developer_only_attribute = false

    string_attribute_constraints {
      min_length = 0
      max_length = 100
    }
  }

  schema {
    name                     = "user_type"
    attribute_data_type      = "String"
    required                 = false
    mutable                  = true
    developer_only_attribute = false

    string_attribute_constraints {
      min_length = 0
      max_length = 50
    }
  }

  # 邮件配置 (使用 SES)
  email_configuration {
    email_sending_account = "DEVELOPER"
    source_arn            = aws_ses_email_identity.main.arn
    from_email_address    = var.ses_email_address
  }

  # 验证消息模板
  verification_message_template {
    default_email_option  = "CONFIRM_WITH_CODE"
    email_subject         = "您的验证码"
    email_message         = "您的验证码是 {####}"
    email_subject_by_link = "验证您的邮箱"
    email_message_by_link = "请点击链接验证您的邮箱: {##Click Here##}"
  }

  # 用户池 Add-ons
  user_pool_add_ons {
    advanced_security_mode = "AUDIT"
  }

  # 管理员创建用户配置
  admin_create_user_config {
    allow_admin_create_user_only = false

    invite_message_template {
      email_subject = "欢迎注册"
      email_message = "您的用户名是 {username}，临时密码是 {####}"
      sms_message   = "您的用户名是 {username}，临时密码是 {####}"
    }
  }

  tags = {
    Name = "${local.name_prefix}-user-pool"
  }
}

# ==============================================================================
# Cognito User Pool Client (Web App)
# ==============================================================================

resource "aws_cognito_user_pool_client" "web" {
  name         = "web-app"
  user_pool_id = aws_cognito_user_pool.main.id

  # 不生成 Client Secret (公开客户端)
  generate_secret = false

  # 认证流程
  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_CUSTOM_AUTH"
  ]

  # OAuth 配置
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "profile", "email"]
  allowed_oauth_flows_user_pool_client = true
  supported_identity_providers         = ["COGNITO"]

  # 回调 URL (使用 CloudFront 域名)
  callback_urls = var.callback_urls
  logout_urls   = var.logout_urls

  # Token 有效期
  access_token_validity  = 1  # 小时
  id_token_validity      = 1  # 小时
  refresh_token_validity = 30 # 天

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  # 防止 Token 撤销
  enable_token_revocation = true

  # 读写属性
  read_attributes = [
    "email",
    "email_verified",
    "given_name",
    "family_name",
    "custom:user_type"
  ]

  write_attributes = [
    "email",
    "given_name",
    "family_name",
    "custom:user_type"
  ]
}

# ==============================================================================
# Cognito User Pool Domain (使用 Cognito 默认域名，无需证书)
# ==============================================================================

resource "random_string" "cognito_domain_suffix" {
  length  = 8
  special = false
  upper   = false
}

resource "aws_cognito_user_pool_domain" "main" {
  domain       = "${var.project_name}-${var.environment}-${random_string.cognito_domain_suffix.result}"
  user_pool_id = aws_cognito_user_pool.main.id
}

# ==============================================================================
# Cognito Resource Server (可选，用于自定义 scopes)
# ==============================================================================

resource "aws_cognito_resource_server" "api" {
  identifier   = "api"
  name         = "API Resource Server"
  user_pool_id = aws_cognito_user_pool.main.id

  scope {
    scope_name        = "read"
    scope_description = "Read access to API"
  }

  scope {
    scope_name        = "write"
    scope_description = "Write access to API"
  }

  scope {
    scope_name        = "admin"
    scope_description = "Admin access to API"
  }
}
