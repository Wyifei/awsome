# Security Hub Auto-Remediation Agent 架构设计文档

## 1. 架构概述

### 1.1 设计原则

| 原则 | 说明 |
|------|------|
| **事件驱动** | 基于 EventBridge 的异步事件处理架构 |
| **松耦合** | 各组件通过消息/事件通信，独立部署和扩展 |
| **最小权限** | 每个组件仅拥有必要的 IAM 权限 |
| **可观测性** | 全链路日志、指标、追踪 |
| **故障隔离** | 单个 Finding 处理失败不影响其他任务 |

### 1.2 高层架构图

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│                                   AWS Cloud                                         │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                          Security Services Layer                             │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │   │
│  │  │  Config  │ │GuardDuty │ │Inspector │ │  Macie   │ │IAM Anlzr │          │   │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘          │   │
│  │       └────────────┴────────────┼────────────┴────────────┘                │   │
│  │                                 ▼                                           │   │
│  │                    ┌────────────────────────┐                               │   │
│  │                    │    Security Hub        │                               │   │
│  │                    │  (Finding Aggregator)  │                               │   │
│  │                    └───────────┬────────────┘                               │   │
│  └────────────────────────────────┼────────────────────────────────────────────┘   │
│                                   │                                                 │
│  ┌────────────────────────────────┼────────────────────────────────────────────┐   │
│  │                     Event Processing Layer                                   │   │
│  │                                ▼                                             │   │
│  │           ┌────────────────────────────────────┐                            │   │
│  │           │         Amazon EventBridge         │                            │   │
│  │           │  Rule: severity IN [HIGH,CRITICAL] │                            │   │
│  │           └─────────────────┬──────────────────┘                            │   │
│  │                             │                                                │   │
│  │                             ▼                                                │   │
│  │           ┌────────────────────────────────────┐                            │   │
│  │           │      Lambda: Event Processor       │                            │   │
│  │           │  - Validate & Enrich Finding       │                            │   │
│  │           │  - Deduplicate                     │                            │   │
│  │           │  - Invoke Agent                    │                            │   │
│  │           └─────────────────┬──────────────────┘                            │   │
│  └─────────────────────────────┼───────────────────────────────────────────────┘   │
│                                │                                                    │
│  ┌─────────────────────────────┼───────────────────────────────────────────────┐   │
│  │                    Agent Layer (AgentCore + Strands) - 两阶段架构            │   │
│  │                             ▼                                                │   │
│  │  ┌──────────────────────────────────────────────────────────────────────┐   │   │
│  │  │  Phase 1 (审批前)          │    Phase 2 (审批后)                      │   │   │
│  │  │  ┌─────────────────┐       │    ┌─────────────────┐ ┌──────────────┐ │   │   │
│  │  │  │  Analyzer Agent │       │    │ Remediator Agent│ │Validator     │ │   │   │
│  │  │  │  - ASR 匹配     │       │    │ - 生成代码      │ │Agent         │ │   │   │
│  │  │  │  - Memory 搜索  │       │    │ - 执行修复      │ │- 验证修复    │ │   │   │
│  │  │  │  - 风险评估     │       │    │ - 保存回滚      │ │- 更新Finding │ │   │   │
│  │  │  │  - 生成描述     │       │    │                 │ │- 保存到LTM   │ │   │   │
│  │  │  └────────┬────────┘       │    └────────┬────────┘ └──────┬───────┘ │   │   │
│  │  │           │                │             └─────────────────┘         │   │   │
│  │  │           ▼                │                      ▼                  │   │   │
│  │  │     审批邮件(描述only)     │                 执行结果                │   │   │
│  │  └────────────────────────────┴─────────────────────────────────────────┘   │   │
│  │                               │                                              │   │
│  │  ┌────────────────────────────┴─────────────────────────────────────────┐   │   │
│  │  │                        Shared Services                                │   │   │
│  │  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────┐  │   │   │
│  │  │  │ Tool Registry│ │AgentCore     │ │ State Store  │ │ LLM Client  │  │   │   │
│  │  │  │  (AWS APIs)  │ │Memory(STM+LTM)│ │ (DynamoDB)   │ │ (Bedrock)   │  │   │   │
│  │  │  └──────────────┘ └──────────────┘ └──────────────┘ └─────────────┘  │   │   │
│  │  └──────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         Approval & Feedback Layer                            │   │
│  │                                                                               │   │
│  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │   │
│  │  │  Amazon SES  │───▶│ Admin Email  │───▶│ API Gateway  │                   │   │
│  │  │  (Notify)    │    │ (Review)     │    │ (Callback)   │                   │   │
│  │  └──────────────┘    └──────────────┘    └───────┬──────┘                   │   │
│  │                                                   │                          │   │
│  │                                    ┌──────────────┼──────────────┐          │   │
│  │                                    ▼              ▼              ▼          │   │
│  │                             ┌────────────┐ ┌────────────┐ ┌────────────┐   │   │
│  │                             │  Lambda:   │ │  Lambda:   │ │  Lambda:   │   │   │
│  │                             │  Event     │ │  Approval  │ │  Feedback  │   │   │
│  │                             │  Handler   │ │  Handler   │ │  Handler   │   │   │
│  │                             └────────────┘ └────────────┘ └────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                           Data & Storage Layer                               │   │
│  │                                                                               │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │   │
│  │  │  DynamoDB    │  │     S3       │  │  Secrets     │  │  Parameter   │     │   │
│  │  │ - Tasks      │  │ - Playbooks  │  │  Manager     │  │   Store      │     │   │
│  │  │ - Approvals  │  │ - Templates  │  │ - API Keys   │  │ - Configs    │     │   │
│  │  │ - Audit Log  │  │ - Reports    │  └──────────────┘  └──────────────┘     │   │
│  │  └──────────────┘  └──────────────┘                                          │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                         Observability Layer                                  │   │
│  │                                                                               │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │   │
│  │  │  CloudWatch  │  │  CloudWatch  │  │   X-Ray      │  │  CloudTrail  │     │   │
│  │  │    Logs      │  │   Metrics    │  │   Tracing    │  │    Audit     │     │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘     │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 组件详细设计

### 2.1 Event Processing Layer

#### 2.1.1 EventBridge Rule

```json
{
  "source": ["aws.securityhub"],
  "detail-type": ["Security Hub Findings - Imported"],
  "detail": {
    "findings": {
      "Severity": {
        "Label": ["HIGH", "CRITICAL"]
      },
      "Workflow": {
        "Status": ["NEW"]
      },
      "RecordState": ["ACTIVE"]
    }
  }
}
```

#### 2.1.2 Event Processor Lambda

**职责：**
- 验证 Finding 格式
- 去重处理（检查是否已处理）
- 丰富 Finding 上下文
- 调用 Agent 系统

