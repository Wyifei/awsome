# Security Hub Auto-Remediation Agent 修复方案知识库

## 1. 概述

本文档定义 SHARA 系统支持的修复场景和对应的 Playbook。每个 Playbook 包含完整的分析、修复、验证步骤。

---

## 2. Playbook 结构

### 2.1 标准 Playbook 格式

```yaml
id: playbook-unique-id
name: Playbook Display Name
version: "1.0.0"
description: Detailed description
category: s3 | ec2 | iam | rds | ...
severity_handled:
  - HIGH
  - CRITICAL

triggers:
  finding_types: []
  generator_ids: []
  resource_types: []

analysis:
  context_queries: []
  risk_factors: []

remediation:
  strategy: description
  prerequisites: []
  steps: []
  rollback: []

validation:
  checks: []

notifications:
  templates: {}
```

---

## 3. S3 Playbooks

### 3.1 S3 Public Access Block

**Playbook ID:** `s3-public-access-block`

**触发条件:**
- Finding Type: `Software and Configuration Checks/AWS Security Best Practices/S3.1`
- Generator: `aws-foundational-security-best-practices`
- Resource Type: `AwsS3Bucket`

#### 问题描述
S3 bucket 未启用 Block Public Access 设置，可能导致数据意外公开。

#### 风险评估
| 因素 | 权重 | 说明 |
|------|------|------|
| 包含敏感数据标签 | +30% | 标签包含 `confidential`, `pii`, `sensitive` |
| 生产环境 | +20% | 标签包含 `env:prod` 或 `environment:production` |
| 已有公开访问 | +50% | 当前 bucket 已被公开访问 |

#### 修复步骤

```yaml
steps:
  - order: 1
    name: backup_current_settings
    description: 备份当前 Block Public Access 设置
    action:
      service: s3
      operation: GetPublicAccessBlock
      parameters:
        Bucket: "${bucket_name}"
    save_result: current_settings

  - order: 2
    name: enable_block_public_access
    description: 启用 Block Public Access
    action:
      service: s3
      operation: PutPublicAccessBlock
      parameters:
        Bucket: "${bucket_name}"
        PublicAccessBlockConfiguration:
          BlockPublicAcls: true
          IgnorePublicAcls: true
          BlockPublicPolicy: true
          RestrictPublicBuckets: true

  - order: 3
    name: verify_settings
    description: 验证设置已生效
    action:
      service: s3
      operation: GetPublicAccessBlock
      parameters:
        Bucket: "${bucket_name}"
    expected:
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        IgnorePublicAcls: true
        BlockPublicPolicy: true
        RestrictPublicBuckets: true
```

#### 生成的 CLI 命令

```bash
# 启用 Block Public Access
aws s3api put-public-access-block \
  --bucket ${bucket_name} \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
```

#### 回滚方案

```bash
# 如果需要回滚
aws s3api delete-public-access-block --bucket ${bucket_name}
```

---

### 3.2 S3 Bucket Policy Public Access

**Playbook ID:** `s3-bucket-policy-public`

**触发条件:**
- Finding Type: `Software and Configuration Checks/AWS Security Best Practices/S3.2`
- Resource Type: `AwsS3Bucket`

#### 问题描述
S3 bucket policy 包含允许公开访问的语句（Principal 为 `*` 且无 Condition 限制）。

#### 分析步骤

```python
def analyze_bucket_policy(policy: dict) -> List[dict]:
    """分析 bucket policy 中的公开访问风险"""
    risks = []
    for statement in policy.get('Statement', []):
        if statement.get('Effect') == 'Allow':
            principal = statement.get('Principal', {})
            condition = statement.get('Condition', {})

            # 检查是否为公开访问
            is_public = (
                principal == '*' or
                principal == {'AWS': '*'} or
                (isinstance(principal, dict) and '*' in principal.get('AWS', []))
            )

            if is_public and not condition:
                risks.append({
                    'statement_id': statement.get('Sid', 'Unknown'),
                    'action': statement.get('Action'),
                    'resource': statement.get('Resource'),
                    'risk': 'PUBLIC_ACCESS_NO_CONDITION'
                })

    return risks
```

