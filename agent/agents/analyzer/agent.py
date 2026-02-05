"""
Analyzer Agent - Phase 1 分析智能体

负责分析 Security Hub Finding 并生成修复方案描述（不生成代码）。
支持两种修复类型:
- aws_api: AWS 配置类问题，通过 AWS API 直接修复
- github_pr: 容器漏洞，通过 GitHub PR 修复源代码
"""
import logging
from typing import Optional

from strands import Agent
from strands.models import BedrockModel

from shared.config import get_config, ANALYZER_MODEL_CONFIG
from shared.tools.asr_playbook import fetch_asr_playbook
from shared.tools.memory_tools import (
    search_similar_findings,
    save_analysis_result,
    set_memory_session,
)
from shared.tools.aws_resources import get_resource_config
from shared.tools.github_mcp_client import (
    search_container_inventory,
    get_service_metadata,
    read_github_file,
)

logger = logging.getLogger(__name__)

# ============================================================
# AWS API 模式 System Prompt (标准 Security Hub 配置修复)
# ============================================================
AWS_API_ANALYZER_SYSTEM_PROMPT = """# 角色
你是 SHARA (Security Hub Auto-Remediation Agent) 的分析智能体。
你的任务是分析 AWS Security Hub 安全发现并生成修复方案描述。

# 重要约束
- 你只生成文字描述，不生成可执行代码
- 代码生成在人工审批后的第二阶段进行
- 你的输出将通过邮件发送给管理员审批

# ⚠️ 强制要求：工具调用顺序
你必须按以下顺序调用工具，不允许跳过任何步骤：

**第一步（强制）: get_resource_config** - 验证资源是否存在
**第二步: fetch_asr_playbook** - 获取 ASR 修复方案
**第三步: search_similar_findings** - 搜索相似经验
**第四步（强制）: save_analysis_result** - 保存分析结果供 Phase 2 使用

# 分析流程

## 步骤 1: 解析 Finding
从 ASFF 格式中提取：
- Control ID (如 SNS.1, S3.1)
- Resources[].Id (完整 ARN)
- Resources[].Type (如 AwsSnsTopic, AwsS3Bucket)
- Region
- Severity

## 步骤 2: 【强制】验证资源存在性
**⚠️ 这是第一个必须调用的工具，不可跳过！**

立即调用 get_resource_config 工具：
```
get_resource_config(
  resource_arn="<Finding 中的 Resources[].Id>",
  resource_type="<Finding 中的 Resources[].Type>"
)
```

根据返回结果：
- status="found": 资源存在，将 properties 记录到 current_state
- status="not_found": 资源已删除，current_state 设为 {"status": "RESOURCE_NOT_FOUND"}
- status="error": 查询失败，记录错误信息

## 步骤 3: 获取 ASR Playbook
调用 fetch_asr_playbook 工具获取预定义修复方案

## 步骤 4: 搜索相似经验
调用 search_similar_findings 工具查找历史修复经验

## 步骤 5: 风险评估
综合评估风险，考虑：
- 资源是否存在（不存在则风险降低）
- 数据敏感性和暴露程度
- 修复操作的潜在影响
- 是否具有破坏性

## 步骤 6: 生成 JSON 输出
生成分析结果 JSON（格式见下方）。

## 步骤 7: 【强制】保存分析结果
**⚠️ 这是必须执行的最后一步，不可跳过！**

调用 save_analysis_result 工具保存分析结果，供 Phase 2 (Remediator) 使用：
```
save_analysis_result(
  task_id="<任务 ID>",
  analysis=<分析结果 JSON 对象>,
  remediation_description="<修复方案描述>",
  finding=<原始 Finding 数据>,
  asr_playbook=<fetch_asr_playbook 的返回结果>,
  top_experience=<search_similar_findings 返回的第一条结果>
)
```

# 输出格式
必须返回以下结构的 JSON 对象：

```json
{
  "analysis": {
    "control_id": "SNS.1",
    "finding_type": "SNS Topic 未启用加密",
    "resource_type": "AwsSnsTopic",
    "resource_id": "arn:aws:sns:...",
    "resource_exists": true,
    "current_state": {"KmsMasterKeyId": null},
    "risk_assessment": {
      "level": "HIGH",
      "factors": ["消息可能包含敏感信息"],
      "justification": "..."
    }
  },
  "asr_match": {
    "matched": true,
    "playbook_id": "ASR_SNS_1",
    "confidence": 1.0,
    "message": "基于 Control ID 精确匹配 ASR Playbook"
  },
  "similar_experiences": [...],
  "remediation": {
    "can_remediate": true,
    "cannot_remediate_reason": null,
    "summary": "为 SNS Topic 启用 KMS 加密",
    "description": "...",
    "prerequisites": [],
    "agent_actions": [],
    "post_actions": [],
    "estimated_impact": "LOW",
    "rollback_available": true,
    "is_destructive": false
  }
}
```

# 修复步骤分类说明
- **prerequisites**: 审批前人工需要确认的前置条件
- **agent_actions**: Agent 将通过 AWS API 自动执行的操作
- **post_actions**: 修复完成后人工需要处理的后续操作

# can_remediate 字段说明
- **true**: AWS 配置类问题，有 ASR Playbook，可通过 AWS API 修复
- **false**: 资源不存在、软件漏洞、需要手动干预、不支持的资源类型

# similar_experiences 格式化要求
将 search_similar_findings 返回的英文内容翻译并格式化为：
```json
{
  "type": "episode",
  "similarity_score": 0.51,
  "title": "S3 Block Public Access 配置修复",
  "problem": "问题描述（中文）",
  "solution": "解决方案（中文）",
  "result": "修复结果（中文）"
}
```

# 重要指南
- 【强制】必须调用 get_resource_config 和 save_analysis_result
- 【强制】必须设置 can_remediate 字段
- 绝不在响应中包含可执行代码
"""