**伪代码：**
```python
def handler(event, context):
    findings = event['detail']['findings']

    for finding in findings:
        # 1. 去重检查
        if is_duplicate(finding['Id']):
            continue

        # 2. 丰富上下文
        enriched = enrich_finding(finding)

        # 3. 创建任务记录
        task_id = create_task(enriched)

        # 4. 异步调用 Agent
        invoke_agent_async(task_id, enriched)

    return {'statusCode': 200}
```

### 2.2 Agent Layer

SHARA 采用 **Lambda 调度 + Agent 执行** 的两阶段混合架构：
- **Phase 1 (审批前)**: Lambda → Analyzer Agent，生成分析和修复描述
- **Phase 2 (审批后)**: Lambda → Remediator Agent → Validator Agent，代码生成和执行

#### 2.2.1 两阶段架构概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Lambda + Agent 两阶段混合架构                            │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                     PHASE 1: 审批前 (分析阶段)                           │ │
│  │                                                                         │ │
│  │   EventBridge ──▶ Lambda (Event Handler) ──▶ Analyzer Agent            │ │
│  │                          │                        │                     │ │
│  │                          │                        ├─ ASR Playbook 匹配  │ │
│  │                          │                        ├─ Memory LTM 搜索    │ │
│  │                          │                        ├─ 风险评估           │ │
│  │                          │                        └─ 生成修复描述       │ │
│  │                          │                                              │ │
│  │                          ▼                                              │ │
│  │                   发送审批邮件 (只包含描述，无代码)                       │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                    │                                         │
│                                    ▼ 管理员审批                              │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                     PHASE 2: 审批后 (执行阶段)                           │ │
│  │                                                                         │ │
│  │   API Gateway ──▶ Lambda (Approval Handler) ──▶ Remediator Agent       │ │
│  │                                                      │                  │ │
│  │                                                      ├─ 从 Memory 获取  │ │
│  │                                                      │   Phase 1 上下文 │ │
│  │                                                      ├─ 生成修复代码    │ │
│  │                                                      └─ 执行修复        │ │
│  │                                                            │            │ │
│  │                                                      (A2A Protocol)     │ │
│  │                                                            │            │ │
│  │                                                            ▼            │ │
│  │                                                    Validator Agent      │ │
│  │                                                      │                  │ │
│  │                                                      ├─ 审查修复代码    │ │
│  │                                                      ├─ 验证执行结果    │ │
│  │                                                      ├─ 更新 Finding    │ │
│  │                                                      ├─ 保存经验到 LTM  │ │
│  │                                                      └─ 触发结果邮件    │ │
│  │                                                            │            │ │
│  │                                                            ▼            │ │
│  │                                                 Lambda (Result Email)   │ │
│  │                                                 (含 Rollback 链接)      │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│   Context Sharing: AgentCore Memory (Session for STM, LTM for experiences)  │
│   State Persistence: DynamoDB (task metadata)                               │
│   Agent Communication: A2A Protocol (Remediator → Validator)                │
│   Lambda Invocation: AgentCore Runtime API                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 2.2.2 Lambda 函数详细设计

##### Event Handler Lambda (Phase 1 入口)

**职责：**
- 接收 Security Hub Finding
- 提取 Control ID
- 创建 Memory Session
- 调用 Analyzer Agent 进行分析和 ASR 匹配
- 发送审批邮件（只包含描述，无代码）

**伪代码：**
```python
def handler(event, context):
    finding = event['detail']['findings'][0]

    # 1. 提取 Control ID
    control_id = extract_control_id(finding)

    # 2. 创建任务和 Memory Session
    task_id = create_task(finding)
    memory_session_id = create_memory_session(task_id)

    # 3. 调用 Analyzer Agent (Phase 1)
    result = invoke_analyzer_agent(
        task_id=task_id,
        memory_session_id=memory_session_id,
        finding=finding,
        control_id=control_id
    )
    # Analyzer 会：
    # - 匹配 ASR Playbook
    # - 搜索 Memory LTM 相似经验
    # - 评估风险
    # - 生成修复描述（不生成代码）

    # 4. 保存分析结果（描述）到 DynamoDB
    save_analysis_result(task_id, result)
    update_task_status(task_id, 'waiting_approval', phase='pre_approval')

    # 5. 发送审批邮件（只包含描述）
    send_approval_email(task_id, result['remediation']['description'])

    return {'statusCode': 200}
```

##### Approval Handler Lambda (Phase 2 入口)

**职责：**
- 处理审批回调
- 审批通过后调用 Remediator Agent（生成代码并执行）
- Remediator 通过 A2A 协议自动调用 Validator Agent

**伪代码：**
```python
def handler(event, context):
    action = event['queryStringParameters']['action']
    task_id = event['queryStringParameters']['task_id']
    token = event['queryStringParameters']['token']

    # 验证 Token
    if not validate_token(token, task_id):
        return {'statusCode': 401, 'body': 'Invalid token'}

    if action == 'approve':
        # 获取 Memory Session ID
        task = get_task(task_id)
        memory_session_id = task['memorySessionId']

        # 更新状态为 Phase 2
        update_task_status(task_id, 'generating_code', phase='post_approval')

        # 调用 Remediator Agent (Phase 2)
        # Remediator 会：
        # - 从 Memory 获取 Phase 1 分析结果
        # - 生成修复代码
        # - 执行修复
        # - 保存回滚数据
        # - 通过 A2A 协议调用 Validator Agent
        #   - Validator 审查代码安全性
        #   - Validator 验证执行结果
        #   - Validator 更新 Security Hub Finding
        #   - Validator 保存经验到 Memory LTM
        #   - Validator 触发 Lambda 发送结果邮件
        execution_result = invoke_remediator_agent(
            task_id=task_id,
            memory_session_id=memory_session_id
        )

        # 注：结果邮件由 Validator Agent 触发 Lambda 发送，不在此处理

    elif action == 'reject':
        update_task_status(task_id, 'rejected')
        send_rejection_email(task_id)

    return redirect_to_result_page()
```

##### Feedback Handler Lambda

**职责：**
- 处理用户反馈回调（Rollback 链接点击）
- 触发回滚操作（如用户不认可修复结果）
- 回滚后由 Validator 验证并发送结果邮件（不含 Rollback 链接）

**伪代码：**
```python
def handler(event, context):
    action = event['queryStringParameters']['action']
    task_id = event['queryStringParameters']['task_id']

    task = get_task(task_id)
    memory_session_id = task['memorySessionId']

    if action == 'confirm':
        # 用户确认修复有效
        # Validator 在 Phase 2 已保存经验到 Memory LTM
        update_task_status(task_id, 'completed')

    elif action == 'rollback':
        # 1. 调用 Remediator Agent 执行回滚
        # Remediator 会：
        # - 获取保存的回滚数据
        # - 执行回滚代码
        # - 通过 A2A 调用 Validator 验证回滚结果
        #   - Validator 验证资源状态已恢复
        #   - Validator 触发 Lambda 发送回滚结果邮件（无 Rollback 链接）
        rollback_result = invoke_remediator_rollback(
            task_id=task_id,
            memory_session_id=memory_session_id,
            is_rollback=True  # 标记为回滚操作
        )

        # 2. 更新任务状态
        update_task_status(task_id, 'rolled_back')

        # 注：回滚结果邮件由 Validator 触发 Lambda 发送，邮件不含 Rollback 链接

    return redirect_to_result_page()
```

