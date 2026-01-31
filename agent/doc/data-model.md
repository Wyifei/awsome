# Security Hub Auto-Remediation Agent 数据模型文档

## 1. 概述

本文档定义 SHARA 系统的数据模型，包括 DynamoDB 表结构、S3 存储结构以及核心数据对象定义。

---

## 2. DynamoDB 表设计

### 2.1 Tasks 表

存储所有处理任务的状态和元数据。

**表名：** `shara-tasks`

**主键设计：**
| 键类型 | 属性名 | 类型 | 说明 |
|--------|--------|------|------|
| Partition Key | PK | String | `TASK#<taskId>` |
| Sort Key | SK | String | `METADATA` |

**GSI (Global Secondary Index):**

| GSI 名称 | Partition Key | Sort Key | 用途 |
|----------|---------------|----------|------|
| GSI1 | GSI1PK (`STATUS#<status>`) | GSI1SK (`<createdAt>`) | 按状态查询 |
| GSI2 | GSI2PK (`FINDING#<findingId>`) | GSI2SK (`<createdAt>`) | 按 Finding 查询 |
| GSI3 | GSI3PK (`ACCOUNT#<accountId>`) | GSI3SK (`<createdAt>`) | 按账户查询 |

**属性定义：**

```typescript
interface TaskItem {
  // Keys
  PK: string;                    // TASK#<taskId>
  SK: string;                    // METADATA

  // GSI Keys
  GSI1PK: string;               // STATUS#<status>
  GSI1SK: string;               // <createdAt> - 用于按时间排序
  GSI2PK: string;               // FINDING#<findingId>
  GSI2SK: string;               // <createdAt>
  GSI3PK: string;               // ACCOUNT#<accountId>
  GSI3SK: string;               // <createdAt>

  // 核心控制字段
  taskId: string;               // UUID
  findingId: string;            // Security Hub Finding ARN
  controlId: string;            // Control ID (如 S3.1, SNS.1)
  status: TaskStatus;           // 任务状态
  phase: 'pre_approval' | 'post_approval';  // 当前处理阶段
  severity: 'HIGH' | 'CRITICAL';

  // 资源标识
  resourceType: string;         // AwsS3Bucket, AwsSnsTopic, etc.
  resourceId: string;           // Resource ARN
  awsAccountId: string;         // AWS 账户 ID
  region: string;               // AWS 区域

  // 修复控制
  canRemediate: boolean;        // 是否可自动修复
  asrMatch?: {                  // ASR Playbook 匹配结果
    matched: boolean;
    playbook_id?: string;       // 匹配的 Playbook ID (如有)
  };

  // Agent 会话
  memorySessionId: string;      // AgentCore Memory Session ID
  actorId: string;              // Memory Actor ID (AWS Account ID，用于跨任务经验共享)

  // 元数据
  createdAt: string;            // ISO8601
  updatedAt: string;            // ISO8601
  version: number;              // Optimistic locking
  traceId?: string;             // Lambda Request ID
}

type TaskStatus =
  // Phase 1: Pre-Approval (Analyzer only)
  | 'analyzing'            // Analyzer Agent 分析中
  | 'waiting_approval'     // 等待管理员审批
  | 'not_remediatable'     // 无法自动修复（资源不存在等）
  | 'analysis_failed'      // 分析失败
  | 'approved'             // 已审批
  | 'rejected'             // 审批被拒绝
  // Phase 2: Post-Approval (Remediator + Validator)
  | 'executing'            // 执行修复中
  | 'execution_failed'     // 执行失败
  | 'validating'           // 验证中
  | 'completed'            // 任务完成
  | 'rolled_back';         // 已回滚
```

**设计说明：**

1. **只存储控制相关字段** - 分析结果、修复方案等详细信息不存储到 DynamoDB，直接用于发送审批邮件
2. **GSI*SK 复用 createdAt** - Sort Key 使用创建时间，支持按时间排序查询
3. **asrMatch 精简** - 只保留 matched 和 playbook_id，不存储完整匹配信息