# ============================================================
# GitHub PR 模式 System Prompt (容器漏洞修复)
# ============================================================
GITHUB_PR_ANALYZER_SYSTEM_PROMPT = """# 角色
你是 SHARA (Security Hub Auto-Remediation Agent) 的分析智能体。
你的任务是分析容器镜像漏洞并生成修复方案。

# 重要约束
- 你只负责分析漏洞和建议文件修改
- PR 创建由 Remediator 负责，你不需要生成 PR 标题/描述
- 所有漏洞将在一个 PR 中统一修复

# ⚠️ 强制要求：工具调用顺序

**第一步: search_container_inventory** - 查找容器对应的服务目录
**第二步: get_service_metadata** - 读取服务元数据
**第三步: read_github_file** - 读取需要修改的文件
**第四步: 分析漏洞和生成修复方案**
**第五步（强制）: save_analysis_result** - 保存分析结果

# 输出格式 (GitHub PR 模式)

```json
{
  "analysis": {
    "control_id": null,
    "finding_type": "容器镜像漏洞",
    "resource_type": "AwsEcrContainerImage",
    "resource_id": "arn:aws:ecr:...",
    "resource_exists": true,
    "current_state": {
      "image_digest": "sha256:...",
      "repository": "my-service",
      "vulnerabilities_count": 5
    },
    "risk_assessment": {
      "level": "HIGH",
      "factors": ["包含 3 个 CRITICAL 漏洞"],
      "justification": "..."
    }
  },
  "service_info": {
    "name": "my-service",
    "path": "application/services/my-service",
    "language": "python",
    "dockerfile": "Dockerfile",
    "dependency_file": "requirements.txt",
    "github_owner": "owner",
    "github_repo": "repo"
  },
  "vulnerabilities": [
    {
      "cve_id": "CVE-2024-12345",
      "severity": "CRITICAL",
      "package_name": "requests",
      "installed_version": "2.25.0",
      "fixed_version": "2.32.0",
      "description": "远程代码执行漏洞"
    }
  ],
  "file_changes": [
    {
      "path": "application/services/my-service/requirements.txt",
      "change_type": "modify",
      "current_content": "# 原始完整文件内容\nrequests==2.25.0\nurllib3==1.26.0\nboto3>=1.34.0",
      "suggested_content": "# 修改后的完整文件内容 (必须是完整文件！)\nrequests>=2.32.0\nurllib3>=2.0.0\nboto3>=1.34.0",
      "description": "升级 requests 和 urllib3 到安全版本"
    }
  ],
  "remediation": {
    "can_remediate": true,
    "remediation_type": "github_pr",
    "summary": "通过 GitHub PR 修复容器镜像漏洞",
    "description": "升级存在漏洞的依赖包到安全版本",
    "prerequisites": ["确认升级不会破坏应用兼容性"],
    "estimated_impact": "LOW",
    "rollback_available": true,
    "is_destructive": false
  }
}
```

# 注意事项
1. **必须先确认服务存在**: search_container_inventory 必须返回 found: true
2. **如果服务不在清单中**: 设置 can_remediate: false
3. **⚠️ file_changes.suggested_content 必须是完整文件内容**:
   - 不是单行修改，是整个文件的内容
   - Remediator 会直接用这个内容创建 PR
   - 先用 read_github_file 读取原文件，修改后作为 suggested_content
4. **所有漏洞合并处理**: 不要为每个漏洞单独分析

# 重要指南
- 【强制】必须调用 save_analysis_result 保存分析结果
- 【强制】service_info 中必须包含 github_owner 和 github_repo
- Remediator 将负责创建 PR（标题、描述、分支名等）
"""

