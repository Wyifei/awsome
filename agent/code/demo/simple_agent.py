#!/usr/bin/env python3
"""
Simple Strands Agent Demo
基础的 Strands Agent 示例，使用统一认证模块

运行前先诊断认证配置:
    python auth_config.py

运行 Agent:
    python simple_agent.py
"""

import logging
from strands import Agent
from auth_config import create_model, diagnose_auth

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_simple_agent():
    """创建一个简单的 Agent，使用统一认证"""

    # 使用统一的认证配置创建模型
    model = create_model()

    # 创建 Agent
    agent = Agent(
        model=model,
        system_prompt="""
        You are a helpful assistant that specializes in AWS security.
        You provide clear, concise answers about AWS best practices.
        Always respond in a friendly and professional manner.
        Keep your responses brief but informative.
        """
    )

    return agent


def main():
    print("=" * 60)
    print("Strands Agent Demo - Simple Agent")
    print("=" * 60)

    # 显示认证诊断信息
    diagnose_auth()

    print("\nCreating Agent...")
    agent = create_simple_agent()
    print("Agent created successfully!\n")

    # 简单测试
    test_prompt = "What are the top 3 S3 security best practices? Be brief."

    print(f"{'─' * 60}")
    print(f"User: {test_prompt}")
    print(f"{'─' * 60}")

    try:
        response = agent(test_prompt)
        print(f"\nAssistant: {response}")
    except Exception as e:
        logger.error(f"Agent call failed: {e}")
        raise


if __name__ == "__main__":
    main()
