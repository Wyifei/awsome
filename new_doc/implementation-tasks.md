# 容器漏洞修复功能 - 实施任务清单

## 任务状态说明

- [ ] 未开始
- [x] 已完成
- [~] 进行中

---

## 阶段 1: 基础设施准备

### T1.1 创建仓库元数据文件
- **状态**: [x] 已完成
- **描述**: 创建 AGENTS.md, container-inventory.json, SERVICE.yaml
- **文件**:
  - [x] `/AGENTS.md`
  - [x] `/.github/container-inventory.json`
  - [x] `/agent/agents/analyzer/SERVICE.yaml`
  - [x] `/agent/agents/remediator/SERVICE.yaml`
  - [x] `/agent/agents/validator/SERVICE.yaml`
  - [x] `/application/services/user-service/SERVICE.yaml`
  - [x] `/application/services/profile-service/SERVICE.yaml`
  - [x] `/application/services/notification-service/SERVICE.yaml`

### T1.2 配置 GitHub MCP Server (Secrets Manager + PAT)
- **状态**: [x] 已完成
- **描述**: 通过 Secrets Manager 存储 GitHub PAT，Agent 直接调用 GitHub 远程 MCP Server
- **架构**: Agent → Strands MCPClient → GitHub Remote MCP Server (`https://api.githubcopilot.com/mcp/`)

#### 子任务

| 子任务 | 状态 | 描述 |
|--------|------|------|
| T1.2.1 | [x] | 在 Secrets Manager 创建 GitHub PAT secret (`shara/github-pat`) |
| T1.2.2 | [x] | 更新 AgentCore Runtime IAM Role 添加 Secrets Manager 访问权限 |
| T1.2.3 | [x] | 创建 `github_mcp_client.py` 工具模块 |
| T1.2.4 | [x] | 测试 MCP 调用链路 |

#### 技术方案

**Secret 信息**:
- Name: `shara/github-pat`
- ARN: `arn:aws:secretsmanager:ap-northeast-1:870414140965:secret:shara/github-pat-OrZCIX`
- Region: `ap-northeast-1`

**MCP Client 实现**:

```python
import boto3
from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp.mcp_client import MCPClient

def get_github_pat() -> str:
    """从 Secrets Manager 获取 GitHub PAT"""
    client = boto3.client('secretsmanager', region_name='ap-northeast-1')
    response = client.get_secret_value(SecretId='shara/github-pat')
    return response['SecretString']

def create_github_mcp_client() -> MCPClient:
    """创建连接 GitHub 远程 MCP 的客户端"""
    pat = get_github_pat()

    def transport_factory():
        return streamablehttp_client(
            url="https://api.githubcopilot.com/mcp/",
            headers={"Authorization": f"Bearer {pat}"}
        )

    return MCPClient(transport_factory)
```

**IAM Policy** (已添加到 `007_ecr.tf`):

```hcl
resource "aws_iam_role_policy" "agentcore_secrets_manager" {
  name = "${local.name_prefix}-agentcore-secrets-manager"
  role = aws_iam_role.agentcore_runtime.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "GitHubPATAccess"
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = ["arn:aws:secretsmanager:${local.region}:${local.account_id}:secret:shara/github-pat-*"]
    }]
  })
}
```

#### 优势

| 方面 | 说明 |
|------|------|
| 实现复杂度 | ⭐ 简单，无需额外基础设施 |
| 安全性 | ✅ PAT 存储在 Secrets Manager |
| Token 轮换 | ✅ 可通过 Secrets Manager rotation |
| 直接调用 | ✅ Agent 直接调用远程 MCP，低延迟 |

---

## 阶段 2: Event Handler Lambda 改造

### T2.1 添加 Inspector API 调用逻辑
- **状态**: [x] 已完成
- **描述**: 实现 `get_container_findings()` 函数，调用 Inspector API 获取容器镜像所有漏洞
- **文件**: `agent/infra/lambda/event_handler/handler.py`
- **代码位置**: 新增函数
- **依赖**: boto3 inspector2 client

