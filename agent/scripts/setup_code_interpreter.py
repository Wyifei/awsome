#!/usr/bin/env python3
"""
Setup AgentCore Code Interpreter for SHARA

Prerequisites:
  - Run `terraform apply` first to create the IAM role
  - Then run this script to create the Code Interpreter resource

Usage:
  python setup_code_interpreter.py create [--role-arn <arn>]
  python setup_code_interpreter.py list
  python setup_code_interpreter.py delete <code-interpreter-id>
"""
import argparse
import json
import subprocess
import sys
import boto3
from botocore.exceptions import ClientError

# Configuration
REGION = "ap-northeast-1"
CODE_INTERPRETER_NAME = "shara-code-interpreter"


def get_terraform_output(output_name: str) -> str:
    """Get output value from Terraform state."""
    try:
        result = subprocess.run(
            ["terraform", "output", "-raw", output_name],
            capture_output=True,
            text=True,
            cwd="../infra"
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    return ""


def get_role_arn_from_terraform() -> str:
    """Get Code Interpreter role ARN from Terraform output."""
    role_arn = get_terraform_output("code_interpreter_role_arn")
    if role_arn:
        print(f"Found role ARN from Terraform: {role_arn}")
        return role_arn
    return ""


def create_code_interpreter(execution_role_arn: str, network_mode: str = "PUBLIC") -> dict:
    """Create Code Interpreter resource."""
    client = boto3.client(
        'bedrock-agentcore-control',
        region_name=REGION,
        endpoint_url=f"https://bedrock-agentcore-control.{REGION}.amazonaws.com"
    )

    try:
        print(f"Creating Code Interpreter: {CODE_INTERPRETER_NAME}")
        print(f"  Role ARN: {execution_role_arn}")
        print(f"  Network Mode: {network_mode}")

        response = client.create_code_interpreter(
            name=CODE_INTERPRETER_NAME,
            description="SHARA security remediation code executor - executes boto3 code in sandbox",
            executionRoleArn=execution_role_arn,
            networkConfiguration={
                "networkMode": network_mode
            }
        )

        code_interpreter_id = response.get('codeInterpreterId')
        code_interpreter_arn = response.get('codeInterpreterArn')
        status = response.get('status')

        print("")
        print("=" * 60)
        print("Code Interpreter Created Successfully!")
        print("=" * 60)
        print(f"  ID:     {code_interpreter_id}")
        print(f"  ARN:    {code_interpreter_arn}")
        print(f"  Status: {status}")
        print("")
        print("Add to your .env file:")
        print(f"  CODE_INTERPRETER_ID={code_interpreter_id}")
        print("")

        return {
            "id": code_interpreter_id,
            "arn": code_interpreter_arn,
            "status": status
        }

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ConflictException':
            print(f"Code Interpreter '{CODE_INTERPRETER_NAME}' already exists")
            # Try to get existing one
            return get_code_interpreter_by_name(CODE_INTERPRETER_NAME)
        else:
            print(f"Error creating Code Interpreter: {e}")
            raise


def get_code_interpreter_by_name(name: str) -> dict:
    """Get Code Interpreter by name."""
    client = boto3.client(
        'bedrock-agentcore-control',
        region_name=REGION,
        endpoint_url=f"https://bedrock-agentcore-control.{REGION}.amazonaws.com"
    )

    try:
        response = client.list_code_interpreters()
        for ci in response.get('codeInterpreters', []):
            if ci.get('name') == name:
                print(f"Found existing Code Interpreter: {ci.get('codeInterpreterId')}")
                return {
                    "id": ci.get('codeInterpreterId'),
                    "arn": ci.get('codeInterpreterArn'),
                    "status": ci.get('status')
                }
    except ClientError as e:
        print(f"Error listing Code Interpreters: {e}")

    return {}


def list_code_interpreters():
    """List all Code Interpreters."""
    client = boto3.client(
        'bedrock-agentcore-control',
        region_name=REGION,
        endpoint_url=f"https://bedrock-agentcore-control.{REGION}.amazonaws.com"
    )

    try:
        response = client.list_code_interpreters()
        interpreters = response.get('codeInterpreters', [])

        if not interpreters:
            print("No Code Interpreters found")
            return []

        print(f"Found {len(interpreters)} Code Interpreter(s):")
        print("-" * 60)
        for ci in interpreters:
            print(f"Name:   {ci.get('name')}")
            print(f"ID:     {ci.get('codeInterpreterId')}")
            print(f"ARN:    {ci.get('codeInterpreterArn')}")
            print(f"Status: {ci.get('status')}")
            print("-" * 60)

        return interpreters

    except ClientError as e:
        print(f"Error listing Code Interpreters: {e}")
        return []


def delete_code_interpreter(code_interpreter_id: str):
    """Delete a Code Interpreter."""
    client = boto3.client(
        'bedrock-agentcore-control',
        region_name=REGION,
        endpoint_url=f"https://bedrock-agentcore-control.{REGION}.amazonaws.com"
    )

    try:
        print(f"Deleting Code Interpreter: {code_interpreter_id}")
        client.delete_code_interpreter(codeInterpreterId=code_interpreter_id)
        print("Deleted successfully")
    except ClientError as e:
        print(f"Error deleting Code Interpreter: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Setup AgentCore Code Interpreter for SHARA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create using Terraform-created role
  python setup_code_interpreter.py create

  # Create with explicit role ARN
  python setup_code_interpreter.py create --role-arn arn:aws:iam::123456789012:role/shara-dev-code-interpreter-role

  # List existing Code Interpreters
  python setup_code_interpreter.py list

  # Delete a Code Interpreter
  python setup_code_interpreter.py delete <code-interpreter-id>
"""
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Create command
    create_parser = subparsers.add_parser('create', help='Create Code Interpreter')
    create_parser.add_argument(
        '--role-arn',
        help='IAM execution role ARN (auto-detected from Terraform if not specified)'
    )
    create_parser.add_argument(
        '--network-mode',
        choices=['PUBLIC', 'SANDBOX'],
        default='PUBLIC',
        help='Network mode (default: PUBLIC)'
    )

    # List command
    subparsers.add_parser('list', help='List Code Interpreters')

    # Delete command
    delete_parser = subparsers.add_parser('delete', help='Delete Code Interpreter')
    delete_parser.add_argument('code_interpreter_id', help='Code Interpreter ID to delete')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == 'create':
        # Get role ARN
        role_arn = args.role_arn
        if not role_arn:
            role_arn = get_role_arn_from_terraform()

        if not role_arn:
            print("Error: Could not find role ARN")
            print("")
            print("Please either:")
            print("  1. Run 'terraform apply' first in the infra directory")
            print("  2. Specify --role-arn explicitly")
            sys.exit(1)

        create_code_interpreter(role_arn, args.network_mode)

    elif args.command == 'list':
        list_code_interpreters()

    elif args.command == 'delete':
        delete_code_interpreter(args.code_interpreter_id)


if __name__ == "__main__":
    main()
