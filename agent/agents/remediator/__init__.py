"""
Remediator Agent - Phase 2 修复智能体

支持两种修复类型:
- aws_api: AWS 配置类问题，使用 run_remediator()
- github_pr: 容器漏洞，使用 run_github_pr_remediator()

System Prompts 已分离:
- AWS_API_REMEDIATOR_SYSTEM_PROMPT: 标准 Security Hub API 修复
- GITHUB_PR_REMEDIATOR_SYSTEM_PROMPT: 容器漏洞 GitHub PR 修复
"""
from remediator.agent import (
    create_remediator_agent,
    run_remediator,
    run_github_pr_remediator,
    REMEDIATOR_SYSTEM_PROMPT,  # 向后兼容 (= AWS_API_REMEDIATOR_SYSTEM_PROMPT)
    AWS_API_REMEDIATOR_SYSTEM_PROMPT,
    GITHUB_PR_REMEDIATOR_SYSTEM_PROMPT,
)

__all__ = [
    'create_remediator_agent',
    'run_remediator',
    'run_github_pr_remediator',
    'REMEDIATOR_SYSTEM_PROMPT',
    'AWS_API_REMEDIATOR_SYSTEM_PROMPT',
    'GITHUB_PR_REMEDIATOR_SYSTEM_PROMPT',
]
