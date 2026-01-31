"""
Memory Tools - AgentCore Memory 交互工具

支持 Episodic Memory Strategy，用于：
- STM: 三个智能体 (Analyzer, Remediator, Validator) 在同一任务中共享信息
- LTM: 存储修复经验，使用 Episodic 结构 (scenario → intent → actions → outcomes)

Namespace 结构:
- Episodes: /remediation/actors/{actorId}/sessions/{sessionId}/
- Reflections: /remediation/actors/{actorId}/
"""
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, TYPE_CHECKING

from strands import tool

from shared.config import get_config

if TYPE_CHECKING:
    from bedrock_agentcore.memory import MemoryClient

logger = logging.getLogger(__name__)

# Global memory session reference (set by agent initialization)
_memory_session = None

# Namespace patterns (must match create_shara_memory.py)
EPISODE_NAMESPACE_PREFIX = "/remediation/actors/"
REFLECTION_NAMESPACE_PREFIX = "/remediation/actors/"


class MemorySession:
    """Memory Session 封装类。

    封装 MemoryClient 以提供统一的 STM/LTM 操作接口。
    用于 Agent tools 进行 Memory 操作。
    """

    def __init__(self, client: "MemoryClient", memory_id: str, actor_id: str, session_id: str):
        """初始化 Memory Session。

        Args:
            client: MemoryClient 实例
            memory_id: Memory ID
            actor_id: Actor ID (通常是 AWS 账户 ID 或任务相关标识)
            session_id: Session ID (任务 ID)
        """
        self.client = client
        self.memory_id = memory_id
        self.actor_id = actor_id
        self.session_id = session_id

    def add_turns(self, messages: list):
        """添加对话消息到 Memory (STM)。

        Args:
            messages: ConversationalMessage 列表或 (content, role) 元组列表
        """
        from bedrock_agentcore.memory.constants import ConversationalMessage, MessageRole

        # 转换为 (content, role) 元组列表
        message_tuples = []
        for msg in messages:
            if isinstance(msg, ConversationalMessage):
                role = msg.role.value if hasattr(msg.role, 'value') else str(msg.role)
                message_tuples.append((msg.text, role))
            elif isinstance(msg, tuple):
                message_tuples.append(msg)
            elif isinstance(msg, dict):
                message_tuples.append((msg.get('content', ''), msg.get('role', 'ASSISTANT')))

        self.client.create_event(
            memory_id=self.memory_id,
            actor_id=self.actor_id,
            session_id=self.session_id,
            messages=message_tuples
        )

    def get_last_k_turns(self, k: int = 10) -> list:
        """获取最近 k 条消息 (STM)。

        Returns:
            list: 消息列表，每条消息包含 'content' (字符串) 和 'role'
        """
        # get_last_k_turns 返回 List[List[Dict]] (events -> messages)
        # 每条消息格式: {'content': {'text': '...'}, 'role': 'ASSISTANT'}
        events = self.client.get_last_k_turns(
            memory_id=self.memory_id,
            actor_id=self.actor_id,
            session_id=self.session_id,
            k=k
        )

        # 展平为消息列表，并提取 content.text
        messages = []
        for event in events:
            if isinstance(event, list):
                for msg in event:
                    content = msg.get('content', {})
                    if isinstance(content, dict):
                        content = content.get('text', '')
                    messages.append({
                        'content': content,
                        'role': msg.get('role', '')
                    })
            elif isinstance(event, dict):
                content = event.get('content', {})
                if isinstance(content, dict):
                    content = content.get('text', '')
                messages.append({
                    'content': content,
                    'role': event.get('role', '')
                })

        return messages

    def search_long_term_memories(self, query: str, namespace_prefix: str, top_k: int = 5) -> list:
        """搜索长期记忆 (LTM)。

        Args:
            query: 搜索查询
            namespace_prefix: 命名空间前缀
            top_k: 返回结果数量

        Returns:
            list: 匹配的记忆列表
        """
        try:
            return self.client.retrieve_memories(
                memory_id=self.memory_id,
                namespace=namespace_prefix,
                query=query,
                actor_id=self.actor_id,
                top_k=top_k
            )
        except Exception as e:
            logger.warning(f"LTM search failed: {e}")
            return []


def create_memory_session(session_manager) -> Optional[MemorySession]:
    """从 AgentCoreMemorySessionManager 创建 MemorySession。

    Args:
        session_manager: AgentCoreMemorySessionManager 实例

    Returns:
        MemorySession: 封装的 Memory session 对象，或 None 如果失败
    """
    try:
        return MemorySession(
            client=session_manager.memory_client,
            memory_id=session_manager.config.memory_id,
            actor_id=session_manager.config.actor_id,
            session_id=session_manager.config.session_id
        )
    except Exception as e:
        logger.error(f"Failed to create MemorySession: {e}")
        return None