#### 修复步骤

```yaml
steps:
  - order: 1
    name: get_current_policy
    description: 获取当前 bucket policy
    action:
      service: s3
      operation: GetBucketPolicy
      parameters:
        Bucket: "${bucket_name}"
    save_result: current_policy

  - order: 2
    name: analyze_policy
    description: 分析 policy 中的风险语句
    action:
      type: analyze
      function: analyze_bucket_policy
      parameters:
        policy: "${current_policy}"
    save_result: risk_analysis

  - order: 3
    name: generate_secure_policy
    description: 生成安全的 policy（移除公开访问语句或添加条件）
    action:
      type: transform
      function: secure_bucket_policy
      parameters:
        policy: "${current_policy}"
        risks: "${risk_analysis}"
    save_result: secure_policy

  - order: 4
    name: apply_secure_policy
    description: 应用安全的 policy
    action:
      service: s3
      operation: PutBucketPolicy
      parameters:
        Bucket: "${bucket_name}"
        Policy: "${secure_policy}"
```

#### 安全 Policy 示例

**Before (不安全):**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadAccess",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::my-bucket/*"
    }
  ]
}
```

**After (安全):**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "RestrictedAccess",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::123456789012:root"
      },
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::my-bucket/*"
    }
  ]
}
```

---

### 3.3 S3 Bucket Encryption

**Playbook ID:** `s3-default-encryption`

**触发条件:**
- Finding Type: `Software and Configuration Checks/AWS Security Best Practices/S3.4`
- Resource Type: `AwsS3Bucket`

#### 修复步骤

```yaml
steps:
  - order: 1
    name: enable_sse_s3
    description: 启用 SSE-S3 默认加密
    action:
      service: s3
      operation: PutBucketEncryption
      parameters:
        Bucket: "${bucket_name}"
        ServerSideEncryptionConfiguration:
          Rules:
            - ApplyServerSideEncryptionByDefault:
                SSEAlgorithm: AES256
              BucketKeyEnabled: true
```

#### CLI 命令

```bash
aws s3api put-bucket-encryption \
  --bucket ${bucket_name} \
  --server-side-encryption-configuration '{
    "Rules": [
      {
        "ApplyServerSideEncryptionByDefault": {
          "SSEAlgorithm": "AES256"
        },
        "BucketKeyEnabled": true
      }
    ]
  }'
```

---

## 4. EC2/网络 Playbooks

### 4.1 Security Group Unrestricted SSH

**Playbook ID:** `ec2-sg-unrestricted-ssh`

**触发条件:**
- Finding Type: `Software and Configuration Checks/AWS Security Best Practices/EC2.13`
- Generator: `aws-foundational-security-best-practices`
- Resource Type: `AwsEc2SecurityGroup`

#### 问题描述
安全组允许从 0.0.0.0/0 或 ::/0 入站 SSH (端口 22) 访问。

#### 风险评估

| 因素 | 风险等级 | 说明 |
|------|----------|------|
| 生产环境安全组 | CRITICAL | 生产环境直接暴露 SSH |
| 关联 EC2 实例 | HIGH | 安全组已绑定实例 |
| 仅规则存在 | MEDIUM | 安全组未关联资源 |

#### 分析步骤

```python
def analyze_security_group_exposure(sg_id: str) -> dict:
    """分析安全组的暴露风险"""
    ec2 = boto3.client('ec2')

    # 获取安全组详情
    sg = ec2.describe_security_groups(GroupIds=[sg_id])['SecurityGroups'][0]

    # 查找关联的 EC2 实例
    instances = ec2.describe_instances(
        Filters=[{'Name': 'instance.group-id', 'Values': [sg_id]}]
    )

    # 分析入站规则
    risky_rules = []
    for rule in sg.get('IpPermissions', []):
        for ip_range in rule.get('IpRanges', []):
            if ip_range.get('CidrIp') == '0.0.0.0/0':
                risky_rules.append({
                    'protocol': rule.get('IpProtocol'),
                    'from_port': rule.get('FromPort'),
                    'to_port': rule.get('ToPort'),
                    'cidr': ip_range.get('CidrIp')
                })

    return {
        'security_group_id': sg_id,
        'security_group_name': sg['GroupName'],
        'vpc_id': sg['VpcId'],
        'associated_instances': [
            i['InstanceId']
            for r in instances['Reservations']
            for i in r['Instances']
        ],
        'risky_rules': risky_rules
    }
```

