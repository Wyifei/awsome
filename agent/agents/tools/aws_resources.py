"""
AWS Resource Tools - 获取 AWS 资源配置信息
"""
import logging
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from strands import tool

from agents.config import get_config

logger = logging.getLogger(__name__)


@tool
def get_s3_bucket_info(bucket_name: str) -> dict:
    """获取 S3 bucket 的完整配置信息。

    收集 bucket 的安全相关配置，包括公共访问设置、策略、ACL 和加密配置。
    用于分析 Finding 的上下文和生成修复方案。

    Args:
        bucket_name: S3 bucket 名称

    Returns:
        dict: Bucket 配置信息
            - bucket_name: str - Bucket 名称
            - public_access_block: dict - 公共访问阻止配置
            - bucket_policy: str - Bucket 策略 (JSON 字符串)
            - bucket_acl: dict - Bucket ACL
            - encryption: dict - 服务端加密配置
            - versioning: dict - 版本控制配置
            - error: str - 错误信息 (如有)
    """
    config = get_config()
    s3 = boto3.client('s3', region_name=config.region)

    info = {
        "bucket_name": bucket_name,
        "public_access_block": None,
        "bucket_policy": None,
        "bucket_acl": None,
        "encryption": None,
        "versioning": None,
        "logging": None
    }

    try:
        # Public Access Block
        try:
            response = s3.get_public_access_block(Bucket=bucket_name)
            info["public_access_block"] = response.get("PublicAccessBlockConfiguration")
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchPublicAccessBlockConfiguration':
                info["public_access_block"] = {
                    "BlockPublicAcls": False,
                    "IgnorePublicAcls": False,
                    "BlockPublicPolicy": False,
                    "RestrictPublicBuckets": False
                }
            else:
                logger.warning(f"Error getting public access block: {e}")

        # Bucket Policy
        try:
            response = s3.get_bucket_policy(Bucket=bucket_name)
            info["bucket_policy"] = response.get("Policy")
        except ClientError as e:
            if e.response['Error']['Code'] != 'NoSuchBucketPolicy':
                logger.warning(f"Error getting bucket policy: {e}")

        # Bucket ACL
        try:
            response = s3.get_bucket_acl(Bucket=bucket_name)
            info["bucket_acl"] = {
                "Owner": response.get("Owner"),
                "Grants": response.get("Grants")
            }
        except ClientError as e:
            logger.warning(f"Error getting bucket ACL: {e}")

        # Encryption
        try:
            response = s3.get_bucket_encryption(Bucket=bucket_name)
            info["encryption"] = response.get("ServerSideEncryptionConfiguration")
        except ClientError as e:
            if e.response['Error']['Code'] != 'ServerSideEncryptionConfigurationNotFoundError':
                logger.warning(f"Error getting bucket encryption: {e}")

        # Versioning
        try:
            response = s3.get_bucket_versioning(Bucket=bucket_name)
            info["versioning"] = {
                "Status": response.get("Status", "Disabled"),
                "MFADelete": response.get("MFADelete", "Disabled")
            }
        except ClientError as e:
            logger.warning(f"Error getting bucket versioning: {e}")

        # Logging
        try:
            response = s3.get_bucket_logging(Bucket=bucket_name)
            info["logging"] = response.get("LoggingEnabled")
        except ClientError as e:
            logger.warning(f"Error getting bucket logging: {e}")

        logger.info(f"Retrieved S3 bucket info for: {bucket_name}")
        return info

    except ClientError as e:
        logger.error(f"Error getting S3 bucket info: {e}")
        return {
            "bucket_name": bucket_name,
            "error": str(e)
        }


@tool
def get_security_group_rules(security_group_id: str) -> dict:
    """获取安全组规则详情。

    收集安全组的入站和出站规则，用于分析网络安全配置问题。

    Args:
        security_group_id: 安全组 ID (如 sg-0123456789abcdef0)

    Returns:
        dict: 安全组规则信息
            - group_id: str - 安全组 ID
            - group_name: str - 安全组名称
            - vpc_id: str - VPC ID
            - description: str - 安全组描述
            - inbound_rules: list - 入站规则列表
            - outbound_rules: list - 出站规则列表
            - tags: list - 标签
            - error: str - 错误信息 (如有)
    """
    config = get_config()
    ec2 = boto3.client('ec2', region_name=config.region)

    try:
        response = ec2.describe_security_groups(
            GroupIds=[security_group_id]
        )

        if not response.get('SecurityGroups'):
            return {
                "group_id": security_group_id,
                "error": "Security group not found"
            }

        sg = response['SecurityGroups'][0]

        # 分析入站规则中的危险配置
        risky_inbound = []
        for rule in sg.get('IpPermissions', []):
            for ip_range in rule.get('IpRanges', []):
                if ip_range.get('CidrIp') == '0.0.0.0/0':
                    risky_inbound.append({
                        "protocol": rule.get('IpProtocol'),
                        "from_port": rule.get('FromPort'),
                        "to_port": rule.get('ToPort'),
                        "cidr": ip_range.get('CidrIp'),
                        "description": ip_range.get('Description', '')
                    })

        result = {
            "group_id": sg['GroupId'],
            "group_name": sg.get('GroupName', ''),
            "vpc_id": sg.get('VpcId'),
            "description": sg.get('Description', ''),
            "inbound_rules": sg.get('IpPermissions', []),
            "outbound_rules": sg.get('IpPermissionsEgress', []),
            "tags": sg.get('Tags', []),
            "risky_inbound_rules": risky_inbound
        }

        logger.info(f"Retrieved security group info for: {security_group_id}")
        return result

    except ClientError as e:
        logger.error(f"Error getting security group info: {e}")
        return {
            "group_id": security_group_id,
            "error": str(e)
        }


