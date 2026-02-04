"""
A2A Tools - Agent-to-Agent Communication Tools

Provides tools for inter-agent communication via AgentCore InvokeAgentRuntime API.

IMPORTANT: In AgentCore Runtime, agents cannot directly communicate via HTTP.
The correct way is to use boto3 bedrock-agentcore client's invoke_agent_runtime API.
"""
import json
import logging
import os
from typing import Optional

import boto3
from botocore.exceptions import ClientError, BotoCoreError
from strands import tool

from shared.config import get_config

logger = logging.getLogger(__name__)


@tool
def invoke_validator_agent(
    task_id: str,
    resource_arn: str,
    resource_type: str,
    control_id: str,
    finding_id: str,
    memory_session_id: str,
    actor_id: str,
    is_rollback: bool = False,
    rollback_failed: bool = False,
    error_message: str = "",
    remediation_type: str = "aws_api"
) -> dict:
    """Through AgentCore Runtime API, invoke Validator Agent for code review and result verification.

    After Remediator completes execution, call Validator Agent to:
    1. Get results from Memory (NOT passed as parameters)
       - aws_api mode: get generated_code and execution_result via get_remediation_result
       - github_pr mode: get pr_info and files_changed via get_pr_result
    2. Review/verify results
    3. Update Security Hub Finding status
    4. Save experience to LTM
    5. Trigger result email

    NOTE: Validator retrieves results from Memory.
    Remediator must call save_remediation_result (aws_api) or save_pr_result (github_pr) before invoking this tool.

    This tool uses the AgentCore InvokeAgentRuntime API (not direct HTTP) because:
    - Agents in AgentCore Runtime cannot directly communicate via HTTP
    - The InvokeAgentRuntime API provides proper authentication and routing
    - This follows the official multi-agent pattern from AgentCore documentation

    Args:
        task_id: Task ID
        resource_arn: Resource ARN
        resource_type: Resource type (e.g., AwsS3Bucket, AwsEcrContainerImage)
        control_id: Security Hub Control ID (e.g., S3.8) - empty for container CVE
        finding_id: Security Hub Finding ID
        memory_session_id: Memory Session ID for context sharing
        actor_id: Actor ID for Memory operations
        is_rollback: Whether this is a rollback operation (rollback emails don't have rollback link)
        rollback_failed: Whether the rollback operation failed (e.g., rollback data not found)
        error_message: Error message to include in the notification email
        remediation_type: Type of remediation ("aws_api" or "github_pr")

    Returns:
        dict: Validator Agent response including:
            - success: bool - Whether A2A call succeeded
            - code_review: dict - Code security review results (aws_api mode)
            - pr_verified: bool - Whether PR was verified (github_pr mode)
            - verification: dict - Execution result verification
            - security_hub_update: dict - Security Hub update status
            - experience_saved: dict - LTM save status
            - result_email: dict - Email send status
            - error: str - Error message if failed
    """
    config = get_config()

    # Get Validator Runtime ARN from environment
    # Priority: VALIDATOR_RUNTIME_ARN (new) > VALIDATOR_RUNTIME_URL (legacy for local dev)
    validator_arn = os.environ.get('VALIDATOR_RUNTIME_ARN')
    validator_url = os.environ.get('VALIDATOR_RUNTIME_URL')

    # Check if we're running in AgentCore Runtime (has ARN) or local development (has URL)
    is_agentcore_runtime = bool(validator_arn)

    if not validator_arn and not validator_url:
        logger.error("Neither VALIDATOR_RUNTIME_ARN nor VALIDATOR_RUNTIME_URL is configured")
        return {
            "success": False,
            "error": "Validator Agent not configured. Set VALIDATOR_RUNTIME_ARN (for AgentCore) or VALIDATOR_RUNTIME_URL (for local dev)."
        }

    # Build A2A request payload
    # NOTE: Results are retrieved from Memory by Validator:
    # - aws_api mode: get_remediation_result (generated_code, execution_result)
    # - github_pr mode: get_pr_result (pr_info, files_changed)
    a2a_payload = {
        "task_id": task_id,
        "resource_arn": resource_arn,
        "resource_type": resource_type,
        "control_id": control_id,
        "finding_id": finding_id,
        "memory_session_id": memory_session_id,
        "memory_id": config.memory_id,
        "actor_id": actor_id,
        "is_rollback": is_rollback,
        "rollback_failed": rollback_failed,
        "error_message": error_message,
        "remediation_type": remediation_type
    }

    logger.info(f"Invoking Validator Agent for task {task_id}, is_rollback={is_rollback}")

    if is_agentcore_runtime:
        # Use AgentCore InvokeAgentRuntime API (production mode)
        return _invoke_via_agentcore_api(validator_arn, a2a_payload, task_id, config.region)
    else:
        # Use direct HTTP call (local development mode)
        return _invoke_via_http(validator_url, a2a_payload, task_id)


