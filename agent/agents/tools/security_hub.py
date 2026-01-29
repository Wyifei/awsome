"""
Security Hub Tools - Security Hub 交互工具
"""
import logging
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from strands import tool

from agents.config import get_config

logger = logging.getLogger(__name__)


@tool
def update_security_hub_finding(
    finding_id: str,
    workflow_status: str = "RESOLVED",
    note: Optional[str] = None
) -> dict:
    """更新 Security Hub Finding 状态。

    修复完成并验证后，更新 Finding 的工作流状态为 RESOLVED。

    Args:
        finding_id: Finding ID (ARN 格式)
        workflow_status: 新状态，可选值:
            - RESOLVED: 已解决
            - NOTIFIED: 已通知
            - SUPPRESSED: 已抑制
        note: 状态说明备注

    Returns:
        dict: 更新结果
            - updated: bool - 是否更新成功
            - finding_id: str - Finding ID
            - new_status: str - 新状态
            - error: str - 错误信息 (如有)
    """
    config = get_config()
    securityhub = boto3.client('securityhub', region_name=config.region)

    try:
        # 从 Finding ID 提取 Product ARN
        # Finding ID 格式: arn:aws:securityhub:region:account:subscription/product/finding-id
        parts = finding_id.split('/')
        if len(parts) >= 2:
            product_arn = '/'.join(finding_id.split('/')[:-1])
        else:
            # 尝试另一种格式
            product_arn = finding_id.rsplit('/', 1)[0]

        logger.info(f"Updating finding {finding_id} to status {workflow_status}")

        response = securityhub.batch_update_findings(
            FindingIdentifiers=[{
                'Id': finding_id,
                'ProductArn': product_arn
            }],
            Workflow={'Status': workflow_status},
            Note={
                'Text': note or f'Remediated by SHARA - Status: {workflow_status}',
                'UpdatedBy': 'SHARA'
            }
        )

        processed = response.get('ProcessedFindings', [])
        unprocessed = response.get('UnprocessedFindings', [])

        if processed:
            logger.info(f"Successfully updated finding: {finding_id}")
            return {
                "updated": True,
                "finding_id": finding_id,
                "new_status": workflow_status
            }
        elif unprocessed:
            error_msg = unprocessed[0].get('ErrorMessage', 'Unknown error')
            logger.error(f"Failed to update finding: {error_msg}")
            return {
                "updated": False,
                "finding_id": finding_id,
                "error": error_msg
            }
        else:
            return {
                "updated": False,
                "finding_id": finding_id,
                "error": "No response from Security Hub"
            }

    except ClientError as e:
        logger.error(f"Error updating Security Hub finding: {e}")
        return {
            "updated": False,
            "finding_id": finding_id,
            "error": str(e)
        }


@tool
def verify_resource_state(
    resource_arn: str,
    resource_type: str,
    expected_state: dict
) -> dict:
    """验证资源当前状态是否符合预期。

    修复执行后，检查资源的实际状态是否与预期的安全配置一致。

    Args:
        resource_arn: 资源 ARN
        resource_type: 资源类型 (如 AwsS3Bucket, AwsEc2SecurityGroup)
        expected_state: 预期的资源状态配置

    Returns:
        dict: 验证结果
            - passed: bool - 是否验证通过
            - checks: list - 各项检查结果
            - error: str - 错误信息 (如有)
    """
    config = get_config()
    checks = []

    try:
        if resource_type == 'AwsS3Bucket':
            checks = _verify_s3_bucket(resource_arn, expected_state, config.region)
        elif resource_type == 'AwsEc2SecurityGroup':
            checks = _verify_security_group(resource_arn, expected_state, config.region)
        elif resource_type == 'AwsIamRole':
            checks = _verify_iam_role(resource_arn, expected_state, config.region)
        else:
            logger.warning(f"Unsupported resource type for verification: {resource_type}")
            return {
                "passed": False,
                "checks": [],
                "error": f"Unsupported resource type: {resource_type}"
            }

        all_passed = all(c.get('passed', False) for c in checks)

        logger.info(f"Verification {'passed' if all_passed else 'failed'} for {resource_arn}")

        return {
            "passed": all_passed,
            "checks": checks,
            "resource_arn": resource_arn,
            "resource_type": resource_type
        }

    except Exception as e:
        logger.exception(f"Error verifying resource state: {e}")
        return {
            "passed": False,
            "checks": checks,
            "error": str(e)
        }