**示例数据 (Phase 1 - 等待审批状态)：**
```json
{
  "PK": "TASK#21e9b3e3-8913-48e8-8e59-05104e3ae6bd",
  "SK": "METADATA",
  "GSI1PK": "STATUS#waiting_approval",
  "GSI1SK": "2025-01-30T07:31:31.412121+00:00",
  "GSI2PK": "FINDING#arn:aws:securityhub:ap-northeast-1:123456789012:subscription/aws-foundational-security-best-practices/v/1.0.0/SNS.1/finding/abc123",
  "GSI2SK": "2025-01-30T07:31:31.412121+00:00",
  "GSI3PK": "ACCOUNT#123456789012",
  "GSI3SK": "2025-01-30T07:31:31.412121+00:00",

  "taskId": "21e9b3e3-8913-48e8-8e59-05104e3ae6bd",
  "findingId": "arn:aws:securityhub:ap-northeast-1:123456789012:subscription/aws-foundational-security-best-practices/v/1.0.0/SNS.1/finding/abc123",
  "controlId": "SNS.1",
  "status": "waiting_approval",
  "phase": "pre_approval",
  "severity": "HIGH",

  "resourceType": "AwsSnsTopic",
  "resourceId": "arn:aws:sns:ap-northeast-1:123456789012:my-topic",
  "awsAccountId": "123456789012",
  "region": "ap-northeast-1",

  "canRemediate": true,
  "asrMatch": {
    "matched": true,
    "playbook_id": "ASR_SNS_1"
  },

  "memorySessionId": "session-task-21e9b3e3-8913-48e8-8e59-05104e3ae6bd",
  "actorId": "123456789012",

  "createdAt": "2025-01-30T07:31:31.412121+00:00",
  "updatedAt": "2025-01-30T07:31:57.845146+00:00",
  "version": 1,
  "traceId": "da27c4ac-01e8-4f59-9cef-0bdbc0ca7ce5"
}
```

**示例数据 (Phase 2 - 执行完成)：**
```json
{
  "PK": "TASK#21e9b3e3-8913-48e8-8e59-05104e3ae6bd",
  "SK": "METADATA",
  "GSI1PK": "STATUS#completed",
  "GSI1SK": "2025-01-30T07:31:31.412121+00:00",

  "taskId": "21e9b3e3-8913-48e8-8e59-05104e3ae6bd",
  "controlId": "SNS.1",
  "status": "completed",
  "phase": "post_approval",

  "canRemediate": true,
  "asrMatch": {
    "matched": true,
    "playbook_id": "ASR_SNS_1"
  },

  "updatedAt": "2025-01-30T08:00:00.000000+00:00"
}
```

**注意：** 分析结果、修复方案等详细信息不存储到 DynamoDB，而是直接用于生成审批邮件内容。这样可以大幅减少存储空间和写入成本。

### 2.2 Task Events (已废弃)

> **注意：** 从 v3.1 开始，Task Events 表已废弃。任务状态变更直接在 Tasks 表的单条记录上进行更新，不再创建独立的事件记录。这简化了数据模型并减少了 DynamoDB 写入成本。
>
> 如果需要审计追踪，可通过 CloudWatch Logs 或 DynamoDB Streams 实现。

### 2.3 Approval Tokens 表

存储审批 Token 信息，用于验证和防止重放攻击。

**表名：** `shara-approval-tokens`

**用途：**
- 为每个待审批任务生成唯一的 approve/reject token
- 验证审批请求的有效性
- 防止 token 重复使用
- 通过 TTL 自动清理过期 token

**主键设计：**
| 键类型 | 属性名 | 类型 | 说明 |
|--------|--------|------|------|
| Partition Key | PK | String | `TOKEN#<tokenHash>` |
| Sort Key | SK | String | `TASK#<taskId>` |

**属性定义：**

```typescript
interface ApprovalTokenItem {
  // Keys
  PK: string;                   // TOKEN#<sha256Hash>
  SK: string;                   // TASK#<taskId>

  // Token 信息
  token: string;                // 原始 token (UUID)
  token_hash: string;           // SHA256 hash
  taskId: string;               // 关联的任务 ID
  action: 'approve' | 'reject'; // Token 类型

  // 时间信息
  createdAt: string;            // ISO8601 创建时间
  expiresAt: string;            // ISO8601 过期时间
  expires_at: number;           // Unix timestamp (DynamoDB TTL)

  // 使用状态
  used: boolean;                // 是否已使用
}
```

