"""
Validator Agent Runtime - FastAPI Wrapper

This module provides the HTTP interface for the Validator Agent.
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
from validator.agent import create_validator_agent, run_validator

# Configure logging
logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class InvocationRequest(BaseModel):
    """AgentCore invocation request schema (supports A2A from Remediator)."""
    input_text: str = ""  # Optional for A2A calls
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    memory_session_id: Optional[str] = None
    memory_id: Optional[str] = None
    finding_id: Optional[str] = None
    resource_arn: Optional[str] = None
    resource_type: Optional[str] = None
    control_id: Optional[str] = None
    # A2A parameters from Remediator
    # NOTE: generated_code and execution_result are now retrieved from Memory
    is_rollback: bool = False  # Whether this is a rollback (no rollback link in email)
    rollback_failed: bool = False  # Whether the rollback operation failed
    error_message: Optional[str] = None  # Error message to include in notification
    actor_id: Optional[str] = None  # 需要与 Analyzer/Remediator 使用相同的值


class InvocationResponse(BaseModel):
    """AgentCore invocation response schema."""
    output_text: str
    session_id: Optional[str] = None
    metadata: Optional[dict] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Validator Agent Runtime")
    yield
    logger.info("Shutting down Validator Agent Runtime")


app = FastAPI(
    title="SHARA Validator Agent",
    description="Security Hub Finding Validator",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/ping")
async def ping():
    """Health check endpoint."""
    return {"status": "healthy", "agent_type": "validator"}


@app.post("/invocations")
async def invocations(request: Request):
    """Agent invocation endpoint."""
    try:
        body = await request.json()
        logger.info(f"Received invocation request: {json.dumps(body, default=str)[:500]}...")

        # 支持三种调用方式:
        # 1. A2A 调用 (from Remediator): 数据在 body 顶层
        # 2. 直接调用 (curl): 数据在 body 顶层
        # 3. AgentCore Runtime: 数据在 prompt 字段中 (JSON 字符串)
        #
        # NOTE: generated_code and execution_result are now retrieved from Memory by Validator Agent

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
            finding_id = prompt_data.get('finding_id')
            resource_arn = prompt_data.get('resource_arn')
            resource_type = prompt_data.get('resource_type')
            control_id = prompt_data.get('control_id')
            is_rollback = prompt_data.get('is_rollback', False)
            rollback_failed = prompt_data.get('rollback_failed', False)
            error_message = prompt_data.get('error_message', '')
            session_id = body.get('session_id')
            actor_id = prompt_data.get('actor_id')
        else:
            # A2A 调用或直接调用
            task_id = body.get('task_id', 'unknown')
            memory_session_id = body.get('memory_session_id')
            memory_id_from_payload = body.get('memory_id')  # 从 body 提取 memory_id
            finding_id = body.get('finding_id')
            resource_arn = body.get('resource_arn')
            resource_type = body.get('resource_type')
            control_id = body.get('control_id')
            is_rollback = body.get('is_rollback', False)
            rollback_failed = body.get('rollback_failed', False)
            error_message = body.get('error_message', '')
            session_id = body.get('session_id')
            actor_id = body.get('actor_id')

        # Detect A2A call source
        is_a2a_call = request.headers.get('X-A2A-Source') == 'remediator-agent'
        if is_a2a_call:
            logger.info(f"A2A invocation from Remediator for task {task_id}, is_rollback={is_rollback}, rollback_failed={rollback_failed}")

        if not memory_session_id:
            raise ValueError("memory_session_id is required for Validator Agent")
        if not finding_id:
            raise ValueError("finding_id is required for Validator Agent")
        if not resource_arn:
            raise ValueError("resource_arn is required for Validator Agent")
        if not resource_type:
            raise ValueError("resource_type is required for Validator Agent")
        if not control_id:
            raise ValueError("control_id is required for Validator Agent")

        config = get_config()
        # 优先使用 payload 中的 memory_id，否则使用环境变量
        memory_id = memory_id_from_payload or config.memory_id

        if not memory_id:
            logger.warning("memory_id is empty - Memory features will be disabled")
        # actor_id 已在上面解析

        # Create agent for this request
        agent = create_validator_agent(
            task_id=task_id,
            memory_session_id=memory_session_id,
            memory_id=memory_id,
            region=config.region,
            actor_id=actor_id
        )

        # Run validator
        # NOTE: generated_code and execution_result are retrieved from Memory by Validator Agent
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: run_validator(
                agent=agent,
                task_id=task_id,
                finding_id=finding_id,
                resource_arn=resource_arn,
                resource_type=resource_type,
                control_id=control_id,
                is_rollback=is_rollback,
                rollback_failed=rollback_failed,
                error_message=error_message
            )
        )

        # 构建响应数据
        response_data = {
            "success": result.get('success', False),
            "task_id": task_id,
            "finding_id": finding_id,
            "resource_arn": resource_arn,
            "is_rollback": is_rollback,
            "code_review_passed": result.get('code_review_passed', False),
            "validation_passed": result.get('validation_passed', False),
            "email_sent": result.get('email_sent', False),
            "validation_result": result.get('validation_result', {}),
            "response": result.get('response', ''),
            "session_id": session_id,
            "metadata": {
                "task_id": task_id,
                "agent_type": "validator",
                "success": result.get('success', False),
                "is_rollback": is_rollback,
                "a2a_source": "remediator" if is_a2a_call else None
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
