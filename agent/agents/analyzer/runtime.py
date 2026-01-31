"""
Analyzer Agent Runtime - FastAPI Wrapper

This module provides the HTTP interface for the Analyzer Agent.
"""
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Add parent directory to path for shared imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.config import get_config
from analyzer.agent import create_analyzer_agent, run_analyzer

# Configure logging
logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class InvocationRequest(BaseModel):
    """AgentCore invocation request schema."""
    input_text: str
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    finding: Optional[dict] = None
    control_id: Optional[str] = None
    memory_id: Optional[str] = None
    memory_session_id: Optional[str] = None  # Lambda 传入的 session_id
    actor_id: Optional[str] = None  # 可选的 actor_id


class InvocationResponse(BaseModel):
    """AgentCore invocation response schema."""
    output_text: str
    session_id: Optional[str] = None
    metadata: Optional[dict] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Analyzer Agent Runtime")
    yield
    logger.info("Shutting down Analyzer Agent Runtime")


app = FastAPI(
    title="SHARA Analyzer Agent",
    description="Security Hub Finding Analyzer",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/ping")
async def ping():
    """Health check endpoint."""
    return {"status": "healthy", "agent_type": "analyzer"}


@app.post("/invocations")
async def invocations(request: Request):
    """Agent invocation endpoint."""
    try:
        body = await request.json()
        logger.info(f"Received invocation request: {json.dumps(body, default=str)[:500]}...")

        # 支持两种调用方式:
        # 1. 直接调用 (curl): task_id, finding, control_id 在 body 顶层
        # 2. AgentCore Runtime/Sandbox: 数据在 prompt 字段中 (JSON 字符串)
        if 'prompt' in body and body.get('prompt'):
            # AgentCore Runtime 调用方式 - 解析 prompt 字段
            prompt_data = body.get('prompt')
            if isinstance(prompt_data, str):
                try:
                    prompt_data = json.loads(prompt_data)
                except json.JSONDecodeError as e:
                    # prompt 不是有效 JSON，返回使用说明
                    logger.error(f"Invalid JSON in prompt field: {e}")
                    raise ValueError(
                        f"prompt 字段必须是有效的 JSON 字符串。\n"
                        f"正确格式示例:\n"
                        f'{{"task_id": "test-001", "control_id": "SNS.1", "finding": {{"Id": "...", "Resources": [...]}}}}\n'
                        f"收到的内容: {prompt_data[:200] if len(prompt_data) > 200 else prompt_data}"
                    )
            task_id = prompt_data.get('task_id', 'unknown')
            finding = prompt_data.get('finding')
            control_id = prompt_data.get('control_id')
            memory_session_id = prompt_data.get('memory_session_id') or body.get('session_id') or f"session-task-{task_id}"
            actor_id = prompt_data.get('actor_id')
        else:
            # 直接调用方式 (curl 或其他 HTTP 客户端)
            task_id = body.get('task_id', 'unknown')
            finding = body.get('finding')
            control_id = body.get('control_id')
            memory_session_id = body.get('memory_session_id') or body.get('session_id') or f"session-task-{task_id}"
            actor_id = body.get('actor_id')

        # 验证必需字段
        if not finding:
            raise ValueError(
                "缺少必需字段 'finding'。\n"
                "请提供 Security Hub Finding (ASFF 格式)。"
            )
        if not control_id:
            raise ValueError(
                "缺少必需字段 'control_id'。\n"
                "请提供 Control ID (如 SNS.1, S3.1, EC2.19)。"
            )

        config = get_config()
        memory_id = body.get('memory_id') or config.memory_id

        logger.info(f"Creating Analyzer Agent: task_id={task_id}, memory_session_id={memory_session_id}")

        # Create agent for this request
        agent = create_analyzer_agent(
            task_id=task_id,
            memory_id=memory_id,
            session_id=memory_session_id,  # 传入 session_id
            region=config.region,
            actor_id=actor_id
        )

        # Run analyzer
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: run_analyzer(agent, finding, control_id, task_id)
        )

        # 构建响应 - 直接包含解析好的数据，避免多层 JSON 嵌套
        response_data = {
            "success": result.get('success', False),
            "task_id": task_id,
            "analysis": result.get('analysis', {}),
            "asr_match": result.get('asr_match', {}),
            "similar_experiences": result.get('similar_experiences', []),
            "remediation": result.get('remediation', {}),
            "session_id": memory_session_id,
            "metadata": {
                "agent_type": "analyzer",
                "has_asr_match": result.get('asr_match', {}).get('matched', False)
            }
        }

        # 如果失败，包含错误信息
        if not result.get('success', False):
            response_data['error'] = result.get('error', 'Unknown error')

        logger.info(f"Invocation completed for task {task_id}")
        # 使用 Response 并设置 ensure_ascii=False 以正确显示中文
        from starlette.responses import Response
        return Response(
            content=json.dumps(response_data, ensure_ascii=False, default=str),
            media_type="application/json; charset=utf-8"
        )

    except Exception as e:
        logger.exception(f"Invocation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get('PORT', 8080))
    uvicorn.run("runtime:app", host="0.0.0.0", port=port, log_level="info")