**回滚流程详细说明：**
1. 用户点击结果邮件中的 Rollback 链接
2. Feedback Handler Lambda 调用 Remediator Agent（回滚模式）
3. Remediator Agent 执行回滚代码
4. Remediator 通过 A2A 调用 Validator Agent 验证回滚结果
5. Validator Agent 触发 Lambda 发送回滚结果邮件
6. 回滚结果邮件**不包含** Rollback 链接（防止循环回滚）
7. 如果回滚失败，邮件中提醒用户手动处理

#### 2.2.3 Analyzer Agent (Phase 1)

**触发时机：** Finding 进入系统后，由 Event Handler Lambda 调用

**核心职责：**
- 解析 Finding 结构，提取 Control ID
- 匹配 ASR Playbook（从 S3 获取预置修复方案）
- 搜索 Memory LTM 获取相似修复经验
- 收集相关资源上下文
- 评估安全风险
- **生成修复描述**（不生成代码，代码在 Phase 2 生成）
- 保存分析结果到 Memory Session

**输出内容（用于审批邮件）：**
- 风险评估结果
- 修复方案描述（文字说明）
- 预估影响
- 是否有 ASR Playbook 匹配
- 是否为破坏性操作

**工具集：**
```python
ANALYZER_TOOLS = [
    # ASR Playbook 匹配
    "fetch_asr_playbook",        # 从 S3 获取 ASR Playbook
    "get_asr_index",             # 获取 ASR 索引文件

    # Memory 操作
    "search_similar_findings",   # 从 Memory LTM 搜索相似修复经验
    "save_analysis_result",      # 保存分析结果到 Memory Session

    # MCP 文档查询
    "search_aws_documentation",  # 搜索 AWS 文档
    "read_aws_documentation",    # 读取 AWS 文档

    # 资源信息获取
    "ec2:DescribeInstances",
    "ec2:DescribeSecurityGroups",
    "s3:GetBucketPolicy",
    "s3:GetBucketAcl",
    "s3:GetPublicAccessBlock",
    "iam:GetRole",
    "iam:GetPolicy",
    "rds:DescribeDBInstances",

    # Security Hub 操作
    "securityhub:GetFindings",
    "securityhub:BatchGetSecurityControls",

    # 配置检查
    "config:GetResourceConfigHistory",
    "config:GetComplianceDetailsByResource",
]
```

#### 2.2.4 Remediator Agent (Phase 2)

**触发时机：** 管理员审批通过后，由 Approval Handler Lambda 调用

**核心职责：**
- 从 Memory Session 获取 Phase 1 分析结果
- **生成修复代码**（基于分析结果和 ASR Playbook）
- 保存当前资源状态（用于回滚）
- 通过 Code Interpreter 执行修复代码
- **通过 A2A 协议调用 Validator Agent** 进行代码审查和结果验证
- 执行回滚操作（当用户不认可修复结果时）

**输入：**
- Memory Session ID（获取 Phase 1 上下文）
- 审批信息

**输出：**
- 生成的修复代码
- 执行结果
- 回滚数据
- Validator 验证结果

**A2A 通信：**
Remediator 执行完毕后，通过 A2A 协议调用 Validator Agent：
- 发送：生成的代码、执行结果、资源状态
- 接收：代码审查结果、验证结果、邮件发送状态

**工具集：**
```python
REMEDIATOR_TOOLS = [
    # Memory 操作
    "get_analysis_context",      # 从 Memory Session 获取 Phase 1 分析结果

    # 代码执行
    "execute_code",              # 通过 Code Interpreter 执行代码

    # 状态管理
    "save_rollback_data",        # 保存资源状态到 DynamoDB (用于回滚)
    "get_rollback_data",         # 获取保存的回滚数据

    # A2A 通信
    "invoke_validator_agent",    # 通过 A2A 协议调用 Validator Agent

    # S3 修复
    "s3:PutBucketPolicy",
    "s3:DeleteBucketPolicy",
    "s3:PutPublicAccessBlock",
    "s3:PutBucketEncryption",

    # EC2/网络修复
    "ec2:AuthorizeSecurityGroupIngress",
    "ec2:RevokeSecurityGroupIngress",
    "ec2:ModifyInstanceAttribute",

    # IAM 修复
    "iam:UpdateAssumeRolePolicy",
    "iam:PutRolePolicy",
    "iam:DeleteRolePolicy",
]
```

#### 2.2.5 Validator Agent (Phase 2)

**触发时机：** Remediator Agent 执行完成后，通过 A2A 协议调用

**核心职责：**
1. **代码安全审查**：检查 Remediator 生成的代码是否存在安全风险
   - 危险代码检测（如删除操作、权限提升）
   - 环境破坏风险评估
   - 敏感信息泄露检查
2. **执行结果验证**：检查资源状态是否符合预期
   - 验证修复效果
   - 运行合规检查
3. **更新 Security Hub Finding 状态**
4. **保存修复经验到 Memory LTM**（供未来相似 Finding 参考）
5. **触发结果邮件发送**：调用 Lambda 发送结果邮件（含 Rollback 链接）

**A2A 通信：**
- 被 Remediator Agent 通过 A2A 协议调用
- 接收：生成的代码、执行结果、资源 ARN、任务 ID
- 返回：代码审查结果、验证结果、邮件发送状态

**输入（通过 A2A）：**
- Task ID
- Memory Session ID
- 生成的修复代码
- 代码执行结果
- 资源 ARN 和类型

**输出：**
- 代码审查结果（通过/风险警告/拒绝）
- 验证结果（通过/失败）
- Security Hub Finding 更新状态
- 经验保存结果
- 邮件发送状态

**工具集：**
```python
VALIDATOR_TOOLS = [
    # 代码安全审查
    "review_code_security",      # 审查代码安全性

    # 状态验证
    "verify_resource_state",     # 验证资源配置状态
    "verify_s3_configuration",
    "verify_security_group",
    "verify_iam_policy",

    # Security Hub 更新
    "securityhub:BatchUpdateFindings",

    # 安全扫描
    "config:StartConfigRulesEvaluation",

    # Memory 操作
    "save_experience",           # 保存修复经验到 Memory LTM

    # 邮件触发
    "trigger_result_email",      # 调用 Lambda 发送结果邮件（含 Rollback 链接）
]
```

