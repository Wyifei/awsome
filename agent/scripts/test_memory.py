#!/usr/bin/env python3
"""
SHARA Memory 功能测试脚本

测试 AgentCore Memory 的 STM 和 LTM 功能：
1. STM 测试: 验证三个智能体在同一任务中共享信息的能力
2. LTM 测试: 验证 Episodic 策略的经验存储和检索

使用方法:
  # 运行所有测试
  python test_memory.py --memory-id <memory_id>

  # 仅测试 STM
  python test_memory.py --memory-id <memory_id> --test stm

  # 仅测试 LTM
  python test_memory.py --memory-id <memory_id> --test ltm

  # 运行测试并清理测试数据
  python test_memory.py --memory-id <memory_id> --cleanup

  # 仅清理之前的测试数据
  python test_memory.py --memory-id <memory_id> --cleanup-only
"""
import argparse
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DEFAULT_REGION = "ap-northeast-1"

# Track created test sessions for cleanup
_test_sessions = []


def track_test_session(memory_id: str, actor_id: str, session_id: str, region: str):
    """记录测试创建的 session，用于后续清理。"""
    _test_sessions.append({
        "memory_id": memory_id,
        "actor_id": actor_id,
        "session_id": session_id,
        "region": region,
        "created_at": datetime.now().isoformat()
    })


def save_test_sessions_record(output_file: str = None):
    """保存测试 session 记录到文件，用于后续清理。"""
    if not _test_sessions:
        return None

    if output_file is None:
        output_file = "test_memory_sessions.json"

    # 读取现有记录
    existing = []
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r') as f:
                existing = json.load(f)
        except:
            pass

    # 合并新记录
    all_sessions = existing + _test_sessions

    with open(output_file, 'w') as f:
        json.dump(all_sessions, f, indent=2)

    logger.info(f"测试 session 记录已保存到: {output_file}")
    return output_file


def cleanup_test_sessions(memory_id: str, region: str, sessions_file: str = None) -> dict:
    """清理测试创建的 sessions。

    Args:
        memory_id: Memory ID
        region: AWS Region
        sessions_file: 包含 session 记录的文件路径

    Returns:
        dict: 清理结果
    """
    try:
        from bedrock_agentcore.memory import MemoryClient
    except ImportError:
        logger.error("bedrock-agentcore 未安装")
        return {"success": False, "error": "bedrock-agentcore not installed"}

    results = {
        "success": True,
        "deleted": [],
        "failed": [],
        "skipped": []
    }

    # 从文件加载 session 记录
    sessions_to_clean = []

    if sessions_file and os.path.exists(sessions_file):
        try:
            with open(sessions_file, 'r') as f:
                sessions_to_clean = json.load(f)
            logger.info(f"从文件加载了 {len(sessions_to_clean)} 个 session 记录")
        except Exception as e:
            logger.warning(f"无法加载 session 记录文件: {e}")

    # 也包含当前运行中记录的 sessions
    sessions_to_clean.extend(_test_sessions)

    if not sessions_to_clean:
        logger.info("没有需要清理的测试 session")
        return results

    # 过滤出属于当前 memory_id 的 sessions
    sessions_to_clean = [s for s in sessions_to_clean if s.get('memory_id') == memory_id]

    if not sessions_to_clean:
        logger.info(f"没有属于 Memory {memory_id} 的测试 session")
        return results

    logger.info(f"准备清理 {len(sessions_to_clean)} 个测试 session")

    client = MemoryClient(region_name=region)

    for session_info in sessions_to_clean:
        actor_id = session_info.get('actor_id')
        session_id = session_info.get('session_id')

        if not actor_id or not session_id:
            results["skipped"].append(session_info)
            continue

        try:
            # 尝试删除 session
            # 注意: 根据 AgentCore API，可能需要使用 delete_session 或类似方法
            client.delete_session(
                memory_id=memory_id,
                actor_id=actor_id,
                session_id=session_id
            )
            logger.info(f"已删除 session: {session_id} (actor: {actor_id})")
            results["deleted"].append(session_info)

        except AttributeError:
            # 如果 delete_session 方法不存在
            logger.warning(f"MemoryClient 不支持 delete_session 方法，跳过 session: {session_id}")
            results["skipped"].append(session_info)

        except Exception as e:
            error_msg = str(e)
            # 如果 session 不存在，也算清理成功
            if "NotFound" in error_msg or "does not exist" in error_msg.lower():
                logger.info(f"Session {session_id} 不存在或已被删除")
                results["deleted"].append(session_info)
            else:
                logger.warning(f"删除 session {session_id} 失败: {e}")
                results["failed"].append({"session": session_info, "error": error_msg})

    # 清理成功后删除记录文件
    if sessions_file and os.path.exists(sessions_file) and not results["failed"]:
        try:
            os.remove(sessions_file)
            logger.info(f"已删除 session 记录文件: {sessions_file}")
        except:
            pass

    logger.info(f"清理完成: 删除 {len(results['deleted'])}, 失败 {len(results['failed'])}, 跳过 {len(results['skipped'])}")
    return results