```python
def get_container_findings(repo_name: str, image_tag: str, image_digest: str, region: str) -> list:
    """获取指定容器镜像的所有 HIGH/CRITICAL 漏洞"""
    # TODO: 实现
    pass
```

### T2.2 实现漏洞聚合和过滤
- **状态**: [x] 已完成
- **描述**: 过滤只保留 HIGH/CRITICAL 漏洞，聚合到列表
- **文件**: `agent/infra/lambda/event_handler/handler.py`
- **依赖**: T2.1

```python
def aggregate_vulnerabilities(findings: list) -> dict:
    """聚合漏洞信息"""
    # TODO: 实现
    pass
```

### T2.3 修改容器 CVE 路由逻辑
- **状态**: [x] 已完成
- **描述**: 修改 `process_cve_finding()` 函数，容器 CVE 改为调用 Analyzer Agent
- **文件**: `agent/infra/lambda/event_handler/handler.py`
- **代码位置**: 约 327-342 行
- **依赖**: T2.2

### T2.4 添加 remediation_type 到 task 数据
- **状态**: [x] 已完成
- **描述**: 在 task 创建时添加 `remediation_type: "github_pr"`
- **文件**: `agent/infra/lambda/event_handler/handler.py`
- **依赖**: T2.3

### T2.5 实现 GitHub PR 审批邮件模板
- **状态**: [x] 已完成
- **描述**: 添加 `format_github_pr_approval_section()` 函数
- **文件**: `agent/infra/lambda/event_handler/handler.py`
- **代码位置**: 约 1288 行附近
- **依赖**: T2.4

---

## 阶段 3: Analyzer Agent 改造

### T3.1 添加 search_container_inventory 工具
- **状态**: [x] 已完成
- **描述**: 创建工具读取 container-inventory.json 并搜索匹配服务
- **文件**: `agent/agents/shared/tools/github_mcp_client.py`
- **依赖**: T1.1
- **实现**: 使用 GitHub MCP Server 的 get_file_contents 读取 container-inventory.json

### T3.2 添加 get_service_metadata 工具
- **状态**: [x] 已完成
- **描述**: 创建工具读取 SERVICE.yaml
- **文件**: `agent/agents/shared/tools/github_mcp_client.py`
- **依赖**: T1.1
- **实现**: 使用 GitHub MCP Server 读取并解析 SERVICE.yaml

### T3.3 添加 GitHub PR 工作流 Prompt 片段
- **状态**: [x] 已完成
- **描述**: 在 ANALYZER_SYSTEM_PROMPT 中添加 github_pr 工作流指导
- **文件**: `agent/agents/analyzer/agent.py`
- **代码位置**: ANALYZER_SYSTEM_PROMPT 变量 - "GitHub PR 工作流" 章节
- **实现内容**:
  - 工具调用顺序指导
  - GitHub PR 专用输出格式 (service_info, vulnerabilities, file_changes, pr_metadata)
  - 字段说明和注意事项

### T3.4 修改分析输出格式
- **状态**: [x] 已完成
- **描述**: 支持 file_changes 和 pr_metadata 输出
- **文件**: `agent/agents/analyzer/agent.py`
- **实现**: 在 ANALYZER_SYSTEM_PROMPT 中定义完整的 GitHub PR 输出格式

### T3.5 添加条件逻辑
- **状态**: [x] 已完成
- **描述**: 根据 remediation_type 选择分析路径
- **文件**: `agent/agents/analyzer/agent.py`
- **实现**:
  - 添加 `run_container_analyzer()` 函数，专门处理 github_pr 类型
  - 工具列表包含 GitHub 工具 (search_container_inventory, get_service_metadata, read_github_file)
  - 导出更新到 `analyzer/__init__.py`

---

## 阶段 4: Remediator Agent 改造

### T4.1 添加 read_github_file 工具
- **状态**: [x] 已完成
- **描述**: 使用 GitHub MCP 读取仓库文件
- **文件**: `agent/agents/shared/tools/github_mcp_client.py`
- **实现**: 通过 GitHub MCP Server `get_file_contents` 工具实现

