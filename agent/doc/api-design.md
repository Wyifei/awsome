# Security Hub Auto-Remediation Agent API 设计文档

## 1. API 概述

### 1.1 API 架构

本系统包含以下 API 接口：

| API 类型 | 用途 | 访问方式 |
|----------|------|----------|
| 审批回调 API | 接收管理员审批响应 | API Gateway (公网) |
| 内部管理 API | 系统管理和监控 | API Gateway (VPC) |
| Agent 调用 API | Lambda 调用 Agent | 内部调用 |

### 1.2 认证方式

| API | 认证方式 | 说明 |
|-----|----------|------|
| 审批回调 | Token-based | JWT Token 验证 |
| 管理 API | IAM | SigV4 签名 |
| 内部 API | IAM | Lambda 执行角色 |

---

## 2. 审批回调 API

### 2.1 审批响应

**POST** `/api/v1/approvals/{taskId}/respond`

处理管理员的审批决定（同意或拒绝）。

#### 请求

**Path Parameters:**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| taskId | string | 是 | 任务 ID |

**Query Parameters:**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| token | string | 是 | 审批 Token |
| action | string | 是 | 操作类型：`approve` 或 `reject` |

**Headers:**
```
Content-Type: application/json
```

**Request Body (可选，用于拒绝时添加原因):**
```json
{
  "reason": "风险过高，需要在维护窗口执行",
  "notes": "计划在周六凌晨执行"
}
```

#### 响应

**200 OK - 审批成功**
```json
{
  "status": "success",
  "message": "Approval recorded successfully",
  "data": {
    "taskId": "task-12345678",
    "findingId": "arn:aws:securityhub:us-east-1:123456789012:finding/abc123",
    "action": "approve",
    "processedAt": "2025-01-28T10:30:00Z",
    "nextStep": "remediation_scheduled",
    "estimatedExecutionTime": "2025-01-28T10:35:00Z"
  }
}
```

**200 OK - 拒绝成功**
```json
{
  "status": "success",
  "message": "Rejection recorded successfully",
  "data": {
    "taskId": "task-12345678",
    "findingId": "arn:aws:securityhub:us-east-1:123456789012:finding/abc123",
    "action": "reject",
    "processedAt": "2025-01-28T10:30:00Z",
    "reason": "风险过高，需要在维护窗口执行"
  }
}
```

**400 Bad Request - 参数错误**
```json
{
  "status": "error",
  "code": "INVALID_PARAMETER",
  "message": "Invalid action parameter. Must be 'approve' or 'reject'",
  "details": {
    "parameter": "action",
    "provided": "maybe",
    "allowed": ["approve", "reject"]
  }
}
```

**401 Unauthorized - Token 无效**
```json
{
  "status": "error",
  "code": "INVALID_TOKEN",
  "message": "The approval token is invalid or has expired",
  "details": {
    "reason": "token_expired",
    "expiredAt": "2025-01-27T10:30:00Z"
  }
}
```

**409 Conflict - 已处理**
```json
{
  "status": "error",
  "code": "ALREADY_PROCESSED",
  "message": "This approval request has already been processed",
  "details": {
    "taskId": "task-12345678",
    "previousAction": "approve",
    "processedAt": "2025-01-28T09:00:00Z",
    "processedBy": "admin@example.com"
  }
}
```

### 2.2 获取审批状态

**GET** `/api/v1/approvals/{taskId}/status`

获取特定任务的审批状态。

#### 请求

**Path Parameters:**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| taskId | string | 是 | 任务 ID |

**Query Parameters:**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| token | string | 是 | 只读访问 Token |

#### 响应

**200 OK**
```json
{
  "status": "success",
  "data": {
    "taskId": "task-12345678",
    "approvalStatus": "pending",
    "finding": {
      "id": "arn:aws:securityhub:us-east-1:123456789012:finding/abc123",
      "title": "S3 bucket has public read access",
      "severity": "HIGH",
      "resourceType": "AwsS3Bucket",
      "resourceId": "arn:aws:s3:::my-bucket"
    },
    "remediationPlan": {
      "summary": "移除 S3 bucket 的公开访问权限",
      "steps": [
        "启用 Block Public Access",
        "更新 Bucket Policy",
        "验证访问权限"
      ],
      "estimatedImpact": "LOW",
      "rollbackAvailable": true
    },
    "createdAt": "2025-01-28T10:00:00Z",
    "expiresAt": "2025-01-29T10:00:00Z"
  }
}
```

---

## 3. 管理 API

### 3.1 任务列表

**GET** `/api/v1/admin/tasks`

获取所有任务列表。

#### 请求