# 向后兼容：保留原变量名
ANALYZER_SYSTEM_PROMPT = AWS_API_ANALYZER_SYSTEM_PROMPT


def create_analyzer_agent(
    task_id: str,
    memory_id: str,
    session_id: str,
    region: Optional[str] = None,
    actor_id: Optional[str] = None,
    mcp_tools: Optional[list] = None,
    remediation_type: str = "aws_api"
) -> Agent:
    """创建 Analyzer Agent 实例。

    Args:
        task_id: 任务 ID
        memory_id: AgentCore Memory ID
        session_id: Memory Session ID (从 Lambda 传入，确保与 Phase 2 共享)
        region: AWS Region (可选，默认从环境变量获取)
        actor_id: Actor ID (可选，默认使用 task_id)
        mcp_tools: AWS MCP Server 提供的工具列表 (可选)
        remediation_type: 修复类型 ("aws_api" 或 "github_pr")，决定使用哪个 System Prompt

    Returns:
        Agent: 配置好的 Analyzer Agent
    """
    config = get_config()
    region = region or config.region

    # 使用 AWS 账户 ID 作为 actor_id
    # 这样同一账户的所有修复经验可以跨 session 共享检索
    if not actor_id:
        logger.warning("actor_id not provided, using task_id as fallback")
        actor_id = f"task-{task_id}"

    # Use provided memory_id or fall back to config
    effective_memory_id = memory_id or config.memory_id

    # 配置 Memory Session Manager
    session_manager = None

    if not effective_memory_id:
        logger.warning("AGENTCORE_MEMORY_ID 未配置，Memory 功能将不可用")
    else:
        try:
            from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager
            from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig, RetrievalConfig

            # 构建检索配置 - 命名空间需要匹配实际存储路径
            # Reflections 存储在 /remediation/actors/{actorId}/ 下
            retrieval_namespaces = {}
            if actor_id:
                retrieval_namespaces[f"/remediation/actors/{actor_id}/"] = RetrievalConfig(
                    top_k=5,
                    relevance_score=0.5
                )

            memory_config = AgentCoreMemoryConfig(
                memory_id=effective_memory_id,  # 使用 effective_memory_id
                actor_id=actor_id,
                session_id=session_id,  # 使用传入的 session_id
                retrieval_config=retrieval_namespaces if retrieval_namespaces else None
            )

            session_manager = AgentCoreMemorySessionManager(
                agentcore_memory_config=memory_config,
                region_name=region
            )

            # 设置全局 memory session 供工具使用
            # 传入 session_manager，会自动从中提取 memory_client 和 config
            set_memory_session(session_manager)

            logger.info(f"已初始化 Memory session: session_id={session_id}, actor_id={actor_id}")

            # NOTE: 由于 bedrock-agentcore SDK 1.2.0 与 strands-agents SDK 1.24.0 的兼容性问题，
            # AgentCoreMemorySessionManager.list_messages() 在处理旧格式数据时会报错：
            # "SessionMessage.__init__() missing 2 required positional arguments: 'message' and 'message_id'"
            # 因此我们不将 session_manager 传给 Agent，而是只用它来设置 _memory_session。
            # 这样 Agent 仍然可以通过 Memory 工具使用 Memory，
            # 但 Agent 不会尝试自动加载历史消息（避免触发这个 bug）。
            session_manager = None  # 不传给 Agent，避免 list_messages bug

        except ImportError:
            logger.warning("AgentCore Memory SDK 未安装，将跳过 Memory 功能")
        except Exception as e:
            logger.warning(f"初始化 Memory session 失败: {e}")

    # 配置 LLM
    # streaming=False 用于绕过 strands SDK 1.24.0 中的流式处理 bug
    # 该 bug 在处理包含整数值的 JSON 工具输入时会失败
    model = BedrockModel(
        model_id=ANALYZER_MODEL_CONFIG.model_id,
        temperature=ANALYZER_MODEL_CONFIG.temperature,
        max_tokens=ANALYZER_MODEL_CONFIG.max_tokens,
        region_name=region,
        streaming=False
    )

    # 根据 remediation_type 选择 System Prompt 和工具
    if remediation_type == "github_pr":
        # GitHub PR 模式 - 容器漏洞修复
        system_prompt = GITHUB_PR_ANALYZER_SYSTEM_PROMPT
        tools = [
            search_container_inventory,  # 搜索容器清单
            get_service_metadata,  # 读取服务元数据
            read_github_file,  # 读取 GitHub 文件
            save_analysis_result,  # 保存分析结果
        ]
        logger.info("Using GitHub PR mode - container vulnerability analysis")
    else:
        # AWS API 模式 - 标准 Security Hub 配置修复
        system_prompt = AWS_API_ANALYZER_SYSTEM_PROMPT
        tools = [
            get_resource_config,  # 验证资源存在性
            fetch_asr_playbook,  # 获取 ASR Playbook
            search_similar_findings,  # 搜索相似经验
            save_analysis_result,  # 保存分析结果
        ]
        logger.info("Using AWS API mode - standard Security Hub remediation")

        # AWS API 模式下添加 MCP 工具 (如果可用)
        if mcp_tools:
            tools.extend(mcp_tools)
            logger.info(f"Added {len(mcp_tools)} AWS MCP tools to agent")

    # 创建 Agent
    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        tools=tools,
        session_manager=session_manager,
    )

    logger.info(f"Created Analyzer Agent for task {task_id}")
    return agent