#### 2.2.6 任务状态机（两阶段）

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  PHASE 1: 审批前                                                                 │
│                                                                                  │
│  PENDING ──▶ ANALYZING ──▶ WAITING_APPROVAL                                     │
│                  │              │                                                │
│                  ▼              ▼                                                │
│           ANALYSIS_FAILED   REJECTED / APPROVAL_EXPIRED                         │
│                                                                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│  PHASE 2: 审批后                                                                 │
│                                                                                  │
│  APPROVED ──▶ GENERATING_CODE ──▶ EXECUTING ──▶ VALIDATING ──▶ WAITING_FEEDBACK │
│                     │                 │              │               │          │
│                     ▼                 ▼              ▼               │          │
│              CODE_GEN_FAILED   EXECUTION_FAILED  VALIDATION_FAILED   │          │
│                                                                      │          │
│                                            ┌─────────────────────────┘          │
│                                            │                                     │
│                                            ▼                                     │
│                                  ┌─────────────────────┐                        │
│                                  │                     │                        │
│                                  ▼                     ▼                        │
│                             COMPLETED             ROLLED_BACK                   │
│                        (经验已保存到 Memory LTM)    (已回滚)                     │
└─────────────────────────────────────────────────────────────────────────────────┘
```

**状态说明：**

| 阶段 | 状态 | 说明 |
|------|------|------|
| Phase 1 | `pending` | 初始状态 |
| Phase 1 | `analyzing` | Analyzer Agent 分析中 |
| Phase 1 | `waiting_approval` | 等待审批（邮件已发送） |
| Phase 2 | `approved` | 已审批，准备生成代码 |
| Phase 2 | `generating_code` | Remediator Agent 生成代码中 |
| Phase 2 | `executing` | 执行修复中 |
| Phase 2 | `validating` | Validator Agent 验证中 |
| Phase 2 | `waiting_feedback` | 等待用户确认 |
| 终态 | `completed` | 修复完成 |
| 终态 | `rolled_back` | 已回滚 |
| 终态 | `rejected` | 审批被拒绝 |

---

## 3. 数据流详细设计

### 3.1 Phase 1: Finding 分析流程（审批前）

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                         Phase 1: Finding Analysis Flow                                     │
│                                                                                            │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐     │
│  │Security │ │Event    │ │Lambda   │ │DynamoDB │ │Analyzer │ │S3 (ASR) │ │Memory   │     │
│  │Hub      │ │Bridge   │ │Handler  │ │         │ │Agent    │ │Playbooks│ │(STM+LTM)│     │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘     │
│       │           │           │           │           │           │           │           │
│       │ 1.Finding │           │           │           │           │           │           │
│       │──────────▶│           │           │           │           │           │           │
│       │           │ 2.Trigger │           │           │           │           │           │
│       │           │──────────▶│           │           │           │           │           │
│       │           │           │           │           │           │           │           │
│       │           │           │ 3.Create  │           │           │           │           │
│       │           │           │   Task    │           │           │           │           │
│       │           │           │──────────▶│           │           │           │           │
│       │           │           │           │           │           │           │           │
│       │           │           │ 4.Create Memory Session           │           │           │
│       │           │           │──────────────────────────────────────────────▶│           │
│       │           │           │           │           │           │           │           │
│       │           │           │ 5.Invoke Analyzer     │           │           │           │
│       │           │           │──────────────────────▶│           │           │           │
│       │           │           │           │           │           │           │           │
│       │           │           │           │           │ 6.Fetch   │           │           │
│       │           │           │           │           │   ASR     │           │           │
│       │           │           │           │           │──────────▶│           │           │
│       │           │           │           │           │◀──────────│           │           │
│       │           │           │           │           │           │           │           │
│       │           │           │           │           │ 7.Search  │           │           │
│       │           │           │           │           │   LTM     │           │           │
│       │           │           │           │           │──────────────────────▶│           │
│       │           │           │           │           │◀──────────────────────│           │
│       │           │           │           │           │           │           │           │
│       │           │           │           │           │ 8.Save    │           │           │
│       │           │           │           │           │  Analysis │           │           │
│       │           │           │           │           │──────────────────────▶│           │
│       │           │           │           │           │           │           │           │
│       │           │           │ 9.Return Analysis (Description only)          │           │
│       │           │           │◀─────────────────────│           │           │           │
│       │           │           │           │           │           │           │           │
│       │           │           │ 10.Update Task Status │           │           │           │
│       │           │           │──────────▶│           │           │           │           │
│       │           │           │           │           │           │           │           │
│       │           │           │ 11.Send Approval Email (Description)          │           │
│       │           │           │─────────────▶ SES     │           │           │           │
│       │           │           │           │           │           │           │           │
│  └────┴────┘ └────┴────┘ └────┴────┘ └────┴────┘ └────┴────┘ └────┴────┘ └────┴────┘     │
└───────────────────────────────────────────────────────────────────────────────────────────┘

Analyzer Agent 内部流程:
┌─────────────────────────────────────────────────────────────────┐
│  1. 提取 Control ID (如 S3.1)                                    │
│                    │                                             │
│                    ▼                                             │
│  2. 从 S3 精确匹配 ASR Playbook ─────────────────────────────┐  │
│     - 读取 index.json                                        │  │
│     - 根据 Control ID 查找对应 Playbook                      │  │
│     - 获取 ASR_S3_1.json + ASR_S3_1_code.py                  │  │
│                    │                                          │  │
│                    ▼                                          │  │
│  3. 从 Memory LTM 语义搜索相似经验 ◀─────────────────────────┘  │
│     - 搜索类似 Finding 的历史修复经验                           │
│     - 作为 ASR 的补充参考                                       │
│                    │                                             │
│                    ▼                                             │
│  4. 综合分析生成修复描述                                         │
│     - 风险评估                                                   │
│     - 修复方案描述（文字）                                       │
│     - 标记是否匹配到 ASR                                         │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Phase 2: 修复执行流程（审批后）

```
┌───────────────────────────────────────────────────────────────────────────────────────────┐
│                          Phase 2: Remediation Execution Flow                               │
│                                                                                            │
│  ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────┐  │
│  │API      │  │Lambda   │  │Remediator│  │Validator│  │Memory   │  │Security │  │Lambda│  │
│  │Gateway  │  │Approval │  │Agent     │  │Agent    │  │(STM+LTM)│  │Hub      │  │Email │  │
│  └────┬────┘  └────┬────┘  └────┬─────┘  └────┬────┘  └────┬────┘  └────┬────┘  └──┬──┘  │
│       │            │            │             │            │            │           │      │
│       │ 1.Approve  │            │             │            │            │           │      │
│       │───────────▶│            │             │            │            │           │      │
│       │            │            │             │            │            │           │      │
│       │            │ 2.Invoke   │             │            │            │           │      │
│       │            │  Remediator│             │            │            │           │      │
│       │            │───────────▶│             │            │            │           │      │
│       │            │            │             │            │            │           │      │
│       │            │            │ 3.Get       │            │            │           │      │
│       │            │            │   Analysis  │            │            │           │      │
│       │            │            │   Context   │            │            │           │      │
│       │            │            │────────────────────────▶│            │           │      │
│       │            │            │◀────────────────────────│            │           │      │
│       │            │            │             │            │            │           │      │
│       │            │            │ 4.Generate  │            │            │           │      │
│       │            │            │   Code &    │            │            │           │      │
│       │            │            │   Execute   │            │            │           │      │
│       │            │            │             │            │            │           │      │
│       │            │            │ 5.A2A Call  │            │            │           │      │
│       │            │            │   Validator │            │            │           │      │
│       │            │            │ (code+result)            │            │           │      │
│       │            │            │────────────▶│            │            │           │      │
│       │            │            │             │            │            │           │      │
│       │            │            │             │ 6.Review   │            │           │      │
│       │            │            │             │   Code     │            │           │      │
│       │            │            │             │  Security  │            │           │      │
│       │            │            │             │            │            │           │      │
│       │            │            │             │ 7.Verify   │            │           │      │
│       │            │            │             │   Result   │            │           │      │
│       │            │            │             │            │            │           │      │
│       │            │            │             │ 8.Update   │            │           │      │
│       │            │            │             │   Finding  │            │           │      │
│       │            │            │             │───────────────────────▶│           │      │
│       │            │            │             │            │            │           │      │
│       │            │            │             │ 9.Save Experience to LTM            │      │
│       │            │            │             │───────────▶│            │           │      │
│       │            │            │             │            │            │           │      │
│       │            │            │             │ 10.Trigger │            │           │      │
│       │            │            │             │   Result   │            │           │      │
│       │            │            │             │   Email    │            │           │      │
│       │            │            │             │──────────────────────────────────▶│      │
│       │            │            │             │            │            │           │      │
│       │            │            │             │            │            │    (SES)  │      │
│       │            │            │             │            │            │ 11.Send   │      │
│       │            │            │             │            │            │  Email    │      │
│       │            │            │             │            │            │ (含Rollback│      │
│       │            │            │             │            │            │  链接)    │      │
│       │            │            │             │            │            │           │      │
│       │            │            │◀───────────│            │            │           │      │
│       │            │            │ 12.Return  │            │            │           │      │
│       │            │            │    Result  │            │            │           │      │
│       │            │            │             │            │            │           │      │
│  └────┴────┘  └────┴────┘  └────┴─────┘  └────┴────┘  └────┴────┘  └────┴────┘  └──┴──┘  │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