#### 修复步骤

```yaml
steps:
  - order: 1
    name: identify_risky_rules
    description: 识别需要修改的规则
    action:
      service: ec2
      operation: DescribeSecurityGroups
      parameters:
        GroupIds:
          - "${security_group_id}"
    save_result: current_rules

  - order: 2
    name: revoke_unrestricted_ssh
    description: 移除不安全的 SSH 入站规则
    action:
      service: ec2
      operation: RevokeSecurityGroupIngress
      parameters:
        GroupId: "${security_group_id}"
        IpPermissions:
          - IpProtocol: tcp
            FromPort: 22
            ToPort: 22
            IpRanges:
              - CidrIp: "0.0.0.0/0"

  - order: 3
    name: add_restricted_ssh
    description: 添加受限的 SSH 访问规则（仅允许内网或特定 IP）
    action:
      service: ec2
      operation: AuthorizeSecurityGroupIngress
      parameters:
        GroupId: "${security_group_id}"
        IpPermissions:
          - IpProtocol: tcp
            FromPort: 22
            ToPort: 22
            IpRanges:
              - CidrIp: "${allowed_cidr}"
                Description: "Restricted SSH access"
    condition: "${add_replacement_rule}"
```

#### CLI 命令

```bash
# 移除不安全规则
aws ec2 revoke-security-group-ingress \
  --group-id ${security_group_id} \
  --protocol tcp \
  --port 22 \
  --cidr 0.0.0.0/0

# 添加受限规则 (可选)
aws ec2 authorize-security-group-ingress \
  --group-id ${security_group_id} \
  --protocol tcp \
  --port 22 \
  --cidr 10.0.0.0/8 \
  --tag-specifications 'ResourceType=security-group-rule,Tags=[{Key=Description,Value="Internal SSH only"}]'
```

---

### 4.2 Security Group Unrestricted RDP

**Playbook ID:** `ec2-sg-unrestricted-rdp`

类似于 SSH playbook，但针对 RDP (端口 3389)。

```bash
# 移除不安全的 RDP 规则
aws ec2 revoke-security-group-ingress \
  --group-id ${security_group_id} \
  --protocol tcp \
  --port 3389 \
  --cidr 0.0.0.0/0
```

---

### 4.3 EC2 Instance Metadata Service v1

**Playbook ID:** `ec2-imdsv2-required`

**触发条件:**
- Finding Type: `Software and Configuration Checks/AWS Security Best Practices/EC2.8`
- Resource Type: `AwsEc2Instance`

#### 问题描述
EC2 实例未强制使用 IMDSv2，可能受到 SSRF 攻击影响。

#### 修复步骤

```yaml
steps:
  - order: 1
    name: enable_imdsv2
    description: 强制使用 IMDSv2
    action:
      service: ec2
      operation: ModifyInstanceMetadataOptions
      parameters:
        InstanceId: "${instance_id}"
        HttpTokens: required
        HttpPutResponseHopLimit: 1
        HttpEndpoint: enabled
```

#### CLI 命令

```bash
aws ec2 modify-instance-metadata-options \
  --instance-id ${instance_id} \
  --http-tokens required \
  --http-put-response-hop-limit 1 \
  --http-endpoint enabled
```

---

## 5. IAM Playbooks

### 5.1 IAM User Console Access Without MFA

**Playbook ID:** `iam-user-mfa-console`

**触发条件:**
- Finding Type: `Software and Configuration Checks/AWS Security Best Practices/IAM.5`
- Resource Type: `AwsIamUser`

#### 问题描述
IAM 用户具有控制台访问权限但未启用 MFA。

#### 修复策略

由于 MFA 设备需要用户配合，此 playbook 采用**策略限制**方式：

