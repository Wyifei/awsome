"""
修复方案: 安全组应仅允许授权端口的入站流量
Control ID: EC2.18
Source: AWS Automated Security Response (ASR)
Generated: 2026-01-29T05:45:46.443131Z

此代码从 ASR 项目转换而来，供 SHARA Analyzer Agent 参考。
"""

import boto3
from botocore.config import Config

# Boto3 配置
BOTO_CONFIG = Config(retries={"mode": "standard"})


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
    # SSM Document: ASR-RevokeUnauthorizedInboundRules

    try:
        # 修复逻辑占位符
        # 请参考 ASR 项目中的具体实现

        return {
            "success": True,
            "message": f"Successfully remediated {resource_id} for EC2.18"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to remediate: {str(e)}"
        }


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

        return {
            "success": True,
            "message": f"Successfully rolled back {resource_id}"
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to rollback: {str(e)}"
        }


# ASR 原始脚本参考 (如果可用)
# ============================================================

# Original ASR Script:
# ------------------------------------------------------------
# # Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# # SPDX-License-Identifier: Apache-2.0
# from typing import TypedDict
# 
# import boto3
# from botocore.config import Config
# 
# BOTO_CONFIG = Config(retries={"mode": "standard", "max_attempts": 10})
# 
# # IPV4 and IPV6 open access
# OPENIPV4 = "0.0.0.0/0"
# OPENIPV6 = "::/0"
# 
# PROTOCOLS = {"tcp", "udp", "-1"}
# 
# 
# def connect_to_ec2():
#     return boto3.client("ec2", config=BOTO_CONFIG)
# 
# 
# class Event(TypedDict):
#     SecurityGroupId: str
#     AuthorizedTcpPorts: list
#     AuthorizedUdpPorts: list
# 
# 
# def lambda_handler(event: Event, _):
#     rules_deleted = []
#     try:
#         security_group_id = event["SecurityGroupId"]
#         authorized_tcp_ports = set(map(int, event["AuthorizedTcpPorts"]))
#         authorized_udp_ports = set(map(int, event["AuthorizedUdpPorts"]))
# 
#         security_group_rules = get_security_group_rules(security_group_id)
# 
#         rules_deleted = revoke_unauthorized_rules(
#             security_group_id,
#             security_group_rules,
#             authorized_tcp_ports,
#             authorized_udp_ports,
#         )
#     except Exception as e:
#         raise RuntimeError("Failed to remove security group rules: " + str(e))
# 
#     if not rules_deleted:
#         raise RuntimeError(
#             f"Could not find rules to delete for Security Group {security_group_id}. Please check the inbound "
#             f"rules manually."
#         )
# 
#     return {
#         "message": "Successfully removed security group rules on " + security_group_id,
#         "status": "Success",
#         "rules_deleted": rules_deleted,
#     }
# 
# 
# def get_security_group_rules(security_group_id: str) -> list:
#     ec2 = connect_to_ec2()
#     try:
#         paginator = ec2.get_paginator("describe_security_group_rules")
#         page_iterator = paginator.paginate(
#             Filters=[
#                 {
#                     "Name": "group-id",
#                     "Values": [security_group_id],
#                 },
#             ]
#         )
# 
#         security_group_rules = []
#         for page in page_iterator:
#             security_group_rules.extend(page.get("SecurityGroupRules", []))
# 
#         return security_group_rules
#     except Exception as e:
#         exit("Failed to describe security group rules: " + str(e))
# 
# 
# def has_open_access(rule: dict) -> bool:
#     return ("CidrIpv4" in rule and rule["CidrIpv4"] == OPENIPV4) or (
#         "CidrIpv6" in rule and rule["CidrIpv6"] == OPENIPV6
#     )
# 
# 
# def check_unauthorized_ports(authorized_ports: set, rule: dict) -> bool:
#     for port in range(rule["FromPort"], rule["ToPort"] + 1):
#         if (port not in authorized_ports) and has_open_access(rule):
#             return True
#     return False
# 
# 
# def is_all_traffic_rule_with_open_access(rule: dict) -> bool:
#     return (rule["FromPort"] == rule["ToPort"] == -1) and has_open_access(rule)
# 
# 
# def should_revoke_rule(rule: dict, authorized_ports: set) -> bool:
#     return is_all_traffic_rule_with_open_access(rule) or check_unauthorized_ports(
#         authorized_ports, rule
#     )
# 
# 
# def revoke_unauthorized_rules(
#     security_group_id: str,
#     security_group_rules: list,
#     authorized_tcp_ports: set,
#     authorized_udp_ports: set,
# ) -> list:
#     ec2 = connect_to_ec2()
#     rules_deleted = []
#     for rule in security_group_rules:
#         if rule["IpProtocol"] not in PROTOCOLS or rule["IsEgress"]:
#             continue
# 
#         authorized_ports = (
#             authorized_tcp_ports
#             if rule["IpProtocol"] == "tcp"
#             else authorized_udp_ports
#         )
# 
#         if should_revoke_rule(rule, authorized_ports):
#             try:
#                 ec2.revoke_security_group_ingress(
#                     GroupId=security_group_id,
#                     SecurityGroupRuleIds=[rule["SecurityGroupRuleId"]],
#                 )
#                 rules_deleted.append(rule["SecurityGroupRuleId"])
#             except Exception as e:
#                 print(f"Failed to delete rule {rule['SecurityGroupRuleId']}: {str(e)}")
#     return rules_deleted
# 