**示例数据：**
```json
{
  "PK": "TOKEN#a1b2c3d4e5f6...",
  "SK": "TASK#21e9b3e3-8913-48e8-8e59-05104e3ae6bd",
  "token": "550e8400-e29b-41d4-a716-446655440000",
  "token_hash": "a1b2c3d4e5f6...",
  "taskId": "21e9b3e3-8913-48e8-8e59-05104e3ae6bd",
  "action": "approve",
  "createdAt": "2025-01-30T07:31:57.845146+00:00",
  "expiresAt": "2025-01-31T07:31:57.845146+00:00",
  "expires_at": 1738312317,
  "used": false
}
```

**设计说明：**
1. 每个任务生成两个 token：一个 approve，一个 reject
2. Token 通过 SHA256 哈希存储，PK 使用哈希值
3. TTL 使用 `expires_at` 字段，自动清理过期 token

### 2.4 Rollback Data 表

存储修复前的资源状态和回滚方案，用于支持回滚操作。

**表名：** `shara-tasks` (与 Tasks 表共用，使用不同的 SK)

**主键设计：**
| 键类型 | 属性名 | 类型 | 说明 |
|--------|--------|------|------|
| Partition Key | PK | String | `TASK#<taskId>` |
| Sort Key | SK | String | `ROLLBACK#<resourceArn>` |

**属性定义：**

```typescript
interface RollbackDataItem {
  PK: string;                   // TASK#<taskId>
  SK: string;                   // ROLLBACK#<resourceArn>

  taskId: string;
  resourceArn: string;
  resourceType: string;         // AwsS3Bucket, AwsEc2SecurityGroup, etc.

  // 修复前的完整资源状态
  preState: {
    // S3 示例
    PublicAccessBlockConfiguration?: {
      BlockPublicAcls: boolean;
      IgnorePublicAcls: boolean;
      BlockPublicPolicy: boolean;
      RestrictPublicBuckets: boolean;
    };
    BucketPolicy?: string;
    // 其他资源类型的配置...
    [key: string]: any;
  };

  // Analyzer 生成的回滚方案
  rollbackPlan: {
    summary: string;
    steps: Array<{
      order: number;
      description: string;
      action: {
        service: string;
        operation: string;
        parameters: Record<string, any>;
      };
      code: string;  // Python/Boto3 代码
    }>;
    generatedCode: string;  // 完整回滚代码
  };

  createdAt: string;            // ISO8601
  ttl: number;                  // 30 天后过期
}
```

**示例数据：**
```json
{
  "PK": "TASK#task-12345678",
  "SK": "ROLLBACK#arn:aws:s3:::my-bucket",
  "taskId": "task-12345678",
  "resourceArn": "arn:aws:s3:::my-bucket",
  "resourceType": "AwsS3Bucket",
  "preState": {
    "PublicAccessBlockConfiguration": {
      "BlockPublicAcls": false,
      "IgnorePublicAcls": false,
      "BlockPublicPolicy": false,
      "RestrictPublicBuckets": false
    },
    "BucketPolicy": "{\"Version\":\"2012-10-17\",\"Statement\":[...]}"
  },
  "rollbackPlan": {
    "summary": "恢复 S3 Block Public Access 到原始配置",
    "steps": [
      {
        "order": 1,
        "description": "恢复 Block Public Access 配置",
        "action": {
          "service": "s3",
          "operation": "PutPublicAccessBlock",
          "parameters": {
            "Bucket": "my-bucket",
            "PublicAccessBlockConfiguration": "${preState.PublicAccessBlockConfiguration}"
          }
        },
        "code": "s3.put_public_access_block(Bucket='my-bucket', PublicAccessBlockConfiguration=pre_state['PublicAccessBlockConfiguration'])"
      }
    ],
    "generatedCode": "..."
  },
  "createdAt": "2025-01-29T10:00:00Z",
  "ttl": 1740825600
}
```

### 2.5 Configuration 表

存储系统配置。

**表名：** `shara-configuration`

