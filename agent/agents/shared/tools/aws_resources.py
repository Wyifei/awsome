"""
AWS Resource Tools - 通用 AWS 资源配置查询工具

使用 AWS Cloud Control API 查询任意资源配置。
"""
import json
import logging
import re
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from strands import tool

from shared.config import get_config

logger = logging.getLogger(__name__)


# Security Hub 资源类型到 CloudFormation 资源类型的映射
SECURITY_HUB_TO_CFN_TYPE_MAP = {
    # Compute
    "AwsEc2Instance": "AWS::EC2::Instance",
    "AwsEc2SecurityGroup": "AWS::EC2::SecurityGroup",
    "AwsEc2Volume": "AWS::EC2::Volume",
    "AwsEc2Vpc": "AWS::EC2::VPC",
    "AwsEc2Subnet": "AWS::EC2::Subnet",
    "AwsEc2NetworkInterface": "AWS::EC2::NetworkInterface",
    "AwsEc2NetworkAcl": "AWS::EC2::NetworkAcl",
    "AwsEc2RouteTable": "AWS::EC2::RouteTable",
    "AwsEc2Eip": "AWS::EC2::EIP",
    "AwsEc2LaunchTemplate": "AWS::EC2::LaunchTemplate",
    "AwsAutoScalingAutoScalingGroup": "AWS::AutoScaling::AutoScalingGroup",
    "AwsAutoScalingLaunchConfiguration": "AWS::AutoScaling::LaunchConfiguration",

    # Storage
    "AwsS3Bucket": "AWS::S3::Bucket",
    "AwsEfsFileSystem": "AWS::EFS::FileSystem",

    # Database
    "AwsRdsDbInstance": "AWS::RDS::DBInstance",
    "AwsRdsDbCluster": "AWS::RDS::DBCluster",
    "AwsRdsDbSnapshot": "AWS::RDS::DBSnapshot",
    "AwsRdsDbClusterSnapshot": "AWS::RDS::DBClusterSnapshot",
    "AwsDynamoDbTable": "AWS::DynamoDB::Table",
    "AwsElastiCacheCacheCluster": "AWS::ElastiCache::CacheCluster",
    "AwsRedshiftCluster": "AWS::Redshift::Cluster",

    # IAM
    "AwsIamRole": "AWS::IAM::Role",
    "AwsIamUser": "AWS::IAM::User",
    "AwsIamGroup": "AWS::IAM::Group",
    "AwsIamPolicy": "AWS::IAM::Policy",
    "AwsIamAccessKey": "AWS::IAM::AccessKey",

    # Lambda
    "AwsLambdaFunction": "AWS::Lambda::Function",
    "AwsLambdaLayerVersion": "AWS::Lambda::LayerVersion",

    # Networking
    "AwsElbLoadBalancer": "AWS::ElasticLoadBalancing::LoadBalancer",
    "AwsElbv2LoadBalancer": "AWS::ElasticLoadBalancingV2::LoadBalancer",
    "AwsApiGatewayRestApi": "AWS::ApiGateway::RestApi",
    "AwsApiGatewayStage": "AWS::ApiGateway::Stage",
    "AwsApiGatewayV2Api": "AWS::ApiGatewayV2::Api",
    "AwsCloudFrontDistribution": "AWS::CloudFront::Distribution",
    "AwsRoute53HostedZone": "AWS::Route53::HostedZone",

    # Security
    "AwsKmsKey": "AWS::KMS::Key",
    "AwsSecretsManagerSecret": "AWS::SecretsManager::Secret",
    "AwsAcmCertificate": "AWS::CertificateManager::Certificate",
    "AwsWafWebAcl": "AWS::WAFv2::WebACL",

    # Container
    "AwsEcsCluster": "AWS::ECS::Cluster",
    "AwsEcsService": "AWS::ECS::Service",
    "AwsEcsTaskDefinition": "AWS::ECS::TaskDefinition",
    "AwsEcrRepository": "AWS::ECR::Repository",
    "AwsEksCluster": "AWS::EKS::Cluster",

    # Monitoring & Logging
    "AwsCloudTrailTrail": "AWS::CloudTrail::Trail",
    "AwsLogsLogGroup": "AWS::Logs::LogGroup",
    "AwsCloudWatchAlarm": "AWS::CloudWatch::Alarm",
    "AwsSnsSubscription": "AWS::SNS::Subscription",
    "AwsSnsTopic": "AWS::SNS::Topic",
    "AwsSqsQueue": "AWS::SQS::Queue",

    # Config & SSM
    "AwsConfigConfigRule": "AWS::Config::ConfigRule",
    "AwsSsmManagedInstanceInventory": "AWS::SSM::ManagedInstanceInventory",
    "AwsSsmPatchCompliance": "AWS::SSM::PatchCompliance",

    # Other
    "AwsCodeBuildProject": "AWS::CodeBuild::Project",
    "AwsSageMakerNotebookInstance": "AWS::SageMaker::NotebookInstance",
    "AwsStepFunctionActivity": "AWS::StepFunctions::Activity",
    "AwsBackupBackupVault": "AWS::Backup::BackupVault",
}

