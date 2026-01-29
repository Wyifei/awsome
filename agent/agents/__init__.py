"""
SHARA Agents - Security Hub Auto-Remediation Agent

This package contains the AI agents for automated security remediation:
- Analyzer Agent (Phase 1): Analyzes findings and generates remediation descriptions
- Remediator Agent (Phase 2): Generates and executes remediation code
- Validator Agent (Phase 2): Validates fixes and saves experiences
"""

from agents.analyzer.agent import create_analyzer_agent
from agents.remediator.agent import create_remediator_agent
from agents.validator.agent import create_validator_agent

__all__ = [
    'create_analyzer_agent',
    'create_remediator_agent',
    'create_validator_agent',
]

__version__ = '1.0.0'
