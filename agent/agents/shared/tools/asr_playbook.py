"""
ASR Playbook Tools - 从 S3 获取 ASR 预置修复方案
"""
import json
import logging
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from strands import tool

from shared.config import get_config

logger = logging.getLogger(__name__)


@tool
def fetch_asr_playbook(control_id: str) -> dict:
    """从 S3 获取 ASR 预置修复方案。

    通过 Control ID 精确匹配 ASR (AWS Automated Security Response) 预置的修复方案。
    ASR 方案包含经过验证的修复步骤和代码模板。

    Args:
        control_id: Security Hub Control ID (如 S3.1, EC2.19, IAM.3)

    Returns:
        dict: ASR Playbook 内容，包含:
            - matched: bool - 是否找到匹配的 playbook
            - playbook_id: str - Playbook ID (如匹配)
            - playbook: dict - Playbook 详情 (如匹配)
            - is_destructive: bool - 是否为破坏性操作
            - error: str - 错误信息 (如有)
    """
    config = get_config()
    s3 = boto3.client('s3', region_name=config.region)

    try:
        # 1. 读取索引文件
        logger.info(f"Fetching ASR index from s3://{config.asr_playbooks_bucket}/index.json")
        index_obj = s3.get_object(
            Bucket=config.asr_playbooks_bucket,
            Key="index.json"
        )
        index = json.loads(index_obj['Body'].read().decode('utf-8'))

        # 2. 查找匹配的 Control
        match = next(
            (c for c in index.get('controls', []) if c['control_id'] == control_id),
            None
        )

        if not match:
            logger.info(f"No ASR playbook found for control_id: {control_id}")
            return {
                "matched": False,
                "control_id": control_id,
                "message": f"No ASR playbook available for {control_id}"
            }

        # 3. 获取 Playbook 详情
        playbook_key = f"{match['path']}/{match['experience_id']}.json"
        logger.info(f"Fetching playbook from s3://{config.asr_playbooks_bucket}/{playbook_key}")

        playbook_obj = s3.get_object(
            Bucket=config.asr_playbooks_bucket,
            Key=playbook_key
        )
        playbook = json.loads(playbook_obj['Body'].read().decode('utf-8'))

        # 4. 尝试获取代码文件
        code_content = None
        code_key = f"{match['path']}/{match['experience_id']}_code.py"
        try:
            code_obj = s3.get_object(
                Bucket=config.asr_playbooks_bucket,
                Key=code_key
            )
            code_content = code_obj['Body'].read().decode('utf-8')
        except ClientError as e:
            if e.response['Error']['Code'] != 'NoSuchKey':
                logger.warning(f"Failed to fetch code file: {e}")

        logger.info(f"ASR playbook matched: {match['experience_id']} for {control_id}")

        return {
            "matched": True,
            "control_id": control_id,
            "playbook_id": match['experience_id'],
            "playbook": playbook,
            "code_template": code_content,
            "is_destructive": match.get('is_destructive', False),
            "standard": match.get('standard', 'AFSBP')
        }

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        logger.error(f"S3 error fetching ASR playbook: {error_code} - {error_msg}")
        return {
            "matched": False,
            "control_id": control_id,
            "error": f"S3 error: {error_code} - {error_msg}"
        }
    except Exception as e:
        logger.exception(f"Unexpected error fetching ASR playbook: {e}")
        return {
            "matched": False,
            "control_id": control_id,
            "error": str(e)
        }