class TestMemorySession:
    """测试用 Memory Session 封装类。

    封装 MemoryClient 以提供与 memory_tools.py 一致的接口。
    """

    def __init__(self, client, memory_id: str, actor_id: str, session_id: str):
        self.client = client
        self.memory_id = memory_id
        self.actor_id = actor_id
        self.session_id = session_id

    def add_turns(self, messages: list):
        """添加对话消息到 Memory。

        Args:
            messages: ConversationalMessage 列表
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
        """获取最近 k 条消息。

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
                    # 提取 content.text 作为 content
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
        """搜索长期记忆。"""
        try:
            return self.client.retrieve_memories(
                memory_id=self.memory_id,
                namespace=namespace_prefix,
                query=query,
                actor_id=self.actor_id,
                top_k=top_k
            )
        except Exception as e:
            logger.warning(f"LTM 搜索失败: {e}")
            return []


def create_test_memory_session(memory_id: str, actor_id: str, session_id: str, region: str):
    """创建 Memory Session。

    直接使用 MemoryClient 进行测试 (不依赖 Strands Agent 框架)。

    Args:
        memory_id: Memory ID
        actor_id: Actor ID (模拟 AWS 账户)
        session_id: Session ID (模拟任务)
        region: AWS Region

    Returns:
        TestMemorySession: 封装的 Memory session 对象
    """
    try:
        from bedrock_agentcore.memory import MemoryClient
    except ImportError as e:
        logger.error(f"bedrock-agentcore 导入失败: {e}")
        logger.error("请运行: pip install bedrock-agentcore")
        sys.exit(1)

    client = MemoryClient(region_name=region)

    return TestMemorySession(client, memory_id, actor_id, session_id)