**主键设计：**
| 键类型 | 属性名 | 类型 | 说明 |
|--------|--------|------|------|
| Partition Key | PK | String | `CONFIG#<scope>` |
| Sort Key | SK | String | `<configKey>` |

**配置示例：**

```json
// 全局配置
{
  "PK": "CONFIG#GLOBAL",
  "SK": "notification",
  "adminEmails": ["security-team@example.com"],
  "approvalTimeoutHours": 24,
  "enableDryRun": true,
  "defaultPriority": "normal"
}

// 服务特定配置
{
  "PK": "CONFIG#SERVICE#s3",
  "SK": "remediation",
  "autoRemediate": false,
  "allowedActions": ["PutPublicAccessBlock", "PutBucketPolicy"],
  "blockedBuckets": ["critical-data-*"]
}

// 账户特定配置
{
  "PK": "CONFIG#ACCOUNT#123456789012",
  "SK": "settings",
  "enabled": true,
  "severityFilter": ["HIGH", "CRITICAL"],
  "excludedResources": ["arn:aws:s3:::legacy-bucket"]
}
```

---

## 3. S3 存储结构

### 3.1 知识库存储（修复经验）

SHARA 采用"经验学习"模式，知识库包含两类经验：
1. **ASR 预置经验** - 从 AWS Automated Security Response 转换的 110 个修复经验，作为初始知识库
2. **用户验证经验** - 用户确认修复有效后保存的经验，持续积累

**Bucket:** `shara-knowledge-<stage>-<account-id>`

```
shara-knowledge-{stage}-{account}/
├── index.json                         # 知识库索引（包含所有经验的元数据）
└── experiences/                       # 修复经验目录
    ├── S3_1/                          # 按 Control ID 分类（下划线替代点号）
    │   ├── ASR_S3_1.json              # ASR 预置经验
    │   ├── ASR_S3_1_code.py           # ASR 修复代码
    │   ├── USER_S3_1_20250129.json    # 用户验证经验
    │   └── USER_S3_1_20250129_code.py # 用户修复代码
    ├── EC2_2/
    │   ├── ASR_EC2_2.json
    │   └── ASR_EC2_2_code.py
    ├── CloudTrail_4/
    │   └── ...
    └── ...
```

### 3.2 ASR 预置经验格式

从 AWS Automated Security Response 转换的预置经验：

```json
// experiences/S3_1/ASR_S3_1.json
{
  "experience_id": "ASR_S3_1",
  "control_id": "S3.1",
  "standard": "AFSBP",
  "title": "S3 Block Public Access setting should be enabled",
  "description": "This control checks whether S3 Block Public Access is enabled at the bucket level",
  "resource_type": "AwsS3Bucket",
  "remediation": {
    "summary": "Enable S3 Block Public Access",
    "approach": "Configure bucket-level block public access settings to prevent public access",
    "parameters": [
      {
        "name": "BlockPublicAcls",
        "type": "boolean",
        "default": true,
        "description": "Block public ACLs"
      },
      {
        "name": "IgnorePublicAcls",
        "type": "boolean",
        "default": true,
        "description": "Ignore public ACLs"
      },
      {
        "name": "BlockPublicPolicy",
        "type": "boolean",
        "default": true,
        "description": "Block public bucket policies"
      },
      {
        "name": "RestrictPublicBuckets",
        "type": "boolean",
        "default": true,
        "description": "Restrict public bucket access"
      }
    ],
    "code_file": "ASR_S3_1_code.py"
  },
  "is_destructive": false,
  "source": "AWS Automated Security Response",
  "created_at": "2025-01-29T05:45:46Z",
  "validated_count": 0
}
```

### 3.3 知识库索引格式 (index.json)

索引文件提供快速的精确匹配查询，避免每次都进行语义搜索：

```json
{
  "version": "1.0.0",
  "generated_at": "2025-01-29T05:45:46Z",
  "source": "AWS Automated Security Response",
  "statistics": {
    "total_experiences": 110,
    "by_standard": {
      "AFSBP": 68,
      "CIS120": 16,
      "PCI321": 26
    },
    "destructive_count": 12
  },
  "controls": [
    {
      "control_id": "S3.1",
      "standard": "AFSBP",
      "experience_id": "ASR_S3_1",
      "is_destructive": false,
      "path": "experiences/S3_1"
    },
    {
      "control_id": "EC2.2",
      "standard": "AFSBP",
      "experience_id": "ASR_EC2_2",
      "is_destructive": true,
      "path": "experiences/EC2_2"
    }
    // ... 110 entries total
  ]
}
```