**Query Parameters:**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| status | string | 否 | all | 状态过滤：`pending`, `approved`, `rejected`, `completed`, `failed` |
| severity | string | 否 | all | 严重级别：`HIGH`, `CRITICAL` |
| startDate | string | 否 | 7天前 | 开始日期 (ISO8601) |
| endDate | string | 否 | 当前 | 结束日期 (ISO8601) |
| limit | integer | 否 | 20 | 返回数量 (1-100) |
| nextToken | string | 否 | - | 分页 Token |

**Headers:**
```
Authorization: AWS4-HMAC-SHA256 ...
Content-Type: application/json
```

#### 响应

**200 OK**
```json
{
  "status": "success",
  "data": {
    "tasks": [
      {
        "taskId": "task-12345678",
        "findingId": "arn:aws:securityhub:...",
        "findingTitle": "S3 bucket has public read access",
        "severity": "HIGH",
        "source": "AWS Config",
        "status": "pending_approval",
        "createdAt": "2025-01-28T10:00:00Z",
        "updatedAt": "2025-01-28T10:05:00Z"
      },
      {
        "taskId": "task-87654321",
        "findingId": "arn:aws:securityhub:...",
        "findingTitle": "Security group allows unrestricted SSH access",
        "severity": "CRITICAL",
        "source": "AWS Config",
        "status": "completed",
        "createdAt": "2025-01-28T09:00:00Z",
        "updatedAt": "2025-01-28T09:30:00Z"
      }
    ],
    "pagination": {
      "totalCount": 45,
      "returnedCount": 2,
      "nextToken": "eyJsYXN0S2V5IjoiMTIzNDU2Nzg..."
    }
  }
}
```

### 3.2 任务详情

**GET** `/api/v1/admin/tasks/{taskId}`

获取特定任务的详细信息。

#### 响应

**200 OK**
```json
{
  "status": "success",
  "data": {
    "taskId": "task-12345678",
    "status": "completed",
    "finding": {
      "id": "arn:aws:securityhub:us-east-1:123456789012:finding/abc123",
      "title": "S3 bucket has public read access",
      "description": "S3 bucket 'my-bucket' is configured to allow public read access...",
      "severity": "HIGH",
      "source": "AWS Config",
      "resourceType": "AwsS3Bucket",
      "resourceId": "arn:aws:s3:::my-bucket",
      "awsAccountId": "123456789012",
      "region": "us-east-1",
      "createdAt": "2025-01-28T09:55:00Z"
    },
    "analysis": {
      "riskLevel": "HIGH",
      "impactAssessment": "该 bucket 包含敏感配置文件，公开访问可能导致数据泄露",
      "affectedResources": [
        "arn:aws:s3:::my-bucket",
        "arn:aws:s3:::my-bucket/*"
      ],
      "analyzedAt": "2025-01-28T10:00:00Z"
    },
    "remediation": {
      "summary": "移除 S3 bucket 的公开访问权限",
      "steps": [
        {
          "order": 1,
          "action": "EnableBlockPublicAccess",
          "description": "启用账户级别的 Block Public Access",
          "status": "completed"
        },
        {
          "order": 2,
          "action": "UpdateBucketPolicy",
          "description": "移除允许公开访问的 Policy 语句",
          "status": "completed"
        },
        {
          "order": 3,
          "action": "VerifyAccess",
          "description": "验证 bucket 不再允许公开访问",
          "status": "completed"
        }
      ],
      "generatedCode": {
        "type": "aws-cli",
        "commands": [
          "aws s3api put-public-access-block --bucket my-bucket --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
        ]
      },
      "rollbackPlan": {
        "available": true,
        "steps": [
          "aws s3api delete-public-access-block --bucket my-bucket"
        ]
      }
    },
    "approval": {
      "status": "approved",
      "approvedBy": "admin@example.com",
      "approvedAt": "2025-01-28T10:15:00Z",
      "notes": null
    },
    "execution": {
      "status": "success",
      "startedAt": "2025-01-28T10:16:00Z",
      "completedAt": "2025-01-28T10:17:30Z",
      "logs": [
        {
          "timestamp": "2025-01-28T10:16:00Z",
          "level": "INFO",
          "message": "Starting remediation execution"
        },
        {
          "timestamp": "2025-01-28T10:16:30Z",
          "level": "INFO",
          "message": "Block Public Access enabled successfully"
        },
        {
          "timestamp": "2025-01-28T10:17:00Z",
          "level": "INFO",
          "message": "Bucket policy updated"
        },
        {
          "timestamp": "2025-01-28T10:17:30Z",
          "level": "INFO",
          "message": "Verification passed - bucket is no longer publicly accessible"
        }
      ]
    },
    "timeline": [
      {"event": "finding_received", "timestamp": "2025-01-28T09:55:00Z"},
      {"event": "task_created", "timestamp": "2025-01-28T09:55:30Z"},
      {"event": "analysis_started", "timestamp": "2025-01-28T09:56:00Z"},
      {"event": "analysis_completed", "timestamp": "2025-01-28T10:00:00Z"},
      {"event": "remediation_planned", "timestamp": "2025-01-28T10:05:00Z"},
      {"event": "approval_requested", "timestamp": "2025-01-28T10:05:30Z"},
      {"event": "approval_received", "timestamp": "2025-01-28T10:15:00Z"},
      {"event": "execution_started", "timestamp": "2025-01-28T10:16:00Z"},
      {"event": "execution_completed", "timestamp": "2025-01-28T10:17:30Z"},
      {"event": "finding_updated", "timestamp": "2025-01-28T10:18:00Z"}
    ]
  }
}
```

