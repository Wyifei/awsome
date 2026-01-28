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
  GSI1SK: string;               // <createdAt>
  GSI2PK: string;               // FINDING#<findingId>
  GSI2SK: string;               // <createdAt>
  GSI3PK: string;               // ACCOUNT#<accountId>
  GSI3SK: string;               // <createdAt>

  // Core Attributes
  taskId: string;               // UUID
  findingId: string;            // Security Hub Finding ARN
  status: TaskStatus;           // 任务状态
  severity: 'HIGH' | 'CRITICAL';
  source: string;               // AWS Config, GuardDuty, etc.

  // Finding Summary
  findingTitle: string;
  findingDescription: string;
  resourceType: string;         // AwsS3Bucket, AwsEc2Instance, etc.
  resourceId: string;           // Resource ARN
  awsAccountId: string;
  region: string;

  // Analysis Results
  analysis?: {
    riskLevel: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
    impactAssessment: string;
    affectedResources: string[];
    recommendations: string[];
    analyzedAt: string;         // ISO8601
    analyzedBy: string;         // Agent ID
  };

  // Remediation Plan
  remediation?: {
    summary: string;
    steps: RemediationStep[];
    estimatedImpact: string;
    rollbackAvailable: boolean;
    rollbackPlan?: string[];
    generatedCode?: {
      type: 'aws-cli' | 'cloudformation' | 'terraform';
      content: string;
    };
    generatedAt: string;
    generatedBy: string;
  };

  // Approval Info
  approval?: {
    status: 'pending' | 'approved' | 'rejected' | 'expired';
    requestedAt: string;
    expiresAt: string;
    token: string;              // Hashed token
    respondedAt?: string;
    respondedBy?: string;
    action?: 'approve' | 'reject';
    reason?: string;
    notes?: string;
  };

  // Execution Info
  execution?: {
    status: 'pending' | 'running' | 'success' | 'failed' | 'rolled_back';
    startedAt?: string;
    completedAt?: string;
    error?: {
      code: string;
      message: string;
      details?: any;
    };
    outputs?: Record<string, any>;
  };

  // Metadata
  createdAt: string;            // ISO8601
  updatedAt: string;            // ISO8601
  ttl?: number;                 // Unix timestamp for auto-deletion
  version: number;              // Optimistic locking

  // Tracing
  traceId?: string;
  spanId?: string;
}

type TaskStatus =
  | 'created'
  | 'analyzing'
  | 'analysis_failed'
  | 'planning'
  | 'planning_failed'
  | 'pending_approval'
  | 'approved'
  | 'rejected'
  | 'approval_expired'
  | 'executing'
  | 'execution_failed'
  | 'validating'
  | 'completed'
  | 'cancelled';

interface RemediationStep {
  order: number;
  action: string;
  description: string;
  service: string;
  operation: string;
  parameters?: Record<string, any>;
  status?: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  result?: any;
  error?: string;
}
```

**示例数据：**
```json
{
  "PK": "TASK#task-12345678-abcd-efgh-ijkl-mnopqrstuvwx",
  "SK": "METADATA",
  "GSI1PK": "STATUS#pending_approval",
  "GSI1SK": "2025-01-28T10:00:00Z",
  "GSI2PK": "FINDING#arn:aws:securityhub:us-east-1:123456789012:finding/abc123",
  "GSI2SK": "2025-01-28T10:00:00Z",
  "GSI3PK": "ACCOUNT#123456789012",
  "GSI3SK": "2025-01-28T10:00:00Z",

  "taskId": "task-12345678-abcd-efgh-ijkl-mnopqrstuvwx",
  "findingId": "arn:aws:securityhub:us-east-1:123456789012:finding/abc123",
  "status": "pending_approval",
  "severity": "HIGH",
  "source": "AWS Config",

  "findingTitle": "S3 bucket has public read access",
  "findingDescription": "S3 bucket 'my-bucket' is configured to allow public read access",
  "resourceType": "AwsS3Bucket",
  "resourceId": "arn:aws:s3:::my-bucket",
  "awsAccountId": "123456789012",
  "region": "us-east-1",

  "analysis": {
    "riskLevel": "HIGH",
    "impactAssessment": "该 bucket 包含敏感配置文件，公开访问可能导致数据泄露",
    "affectedResources": ["arn:aws:s3:::my-bucket"],
    "recommendations": ["启用 Block Public Access", "审查 Bucket Policy"],
    "analyzedAt": "2025-01-28T10:02:00Z",
    "analyzedBy": "analyzer-agent-v1"
  },

  "remediation": {
    "summary": "移除 S3 bucket 的公开访问权限",
    "steps": [
      {
        "order": 1,
        "action": "EnableBlockPublicAccess",
        "description": "启用 Block Public Access",
        "service": "s3",
        "operation": "PutPublicAccessBlock",
        "parameters": {
          "Bucket": "my-bucket",
          "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": true,
            "IgnorePublicAcls": true,
            "BlockPublicPolicy": true,
            "RestrictPublicBuckets": true
          }
        },
        "status": "pending"
      }
    ],
    "estimatedImpact": "LOW",
    "rollbackAvailable": true,
    "generatedCode": {
      "type": "aws-cli",
      "content": "aws s3api put-public-access-block --bucket my-bucket ..."
    },
    "generatedAt": "2025-01-28T10:04:00Z",
    "generatedBy": "remediator-agent-v1"
  },

  "approval": {
    "status": "pending",
    "requestedAt": "2025-01-28T10:05:00Z",
    "expiresAt": "2025-01-29T10:05:00Z",
    "token": "sha256:abc123..."
  },

  "createdAt": "2025-01-28T10:00:00Z",
  "updatedAt": "2025-01-28T10:05:00Z",
  "version": 3
}
```

### 2.2 Task Events 表

存储任务的事件历史记录。

**表名：** `shara-task-events`

**主键设计：**
| 键类型 | 属性名 | 类型 | 说明 |
|--------|--------|------|------|
| Partition Key | PK | String | `TASK#<taskId>` |
| Sort Key | SK | String | `EVENT#<timestamp>#<eventId>` |

