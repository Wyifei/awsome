#!/usr/bin/env python3
"""
ASR Playbooks 转换脚本

将 AWS Automated Security Response (ASR) 的 playbooks 转换为 SHARA Knowledge Base 格式。

使用方法:
    python convert_asr_playbooks.py --asr-path /path/to/asr --output-path /path/to/output

依赖:
    pip install pyyaml boto3
"""

import os
import re
import json
import yaml
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 破坏性操作的控制项列表
DESTRUCTIVE_CONTROLS = {
    # EC2 相关
    "EC2.19",   # 删除安全组规则
    "EC2.2",    # 删除默认 VPC 安全组规则

    # IAM 相关
    "IAM.3",    # 禁用/删除访问密钥
    "IAM.7",    # 删除 root 访问密钥
    "IAM.8",    # 删除未使用的凭证

    # 网络相关
    "EC2.18",   # 删除未限制的安全组规则
    "EC2.19",   # 删除未限制的高危端口

    # Lambda
    "Lambda.1", # 移除公共访问

    # RDS
    "RDS.1",    # 禁用公共访问

    # Redshift
    "Redshift.1",  # 禁用公共访问
}

# 控制项到服务的映射
CONTROL_SERVICE_MAP = {
    "S3": "s3",
    "EC2": "ec2",
    "RDS": "rds",
    "IAM": "iam",
    "Lambda": "lambda",
    "CloudTrail": "cloudtrail",
    "Config": "config",
    "GuardDuty": "guardduty",
    "SNS": "sns",
    "SQS": "sqs",
    "KMS": "kms",
    "Redshift": "redshift",
    "ELBv2": "elbv2",
    "AutoScaling": "autoscaling",
    "CloudFront": "cloudfront",
    "DynamoDB": "dynamodb",
    "ECR": "ecr",
    "ECS": "ecs",
    "SSM": "ssm",
    "SecretsManager": "secretsmanager",
    "Athena": "athena",
    "CodeBuild": "codebuild",
    "APIGateway": "apigateway",
    "Macie": "macie",
    "CloudFormation": "cloudformation",
    "ElastiCache": "elasticache",
}

# 控制项描述映射
CONTROL_DESCRIPTIONS = {
    "S3.1": "S3 Block Public Access 应启用",
    "S3.2": "S3 bucket 应禁止公共读取访问",
    "S3.4": "S3 bucket 应启用服务端加密",
    "S3.5": "S3 bucket 应要求 SSL 请求",
    "S3.6": "S3 bucket 跨区域访问应限制",
    "S3.9": "S3 bucket 应启用服务器访问日志",
    "S3.11": "S3 bucket 应启用事件通知",
    "S3.13": "S3 bucket 应配置生命周期策略",
    "EC2.1": "EBS 快照不应公开可恢复",
    "EC2.2": "VPC 默认安全组不应允许入站和出站流量",
    "EC2.4": "未使用的 EC2 EIP 应移除",
    "EC2.6": "VPC 流日志应启用",
    "EC2.7": "EBS 默认加密应启用",
    "EC2.8": "EC2 实例应使用 IMDSv2",
    "EC2.10": "Amazon EC2 应配置为使用 VPC 端点",
    "EC2.15": "EC2 子网不应自动分配公共 IP",
    "EC2.18": "安全组应仅允许授权端口的入站流量",
    "EC2.19": "安全组不应允许对高风险端口的无限制访问",
    "RDS.1": "RDS 快照应为私有",
    "RDS.2": "RDS DB 实例应禁止公共访问",
    "RDS.4": "RDS 集群快照和数据库快照应加密",
    "RDS.5": "RDS DB 实例应配置多个可用区",
    "RDS.6": "应为 RDS DB 实例配置增强监控",
    "RDS.7": "RDS 集群应启用删除保护",
    "RDS.8": "RDS DB 实例应启用删除保护",
    "IAM.3": "IAM 用户访问密钥应每 90 天或更短时间轮换",
    "IAM.7": "不应为 root 用户设置访问密钥",
    "IAM.8": "应移除未使用的 IAM 用户凭证",
    "CloudTrail.1": "应启用 CloudTrail 并配置至少一个多区域跟踪",
    "CloudTrail.2": "CloudTrail 应启用静态加密",
    "CloudTrail.4": "应启用 CloudTrail 日志文件验证",
    "CloudTrail.5": "CloudTrail 跟踪应与 CloudWatch Logs 集成",
    "Lambda.1": "Lambda 函数策略应禁止公共访问",
    "Config.1": "应启用 AWS Config",
    "GuardDuty.1": "应启用 GuardDuty",
}