```yaml
steps:
  - order: 1
    name: attach_mfa_policy
    description: 附加 MFA 强制策略
    action:
      service: iam
      operation: AttachUserPolicy
      parameters:
        UserName: "${user_name}"
        PolicyArn: "arn:aws:iam::${account_id}:policy/ForceMFAPolicy"
```

#### MFA 强制策略示例

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowViewAccountInfo",
      "Effect": "Allow",
      "Action": [
        "iam:GetAccountPasswordPolicy",
        "iam:ListVirtualMFADevices"
      ],
      "Resource": "*"
    },
    {
      "Sid": "AllowManageOwnMFA",
      "Effect": "Allow",
      "Action": [
        "iam:CreateVirtualMFADevice",
        "iam:EnableMFADevice",
        "iam:ResyncMFADevice"
      ],
      "Resource": [
        "arn:aws:iam::*:mfa/${aws:username}",
        "arn:aws:iam::*:user/${aws:username}"
      ]
    },
    {
      "Sid": "DenyAllExceptMFASetupWithoutMFA",
      "Effect": "Deny",
      "NotAction": [
        "iam:CreateVirtualMFADevice",
        "iam:EnableMFADevice",
        "iam:GetUser",
        "iam:ListMFADevices",
        "iam:ListVirtualMFADevices",
        "iam:ResyncMFADevice",
        "sts:GetSessionToken"
      ],
      "Resource": "*",
      "Condition": {
        "BoolIfExists": {
          "aws:MultiFactorAuthPresent": "false"
        }
      }
    }
  ]
}
```

---

### 5.2 IAM Role Overprivileged

**Playbook ID:** `iam-role-overprivileged`

**触发条件:**
- Finding Type: 来自 IAM Access Analyzer
- Resource Type: `AwsIamRole`

#### 分析步骤

```python
def analyze_iam_role_permissions(role_name: str) -> dict:
    """分析 IAM Role 的权限范围"""
    iam = boto3.client('iam')

    # 获取 role 详情
    role = iam.get_role(RoleName=role_name)['Role']

    # 获取附加的策略
    attached_policies = iam.list_attached_role_policies(RoleName=role_name)
    inline_policies = iam.list_role_policies(RoleName=role_name)

    # 分析每个策略的权限
    permissions = []
    risks = []

    for policy in attached_policies['AttachedPolicies']:
        policy_arn = policy['PolicyArn']
        version = iam.get_policy(PolicyArn=policy_arn)['Policy']['DefaultVersionId']
        document = iam.get_policy_version(
            PolicyArn=policy_arn,
            VersionId=version
        )['PolicyVersion']['Document']

        # 检查危险权限
        for statement in document.get('Statement', []):
            if statement.get('Effect') == 'Allow':
                actions = statement.get('Action', [])
                if isinstance(actions, str):
                    actions = [actions]

                for action in actions:
                    if action == '*' or action.endswith(':*'):
                        risks.append({
                            'policy': policy_arn,
                            'action': action,
                            'resource': statement.get('Resource'),
                            'risk': 'WILDCARD_ACTION'
                        })

    return {
        'role_name': role_name,
        'role_arn': role['Arn'],
        'attached_policies': attached_policies['AttachedPolicies'],
        'inline_policies': inline_policies['PolicyNames'],
        'risks': risks
    }
```

---

## 6. GuardDuty Playbooks

### 6.1 UnauthorizedAccess: IAMUser/InstanceCredentialExfiltration

**Playbook ID:** `guardduty-credential-exfiltration`

**触发条件:**
- Finding Type: `TTPs/Initial Access/UnauthorizedAccess:IAMUser-InstanceCredentialExfiltration`
- Generator: `guardduty`

#### 问题描述
检测到 EC2 实例凭证在实例外部被使用，可能是凭证泄露。

#### 修复步骤

```yaml
steps:
  - order: 1
    name: identify_instance
    description: 识别受影响的 EC2 实例
    action:
      type: parse
      function: extract_instance_from_finding
      parameters:
        finding: "${finding}"
    save_result: instance_info

  - order: 2
    name: rotate_instance_role
    description: 轮换实例角色的临时凭证
    action:
      type: composite
      steps:
        - detach_role_from_instance
        - wait_30_seconds
        - reattach_role_to_instance

  - order: 3
    name: isolate_instance
    description: 隔离可疑实例（更换安全组）
    condition: "${risk_level} == 'CRITICAL'"
    action:
      service: ec2
      operation: ModifyInstanceAttribute
      parameters:
        InstanceId: "${instance_id}"
        Groups:
          - "${isolation_security_group}"

  - order: 4
    name: notify_security_team
    description: 通知安全团队进一步调查
    action:
      type: notification
      template: security_incident
      parameters:
        severity: HIGH
        incident_type: CREDENTIAL_EXFILTRATION