**属性定义：**

```typescript
interface TaskEventItem {
  PK: string;                   // TASK#<taskId>
  SK: string;                   // EVENT#<timestamp>#<eventId>

  taskId: string;
  eventId: string;
  eventType: TaskEventType;
  timestamp: string;

  actor?: {
    type: 'system' | 'agent' | 'user' | 'lambda';
    id: string;
    name?: string;
  };

  data?: Record<string, any>;

  metadata?: {
    traceId?: string;
    spanId?: string;
    duration_ms?: number;
  };

  ttl: number;                  // 90 days retention
}

type TaskEventType =
  | 'task_created'
  | 'finding_received'
  | 'analysis_started'
  | 'analysis_completed'
  | 'analysis_failed'
  | 'remediation_planned'
  | 'approval_requested'
  | 'approval_email_sent'
  | 'approval_received'
  | 'approval_expired'
  | 'execution_started'
  | 'execution_step_completed'
  | 'execution_completed'
  | 'execution_failed'
  | 'validation_started'
  | 'validation_completed'
  | 'finding_updated'
  | 'task_cancelled'
  | 'error_occurred';
```

### 2.3 Approval Tokens 表

存储审批 Token 信息，用于验证和防止重放攻击。

**表名：** `shara-approval-tokens`

**主键设计：**
| 键类型 | 属性名 | 类型 | 说明 |
|--------|--------|------|------|
| Partition Key | PK | String | `TOKEN#<tokenHash>` |
| Sort Key | SK | String | `TASK#<taskId>` |

**属性定义：**

```typescript
interface ApprovalTokenItem {
  PK: string;                   // TOKEN#<sha256Hash>
  SK: string;                   // TASK#<taskId>

  taskId: string;
  tokenHash: string;            // SHA256 hash of token

  issuedAt: string;
  expiresAt: string;

  used: boolean;
  usedAt?: string;
  usedAction?: 'approve' | 'reject';
  usedBy?: string;
  usedFromIp?: string;

  ttl: number;                  // Token expiry + 1 day
}
```

### 2.4 Configuration 表

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

### 3.1 知识库存储

**Bucket:** `shara-knowledge-base-<account-id>-<region>`

```
shara-knowledge-base/
├── playbooks/
│   ├── s3/
│   │   ├── public-access/
│   │   │   ├── playbook.md
│   │   │   ├── remediation.json
│   │   │   └── templates/
│   │   │       ├── cloudformation.yaml
│   │   │       └── cli-commands.sh
│   │   ├── encryption/
│   │   └── logging/
│   ├── ec2/
│   │   ├── security-group/
│   │   ├── instance-metadata/
│   │   └── ebs-encryption/
│   ├── iam/
│   │   ├── overprivileged-role/
│   │   ├── access-key-rotation/
│   │   └── mfa-enforcement/
│   ├── rds/
│   ├── lambda/
│   └── ...
├── templates/
│   ├── cloudformation/
│   │   ├── s3-secure-bucket.yaml
│   │   ├── vpc-flow-logs.yaml
│   │   └── ...
│   └── terraform/
│       ├── s3-secure-bucket.tf
│       └── ...
├── policies/
│   ├── remediation-policies.json
│   ├── exclusion-rules.json
│   └── risk-assessment-rules.json
└── index.json
```

### 3.2 Playbook 格式

