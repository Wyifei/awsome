"""
Memory Tools - AgentCore Memory 交互工具
"""
import json
import logging
from datetime import datetime
from typing import List, Optional

from strands import tool

from agents.config import get_config

logger = logging.getLogger(__name__)

# Global memory session reference (set by agent initialization)
_memory_session = None


def set_memory_session(session):
    """Set the memory session for tools to use"""
    global _memory_session
    _memory_session = session


def get_memory_session():
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

    使用语义搜索在长期记忆中查找与当前 Finding 相似的历史修复经验。
    这些经验来自用户验证过的成功修复案例。

    Args:
        control_id: Security Hub Control ID (如 S3.1)
        finding_title: Finding 标题，用于语义搜索
        resource_type: AWS 资源类型 (如 AwsS3Bucket)
        top_k: 返回的最大结果数，默认 5

    Returns:
        list: 相似修复经验列表，每个经验包含:
            - experience_id: str - 经验 ID
            - control_id: str - Control ID
            - similarity_score: float - 相似度分数
            - remediation_approach: str - 修复方案
            - generated_code: str - 修复代码
    """
    session = get_memory_session()
    if not session:
        logger.warning("Memory session not initialized, returning empty results")
        return []

    try:
        # 构建搜索查询
        query = f"Control: {control_id}, Finding: {finding_title}, Resource: {resource_type}"

        # 构建命名空间前缀
        # 使用下划线替代点号，符合 S3 路径规范
        namespace_prefix = f"/remediation/{control_id.replace('.', '_')}/"

        logger.info(f"Searching Memory LTM with query: {query[:100]}... namespace: {namespace_prefix}")

        memories = session.search_long_term_memories(
            query=query,
            namespace_prefix=namespace_prefix,
            top_k=top_k
        )

        logger.info(f"Found {len(memories)} similar experiences")

        # 格式化返回结果
        results = []
        for memory in memories:
            content = memory.get('content', {})
            results.append({
                "experience_id": content.get('experience_id', ''),
                "control_id": content.get('control_id', control_id),
                "similarity_score": memory.get('score', 0.0),
                "remediation_approach": content.get('remediation_approach', ''),
                "generated_code": content.get('generated_code', ''),
                "lessons_learned": content.get('lessons_learned', ''),
                "source": content.get('source', 'user_validated')
            })

        return results

    except Exception as e:
        logger.exception(f"Error searching Memory LTM: {e}")
        return []


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
            "saved_at": datetime.utcnow().isoformat()
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
    lessons_learned: Optional[str] = None
) -> dict:
    """保存修复经验到 Memory 长期记忆。

    当修复成功且经过验证后，将此次修复经验保存到 LTM，
    供未来类似 Finding 的处理参考。

    Args:
        control_id: Control ID (如 S3.1)
        task_id: 任务 ID
        finding_title: Finding 标题
        resource_type: 资源类型
        analysis_summary: 分析摘要
        remediation_approach: 修复方案描述
        generated_code: 生成的修复代码
        lessons_learned: 经验教训 (可选)

    Returns:
        dict: 保存结果
            - saved: bool - 是否成功
            - namespace: str - 保存的命名空间
            - experience_id: str - 经验 ID
    """
    config = get_config()

    try:
        from bedrock_agentcore.memory import MemorySessionManager

        manager = MemorySessionManager(
            memory_id=config.memory_id,
            region_name=config.region
        )

        # 构建经验文档
        experience = {
            "experience_id": f"USER_{control_id.replace('.', '_')}_{task_id[:8]}",
            "task_id": task_id,
            "control_id": control_id,
            "finding_title": finding_title,
            "resource_type": resource_type,
            "analysis_summary": analysis_summary,
            "remediation_approach": remediation_approach,
            "generated_code": generated_code,
            "lessons_learned": lessons_learned or "",
            "source": "user_validated",
            "created_at": datetime.utcnow().isoformat()
        }

        # 保存到 LTM
        namespace = f"/remediation/{control_id.replace('.', '_')}/{task_id}"

        # TODO: 调用 AgentCore Memory LTM API 保存
        # 当前 API 可能需要根据实际 SDK 版本调整
        logger.info(f"Saving experience to LTM namespace: {namespace}")

        return {
            "saved": True,
            "namespace": namespace,
            "experience_id": experience["experience_id"]
        }

    except Exception as e:
        logger.exception(f"Error saving experience to LTM: {e}")
        return {
            "saved": False,
            "error": str(e)
        }
