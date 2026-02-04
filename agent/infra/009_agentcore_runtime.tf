###############################################################################
# AgentCore Runtime Configuration
###############################################################################

#------------------------------------------------------------------------------
# Security Group for AgentCore Runtime
#------------------------------------------------------------------------------

resource "aws_security_group" "agentcore_runtime" {
  name        = "${local.name_prefix}-agentcore-runtime-sg"
  description = "Security group for AgentCore Runtime - allows outbound access to SES"
  vpc_id      = aws_vpc.main.id

  # No inbound rules needed - AgentCore invocations don't go through VPC
  # VPC connectivity only affects outbound traffic from the runtime

  # Outbound: Allow all traffic
  # Runtime needs to access:
  # - VPC Endpoints (Bedrock Runtime, SES, DynamoDB, S3, CloudWatch Logs, etc.)
  # - External services via NAT Gateway (if needed)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound traffic"
  }

  tags = {
    Name = "${local.name_prefix}-agentcore-runtime-sg"
  }
}

#------------------------------------------------------------------------------
# Update VPC Endpoints Security Group to allow inbound from AgentCore Runtime
#------------------------------------------------------------------------------

resource "aws_security_group_rule" "vpc_endpoints_from_agentcore_runtime_https" {
  count = var.enable_vpc_endpoints ? 1 : 0

  type                     = "ingress"
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.agentcore_runtime.id
  security_group_id        = aws_security_group.vpc_endpoints[0].id
  description              = "HTTPS from AgentCore Runtime"
}

resource "aws_security_group_rule" "vpc_endpoints_from_agentcore_runtime_smtp" {
  count = var.enable_vpc_endpoints ? 1 : 0

  type                     = "ingress"
  from_port                = 587
  to_port                  = 587
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.agentcore_runtime.id
  security_group_id        = aws_security_group.vpc_endpoints[0].id
  description              = "SMTP TLS from AgentCore Runtime"
}

resource "aws_security_group_rule" "vpc_endpoints_from_agentcore_runtime_smtps" {
  count = var.enable_vpc_endpoints ? 1 : 0

  type                     = "ingress"
  from_port                = 465
  to_port                  = 465
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.agentcore_runtime.id
  security_group_id        = aws_security_group.vpc_endpoints[0].id
  description              = "SMTPS from AgentCore Runtime"
}
