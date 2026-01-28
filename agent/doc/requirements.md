# Security Hub Auto-Remediation Agent 需求文档

## 1. 项目概述

### 1.1 项目名称
Security Hub Auto-Remediation Agent (SHARA)

### 1.2 项目目标
构建一个基于 AWS AgentCore 和 Strands Agent 框架的智能体系统，自动化处理 AWS Security Hub 中的 HIGH 和 CRITICAL 级别安全发现，生成修复方案，并通过审批流程实施修复。

### 1.3 核心价值
- **自动化响应**：减少安全事件响应时间从小时级降至分钟级
- **智能决策**：利用 AI 能力生成针对性的修复方案
- **合规审批**：确保所有修复操作经过人工审批，满足合规要求
- **全面覆盖**：支持 Security Hub 聚合的多种安全服务的 findings

---

## 2. 功能需求

### 2.1 Finding 接收与分析

#### 2.1.1 事件触发
| 需求ID | 描述 | 优先级 |
|--------|------|--------|
| FR-001 | 通过 EventBridge 规则监听 Security Hub findings 事件 | P0 |
| FR-002 | 仅处理 severity 为 HIGH 或 CRITICAL 的 findings | P0 |
| FR-003 | 支持 Lambda 函数作为事件处理入口 | P0 |
| FR-004 | 支持批量 findings 的去重和聚合处理 | P1 |

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
| FR-020 | 根据 finding 类型自动生成修复方案 | P0 |
| FR-021 | 修复方案包含：问题描述、影响分析、修复步骤、回滚方案 | P0 |
| FR-022 | 支持生成 IaC 代码（CloudFormation/Terraform） | P1 |
| FR-023 | 支持生成 AWS CLI 命令 | P0 |
| FR-024 | 提供修复风险评估和预期影响说明 | P0 |

#### 2.2.2 常见修复场景
| 场景 | 描述 | 修复方式 |
|------|------|----------|
| S3 公开访问 | S3 bucket 配置了公开访问权限 | 修改 bucket policy，启用 Block Public Access |
| 安全组开放 | 安全组对 0.0.0.0/0 开放敏感端口 | 收紧安全组规则 |
| 未加密存储 | EBS/RDS/S3 未启用加密 | 启用加密（可能需要数据迁移） |
| IAM 权限过大 | IAM 策略授予过多权限 | 最小权限原则优化策略 |
| 漏洞修复 | EC2/ECR 存在已知漏洞 | 补丁更新或镜像重建 |
| 异常活动 | GuardDuty 检测到异常行为 | 隔离资源、轮换凭证 |

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

### 2.4 修复执行

#### 2.4.1 执行能力
| 需求ID | 描述 | 优先级 |
|--------|------|--------|
| FR-050 | 审批通过后自动执行修复方案 | P0 |
| FR-051 | 支持 dry-run 模式预览修复效果 | P1 |
| FR-052 | 执行结果通过邮件通知管理员 | P0 |
| FR-053 | 修复失败时自动执行回滚 | P1 |
| FR-054 | 所有操作记录 CloudTrail 日志 | P0 |

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
                    ┌──────────────────────────────┐
                    │       Lambda Function        │
                    │    (Event Preprocessor)      │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Agent System (AgentCore + Strands)                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐              │
│  │  Orchestrator   │  │    Analyzer     │  │   Remediator    │              │
│  │     Agent       │◄─┤     Agent       │◄─┤     Agent       │              │
│  │                 │  │                 │  │                 │              │
│  │ - 任务分发      │  │ - Finding 分析  │  │ - 方案生成      │              │
│  │ - 流程协调      │  │ - 风险评估      │  │ - 代码生成      │              │
│  │ - 状态管理      │  │ - 上下文收集    │  │ - 执行修复      │              │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘              │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────┐            │
│  │                    Shared Components                         │            │
│  │  - Knowledge Base (修复方案知识库)                           │            │
│  │  - Tool Registry (AWS API 工具集)                            │            │
│  │  - Memory Store (会话状态存储)                               │            │
│  └─────────────────────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────────────────────┘
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
                    │   (Approval Endpoint)        │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │     Execution Engine         │
                    │   (Apply Remediation)        │
                    └──────────────────────────────┘
```

### 3.2 核心组件

#### 3.2.1 Agent 架构选型

**方案：多智能体协作架构**

| Agent | 职责 | 使用的 LLM 能力 |
|-------|------|-----------------|
| Orchestrator Agent | 任务调度、流程控制、状态管理 | 任务规划、决策 |
| Analyzer Agent | Finding 分析、风险评估、上下文收集 | 信息提取、推理 |
| Remediator Agent | 修复方案生成、代码生成、执行修复 | 代码生成、方案设计 |

**选择多智能体的理由：**
1. 关注点分离，每个 Agent 专注特定领域
2. 可独立扩展和优化各个 Agent
3. 支持并行处理多个 findings
4. 便于添加新的专业 Agent（如合规检查 Agent）

#### 3.2.2 技术栈

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| Agent 框架 | AWS Strands Agent | 官方支持，与 AWS 服务深度集成 |
| Agent 运行时 | AWS AgentCore | 提供 Agent 生命周期管理 |
| LLM | Amazon Bedrock (Claude) | 强大的推理和代码生成能力 |
| 事件处理 | EventBridge + Lambda | 事件驱动架构 |
| 状态存储 | DynamoDB | 审批状态、执行记录 |
| 通知服务 | Amazon SES | 邮件发送 |
| API 网关 | API Gateway | 审批回调端点 |
| 知识库 | Amazon Bedrock Knowledge Base | 修复方案知识库 |
| 日志监控 | CloudWatch | 运行监控和告警 |

### 3.3 数据流设计

```
1. Finding 产生
   Security Hub ─► EventBridge ─► Lambda (Filter & Enrich)