def _invoke_via_agentcore_api(validator_arn: str, payload: dict, task_id: str, region: str) -> dict:
    """Invoke Validator Agent using AgentCore InvokeAgentRuntime API.

    This is the correct way to invoke another agent in AgentCore Runtime.
    Agents cannot directly communicate via HTTP in AgentCore Runtime.

    Args:
        validator_arn: The ARN of the Validator Agent Runtime
        payload: The request payload to send
        task_id: Task ID for logging
        region: AWS region

    Returns:
        dict: Response from Validator Agent
    """
    logger.info(f"Invoking Validator Agent via AgentCore API: {validator_arn}")

    try:
        # Create bedrock-agentcore client
        agentcore_client = boto3.client('bedrock-agentcore', region_name=region)

        # Invoke the validator agent runtime
        # The payload is sent as JSON string in the 'payload' parameter
        response = agentcore_client.invoke_agent_runtime(
            agentRuntimeArn=validator_arn,
            qualifier="DEFAULT",
            payload=json.dumps(payload)
        )

        # Handle the response based on content type
        content_type = response.get("contentType", "")
        logger.info(f"Validator response content type: {content_type}")

        if "text/event-stream" in content_type:
            # Handle streaming response (Server-Sent Events)
            result_text = ""
            for line in response["response"].iter_lines(chunk_size=1024):
                if line:
                    line_str = line.decode("utf-8")
                    # Remove 'data: ' prefix if present
                    if line_str.startswith("data: "):
                        line_str = line_str[6:]
                    result_text += line_str

            # Try to parse as JSON
            try:
                result = json.loads(result_text)
            except json.JSONDecodeError:
                result = {"response": result_text}

        elif content_type == "application/json":
            # Handle JSON response
            content = []
            for chunk in response.get("response", []):
                content.append(chunk.decode('utf-8'))
            result = json.loads(''.join(content))

        else:
            # Handle other response types
            response_body = response['response'].read()
            result_text = response_body.decode('utf-8')
            try:
                result = json.loads(result_text)
            except json.JSONDecodeError:
                result = {"response": result_text}

        logger.info(f"Validator Agent response received for task {task_id}")

        return {
            "success": True,
            "validator_response": result
        }

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', str(e))
        logger.error(f"AgentCore API error invoking Validator: {error_code} - {error_message}")
        return {
            "success": False,
            "error": f"AgentCore API error ({error_code}): {error_message}"
        }

    except BotoCoreError as e:
        logger.error(f"BotoCore error invoking Validator: {e}")
        return {
            "success": False,
            "error": f"AWS SDK error: {str(e)}"
        }

    except Exception as e:
        logger.exception(f"Unexpected error invoking Validator via AgentCore API: {e}")
        return {
            "success": False,
            "error": f"Failed to invoke Validator Agent: {str(e)}"
        }


def _invoke_via_http(validator_url: str, payload: dict, task_id: str) -> dict:
    """Invoke Validator Agent using direct HTTP call (for local development only).

    WARNING: This method only works in local development with Docker Compose.
    In AgentCore Runtime, agents cannot directly communicate via HTTP.

    Args:
        validator_url: The HTTP URL of the Validator Agent (e.g., http://validator:8080)
        payload: The request payload to send
        task_id: Task ID for logging

    Returns:
        dict: Response from Validator Agent
    """
    import httpx

    logger.info(f"Invoking Validator Agent via HTTP (local dev): {validator_url}")
    logger.warning("Direct HTTP invocation is only for local development. Use VALIDATOR_RUNTIME_ARN in AgentCore Runtime.")

    try:
        # Make HTTP call to Validator runtime (local development only)
        with httpx.Client(timeout=300.0) as client:
            response = client.post(
                f"{validator_url}/invocations",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-A2A-Source": "remediator-agent",
                    "X-Task-Id": task_id
                }
            )
            response.raise_for_status()

            result = response.json()
            logger.info(f"Validator Agent response received for task {task_id}")

            return {
                "success": True,
                "validator_response": result
            }

    except httpx.TimeoutException as e:
        logger.error(f"HTTP call to Validator timed out: {e}")
        return {
            "success": False,
            "error": "Validator Agent call timed out after 300 seconds"
        }

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP call to Validator failed with HTTP error: {e}")
        return {
            "success": False,
            "error": f"HTTP error {e.response.status_code}: {e.response.text}"
        }

    except Exception as e:
        logger.exception(f"HTTP call to Validator failed: {e}")
        return {
            "success": False,
            "error": f"Failed to invoke Validator Agent: {str(e)}"
        }
