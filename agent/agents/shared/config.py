"""
SHARA Agent Configuration
"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class AgentConfig:
    """Agent configuration settings"""

    # AWS Region
    region: str = os.environ.get('AWS_REGION', 'ap-northeast-1')

    # DynamoDB Tables
    tasks_table: str = os.environ.get('TASKS_TABLE', 'shara-dev-tasks')
    tokens_table: str = os.environ.get('TOKENS_TABLE', 'shara-dev-approval-tokens')

    # S3 Buckets
    asr_playbooks_bucket: str = os.environ.get('ASR_PLAYBOOKS_BUCKET', 'shara-dev-asr-playbooks-870414140965')
    remediation_audit_bucket: str = os.environ.get('REMEDIATION_AUDIT_BUCKET', 'shara-dev-remediation-audit-870414140965')

    # AgentCore Memory
    memory_id: str = os.environ.get('AGENTCORE_MEMORY_ID', '')
    # actor_id 通常从 Finding 的 AwsAccountId 获取，用于 Memory 共享
    # 同一 AWS 账户的修复经验会被分组在一起，便于 LTM 跨任务共享

    # AgentCore Code Interpreter (通过 Console 创建，关联 IAM Role)
    # 用于 Remediator 在安全沙箱中执行修复代码
    code_interpreter_id: str = os.environ.get('CODE_INTERPRETER_ID', 'shara_interpreter_tool-sGd1u5rIet')

    # LLM Configuration
    model_id: str = os.environ.get('MODEL_ID', 'global.anthropic.claude-opus-4-5-20251101-v1:0')

    # Stage
    stage: str = os.environ.get('STAGE', 'dev')
    log_level: str = os.environ.get('LOG_LEVEL', 'DEBUG')


@dataclass
class ModelConfig:
    """LLM model configuration for each agent"""
    model_id: str
    temperature: float
    max_tokens: int


# Model configurations for each agent
ANALYZER_MODEL_CONFIG = ModelConfig(
    model_id='global.anthropic.claude-opus-4-5-20251101-v1:0',
    temperature=0.2,
    max_tokens=8192
)

REMEDIATOR_MODEL_CONFIG = ModelConfig(
    model_id='global.anthropic.claude-opus-4-5-20251101-v1:0',
    temperature=0.1,
    max_tokens=8192
)

VALIDATOR_MODEL_CONFIG = ModelConfig(
    model_id='global.anthropic.claude-opus-4-5-20251101-v1:0',
    temperature=0.1,
    max_tokens=4096
)


def get_config() -> AgentConfig:
    """Get agent configuration from environment"""
    return AgentConfig()