def run_analyzer(
    agent: Agent,
    finding: dict,
    control_id: str,
    task_id: str,
    remediation_type: str = "auto",
    github_owner: str = "",
    github_repo: str = "",
    # 容器 CVE 模式的额外参数 (从 Lambda 传入的预聚合数据)
    container_details: dict = None,
    vulnerabilities: list = None,
    vulnerability_summary: dict = None
) -> dict:
    """运行 Analyzer Agent 分析 Finding。

    Args:
        agent: Analyzer Agent 实例
        finding: Security Hub Finding (ASFF 格式)
        control_id: Control ID
        task_id: 任务 ID
        remediation_type: 修复类型 ("auto" 或 "github_pr")
        github_owner: GitHub 用户/组织 (github_pr 模式必需)
        github_repo: GitHub 仓库名 (可选，留空则动态搜索)
        container_details: 容器镜像详情 (github_pr 模式，从 Lambda 传入)
        vulnerabilities: 预聚合的漏洞列表 (github_pr 模式，从 Lambda 传入)
        vulnerability_summary: 漏洞摘要 (github_pr 模式，从 Lambda 传入)

    Returns:
        dict: 分析结果
    """
    import json

    # 如果是 github_pr 模式，调用专门的容器分析函数
    if remediation_type == "github_pr":
        return _run_github_pr_analyzer(
            agent, finding, task_id, github_owner, github_repo,
            container_details=container_details,
            vulnerabilities=vulnerabilities,
            vulnerability_summary=vulnerability_summary
        )

    # 以下是 aws_api 模式（默认）
    # 提取资源信息供 prompt 使用
    resources = finding.get('Resources', [{}])
    resource_arn = resources[0].get('Id', '') if resources else ''
    resource_type = resources[0].get('Type', '') if resources else ''

    prompt = f"""
Analyze this Security Hub Finding and generate a remediation description:

**Task ID:** {task_id}
**Control ID:** {control_id}

**Finding (ASFF Format):**
```json
{json.dumps(finding, indent=2, default=str)}
```

**⚠️ 必须按以下顺序执行工具调用:**

**步骤 1 [强制]: 验证资源存在性**
立即调用 get_resource_config 工具:
```
get_resource_config(
  resource_arn="{resource_arn}",
  resource_type="{resource_type}"
)
```

**步骤 2: 获取 ASR Playbook**
调用 fetch_asr_playbook 工具获取 Control ID: {control_id} 的修复方案
**保存返回结果**，步骤 5 需要用到

**步骤 3: 搜索相似经验**
调用 search_similar_findings 工具
将返回结果中**相似度 >= 0.5**的经验加工为固定格式:
- 从英文 content 中提取关键信息
- 翻译并格式化为: title, problem, solution, result (全部中文)
- 保留原始 similarity_score
**同时记录分数最高的那条**，步骤 5 的 top_experience 参数需要用到

**步骤 4: 风险评估并生成 JSON 输出**
如果步骤 3 返回了相似经验，参考其中的修复方法和经验教训
**重要**: similar_experiences 数组中的每条记录必须包含: similarity_score, title, problem, solution, result

**步骤 5 [强制]: 保存分析结果**
调用 save_analysis_result 工具:
- task_id: {task_id}
- analysis: 步骤 4 生成的分析 JSON
- remediation_description: 修复方案描述
- finding: 传递完整的原始 Finding 数据 (上面的 ASFF JSON)
- asr_playbook: **步骤 2 的 fetch_asr_playbook 返回结果** (如果 matched=true)
- top_experience: **步骤 3 返回的第一条（最高分）经验** (如果有结果)

Remember: Generate DESCRIPTIONS only, not executable code. Return result as JSON format.
"""

    logger.info(f"Running Analyzer Agent for task {task_id}, control {control_id}")

    try:
        result = agent(prompt)

        # 正确提取响应文本
        response_text = ""
        if hasattr(result, 'message'):
            msg = result.message
            # Strands Agent 返回的 message 可能是 dict 格式
            if isinstance(msg, dict):
                content = msg.get('content', [])
                if content and isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and 'text' in item:
                            response_text += item['text']
                        elif isinstance(item, str):
                            response_text += item
            elif isinstance(msg, str):
                response_text = msg
            else:
                response_text = str(msg)
        else:
            response_text = str(result)

        # 尝试从响应中提取 JSON 结构
        analysis_data = _extract_json_from_response(response_text)

        logger.info(f"Analyzer completed for task {task_id}")

        return {
            "success": True,
            "task_id": task_id,
            "analysis": analysis_data.get('analysis', {}),
            "asr_match": analysis_data.get('asr_match', {}),
            "similar_experiences": analysis_data.get('similar_experiences', []),
            "remediation": analysis_data.get('remediation', {}),
            "raw_response": response_text  # 保留原始响应用于调试
        }

    except Exception as e:
        logger.exception(f"Analyzer failed for task {task_id}: {e}")
        return {
            "success": False,
            "task_id": task_id,
            "error": str(e)
        }


