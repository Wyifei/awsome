"""
Code Check Tools - Pre-execution Code Safety Check

Provides a fast, lightweight code safety check for Remediator Agent
to run BEFORE executing generated code. This is a first-line defense
that blocks obviously dangerous operations.

Flow:
1. Remediator generates code
2. Remediator calls pre_execution_check (THIS TOOL) - fast check
3. If passed, Remediator executes code
4. Remediator calls Validator via A2A for full review
"""
import logging
import re
from strands import tool

logger = logging.getLogger(__name__)


# Critical patterns that should BLOCK execution immediately
CRITICAL_PATTERNS = [
    # Destructive resource operations
    (r'\.delete_bucket\s*\(', "S3 bucket deletion - BLOCKED"),
    (r'\.terminate_instances\s*\(', "EC2 instance termination - BLOCKED"),
    (r'\.delete_db_instance\s*\(', "RDS instance deletion - BLOCKED"),
    (r'\.delete_db_cluster\s*\(', "RDS cluster deletion - BLOCKED"),
    (r'\.delete_table\s*\(', "DynamoDB table deletion - BLOCKED"),
    (r'\.delete_function\s*\(', "Lambda function deletion - BLOCKED"),
    (r'\.delete_stack\s*\(', "CloudFormation stack deletion - BLOCKED"),
    (r'\.delete_cluster\s*\(', "ECS/EKS cluster deletion - BLOCKED"),

    # IAM critical operations
    (r'iam\.create_user\s*\(', "IAM user creation - BLOCKED"),
    (r'iam\.create_access_key\s*\(', "Access key creation - BLOCKED"),
    (r'iam\.delete_role\s*\(', "IAM role deletion - BLOCKED"),
    (r'iam\.delete_user\s*\(', "IAM user deletion - BLOCKED"),
    (r'AdministratorAccess', "AdministratorAccess policy reference - BLOCKED"),

    # Code injection risks
    (r'\beval\s*\(', "eval() function - BLOCKED"),
    (r'\bexec\s*\(', "exec() function - BLOCKED"),
    (r'subprocess\.call\s*\([^)]*shell\s*=\s*True', "shell=True in subprocess - BLOCKED"),
]

# Credential patterns that should BLOCK execution
CREDENTIAL_PATTERNS = [
    (r'AKIA[0-9A-Z]{16}', "AWS Access Key ID detected - BLOCKED"),
    (r'-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----', "Private key detected - BLOCKED"),
    (r'-----BEGIN\s+EC\s+PRIVATE\s+KEY-----', "EC private key detected - BLOCKED"),
]

# Warning patterns - allow but flag
WARNING_PATTERNS = [
    (r'\.delete_objects\s*\(', "S3 objects deletion detected"),
    (r'\.revoke_security_group', "Security group rule revocation"),
    (r'0\.0\.0\.0/0', "Open CIDR block (0.0.0.0/0)"),
    (r'::/0', "Open IPv6 CIDR block (::/0)"),
    (r'iam\.attach_user_policy\s*\(', "User policy attachment"),
    (r'iam\.put_user_policy\s*\(', "Inline user policy creation"),
    (r'sts\.assume_role\s*\(', "Role assumption detected"),
]


@tool
def pre_execution_check(code: str) -> dict:
    """Fast pre-execution safety check for generated code.

    Run this BEFORE executing any generated code. This is a quick first-line
    defense that blocks obviously dangerous operations.

    This check is intentionally fast and focused on critical issues only.
    Full security review is done by Validator Agent after execution.

    Args:
        code: The Python code to check before execution

    Returns:
        dict: Check results including:
            - safe_to_execute: bool - Whether code is safe to execute
            - blocked_reasons: list - Critical issues that block execution
            - warnings: list - Non-blocking warnings to note
            - recommendation: str - What to do next
    """
    blocked_reasons = []
    warnings = []

    logger.info(f"Pre-execution check (code length: {len(code)} chars)")

    # Check for critical patterns that BLOCK execution
    for pattern, message in CRITICAL_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            blocked_reasons.append(message)
            logger.warning(f"BLOCKED: {message}")

    # Check for credential leakage
    for pattern, message in CREDENTIAL_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            blocked_reasons.append(message)
            logger.warning(f"BLOCKED: {message}")

    # Check for warning patterns (non-blocking)
    for pattern, message in WARNING_PATTERNS:
        if re.search(pattern, code, re.IGNORECASE):
            warnings.append(message)
            logger.info(f"WARNING: {message}")

    # Determine if safe to execute
    safe_to_execute = len(blocked_reasons) == 0

    if safe_to_execute:
        if warnings:
            recommendation = "Code passed pre-check with warnings. Proceed with execution, Validator will do full review."
        else:
            recommendation = "Code passed pre-check. Proceed with execution."
    else:
        recommendation = "Code BLOCKED. Do not execute. Review and regenerate code without dangerous operations."

    result = {
        "safe_to_execute": safe_to_execute,
        "blocked_reasons": blocked_reasons,
        "warnings": warnings,
        "recommendation": recommendation,
        "checks_performed": len(CRITICAL_PATTERNS) + len(CREDENTIAL_PATTERNS)
    }

    if safe_to_execute:
        logger.info(f"Pre-execution check PASSED (warnings: {len(warnings)})")
    else:
        logger.error(f"Pre-execution check FAILED (blocked: {len(blocked_reasons)})")

    return result