### 3.3 审批流程

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           Approval Flow                                       │
│                                                                               │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    │
│  │Lambda   │    │SES      │    │Admin    │    │API GW   │    │Lambda   │    │
│  │Event    │    │         │    │         │    │         │    │Approval │    │
│  │Handler  │    │         │    │         │    │         │    │Handler  │    │
│  └────┬────┘    └────┬────┘    └────┬────┘    └────┬────┘    └────┬────┘    │
│       │              │              │              │              │          │
│       │ 1.Send Email │              │              │              │          │
│       │  (描述 only) │              │              │              │          │
│       │─────────────▶│              │              │              │          │
│       │              │              │              │              │          │
│       │              │ 2.Deliver    │              │              │          │
│       │              │─────────────▶│              │              │          │
│       │              │              │              │              │          │
│       │              │              │ 3.Review     │              │          │
│       │              │              │  修复描述    │              │          │
│       │              │              │  (无代码)    │              │          │
│       │              │              │              │              │          │
│       │              │              │ 4.Click      │              │          │
│       │              │              │  Approve     │              │          │
│       │              │              │─────────────▶│              │          │
│       │              │              │              │              │          │
│       │              │              │              │ 5.Callback   │          │
│       │              │              │              │─────────────▶│          │
│       │              │              │              │              │          │
│       │              │              │              │ 6.Validate   │          │
│       │              │              │              │   Token      │          │
│       │              │              │              │              │          │
│       │              │              │              │ 7.Trigger    │          │
│       │              │              │              │   Phase 2    │          │
│       │              │              │              │   (代码生成  │          │
│       │              │              │              │    +执行)    │          │
│       │              │              │              │              │          │
│  └────┴────┘    └────┴────┘    └────┴────┘    └────┴────┘    └────┴────┘    │
└──────────────────────────────────────────────────────────────────────────────┘

审批邮件内容：
┌────────────────────────────────────────────────────────────────┐
│ Subject: [SHARA] 安全修复审批请求 - S3 公开访问                  │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Finding: S3 bucket has public read access                       │
│ 资源: arn:aws:s3:::my-bucket                                    │
│ 严重级别: HIGH                                                  │
│                                                                 │
│ ─────────────────────────────────────────────────────────────── │
│                                                                 │
│ 修复方案描述:                                                    │
│ 通过启用 S3 Block Public Access 来阻止所有公共访问。            │
│ 此操作将配置存储桶级别的访问阻止设置，防止任何公共访问策略生效。│
│                                                                 │
│ 预估影响: LOW                                                   │
│ 可回滚: 是                                                      │
│ ASR Playbook: ASR_S3_1 (已匹配)                                │
│                                                                 │
│ ─────────────────────────────────────────────────────────────── │
│                                                                 │
│ [同意修复]  [拒绝修复]                                          │
│                                                                 │
│ 注：同意后系统将自动生成修复代码并执行                           │
└────────────────────────────────────────────────────────────────┘
```

### 3.4 结果邮件与回滚流程

#### 3.4.1 结果邮件流程

Validator Agent 完成验证后，触发 Lambda 发送结果邮件：

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                         Result Email Flow                                      │
│                                                                                │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐             │
│  │Validator│  │Lambda   │  │DynamoDB │  │SES      │  │User     │             │
│  │Agent    │  │Email    │  │         │  │         │  │         │             │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘             │
│       │            │            │            │            │                   │
│       │ 1.Trigger  │            │            │            │                   │
│       │   Email    │            │            │            │                   │
│       │   Lambda   │            │            │            │                   │
│       │───────────▶│            │            │            │                   │
│       │   (task_id,│            │            │            │                   │
│       │    result, │            │            │            │                   │
│       │    is_rollback=false)   │            │            │                   │
│       │            │            │            │            │                   │
│       │            │ 2.Get Task │            │            │                   │
│       │            │   Details  │            │            │                   │
│       │            │───────────▶│            │            │                   │
│       │            │◀───────────│            │            │                   │
│       │            │            │            │            │                   │
│       │            │ 3.Generate │            │            │                   │
│       │            │   Rollback │            │            │                   │
│       │            │   Token    │            │            │                   │
│       │            │            │            │            │                   │
│       │            │ 4.Send     │            │            │                   │
│       │            │   Email    │            │            │                   │
│       │            │   (含      │            │            │                   │
│       │            │   Rollback │            │            │                   │
│       │            │   链接)    │            │            │                   │
│       │            │───────────────────────▶│            │                   │
│       │            │            │            │            │                   │
│       │            │            │            │ 5.Deliver  │                   │
│       │            │            │            │───────────▶│                   │
│       │            │            │            │            │                   │
│  └────┴────┘  └────┴────┘  └────┴────┘  └────┴────┘  └────┴────┘             │
└───────────────────────────────────────────────────────────────────────────────┘

结果邮件内容：
┌────────────────────────────────────────────────────────────────┐
│ Subject: [SHARA] 修复完成 - S3.8 Block Public Access           │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Finding: S3 bucket should have public access blocked            │
│ 资源: arn:aws:s3:::my-bucket                                    │
│ 状态: ✅ 修复成功                                               │
│                                                                 │
│ ─────────────────────────────────────────────────────────────── │
│                                                                 │
│ 代码审查结果: ✅ 通过                                           │
│ - 无危险操作                                                    │
│ - 无敏感信息泄露风险                                            │
│                                                                 │
│ 执行结果验证: ✅ 通过                                           │
│ - Block Public Access 已启用                                    │
│ - 配置符合预期                                                  │
│                                                                 │
│ Security Hub Finding: 已更新为 RESOLVED                         │
│                                                                 │
│ ─────────────────────────────────────────────────────────────── │
│                                                                 │
│ 如果此修复导致问题，您可以回滚：                                │
│                                                                 │
│ [回滚修复]                                                      │
│                                                                 │
│ 回滚链接有效期：24小时                                          │
└────────────────────────────────────────────────────────────────┘
```