def set_memory_session(session):
    """Set the memory session for tools to use.

    Args:
        session: MemorySession 实例或 AgentCoreMemorySessionManager 实例
    """
    global _memory_session

    # 如果传入的是 AgentCoreMemorySessionManager，则创建 MemorySession
    if hasattr(session, 'memory_client') and hasattr(session, 'config'):
        _memory_session = create_memory_session(session)
    elif isinstance(session, MemorySession):
        _memory_session = session
    else:
        # 假设是已经封装好的 session
        _memory_session = session


def get_memory_session() -> Optional[MemorySession]:
    """Get the current memory session"""
    return _memory_session


@tool
def search_similar_findings(
    control_id: str,
    finding_title: str,
    resource_type: str,
    top_k: int = 5
) -> list:
    """从 Memory LTM 搜索相似的修复经验。

    使用 Episodic Memory Strategy 搜索历史修复经验：
    1. 首先搜索 Reflections (跨任务高级洞察和模式)
    2. 然后搜索 Episodes (具体修复场景)

    Namespace 结构:
    - Episodes: /remediation/actors/{actorId}/sessions/{sessionId}/
    - Reflections: /remediation/actors/{actorId}/

    Args:
        control_id: Security Hub Control ID (如 S3.1)
        finding_title: Finding 标题，用于语义搜索
        resource_type: AWS 资源类型 (如 AwsS3Bucket)
        top_k: 返回的最大结果数，默认 5

    Returns:
        list: 相似修复经验列表，每个经验包含:
            - type: str - "reflection" 或 "episode"
            - similarity_score: float - 相似度分数
            - content: str/dict - 经验内容
            - control_id: str - Control ID (如匹配)
            - insights: str - 提取的关键洞察 (如有)
    """
    session = get_memory_session()
    if not session:
        logger.warning("Memory session not initialized, returning empty results")
        return []

    results = []

    try:
        # 构建语义搜索查询 - 包含关键信息以提高匹配准确度
        query = f"Security remediation for AWS {resource_type}: Control ID {control_id}, Finding: {finding_title}"

        # 1. 首先搜索 Reflections - 跨任务的高级洞察
        # Reflections 存储在 /remediation/actors/{actorId}/ 下
        logger.info(f"Searching Reflections with query: {query[:80]}...")

        try:
            reflection_memories = session.search_long_term_memories(
                query=query,
                namespace_prefix=REFLECTION_NAMESPACE_PREFIX,
                top_k=top_k // 2 + 1  # 分配一半给 reflections
            )

            for memory in reflection_memories:
                content = memory.get('content', '')
                score = memory.get('score', 0.0)

                # Reflections 通常包含跨任务的模式和洞察
                result = {
                    "type": "reflection",
                    "similarity_score": score,
                    "content": content,
                    "insights": _extract_insights_from_reflection(content, control_id),
                }
                results.append(result)

            logger.info(f"Found {len(reflection_memories)} reflections")
        except Exception as e:
            logger.warning(f"Error searching reflections: {e}")

        # 2. 搜索 Episodes - 具体的修复场景
        # Episodes 存储在 /remediation/actors/{actorId}/sessions/{sessionId}/ 下
        logger.info(f"Searching Episodes with query: {query[:80]}...")

        try:
            episode_memories = session.search_long_term_memories(
                query=query,
                namespace_prefix=EPISODE_NAMESPACE_PREFIX,
                top_k=top_k // 2 + 1  # 分配一半给 episodes
            )

            for memory in episode_memories:
                content = memory.get('content', '')
                score = memory.get('score', 0.0)

                # Episodes 包含具体的修复场景 (scenario → intent → actions → outcomes)
                result = {
                    "type": "episode",
                    "similarity_score": score,
                    "content": content,
                    "episode_structure": _parse_episode_structure(content),
                }
                results.append(result)

            logger.info(f"Found {len(episode_memories)} episodes")
        except Exception as e:
            logger.warning(f"Error searching episodes: {e}")

        # 按相似度分数排序并限制结果数量
        results.sort(key=lambda x: x.get('similarity_score', 0), reverse=True)
        results = results[:top_k]

        logger.info(f"Returning {len(results)} total similar experiences")
        return results

    except Exception as e:
        logger.exception(f"Error searching Memory LTM: {e}")
        return []


def _extract_insights_from_reflection(content: str, control_id: str) -> str:
    """从 Reflection 内容中提取与当前 Control ID 相关的洞察。

    Args:
        content: Reflection 内容
        control_id: 当前 Control ID

    Returns:
        str: 提取的关键洞察
    """
    if not content:
        return ""

    # 提取与 Control ID 或其服务家族相关的内容
    # 例如 S3.1 -> S3, EC2.19 -> EC2
    service_prefix = control_id.split('.')[0] if '.' in control_id else control_id

    # 简单的关键词匹配来提取相关段落
    lines = content.split('\n') if isinstance(content, str) else []
    relevant_lines = []

    for line in lines:
        if control_id in line or service_prefix in line or 'remediation' in line.lower():
            relevant_lines.append(line.strip())

    return '\n'.join(relevant_lines[:5]) if relevant_lines else ""


