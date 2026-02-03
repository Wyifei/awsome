# SHARA 工作流程

> **SHARA**: Security Hub Auto-Remediation Agent

## 系统概览

```
                              Security Hub Finding (HIGH/CRITICAL)
                                            │
                                            ▼
                                  ┌───────────────────┐
                                  │  EventBridge Rule │
                                  └─────────┬─────────┘
                                            │
                                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DynamoDB                                       │
│  ┌─────────────────────────────┐    ┌─────────────────────────────┐        │
│  │         Tasks 表            │    │        Tokens 表            │        │
│  │  • 创建/更新任务状态        │    │  • 存储审批 Token           │        │
│  │  • 保存分析结果             │    │  • 存储回滚 Token           │        │
│  │  • 记录修复结果             │    │  • Token 验证               │        │
│  └─────────────────────────────┘    └─────────────────────────────┘        │
└──────────────────────────┬──────────────────────┬───────────────────────────┘
                           │                      │
         ┌─────────────────┴──────┐    ┌─────────┴─────────────────┐
         │                        │    │                           │
         ▼                        │    │                           ▼
┌─────────────────┐               │    │               ┌─────────────────┐
│  Event Handler  │               │    │               │Approval Handler │
│     Lambda      │               │    │               │     Lambda      │
└────────┬────────┘               │    │               └────────┬────────┘
         │                        │    │                        ▲
         │ 调用                   │    │                        │
         ▼                        │    │                        │
┌─────────────────┐               │    │               ┌────────┴────────┐
│    Analyzer     │               │    │               │   API Gateway   │
│     Agent       │               │    │               │  /approvals/    │
│  ────────────   │               │    │               └────────┬────────┘
│  • 获取 ASR     │               │    │                        ▲
│  • 搜索 LTM     │               │    │                        │ 用户点击
│  • 生成方案     │               │    │                        │
└────────┬────────┘               │    │               ┌────────┴────────┐
         │                        │    │               │                 │
         │                        │    │      ┌───────┴───────┐ ┌───────┴───────┐
         ▼                        │    │      │   审批链接     │ │   回滚链接     │
┌─────────────────┐               │    │      │ ?action=      │ │ ?action=      │
│    审批邮件     │───────────────┼────┼─────▶│   approve     │ │   rollback    │
│  ────────────   │               │    │      └───────────────┘ └───────────────┘
│  • 分析结果     │               │    │               ▲
│  • 修复方案     │               │    │               │
│  • 审批/拒绝链接│               │    │               │
└─────────────────┘               │    │               │
                                  │    │               │
                           ┌──────┴────┴───────┐       │
                           │                   │       │
                           │                   ▼       │
                           │          ┌─────────────────┐
                           │          │   Remediator    │
                           │          │     Agent       │
                           │          │  ────────────   │
                           │          │  • 生成代码     │
                           │          │  • 执行修复     │
                           │          │  • 保存回滚数据 │
                           │          └────────┬────────┘
                           │                   │ A2A
                           │                   ▼
                           │          ┌─────────────────┐
                           │          │    Validator    │
                           │          │     Agent       │
                           │          │  ────────────   │
                           │          │  • 代码审查     │
                           │          │  • 验证状态     │
                           │          │  • 更新 Finding │
                           │          │  • 保存 LTM     │
                           │          └────────┬────────┘
                           │                   │
                           │                   ▼
                           │          ┌─────────────────┐
                           └──────────│    结果邮件     │
                              写入    │  ────────────   │
                             回滚Token│  • 执行结果     │
                                      │  • 检查明细     │
                                      │  • 回滚链接  ───┼──▶ 指向 API Gateway
                                      └─────────────────┘
```

### 审批流程时序

