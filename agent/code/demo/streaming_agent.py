#!/usr/bin/env python3
"""
Strands Agent Streaming Demo
展示流式输出的 Agent 使用方式
"""

import os
import asyncio
from strands import Agent
from strands.models import BedrockModel

# 模型配置 - 使用跨区域推理配置文件 (APAC)
DEFAULT_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID",
    "apac.anthropic.claude-sonnet-4-20250514-v1:0"
)
DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-1")


async def run_streaming_agent():
    """运行支持流式输出的 Agent"""

    print(f"Using model: {DEFAULT_MODEL_ID} in region: {DEFAULT_REGION}")

    model = BedrockModel(
        model_id=DEFAULT_MODEL_ID,
        region_name=DEFAULT_REGION,
        temperature=0.3,
        max_tokens=2048
    )

    agent = Agent(
        model=model,
        system_prompt="""
        You are a helpful AWS security expert.
        Provide detailed explanations with examples.
        """
    )

    prompt = "Explain the top 3 S3 security best practices with examples."

    print("=" * 60)
    print("Strands Agent Demo - Streaming Output")
    print("=" * 60)
    print(f"\nUser: {prompt}\n")
    print("Assistant: ", end="", flush=True)

    # 使用流式输出
    async for chunk in agent.stream_async(prompt):
        if hasattr(chunk, 'content'):
            print(chunk.content, end="", flush=True)
        elif isinstance(chunk, str):
            print(chunk, end="", flush=True)

    print("\n")


def main():
    asyncio.run(run_streaming_agent())


if __name__ == "__main__":
    main()