### 3.3 手动触发处理

**POST** `/api/v1/admin/tasks`

手动创建任务处理指定 Finding。

#### 请求

```json
{
  "findingId": "arn:aws:securityhub:us-east-1:123456789012:finding/abc123",
  "priority": "high",
  "options": {
    "skipApproval": false,
    "dryRun": true,
    "notifyEmail": "security-team@example.com"
  }
}
```

#### 响应

**202 Accepted**
```json
{
  "status": "success",
  "message": "Task created successfully",
  "data": {
    "taskId": "task-new-12345",
    "findingId": "arn:aws:securityhub:us-east-1:123456789012:finding/abc123",
    "status": "created",
    "createdAt": "2025-01-28T10:30:00Z"
  }
}
```

### 3.4 重试任务

**POST** `/api/v1/admin/tasks/{taskId}/retry`

重试失败的任务。

#### 请求

```json
{
  "fromStep": "execution",
  "options": {
    "forceReapproval": false
  }
}
```

#### 响应

**202 Accepted**
```json
{
  "status": "success",
  "message": "Task retry initiated",
  "data": {
    "taskId": "task-12345678",
    "retryCount": 2,
    "retryFromStep": "execution",
    "status": "retrying"
  }
}
```

### 3.5 取消任务

**POST** `/api/v1/admin/tasks/{taskId}/cancel`

取消进行中的任务。

#### 响应

**200 OK**
```json
{
  "status": "success",
  "message": "Task cancelled successfully",
  "data": {
    "taskId": "task-12345678",
    "previousStatus": "pending_approval",
    "currentStatus": "cancelled",
    "cancelledAt": "2025-01-28T10:30:00Z"
  }
}
```

### 3.6 统计数据

**GET** `/api/v1/admin/statistics`

获取系统统计数据。

#### 请求

**Query Parameters:**
| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| period | string | 否 | 7d | 统计周期：`1d`, `7d`, `30d`, `90d` |

#### 响应

**200 OK**
```json
{
  "status": "success",
  "data": {
    "period": "7d",
    "summary": {
      "totalFindings": 156,
      "processedFindings": 142,
      "pendingApproval": 8,
      "approved": 130,
      "rejected": 12,
      "successfulRemediations": 125,
      "failedRemediations": 5
    },
    "bySeverity": {
      "CRITICAL": {
        "total": 23,
        "remediated": 21,
        "pending": 2
      },
      "HIGH": {
        "total": 133,
        "remediated": 104,
        "pending": 6
      }
    },
    "bySource": {
      "AWS Config": 89,
      "GuardDuty": 34,
      "Inspector": 28,
      "Macie": 5
    },
    "byFindingType": {
      "S3 Public Access": 25,
      "Security Group Open": 42,
      "Unencrypted Resources": 31,
      "IAM Overprivileged": 18,
      "Other": 40
    },
    "performance": {
      "avgProcessingTime": "4m 32s",
      "avgApprovalTime": "2h 15m",
      "avgRemediationTime": "1m 45s"
    },
    "trends": {
      "findingsPerDay": [
        {"date": "2025-01-22", "count": 18},
        {"date": "2025-01-23", "count": 22},
        {"date": "2025-01-24", "count": 15},
        {"date": "2025-01-25", "count": 28},
        {"date": "2025-01-26", "count": 19},
        {"date": "2025-01-27", "count": 31},
        {"date": "2025-01-28", "count": 23}
      ]
    }
  }
}
```

---

## 4. 内部 Agent API

### 4.1 Agent 调用接口

这些接口用于系统内部 Lambda 与 Agent 之间的通信。

#### 4.1.1 调用 Orchestrator Agent

**Function:** `shara-orchestrator-agent`