def _run_github_pr_analyzer(
    agent: Agent,
    finding: dict,
    task_id: str,
    github_owner: str,
    github_repo: str = "",
    # 从 Lambda 传入的预聚合数据 (优先使用)
    container_details: dict = None,
    vulnerabilities: list = None,
    vulnerability_summary: dict = None
) -> dict:
    """GitHub PR 模式的分析入口函数。

    优先使用 Lambda 传入的预聚合数据，否则从单个 Finding 中提取。

    Args:
        agent: Analyzer Agent 实例
        finding: Security Hub Finding (ASFF 格式)
        task_id: 任务 ID
        github_owner: GitHub 用户/组织
        github_repo: GitHub 仓库名 (可选，留空则动态搜索)
        container_details: 容器镜像详情 (从 Lambda 传入，已包含完整 repo path)
        vulnerabilities: 预聚合的漏洞列表 (从 Lambda 传入，包含所有 HIGH/CRITICAL)
        vulnerability_summary: 漏洞摘要 (从 Lambda 传入)

    Returns:
        dict: 分析结果
    """
    # 优先使用 Lambda 传入的预聚合数据
    if vulnerabilities and container_details:
        logger.info(f"Using pre-aggregated data from Lambda: {len(vulnerabilities)} vulnerabilities")
        container_info = {
            'repo_name': container_details.get('ecr_repository', ''),
            'image_tag': container_details.get('image_tag', ''),
            'image_digest': container_details.get('image_digest', '')
        }
        # 转换漏洞格式以匹配 run_container_analyzer 的期望
        aggregated_vulnerabilities = []
        for vuln in vulnerabilities:
            aggregated_vulnerabilities.append({
                'cve_id': vuln.get('cve_id', ''),
                'severity': vuln.get('severity', 'UNKNOWN'),
                'package_name': vuln.get('package_name', ''),
                'installed_version': vuln.get('current_version', ''),
                'fixed_version': vuln.get('fixed_version', ''),
                'description': vuln.get('description', ''),
                'cvss_score': vuln.get('cvss_score', 0.0),
                'exploit_available': vuln.get('exploit_available', False)
            })
        logger.info(f"Container info: {container_info}, vulnerabilities: {len(aggregated_vulnerabilities)}")
    else:
        # 降级: 从单个 Finding 中提取 (只会有 1 个漏洞)
        logger.warning("No pre-aggregated data from Lambda, extracting from single Finding (will only get 1 CVE)")

        # 从 Finding 中提取容器信息
        resources = finding.get('Resources', [{}])
        resource = resources[0] if resources else {}
        resource_arn = resource.get('Id', '')

        # 解析 ECR ARN: arn:aws:ecr:region:account:repository/name/image/sha256:digest
        container_info = {
            'repo_name': '',
            'image_tag': '',
            'image_digest': ''
        }

        if 'ecr' in resource_arn.lower():
            # 从 ARN 中提取仓库名 (完整路径)
            if '/repository/' in resource_arn:
                after_repo = resource_arn.split('/repository/')[-1]
                if '/image/' in after_repo:
                    container_info['repo_name'] = after_repo.split('/image/')[0]
            if 'sha256:' in resource_arn:
                container_info['image_digest'] = 'sha256:' + resource_arn.split('sha256:')[-1]

        # 从 Finding 中提取漏洞信息 (只会有 1 个)
        aggregated_vulnerabilities = []

        # 检查是否有 Vulnerabilities 数组 (Inspector v2 格式)
        vulns = finding.get('Vulnerabilities', [])
        for vuln in vulns:
            vuln_info = {
                'cve_id': vuln.get('Id', ''),
                'severity': finding.get('Severity', {}).get('Label', 'UNKNOWN'),
                'package_name': '',
                'installed_version': '',
                'fixed_version': '',
                'description': vuln.get('Description', '') or finding.get('Description', '')
            }

            # 提取包信息
            packages = vuln.get('VulnerablePackages', [])
            if packages:
                pkg = packages[0]
                vuln_info['package_name'] = pkg.get('Name', '')
                vuln_info['installed_version'] = pkg.get('Version', '')
                vuln_info['fixed_version'] = pkg.get('FixedInVersion', '')

            if vuln_info['cve_id']:
                aggregated_vulnerabilities.append(vuln_info)

        # 如果 Vulnerabilities 为空，尝试从 ProductFields 提取
        if not aggregated_vulnerabilities:
            product_fields = finding.get('ProductFields', {})
            cve_id = (
                finding.get('Title', '').split(' - ')[0] if ' - ' in finding.get('Title', '')
                else product_fields.get('CVE', '')
            )
            if cve_id:
                aggregated_vulnerabilities.append({
                    'cve_id': cve_id,
                    'severity': finding.get('Severity', {}).get('Label', 'UNKNOWN'),
                    'package_name': product_fields.get('PackageName', ''),
                    'installed_version': product_fields.get('InstalledVersion', ''),
                    'fixed_version': product_fields.get('FixedVersion', ''),
                    'description': finding.get('Description', '')
                })

        logger.info(f"Extracted container info: {container_info}, vulnerabilities: {len(aggregated_vulnerabilities)}")

    # 调用容器分析器
    return run_container_analyzer(
        agent=agent,
        finding=finding,
        task_id=task_id,
        aggregated_vulnerabilities=aggregated_vulnerabilities,
        container_info=container_info,
        github_owner=github_owner,
        github_repo=github_repo  # 如果有值则直接使用，否则由 Agent 动态搜索
    )