#### 3.4.2 回滚流程

用户点击回滚链接后触发回滚：

```
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                              Rollback Flow                                             │
│                                                                                        │
│  ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐       │
│  │User     │  │API      │  │Lambda    │  │Remediator│  │Validator│  │Lambda   │       │
│  │         │  │Gateway  │  │Feedback  │  │Agent     │  │Agent    │  │Email    │       │
│  └────┬────┘  └────┬────┘  └────┬─────┘  └────┬─────┘  └────┬────┘  └────┬────┘       │
│       │            │            │             │             │            │             │
│       │ 1.Click    │            │             │             │            │             │
│       │  Rollback  │            │             │             │            │             │
│       │───────────▶│            │             │             │            │             │
│       │            │            │             │             │            │             │
│       │            │ 2.Callback │             │             │            │             │
│       │            │───────────▶│             │             │            │             │
│       │            │            │             │             │            │             │
│       │            │            │ 3.Validate  │             │            │             │
│       │            │            │   Token     │             │            │             │
│       │            │            │             │             │            │             │
│       │            │            │ 4.Invoke    │             │            │             │
│       │            │            │  Remediator │             │            │             │
│       │            │            │ (rollback   │             │            │             │
│       │            │            │  mode)      │             │            │             │
│       │            │            │────────────▶│             │            │             │
│       │            │            │             │             │            │             │
│       │            │            │             │ 5.Get       │            │             │
│       │            │            │             │   Rollback  │            │             │
│       │            │            │             │   Data      │            │             │
│       │            │            │             │             │            │             │
│       │            │            │             │ 6.Execute   │            │             │
│       │            │            │             │   Rollback  │            │             │
│       │            │            │             │   Code      │            │             │
│       │            │            │             │             │            │             │
│       │            │            │             │ 7.A2A Call  │            │             │
│       │            │            │             │  Validator  │            │             │
│       │            │            │             │ (is_rollback│            │             │
│       │            │            │             │  =true)     │            │             │
│       │            │            │             │────────────▶│            │             │
│       │            │            │             │             │            │             │
│       │            │            │             │             │ 8.Verify   │             │
│       │            │            │             │             │  Rollback  │             │
│       │            │            │             │             │  Result    │             │
│       │            │            │             │             │            │             │
│       │            │            │             │             │ 9.Trigger  │             │
│       │            │            │             │             │  Rollback  │             │
│       │            │            │             │             │  Email     │             │
│       │            │            │             │             │ (无Rollback│             │
│       │            │            │             │             │  链接)     │             │
│       │            │            │             │             │───────────▶│             │
│       │            │            │             │             │            │             │
│       │            │            │             │             │            │ 10.Send     │
│       │            │            │             │             │            │   Rollback  │
│       │            │            │             │             │            │   Result    │
│       │            │            │             │             │            │   Email     │
│       │            │            │             │             │            │  (via SES)  │
│       │            │            │             │             │            │             │
│  └────┴────┘  └────┴────┘  └────┴─────┘  └────┴─────┘  └────┴────┘  └────┴────┘       │
└───────────────────────────────────────────────────────────────────────────────────────┘

回滚结果邮件内容：
┌────────────────────────────────────────────────────────────────┐
│ Subject: [SHARA] 回滚完成 - S3.8 Block Public Access           │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Finding: S3 bucket should have public access blocked            │
│ 资源: arn:aws:s3:::my-bucket                                    │
│ 状态: ⚠️ 已回滚                                                 │
│                                                                 │
│ ─────────────────────────────────────────────────────────────── │
│                                                                 │
│ 回滚验证结果: ✅ 通过                                           │
│ - 资源配置已恢复到修复前状态                                    │
│                                                                 │
│ Security Hub Finding: 已更新为 NEW                              │
│                                                                 │
│ ─────────────────────────────────────────────────────────────── │
│                                                                 │
│ 注意: 回滚后原有安全问题可能重新出现，请评估风险。              │
│ 如需重新修复，请等待系统重新检测或手动处理。                    │
│                                                                 │
│ （此邮件不包含回滚链接）                                        │
└────────────────────────────────────────────────────────────────┘

回滚失败时的邮件：
┌────────────────────────────────────────────────────────────────┐
│ Subject: [SHARA] ⚠️ 回滚失败 - S3.8 Block Public Access        │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Finding: S3 bucket should have public access blocked            │
│ 资源: arn:aws:s3:::my-bucket                                    │
│ 状态: ❌ 回滚失败                                               │
│                                                                 │
│ ─────────────────────────────────────────────────────────────── │
│                                                                 │
│ 错误信息: AccessDenied - ...                                    │
│                                                                 │
│ ─────────────────────────────────────────────────────────────── │
│                                                                 │
│ ⚠️ 请手动处理:                                                  │
│ 1. 登录 AWS 控制台                                              │
│ 2. 检查资源状态                                                 │
│ 3. 根据需要手动恢复配置                                         │
│                                                                 │
│ （此邮件不包含回滚链接）                                        │
└────────────────────────────────────────────────────────────────┘
```

### 3.5 AgentCore Memory 集成