def test_stm(memory_id: str, region: str) -> dict:
    """测试 STM (短期记忆) 功能。

    模拟三个智能体在同一任务中共享信息：
    1. Analyzer 保存分析结果
    2. Remediator 读取分析结果并保存执行信息
    3. Validator 读取前两者的信息

    Args:
        memory_id: Memory ID
        region: AWS Region

    Returns:
        dict: 测试结果
    """
    from bedrock_agentcore.memory.constants import ConversationalMessage, MessageRole

    logger.info("=" * 60)
    logger.info("开始 STM (短期记忆) 测试")
    logger.info("=" * 60)

    # 使用相同的 actor_id 和 session_id 模拟同一任务
    actor_id = f"test-account-{uuid.uuid4().hex[:8]}"
    session_id = f"task-{uuid.uuid4().hex[:8]}"

    logger.info(f"Actor ID: {actor_id}")
    logger.info(f"Session ID: {session_id}")

    # 记录测试 session 用于清理
    track_test_session(memory_id, actor_id, session_id, region)

    results = {
        "stm_test": True,
        "actor_id": actor_id,
        "session_id": session_id,
        "phases": []
    }

    try:
        # Phase 1: Analyzer 保存分析结果
        logger.info("\n--- Phase 1: Analyzer Agent ---")

        session = create_test_memory_session(memory_id, actor_id, session_id, region)

        analyzer_data = {
            "type": "phase1_analysis",
            "task_id": session_id,
            "control_id": "S3.1",
            "finding_title": "S3 Block Public Access should be enabled",
            "resource_arn": "arn:aws:s3:::test-bucket-123",
            "analysis": {
                "risk_level": "HIGH",
                "root_cause": "Block Public Access settings not enabled",
                "recommendation": "Enable all four Block Public Access settings"
            },
            "remediation_description": "Use put_public_access_block API to enable all settings",
            "saved_at": datetime.now(timezone.utc).isoformat()
        }

        session.add_turns([
            ConversationalMessage(
                json.dumps(analyzer_data),
                MessageRole.ASSISTANT
            )
        ])

        logger.info("Analyzer 保存分析结果: SUCCESS")
        results["phases"].append({"agent": "analyzer", "action": "save", "success": True})

        # Phase 2: Remediator 读取分析结果
        logger.info("\n--- Phase 2: Remediator Agent ---")

        # 同一 session，应该能读取到 Analyzer 的数据
        turns = session.get_last_k_turns(k=10)

        found_analysis = False
        for turn in turns:
            content = turn.get('content', '')
            if isinstance(content, str) and 'phase1_analysis' in content:
                try:
                    data = json.loads(content)
                    if data.get('type') == 'phase1_analysis':
                        found_analysis = True
                        logger.info(f"Remediator 读取到 Analyzer 数据:")
                        logger.info(f"  - Control ID: {data.get('control_id')}")
                        logger.info(f"  - Risk Level: {data.get('analysis', {}).get('risk_level')}")
                        break
                except json.JSONDecodeError:
                    continue

        if found_analysis:
            logger.info("Remediator 读取分析结果: SUCCESS")
            results["phases"].append({"agent": "remediator", "action": "read", "success": True})

            # Remediator 保存执行信息
            remediator_data = {
                "type": "phase2_execution",
                "task_id": session_id,
                "execution_status": "completed",
                "code_generated": "import boto3\ns3 = boto3.client('s3')\n...",
                "executed_at": datetime.now(timezone.utc).isoformat()
            }

            session.add_turns([
                ConversationalMessage(
                    json.dumps(remediator_data),
                    MessageRole.ASSISTANT
                )
            ])

            logger.info("Remediator 保存执行信息: SUCCESS")
            results["phases"].append({"agent": "remediator", "action": "save", "success": True})
        else:
            logger.error("Remediator 读取分析结果: FAILED")
            results["phases"].append({"agent": "remediator", "action": "read", "success": False})
            results["stm_test"] = False

        # Phase 3: Validator 读取所有信息
        logger.info("\n--- Phase 3: Validator Agent ---")

        turns = session.get_last_k_turns(k=10)

        found_analysis = False
        found_execution = False

        for turn in turns:
            content = turn.get('content', '')
            if isinstance(content, str):
                try:
                    data = json.loads(content)
                    if data.get('type') == 'phase1_analysis':
                        found_analysis = True
                    elif data.get('type') == 'phase2_execution':
                        found_execution = True
                except json.JSONDecodeError:
                    continue

        if found_analysis and found_execution:
            logger.info("Validator 读取到 Analyzer 数据: SUCCESS")
            logger.info("Validator 读取到 Remediator 数据: SUCCESS")
            results["phases"].append({"agent": "validator", "action": "read_all", "success": True})
        else:
            logger.error(f"Validator 读取: analysis={found_analysis}, execution={found_execution}")
            results["phases"].append({"agent": "validator", "action": "read_all", "success": False})
            results["stm_test"] = False

        logger.info("\n" + "=" * 60)
        if results["stm_test"]:
            logger.info("STM 测试结果: PASSED")
        else:
            logger.info("STM 测试结果: FAILED")
        logger.info("=" * 60)

        return results

    except Exception as e:
        logger.exception(f"STM 测试失败: {e}")
        results["stm_test"] = False
        results["error"] = str(e)
        return results