```

---

### 6.2 CryptoCurrency Mining Detection

**Playbook ID:** `guardduty-crypto-mining`

**触发条件:**
- Finding Type: `CryptoCurrency:EC2/BitcoinTool.B!DNS`
- Generator: `guardduty`

#### 修复步骤

```yaml
steps:
  - order: 1
    name: identify_instance
    description: 识别涉及的 EC2 实例
    action:
      type: parse
      function: extract_instance_from_finding

  - order: 2
    name: create_snapshot
    description: 创建 EBS 快照用于取证
    action:
      service: ec2
      operation: CreateSnapshot
      parameters:
        VolumeId: "${volume_id}"
        Description: "Forensic snapshot - crypto mining detection"
        TagSpecifications:
          - ResourceType: snapshot
            Tags:
              - Key: Purpose
                Value: ForensicInvestigation
              - Key: Finding
                Value: "${finding_id}"

  - order: 3
    name: isolate_instance
    description: 隔离实例
    action:
      service: ec2
      operation: ModifyInstanceAttribute
      parameters:
        InstanceId: "${instance_id}"
        Groups:
          - "${isolation_security_group}"

  - order: 4
    name: stop_instance
    description: 停止实例
    condition: "${auto_stop_enabled}"
    action:
      service: ec2
      operation: StopInstances
      parameters:
        InstanceIds:
          - "${instance_id}"
```

---

## 7. Inspector Playbooks

### 7.1 EC2 Vulnerability - Critical CVE

**Playbook ID:** `inspector-ec2-critical-cve`

**触发条件:**
- Finding Type: 来自 Inspector EC2 扫描
- Severity: CRITICAL
- Resource Type: `AwsEc2Instance`

#### 修复策略

```yaml
remediation_strategies:
  - strategy: ssm_patch
    description: 通过 SSM 自动打补丁
    applicable_when:
      - instance_has_ssm_agent
      - patch_available

  - strategy: manual_notification
    description: 通知运维团队手动处理
    applicable_when:
      - no_ssm_agent
      - or: no_patch_available
```

#### SSM 补丁修复步骤

```yaml
steps:
  - order: 1
    name: check_ssm_status
    description: 检查实例 SSM 代理状态
    action:
      service: ssm
      operation: DescribeInstanceInformation
      parameters:
        Filters:
          - Key: InstanceIds
            Values:
              - "${instance_id}"
    save_result: ssm_status

  - order: 2
    name: run_patch_baseline
    description: 执行补丁基线
    condition: "${ssm_status.online}"
    action:
      service: ssm
      operation: SendCommand
      parameters:
        InstanceIds:
          - "${instance_id}"
        DocumentName: AWS-RunPatchBaseline
        Parameters:
          Operation:
            - Install
          RebootOption:
            - RebootIfNeeded
```

---

### 7.2 ECR Image Vulnerability

**Playbook ID:** `inspector-ecr-vulnerability`

**触发条件:**
- Finding Type: 来自 Inspector ECR 扫描
- Severity: HIGH/CRITICAL
- Resource Type: `AwsEcrContainerImage`

#### 修复建议

由于容器镜像漏洞需要重新构建镜像，此 playbook 主要提供通知和指导：

```yaml
steps:
  - order: 1
    name: analyze_vulnerability
    description: 分析漏洞详情
    action:
      type: parse
      function: extract_vulnerability_details

  - order: 2
    name: check_running_tasks
    description: 检查是否有使用该镜像的运行任务
    action:
      service: ecs
      operation: ListTasks
      # ... 搜索使用该镜像的任务

  - order: 3
    name: generate_remediation_guide
    description: 生成修复指南
    action:
      type: generate
      template: ecr_vulnerability_guide
      parameters:
        vulnerability: "${vulnerability}"
        affected_packages: "${affected_packages}"
        fixed_version: "${fixed_version}"

  - order: 4
    name: create_jira_ticket
    description: 创建工单跟踪
    condition: "${create_ticket}"
    action:
      type: integration
      system: jira
      operation: create_issue