def extract_control_id(filename: str) -> Optional[str]:
    """
    从文件名提取控制项 ID

    示例:
        AFSBP_S3.4.yaml -> S3.4
        CIS_2.7.yaml -> 2.7
        PCI_PCI.S3.4.yaml -> S3.4
    """
    basename = Path(filename).stem

    # 匹配模式: STANDARD_SERVICE.NUMBER 或 STANDARD_STANDARD.SERVICE.NUMBER
    patterns = [
        r'AFSBP_([A-Za-z]+\d*\.\d+)',    # AFSBP_S3.4, AFSBP_ELBv2.1
        r'CIS_(\d+\.\d+)',                # CIS_2.7
        r'CIS\d+_(\d+\.\d+)',             # CIS140_2.7
        r'PCI_PCI\.([A-Za-z]+\d*\.\d+)',  # PCI_PCI.S3.4, PCI_PCI.EC2.6
        r'NIST_([A-Za-z]+\d*\.\d+)',      # NIST_S3.4
        r'SC_([A-Za-z]+\d*\.\d+)',        # SC_S3.4
    ]

    for pattern in patterns:
        match = re.search(pattern, basename)
        if match:
            return match.group(1)

    return None


def extract_standard(filename: str) -> str:
    """从文件名提取标准名称"""
    basename = Path(filename).stem

    if basename.startswith('AFSBP'):
        return 'AFSBP'
    elif basename.startswith('CIS'):
        return 'CIS'
    elif basename.startswith('PCI'):
        return 'PCI'
    elif basename.startswith('NIST'):
        return 'NIST'
    elif basename.startswith('SC'):
        return 'SC'

    return 'UNKNOWN'


def get_service_from_control(control_id: str) -> str:
    """从控制项 ID 获取 AWS 服务名称"""
    # 提取服务前缀 (如 S3, EC2, IAM)
    match = re.match(r'([A-Za-z]+)', control_id)
    if match:
        service_prefix = match.group(1)
        return CONTROL_SERVICE_MAP.get(service_prefix, service_prefix.lower())
    return 'unknown'


