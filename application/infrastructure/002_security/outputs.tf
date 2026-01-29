output "alb_security_group_id" {
  description = "ALB 安全组 ID"
  value       = aws_security_group.alb.id
}

output "eks_control_plane_security_group_id" {
  description = "EKS Control Plane 安全组 ID"
  value       = aws_security_group.eks_control_plane.id
}

output "eks_worker_security_group_id" {
  description = "EKS Worker 安全组 ID"
  value       = aws_security_group.eks_worker.id
}

output "aurora_security_group_id" {
  description = "Aurora 安全组 ID"
  value       = aws_security_group.aurora.id
}