@tool
def get_iam_role_info(role_name: str) -> dict:
    """获取 IAM Role 详情。

    收集 IAM Role 的信任策略和权限策略，用于分析权限配置问题。

    Args:
        role_name: IAM Role 名称

    Returns:
        dict: Role 信息
            - role_name: str - Role 名称
            - role_arn: str - Role ARN
            - assume_role_policy: dict - 信任策略
            - inline_policies: list - 内联策略名称列表
            - attached_policies: list - 附加的托管策略
            - permissions_boundary: dict - 权限边界 (如有)
            - error: str - 错误信息 (如有)
    """
    config = get_config()
    iam = boto3.client('iam', region_name=config.region)

    try:
        # 获取 Role 基本信息
        role_response = iam.get_role(RoleName=role_name)
        role = role_response['Role']

        # 获取内联策略列表
        inline_response = iam.list_role_policies(RoleName=role_name)
        inline_policies = inline_response.get('PolicyNames', [])

        # 获取附加的托管策略
        attached_response = iam.list_attached_role_policies(RoleName=role_name)
        attached_policies = attached_response.get('AttachedPolicies', [])

        # 分析信任策略中的危险配置
        trust_policy = role.get('AssumeRolePolicyDocument', {})
        risky_principals = []
        for statement in trust_policy.get('Statement', []):
            principal = statement.get('Principal', {})
            if principal == '*' or principal.get('AWS') == '*':
                risky_principals.append({
                    "effect": statement.get('Effect'),
                    "principal": principal,
                    "action": statement.get('Action')
                })

        result = {
            "role_name": role['RoleName'],
            "role_arn": role['Arn'],
            "role_id": role['RoleId'],
            "path": role.get('Path', '/'),
            "created_date": role.get('CreateDate', '').isoformat() if role.get('CreateDate') else None,
            "assume_role_policy": trust_policy,
            "inline_policies": inline_policies,
            "attached_policies": attached_policies,
            "permissions_boundary": role.get('PermissionsBoundary'),
            "max_session_duration": role.get('MaxSessionDuration'),
            "risky_trust_principals": risky_principals,
            "tags": role.get('Tags', [])
        }

        logger.info(f"Retrieved IAM role info for: {role_name}")
        return result

    except ClientError as e:
        logger.error(f"Error getting IAM role info: {e}")
        return {
            "role_name": role_name,
            "error": str(e)
        }


@tool
def get_rds_instance_info(db_instance_identifier: str) -> dict:
    """获取 RDS 实例详情。

    收集 RDS 实例的安全配置，包括加密、公开访问、安全组等。

    Args:
        db_instance_identifier: RDS 实例标识符

    Returns:
        dict: RDS 实例信息
    """
    config = get_config()
    rds = boto3.client('rds', region_name=config.region)

    try:
        response = rds.describe_db_instances(
            DBInstanceIdentifier=db_instance_identifier
        )

        if not response.get('DBInstances'):
            return {
                "db_instance_identifier": db_instance_identifier,
                "error": "RDS instance not found"
            }

        instance = response['DBInstances'][0]

        result = {
            "db_instance_identifier": instance['DBInstanceIdentifier'],
            "db_instance_arn": instance['DBInstanceArn'],
            "engine": instance.get('Engine'),
            "engine_version": instance.get('EngineVersion'),
            "publicly_accessible": instance.get('PubliclyAccessible', False),
            "storage_encrypted": instance.get('StorageEncrypted', False),
            "kms_key_id": instance.get('KmsKeyId'),
            "vpc_security_groups": instance.get('VpcSecurityGroups', []),
            "db_subnet_group": instance.get('DBSubnetGroup', {}).get('DBSubnetGroupName'),
            "multi_az": instance.get('MultiAZ', False),
            "auto_minor_version_upgrade": instance.get('AutoMinorVersionUpgrade', False),
            "backup_retention_period": instance.get('BackupRetentionPeriod', 0),
            "deletion_protection": instance.get('DeletionProtection', False),
            "iam_database_authentication_enabled": instance.get('IAMDatabaseAuthenticationEnabled', False)
        }

        logger.info(f"Retrieved RDS instance info for: {db_instance_identifier}")
        return result

    except ClientError as e:
        logger.error(f"Error getting RDS instance info: {e}")
        return {
            "db_instance_identifier": db_instance_identifier,
            "error": str(e)
        }
