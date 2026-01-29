#!/usr/bin/env python3
"""
Strands Agent with Custom Tools Demo
展示如何创建带有自定义工具的 Agent
"""

import os
import json
import boto3
from strands import Agent, tool
from strands.models import BedrockModel

# 模型配置 - 使用跨区域推理配置文件 (APAC)
DEFAULT_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID",
    "apac.anthropic.claude-sonnet-4-20250514-v1:0"
)
DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-1")


# ============================================
# 自定义工具定义
# ============================================

@tool
def get_s3_bucket_info(bucket_name: str) -> str:
    """
    Get information about an S3 bucket including its configuration.

    Args:
        bucket_name: Name of the S3 bucket to query

    Returns:
        JSON string with bucket information
    """
    s3 = boto3.client('s3')

    result = {
        "bucket_name": bucket_name,
        "public_access_block": None,
        "versioning": None,
        "encryption": None,
        "error": None
    }

    try:
        # 获取 Public Access Block 配置
        try:
            pab = s3.get_public_access_block(Bucket=bucket_name)
            result["public_access_block"] = pab.get("PublicAccessBlockConfiguration", {})
        except s3.exceptions.NoSuchPublicAccessBlockConfiguration:
            result["public_access_block"] = "Not configured"

        # 获取版本控制状态
        try:
            versioning = s3.get_bucket_versioning(Bucket=bucket_name)
            result["versioning"] = versioning.get("Status", "Disabled")
        except Exception as e:
            result["versioning"] = f"Error: {str(e)}"

        # 获取加密配置
        try:
            encryption = s3.get_bucket_encryption(Bucket=bucket_name)
            result["encryption"] = encryption.get("ServerSideEncryptionConfiguration", {})
        except s3.exceptions.ClientError as e:
            if "ServerSideEncryptionConfigurationNotFoundError" in str(e):
                result["encryption"] = "Not configured"
            else:
                result["encryption"] = f"Error: {str(e)}"

    except Exception as e:
        result["error"] = str(e)

    return json.dumps(result, indent=2, default=str)


@tool
def get_security_group_rules(security_group_id: str) -> str:
    """
    Get inbound and outbound rules for a security group.

    Args:
        security_group_id: The ID of the security group (e.g., sg-12345678)

    Returns:
        JSON string with security group rules
    """
    ec2 = boto3.client('ec2')

    try:
        response = ec2.describe_security_groups(GroupIds=[security_group_id])

        if not response.get("SecurityGroups"):
            return json.dumps({"error": f"Security group {security_group_id} not found"})

        sg = response["SecurityGroups"][0]

        result = {
            "security_group_id": security_group_id,
            "group_name": sg.get("GroupName"),
            "description": sg.get("Description"),
            "vpc_id": sg.get("VpcId"),
            "inbound_rules": sg.get("IpPermissions", []),
            "outbound_rules": sg.get("IpPermissionsEgress", [])
        }

        return json.dumps(result, indent=2, default=str)

    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def list_iam_users() -> str:
    """
    List all IAM users in the account with their MFA status.

    Returns:
        JSON string with list of IAM users and their MFA status
    """
    iam = boto3.client('iam')

    try:
        users = []
        paginator = iam.get_paginator('list_users')

        for page in paginator.paginate():
            for user in page['Users']:
                user_info = {
                    "user_name": user['UserName'],
                    "user_id": user['UserId'],
                    "created": user['CreateDate'].isoformat(),
                    "has_mfa": False
                }

                # 检查 MFA 状态
                try:
                    mfa_devices = iam.list_mfa_devices(UserName=user['UserName'])
                    user_info["has_mfa"] = len(mfa_devices.get('MFADevices', [])) > 0
                except Exception:
                    pass

                users.append(user_info)

        return json.dumps({"users": users, "total_count": len(users)}, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)})


# ============================================
# Agent 创建
# ============================================

def create_security_agent():
    """创建带安全工具的 Agent"""

    print(f"Using model: {DEFAULT_MODEL_ID} in region: {DEFAULT_REGION}")

    model = BedrockModel(
        model_id=DEFAULT_MODEL_ID,
        region_name=DEFAULT_REGION,
        temperature=0.2,
        max_tokens=4096
    )

    agent = Agent(
        model=model,
        tools=[
            get_s3_bucket_info,
            get_security_group_rules,
            list_iam_users
        ],
        system_prompt="""
        You are a security analyst assistant with access to AWS security tools.

        Available tools:
        1. get_s3_bucket_info - Get S3 bucket security configuration
        2. get_security_group_rules - Get EC2 security group rules
        3. list_iam_users - List IAM users with MFA status

        When asked about AWS resources:
        1. Use the appropriate tool to gather information
        2. Analyze the results for security issues
        3. Provide clear recommendations

        Always explain what you found and any security concerns.
        """
    )

    return agent


def main():
    print("=" * 60)
    print("Strands Agent Demo - Agent with Tools")
    print("=" * 60)

    agent = create_security_agent()

    # 交互式对话
    print("\nAgent is ready. Type 'quit' to exit.")
    print("Example prompts:")
    print("  - Check the security of S3 bucket 'my-bucket'")
    print("  - Analyze security group sg-12345678")
    print("  - List all IAM users and their MFA status")
    print()

    while True:
        try:
            user_input = input("You: ").strip()

            if user_input.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break

            if not user_input:
                continue

            print("\nAssistant: ", end="")
            response = agent(user_input)
            print(response)
            print()

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}")


if __name__ == "__main__":
    main()