def _verify_s3_bucket(resource_arn: str, expected_state: dict, region: str) -> list:
    """验证 S3 Bucket 状态"""
    s3 = boto3.client('s3', region_name=region)
    checks = []

    # 从 ARN 提取 bucket 名称
    bucket_name = resource_arn.split(':')[-1]

    try:
        actual = s3.get_public_access_block(Bucket=bucket_name)
        config = actual.get('PublicAccessBlockConfiguration', {})

        for key, expected_value in expected_state.items():
            actual_value = config.get(key)
            checks.append({
                "name": key,
                "expected": expected_value,
                "actual": actual_value,
                "passed": actual_value == expected_value
            })

    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchPublicAccessBlockConfiguration':
            # 没有配置公共访问阻止
            for key, expected_value in expected_state.items():
                checks.append({
                    "name": key,
                    "expected": expected_value,
                    "actual": False,
                    "passed": False
                })
        else:
            checks.append({
                "name": "PublicAccessBlock",
                "expected": "configured",
                "actual": f"error: {str(e)}",
                "passed": False
            })

    return checks


def _verify_security_group(resource_arn: str, expected_state: dict, region: str) -> list:
    """验证 Security Group 状态"""
    ec2 = boto3.client('ec2', region_name=region)
    checks = []

    # 从 ARN 提取安全组 ID
    sg_id = resource_arn.split('/')[-1]

    try:
        response = ec2.describe_security_groups(GroupIds=[sg_id])
        if not response.get('SecurityGroups'):
            checks.append({
                "name": "SecurityGroupExists",
                "expected": True,
                "actual": False,
                "passed": False
            })
            return checks

        sg = response['SecurityGroups'][0]

        # 检查是否移除了 0.0.0.0/0 的危险入站规则
        if expected_state.get('no_unrestricted_inbound'):
            has_unrestricted = False
            for rule in sg.get('IpPermissions', []):
                for ip_range in rule.get('IpRanges', []):
                    if ip_range.get('CidrIp') == '0.0.0.0/0':
                        has_unrestricted = True
                        break

            checks.append({
                "name": "NoUnrestrictedInbound",
                "expected": True,
                "actual": not has_unrestricted,
                "passed": not has_unrestricted
            })

    except ClientError as e:
        checks.append({
            "name": "SecurityGroup",
            "expected": "accessible",
            "actual": f"error: {str(e)}",
            "passed": False
        })

    return checks


def _verify_iam_role(resource_arn: str, expected_state: dict, region: str) -> list:
    """验证 IAM Role 状态"""
    iam = boto3.client('iam', region_name=region)
    checks = []

    # 从 ARN 提取 role 名称
    role_name = resource_arn.split('/')[-1]

    try:
        response = iam.get_role(RoleName=role_name)
        role = response['Role']
        trust_policy = role.get('AssumeRolePolicyDocument', {})

        # 检查是否移除了不安全的信任策略
        if expected_state.get('no_wildcard_principal'):
            has_wildcard = False
            for statement in trust_policy.get('Statement', []):
                principal = statement.get('Principal', {})
                if principal == '*' or principal.get('AWS') == '*':
                    has_wildcard = True
                    break

            checks.append({
                "name": "NoWildcardPrincipal",
                "expected": True,
                "actual": not has_wildcard,
                "passed": not has_wildcard
            })

    except ClientError as e:
        checks.append({
            "name": "IAMRole",
            "expected": "accessible",
            "actual": f"error: {str(e)}",
            "passed": False
        })

    return checks
