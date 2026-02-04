"""
Analyzer Agent - Phase 1 分析智能体

支持两种修复类型:
- aws_api: AWS 配置类问题，使用 run_analyzer()
- github_pr: 容器漏洞，使用 run_container_analyzer()

System Prompts 已分离:
- AWS_API_ANALYZER_SYSTEM_PROMPT: 标准 Security Hub 配置修复
- GITHUB_PR_ANALYZER_SYSTEM_PROMPT: 容器漏洞 GitHub PR 修复
"""
from analyzer.agent import (
    create_analyzer_agent,
    run_analyzer,
    run_container_analyzer,
    ANALYZER_SYSTEM_PROMPT,  # 向后兼容 (= AWS_API_ANALYZER_SYSTEM_PROMPT)
    AWS_API_ANALYZER_SYSTEM_PROMPT,
    GITHUB_PR_ANALYZER_SYSTEM_PROMPT,
)

__all__ = [
    'create_analyzer_agent',
    'run_analyzer',
    'run_container_analyzer',
    'ANALYZER_SYSTEM_PROMPT',
    'AWS_API_ANALYZER_SYSTEM_PROMPT',
    'GITHUB_PR_ANALYZER_SYSTEM_PROMPT',
]