```

---

## 8. 复合 Playbooks

### 8.1 S3 Security Hardening

**Playbook ID:** `s3-security-hardening`

组合多个 S3 安全修复：

```yaml
includes:
  - s3-public-access-block
  - s3-default-encryption
  - s3-bucket-logging
  - s3-versioning

execution_mode: sequential
stop_on_failure: true
```

### 8.2 EC2 Instance Hardening

**Playbook ID:** `ec2-instance-hardening`

```yaml
includes:
  - ec2-imdsv2-required
  - ec2-ebs-encryption
  - ec2-detailed-monitoring

execution_mode: parallel_where_possible
```

---

## 9. 自定义 Playbook 开发

### 9.1 创建新 Playbook

```python
# playbooks/custom/my_playbook.py
from shara.playbook import Playbook, Step, Action

class MyCustomPlaybook(Playbook):
    id = "custom-my-playbook"
    name = "My Custom Remediation"
    version = "1.0.0"

    triggers = {
        "finding_types": ["Custom/MyFindingType"],
        "resource_types": ["AwsCustomResource"]
    }

    def analyze(self, finding: dict) -> dict:
        # 自定义分析逻辑
        return {
            "risk_level": "HIGH",
            "context": {}
        }

    def generate_steps(self, analysis: dict) -> List[Step]:
        return [
            Step(
                order=1,
                name="custom_action",
                description="执行自定义操作",
                action=Action(
                    service="custom",
                    operation="CustomOperation",
                    parameters={}
                )
            )
        ]
```

### 9.2 注册 Playbook

```python
# playbooks/__init__.py
from shara.playbook import PlaybookRegistry
from .custom.my_playbook import MyCustomPlaybook

registry = PlaybookRegistry()
registry.register(MyCustomPlaybook())
```

---

## 10. Playbook 测试

### 10.1 单元测试

```python
# tests/test_playbooks.py
import pytest
from playbooks.s3 import S3PublicAccessBlockPlaybook

class TestS3PublicAccessBlockPlaybook:

    def test_trigger_matching(self):
        playbook = S3PublicAccessBlockPlaybook()
        finding = {
            "Types": ["Software and Configuration Checks/AWS Security Best Practices/S3.1"],
            "Resources": [{"Type": "AwsS3Bucket"}]
        }
        assert playbook.matches(finding)

    def test_step_generation(self):
        playbook = S3PublicAccessBlockPlaybook()
        analysis = {"bucket_name": "test-bucket", "risk_level": "HIGH"}
        steps = playbook.generate_steps(analysis)
        assert len(steps) >= 1
        assert steps[0].action.operation == "PutPublicAccessBlock"
```

### 10.2 集成测试

```python
# tests/integration/test_s3_remediation.py
import boto3
import pytest

@pytest.fixture
def test_bucket():
    s3 = boto3.client('s3')
    bucket_name = f"shara-test-{int(time.time())}"
    s3.create_bucket(Bucket=bucket_name)
    yield bucket_name
    # Cleanup
    s3.delete_bucket(Bucket=bucket_name)

def test_s3_public_access_block_remediation(test_bucket):
    # 执行 playbook
    from playbooks.s3 import S3PublicAccessBlockPlaybook
    playbook = S3PublicAccessBlockPlaybook()

    finding = create_test_finding(test_bucket)
    result = playbook.execute(finding)

    assert result.success

    # 验证结果
    s3 = boto3.client('s3')
    config = s3.get_public_access_block(Bucket=test_bucket)
    assert config['PublicAccessBlockConfiguration']['BlockPublicAcls']
```

---

## 11. 文档版本

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| 1.0 | 2025-01-28 | - | 初始版本 |
