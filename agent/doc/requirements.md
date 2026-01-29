# Security Hub Auto-Remediation Agent 需求文档

## 1. 项目概述

### 1.1 项目名称
Security Hub Auto-Remediation Agent (SHARA)

### 1.2 项目目标
构建一个基于 AWS AgentCore 和 Strands Agent 框架的智能体系统，自动化处理 AWS Security Hub 中的 HIGH 和 CRITICAL 级别安全发现，生成修复方案，并通过审批流程实施修复。

### 1.3 核心价值
- **自动化响应**：减少安全事件响应时间从小时级降至分钟级
- **智能决策**：利用 AI 能力结合 ASR 经验库生成针对性的修复方案
- **合规审批**：确保所有修复操作经过人工审批，满足合规要求
- **全面覆盖**：支持 Security Hub 聚合的多种安全服务的 findings
- **经验积累**：通过长期记忆积累修复经验，持续优化修复质量

---

## 2. 功能需求

### 2.1 Finding 接收与分析

#### 2.1.1 事件触发
| 需求ID | 描述 | 优先级 |
|--------|------|--------|
| FR-001 | 通过 EventBridge 规则监听 Security Hub findings 事件 | P0 |
| FR-002 | 仅处理 severity 为 HIGH 或 CRITICAL 的 findings | P0 |
| FR-003 | 支持 Lambda 函数作为事件处理入口和流程协调器 | P0 |
| FR-004 | 支持批量 findings 的去重和聚合处理 | P1 |
| FR-005 | 支持基于 Control ID 精准匹配 ASR 修复方案 | P0 |

#### 2.1.2 支持的 Finding 来源
| 需求ID | 来源服务 | Finding 类型示例 | 优先级 |
|--------|----------|------------------|--------|
| FR-010 | AWS Config | 配置合规性检查（如 S3 公开访问、未加密资源等） | P0 |
| FR-011 | Amazon GuardDuty | 威胁检测（如异常 API 调用、恶意 IP 访问等） | P0 |
| FR-012 | Amazon Inspector | EC2 实例漏洞、ECR 镜像漏洞 | P0 |
| FR-013 | IAM Access Analyzer | IAM 策略风险分析 | P1 |
| FR-014 | Amazon Macie | S3 敏感数据发现 | P1 |
| FR-015 | AWS Firewall Manager | 网络安全策略违规 | P2 |

### 2.2 修复方案生成

#### 2.2.1 方案生成能力
| 需求ID | 描述 | 优先级 |
|--------|------|--------|
| FR-020 | 根据 Control ID 精准匹配 ASR 修复方案 | P0 |
| FR-021 | 无精准匹配时，使用 AI 结合长期记忆生成方案 | P0 |
| FR-022 | 修复方案包含：问题描述、影响分析、修复步骤、回滚方案 | P0 |
| FR-023 | 支持生成 Terraform/CloudFormation IaC 代码 | P1 |
| FR-024 | 支持生成 AWS CLI/SDK 命令 | P0 |
| FR-025 | 提供修复风险评估和预期影响说明 | P0 |

#### 2.2.2 ASR 方案匹配策略

> **注意**：ASR 方案匹配由 **Analyzer Agent** 在审批前完成，匹配结果存储到 Memory 供审批后的 Remediator Agent 使用。

```
┌─────────────────────────────────────────────────────────┐
│           Analyzer Agent 方案匹配流程                    │
├─────────────────────────────────────────────────────────┤
│  1. 精准匹配: Control ID → S3 ASR Playbook              │
│     - 使用 fetch_asr_playbook 工具从 S3 获取            │
│     - 适用于: S3.1, EC2.19, IAM.1 等标准控制 (110+)     │
│     - 返回: 修复步骤和指导说明                           │
│                                                         │
│  2. 语义匹配: Finding 描述 → Memory LTM 检索             │
│     - 使用 search_similar_findings 工具                  │
│     - 检索相似的历史修复经验                              │
│     - 适用于: 无标准 Control ID 的 findings              │
│                                                         │
│  3. AI 生成: LLM + 上下文 → 修复建议                     │
│     - 结合资源配置和历史经验                              │
│     - 适用于: 新类型或复杂场景                           │
│                                                         │
│  ──────────────────────────────────────────────────────  │
│  匹配结果 → save_analysis_result → Memory               │
│  (供审批后 Remediator Agent 使用)                        │
└─────────────────────────────────────────────────────────┘
```