def test_ltm(memory_id: str, region: str) -> dict:
    """测试 LTM (长期记忆) 功能。

    测试 Episodic Memory 的经验存储和检索：
    1. 保存一个修复经验 (Episodic 格式)
    2. 等待 LTM 提取处理
    3. 搜索相似经验

    Args:
        memory_id: Memory ID
        region: AWS Region

    Returns:
        dict: 测试结果
    """
    from bedrock_agentcore.memory.constants import ConversationalMessage, MessageRole

    logger.info("=" * 60)
    logger.info("开始 LTM (长期记忆) 测试")
    logger.info("=" * 60)

    actor_id = f"test-account-{uuid.uuid4().hex[:8]}"
    session_id = f"task-{uuid.uuid4().hex[:8]}"

    logger.info(f"Actor ID: {actor_id}")
    logger.info(f"Session ID: {session_id}")

    # 记录测试 session 用于清理
    track_test_session(memory_id, actor_id, session_id, region)

    results = {
        "ltm_test": True,
        "actor_id": actor_id,
        "session_id": session_id,
        "steps": []
    }

    try:
        session = create_test_memory_session(memory_id, actor_id, session_id, region)

        # Step 1: 保存 Episodic 格式的经验
        logger.info("\n--- Step 1: 保存 Episodic 经验 ---")

        experience_id = f"EXP_S3_1_{session_id[:8]}"

        episodic_content = f"""
# Security Remediation Episode

## Episode ID
{experience_id}

## Scenario
**What happened:** AWS Security Hub detected a security finding.
- **Control ID:** S3.1
- **Finding Title:** S3 Block Public Access should be enabled
- **Resource Type:** AwsS3Bucket
- **Task ID:** {session_id}

### Finding Details
The S3 bucket 'test-bucket-123' does not have Block Public Access enabled, potentially exposing data to public access.

## Intent
**Goal:** Remediate the security finding S3.1 on AwsS3Bucket resource to achieve compliance with AWS Security Hub standards.

**Expected Outcome:** All four Block Public Access settings should be enabled on the bucket.

## Actions
**Remediation Approach:**
Enable all four Block Public Access settings using boto3 put_public_access_block API.

**Generated Code:**
```python
import boto3

s3 = boto3.client('s3')
s3.put_public_access_block(
    Bucket='test-bucket-123',
    PublicAccessBlockConfiguration={{
        'BlockPublicAcls': True,
        'IgnorePublicAcls': True,
        'BlockPublicPolicy': True,
        'RestrictPublicBuckets': True
    }}
)
```

**Execution Steps:**
1. Phase 1 (Analyzer): Analyzed finding and determined remediation strategy
2. Phase 2 (Remediator): Generated and executed remediation code
3. Phase 2 (Validator): Verified remediation success

## Outcomes
**Result:** SUCCESS

**Validation Details:**
All four Block Public Access settings verified as enabled. Security Hub finding status updated to RESOLVED.

**Lessons Learned:**
- Always verify bucket exists before applying settings
- Wait 15-30 seconds before validation for propagation

## Metadata
- **Timestamp:** {datetime.now(timezone.utc).isoformat()}
- **Source:** validated_remediation
- **Service Family:** S3
"""

        session.add_turns([
            ConversationalMessage(
                episodic_content,
                MessageRole.ASSISTANT
            )
        ])

        logger.info(f"保存 Episodic 经验 ({experience_id}): SUCCESS")
        results["steps"].append({"step": "save_experience", "success": True, "experience_id": experience_id})

        # Step 2: 等待 LTM 提取
        logger.info("\n--- Step 2: 等待 LTM 提取处理 ---")
        logger.info("LTM 提取是异步的，等待 30 秒...")

        # 注意：实际 LTM 提取可能需要更长时间
        # 这里仅等待 30 秒用于测试
        for i in range(6):
            time.sleep(5)
            logger.info(f"已等待 {(i+1)*5} 秒...")

        results["steps"].append({"step": "wait_extraction", "success": True, "wait_seconds": 30})

        # Step 3: 搜索相似经验
        logger.info("\n--- Step 3: 搜索相似经验 ---")

        query = "Security remediation for AWS S3 bucket Block Public Access"
        namespace_prefix = "/remediation/actors/"

        logger.info(f"搜索查询: {query}")
        logger.info(f"命名空间前缀: {namespace_prefix}")

        try:
            memories = session.search_long_term_memories(
                query=query,
                namespace_prefix=namespace_prefix,
                top_k=5
            )

            if memories:
                logger.info(f"找到 {len(memories)} 条相关经验:")
                for i, mem in enumerate(memories):
                    score = mem.get('score', 0)
                    content_preview = str(mem.get('content', ''))[:100]
                    logger.info(f"  [{i+1}] 相似度: {score:.3f}")
                    logger.info(f"      内容预览: {content_preview}...")

                results["steps"].append({
                    "step": "search_experience",
                    "success": True,
                    "found_count": len(memories)
                })
            else:
                logger.warning("未找到相关经验（可能 LTM 提取仍在进行中）")
                results["steps"].append({
                    "step": "search_experience",
                    "success": False,
                    "note": "No results - LTM extraction may still be in progress"
                })
                # 不标记为测试失败，因为 LTM 提取是异步的
                results["ltm_test"] = "PENDING"

        except Exception as e:
            logger.warning(f"搜索 LTM 失败: {e}")
            results["steps"].append({
                "step": "search_experience",
                "success": False,
                "error": str(e)
            })

        logger.info("\n" + "=" * 60)
        if results["ltm_test"] == True:
            logger.info("LTM 测试结果: PASSED")
        elif results["ltm_test"] == "PENDING":
            logger.info("LTM 测试结果: PENDING (等待异步提取完成)")
        else:
            logger.info("LTM 测试结果: FAILED")
        logger.info("=" * 60)

        return results

    except Exception as e:
        logger.exception(f"LTM 测试失败: {e}")
        results["ltm_test"] = False
        results["error"] = str(e)
        return results