### 3.4 用户验证经验格式

```json
// experiences/S3_1/USER_S3_1_20250129.json
{
  "task_id": "task-12345678-abcd-efgh-ijkl",
  "control_id": "S3.1",
  "finding_title": "S3 Block Public Access setting is disabled for account",
  "finding_type": "Software and Configuration Checks/AWS Security Best Practices",

  "resource": {
    "type": "AwsS3Bucket",
    "id": "arn:aws:s3:::my-bucket",
    "region": "ap-northeast-1",
    "account_id": "123456789012"
  },

  "analysis": {
    "summary": "S3 存储桶 my-bucket 未启用 Block Public Access，存在数据泄露风险",
    "risk_level": "HIGH",
    "risk_factors": [
      "存储桶包含敏感配置文件",
      "位于生产环境"
    ],
    "root_cause": "存储桶创建时未启用默认的公共访问阻止设置"
  },

  "remediation": {
    "approach": "启用 S3 Block Public Access 阻止所有公共访问",
    "steps": [
      {
        "order": 1,
        "description": "配置 Block Public Access",
        "service": "s3",
        "operation": "PutPublicAccessBlock"
      }
    ],
    "impact_assessment": {
      "service_impact": "none",
      "downtime": "none",
      "data_loss": false
    }
  },

  "generated_code": "import boto3\n\ns3 = boto3.client('s3')\n\ns3.put_public_access_block(\n    Bucket='my-bucket',\n    PublicAccessBlockConfiguration={\n        'BlockPublicAcls': True,\n        'IgnorePublicAcls': True,\n        'BlockPublicPolicy': True,\n        'RestrictPublicBuckets': True\n    }\n)",

  "lessons_learned": "对于包含敏感数据的存储桶，应在创建时就启用 Block Public Access。建议配置 SCP 强制所有新建存储桶启用此设置。",

  "references": {
    "aws_documentation": [
      "https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html"
    ],
    "knowledge_base_hits": []
  },

  "metadata": {
    "rating": "effective",
    "rated_by": "admin@example.com",
    "rated_at": "2025-01-29T12:00:00Z",
    "created_at": "2025-01-29T10:00:00Z",
    "execution_duration_seconds": 3
  }
}
```

### 3.5 修复代码文件格式

```python
# experiences/S3.1/{task_id}_code.py
"""
修复方案: S3 Block Public Access setting is disabled for account
Control ID: S3.1
Resource: arn:aws:s3:::my-bucket
Generated: 2025-01-29T10:00:00Z
"""

import boto3

def remediate(bucket_name: str) -> dict:
    """
    启用 S3 Block Public Access

    Args:
        bucket_name: S3 存储桶名称

    Returns:
        dict: 执行结果
    """
    s3 = boto3.client('s3')

    # 配置 Block Public Access
    s3.put_public_access_block(
        Bucket=bucket_name,
        PublicAccessBlockConfiguration={
            'BlockPublicAcls': True,
            'IgnorePublicAcls': True,
            'BlockPublicPolicy': True,
            'RestrictPublicBuckets': True
        }
    )

    return {
        'success': True,
        'message': f'Successfully enabled Block Public Access for {bucket_name}'
    }


def rollback(bucket_name: str, pre_state: dict) -> dict:
    """
    回滚 S3 Block Public Access 配置

    Args:
        bucket_name: S3 存储桶名称
        pre_state: 修复前的配置状态

    Returns:
        dict: 回滚结果
    """
    s3 = boto3.client('s3')

    # 恢复原始配置
    s3.put_public_access_block(
        Bucket=bucket_name,
        PublicAccessBlockConfiguration=pre_state['PublicAccessBlockConfiguration']
    )

    return {
        'success': True,
        'message': f'Successfully rolled back Block Public Access for {bucket_name}'
    }


if __name__ == '__main__':
    # 示例用法
    result = remediate('my-bucket')
    print(result)
```