```
用户点击审批链接
      │
      ▼
┌──────────────┐    GET /approvals/{taskId}/respond?action=approve&token=xxx
│              │─────────────────────────────────────────────────────────────▶
│    浏览器    │
│              │◀─────────────────────────────────────────────────────────────
└──────────────┘    HTML 响应页面
                              │
                              ▼
                    ┌──────────────────┐
                    │   API Gateway    │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐     ┌──────────────┐
                    │ Approval Handler │────▶│   DynamoDB   │ 1. 验证 Token
                    │      Lambda      │◀────│    Tokens    │    (是否有效/过期)
                    └────────┬─────────┘     └──────────────┘
                             │
                             │ Token 验证通过
                             ▼
                    ┌──────────────────┐
                    │ Approval Handler │────▶ 2. 更新 Task 状态为 remediating
                    └────────┬─────────┘
                             │
                             │ 异步调用
                             ▼
                    ┌──────────────────┐
                    │    Remediator    │────▶ 3. 生成代码、执行修复
                    │      Agent       │
                    └────────┬─────────┘
                             │ A2A
                             ▼
                    ┌──────────────────┐
                    │     Validator    │────▶ 4. 验证、更新 Finding、保存 LTM
                    │      Agent       │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐     ┌──────────────┐
                    │ Approval Handler │────▶│   DynamoDB   │ 5. 生成回滚 Token
                    │   (发送邮件)     │     │    Tokens    │
                    └────────┬─────────┘     └──────────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │     结果邮件     │────▶ 包含回滚链接 (24小时有效)
                    └──────────────────┘
```

### 回滚流程时序

```
用户点击回滚链接
      │
      ▼
┌──────────────┐    GET /approvals/{taskId}/respond?action=rollback&token=xxx
│    浏览器    │─────────────────────────────────────────────────────────────▶
└──────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │   API Gateway    │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐     ┌──────────────┐
                    │ Approval Handler │────▶│   DynamoDB   │ 1. 验证回滚 Token
                    │      Lambda      │◀────│    Tokens    │
                    └────────┬─────────┘     └──────────────┘
                             │
                             │ Token 验证通过
                             ▼
                    ┌──────────────────┐
                    │    Remediator    │────▶ 2. 从 Memory 获取回滚代码并执行
                    │  (is_rollback)   │
                    └────────┬─────────┘
                             │ A2A
                             ▼
                    ┌──────────────────┐
                    │     Validator    │────▶ 3. 验证恢复到 pre_state
                    │  (is_rollback)   │────▶ 4. Finding 状态改回 NEW
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │   回滚结果邮件   │────▶ ⚠️ 不含回滚链接 (回滚不可逆)
                    └──────────────────┘
```

### 核心流程说明

| 流程 | 触发方式 | 处理 Lambda | 调用 Agent |
|------|----------|-------------|------------|
| 分析 | EventBridge 事件 | Event Handler | Analyzer |
| 修复 | 用户点击审批链接 | Approval Handler | Remediator → Validator |
| 回滚 | 用户点击回滚链接 | Approval Handler | Remediator → Validator |

### DynamoDB 在流程中的作用

| 阶段 | Lambda | DynamoDB 操作 |
|------|--------|---------------|
| 分析开始 | Event Handler | 创建 Task (status=analyzing) |
| 分析完成 | Event Handler | 更新 Task + 生成审批 Token |
| 审批请求 | Approval Handler | **验证审批 Token** |
| 修复开始 | Approval Handler | 更新 Task (status=remediating) |
| 修复完成 | Approval Handler | 更新 Task + **生成回滚 Token** |
| 回滚请求 | Approval Handler | **验证回滚 Token** |
| 回滚完成 | Approval Handler | 更新 Task (status=rolled_back) |

---

## Phase 1: 分析与审批

### 1.1 事件触发

**触发条件**: Security Hub 产生 HIGH 或 CRITICAL 级别的 Finding

**EventBridge 规则**:
```json
{
  "source": ["aws.securityhub"],
  "detail-type": ["Security Hub Findings - Imported"],
  "detail": {
    "findings": {
      "Severity": { "Label": ["HIGH", "CRITICAL"] },
      "Workflow": { "Status": ["NEW"] }
    }
  }
}
```

### 1.2 Event Handler Lambda

**职责**: 接收 Finding，创建任务，调用 Analyzer Agent

**处理流程**:
1. 解析 Finding，提取 Control ID (如 `S3.1`)
2. 分类 Finding 类型:
   - `FSBP_CONTROL`: AWS 基础安全最佳实践 → 调用 Agent 修复
   - `CONTAINER_CVE`: 容器镜像漏洞 → 发送通知邮件
   - `EC2_CVE`: EC2 软件漏洞 → 发送通知邮件
3. 检查重复任务 (24 小时去重)
4. 创建任务记录 (DynamoDB)
5. 调用 Analyzer Agent Runtime