2. 分析阶段
   Lambda ─► Orchestrator Agent ─► Analyzer Agent
   Analyzer Agent:
     - 解析 Finding 详情
     - 查询相关资源配置
     - 评估影响范围
     - 确定修复优先级

3. 方案生成
   Analyzer Agent ─► Remediator Agent
   Remediator Agent:
     - 检索知识库中的修复模板
     - 生成定制化修复方案
     - 生成可执行代码/命令
     - 评估修复风险

4. 审批流程
   Remediator Agent ─► SES ─► Administrator
   Administrator ─► API Gateway ─► Lambda (Approval Handler)

5. 执行修复
   Approval Handler ─► Remediator Agent ─► AWS APIs
   Remediator Agent:
     - 执行修复操作
     - 验证修复结果
     - 更新 Finding 状态
     - 发送执行报告
```

---

## 4. 非功能需求

### 4.1 性能要求

| 指标 | 要求 | 说明 |
|------|------|------|
| 响应延迟 | < 5 分钟 | 从 Finding 产生到邮件发送 |
| 并发处理 | 支持 100+ findings/分钟 | 突发安全事件场景 |
| 方案生成 | < 2 分钟 | 单个 Finding 的方案生成时间 |

### 4.2 可用性要求

| 指标 | 要求 |
|------|------|
| SLA | 99.9% |
| 故障恢复 | RTO < 15 分钟 |
| 数据持久性 | 审批记录保留 90 天 |

### 4.3 安全要求

| 需求ID | 描述 | 优先级 |
|--------|------|--------|
| NFR-S01 | Agent 执行使用最小权限 IAM Role | P0 |
| NFR-S02 | 审批链接使用一次性 Token | P0 |
| NFR-S03 | 所有 API 调用启用 CloudTrail 审计 | P0 |
| NFR-S04 | 敏感数据（如凭证）不记录日志 | P0 |
| NFR-S05 | 支持 VPC 内部署（私有子网） | P1 |

### 4.4 可观测性要求

| 需求ID | 描述 | 优先级 |
|--------|------|--------|
| NFR-O01 | CloudWatch Metrics: 处理数量、成功率、延迟 | P0 |
| NFR-O02 | CloudWatch Logs: 结构化日志输出 | P0 |
| NFR-O03 | X-Ray: 分布式追踪 | P1 |
| NFR-O04 | CloudWatch Dashboard: 运营监控面板 | P1 |

---

## 5. 实现计划

### 5.1 阶段划分

#### Phase 1: MVP (最小可行产品)
- EventBridge + Lambda 事件处理框架
- 单 Agent 架构，支持 3-5 种常见 Finding 类型
- 基础邮件通知和审批流程
- AWS Config findings 支持

#### Phase 2: 扩展能力
- 多 Agent 协作架构
- 知识库集成
- GuardDuty、Inspector findings 支持
- 高级审批流程（多级审批）

#### Phase 3: 企业级功能
- 自定义修复规则引擎
- 与 ITSM 系统集成（ServiceNow 等）
- 多账户/组织支持
- 合规报告生成

### 5.2 依赖项

| 依赖 | 类型 | 说明 |
|------|------|------|
| AWS AgentCore | 服务 | Agent 运行时环境 |
| Strands Agent SDK | SDK | Agent 开发框架 |
| Amazon Bedrock | 服务 | LLM 推理能力 |
| Security Hub | 服务 | Finding 聚合 |
| 已验证的 SES 域名 | 配置 | 邮件发送 |

---

## 6. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| LLM 生成错误修复方案 | 高 | 人工审批 + 知识库约束 + dry-run 验证 |
| 修复操作导致服务中断 | 高 | 回滚机制 + 影响分析 + 维护窗口 |
| 审批邮件被忽略 | 中 | 超时提醒 + 升级机制 |
| AgentCore 服务限制 | 中 | 了解服务配额，必要时申请提升 |

---

## 7. 附录

### 7.1 术语表

| 术语 | 定义 |
|------|------|
| Finding | Security Hub 中的安全发现/告警 |
| Remediation | 修复/补救措施 |
| ASFF | AWS Security Finding Format |
| AgentCore | AWS 的 AI Agent 托管服务 |
| Strands | AWS 开源的 Agent 开发框架 |

### 7.2 参考资料

- [AWS Security Hub Documentation](https://docs.aws.amazon.com/securityhub/)
- [AWS Strands Agent Framework](https://github.com/strands-agents/strands-agents)
- [Amazon Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)
- [ASFF Syntax](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-findings-format.html)

---

## 8. 文档历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| 1.0 | 2025-01-28 | - | 初始版本 |