#### 2.2.3 常见修复场景
| 场景 | 描述 | 修复方式 | ASR 控制 |
|------|------|----------|----------|
| S3 公开访问 | S3 bucket 配置了公开访问权限 | 修改 bucket policy，启用 Block Public Access | S3.1-S3.20 |
| 安全组开放 | 安全组对 0.0.0.0/0 开放敏感端口 | 收紧安全组规则 | EC2.18-EC2.21 |
| 未加密存储 | EBS/RDS/S3 未启用加密 | 启用加密（可能需要数据迁移） | EC2.3, RDS.3 |
| IAM 权限过大 | IAM 策略授予过多权限 | 最小权限原则优化策略 | IAM.1-IAM.21 |
| 漏洞修复 | EC2/ECR 存在已知漏洞 | 补丁更新或镜像重建 | Inspector |
| 异常活动 | GuardDuty 检测到异常行为 | 隔离资源、轮换凭证 | GuardDuty |

### 2.3 审批流程

#### 2.3.1 邮件通知
| 需求ID | 描述 | 优先级 |
|--------|------|--------|
| FR-030 | 通过 Amazon SES 发送修复方案邮件 | P0 |
| FR-031 | 邮件内容包含：finding 详情、修复方案、风险说明 | P0 |
| FR-032 | 邮件包含"同意执行"和"拒绝"按钮/链接 | P0 |
| FR-033 | 支持配置多个审批人（邮件分发列表） | P1 |
| FR-034 | 支持审批超时提醒 | P2 |

#### 2.3.2 审批机制
| 需求ID | 描述 | 优先级 |
|--------|------|--------|
| FR-040 | 提供 API Gateway 端点接收审批响应 | P0 |
| FR-041 | 审批链接包含安全 token，防止未授权操作 | P0 |
| FR-042 | 支持审批记录持久化（DynamoDB） | P0 |
| FR-043 | 支持审批有效期设置（如 24 小时） | P1 |

### 2.4 修复执行与验证

#### 2.4.1 执行能力
| 需求ID | 描述 | 优先级 |
|--------|------|--------|
| FR-050 | 审批通过后自动执行修复方案 | P0 |
| FR-051 | 支持 dry-run 模式预览修复效果 | P1 |
| FR-052 | 执行结果通过邮件通知管理员 | P0 |
| FR-053 | 修复失败时自动执行回滚 | P1 |
| FR-054 | 所有操作记录 CloudTrail 日志 | P0 |

#### 2.4.2 验证能力
| 需求ID | 描述 | 优先级 |
|--------|------|--------|
| FR-060 | 修复后自动验证资源合规状态 | P0 |
| FR-061 | 验证失败时触发告警和回滚 | P0 |
| FR-062 | 更新 Security Hub Finding 状态 | P0 |
| FR-063 | 记录修复经验到长期记忆 | P1 |

---

## 3. 技术架构

### 3.1 架构概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Event Sources                                   │
├─────────────┬─────────────┬─────────────┬─────────────┬────────────────────┤
│ AWS Config  │  GuardDuty  │  Inspector  │   Macie     │  IAM Analyzer      │
└──────┬──────┴──────┬──────┴──────┬──────┴──────┬──────┴─────────┬──────────┘
       │             │             │             │                │
       └─────────────┴─────────────┴─────────────┴────────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │      AWS Security Hub        │
                    │   (Findings Aggregation)     │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │      Amazon EventBridge      │
                    │  (HIGH/CRITICAL Filter)      │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Lambda Orchestrator Layer                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     Lambda Function                                  │   │
