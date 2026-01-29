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
    region: str = os.environ.get('AWS_REGION', 'us-east-1')

    # DynamoDB Tables
    tasks_table: str = os.environ.get('TASKS_TABLE', 'shara-tasks')
    tokens_table: str = os.environ.get('TOKENS_TABLE', 'shara-approval-tokens')

    # S3 Buckets
    asr_playbooks_bucket: str = os.environ.get('ASR_PLAYBOOKS_BUCKET', '')

    # AgentCore Memory
    memory_id: str = os.environ.get('AGENTCORE_MEMORY_ID', '')

    # LLM Configuration
    model_id: str = os.environ.get('MODEL_ID', 'anthropic.claude-sonnet-4-20250514-v1:0')

    # Stage
    stage: str = os.environ.get('STAGE', 'dev')
    log_level: str = os.environ.get('LOG_LEVEL', 'INFO')


@dataclass
class ModelConfig:
    """LLM model configuration for each agent"""
    model_id: str
    temperature: float
    max_tokens: int
    top_p: float = 0.9


# Model configurations for each agent
ANALYZER_MODEL_CONFIG = ModelConfig(
    model_id='anthropic.claude-sonnet-4-20250514-v1:0',
    temperature=0.2,
    max_tokens=8192,
    top_p=0.9
)

REMEDIATOR_MODEL_CONFIG = ModelConfig(
    model_id='anthropic.claude-sonnet-4-20250514-v1:0',
    temperature=0.1,
    max_tokens=8192,
    top_p=0.95
)

VALIDATOR_MODEL_CONFIG = ModelConfig(
    model_id='anthropic.claude-sonnet-4-20250514-v1:0',
    temperature=0.1,
    max_tokens=4096,
    top_p=0.9
)


def get_config() -> AgentConfig:
    """Get agent configuration from environment"""
    return AgentConfig()