### 1.3 Analyzer Agent

**职责**: 分析 Finding，生成修复方案描述，发送审批邮件

**工具调用顺序**:

| 步骤 | 工具 | 说明 |
|------|------|------|
| 1 | `get_resource_config` | 验证资源是否存在，获取当前配置 |
| 2 | `fetch_asr_playbook` | 从 S3 获取 ASR 预定义修复方案 |
| 3 | `search_similar_findings` | 从 LTM 搜索历史修复经验 |
| 4 | `save_analysis_result` | 保存分析结果到 Memory (STM) |

**ASR Playbook 获取**:
- 存储位置: `s3://{bucket}/playbooks/{control_id}.json`
- 包含: 修复描述、代码模板、参数定义

**LTM 搜索**:
- 搜索 Reflection (方法论框架) 和 Episode (执行记录)
- 命名空间: `/remediation/actors/{accountId}/`

**输出**: JSON 格式的分析结果，包含:
- `analysis`: 风险评估、资源状态
- `asr_match`: ASR Playbook 匹配信息
- `similar_experiences`: 历史修复经验
- `remediation`: 修复方案 (prerequisites / agent_actions / post_actions)

### 1.4 审批邮件

**发送**: Event Handler Lambda 通过 SES 发送

**内容**:
- Finding 详情 (Control ID, 资源, 严重性)
- 分析结果摘要
- 修复方案描述
- 相似修复经验 (如有)
- 审批/拒绝链接 (24 小时有效)

---

## Phase 2: 修复与验证

### 2.1 审批通过

用户点击审批链接后，API Gateway 调用 Approval Handler Lambda。

### 2.2 Approval Handler Lambda

**职责**: 验证审批 Token，调用 Remediator Agent

**处理流程**:
1. 验证 Token 有效性 (DynamoDB)
2. 更新任务状态为 `remediating`
3. 异步调用 Remediator Agent Runtime

### 2.3 Remediator Agent

**职责**: 生成并执行修复代码，调用 Validator 验证

**工具调用顺序**:

| 阶段 | 步骤 | 工具 | 说明 |
|------|------|------|------|
| 准备 | 1 | `get_analysis_context` | 获取 Phase 1 分析结果 |
| 准备 | 2 | `get_resource_config` | 获取资源当前状态 (pre_state) |
| 代码生成 | 3 | - | 生成修复代码 (优先使用 ASR 模板) |
| 代码生成 | 4 | - | 生成回滚代码 |
| 保存 | 5 | `save_rollback_to_memory` | 保存回滚数据 |
| 执行 | 6 | `pre_execution_check` | 验证代码安全性 |
| 执行 | 7 | `execute_code` | 在沙盒中执行修复代码 |
| 保存 | 8 | `save_remediation_result` | 保存执行结果到 Memory |
| A2A | 9 | `invoke_validator_agent` | 调用 Validator Agent |

**代码执行**: 通过 AgentCore Code Interpreter 在隔离沙盒中执行

**错误重试**: 最多 2 次，在同一沙盒 Session 中

### 2.4 Validator Agent

**职责**: 验证修复结果，更新 Security Hub，保存经验

**工具调用顺序**:

| 步骤 | 工具 | 说明 |
|------|------|------|
| 1 | `get_remediation_result` | 从 Memory 获取代码和执行结果 |
| 2 | `review_code_security` | 审查代码安全风险 |
| 3 | `verify_resource_state` | 验证资源达到期望状态 |
| 4 | `update_security_hub_finding` | 更新 Finding 状态为 RESOLVED |
| 5 | `save_experience_to_ltm` | 保存成功经验到 LTM |
| 6 | `trigger_result_email` | 触发结果通知邮件 |

### 2.5 结果邮件

**发送**: Approval Handler Lambda 通过 SES 发送

**内容**:
- 任务执行结果 (成功/失败)
- 代码审查结果 (状态、风险等级、问题数)
- 验证检查项明细
- 回滚链接 (24 小时有效)

---

## 数据流

### Memory (AgentCore Memory)

**STM (短期记忆)**: 同一任务内三个 Agent 共享

| 数据类型 | 写入 Agent | 读取 Agent |
|----------|-----------|-----------|
| `phase1_analysis` | Analyzer | Remediator |
| `rollback_data` | Remediator | Validator (回滚时) |
| `remediation_result` | Remediator | Validator |