│  │  - Event Preprocessing (Finding 解析、去重、优先级排序)              │   │
│  │  - Control ID Extraction (提取控制标识符)                           │   │
│  │  - Agent Invocation (调用 AgentCore Runtime)                        │   │
│  │  - Approval Handling (审批回调处理)                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      AgentCore Runtime Layer                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    BedrockAgentCoreApp                               │   │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐              │   │
│  │  │  Analyzer   │ ─► │ Remediator  │ ─► │  Validator  │              │   │
│  │  │   Agent     │    │   Agent     │    │   Agent     │              │   │
│  │  ├─────────────┤    ├─────────────┤    ├─────────────┤              │   │
│  │  │- Finding 分析│    │- 代码生成    │    │- 执行验证   │              │   │
│  │  │- 风险评估   │    │- 执行修复    │    │- 状态检查   │              │   │
│  │  │- ASR方案匹配│    │- 回滚处理    │    │- 结果报告   │              │   │
│  │  │- 修复建议   │    │             │    │- 经验记录   │              │   │
│  │  └─────────────┘    └─────────────┘    └─────────────┘              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                  │                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │               AgentCoreMemorySessionManager                          │   │
│  │  - 短期记忆: 对话历史、执行状态                                       │   │
│  │  - 长期记忆: ASR 经验、历史修复方案                                   │   │
│  │  - Hook 集成: 自动检索相关上下文                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
        ▼                         ▼                         ▼
┌───────────────┐      ┌───────────────────┐      ┌─────────────────┐
│  Amazon S3    │      │  AgentCore Memory │      │   DynamoDB      │
│ (ASR Playbooks│      │ (Session & LTM)   │      │ (Approval State)│
│  110+ files)  │      │                   │      │                 │
└───────────────┘      └───────────────────┘      └─────────────────┘
                                  │
                                  ▼
                    ┌──────────────────────────────┐
                    │        Amazon SES            │
                    │    (Email Notification)      │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │      Administrator           │
                    │   (Approve / Reject)         │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │      API Gateway             │
                    │   (Approval Callback)        │
                    └──────────────────────────────┘
```

### 3.2 核心组件

#### 3.2.1 Agent 架构设计

**方案：Lambda + 三智能体协作架构**

| 组件 | 职责 | 说明 |
|------|------|------|
| Lambda Orchestrator | 事件预处理、Control ID 提取、Agent 调用、审批回调 | 轻量级，按需执行 |
| Analyzer Agent | Finding 分析、风险评估、ASR 方案匹配、生成修复建议 | 分析 + 决策（做什么） |
| Remediator Agent | 代码生成、执行修复、回滚处理 | 实现 + 执行（怎么做） |
| Validator Agent | 修复验证、状态更新、经验记录 | 验证（做对了吗） |

**架构优势：**
1. **关注点分离**：Lambda 处理事件，Agent 专注 AI 推理
2. **成本优化**：Lambda 按需计费，避免 Agent 空闲开销
3. **可扩展性**：各组件独立扩展和优化
4. **经验积累**：通过 Memory 长期记忆持续学习

#### 3.2.2 技术栈

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| Agent 框架 | Strands Agent SDK | 开源框架，支持多模型 |
| Agent 运行时 | AWS AgentCore Runtime | 安全隔离的执行环境 |
| Session 管理 | AgentCoreMemorySessionManager | Strands + Memory 深度集成 |
| LLM | Amazon Bedrock (Claude) | 强大的推理和代码生成能力 |
| 事件处理 | EventBridge + Lambda | 事件驱动架构 |
| 短期记忆 | AgentCore Memory (Events) | 对话历史、执行状态 |
| 长期记忆 | AgentCore Memory (LTM) | ASR 经验、历史方案 |
| 状态存储 | DynamoDB | 审批状态、执行记录 |
| ASR 方案 | Amazon S3 | 110+ Terraform 修复方案 |
| 通知服务 | Amazon SES | 邮件发送 |
| API 网关 | API Gateway | 审批回调端点 |
| 可观测性 | CloudWatch + OpenTelemetry | 监控、追踪、日志 |

### 3.3 Memory 架构设计

#### 3.3.1 记忆层次

```
AgentCore Memory
├── 短期记忆 (Session Events)
│   ├── Actor: 用户/账户标识
│   ├── Session: 修复任务会话
│   └── Events: 对话历史、中间状态
│
└── 长期记忆 (Semantic Memory)
    ├── /asr/playbooks/{controlId}
    │   └── ASR 修复方案 (110+ controls)
    │
    ├── /remediation/history/{actorId}
    │   └── 历史修复记录和经验
    │
    └── /context/resources/{sessionId}
        └── 资源配置快照