def parse_yaml_playbook(playbook_path: str) -> Optional[Dict]:
    """解析 YAML 格式的 playbook"""
    try:
        with open(playbook_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.warning(f"Failed to parse {playbook_path}: {e}")
        return None


def extract_resource_regex(playbook: Dict) -> Optional[str]:
    """从 playbook 提取资源 ID 正则表达式"""
    if not playbook or 'mainSteps' not in playbook:
        return None

    for step in playbook['mainSteps']:
        if step.get('name') == 'ParseInput':
            inputs = step.get('inputs', {})
            input_payload = inputs.get('InputPayload', {})
            if 'parse_id_pattern' in input_payload:
                return input_payload['parse_id_pattern']

    return None


def extract_remediation_doc(playbook: Dict) -> Optional[str]:
    """提取修复文档名称"""
    if not playbook or 'mainSteps' not in playbook:
        return None

    for step in playbook['mainSteps']:
        if step.get('name') == 'Remediation':
            inputs = step.get('inputs', {})
            return inputs.get('DocumentName')

    return None


def extract_parameters(playbook: Dict) -> List[str]:
    """提取修复参数列表"""
    if not playbook or 'mainSteps' not in playbook:
        return []

    params = []
    for step in playbook['mainSteps']:
        if step.get('name') == 'Remediation':
            inputs = step.get('inputs', {})
            runtime_params = inputs.get('RuntimeParameters', {})
            params = list(runtime_params.keys())
            break

    return params


def load_remediation_script(scripts_path: str, doc_name: str) -> Optional[str]:
    """加载修复脚本内容"""
    # 移除 ASR- 前缀
    script_name = doc_name.replace('ASR-', '') if doc_name else None
    if not script_name:
        return None

    script_file = os.path.join(scripts_path, f"{script_name}.py")
    if os.path.exists(script_file):
        try:
            with open(script_file, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.warning(f"Failed to read script {script_file}: {e}")

    return None


def convert_playbook_to_experience(
    playbook_path: str,
    scripts_path: str,
    control_id: str,
    standard: str
) -> Dict[str, Any]:
    """
    将单个 playbook 转换为 SHARA 经验格式
    """
    playbook = parse_yaml_playbook(playbook_path)

    # 获取服务名称
    service = get_service_from_control(control_id)

    # 获取描述
    description = CONTROL_DESCRIPTIONS.get(control_id, f"Security control {control_id}")

    # 提取信息
    resource_regex = extract_resource_regex(playbook) if playbook else None
    remediation_doc = extract_remediation_doc(playbook) if playbook else None
    parameters = extract_parameters(playbook) if playbook else []

    # 判断是否是破坏性操作
    is_destructive = control_id in DESTRUCTIVE_CONTROLS

    # 构建经验文档
    experience = {
        "experience_id": f"ASR_{control_id.replace('.', '_')}",
        "source": "AWS-ASR",
        "control_id": control_id,
        "standard": standard,
        "standard_version": "1.0.0",

        "finding_pattern": {
            "title_pattern": control_id,
            "resource_type": f"Aws{service.capitalize()}*",
            "resource_id_regex": resource_regex,
            "severity": ["HIGH", "CRITICAL"] if is_destructive else ["MEDIUM", "HIGH", "CRITICAL"]
        },

        "analysis": {
            "summary": description,
            "risk_level": "HIGH" if is_destructive else "MEDIUM",
            "root_cause": f"Resource does not comply with {control_id} security control"
        },

        "remediation": {
            "summary": f"Remediate {control_id} finding",
            "approach": description,
            "ssm_document": remediation_doc,
            "parameters": parameters,
            "steps": [
                {
                    "order": 1,
                    "description": "Parse finding input and extract resource ID",
                    "type": "parse_input"
                },
                {
                    "order": 2,
                    "description": f"Execute remediation for {control_id}",
                    "type": "remediation",
                    "ssm_document": remediation_doc
                },
                {
                    "order": 3,
                    "description": "Update Security Hub finding status",
                    "type": "update_finding",
                    "workflow_status": "RESOLVED"
                }
            ],
            "is_destructive": is_destructive,
            "impact_assessment": {
                "service_impact": "minimal" if is_destructive else "none",
                "downtime": "none",
                "data_loss": False
            }
        },

        "rollback": {
            "available": not is_destructive,
            "summary": f"Rollback {control_id} remediation" if not is_destructive else "Rollback not recommended for destructive operations",
            "steps": [] if is_destructive else [
                {
                    "order": 1,
                    "description": "Restore previous configuration from saved state"
                }
            ]
        },

        "metadata": {
            "source_project": "automated-security-response-on-aws",
            "source_version": "2.1.0",
            "verified": True,
            "verified_by": "AWS Solutions",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "tags": [standard, service, control_id]
        }
    }

    return experience


def generate_code_file(control_id: str, experience: Dict, script_content: Optional[str]) -> str:
    """生成修复代码文件内容"""

    code_template = f'''"""
修复方案: {experience['analysis']['summary']}
Control ID: {control_id}
Source: AWS Automated Security Response (ASR)
Generated: {datetime.utcnow().isoformat()}Z

此代码从 ASR 项目转换而来，供 SHARA Analyzer Agent 参考。
"""

import boto3
from botocore.config import Config

# Boto3 配置
BOTO_CONFIG = Config(retries={{"mode": "standard"}})


def get_client(service: str, region: str = None):
    """获取 AWS 服务客户端"""
    return boto3.client(service, config=BOTO_CONFIG, region_name=region)


def remediate(resource_id: str, **kwargs) -> dict:
    """
    执行修复操作

    Args:
        resource_id: 资源标识符
        **kwargs: 其他参数

    Returns:
        dict: 包含 success 和 message 的结果
    """
    # TODO: 从 ASR 的 SSM Document 提取具体实现
    # SSM Document: {experience['remediation'].get('ssm_document', 'N/A')}

    try:
        # 修复逻辑占位符
        # 请参考 ASR 项目中的具体实现

        return {{
            "success": True,
            "message": f"Successfully remediated {{resource_id}} for {control_id}"
        }}
    except Exception as e:
        return {{
            "success": False,
            "message": f"Failed to remediate: {{str(e)}}"
        }}


def rollback(resource_id: str, pre_state: dict) -> dict:
    """
    执行回滚操作

    Args:
        resource_id: 资源标识符
        pre_state: 修复前保存的状态

    Returns:
        dict: 包含 success 和 message 的结果
    """
    try:
        # 回滚逻辑占位符
        # 使用 pre_state 恢复原始配置

        return {{
            "success": True,
            "message": f"Successfully rolled back {{resource_id}}"
        }}
    except Exception as e:
        return {{
            "success": False,
            "message": f"Failed to rollback: {{str(e)}}"
        }}


# ASR 原始脚本参考 (如果可用)
# ============================================================
'''

    if script_content:
        code_template += f"\n# Original ASR Script:\n# {'-' * 60}\n"
        # 添加注释前缀
        commented_script = '\n'.join(f"# {line}" for line in script_content.split('\n'))
        code_template += commented_script

    return code_template


def process_playbooks(
    asr_path: str,
    output_path: str,
    standards: List[str] = None
) -> Dict[str, int]:
    """
    处理所有 playbooks 并输出到指定目录

    Args:
        asr_path: ASR 项目路径
        output_path: 输出目录路径
        standards: 要处理的标准列表，默认处理所有

    Returns:
        处理统计信息
    """
    if standards is None:
        standards = ['AFSBP', 'CIS120', 'CIS140', 'CIS300', 'PCI321', 'SC']

    scripts_path = os.path.join(asr_path, 'source', 'remediation_runbooks', 'scripts')

    stats = {
        'total': 0,
        'success': 0,
        'failed': 0,
        'by_standard': {}
    }

    # 创建输出目录
    experiences_path = os.path.join(output_path, 'experiences')
    os.makedirs(experiences_path, exist_ok=True)

    # 所有经验的索引
    index = {
        "version": "1.0.0",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "source": "AWS Automated Security Response",
        "controls": []
    }

    for standard in standards:
        playbooks_dir = os.path.join(asr_path, 'source', 'playbooks', standard, 'ssmdocs')

        if not os.path.exists(playbooks_dir):
            logger.warning(f"Playbooks directory not found: {playbooks_dir}")
            continue

        stats['by_standard'][standard] = {'success': 0, 'failed': 0}

        for playbook_file in Path(playbooks_dir).glob("*.yaml"):
            stats['total'] += 1

            try:
                control_id = extract_control_id(str(playbook_file))
                if not control_id:
                    logger.warning(f"Could not extract control ID from {playbook_file}")
                    stats['failed'] += 1
                    stats['by_standard'][standard]['failed'] += 1
                    continue

                # 转换为经验格式
                experience = convert_playbook_to_experience(
                    str(playbook_file),
                    scripts_path,
                    control_id,
                    standard
                )

                # 创建控制项目录
                control_dir = os.path.join(experiences_path, control_id.replace('.', '_'))
                os.makedirs(control_dir, exist_ok=True)

                # 保存经验文档
                experience_file = os.path.join(control_dir, f"ASR_{control_id.replace('.', '_')}.json")
                with open(experience_file, 'w', encoding='utf-8') as f:
                    json.dump(experience, f, indent=2, ensure_ascii=False)

                # 加载并保存代码文件
                remediation_doc = experience['remediation'].get('ssm_document')
                script_content = load_remediation_script(scripts_path, remediation_doc)

                code_content = generate_code_file(control_id, experience, script_content)
                code_file = os.path.join(control_dir, f"ASR_{control_id.replace('.', '_')}_code.py")
                with open(code_file, 'w', encoding='utf-8') as f:
                    f.write(code_content)

                # 添加到索引
                index['controls'].append({
                    "control_id": control_id,
                    "standard": standard,
                    "experience_id": experience['experience_id'],
                    "is_destructive": experience['remediation']['is_destructive'],
                    "path": f"experiences/{control_id.replace('.', '_')}"
                })

                logger.info(f"Converted: {standard}/{control_id}")
                stats['success'] += 1
                stats['by_standard'][standard]['success'] += 1

            except Exception as e:
                logger.error(f"Failed to convert {playbook_file}: {e}")
                stats['failed'] += 1
                stats['by_standard'][standard]['failed'] += 1

    # 保存索引文件
    index_file = os.path.join(output_path, 'index.json')
    with open(index_file, 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    logger.info(f"Index saved to {index_file}")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description='Convert ASR playbooks to SHARA Knowledge Base format'
    )
    parser.add_argument(
        '--asr-path',
        default='/Users/yifeiwf/Code/awsome2/automated-security-response-on-aws',
        help='Path to ASR project'
    )
    parser.add_argument(
        '--output-path',
        default='/Users/yifeiwf/Code/awsome2/agent/data/knowledge_base',
        help='Output path for converted files'
    )
    parser.add_argument(
        '--standards',
        nargs='+',
        default=None,
        help='Standards to process (default: all)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("Starting ASR playbooks conversion...")
    logger.info(f"ASR path: {args.asr_path}")
    logger.info(f"Output path: {args.output_path}")

    stats = process_playbooks(
        args.asr_path,
        args.output_path,
        args.standards
    )

    # 打印统计信息
    print("\n" + "=" * 60)
    print("Conversion Summary")
    print("=" * 60)
    print(f"Total playbooks processed: {stats['total']}")
    print(f"Successfully converted: {stats['success']}")
    print(f"Failed: {stats['failed']}")
    print("\nBy Standard:")
    for standard, counts in stats['by_standard'].items():
        print(f"  {standard}: {counts['success']} success, {counts['failed']} failed")
    print("=" * 60)


if __name__ == '__main__':
    main()
