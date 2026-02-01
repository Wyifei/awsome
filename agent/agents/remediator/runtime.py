"""
Remediator Agent Runtime - FastAPI Wrapper

This module provides the HTTP interface for the Remediator Agent.
"""
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

# Add parent directory to path for shared imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.config import get_config
from remediator.agent import create_remediator_agent, run_remediator

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
    memory_session_id: Optional[str] = None
    memory_id: Optional[str] = None
    resource_arn: Optional[str] = None
    resource_type: Optional[str] = None
    actor_id: Optional[str] = None  # 需要与 Analyzer 使用相同的值


class InvocationResponse(BaseModel):
    """AgentCore invocation response schema."""
    output_text: str
    session_id: Optional[str] = None
    metadata: Optional[dict] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Remediator Agent Runtime")
    yield
    logger.info("Shutting down Remediator Agent Runtime")


app = FastAPI(
    title="SHARA Remediator Agent",
    description="Security Hub Finding Remediator",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/ping")
async def ping():
    """Health check endpoint."""
    return {"status": "healthy", "agent_type": "remediator"}


@app.post("/invocations")
async def invocations(request: Request):
    """Agent invocation endpoint."""
    try:
        body = await request.json()
        logger.info(f"Received invocation request: {json.dumps(body, default=str)[:500]}...")

        # 支持两种调用方式:
        # 1. 直接调用 (curl): 数据在 body 顶层
        # 2. AgentCore Runtime: 数据在 prompt 字段中 (JSON 字符串)
        memory_id_from_payload = None  # 从 payload 提取的 memory_id

        if 'prompt' in body and body.get('prompt'):
            prompt_data = body.get('prompt')
            if isinstance(prompt_data, str):
                try:
                    prompt_data = json.loads(prompt_data)
                except json.JSONDecodeError:
                    prompt_data = {}
            task_id = prompt_data.get('task_id', 'unknown')
            memory_session_id = prompt_data.get('memory_session_id')
            memory_id_from_payload = prompt_data.get('memory_id')  # 从 prompt 提取 memory_id
            resource_arn = prompt_data.get('resource_arn')
            resource_type = prompt_data.get('resource_type')
            control_id = prompt_data.get('control_id', '')
            finding_id = prompt_data.get('finding_id', '')
            is_rollback = prompt_data.get('is_rollback', False)
            session_id = body.get('session_id')
            actor_id = prompt_data.get('actor_id')
        else:
            task_id = body.get('task_id', 'unknown')
            memory_session_id = body.get('memory_session_id')
            memory_id_from_payload = body.get('memory_id')  # 从 body 提取 memory_id
            resource_arn = body.get('resource_arn')
            resource_type = body.get('resource_type')
            control_id = body.get('control_id', '')
            finding_id = body.get('finding_id', '')
            is_rollback = body.get('is_rollback', False)
            session_id = body.get('session_id')
            actor_id = body.get('actor_id')

        if not memory_session_id:
            raise ValueError("memory_session_id is required for Remediator Agent")
        if not resource_arn:
            raise ValueError("resource_arn is required for Remediator Agent")
        if not resource_type:
            raise ValueError("resource_type is required for Remediator Agent")

        config = get_config()
        # 优先使用 payload 中的 memory_id，否则使用环境变量
        memory_id = memory_id_from_payload or config.memory_id

        if not memory_id:
            logger.warning("memory_id is empty - Memory features will be disabled")

        # actor_id 已在上面解析

        # Create agent for this request
        agent = create_remediator_agent(
            task_id=task_id,
            memory_session_id=memory_session_id,
            memory_id=memory_id,
            region=config.region,
            actor_id=actor_id
        )

        # Run remediator
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: run_remediator(
                agent=agent,
                task_id=task_id,
                resource_arn=resource_arn,
                resource_type=resource_type,
                control_id=control_id,
                finding_id=finding_id,
                memory_session_id=memory_session_id,
                actor_id=actor_id,
                is_rollback=is_rollback
            )
        )

        # 构建响应数据
        response_data = {
            "success": result.get('success', False),
            "task_id": task_id,
            "resource_arn": resource_arn,
            "is_rollback": is_rollback,
            "validator_called": result.get('validator_called', False),
            "response": result.get('response', ''),
            "session_id": session_id,
            "metadata": {
                "task_id": task_id,
                "agent_type": "remediator",
                "success": result.get('success', False),
                "is_rollback": is_rollback,
                "validator_called": result.get('validator_called', False)
            }
        }

        if result.get('error'):
            response_data['error'] = result.get('error')

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