```

#### 3.3.2 检索配置

```python
retrieval_config = {
    # ASR 经验库 - 按控制ID检索
    "asr/playbooks/{controlId}": RetrievalConfig(
        top_k=3,
        relevance_score=0.7
    ),

    # 历史修复方案 - 按用户检索
    "remediation/history/{actorId}": RetrievalConfig(
        top_k=5,
        relevance_score=0.5
    ),

    # 资源上下文 - 按会话检索
    "context/resources/{sessionId}": RetrievalConfig(
        top_k=10,
        relevance_score=0.4
    ),
}
```

### 3.4 数据流设计

```
═══════════════════════════════════════════════════════════════
                    阶段一：分析与审批（审批前）
═══════════════════════════════════════════════════════════════

1. Finding 接收与预处理
   Security Hub ─► EventBridge ─► Lambda Orchestrator
   Lambda:
     - 解析 Finding (ASFF 格式)
     - 提取 Control ID (如 S3.1, EC2.19)
     - 去重和优先级排序
     - 调用 AgentCore Runtime

2. 分析与方案匹配
   Lambda ─► AgentCore Runtime ─► Analyzer Agent
   Analyzer Agent:
     - 解析 Finding 详情
     - 查询相关资源配置 (AWS API)
     - 评估影响范围和风险等级
     - ASR 方案匹配:
       · 精准匹配: Control ID → S3 ASR Playbook
       · 语义匹配: Finding 描述 → Memory LTM 检索
     - 生成修复建议描述（用于审批邮件）
     - 存储分析结果到 Memory

3. 发送审批请求
   Analyzer Agent ─► Lambda ─► SES ─► Administrator
   邮件内容:
     - Finding 摘要
     - 风险等级
     - 修复建议描述（不含代码）
     - 同意/拒绝按钮

═══════════════════════════════════════════════════════════════
                    阶段二：执行与验证（审批后）
═══════════════════════════════════════════════════════════════

4. 审批回调
   Administrator ─► API Gateway ─► Lambda (Approval Handler)
   Lambda:
     - 验证审批 Token
     - 更新 DynamoDB 状态
     - 从 Memory 获取分析结果
     - 调用 AgentCore Runtime

5. 代码生成与执行
   Lambda ─► AgentCore Runtime ─► Remediator Agent
   Remediator Agent:
     - 获取 ASR 方案详情（Analyzer 已匹配）
     - 生成可执行代码 (Terraform/CLI)
     - 执行修复操作 (AWS API)
     - 记录执行日志

6. 验证与报告
   Remediator Agent ─► Validator Agent
   Validator Agent:
     - 验证资源合规状态
     - 更新 Security Hub Finding 状态
     - 记录修复经验到 Memory LTM
     - 发送执行结果邮件
```

### 3.5 Agent 工具设计

#### 3.5.1 Analyzer Agent 工具

```python
@tool
def get_resource_configuration(resource_arn: str, resource_type: str) -> dict:
    """获取 AWS 资源的当前配置"""

@tool
def assess_impact(resource_arn: str, finding_type: str) -> dict:
    """评估安全发现的影响范围"""

@tool
def get_related_resources(resource_arn: str) -> list:
    """获取与目标资源相关的其他资源"""