SHARA 使用 AgentCore Memory 实现跨阶段上下文传递和经验积累：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AgentCore Memory 架构                                 │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                     Memory Session (STM - 短期记忆)                     │  │
│  │                                                                        │  │
│  │   用途: 单个任务的上下文传递 (Phase 1 → Phase 2)                       │  │
│  │   生命周期: 任务开始 → 任务完成                                        │  │
│  │   Session ID: session-task-{taskId}                                   │  │
│  │                                                                        │  │
│  │   存储内容:                                                            │  │
│  │   ├─ Phase 1 分析结果                                                 │  │
│  │   │  ├─ Finding 解析                                                  │  │
│  │   │  ├─ ASR Playbook 匹配结果                                         │  │
│  │   │  ├─ 风险评估                                                      │  │
│  │   │  └─ 修复描述                                                      │  │
│  │   │                                                                    │  │
│  │   └─ Phase 2 执行上下文                                               │  │
│  │      ├─ 生成的代码                                                    │  │
│  │      ├─ 执行结果                                                      │  │
│  │      └─ 验证结果                                                      │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                     Memory LTM (长期记忆 - 语义搜索)                    │  │
│  │                                                                        │  │
│  │   用途: 存储和检索修复经验                                             │  │
│  │   生命周期: 永久                                                       │  │
│  │                                                                        │  │
│  │   Namespace 结构:                                                      │  │
│  │   /remediation/                                                        │  │
│  │   ├─ /remediation/{controlId}/                  # 按 Control ID 分类  │  │
│  │   │  ├─ /remediation/S3.1/user-123             # 用户验证的经验       │  │
│  │   │  ├─ /remediation/S3.1/user-456             │  │
│  │   │  └─ ...                                                            │  │
│  │   └─ /remediation/{resourceType}/               # 按资源类型分类      │  │
│  │      ├─ /remediation/AwsS3Bucket/...                                  │  │
│  │      └─ /remediation/AwsEc2SecurityGroup/...                          │  │
│  │                                                                        │  │
│  │   搜索场景:                                                            │  │
│  │   - Analyzer Agent 搜索相似 Finding 的修复经验                        │  │
│  │   - 基于 Control ID + Finding 描述进行语义搜索                        │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Memory 使用流程:**

| 阶段 | Agent | 操作 | 说明 |
|------|-------|------|------|
| Phase 1 | Analyzer | `search_long_term_memories()` | 搜索相似修复经验 |
| Phase 1 | Analyzer | `add_turns()` | 保存分析结果到 Session |
| Phase 2 | Remediator | `get_last_k_turns()` | 获取 Phase 1 分析结果 |
| Phase 2 | Remediator | `add_turns()` | 保存执行结果到 Session |
| Phase 2 | Validator | `save_experience()` | 保存验证通过的经验到 LTM |

---

## 4. 安全设计

### 4.1 IAM 权限设计

#### 4.1.1 最小权限原则

```yaml
# Event Processor Lambda Role
EventProcessorRole:
  Policies:
    - SecurityHubReadOnly
    - DynamoDBTaskTableWrite
    - LambdaInvokeAgent
    - CloudWatchLogsWrite

# Agent Execution Role
AgentExecutionRole:
  Policies:
    - BedrockInvokeModel
    - DynamoDBTaskTableReadWrite
    - S3KnowledgeBaseRead
    - SecurityServicesRead  # Config, GuardDuty, Inspector 只读

# Remediation Execution Role (需要审批后才能 assume)
RemediationRole:
  Policies:
    - SecurityRemediationActions  # 具体修复操作权限
    - SecurityHubUpdateFindings
  Conditions:
    - RequireApprovalToken
```

#### 4.1.2 权限边界

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Deny",
      "Action": [
        "iam:CreateUser",
        "iam:DeleteUser",
        "iam:CreateAccessKey",
        "organizations:*",
        "account:*"
      ],
      "Resource": "*"
    }
  ]
}
```

### 4.2 数据安全

| 数据类型 | 加密方式 | 访问控制 |
|----------|----------|----------|
| DynamoDB 数据 | AWS managed KMS | IAM + Resource Policy |
| S3 知识库 | SSE-S3 | Bucket Policy |
| 审批 Token | JWT (RS256) | 时效性验证 |
| API 调用 | TLS 1.2+ | API Gateway Auth |

### 4.3 审批 Token 设计

```python
# Token 结构
{
    "task_id": "uuid",
    "finding_id": "arn:aws:...",
    "action": "approve|reject",
    "expires_at": "ISO8601",
    "issued_at": "ISO8601",
    "issuer": "shara-agent",
    "signature": "..."
}

# Token 验证流程
1. 检查签名有效性
2. 检查是否过期
3. 检查任务状态是否为 PENDING_APPROVAL
4. 检查是否已被使用（防止重放）
```

---

## 5. 可观测性设计

### 5.1 日志设计

```json
{
  "timestamp": "2025-01-28T10:30:00Z",
  "level": "INFO",
  "service": "shara-agent",
  "component": "orchestrator",
  "trace_id": "1-abc123",
  "span_id": "def456",
  "task_id": "task-789",
  "finding_id": "arn:aws:securityhub:...",
  "action": "analyze_finding",
  "duration_ms": 1234,
  "status": "success",
  "metadata": {
    "finding_type": "Software and Configuration Checks",
    "resource_type": "AwsS3Bucket"
  }
}
```

### 5.2 指标设计

| 指标名称 | 类型 | 维度 | 说明 |
|----------|------|------|------|
| FindingsReceived | Counter | severity, source | 接收的 Finding 数量 |
| FindingsProcessed | Counter | severity, status | 处理完成的 Finding |
| ProcessingDuration | Timer | stage | 各阶段处理时长 |
| ApprovalLatency | Timer | - | 审批响应时间 |
| RemediationSuccess | Counter | finding_type | 修复成功数量 |
| RemediationFailure | Counter | finding_type, error | 修复失败数量 |
| AgentInvocations | Counter | agent_type | Agent 调用次数 |
| LLMTokenUsage | Counter | model, agent | Token 消耗 |

### 5.3 告警设计

| 告警名称 | 条件 | 严重级别 | 通知方式 |
|----------|------|----------|----------|
| HighProcessingLatency | P95 > 5min | WARNING | SNS |
| ProcessingFailureRate | > 10% in 5min | CRITICAL | SNS + PagerDuty |
| ApprovalTimeout | Pending > 24h | WARNING | SNS |
| AgentError | Any error | WARNING | SNS |
| LLMQuotaWarning | Usage > 80% | WARNING | SNS |

---

## 6. 部署架构

### 6.1 基础设施

```
┌─────────────────────────────────────────────────────────────────────┐
│                              VPC                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                      Private Subnet                            │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │  │
│  │  │   Lambda    │  │   Lambda    │  │  AgentCore  │           │  │
│  │  │  Processor  │  │  Approval   │  │   Runtime   │           │  │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘           │  │
│  │         │                │                │                   │  │
│  │         └────────────────┼────────────────┘                   │  │
│  │                          │                                     │  │
│  │                          ▼                                     │  │
│  │              ┌─────────────────────┐                          │  │
│  │              │    VPC Endpoints    │                          │  │
│  │              │  - DynamoDB         │                          │  │
│  │              │  - S3               │                          │  │
│  │              │  - Secrets Manager  │                          │  │
│  │              │  - Bedrock          │                          │  │
│  │              │  - Security Hub     │                          │  │
│  │              └─────────────────────┘                          │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                      Public Subnet                             │  │
│  │  ┌─────────────┐                                              │  │
│  │  │ NAT Gateway │ (用于 SES 发送邮件)                          │  │
│  │  └─────────────┘                                              │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 多区域部署（可选）

