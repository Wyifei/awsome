# ==============================================================================
# 安全组
# ==============================================================================

locals {
  name_prefix = "${var.project_name}-${var.environment}"
}

# ==============================================================================
# ALB 安全组
# ==============================================================================

resource "aws_security_group" "alb" {
  name        = "${local.name_prefix}-alb-sg"
  description = "Security group for Application Load Balancer"
  vpc_id      = var.vpc_id

  # CloudFront IP 范围 (使用 AWS managed prefix list)
  ingress {
    description = "HTTPS from CloudFront"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # 实际生产中应限制为 CloudFront IP
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.name_prefix}-alb-sg"
  }
}

# ==============================================================================
# EKS Control Plane 安全组
# ==============================================================================

resource "aws_security_group" "eks_control_plane" {
  name        = "${local.name_prefix}-eks-control-sg"
  description = "Security group for EKS control plane"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.name_prefix}-eks-control-sg"
  }
}

# ==============================================================================
# EKS Worker 安全组
# ==============================================================================

resource "aws_security_group" "eks_worker" {
  name        = "${local.name_prefix}-eks-worker-sg"
  description = "Security group for EKS worker nodes"
  vpc_id      = var.vpc_id

  # Kubelet API from control plane
  ingress {
    description     = "Kubelet API from control plane"
    from_port       = 10250
    to_port         = 10250
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_control_plane.id]
  }

  # NodePort services from ALB
  ingress {
    description     = "NodePort services from ALB"
    from_port       = 30000
    to_port         = 32767
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  # Worker to worker communication
  ingress {
    description = "Worker to worker communication"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
  }

  # Control plane to worker
  ingress {
    description     = "Control plane to worker"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_control_plane.id]
  }

  # CoreDNS (UDP)
  ingress {
    description = "CoreDNS UDP"
    from_port   = 53
    to_port     = 53
    protocol    = "udp"
    self        = true
  }

  # CoreDNS (TCP)
  ingress {
    description = "CoreDNS TCP"
    from_port   = 53
    to_port     = 53
    protocol    = "tcp"
    self        = true
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.name_prefix}-eks-worker-sg"
  }
}

# Control plane to worker ingress rule
resource "aws_security_group_rule" "eks_control_to_worker" {
  type                     = "egress"
  from_port                = 1025
  to_port                  = 65535
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.eks_worker.id
  security_group_id        = aws_security_group.eks_control_plane.id
  description              = "Control plane to worker nodes"
}

# Worker to control plane ingress rule
resource "aws_security_group_rule" "eks_worker_to_control" {
  type                     = "ingress"
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  source_security_group_id = aws_security_group.eks_worker.id
  security_group_id        = aws_security_group.eks_control_plane.id
  description              = "Worker nodes to control plane"
}

# ==============================================================================
# Aurora 安全组
# ==============================================================================

resource "aws_security_group" "aurora" {
  name        = "${local.name_prefix}-aurora-sg"
  description = "Security group for Aurora PostgreSQL"
  vpc_id      = var.vpc_id

  # PostgreSQL from EKS workers
  ingress {
    description     = "PostgreSQL from EKS workers"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_worker.id]
  }

  # PostgreSQL from VPC (CloudShell VPC 环境、Bastion、调试等)
  ingress {
    description = "PostgreSQL from VPC"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.name_prefix}-aurora-sg"
  }
}
