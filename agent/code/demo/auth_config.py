#!/usr/bin/env python3
"""
Bedrock 模型鉴权配置模块

支持多种认证方式:
1. Bearer Token (aws-bedrock-token-generator)
2. IAM 凭证 (标准 AWS 凭证链)
3. AgentCore Runtime (自动 IAM Role)
"""

import os
import logging
from typing import Optional
from functools import lru_cache

import boto3
from botocore.config import Config as BotocoreConfig

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-1")
DEFAULT_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID",
    "apac.anthropic.claude-sonnet-4-20250514-v1:0"
)


class BedrockAuthConfig:
    """Bedrock 认证配置类"""

    def __init__(
        self,
        region: str = DEFAULT_REGION,
        model_id: str = DEFAULT_MODEL_ID,
        bearer_token: Optional[str] = None,
        auto_refresh_token: bool = True
    ):
        self.region = region
        self.model_id = model_id
        self._bearer_token = bearer_token
        self._auto_refresh_token = auto_refresh_token
        self._auth_method = None

    @property
    def bearer_token(self) -> Optional[str]:
        """获取 Bearer Token，支持自动刷新"""
        if self._bearer_token:
            return self._bearer_token

        # 从环境变量获取
        token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")
        if token:
            self._auth_method = "bearer_token_env"
            return token

        # 尝试动态生成
        if self._auto_refresh_token:
            token = self._generate_bearer_token()
            if token:
                self._auth_method = "bearer_token_generated"
                return token

        return None

    def _generate_bearer_token(self) -> Optional[str]:
        """使用 aws-bedrock-token-generator 生成 token"""
        try:
            from aws_bedrock_token_generator import provide_token
            token = provide_token()
            logger.info("Successfully generated bearer token")
            return token
        except ImportError:
            logger.debug("aws-bedrock-token-generator not installed")
            return None
        except Exception as e:
            logger.warning(f"Failed to generate bearer token: {e}")
            return None

    def get_auth_method(self) -> str:
        """返回当前使用的认证方式"""
        if self._auth_method:
            return self._auth_method

        # 检查各种认证方式
        if self.bearer_token:
            return self._auth_method

        # 检查 IAM 凭证
        session = boto3.Session()
        credentials = session.get_credentials()
        if credentials:
            if os.environ.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"):
                return "iam_role_ecs"
            elif os.environ.get("AWS_WEB_IDENTITY_TOKEN_FILE"):
                return "iam_role_web_identity"
            elif hasattr(credentials, '_method') and 'iam-role' in str(credentials._method).lower():
                return "iam_role_ec2"
            else:
                return "iam_credentials"

        return "unknown"


def create_bedrock_session(config: BedrockAuthConfig) -> boto3.Session:
    """创建配置好认证的 boto3 Session"""
    return boto3.Session(region_name=config.region)


def create_bedrock_client(config: BedrockAuthConfig):
    """
    创建配置好认证的 Bedrock Runtime 客户端

    根据认证方式自动配置:
    - Bearer Token: 注入 token 到请求头
    - IAM: 使用标准 SigV4 签名
    """
    session = create_bedrock_session(config)

    # 创建客户端配置
    client_config = BotocoreConfig(
        user_agent_extra="strands-agents-shara",
        read_timeout=120,
        retries={'max_attempts': 3}
    )

    # 创建客户端
    client = session.client(
        'bedrock-runtime',
        region_name=config.region,
        config=client_config
    )

    # 如果使用 Bearer Token，注入到请求
    bearer_token = config.bearer_token
    if bearer_token:
        def inject_bearer_token(request, **kwargs):
            request.headers['Authorization'] = f'Bearer {bearer_token}'
            logger.debug("Injected bearer token into request")

        client.meta.events.register(
            'before-send.bedrock-runtime.*',
            inject_bearer_token
        )
        logger.info(f"Configured Bearer Token authentication for {config.region}")
    else:
        logger.info(f"Using IAM credentials for {config.region}")

    return client


# ============================================
# Strands Agent 集成
# ============================================