@tool
def fetch_asr_playbook(control_id: str, resource_type: str) -> dict:
    """从 S3 获取 ASR 修复方案 (精准匹配)

    Args:
        control_id: Security Hub 控制 ID (如 S3.1, EC2.19)
        resource_type: AWS 资源类型

    Returns:
        包含修复步骤和指导的方案，无匹配时返回空
    """

@tool
def search_similar_findings(query: str, namespace: str) -> list:
    """从 Memory LTM 语义检索相似的历史 Finding 和修复经验

    Args:
        query: 搜索查询 (Finding 描述)
        namespace: Memory 命名空间

    Returns:
        相似的历史修复经验列表
    """

@tool
def save_analysis_result(finding_id: str, analysis: dict) -> str:
    """保存分析结果到 Memory，供审批后使用"""
```

#### 3.5.2 Remediator Agent 工具

```python
@tool
def get_analysis_result(finding_id: str) -> dict:
    """从 Memory 获取 Analyzer 的分析结果和 ASR 方案"""

@tool
def generate_remediation_code(asr_plan: dict, resource_config: dict) -> str:
    """根据 ASR 方案和资源配置生成修复代码 (Terraform/CLI)"""

@tool
def execute_remediation(resource_arn: str, code: str, dry_run: bool = True) -> dict:
    """执行修复操作"""

@tool
def rollback_remediation(execution_id: str) -> dict:
    """回滚修复操作"""
```

#### 3.5.3 Validator Agent 工具

```python
@tool
def validate_compliance(resource_arn: str, control_id: str) -> dict:
    """验证资源合规状态"""

@tool
def update_finding_status(finding_id: str, status: str, note: str) -> dict:
    """更新 Security Hub Finding 状态"""

@tool
def record_remediation_experience(finding_id: str, result: dict) -> None:
    """记录修复经验到长期记忆"""