**LTM (长期记忆)**: 跨任务共享的修复经验

| 类型 | 说明 | 索引字段 |
|------|------|----------|
| Reflection | 方法论框架 | use_cases |
| Episode | 执行记录 | intent |

### DynamoDB

#### Tasks 表 (`shara-{stage}-tasks`)

**用途**: 任务全生命周期状态管理

| 阶段 | 操作 Lambda | 状态变化 |
|------|-------------|----------|
| 创建 | Event Handler | `analyzing` |
| 分析完成 | Event Handler | `waiting_approval` |
| 审批通过 | Approval Handler | `remediating` |
| 修复完成 | Approval Handler | `completed` / `failed` |
| 回滚中 | Approval Handler | `rolling_back` |
| 回滚完成 | Approval Handler | `rolled_back` |

**关键字段**:
- `taskId`: 任务唯一标识
- `findingId`: Security Hub Finding ID (用于去重)
- `controlId`: 控制项 ID (如 S3.1)
- `status`: 当前状态
- `phase`: 当前阶段 (pre_approval / post_approval)
- `memorySessionId`: Memory Session ID (三个 Agent 共享)
- `actorId`: AWS Account ID (用于 LTM 检索)
- `analysisResult`: Phase 1 分析结果 (JSON)
- `ttl`: 过期时间 (24 小时)

#### Tokens 表 (`shara-{stage}-approval-tokens`)

**用途**: 审批/回滚链接的 Token 验证

| Token 类型 | 生成时机 | 有效期 | 用途 |
|------------|----------|--------|------|
| 审批 Token | Event Handler 发送审批邮件时 | 24 小时 | 验证审批/拒绝请求 |
| 回滚 Token | Approval Handler 发送结果邮件时 | 24 小时 | 验证回滚请求 |

**关键字段**:
- `token`: Token 值 (UUID)
- `taskId`: 关联的任务 ID
- `type`: Token 类型 (approval / rollback)
- `ttl`: 过期时间戳

### S3

| Bucket | 用途 |
|--------|------|
| `shara-{stage}-asr-playbooks-{accountId}` | ASR 预定义修复方案 |

---

## 回滚流程

```
结果邮件 (含回滚链接)
        │
        │ 用户点击: /approvals/{taskId}/respond?action=rollback&token=xxx
        ▼
┌───────────────────┐
│   API Gateway     │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐     ┌─────────────┐
│ Approval Handler  │────▶│  DynamoDB   │  验证回滚 Token
│     Lambda        │     │   Tokens    │
└─────────┬─────────┘     └─────────────┘
          │
          ▼
┌───────────────────┐
│   Remediator      │  is_rollback=True
│     Agent         │
│  ─────────────    │
│  1. get_rollback_from_memory  ──▶ 获取预存的回滚代码
│  2. execute_code              ──▶ 执行回滚代码
│  3. invoke_validator_agent    ──▶ A2A 调用验证
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│    Validator      │  is_rollback=True
│     Agent         │
│  ─────────────    │
│  1. verify_resource_state     ──▶ 验证恢复到 pre_state
│  2. update_security_hub       ──▶ 状态改回 NEW
│  3. trigger_result_email      ──▶ 发送回滚结果邮件
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│   回滚结果邮件    │  ⚠️ 不含回滚链接
│  (回滚不可逆)     │
└───────────────────┘
```

**关键区别**:
- 修复验证: 检查资源是否达到安全配置 → Finding 状态改为 `RESOLVED`
- 回滚验证: 检查资源是否恢复到 pre_state → Finding 状态改回 `NEW`

---

## 关键文件

| 组件 | 路径 |
|------|------|
| Event Handler | `infra/lambda/event_handler/handler.py` |
| Approval Handler | `infra/lambda/approval_handler/handler.py` |
| Analyzer Agent | `agents/analyzer/agent.py` |
| Remediator Agent | `agents/remediator/agent.py` |
| Validator Agent | `agents/validator/agent.py` |
| Memory Tools | `agents/shared/tools/memory_tools.py` |
| ASR Playbook Tool | `agents/shared/tools/asr_playbook.py` |
| Code Execution | `agents/shared/tools/execution.py` |