def create_authenticated_bedrock_model(config: Optional[BedrockAuthConfig] = None):
    """
    创建已配置认证的 BedrockModel

    用法:
        from auth_config import create_authenticated_bedrock_model
        model = create_authenticated_bedrock_model()
        agent = Agent(model=model, ...)
    """
    from strands.models import BedrockModel

    if config is None:
        config = BedrockAuthConfig()

    auth_method = config.get_auth_method()
    logger.info(f"Creating BedrockModel with auth method: {auth_method}")
    logger.info(f"Model: {config.model_id}, Region: {config.region}")

    # 创建 BedrockModel
    model = BedrockModel(
        model_id=config.model_id,
        region_name=config.region,
        temperature=0.3,
        max_tokens=4096
    )

    # 如果使用 Bearer Token，注入认证
    bearer_token = config.bearer_token
    if bearer_token:
        def inject_bearer_token(request, **kwargs):
            request.headers['Authorization'] = f'Bearer {bearer_token}'

        model.client.meta.events.register(
            'before-send.bedrock-runtime.*',
            inject_bearer_token
        )

    return model


# ============================================
# AgentCore Runtime 集成
# ============================================

def create_agentcore_bedrock_model():
    """
    为 AgentCore Runtime 创建 BedrockModel

    在 AgentCore Runtime 中运行时:
    - Runtime 自动提供 IAM Role 凭证
    - 无需手动配置认证
    - 凭证通过环境自动注入
    """
    from strands.models import BedrockModel

    # AgentCore Runtime 环境变量
    runtime_region = os.environ.get("AWS_REGION", DEFAULT_REGION)
    runtime_model = os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID)

    logger.info(f"AgentCore Runtime - Region: {runtime_region}, Model: {runtime_model}")

    # AgentCore Runtime 自动提供凭证，无需额外配置
    model = BedrockModel(
        model_id=runtime_model,
        region_name=runtime_region,
        temperature=0.3,
        max_tokens=4096
    )

    return model


def is_running_in_agentcore() -> bool:
    """检测是否在 AgentCore Runtime 环境中运行"""
    # AgentCore Runtime 会设置特定的环境变量
    agentcore_indicators = [
        "AGENTCORE_RUNTIME_ID",
        "AGENTCORE_SESSION_ID",
        "AWS_EXECUTION_ENV"  # 值可能包含 "AgentCore"
    ]

    for indicator in agentcore_indicators:
        if os.environ.get(indicator):
            return True

    # 检查 AWS_EXECUTION_ENV 是否包含 AgentCore
    exec_env = os.environ.get("AWS_EXECUTION_ENV", "")
    if "AgentCore" in exec_env or "agentcore" in exec_env:
        return True

    return False


# ============================================
# 统一入口
# ============================================

def create_model(config: Optional[BedrockAuthConfig] = None):
    """
    智能创建 BedrockModel

    自动检测运行环境并选择最佳认证方式:
    - AgentCore Runtime: 使用 Runtime 提供的 IAM Role
    - 本地开发 + Bearer Token: 使用 token 认证
    - 本地开发 + IAM: 使用标准凭证
    """
    if is_running_in_agentcore():
        logger.info("Detected AgentCore Runtime environment")
        return create_agentcore_bedrock_model()
    else:
        logger.info("Running in local/standalone environment")
        return create_authenticated_bedrock_model(config)


# ============================================
# 测试和诊断
# ============================================

def diagnose_auth():
    """诊断当前的认证配置"""
    print("=" * 60)
    print("Bedrock Authentication Diagnosis")
    print("=" * 60)

    config = BedrockAuthConfig()

    print(f"\n1. Environment:")
    print(f"   Region: {config.region}")
    print(f"   Model ID: {config.model_id}")
    print(f"   AgentCore Runtime: {is_running_in_agentcore()}")

    print(f"\n2. Authentication Method: {config.get_auth_method()}")

    print(f"\n3. Bearer Token:")
    token = config.bearer_token
    if token:
        print(f"   Status: Available")
        print(f"   Token preview: {token[:30]}...")
    else:
        print(f"   Status: Not available")

    print(f"\n4. IAM Credentials:")
    session = boto3.Session()
    credentials = session.get_credentials()
    if credentials:
        print(f"   Status: Available")
        if credentials.access_key:
            print(f"   Access Key: {credentials.access_key[:8]}...")
    else:
        print(f"   Status: Not available")

    print(f"\n5. Environment Variables:")
    env_vars = [
        "AWS_DEFAULT_REGION",
        "AWS_REGION",
        "AWS_BEARER_TOKEN_BEDROCK",
        "AWS_ACCESS_KEY_ID",
        "AWS_PROFILE",
        "BEDROCK_MODEL_ID",
    ]
    for var in env_vars:
        value = os.environ.get(var)
        if value:
            # 隐藏敏感值
            if "TOKEN" in var or "KEY" in var or "SECRET" in var:
                print(f"   {var}: {value[:10]}... (hidden)")
            else:
                print(f"   {var}: {value}")
        else:
            print(f"   {var}: (not set)")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    diagnose_auth()