### T4.2 添加 create_pull_request 工具
- **状态**: [x] 已完成
- **描述**: 使用 GitHub MCP 创建 PR
- **文件**: `agent/agents/shared/tools/github_mcp_client.py`
- **实现**: 集成 `create_github_branch`, `push_files_to_github`, `create_pull_request` 三个工具

### T4.3 添加 save_pr_result 工具
- **状态**: [x] 已完成
- **描述**: 保存 PR 信息到 Memory STM
- **文件**: `agent/agents/shared/tools/memory_tools.py`
- **实现**: 保存 pr_info 和 files_changed 到 Memory Session

### T4.4 添加 GitHub PR 工作流 Prompt 片段
- **状态**: [x] 已完成
- **描述**: 在 REMEDIATOR_SYSTEM_PROMPT 中添加 "GitHub PR 工作流" 章节
- **文件**: `agent/agents/remediator/agent.py`
- **实现**: 添加工具调用顺序指导，创建 `run_github_pr_remediator()` 函数

### T4.5 修改 invoke_validator_agent 调用
- **状态**: [x] 已完成
- **描述**: 添加 `remediation_type` 参数支持 github_pr 模式
- **文件**: `agent/agents/shared/tools/a2a_tools.py`
- **实现**: A2A payload 包含 remediation_type 字段

---

## 阶段 5: Validator Agent 改造

### T5.1 添加 get_pr_result 工具
- **状态**: [x] 已完成
- **描述**: 从 Memory STM 获取 PR 信息
- **文件**: `agent/agents/shared/tools/memory_tools.py`
- **实现**: 获取 pr_info 和 files_changed 供验证使用

### T5.2 添加 verify_pr_created 工具
- **状态**: [x] 已完成
- **描述**: 使用 GitHub MCP 验证 PR 状态
- **文件**: `agent/agents/shared/tools/github_mcp_client.py`
- **实现**: 通过 `get_pull_request` 工具验证 PR 存在且状态正确

### T5.3 添加 verify_pr_content 工具
- **状态**: [x] 已完成
- **描述**: 验证 PR 文件变更
- **文件**: `agent/agents/shared/tools/github_mcp_client.py`
- **实现**: 通过 `get_pull_request_files` 工具获取 PR 文件列表并验证

### T5.4 添加 GitHub PR 工作流 Prompt 片段
- **状态**: [x] 已完成
- **描述**: 在 VALIDATOR_SYSTEM_PROMPT 中添加 "GitHub PR 工作流验证" 章节
- **文件**: `agent/agents/validator/agent.py`
- **实现**: 添加 PR 验证流程指导，创建 `run_github_pr_validator()` 函数

### T5.5 修改 trigger_result_email 支持 PR 结果
- **状态**: [x] 已完成
- **描述**: 添加 `remediation_type` 和 `pr_info` 参数
- **文件**: `agent/agents/shared/tools/validator_tools.py`
- **实现**: 支持 github_pr_result 邮件类型，包含 includes_pr_link 标志

---

## 阶段 6: Approval Handler Lambda 改造

### T6.1 实现 GitHub PR 结果邮件模板
- **状态**: [x] 已完成
- **描述**: 添加 `format_github_pr_result_email()` 函数
- **文件**: `agent/infra/lambda/approval_handler/handler.py`
- **实现**: 完整的 HTML 邮件模板，包含:
  - 任务信息 (task_id, 修复类型, 镜像)
  - PR 信息 (编号, 标题, 状态, PR 链接按钮)
  - 变更文件列表 (带文件类型图标)
  - 验证结果 (pr_verified, files_verified)
  - 下一步操作说明

### T6.2 修改 handle_send_result_email 支持条件渲染
- **状态**: [x] 已完成
- **描述**: 根据 `remediation_type` 选择邮件模板
- **文件**: `agent/infra/lambda/approval_handler/handler.py`
- **实现**:
  - 提取 `remediation_type` 和 `pr_info` 参数
  - github_pr 类型调用 `format_github_pr_result_email()`
  - aws_api 类型调用原有的 `format_result_email_body()`
  - 不同类型使用不同的邮件主题格式

---

## 阶段 7: 测试和验证