```
┌──────────────────┐     ┌──────────────────┐
│   us-east-1      │     │   eu-west-1      │
│  (Primary)       │     │  (Secondary)     │
│                  │     │                  │
│  ┌────────────┐  │     │  ┌────────────┐  │
│  │ Security   │  │     │  │ Security   │  │
│  │ Hub        │──┼─────┼──│ Hub        │  │
│  │ (Aggr)     │  │     │  │ (Member)   │  │
│  └────────────┘  │     │  └────────────┘  │
│                  │     │                  │
│  ┌────────────┐  │     │                  │
│  │ Agent      │  │     │                  │
│  │ System     │  │     │                  │
│  └────────────┘  │     │                  │
└──────────────────┘     └──────────────────┘
```

---

## 7. 扩展性设计

### 7.1 插件式 Finding Handler

```python
# Finding Handler 接口
class FindingHandler(ABC):
    @abstractmethod
    def can_handle(self, finding: dict) -> bool:
        """判断是否能处理该类型 Finding"""
        pass

    @abstractmethod
    def analyze(self, finding: dict) -> AnalysisResult:
        """分析 Finding"""
        pass

    @abstractmethod
    def generate_remediation(self, analysis: AnalysisResult) -> RemediationPlan:
        """生成修复方案"""
        pass

    @abstractmethod
    def execute_remediation(self, plan: RemediationPlan) -> ExecutionResult:
        """执行修复"""
        pass

# 注册新的 Handler
handler_registry.register(S3PublicAccessHandler())
handler_registry.register(SecurityGroupOpenHandler())
handler_registry.register(IAMOverprivilegedHandler())
```

### 7.2 经验学习与知识库

SHARA 采用"经验学习"模式，通过用户反馈持续优化修复质量，而非依赖预定义的 Playbook。

#### 7.2.1 经验学习流程

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         修复经验学习流程                                  │
│                                                                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                 │
│  │  修复完成    │───▶│  发送邮件   │───▶│  用户评价    │                 │
│  └─────────────┘    │ (含评价链接) │    └──────┬──────┘                 │
│                     └─────────────┘           │                         │
│                                               │                         │
│                           ┌───────────────────┴───────────────────┐     │
│                           │                                       │     │
│                           ▼                                       ▼     │
│                  ┌─────────────────┐                    ┌─────────────┐ │
│                  │  评价"有效"     │                    │ 评价"无效"  │ │
│                  └────────┬────────┘                    └─────────────┘ │
│                           │                                             │
│                           ▼                                             │
│                  ┌─────────────────┐                                    │
│                  │  Agent 保存     │                                    │
│                  │  修复经验       │                                    │
│                  │  (思路+代码)    │                                    │
│                  └────────┬────────┘                                    │
│                           │                                             │
│                           ▼                                             │
│                  ┌─────────────────┐                                    │
│                  │  S3 Knowledge   │                                    │
│                  │  Bucket         │                                    │
│                  └────────┬────────┘                                    │
│                           │                                             │
│                           ▼                                             │
│                  ┌─────────────────┐                                    │
│                  │  Bedrock KB     │                                    │
│                  │  自动向量化     │                                    │
│                  └────────┬────────┘                                    │
│                           │                                             │
│                           ▼                                             │
│                  ┌─────────────────┐                                    │
│                  │  未来修复时     │                                    │
│                  │  检索相似经验   │                                    │
│                  └─────────────────┘                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

#### 7.2.2 知识库存储结构

```
s3://shara-knowledge-{stage}-{account}/
├── experiences/
│   ├── S3.1/                              # 按 Control ID 分类
│   │   ├── {task_id}.json                 # 修复经验文档
│   │   │   {
│   │   │     "task_id": "xxx",
│   │   │     "control_id": "S3.1",
│   │   │     "finding_title": "S3 Block Public Access",
│   │   │     "resource_type": "AwsS3Bucket",
│   │   │     "analysis_summary": "...",    # Agent 分析思路
│   │   │     "remediation_approach": "...", # 修复方案
│   │   │     "execution_steps": [...],     # 执行步骤
│   │   │     "lessons_learned": "...",     # 经验总结
│   │   │     "rating": "effective",        # 用户评价
│   │   │     "created_at": "..."
│   │   │   }
│   │   └── {task_id}_code.py              # 修复代码
│   │
│   ├── EC2.19/
│   │   └── ...
│   └── IAM.4/
│       └── ...
```

#### 7.2.3 Bedrock Knowledge Base 配置

部署后需要在 AWS 控制台创建 Bedrock Knowledge Base：

| 配置项 | 值 |
|--------|-----|
| 数据源 | S3: `shara-knowledge-{stage}-{account}` |
| 嵌入模型 | Amazon Titan Text Embeddings V2 |
| 向量数据库 | Amazon OpenSearch Serverless |
| 同步频率 | 按需或每日 |

#### 7.2.4 Agent 检索经验流程

```python
# Agent 在分析新 Finding 时检索相关经验
def retrieve_similar_experiences(control_id: str, finding: dict) -> list:
    """
    使用 Bedrock Knowledge Base 检索相似修复经验
    """
    kb_client = boto3.client('bedrock-agent-runtime')

    response = kb_client.retrieve(
        knowledgeBaseId=KNOWLEDGE_BASE_ID,
        retrievalQuery={
            'text': f"Control: {control_id}, Finding: {finding['title']}"
        },
        retrievalConfiguration={
            'vectorSearchConfiguration': {
                'numberOfResults': 3
            }
        }
    )

    return response['retrievalResults']
```

---

## 8. 文档版本

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| 1.0 | 2025-01-28 | - | 初始版本 |
| 1.1 | 2025-01-29 | - | 新增"经验学习与知识库"章节，重构知识库为向量化存储 |
| 2.0 | 2025-01-29 | - | 重构架构：移除 Orchestrator Agent，Lambda 负责调度；增加 Feedback Handler Lambda；Analyzer 负责生成修复/回滚方案；增加回滚机制 |
| 3.0 | 2025-01-29 | - | 重构为两阶段架构（Phase 1: 审批前分析; Phase 2: 审批后执行）；审批邮件只包含描述不含代码；新增 AgentCore Memory 集成；更新任务状态机和数据流图 |
| 4.0 | 2025-01-31 | - | A2A 协议重构：Remediator 通过 A2A 协议调用 Validator；Validator 增强职责（代码安全审查、结果验证、触发结果邮件）；新增结果邮件和回滚流程；结果邮件含 Rollback 链接；回滚邮件不含 Rollback 链接 |