**Input Event:**
```json
{
  "action": "process_finding",
  "taskId": "task-12345678",
  "finding": {
    "id": "arn:aws:securityhub:...",
    "SchemaVersion": "2018-10-08",
    "ProductArn": "arn:aws:securityhub:...",
    "GeneratorId": "aws-config-rules",
    "AwsAccountId": "123456789012",
    "Types": ["Software and Configuration Checks/AWS Security Best Practices"],
    "Title": "S3 bucket has public read access",
    "Description": "...",
    "Severity": {
      "Label": "HIGH",
      "Normalized": 70
    },
    "Resources": [
      {
        "Type": "AwsS3Bucket",
        "Id": "arn:aws:s3:::my-bucket",
        "Region": "us-east-1"
      }
    ],
    "Compliance": {
      "Status": "FAILED"
    }
  },
  "options": {
    "mode": "auto",
    "notifyOnComplete": true
  }
}
```

**Output:**
```json
{
  "status": "success",
  "taskId": "task-12345678",
  "result": {
    "phase": "pending_approval",
    "analysis": {
      "completed": true,
      "riskLevel": "HIGH"
    },
    "remediationPlan": {
      "generated": true,
      "stepsCount": 3
    },
    "approvalRequest": {
      "sent": true,
      "sentAt": "2025-01-28T10:05:30Z",
      "expiresAt": "2025-01-29T10:05:30Z"
    }
  }
}
```

#### 4.1.2 Agent 间通信

**Analyzer -> Remediator:**
```json
{
  "action": "generate_remediation",
  "taskId": "task-12345678",
  "analysis": {
    "findingType": "S3PublicAccess",
    "resourceType": "AwsS3Bucket",
    "resourceId": "arn:aws:s3:::my-bucket",
    "riskLevel": "HIGH",
    "context": {
      "bucketPolicy": {...},
      "publicAccessBlock": {...},
      "bucketAcl": {...}
    },
    "recommendation": "block_public_access"
  }
}
```

**Remediator -> Validator:**
```json
{
  "action": "validate_remediation",
  "taskId": "task-12345678",
  "remediation": {
    "type": "S3PublicAccess",
    "resourceId": "arn:aws:s3:::my-bucket",
    "actions": [
      {
        "service": "s3",
        "operation": "PutPublicAccessBlock",
        "parameters": {...},
        "executed": true,
        "result": "success"
      }
    ]
  },
  "expectedState": {
    "publicAccessBlocked": true,
    "bucketPolicySecure": true
  }
}
```

---

## 5. Webhook 事件

### 5.1 事件类型

系统支持通过 Webhook 推送事件通知：

| 事件类型 | 触发时机 | 说明 |
|----------|----------|------|
| `finding.received` | 接收到新 Finding | Finding 开始处理 |
| `analysis.completed` | 分析完成 | 风险分析结果 |
| `approval.requested` | 发送审批请求 | 等待管理员审批 |
| `approval.received` | 收到审批响应 | 同意或拒绝 |
| `remediation.started` | 开始执行修复 | 修复操作开始 |
| `remediation.completed` | 修复完成 | 成功或失败 |
| `task.failed` | 任务失败 | 处理异常 |

### 5.2 Webhook Payload

```json
{
  "eventType": "remediation.completed",
  "eventId": "evt-12345678",
  "timestamp": "2025-01-28T10:17:30Z",
  "data": {
    "taskId": "task-12345678",
    "findingId": "arn:aws:securityhub:...",
    "status": "success",
    "details": {
      "findingTitle": "S3 bucket has public read access",
      "severity": "HIGH",
      "remediationSummary": "Block Public Access enabled",
      "duration": "1m 30s"
    }
  },
  "metadata": {
    "awsAccountId": "123456789012",
    "region": "us-east-1",
    "source": "SHARA"
  }
}
```

---

## 6. 错误码参考

| 错误码 | HTTP 状态 | 说明 |
|--------|-----------|------|
| INVALID_PARAMETER | 400 | 请求参数无效 |
| MISSING_PARAMETER | 400 | 缺少必需参数 |
| INVALID_TOKEN | 401 | Token 无效或过期 |
| UNAUTHORIZED | 403 | 无权访问 |
| TASK_NOT_FOUND | 404 | 任务不存在 |
| FINDING_NOT_FOUND | 404 | Finding 不存在 |
| ALREADY_PROCESSED | 409 | 任务已处理 |
| TASK_IN_PROGRESS | 409 | 任务正在进行中 |
| RATE_LIMIT_EXCEEDED | 429 | 请求频率超限 |
| INTERNAL_ERROR | 500 | 内部错误 |
| AGENT_ERROR | 500 | Agent 执行错误 |
| SERVICE_UNAVAILABLE | 503 | 服务不可用 |

---

## 7. 速率限制

| API 类型 | 限制 | 窗口 |
|----------|------|------|
| 审批回调 | 100 requests | 1 minute |
| 管理 API | 1000 requests | 1 minute |
| 统计 API | 60 requests | 1 minute |

---

## 8. 文档版本

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| 1.0 | 2025-01-28 | - | 初始版本 |