def run_container_analyzer(
    agent: Agent,
    finding: dict,
    task_id: str,
    aggregated_vulnerabilities: list,
    container_info: dict,
    github_owner: str = "Wyifei",
    github_repo: str = "awsome"
) -> dict:
    """运行 Analyzer Agent 分析容器漏洞 Finding。

    Args:
        agent: Analyzer Agent 实例
        finding: Security Hub Finding (ASFF 格式)
        task_id: 任务 ID
        aggregated_vulnerabilities: 聚合后的漏洞列表
        container_info: 容器信息 (repo_name, image_tag, image_digest)
        github_owner: GitHub 用户/组织
        github_repo: GitHub 仓库名

    Returns:
        dict: 分析结果
    """
    import json

    # 提取容器信息
    repo_name = container_info.get('repo_name', '')
    image_tag = container_info.get('image_tag', '')
    image_digest = container_info.get('image_digest', '')

    # 统计受影响的包（去重）并创建升级表
    affected_packages = list(set(v.get("package_name", "") for v in aggregated_vulnerabilities if v.get("package_name")))

    # 创建紧凑的升级表（按包名去重，只保留最高修复版本）
    upgrade_table_lines = []
    package_versions = {}  # {package_name: (installed, fixed)}
    for vuln in aggregated_vulnerabilities:
        pkg = vuln.get("package_name", "")
        if pkg:
            # 支持两种字段名: current_version (Lambda传入) 或 installed_version
            installed = vuln.get("current_version") or vuln.get("installed_version") or "?"
            fixed = vuln.get("fixed_version", "?")
            if pkg not in package_versions:
                package_versions[pkg] = (installed, fixed)
            else:
                # 保留已有版本（简化处理）
                pass
    for pkg, (installed, fixed) in package_versions.items():
        upgrade_table_lines.append(f"  - {pkg}: {installed} → {fixed}")
    critical_count = sum(1 for v in aggregated_vulnerabilities if v.get("severity") == "CRITICAL")
    high_count = sum(1 for v in aggregated_vulnerabilities if v.get("severity") == "HIGH")

    prompt = f"""
**任务: 容器漏洞分析 (Task ID: {task_id})**

**⚠️⚠️⚠️ 立即执行步骤 1 - 不要跳过！⚠️⚠️⚠️**

## 步骤 1 [现在执行]: 搜索容器清单
```
search_container_inventory(
  ecr_repository="{repo_name}",
  github_owner="{github_owner}"
)
```
- 如果 found=false → 设置 can_remediate=false，跳到步骤 5
- 如果 found=true → 继续步骤 2

## 步骤 2: 读取服务元数据
```
get_service_metadata(
  service_path="<步骤1返回的path>",
  github_owner="{github_owner}",
  github_repo="<步骤1返回的github_repo>"
)
```

## 步骤 3: 读取依赖文件
使用 read_github_file 读取需要修改的文件 (如 pom.xml, requirements.txt)

## 步骤 4: 生成 file_changes
- 漏洞数量: {len(aggregated_vulnerabilities)} ({critical_count} CRITICAL, {high_count} HIGH)
- 受影响包: {', '.join(affected_packages[:5])}{'...' if len(affected_packages) > 5 else ''}
- **⚠️ suggested_content 必须是完整文件内容！**

## 步骤 5 [必须]: 保存分析结果
```
save_analysis_result(
  task_id="{task_id}",
  analysis={{...}},
  remediation_description="...",
  finding={{...}},
  vulnerabilities=[...],  // 所有 {len(aggregated_vulnerabilities)} 个漏洞
  service_info={{...}},
  file_changes=[...],     // suggested_content 是完整文件
  remediation={{...}}
)
```

---

**参考信息 (步骤 4 时使用):**
- Container: {repo_name}:{image_tag}
- GitHub: {github_owner}/{github_repo if github_repo else "(待搜索)"}

**需要升级的依赖包 (用于步骤 4 生成 file_changes):**
{chr(10).join(upgrade_table_lines) if upgrade_table_lines else "  (无版本信息)"}

**⚠️ 现在执行步骤 1！**
"""

    logger.info(f"Running Container Analyzer Agent for task {task_id}, repo {repo_name}")

    try:
        result = agent(prompt)

        # 正确提取响应文本
        response_text = ""
        if hasattr(result, 'message'):
            msg = result.message
            if isinstance(msg, dict):
                content = msg.get('content', [])
                if content and isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and 'text' in item:
                            response_text += item['text']
                        elif isinstance(item, str):
                            response_text += item
            elif isinstance(msg, str):
                response_text = msg
            else:
                response_text = str(msg)
        else:
            response_text = str(result)

        logger.info(f"Container Analyzer completed for task {task_id}")

        # 从 Agent 响应中提取 JSON 结构
        # Agent 已通过 save_analysis_result 将数据保存到 Memory（供 Remediator 使用）
        # 同时 Agent 应该在响应末尾返回完整的 JSON（供我们直接提取）
        analysis_data = _extract_json_from_response(response_text)

        # 使用 LLM 返回的漏洞列表，确保邮件显示的是 LLM 实际分析并将修复的漏洞
        # 如果 LLM 没有返回漏洞列表，使用原始列表作为 fallback
        llm_vulnerabilities = analysis_data.get('vulnerabilities', [])
        if not llm_vulnerabilities:
            logger.warning(f"LLM did not return vulnerabilities, using original list ({len(aggregated_vulnerabilities)} items)")
            llm_vulnerabilities = aggregated_vulnerabilities

        file_changes = analysis_data.get('file_changes', [])
        service_info = analysis_data.get('service_info', {})
        remediation = analysis_data.get('remediation', {})

        # ⚠️ FALLBACK: 如果 LLM 没有正确调用 save_analysis_result 保存 file_changes，
        # 我们在这里手动保存，确保 Remediator 能从 Memory 获取数据
        if file_changes:
            logger.info(f"[Container Analyzer] Ensuring analysis data is saved to Memory (file_changes count: {len(file_changes)})")
            try:
                # 调用 save_analysis_result 保存完整数据
                save_result = save_analysis_result(
                    task_id=task_id,
                    analysis=analysis_data.get('analysis', {}),
                    remediation_description=remediation.get('description', ''),
                    finding=finding,
                    vulnerabilities=llm_vulnerabilities,
                    service_info=service_info,
                    file_changes=file_changes,
                    remediation=remediation
                )
                if save_result.get('success'):
                    logger.info(f"[Container Analyzer] Analysis data saved to Memory successfully")
                else:
                    logger.warning(f"[Container Analyzer] Failed to save analysis to Memory: {save_result.get('error')}")
            except Exception as save_error:
                logger.warning(f"[Container Analyzer] Exception saving analysis to Memory: {save_error}")
        else:
            logger.warning(f"[Container Analyzer] No file_changes found in LLM response - Remediator may fail")

        return {
            "success": True,
            "task_id": task_id,
            "remediation_type": "github_pr",
            "analysis": analysis_data.get('analysis', {}),
            "service_info": service_info,
            "vulnerabilities": llm_vulnerabilities,
            "file_changes": file_changes,
            "remediation": remediation,
            "raw_response": response_text
        }

    except Exception as e:
        logger.exception(f"Container Analyzer failed for task {task_id}: {e}")
        return {
            "success": False,
            "task_id": task_id,
            "remediation_type": "github_pr",
            "error": str(e)
        }