### 3.6 工件存储

**Bucket:** `shara-artifacts-<stage>-<account-id>`

```
shara-artifacts-{stage}-{account}/
├── tasks/                             # 任务相关文件
│   ├── {task_id}/
│   │   ├── finding.json               # 原始 Finding
│   │   ├── analysis.json              # 分析结果
│   │   ├── remediation-plan.json      # 修复方案
│   │   ├── execution-log.json         # 执行日志
│   │   └── audit-trail.json           # 审计记录
│   └── ...
├── reports/                           # 报告目录
│   ├── daily/
│   │   ├── 2025/
│   │   │   └── 01/
│   │   │       ├── 29/
│   │   │       │   ├── summary.json
│   │   │       │   └── findings-processed.json
│   │   │       └── ...
│   └── monthly/
│       └── ...
└── exports/                           # 导出文件
    └── ...
```

---

## 4. 核心数据对象

### 4.1 Finding 对象 (ASFF 格式)

基于 AWS Security Finding Format (ASFF)：

```typescript
interface SecurityFinding {
  SchemaVersion: string;
  Id: string;
  ProductArn: string;
  ProductName?: string;
  CompanyName?: string;
  Region: string;
  GeneratorId: string;
  AwsAccountId: string;

  Types: string[];

  FirstObservedAt?: string;
  LastObservedAt?: string;
  CreatedAt: string;
  UpdatedAt: string;

  Severity: {
    Label: 'INFORMATIONAL' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
    Normalized: number;  // 0-100
    Original?: string;
  };

  Title: string;
  Description: string;

  Remediation?: {
    Recommendation: {
      Text?: string;
      Url?: string;
    };
  };

  Resources: Array<{
    Type: string;
    Id: string;
    Partition?: string;
    Region?: string;
    Tags?: Record<string, string>;
    Details?: Record<string, any>;
  }>;

  Compliance?: {
    Status: 'PASSED' | 'WARNING' | 'FAILED' | 'NOT_AVAILABLE';
    RelatedRequirements?: string[];
  };

  Workflow?: {
    Status: 'NEW' | 'NOTIFIED' | 'RESOLVED' | 'SUPPRESSED';
  };

  RecordState: 'ACTIVE' | 'ARCHIVED';

  Note?: {
    Text: string;
    UpdatedBy: string;
    UpdatedAt: string;
  };
}
```

### 4.2 修复方案对象

```typescript
interface RemediationPlan {
  id: string;
  taskId: string;
  findingId: string;

  summary: string;
  description: string;

  riskAssessment: {
    level: 'LOW' | 'MEDIUM' | 'HIGH';
    factors: string[];
    mitigations: string[];
  };

  impactAnalysis: {
    affectedResources: string[];
    serviceImpact: string;
    downtime: 'none' | 'minimal' | 'significant';
    dataLoss: boolean;
  };

  steps: RemediationStep[];

  rollback: {
    available: boolean;
    automatic: boolean;
    steps?: RemediationStep[];
    timeLimit?: string;  // ISO8601 Duration
  };

  prerequisites?: {
    permissions: string[];
    resources: string[];
    conditions: string[];
  };

  generatedCode: {
    awsCli?: string;
    cloudformation?: string;
    terraform?: string;
    python?: string;
  };

  metadata: {
    generatedAt: string;
    generatedBy: string;
    playbookId?: string;
    playbookVersion?: string;
    confidence: number;  // 0-1
  };
}
```

### 4.3 审批请求对象

```typescript
interface ApprovalRequest {
  id: string;
  taskId: string;
  findingId: string;

  status: 'pending' | 'approved' | 'rejected' | 'expired';

  requestedAt: string;
  expiresAt: string;

  requestedBy: string;

  recipients: string[];

  finding: {
    title: string;
    severity: string;
    resourceId: string;
    description: string;
  };

  remediation: {
    summary: string;
    steps: string[];
    riskLevel: string;
    rollbackAvailable: boolean;
  };

  approvalUrl: string;
  rejectUrl: string;
  detailsUrl: string;

  response?: {
    action: 'approve' | 'reject';
    respondedAt: string;
    respondedBy: string;
    reason?: string;
    notes?: string;
  };
}
```