```

---

## 4. 非功能需求

### 4.1 性能要求

| 指标 | 要求 | 说明 |
|------|------|------|
| 响应延迟 | < 5 分钟 | 从 Finding 产生到邮件发送 |
| 并发处理 | 支持 100+ findings/分钟 | 突发安全事件场景 |
| 方案生成 | < 2 分钟 | 单个 Finding 的方案生成时间 |
| ASR 匹配 | < 500ms | Control ID 精准匹配 |

### 4.2 可用性要求

| 指标 | 要求 |
|------|------|
| SLA | 99.9% |
| 故障恢复 | RTO < 15 分钟 |
| 数据持久性 | 审批记录保留 90 天 |
| Memory 持久性 | 长期记忆永久保留 |

### 4.3 安全要求

| 需求ID | 描述 | 优先级 |
|--------|------|--------|
| NFR-S01 | Agent 执行使用最小权限 IAM Role | P0 |
| NFR-S02 | 审批链接使用一次性 Token | P0 |
| NFR-S03 | 所有 API 调用启用 CloudTrail 审计 | P0 |
| NFR-S04 | 敏感数据（如凭证）不记录日志 | P0 |
| NFR-S05 | 支持 VPC 内部署（私有子网） | P1 |
| NFR-S06 | Memory 数据加密存储 | P0 |

### 4.4 可观测性要求

| 需求ID | 描述 | 优先级 |
|--------|------|--------|
| NFR-O01 | CloudWatch Metrics: 处理数量、成功率、延迟 | P0 |
| NFR-O02 | CloudWatch Logs: 结构化 JSON 日志 | P0 |
| NFR-O03 | OpenTelemetry: Agent 调用追踪 | P0 |
| NFR-O04 | Token 使用统计和成本监控 | P1 |
| NFR-O05 | CloudWatch Dashboard: 运营监控面板 | P1 |

---

## 5. 实现计划

### 5.1 阶段划分

#### Phase 1: MVP (最小可行产品)
- [x] EventBridge + Lambda 事件处理框架
- [x] ASR Playbooks 转换 (110 个 Terraform 方案)
- [ ] 单 Agent 架构，支持 ASR 精准匹配
- [ ] 基础邮件通知和审批流程
- [ ] AWS Config findings 支持 (S3, EC2, IAM)

#### Phase 2: 多智能体架构
- [ ] Analyzer + Remediator + Validator 三智能体
- [ ] AgentCore Memory 集成
- [ ] 长期记忆：ASR 经验库
- [ ] GuardDuty、Inspector findings 支持

#### Phase 3: 智能化增强
- [ ] 语义检索：历史修复方案匹配
- [ ] AI 生成：无 ASR 匹配时的智能方案
- [ ] 修复经验自动积累
- [ ] 高级审批流程（多级审批）

#### Phase 4: 企业级功能
- [ ] 自定义修复规则引擎
- [ ] 与 ITSM 系统集成（ServiceNow 等）
- [ ] 多账户/组织支持
- [ ] 合规报告生成

### 5.2 依赖项

| 依赖 | 类型 | 状态 |
|------|------|------|
| AWS AgentCore Runtime | 服务 | 可用 |
| AgentCore Memory | 服务 | 可用 |
| Strands Agent SDK | SDK | 可用 |
| Amazon Bedrock (Claude) | 服务 | 可用 |
| Security Hub | 服务 | 已配置 |
| ASR Playbooks | 资源 | 已转换 (110 files) |
| 已验证的 SES 域名 | 配置 | 待配置 |

### 5.3 ASR Playbooks 清单

已转换的 ASR 修复方案（110 个文件）：

| 服务 | 控制数量 | 示例控制 |
|------|----------|----------|
| S3 | 20+ | S3.1 (公开访问), S3.5 (SSL), S3.8 (加密) |
| EC2 | 25+ | EC2.1 (EBS加密), EC2.18-21 (安全组) |
| IAM | 20+ | IAM.1 (策略), IAM.6 (MFA), IAM.21 (密码策略) |
| RDS | 15+ | RDS.1 (加密), RDS.3 (存储加密) |
| Lambda | 5+ | Lambda.1 (公开访问), Lambda.5 (VPC) |
| CloudTrail | 5+ | CloudTrail.1 (启用), CloudTrail.5 (加密) |
| KMS | 5+ | KMS.1 (轮换), KMS.3 (删除) |
| 其他 | 15+ | ELB, SNS, SQS, Secrets Manager |

---

## 6. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| LLM 生成错误修复方案 | 高 | ASR 精准匹配优先 + 人工审批 + dry-run 验证 |
| 修复操作导致服务中断 | 高 | 回滚机制 + 影响分析 + 维护窗口 |
| 审批邮件被忽略 | 中 | 超时提醒 + 升级机制 |
| AgentCore 服务限制 | 中 | 了解服务配额，必要时申请提升 |
| Memory 检索不准确 | 中 | 合理设置 relevance_score 阈值 |

---

## 7. 附录

### 7.1 术语表

| 术语 | 定义 |
|------|------|
| Finding | Security Hub 中的安全发现/告警 |
| Remediation | 修复/补救措施 |
| ASFF | AWS Security Finding Format |
| ASR | Automated Security Response（自动化安全响应） |
| Control ID | Security Hub 控制标识符（如 S3.1, EC2.19） |
| AgentCore | AWS 的 AI Agent 托管服务 |
| Strands | AWS 开源的 Agent 开发框架 |
| LTM | Long-Term Memory（长期记忆） |

### 7.2 参考资料

- [AWS Security Hub Documentation](https://docs.aws.amazon.com/securityhub/)
- [Strands Agents Documentation](https://strandsagents.com/)
- [AWS Bedrock AgentCore Documentation](https://docs.aws.amazon.com/bedrock-agentcore/)
- [Amazon Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)
- [ASFF Syntax](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-findings-format.html)
- [ASR Playbooks Reference](https://github.com/aws-samples/automated-security-response-on-aws)

---

## 8. 文档历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| 1.0 | 2025-01-28 | - | 初始版本 |
| 2.0 | 2025-01-29 | - | 架构重构：Lambda + 3 Agent 设计，移除 Orchestrator Agent；增加 Memory 架构设计；更新 ASR 集成方案；增加 Validator Agent |