# Cloud Control API 标识符类型映射
# "arn" = 使用完整 ARN
# "name" = 使用资源名称 (ARN 最后一部分，/ 或 : 分隔)
# "id" = 使用资源 ID (如 sg-xxx, i-xxx)
IDENTIFIER_TYPE_MAP = {
    "AWS::SNS::Topic": "arn",
    "AWS::SQS::Queue": "arn",
    "AWS::S3::Bucket": "name",
    "AWS::IAM::Role": "name",
    "AWS::IAM::User": "name",
    "AWS::IAM::Group": "name",
    "AWS::IAM::Policy": "arn",
    "AWS::Lambda::Function": "name",
    "AWS::DynamoDB::Table": "name",
    "AWS::EC2::SecurityGroup": "id",
    "AWS::EC2::Instance": "id",
    "AWS::EC2::Volume": "id",
    "AWS::EC2::VPC": "id",
    "AWS::EC2::Subnet": "id",
    "AWS::RDS::DBInstance": "name",
    "AWS::RDS::DBCluster": "name",
    "AWS::KMS::Key": "id",
    "AWS::Logs::LogGroup": "name",
    "AWS::ECS::Cluster": "name",
    "AWS::EKS::Cluster": "name",
    "AWS::ECR::Repository": "name",
    "AWS::SecretsManager::Secret": "arn",
    "AWS::CloudTrail::Trail": "name",
}


def _extract_identifier_from_arn(arn: str, cfn_type: str) -> str:
    """从 ARN 中提取 Cloud Control API 所需的标识符。

    根据 IDENTIFIER_TYPE_MAP 配置，提取适当的标识符格式。

    Args:
        arn: 完整的 AWS ARN
        cfn_type: CloudFormation 资源类型

    Returns:
        str: Cloud Control API 标识符
    """
    if not arn or not arn.startswith('arn:'):
        return arn

    identifier_type = IDENTIFIER_TYPE_MAP.get(cfn_type, "name")

    if identifier_type == "arn":
        # 使用完整 ARN
        return arn

    # 解析 ARN: arn:partition:service:region:account:resource
    parts = arn.split(':')
    if len(parts) < 6:
        return arn

    resource_part = ':'.join(parts[5:])

    if identifier_type == "id":
        # 提取资源 ID (如 security-group/sg-xxx -> sg-xxx)
        if '/' in resource_part:
            return resource_part.split('/')[-1]
        return resource_part

    # identifier_type == "name"
    # 提取资源名称
    if '/' in resource_part:
        return resource_part.split('/')[-1]
    if ':' in resource_part:
        # 处理如 function:my-function 或 db:my-db 格式
        return resource_part.split(':')[-1]
    return resource_part