---

## 5. 数据生命周期

### 5.1 数据保留策略

| 数据类型 | 保留期限 | 存储位置 | 归档策略 |
|----------|----------|----------|----------|
| 活跃任务 | 30 天 | DynamoDB | 完成后 7 天归档 |
| 审批 Token | Token 过期后自动删除 | DynamoDB (TTL) | 自动删除 |
| 任务报告 | 1 年 | S3 | Glacier 深度归档 |
| 审计日志 | 7 年 | S3 + CloudTrail | 合规要求 |

### 5.2 DynamoDB TTL 配置

```typescript
// Tasks 表 - 完成的任务 30 天后删除
if (task.status === 'completed' || task.status === 'cancelled') {
  task.ttl = Math.floor(Date.now() / 1000) + (30 * 24 * 60 * 60);
}

// Tokens 表 - 使用 expires_at 字段，token 过期后自动删除
token.expires_at = Math.floor(new Date(token.expiresAt).getTime() / 1000);
```

### 5.3 S3 生命周期规则

```json
{
  "Rules": [
    {
      "ID": "ArchiveOldReports",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "tasks/"
      },
      "Transitions": [
        {
          "Days": 90,
          "StorageClass": "STANDARD_IA"
        },
        {
          "Days": 365,
          "StorageClass": "GLACIER"
        }
      ]
    },
    {
      "ID": "DeleteOldDailyReports",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "daily/"
      },
      "Expiration": {
        "Days": 365
      }
    }
  ]
}
```

---

## 6. 索引和查询模式

### 6.1 常用查询模式

| 查询场景 | 使用的索引 | 查询条件 |
|----------|------------|----------|
| 按任务 ID 查询 | 主键 | PK = TASK#<id>, SK = METADATA |
| 按状态查询任务 | GSI1 | GSI1PK = STATUS#<status> |
| 按 Finding 查询 | GSI2 | GSI2PK = FINDING#<id> |
| 按账户查询 | GSI3 | GSI3PK = ACCOUNT#<id> |
| 查询审批 Token | 主键 | PK = TOKEN#<hash>, SK = TASK#<id> |

### 6.2 查询示例

```python
# 查询所有待审批任务
response = tasks_table.query(
    IndexName='GSI1',
    KeyConditionExpression='GSI1PK = :pk',
    ExpressionAttributeValues={
        ':pk': 'STATUS#waiting_approval'
    },
    ScanIndexForward=False,  # 最新的优先
    Limit=50
)

# 查询特定 Finding 的处理历史
response = tasks_table.query(
    IndexName='GSI2',
    KeyConditionExpression='GSI2PK = :pk',
    ExpressionAttributeValues={
        ':pk': f'FINDING#{finding_id}'
    }
)

# 查询单个任务详情
response = tasks_table.get_item(
    Key={
        'PK': f'TASK#{task_id}',
        'SK': 'METADATA'
    }
)

# 验证审批 Token
import hashlib
token_hash = hashlib.sha256(token.encode()).hexdigest()
response = tokens_table.get_item(
    Key={
        'PK': f'TOKEN#{token_hash}',
        'SK': f'TASK#{task_id}'
    }
)
```

---

## 7. 文档版本

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| 1.0 | 2025-01-28 | - | 初始版本 |
| 2.0 | 2025-01-29 | - | 更新任务状态；增加 Rollback Data 数据模型；重构知识库为经验学习模式 |
| 2.1 | 2025-01-29 | - | 新增 ASR 预置经验数据格式；新增知识库索引 (index.json) 格式；区分 ASR 和用户经验 |
| 3.0 | 2025-01-29 | - | 重构为两阶段工作流（Phase 1: 审批前仅生成描述；Phase 2: 审批后生成代码执行）；分离 remediation 和 generatedCode；新增 phase 和 memorySessionId 字段 |
| 3.1 | 2025-01-30 | - | 简化数据模型：废弃 Task Events 表，状态变更直接更新 Tasks 表；Tasks 表只存储控制相关字段，不存储分析结果；更新 Approval Tokens 表结构；优化 DynamoDB 存储空间（记录大小减少约 68%）|