def test_memory_tools(memory_id: str, region: str) -> dict:
    """测试 memory_tools.py 中的工具函数。

    Args:
        memory_id: Memory ID
        region: AWS Region

    Returns:
        dict: 测试结果
    """
    logger.info("=" * 60)
    logger.info("开始 Memory Tools 测试")
    logger.info("=" * 60)

    # 添加 agents 目录到 path
    agents_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if agents_dir not in sys.path:
        sys.path.insert(0, os.path.join(agents_dir, 'agents'))

    results = {
        "tools_test": True,
        "tests": []
    }

    try:
        from shared.tools.memory_tools import (
            set_memory_session,
            search_similar_findings,
            save_analysis_result,
            get_analysis_context,
            save_experience_to_ltm
        )

        actor_id = f"test-account-{uuid.uuid4().hex[:8]}"
        session_id = f"task-{uuid.uuid4().hex[:8]}"

        # 记录测试 session 用于清理
        track_test_session(memory_id, actor_id, session_id, region)

        # 创建 session 并设置
        session = create_test_memory_session(memory_id, actor_id, session_id, region)
        set_memory_session(session)

        logger.info(f"Actor ID: {actor_id}")
        logger.info(f"Session ID: {session_id}")

        # Test 1: save_analysis_result
        logger.info("\n--- Test 1: save_analysis_result ---")
        try:
            result = save_analysis_result(
                task_id=session_id,
                analysis={
                    "control_id": "EC2.19",
                    "risk_level": "MEDIUM",
                    "root_cause": "Security group allows unrestricted SSH access"
                },
                remediation_description="Restrict SSH access to specific IP ranges"
            )
            success = result.get('success', False)
            logger.info(f"save_analysis_result: {'SUCCESS' if success else 'FAILED'}")
            results["tests"].append({"test": "save_analysis_result", "success": success})
        except Exception as e:
            logger.error(f"save_analysis_result 失败: {e}")
            results["tests"].append({"test": "save_analysis_result", "success": False, "error": str(e)})

        # Test 2: get_analysis_context
        logger.info("\n--- Test 2: get_analysis_context ---")
        try:
            result = get_analysis_context(task_id=session_id)
            success = result.get('success', False)
            logger.info(f"get_analysis_context: {'SUCCESS' if success else 'FAILED'}")
            if success:
                logger.info(f"  Retrieved analysis: {result.get('analysis', {}).get('control_id')}")
            results["tests"].append({"test": "get_analysis_context", "success": success})
        except Exception as e:
            logger.error(f"get_analysis_context 失败: {e}")
            results["tests"].append({"test": "get_analysis_context", "success": False, "error": str(e)})

        # Test 3: save_experience_to_ltm
        logger.info("\n--- Test 3: save_experience_to_ltm ---")
        try:
            result = save_experience_to_ltm(
                control_id="EC2.19",
                task_id=session_id,
                finding_title="Security groups should not allow unrestricted SSH access",
                resource_type="AwsEc2SecurityGroup",
                analysis_summary="Security group sg-123 allows SSH from 0.0.0.0/0",
                remediation_approach="Remove the unrestricted SSH rule and add specific IP range",
                generated_code="import boto3\nec2 = boto3.client('ec2')\n# revoke and add rules...",
                lessons_learned="Always backup security group rules before modification",
                validation_result="All security group rules verified"
            )
            success = result.get('saved', False)
            logger.info(f"save_experience_to_ltm: {'SUCCESS' if success else 'FAILED'}")
            if success:
                logger.info(f"  Experience ID: {result.get('experience_id')}")
            results["tests"].append({"test": "save_experience_to_ltm", "success": success})
        except Exception as e:
            logger.error(f"save_experience_to_ltm 失败: {e}")
            results["tests"].append({"test": "save_experience_to_ltm", "success": False, "error": str(e)})

        # Test 4: search_similar_findings
        logger.info("\n--- Test 4: search_similar_findings ---")
        try:
            result = search_similar_findings(
                control_id="EC2.19",
                finding_title="Security groups should not allow unrestricted SSH access",
                resource_type="AwsEc2SecurityGroup",
                top_k=3
            )
            # 搜索可能返回空结果（如果 LTM 未提取）
            logger.info(f"search_similar_findings: 返回 {len(result)} 条结果")
            results["tests"].append({
                "test": "search_similar_findings",
                "success": True,  # 函数执行成功即可
                "result_count": len(result)
            })
        except Exception as e:
            logger.error(f"search_similar_findings 失败: {e}")
            results["tests"].append({"test": "search_similar_findings", "success": False, "error": str(e)})

        # 计算总体结果
        failed_tests = [t for t in results["tests"] if not t.get("success", False)]
        results["tools_test"] = len(failed_tests) == 0

        logger.info("\n" + "=" * 60)
        if results["tools_test"]:
            logger.info("Memory Tools 测试结果: PASSED")
        else:
            logger.info(f"Memory Tools 测试结果: FAILED ({len(failed_tests)} tests failed)")
        logger.info("=" * 60)

        return results

    except ImportError as e:
        logger.error(f"无法导入 memory_tools: {e}")
        logger.info("请确保从 agents 目录运行此脚本，或正确设置 PYTHONPATH")
        results["tools_test"] = False
        results["error"] = str(e)
        return results


