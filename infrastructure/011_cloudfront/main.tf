# ==============================================================================
# CloudFront Distribution (使用 CloudFront 默认域名，无自定义域名)
# ==============================================================================
# Origins:
#   - S3: 前端静态资源 (/)
#   - ALB: 后端 API (/api/*)
# ==============================================================================

locals {
  name_prefix    = "${var.project_name}-${var.environment}"
  s3_origin_id   = "S3-${var.s3_bucket_id}"
  alb_origin_id  = "ALB-api"
  has_alb_origin = var.alb_dns_name != null && var.alb_dns_name != ""
}

# ==============================================================================
# CloudFront OAC
# ==============================================================================

resource "aws_cloudfront_origin_access_control" "s3" {
  name                              = "${local.name_prefix}-s3-oac"
  description                       = "OAC for S3 origin"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# ==============================================================================
# CloudFront Distribution
# ==============================================================================

resource "aws_cloudfront_distribution" "main" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "${local.name_prefix} distribution"
  default_root_object = "index.html"
  price_class         = "PriceClass_200"
  http_version        = "http2and3"

  # 不使用自定义域名，使用 CloudFront 默认域名
  # aliases = []

  # ==============================================================================
  # S3 Origin (前端静态资源)
  # ==============================================================================

  origin {
    domain_name              = var.s3_bucket_domain_name
    origin_id                = local.s3_origin_id
    origin_access_control_id = aws_cloudfront_origin_access_control.s3.id
  }

  # ==============================================================================
  # ALB Origin (后端 API) - 当 ALB DNS 存在时创建
  # ==============================================================================

  dynamic "origin" {
    for_each = local.has_alb_origin ? [1] : []
    content {
      domain_name = var.alb_dns_name
      origin_id   = local.alb_origin_id

      custom_origin_config {
        http_port              = 80
        https_port             = 443
        origin_protocol_policy = "http-only" # ALB 未配置 HTTPS 证书时使用 HTTP
        origin_ssl_protocols   = ["TLSv1.2"]
      }

      # 自定义 Header (可选 - 用于验证请求来自 CloudFront)
      custom_header {
        name  = "X-CloudFront-Secret"
        value = "cloudfront-to-alb-${var.project_name}"
      }
    }
  }

  # ==============================================================================
  # Default Cache Behavior (S3 - 前端)
  # ==============================================================================

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = local.s3_origin_id

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 3600
    max_ttl                = 86400
    compress               = true
  }

  # ==============================================================================
  # API Cache Behavior (ALB - 后端) - 当 ALB DNS 存在时创建
  # ==============================================================================

  dynamic "ordered_cache_behavior" {
    for_each = local.has_alb_origin ? [1] : []
    content {
      path_pattern     = "/api/*"
      allowed_methods  = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
      cached_methods   = ["GET", "HEAD"]
      target_origin_id = local.alb_origin_id

      forwarded_values {
        query_string = true
        headers = [
          "Authorization",
          "Origin",
          "Accept",
          "Accept-Language",
          "Host",
          "X-Forwarded-For",
          "X-Forwarded-Proto"
        ]
        cookies {
          forward = "all"
        }
      }

      viewer_protocol_policy = "https-only"
      min_ttl                = 0
      default_ttl            = 0
      max_ttl                = 0
      compress               = true
    }
  }

  # ==============================================================================
  # Health Check Path (ALB - 健康检查)
  # ==============================================================================

  dynamic "ordered_cache_behavior" {
    for_each = local.has_alb_origin ? [1] : []
    content {
      path_pattern     = "/health*"
      allowed_methods  = ["GET", "HEAD", "OPTIONS"]
      cached_methods   = ["GET", "HEAD"]
      target_origin_id = local.alb_origin_id

      forwarded_values {
        query_string = false
        cookies {
          forward = "none"
        }
      }

      viewer_protocol_policy = "https-only"
      min_ttl                = 0
      default_ttl            = 0
      max_ttl                = 0
      compress               = false
    }
  }

  # ==============================================================================
  # Custom Error Responses (SPA 支持)
  # ==============================================================================

  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 300
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 300
  }

  # ==============================================================================
  # SSL/TLS 配置 (使用 CloudFront 默认证书)
  # ==============================================================================

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  # ==============================================================================
  # 地理位置限制
  # ==============================================================================

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # ==============================================================================
  # WAF 关联
  # ==============================================================================

  web_acl_id = var.waf_web_acl_arn

  tags = {
    Name = "${local.name_prefix}-cloudfront"
  }
}