### T7.1 编写 Event Handler 单元测试
- **状态**: [ ] 未开始
- **描述**: 测试 Inspector API 调用、漏洞聚合、路由逻辑
- **文件**: `agent/infra/lambda/event_handler/test_handler.py` (新建)
- **依赖**: T2.5

### T7.2 编写 Agent 工具单元测试
- **状态**: [ ] 未开始
- **描述**: 测试新增的 GitHub 工具
- **文件**: `agent/agents/shared/tools/test_github_tools.py` (新建)
- **依赖**: T3.5, T4.5, T5.5

### T7.3 端到端集成测试 (本地)
- **状态**: [ ] 未开始
- **描述**: Docker Compose 环境下的完整流程测试
- **依赖**: T6.2

### T7.4 端到端集成测试 (AWS)
- **状态**: [ ] 未开始
- **描述**: AWS 环境下的完整流程测试
- **依赖**: T7.3

---

## 进度跟踪

| 阶段 | 任务数 | 已完成 | 进度 |
|------|--------|--------|------|
| 阶段 1 | 2 | 2 | 100% ✅ |
| 阶段 2 | 5 | 5 | 100% ✅ |
| 阶段 3 | 5 | 5 | 100% ✅ |
| 阶段 4 | 5 | 5 | 100% ✅ |
| 阶段 5 | 5 | 5 | 100% ✅ |
| 阶段 6 | 2 | 2 | 100% ✅ |
| 阶段 7 | 4 | 0 | 0% |
| **总计** | **28** | **24** | **86%** |

---

## 下一步行动

1. ✅ **阶段 1 已完成**: 基础设施准备 (仓库元数据、GitHub MCP 配置)
2. ✅ **阶段 2 已完成**: Event Handler Lambda 改造 (Inspector API、漏洞聚合、路由逻辑、审批邮件)
3. ✅ **阶段 3 已完成**: Analyzer Agent 改造 (GitHub PR 工作流 Prompt、输出格式、run_container_analyzer)
4. ✅ **阶段 4 已完成**: Remediator Agent 改造 (GitHub 工具、save_pr_result、PR 工作流 Prompt)
5. ✅ **阶段 5 已完成**: Validator Agent 改造 (get_pr_result、PR 验证、trigger_result_email PR 支持)
6. ✅ **阶段 6 已完成**: Approval Handler Lambda 改造 (GitHub PR 邮件模板、条件渲染)
7. **开始阶段 7**: 测试和验证
   - T7.1: 编写 Event Handler 单元测试
   - T7.2: 编写 Agent 工具单元测试
   - T7.3: 端到端集成测试 (本地 Docker Compose)
   - T7.4: 端到端集成测试 (AWS 环境)

---

## 更新记录

| 日期 | 更新内容 |
|------|----------|
| 2025-02-04 | 初始版本，创建任务清单 |
| 2025-02-04 | 更新 T1.2 架构为 Secrets Manager + PAT 方案；完成 T1.2.1 (创建 secret) 和 T1.2.2 (IAM Policy) |
| 2026-02-04 | 完成 T1.2.3 (创建 github_mcp_client.py) 和 T1.2.4 (测试 MCP 调用链路)；阶段 1 完成 100% |
| 2026-02-04 | 完成阶段 2: T2.1-T2.5 (Inspector API, 漏洞聚合, 容器CVE路由, remediation_type, PR审批邮件)；总进度 25% |
| 2026-02-04 | 完成阶段 3: T3.1-T3.5 (Analyzer Agent 改造)；添加 GitHub PR 工作流 Prompt，run_container_analyzer()；总进度 43% |
| 2026-02-04 | 完成阶段 4: T4.1-T4.5 (Remediator Agent 改造)；添加 save_pr_result, GitHub PR 工作流 Prompt，run_github_pr_remediator() |
| 2026-02-04 | 完成阶段 5: T5.1-T5.5 (Validator Agent 改造)；添加 get_pr_result, PR 验证工具，trigger_result_email PR 支持 |
| 2026-02-04 | 完成阶段 6: T6.1-T6.2 (Approval Handler 改造)；添加 format_github_pr_result_email()，条件渲染邮件模板；总进度 86% |