@tool
def get_resource_config(resource_arn: str, resource_type: str) -> dict:
    """使用 Cloud Control API 查询 AWS 资源配置。

    这是一个通用工具，可以查询任何 Security Hub Finding 中的资源。
    直接传入 Finding 中的 Resources[].Id (ARN) 和 Resources[].Type。

    Args:
        resource_arn: 资源 ARN，直接从 Finding 的 Resources[].Id 获取
        resource_type: Security Hub 资源类型，从 Finding 的 Resources[].Type 获取
                      (如 AwsS3Bucket, AwsSnsTopic, AwsEc2SecurityGroup)

    Returns:
        dict: 资源配置信息
            - status: str - "found" 或 "not_found" 或 "error"
            - resource_type: str - 资源类型
            - resource_arn: str - 资源 ARN
            - identifier: str - Cloud Control API 使用的标识符
            - properties: dict - 资源属性配置 (如果找到)
            - error: str - 错误信息 (如有)

    Examples:
        # 直接使用 Finding 中的数据
        get_resource_config(
            resource_arn="arn:aws:sns:ap-northeast-1:123456789012:my-topic",
            resource_type="AwsSnsTopic"
        )

        get_resource_config(
            resource_arn="arn:aws:s3:::my-bucket",
            resource_type="AwsS3Bucket"
        )

        get_resource_config(
            resource_arn="arn:aws:ec2:ap-northeast-1:123456789012:security-group/sg-12345",
            resource_type="AwsEc2SecurityGroup"
        )
    """
    config = get_config()
    cloudcontrol = boto3.client('cloudcontrol', region_name=config.region)

    # 转换 Security Hub 类型到 CloudFormation 类型
    cfn_type = SECURITY_HUB_TO_CFN_TYPE_MAP.get(resource_type)
    if not cfn_type:
        logger.warning(f"Unknown Security Hub resource type: {resource_type}")
        return {
            "status": "error",
            "resource_type": resource_type,
            "resource_arn": resource_arn,
            "error": f"不支持的资源类型: {resource_type}"
        }

    # 从 ARN 提取 Cloud Control API 所需的标识符
    identifier = _extract_identifier_from_arn(resource_arn, cfn_type)

    logger.info(f"Querying resource via Cloud Control API: type={cfn_type}, identifier={identifier}")

    try:
        response = cloudcontrol.get_resource(
            TypeName=cfn_type,
            Identifier=identifier
        )

        resource_desc = response.get('ResourceDescription', {})
        properties_str = resource_desc.get('Properties', '{}')

        try:
            properties = json.loads(properties_str)
        except json.JSONDecodeError:
            properties = {"raw": properties_str}

        logger.info(f"Resource found: {cfn_type}/{identifier}")

        return {
            "status": "found",
            "resource_type": resource_type,
            "cfn_type": cfn_type,
            "resource_arn": resource_arn,
            "identifier": identifier,
            "properties": properties
        }

    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', '')
        error_message = e.response.get('Error', {}).get('Message', str(e))

        logger.warning(f"Cloud Control API error: {error_code} - {error_message}")

        if error_code == 'ResourceNotFoundException':
            return {
                "status": "not_found",
                "resource_type": resource_type,
                "cfn_type": cfn_type,
                "resource_arn": resource_arn,
                "identifier": identifier,
                "error": f"资源不存在: {identifier}",
                "possible_reasons": [
                    "资源已被删除",
                    "资源 ARN 不正确",
                    "跨账户/跨区域访问权限不足",
                    "Finding 数据可能已过期"
                ]
            }
        elif error_code == 'UnsupportedActionException':
            return {
                "status": "error",
                "resource_type": resource_type,
                "cfn_type": cfn_type,
                "resource_arn": resource_arn,
                "identifier": identifier,
                "error": f"Cloud Control API 不支持查询此资源类型: {cfn_type}"
            }
        else:
            return {
                "status": "error",
                "resource_type": resource_type,
                "cfn_type": cfn_type,
                "resource_arn": resource_arn,
                "identifier": identifier,
                "error": f"{error_code}: {error_message}"
            }

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return {
            "status": "error",
            "resource_type": resource_type,
            "resource_arn": resource_arn,
            "identifier": identifier,
            "error": str(e)
        }