```json
// playbooks/s3/public-access/remediation.json
{
  "id": "s3-public-access",
  "name": "S3 Public Access Remediation",
  "version": "1.0.0",
  "description": "修复 S3 bucket 公开访问问题",

  "triggers": {
    "findingTypes": [
      "Software and Configuration Checks/AWS Security Best Practices/S3.2"
    ],
    "resourceTypes": ["AwsS3Bucket"],
    "severities": ["HIGH", "CRITICAL"]
  },

  "analysis": {
    "contextRequired": [
      "s3:GetBucketPolicy",
      "s3:GetBucketAcl",
      "s3:GetPublicAccessBlock",
      "s3:GetBucketLocation"
    ],
    "riskFactors": [
      {
        "condition": "bucket contains sensitive data tags",
        "multiplier": 1.5
      },
      {
        "condition": "bucket is in production account",
        "multiplier": 1.2
      }
    ]
  },

  "remediation": {
    "strategy": "block_public_access",
    "steps": [
      {
        "order": 1,
        "name": "enable_block_public_access",
        "description": "启用账户级别的 Block Public Access",
        "action": {
          "service": "s3",
          "operation": "PutPublicAccessBlock",
          "parameters": {
            "Bucket": "${resourceName}",
            "PublicAccessBlockConfiguration": {
              "BlockPublicAcls": true,
              "IgnorePublicAcls": true,
              "BlockPublicPolicy": true,
              "RestrictPublicBuckets": true
            }
          }
        },
        "rollback": {
          "service": "s3",
          "operation": "DeletePublicAccessBlock",
          "parameters": {
            "Bucket": "${resourceName}"
          }
        }
      },
      {
        "order": 2,
        "name": "update_bucket_policy",
        "description": "移除公开访问的 Policy 语句",
        "condition": "bucket_policy_has_public_statements",
        "action": {
          "service": "s3",
          "operation": "PutBucketPolicy",
          "parameters": {
            "Bucket": "${resourceName}",
            "Policy": "${securedPolicy}"
          }
        }
      }
    ],
    "validation": {
      "checks": [
        {
          "name": "verify_block_public_access",
          "action": {
            "service": "s3",
            "operation": "GetPublicAccessBlock",
            "parameters": {
              "Bucket": "${resourceName}"
            }
          },
          "expectedResult": {
            "PublicAccessBlockConfiguration.BlockPublicAcls": true,
            "PublicAccessBlockConfiguration.IgnorePublicAcls": true,
            "PublicAccessBlockConfiguration.BlockPublicPolicy": true,
            "PublicAccessBlockConfiguration.RestrictPublicBuckets": true
          }
        }
      ]
    }
  },

  "notifications": {
    "onSuccess": {
      "template": "remediation-success",
      "includeDetails": true
    },
    "onFailure": {
      "template": "remediation-failure",
      "escalate": true
    }
  }
}
```

### 3.3 报告存储

**Bucket:** `shara-reports-<account-id>-<region>`

```
shara-reports/
├── daily/
│   ├── 2025/
│   │   └── 01/
│   │       ├── 28/
│   │       │   ├── summary.json
│   │       │   ├── findings-processed.json
│   │       │   └── remediations-executed.json
│   │       └── ...
├── tasks/
│   ├── task-12345678/
│   │   ├── finding.json
│   │   ├── analysis.json
│   │   ├── remediation-plan.json
│   │   ├── execution-log.json
│   │   └── audit-trail.json
│   └── ...
└── exports/
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
| 任务事件 | 90 天 | DynamoDB (TTL) | 自动删除 |
| 审批 Token | Token 过期 + 1 天 | DynamoDB (TTL) | 自动删除 |
| 任务报告 | 1 年 | S3 | Glacier 深度归档 |
| 审计日志 | 7 年 | S3 + CloudTrail | 合规要求 |

### 5.2 DynamoDB TTL 配置

```typescript
// Tasks 表 - 完成的任务 30 天后删除
if (task.status === 'completed' || task.status === 'cancelled') {
  task.ttl = Math.floor(Date.now() / 1000) + (30 * 24 * 60 * 60);
}

// Events 表 - 90 天后删除
event.ttl = Math.floor(Date.now() / 1000) + (90 * 24 * 60 * 60);

// Tokens 表 - 过期后 1 天删除
token.ttl = Math.floor(new Date(token.expiresAt).getTime() / 1000) + (24 * 60 * 60);
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
| 按任务 ID 查询 | 主键 | PK = TASK#<id> |
| 按状态查询任务 | GSI1 | GSI1PK = STATUS#<status> |
| 按 Finding 查询 | GSI2 | GSI2PK = FINDING#<id> |
| 按账户查询 | GSI3 | GSI3PK = ACCOUNT#<id> |
| 查询任务事件 | 主键 | PK = TASK#<id>, SK begins_with EVENT# |

### 6.2 查询示例

```python
# 查询所有待审批任务
response = table.query(
    IndexName='GSI1',
    KeyConditionExpression='GSI1PK = :pk',
    ExpressionAttributeValues={
        ':pk': 'STATUS#pending_approval'
    },
    ScanIndexForward=False,  # 最新的优先
    Limit=50
)

# 查询特定 Finding 的处理历史
response = table.query(
    IndexName='GSI2',
    KeyConditionExpression='GSI2PK = :pk',
    ExpressionAttributeValues={
        ':pk': f'FINDING#{finding_id}'
    }
)

# 查询任务的所有事件
response = events_table.query(
    KeyConditionExpression='PK = :pk AND begins_with(SK, :sk)',
    ExpressionAttributeValues={
        ':pk': f'TASK#{task_id}',
        ':sk': 'EVENT#'
    },
    ScanIndexForward=True  # 按时间顺序
)
```

---

## 7. 文档版本

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| 1.0 | 2025-01-28 | - | 初始版本 |
