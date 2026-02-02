"""
Analyzer Agent - Phase 1 分析智能体

负责分析 Security Hub Finding 并生成修复方案描述（不生成代码）。
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

logger = logging.getLogger(__name__)

# Analyzer Agent System Prompt
ANALYZER_SYSTEM_PROMPT = """# 角色
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
  finding=<原始 Finding 数据>,  # 完整的 ASFF 格式 Finding
  asr_playbook=<fetch_asr_playbook 的返回结果>,  # 如果有匹配
  top_experience=<search_similar_findings 返回的第一条结果>  # 如果有结果
)
```

**重要**: 必须传递完整的 `finding` 数据，Remediator 需要从中提取：
- Region: 资源所在的 AWS 区域
- Resources[].Id: 资源 ARN
- Resources[].Type: 资源类型
- 其他修复所需的上下文信息

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
    "current_state": {
      "KmsMasterKeyId": null
    },
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
  "similar_experiences": [
    {
      "similarity_score": 0.51,
      "title": "S3 Block Public Access 配置修复",
      "problem": "S3 存储桶的 Block Public Access 设置被禁用",
      "solution": "通过 S3 API 启用所有四项公共访问阻止设置",
      "result": "成功修复，符合 AWS 安全最佳实践"
    }
  ],
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

# 修复步骤分类说明（重要）
在 remediation 对象中，必须将修复步骤分为三类：

## 1. prerequisites（前置条件）
**审批前人工需要确认的事项**，Agent 无法自动验证或执行。例如：
- 确认替代访问路径存在（如 VPN、bastion host）
- 确认业务影响已评估
- 确认相关团队已通知
- 验证依赖服务的连通性

## 2. agent_actions（Agent 执行）
**Agent 将通过 AWS API 自动执行的操作**。只包含可通过代码实现的步骤：
- 调用 AWS API 修改资源配置
- 等待资源状态变更
- 验证配置是否生效
- 创建/修改安全策略

## 3. post_actions（后续操作）
**修复完成后人工需要处理的事项**，Agent 无法自动完成。例如：
- 更新 IaC 代码（Terraform/CloudFormation）保持一致性
- 更新相关文档
- 通知相关团队
- 进行额外的安全审计

## 分类原则
- **可通过 AWS SDK/API 实现** → agent_actions
- **需要访问外部系统或人工判断** → prerequisites 或 post_actions
- **修复前需要确认** → prerequisites
- **修复后需要跟进** → post_actions

## 示例
```json
"remediation": {
  "can_remediate": true,
  "summary": "禁用 EKS 集群公共端点访问",
  "prerequisites": [
    "确认 VPC 内有可用的私有访问路径（bastion host/VPN/Direct Connect）",
    "验证 kubectl 可通过私有端点连接集群"
  ],
  "agent_actions": [
    "调用 EKS UpdateClusterConfig API 设置 EndpointPublicAccess=false",
    "等待集群更新完成（状态变为 ACTIVE）",
    "验证公共端点已禁用"
  ],
  "post_actions": [
    "更新 Terraform/CloudFormation 代码保持配置一致性",
    "通知 DevOps 团队配置变更"
  ],
  "estimated_impact": "MEDIUM",
  "rollback_available": true,
  "is_destructive": false
}
```

# can_remediate 字段说明
**必须**在 remediation 对象中包含 can_remediate 字段：

设置 `can_remediate: false` 的情况：
1. **资源不存在** - 资源已被删除，无需修复
2. **ECR/容器镜像漏洞** - 需要开发团队更新代码/镜像，无法通过 AWS API 自动修复
3. **Inspector 软件漏洞** - 需要更新软件包，不是 AWS 配置问题
4. **需要手动干预** - 例如需要业务决策、涉及第三方系统等
5. **不支持的资源类型** - SHARA 当前不支持自动修复的资源

设置 `can_remediate: true` 的情况：
1. AWS 配置类问题（如 S3 加密、安全组规则、IAM 策略等）
2. 有对应的 ASR Playbook
3. 可以通过 AWS API 直接修改配置

当 `can_remediate: false` 时，必须填写 `cannot_remediate_reason` 说明原因。

# AWS Documentation MCP 工具 (可选)
如果你有 AWS Documentation MCP 工具可用 (工具名以 `aws_doc_` 前缀开头)，可以在以下情况使用：

## 何时使用 AWS Documentation MCP 工具
1. **没有 ASR Playbook** - fetch_asr_playbook 返回 matched=false
2. **没有相似经验** - search_similar_findings 返回空结果
3. **不确定修复方法** - 对于不熟悉的 Control ID 或资源类型
4. **需要了解 AWS 最佳实践** - 确认正确的安全配置方式

## 可用的 MCP 工具
- `aws_doc_search_documentation`: 搜索 AWS 官方文档，获取修复指南和最佳实践
- `aws_doc_read_documentation`: 读取特定 AWS 文档页面获取详细信息
- `aws_doc_recommend`: 获取相关文档推荐

## 使用示例
当遇到不熟悉的 Control ID 时：
```
aws_doc_search_documentation(
  search_phrase="Security Hub <Control ID> remediation best practices"
)
```

当需要阅读特定文档时：
```
aws_doc_read_documentation(
  url="https://docs.aws.amazon.com/console/securityhub/<Control ID>/remediation"
)
```

## 注意事项
- MCP 工具是**辅助**工具，不是必须调用的
- 优先使用 fetch_asr_playbook 和 search_similar_findings
- 只有在缺乏信息时才查询 AWS 文档
- 搜索时使用英文关键词效果更好

# asr_match 字段说明
ASR (Automated Security Response) 匹配基于 Control ID 精确匹配：
- **matched=true**: 找到对应的 ASR Playbook，confidence 固定为 **1.0**（精确匹配）
- **matched=false**: 未找到匹配，confidence 为 **0**
- 不存在中间置信度，因为是基于 Control ID 的精确匹配

# similar_experiences 字段说明
**必须**将 search_similar_findings 工具返回的结果加工后放入此数组。

## 如何使用 LTM 返回的经验
search_similar_findings 会返回两种类型的经验，你需要区别对待：

### 1. Reflection (type="reflection") - 方法论框架
这是从多次修复中总结的**高级洞察和模式**。在分析过程中：
- **主动应用**其中描述的分析方法和检查要点
- 参考其中的风险评估标准和最佳实践
- 将方法论融入你的 `risk_assessment` 和 `remediation` 设计

### 2. Episode (type="episode") - 执行记录
这是**具体的成功修复案例**，包含实际的场景、意图、操作和结果。用于：
- 参考类似场景的**具体修复步骤**
- 了解之前成功的**验证方法**
- 在 `similar_experiences` 中**突出显示执行结果**（result 字段）

**重要**: Reflection 指导"怎么做"，Episode 提供"做过什么"。两者都要参考。

## 格式化要求
LTM 返回的 content 是自然语言描述（英文），你需要从中提取关键信息，格式化为以下**固定格式**：

```json
{
  "type": "episode",
  "similarity_score": 0.51,
  "title": "S3 Block Public Access 配置修复",
  "problem": "S3 存储桶的 Block Public Access 设置被禁用，存在数据泄露风险",
  "solution": "通过 S3 API 启用所有四项公共访问阻止设置",
  "result": "成功修复，符合 AWS 安全最佳实践"
}
```

## 字段说明（必须按此格式输出）
- **type**: 经验类型（直接使用工具返回的 type: "reflection" 或 "episode"）
- **similarity_score**: 相似度分数 (0-1，直接使用工具返回的值)
- **title**: 经验标题（中文，10-20字，描述修复的核心内容）
- **problem**: 问题描述（中文，简述发现的安全问题）
- **solution**: 解决方案（中文，简述采取的修复措施）
- **result**: 修复结果（中文，简述修复效果。Episode 类型应突出实际执行结果）

## 格式化示例
假设 search_similar_findings 返回:
```
{
  "type": "episode",
  "similarity_score": 0.51,
  "content": "I conducted a security analysis on an S3 bucket and found that the Block Public Access settings were completely disabled, posing a high risk of accidental public exposure. I provided a detailed remediation plan to enable all four public access blocking settings through the S3 API, ensuring the bucket's data remains secure and compliant with AWS best practices."
}
```

你应该输出:
```json
{
  "type": "episode",
  "similarity_score": 0.51,
  "title": "S3 Block Public Access 配置修复",
  "problem": "S3 存储桶的 Block Public Access 设置被禁用，存在公开暴露风险",
  "solution": "通过 S3 API 启用所有四项公共访问阻止设置",
  "result": "成功修复，验证通过，数据安全符合 AWS 最佳实践"
}
```

## 重要说明 - 分数阈值
- **Reflection (方法论)**: 只处理相似度 >= 0.5 的结果
- **Episode (执行记录)**: 处理相似度 >= 0.35 的结果（因为包含实际执行结果，价值更高）
- **必须翻译成中文**: 邮件内容需要中文显示
- **参考历史经验**: 在分析和生成修复方案时，主动应用 Reflection 的方法论，参考 Episode 的执行结果

# 重要指南
- **【强制】必须调用 get_resource_config**: 这是第一个必须执行的工具调用
- **【强制】必须调用 save_analysis_result**: 这是最后一个必须执行的工具调用，保存分析结果供 Phase 2 使用
- **【强制】必须设置 can_remediate 字段**: 明确指示此 Finding 是否可自动修复
- **asr_match 必须如实反映 fetch_asr_playbook 的返回结果**，confidence 按上述规则设置
- 如果资源不存在，设置 resource_exists: false 且 can_remediate: false
- 绝不在响应中包含可执行代码
"""


def create_analyzer_agent(
    task_id: str,
    memory_id: str,
    session_id: str,
    region: Optional[str] = None,
    actor_id: Optional[str] = None,
    mcp_tools: Optional[list] = None
) -> Agent:
    """创建 Analyzer Agent 实例。

    Args:
        task_id: 任务 ID
        memory_id: AgentCore Memory ID
        session_id: Memory Session ID (从 Lambda 传入，确保与 Phase 2 共享)
        region: AWS Region (可选，默认从环境变量获取)
        actor_id: Actor ID (可选，默认使用 task_id)
        mcp_tools: AWS MCP Server 提供的工具列表 (可选)

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

    # 构建工具列表
    tools = [
        get_resource_config,  # 第一个必须调用的工具
        fetch_asr_playbook,
        search_similar_findings,
        save_analysis_result,  # 保存分析结果供 Phase 2 使用
    ]

    # 添加 AWS MCP 工具 (如果可用)
    if mcp_tools:
        tools.extend(mcp_tools)
        logger.info(f"Added {len(mcp_tools)} AWS MCP tools to agent")

    # 创建 Agent
    agent = Agent(
        model=model,
        system_prompt=ANALYZER_SYSTEM_PROMPT,
        tools=tools,
        session_manager=session_manager,
    )

    logger.info(f"Created Analyzer Agent for task {task_id}")
    return agent


def run_analyzer(
    agent: Agent,
    finding: dict,
    control_id: str,
    task_id: str
) -> dict:
    """运行 Analyzer Agent 分析 Finding。

    Args:
        agent: Analyzer Agent 实例
        finding: Security Hub Finding (ASFF 格式)
        control_id: Control ID
        task_id: 任务 ID

    Returns:
        dict: 分析结果
    """
    import json

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