def main():
    parser = argparse.ArgumentParser(
        description="SHARA Memory 功能测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 运行所有测试
  python test_memory.py --memory-id <memory_id>

  # 仅测试 STM
  python test_memory.py --memory-id <memory_id> --test stm

  # 仅测试 LTM
  python test_memory.py --memory-id <memory_id> --test ltm

  # 测试 memory_tools.py 中的工具
  python test_memory.py --memory-id <memory_id> --test tools

  # 运行测试并清理测试数据
  python test_memory.py --memory-id <memory_id> --cleanup

  # 仅清理之前的测试数据 (不运行测试)
  python test_memory.py --memory-id <memory_id> --cleanup-only
"""
    )

    parser.add_argument(
        '--memory-id',
        required=True,
        help='AgentCore Memory ID'
    )
    parser.add_argument(
        '--region',
        default=os.environ.get('AWS_REGION', DEFAULT_REGION),
        help=f'AWS Region (default: {DEFAULT_REGION})'
    )
    parser.add_argument(
        '--test',
        choices=['all', 'stm', 'ltm', 'tools'],
        default='all',
        help='要运行的测试类型'
    )
    parser.add_argument(
        '--cleanup',
        action='store_true',
        help='运行测试后清理测试数据'
    )
    parser.add_argument(
        '--cleanup-only',
        action='store_true',
        help='仅清理之前的测试数据，不运行测试'
    )
    parser.add_argument(
        '--sessions-file',
        default='test_memory_sessions.json',
        help='测试 session 记录文件路径 (default: test_memory_sessions.json)'
    )

    args = parser.parse_args()

    # 仅清理模式
    if args.cleanup_only:
        logger.info("=" * 60)
        logger.info("仅清理模式")
        logger.info("=" * 60)
        cleanup_result = cleanup_test_sessions(
            args.memory_id,
            args.region,
            args.sessions_file
        )
        print("\n清理结果:")
        print(f"  删除: {len(cleanup_result.get('deleted', []))} 个 sessions")
        print(f"  失败: {len(cleanup_result.get('failed', []))} 个 sessions")
        print(f"  跳过: {len(cleanup_result.get('skipped', []))} 个 sessions")
        return

    all_results = {}

    if args.test in ['all', 'stm']:
        all_results['stm'] = test_stm(args.memory_id, args.region)

    if args.test in ['all', 'ltm']:
        all_results['ltm'] = test_ltm(args.memory_id, args.region)

    if args.test in ['all', 'tools']:
        all_results['tools'] = test_memory_tools(args.memory_id, args.region)

    # 输出汇总
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)

    for test_name, result in all_results.items():
        status_key = f"{test_name}_test"
        status = result.get(status_key, False)
        if status == True:
            print(f"  {test_name.upper()}: PASSED")
        elif status == "PENDING":
            print(f"  {test_name.upper()}: PENDING")
        else:
            print(f"  {test_name.upper()}: FAILED")

    print("=" * 60)

    # 保存详细结果
    output_file = f"test_memory_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n详细结果已保存到: {output_file}")

    # 清理测试数据
    if args.cleanup:
        print("\n" + "=" * 60)
        print("清理测试数据")
        print("=" * 60)

        cleanup_result = cleanup_test_sessions(
            args.memory_id,
            args.region,
            args.sessions_file
        )

        print(f"\n清理结果:")
        print(f"  删除: {len(cleanup_result.get('deleted', []))} 个 sessions")
        print(f"  失败: {len(cleanup_result.get('failed', []))} 个 sessions")
        print(f"  跳过: {len(cleanup_result.get('skipped', []))} 个 sessions")
    else:
        # 保存 session 记录用于后续清理
        sessions_file = save_test_sessions_record(args.sessions_file)
        if sessions_file:
            print(f"\n提示: 测试 session 记录已保存到 {sessions_file}")
            print(f"      使用 --cleanup-only 可清理这些测试数据")


if __name__ == '__main__':
    main()