def _parse_episode_structure(content: str) -> dict:
    """解析 Episode 内容的结构。

    Episodic Memory 的内容应该包含:
    - scenario: 发生了什么
    - intent: 目标是什么
    - actions: 采取了什么行动
    - outcomes: 结果如何

    Args:
        content: Episode 内容

    Returns:
        dict: 解析后的结构
    """
    structure = {
        "scenario": "",
        "intent": "",
        "actions": "",
        "outcomes": ""
    }

    if not content or not isinstance(content, str):
        return structure

    # 尝试解析结构化内容
    content_lower = content.lower()

    # 查找各个部分的标记
    markers = {
        "scenario": ["scenario:", "finding:", "issue:", "## scenario", "**scenario**"],
        "intent": ["intent:", "goal:", "objective:", "## intent", "**intent**"],
        "actions": ["actions:", "steps:", "remediation:", "## actions", "**actions**"],
        "outcomes": ["outcomes:", "results:", "validation:", "## outcomes", "**outcomes**"]
    }

    for key, keywords in markers.items():
        for keyword in keywords:
            if keyword in content_lower:
                # 找到关键词后，提取后续内容
                idx = content_lower.index(keyword)
                end_idx = len(content)

                # 查找下一个部分的开始
                for other_key, other_keywords in markers.items():
                    if other_key != key:
                        for other_kw in other_keywords:
                            other_idx = content_lower.find(other_kw, idx + len(keyword))
                            if other_idx > idx and other_idx < end_idx:
                                end_idx = other_idx

                structure[key] = content[idx + len(keyword):end_idx].strip()[:500]
                break

    return structure


@tool
def save_analysis_result(
    task_id: str,
    analysis: dict,
    remediation_description: str
) -> dict:
    """保存分析结果到 Memory Session (供 Phase 2 使用)。

    将 Phase 1 的分析结果保存到 Memory Session，
    以便 Phase 2 的 Remediator Agent 可以获取上下文继续工作。

    Args:
        task_id: 任务 ID
        analysis: 分析结果，包含风险评估等信息
        remediation_description: 修复方案的文字描述

    Returns:
        dict: 保存结果
            - success: bool - 是否成功
            - task_id: str - 任务 ID
            - error: str - 错误信息 (如有)
    """
    session = get_memory_session()
    if not session:
        logger.error("Memory session not initialized")
        return {"success": False, "error": "Memory session not initialized"}

    try:
        from bedrock_agentcore.memory.constants import ConversationalMessage, MessageRole

        # 构建要保存的数据
        data = {
            "type": "phase1_analysis",
            "task_id": task_id,
            "analysis": analysis,
            "remediation_description": remediation_description,
            "saved_at": datetime.now(timezone.utc).isoformat()
        }

        # 保存为对话记录
        session.add_turns([
            ConversationalMessage(
                json.dumps(data),
                MessageRole.ASSISTANT
            )
        ])

        logger.info(f"Saved Phase 1 analysis for task {task_id}")
        return {"success": True, "task_id": task_id}

    except Exception as e:
        logger.exception(f"Error saving analysis result: {e}")
        return {"success": False, "task_id": task_id, "error": str(e)}


@tool
def get_analysis_context(task_id: str) -> dict:
    """从 Memory Session 获取 Phase 1 分析结果。

    Phase 2 开始时调用，获取 Analyzer Agent 在 Phase 1 保存的分析结果，
    包括修复描述、风险评估、ASR 匹配信息等。

    Args:
        task_id: 任务 ID

    Returns:
        dict: Phase 1 分析结果
            - success: bool - 是否成功获取
            - analysis: dict - 分析结果
            - remediation_description: str - 修复描述
            - error: str - 错误信息 (如有)
    """
    session = get_memory_session()
    if not session:
        logger.error("Memory session not initialized")
        return {"success": False, "error": "Memory session not initialized"}

    try:
        # 获取最近的对话记录
        turns = session.get_last_k_turns(k=10)

        # 查找 Phase 1 分析结果
        for turn in reversed(turns):
            content = turn.get('content', '')
            if isinstance(content, str) and 'phase1_analysis' in content:
                try:
                    data = json.loads(content)
                    if data.get('type') == 'phase1_analysis' and data.get('task_id') == task_id:
                        logger.info(f"Retrieved Phase 1 analysis for task {task_id}")
                        return {
                            "success": True,
                            "analysis": data.get('analysis', {}),
                            "remediation_description": data.get('remediation_description', '')
                        }
                except json.JSONDecodeError:
                    continue

        logger.warning(f"Phase 1 analysis not found for task {task_id}")
        return {"success": False, "error": "Phase 1 analysis not found"}

    except Exception as e:
        logger.exception(f"Error getting analysis context: {e}")
        return {"success": False, "error": str(e)}


