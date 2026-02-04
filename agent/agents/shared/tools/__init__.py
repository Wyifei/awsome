"""
SHARA Agent Tools

Tools available to agents for performing remediation tasks.
"""

from shared.tools.asr_playbook import fetch_asr_playbook
from shared.tools.memory_tools import (
    search_similar_findings,
    save_analysis_result,
    get_analysis_context,
    save_experience_to_ltm,
    set_memory_session,
    save_rollback_to_memory,
    get_rollback_from_memory,
    save_remediation_result,
    get_remediation_result,
    save_pr_result,
    get_pr_result,
)
from shared.tools.aws_resources import get_resource_config
from shared.tools.security_hub import (
    update_security_hub_finding,
    verify_resource_state,
)
from shared.tools.execution import (
    save_rollback_data,
    get_rollback_data,
    execute_rollback,
    execute_code,
    set_audit_context,
)
from shared.tools.a2a_tools import (
    invoke_validator_agent,
)
from shared.tools.validator_tools import (
    review_code_security,
    trigger_result_email,
)
from shared.tools.code_check import (
    pre_execution_check,
)
from shared.tools.github_mcp_client import (
    read_github_file,
    create_github_branch,
    push_files_to_github,
    create_pull_request,
    get_pull_request,
    get_pull_request_files,
    search_repo_for_container,
    search_container_inventory,
    get_service_metadata,
)

__all__ = [
    # ASR Playbook
    'fetch_asr_playbook',
    # Memory
    'search_similar_findings',
    'save_analysis_result',
    'get_analysis_context',
    'save_experience_to_ltm',
    'set_memory_session',
    'save_rollback_to_memory',
    'get_rollback_from_memory',
    'save_remediation_result',
    'get_remediation_result',
    'save_pr_result',
    'get_pr_result',
    # AWS Resources
    'get_resource_config',
    # Security Hub
    'update_security_hub_finding',
    'verify_resource_state',
    # Execution
    'save_rollback_data',
    'get_rollback_data',
    'execute_rollback',
    'execute_code',
    'set_audit_context',
    # A2A Communication (Remediator -> Validator)
    'invoke_validator_agent',
    # Validator Tools
    'review_code_security',
    'trigger_result_email',
    # Pre-execution Check (Remediator)
    'pre_execution_check',
    # GitHub MCP Tools (容器漏洞修复)
    'read_github_file',
    'create_github_branch',
    'push_files_to_github',
    'create_pull_request',
    'get_pull_request',
    'get_pull_request_files',
    'search_repo_for_container',
    'search_container_inventory',
    'get_service_metadata',
]