def _extract_json_from_response(response_text: str) -> dict:
    """从 Agent 响应中提取 JSON 结构。

    Args:
        response_text: Agent 的原始响应文本

    Returns:
        dict: 解析后的 JSON 数据，如果解析失败返回空 dict
    """
    import json
    import re

    # 尝试找到 JSON 代码块 (支持 ```json 或 ``` 开头)
    json_block_patterns = [
        r'```json\s*\n?([\s\S]*?)\n?\s*```',
        r'```\s*\n?(\{[\s\S]*?"analysis"[\s\S]*?\})\n?\s*```',
    ]

    for pattern in json_block_patterns:
        json_block_match = re.search(pattern, response_text)
        if json_block_match:
            try:
                json_text = json_block_match.group(1).strip()
                return json.loads(json_text)
            except json.JSONDecodeError as e:
                logger.debug(f"JSON decode failed for pattern {pattern}: {e}")
                continue

    # 尝试找到包含 "analysis" 的 JSON 对象，使用括号匹配
    start_idx = response_text.find('{"analysis"')
    if start_idx == -1:
        start_idx = response_text.find('{\n  "analysis"')
    if start_idx == -1:
        start_idx = response_text.find('{\\n  "analysis"')

    if start_idx >= 0:
        try:
            # 从起始位置找到匹配的闭合括号
            text = response_text[start_idx:]
            depth = 0
            end_pos = 0
            in_string = False
            escape_next = False

            for i, char in enumerate(text):
                if escape_next:
                    escape_next = False
                    continue
                if char == '\\':
                    escape_next = True
                    continue
                if char == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if char == '{':
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0:
                        end_pos = i + 1
                        break

            if end_pos > 0:
                json_text = text[:end_pos]
                return json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.debug(f"JSON decode failed for bracket matching: {e}")

    logger.warning(f"Could not extract JSON from agent response. First 300 chars: {response_text[:300]}")
    return {}
