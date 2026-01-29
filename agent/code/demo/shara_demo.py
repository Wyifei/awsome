#!/usr/bin/env python3
"""
SHARA Agent Demo (Simplified)
简化版 SHARA 系统演示，展示多 Agent 协作流程
"""

import os
import json
from dataclasses import dataclass
from typing import Optional
from strands import Agent, tool
from strands.models import BedrockModel

# 模型配置 - 使用跨区域推理配置文件 (APAC)
DEFAULT_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID",
    "apac.anthropic.claude-sonnet-4-20250514-v1:0"
)
DEFAULT_REGION = os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-1")


# ============================================
# 数据模型
# ============================================

@dataclass
class SecurityFinding:
    """Security Hub Finding 简化模型"""
    id: str
    title: str
    severity: str
    resource_type: str
    resource_id: str
    description: str


# ============================================
# 模拟数据
# ============================================

MOCK_FINDINGS = [
    SecurityFinding(
        id="finding-001",
        title="S3 Bucket Public Access Enabled",
        severity="HIGH",
        resource_type="AwsS3Bucket",
        resource_id="arn:aws:s3:::my-insecure-bucket",
        description="S3 bucket has public access enabled which could lead to data exposure."
    ),
    SecurityFinding(
        id="finding-002",
        title="Security Group Allows Unrestricted SSH",
        severity="HIGH",
        resource_type="AwsEc2SecurityGroup",
        resource_id="sg-0123456789abcdef0",
        description="Security group allows inbound SSH (port 22) from 0.0.0.0/0."
    ),
    SecurityFinding(
        id="finding-003",
        title="IAM User Without MFA",
        severity="MEDIUM",
        resource_type="AwsIamUser",
        resource_id="arn:aws:iam::123456789012:user/developer",
        description="IAM user does not have MFA enabled."
    )
]


# ============================================
# 工具定义
# ============================================

@tool
def get_finding_details(finding_id: str) -> str:
    """
    Get details of a security finding.

    Args:
        finding_id: The ID of the finding to retrieve

    Returns:
        JSON string with finding details
    """
    for finding in MOCK_FINDINGS:
        if finding.id == finding_id:
            return json.dumps({
                "id": finding.id,
                "title": finding.title,
                "severity": finding.severity,
                "resource_type": finding.resource_type,
                "resource_id": finding.resource_id,
                "description": finding.description
            }, indent=2)

    return json.dumps({"error": f"Finding {finding_id} not found"})


@tool
def list_pending_findings() -> str:
    """
    List all pending security findings.

    Returns:
        JSON string with list of pending findings
    """
    findings = [
        {
            "id": f.id,
            "title": f.title,
            "severity": f.severity,
            "resource_type": f.resource_type
        }
        for f in MOCK_FINDINGS
    ]
    return json.dumps({"findings": findings, "count": len(findings)}, indent=2)


@tool
def generate_remediation_code(finding_id: str, resource_type: str, resource_id: str) -> str:
    """
    Generate Python/boto3 remediation code for a finding.

    Args:
        finding_id: The finding ID
        resource_type: Type of AWS resource
        resource_id: ARN or ID of the resource

    Returns:
        Generated Python code as string
    """
    # 模拟代码生成
    if resource_type == "AwsS3Bucket":
        bucket_name = resource_id.split(":")[-1]
        code = f'''
# Remediation for: {finding_id}
# Resource: {resource_id}

import boto3

def remediate_s3_public_access():
    s3 = boto3.client('s3')

    # Block public access
    s3.put_public_access_block(
        Bucket='{bucket_name}',
        PublicAccessBlockConfiguration={{
            'BlockPublicAcls': True,
            'IgnorePublicAcls': True,
            'BlockPublicPolicy': True,
            'RestrictPublicBuckets': True
        }}
    )

    print(f"Public access blocked for {bucket_name}")
    return {{"status": "success"}}

if __name__ == "__main__":
    remediate_s3_public_access()
'''
    elif resource_type == "AwsEc2SecurityGroup":
        code = f'''
# Remediation for: {finding_id}
# Resource: {resource_id}

import boto3

def remediate_security_group():
    ec2 = boto3.client('ec2')

    # Revoke unrestricted SSH access
    ec2.revoke_security_group_ingress(
        GroupId='{resource_id}',
        IpPermissions=[{{
            'IpProtocol': 'tcp',
            'FromPort': 22,
            'ToPort': 22,
            'IpRanges': [{{'CidrIp': '0.0.0.0/0'}}]
        }}]
    )

    print(f"Unrestricted SSH access revoked for {resource_id}")
    return {{"status": "success"}}

if __name__ == "__main__":
    remediate_security_group()
'''
    else:
        code = f"# No automated remediation available for {resource_type}"

    return code


@tool
def request_approval(finding_id: str, remediation_code: str, approver_email: str) -> str:
    """
    Request approval for remediation (simulation).

    Args:
        finding_id: The finding being remediated
        remediation_code: The generated code to execute
        approver_email: Email of the approver

    Returns:
        Approval request status
    """
    # 模拟审批请求
    return json.dumps({
        "status": "approval_requested",
        "finding_id": finding_id,
        "approver": approver_email,
        "message": f"Approval email sent to {approver_email}",
        "approval_link": f"https://shara.example.com/approve/{finding_id}"
    }, indent=2)


# ============================================
# Agent 定义
# ============================================

def create_orchestrator_agent():
    """创建 Orchestrator Agent"""

    print(f"Using model: {DEFAULT_MODEL_ID} in region: {DEFAULT_REGION}")

    model = BedrockModel(
        model_id=DEFAULT_MODEL_ID,
        region_name=DEFAULT_REGION,
        temperature=0.2,
        max_tokens=4096
    )

    return Agent(
        model=model,
        tools=[
            list_pending_findings,
            get_finding_details,
            generate_remediation_code,
            request_approval
        ],
        system_prompt="""
        You are the SHARA Orchestrator Agent responsible for managing security remediation tasks.

        Your workflow:
        1. Use list_pending_findings to see what needs attention
        2. Use get_finding_details to understand each finding
        3. Use generate_remediation_code to create fix code
        4. Use request_approval to send for human review

        Always:
        - Prioritize HIGH severity findings
        - Explain your reasoning
        - Show the generated code before requesting approval
        - Never execute code without approval
        """
    )


# ============================================
# 主程序
# ============================================

def main():
    print("=" * 60)
    print("SHARA Agent Demo (Simplified)")
    print("=" * 60)

    agent = create_orchestrator_agent()

    print("\nSHARA Orchestrator is ready.")
    print("This demo simulates the SHARA security remediation workflow.")
    print("\nExample commands:")
    print("  - Show me all pending security findings")
    print("  - Analyze finding-001 and generate remediation")
    print("  - Process the highest severity finding")
    print("\nType 'quit' to exit.\n")

    while True:
        try:
            user_input = input("Security Admin: ").strip()

            if user_input.lower() in ['quit', 'exit', 'q']:
                print("SHARA session ended.")
                break

            if not user_input:
                continue

            print("\n" + "─" * 60)
            print("SHARA Orchestrator:")
            print("─" * 60)

            response = agent(user_input)
            print(response)
            print()

        except KeyboardInterrupt:
            print("\nSHARA session ended.")
            break
        except Exception as e:
            print(f"\nError: {e}")


if __name__ == "__main__":
    main()