@tool
def save_experience_to_ltm(
    control_id: str,
    task_id: str,
    finding_title: str,
    resource_type: str,
    analysis_summary: str,
    remediation_approach: str,
    generated_code: str,
    lessons_learned: Optional[str] = None,
    validation_result: Optional[str] = None
) -> dict:
    """保存修复经验到 Memory（通过 STM 触发 LTM Episodic 提取）。

    当修复成功且经过验证后，将此次修复经验保存为 Episodic 格式的 event。
    AgentCore Memory 的 Episodic Strategy 会自动从 events 中提取:
    - Episodes (scenario → intent → actions → outcomes) 存储在 /remediation/actors/{actorId}/sessions/{sessionId}/
    - Reflections (跨任务模式分析) 存储在 /remediation/actors/{actorId}/

    注意：LTM 提取是异步的，保存后可能需要几分钟才能在 LTM 中检索到。

    Args:
        control_id: Control ID (如 S3.1)
        task_id: 任务 ID
        finding_title: Finding 标题
        resource_type: 资源类型
        analysis_summary: 分析摘要
        remediation_approach: 修复方案描述
        generated_code: 生成的修复代码
        lessons_learned: 经验教训 (可选)
        validation_result: 验证结果 (可选)

    Returns:
        dict: 保存结果
            - saved: bool - 是否成功
            - experience_id: str - 经验 ID
            - episode_namespace: str - Episode 命名空间
            - reflection_namespace: str - Reflection 命名空间
    """
    session = get_memory_session()
    if not session:
        logger.error("Memory session not initialized")
        return {"saved": False, "error": "Memory session not initialized"}

    try:
        from bedrock_agentcore.memory.constants import ConversationalMessage, MessageRole

        # 构建经验 ID
        safe_control_id = control_id.replace('.', '_')
        experience_id = f"EXP_{safe_control_id}_{task_id[:8]}"

        # 构建 Episodic 格式的经验内容
        # 结构: scenario → intent → actions → outcomes
        # 这种格式便于 Episodic Extraction 正确识别和提取
        experience_content = f"""
# Security Remediation Episode

## Episode ID
{experience_id}

## Scenario
**What happened:** AWS Security Hub detected a security finding.
- **Control ID:** {control_id}
- **Finding Title:** {finding_title}
- **Resource Type:** {resource_type}
- **Task ID:** {task_id}

### Finding Details
{analysis_summary}

## Intent
**Goal:** Remediate the security finding {control_id} on {resource_type} resource to achieve compliance with AWS Security Hub standards.

**Expected Outcome:** Resource should pass the security control check after remediation.

## Actions
**Remediation Approach:**
{remediation_approach}

**Generated Code:**
```python
{generated_code}
```

**Execution Steps:**
1. Phase 1 (Analyzer): Analyzed finding and determined remediation strategy
2. Phase 2 (Remediator): Generated and executed remediation code
3. Phase 2 (Validator): Verified remediation success and updated Security Hub

## Outcomes
**Result:** {'SUCCESS' if validation_result else 'PENDING VALIDATION'}

**Validation Details:**
{validation_result or 'Awaiting validation'}

**Lessons Learned:**
{lessons_learned or 'N/A'}

## Metadata
- **Timestamp:** {datetime.now(timezone.utc).isoformat()}
- **Source:** validated_remediation
- **Service Family:** {control_id.split('.')[0] if '.' in control_id else control_id}
"""

        # 保存为 event，Episodic Strategy 会自动:
        # 1. 提取 Episode 到 /remediation/actors/{actorId}/sessions/{sessionId}/
        # 2. 生成 Reflection 到 /remediation/actors/{actorId}/
        session.add_turns([
            ConversationalMessage(
                experience_content,
                MessageRole.ASSISTANT
            )
        ])

        logger.info(f"Saved remediation experience for {control_id} in Episodic format")
        logger.info(f"Episode will be stored in /remediation/actors/{{actorId}}/sessions/{{sessionId}}/")
        logger.info(f"Reflection will be stored in /remediation/actors/{{actorId}}/")

        return {
            "saved": True,
            "experience_id": experience_id,
            "control_id": control_id,
            "episode_namespace": "/remediation/actors/{actorId}/sessions/{sessionId}/",
            "reflection_namespace": "/remediation/actors/{actorId}/",
            "note": "Episodic LTM extraction is asynchronous, may take a few minutes to be searchable"
        }

    except Exception as e:
        logger.exception(f"Error saving experience: {e}")
        return {
            "saved": False,
            "error": str(e)
        }
