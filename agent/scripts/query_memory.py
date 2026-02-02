#!/usr/bin/env python3
"""
SHARA Memory 查询脚本

用于调试和检查 AgentCore Memory 内容：
1. 查询 STM (短期记忆) - 特定 session 的 events
2. 查询 LTM (长期记忆) - 搜索 episodic memories
3. 列出 sessions
4. 检查 memory 状态

使用方法:
  # 查询 LTM (搜索修复经验)
  python query_memory.py ltm --memory-id <memory_id> --actor-id <actor_id> --query "S3 Block Public Access"

  # 查询 STM (查看 session 中的 events)
  python query_memory.py stm --memory-id <memory_id> --actor-id <actor_id> --session-id <session_id>

  # 列出所有可用的 namespaces
  python query_memory.py namespaces --memory-id <memory_id> --actor-id <actor_id>

  # 查看 memory 状态
  python query_memory.py status --memory-id <memory_id>
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DEFAULT_REGION = "ap-northeast-1"

# Namespace patterns (must match create_shara_memory.py)
# NOTE: AgentCore Memory API 不支持通配符，必须使用完全匹配的 namespace
# Memory Strategy 配置使用 {actorId} 占位符，在运行时需要替换为实际值
EPISODE_NAMESPACE_PATTERN = "/remediation/actors/{actorId}/"
REFLECTION_NAMESPACE_PATTERN = "/remediation/actors/{actorId}/"

# 兼容旧代码的别名
EPISODE_NAMESPACE_PREFIX = "/remediation/actors/"
REFLECTION_NAMESPACE_PREFIX = "/remediation/actors/"


def get_memory_client(region: str):
    """获取 MemoryClient。"""
    try:
        from bedrock_agentcore.memory import MemoryClient
        return MemoryClient(region_name=region)
    except ImportError as e:
        logger.error(f"bedrock-agentcore 未安装: {e}")
        logger.error("请运行: pip install bedrock-agentcore")
        sys.exit(1)


def query_ltm(
    memory_id: str,
    actor_id: str,
    query: str,
    namespace: str = None,
    top_k: int = 10,
    region: str = DEFAULT_REGION,
    show_full: bool = False
):
    """查询 LTM (长期记忆)。

    Args:
        memory_id: Memory ID
        actor_id: Actor ID
        query: 搜索查询
        namespace: 命名空间前缀 (默认尝试多个)
        top_k: 返回结果数量
        region: AWS Region
    """
    client = get_memory_client(region)

    print("\n" + "=" * 80)
    print("LTM (长期记忆) 查询")
    print("=" * 80)
    print(f"Memory ID: {memory_id}")
    print(f"Actor ID: {actor_id}")
    print(f"Query: {query}")
    print(f"Top K: {top_k}")
    print(f"Region: {region}")
    print("=" * 80)

    # 尝试不同的 namespace 前缀
    namespaces_to_try = []
    if namespace:
        namespaces_to_try.append(namespace)
    else:
        # 默认尝试的 namespace 列表
        # 首先尝试正确的 namespace（包含 actorId）
        correct_namespace = EPISODE_NAMESPACE_PATTERN.replace("{actorId}", actor_id)
        namespaces_to_try = [
            correct_namespace,  # 正确的完整 namespace
            f"/remediation/actors/{actor_id}/",  # 备用格式
        ]

    total_results = []

    for ns in namespaces_to_try:
        print(f"\n--- 搜索 namespace: {ns} ---")

        try:
            results = client.retrieve_memories(
                memory_id=memory_id,
                namespace=ns,
                query=query,
                actor_id=actor_id,
                top_k=top_k
            )

            if results:
                print(f"找到 {len(results)} 条结果:")
                for i, mem in enumerate(results):
                    score = mem.get('score', 0)
                    raw_content = mem.get('content', '')
                    memory_record_id = mem.get('memoryRecordId', '')
                    namespace_found = mem.get('namespace', '')

                    # 处理 content 格式：可能是字符串或 {'text': '...'} 格式
                    if isinstance(raw_content, dict):
                        content = raw_content.get('text', str(raw_content))
                    else:
                        content = str(raw_content) if raw_content else ''

                    print(f"\n  [{i+1}] Score: {score:.4f}")
                    print(f"      Record ID: {memory_record_id}")
                    print(f"      Namespace: {namespace_found}")

                    if show_full:
                        # 显示完整内容
                        print(f"      Content ({len(content)} chars):")
                        # 尝试格式化 JSON
                        try:
                            content_json = json.loads(content)
                            print(json.dumps(content_json, indent=6, ensure_ascii=False))
                        except:
                            print(f"      {content}")
                    else:
                        # 截取内容预览
                        preview = content[:200].replace('\n', ' ') if content else '(empty)'
                        print(f"      Content preview: {preview}...")

                    total_results.append({
                        "namespace_searched": ns,
                        "score": score,
                        "content": content,
                        "record_id": memory_record_id
                    })
            else:
                print("未找到结果")

        except Exception as e:
            print(f"搜索失败: {e}")

    print("\n" + "=" * 80)
    print(f"总计找到 {len(total_results)} 条结果")
    print("=" * 80)

    return total_results


def query_stm(
    memory_id: str,
    actor_id: str,
    session_id: str,
    k: int = 50,
    region: str = DEFAULT_REGION
):
    """查询 STM (短期记忆)。

    Args:
        memory_id: Memory ID
        actor_id: Actor ID
        session_id: Session ID
        k: 返回的最近 k 条消息
        region: AWS Region
    """
    client = get_memory_client(region)

    print("\n" + "=" * 80)
    print("STM (短期记忆) 查询")
    print("=" * 80)
    print(f"Memory ID: {memory_id}")
    print(f"Actor ID: {actor_id}")
    print(f"Session ID: {session_id}")
    print(f"K (最近消息数): {k}")
    print(f"Region: {region}")
    print("=" * 80)

    try:
        # 获取最近的 events
        events = client.get_last_k_turns(
            memory_id=memory_id,
            actor_id=actor_id,
            session_id=session_id,
            k=k
        )

        print(f"\n找到 {len(events)} 个 events:")

        for i, event in enumerate(events):
            print(f"\n--- Event {i+1} ---")

            if isinstance(event, list):
                for j, msg in enumerate(event):
                    content = msg.get('content', {})
                    if isinstance(content, dict):
                        content_text = content.get('text', '')
                    else:
                        content_text = str(content)

                    role = msg.get('role', '')

                    # 尝试解析 JSON 内容以显示类型
                    content_type = "unknown"
                    try:
                        data = json.loads(content_text)
                        content_type = data.get('type', 'unknown')
                    except:
                        pass

                    print(f"  Message {j+1}:")
                    print(f"    Role: {role}")
                    print(f"    Type: {content_type}")
                    print(f"    Content length: {len(content_text)} chars")
                    print(f"    Preview: {content_text[:150]}...")

            elif isinstance(event, dict):
                content = event.get('content', {})
                if isinstance(content, dict):
                    content_text = content.get('text', '')
                else:
                    content_text = str(content)

                role = event.get('role', '')

                content_type = "unknown"
                try:
                    data = json.loads(content_text)
                    content_type = data.get('type', 'unknown')
                except:
                    pass

                print(f"  Role: {role}")
                print(f"  Type: {content_type}")
                print(f"  Content length: {len(content_text)} chars")
                print(f"  Preview: {content_text[:150]}...")

        print("\n" + "=" * 80)
        return events

    except Exception as e:
        logger.error(f"查询 STM 失败: {e}")
        return []


def list_memory_records(
    memory_id: str,
    actor_id: str,
    namespace: str = None,
    region: str = DEFAULT_REGION
):
    """列出 Memory Records。

    使用 list_memory_records API (如果可用)。
    """
    client = get_memory_client(region)

    print("\n" + "=" * 80)
    print("列出 Memory Records")
    print("=" * 80)
    print(f"Memory ID: {memory_id}")
    print(f"Actor ID: {actor_id}")
    print(f"Namespace: {namespace or '(default)'}")
    print(f"Region: {region}")
    print("=" * 80)

    try:
        # 尝试调用 list_memory_records (如果 API 支持)
        if hasattr(client, 'list_memory_records'):
            kwargs = {
                'memory_id': memory_id,
                'actor_id': actor_id,
            }
            if namespace:
                kwargs['namespace'] = namespace

            records = client.list_memory_records(**kwargs)
            print(f"\n找到 {len(records)} 条 records")

            for i, record in enumerate(records):
                print(f"\n  [{i+1}] {record}")

            return records
        else:
            print("\nMemoryClient 不支持 list_memory_records 方法")
            print("尝试使用 retrieve_memories 进行通用搜索...")

            # 使用通用查询
            return query_ltm(
                memory_id=memory_id,
                actor_id=actor_id,
                query="security remediation",
                namespace=namespace,
                region=region
            )

    except Exception as e:
        logger.error(f"列出 records 失败: {e}")
        return []


def get_memory_status(memory_id: str, region: str = DEFAULT_REGION):
    """获取 Memory 状态。"""
    import boto3

    print("\n" + "=" * 80)
    print("Memory 状态")
    print("=" * 80)
    print(f"Memory ID: {memory_id}")
    print(f"Region: {region}")
    print("=" * 80)

    try:
        client = boto3.client('bedrock-agentcore-control', region_name=region)
        response = client.get_memory(memoryId=memory_id)
        memory = response.get('memory', {})

        print(f"\n基本信息:")
        print(f"  Name: {memory.get('name')}")
        print(f"  ID: {memory.get('id')}")
        print(f"  ARN: {memory.get('arn')}")
        print(f"  Status: {memory.get('status')}")
        print(f"  Event Expiry: {memory.get('eventExpiryDuration')} days")
        print(f"  Created: {memory.get('createdAt')}")
        print(f"  Updated: {memory.get('updatedAt')}")

        strategies = memory.get('strategies', [])
        if strategies:
            print(f"\n策略 ({len(strategies)}):")
            for strat in strategies:
                print(f"\n  Strategy: {strat.get('name')}")
                print(f"    ID: {strat.get('strategyId')}")
                print(f"    Type: {strat.get('type')}")
                print(f"    Status: {strat.get('status')}")
                print(f"    Namespaces: {strat.get('namespaces')}")

        print("\n" + "=" * 80)
        return memory

    except Exception as e:
        logger.error(f"获取 Memory 状态失败: {e}")
        return None


def check_ltm_extraction_status(
    memory_id: str,
    actor_id: str,
    session_id: str,
    region: str = DEFAULT_REGION
):
    """检查 LTM 提取状态。

    通过比较 STM 和 LTM 内容来判断提取是否完成。
    """
    print("\n" + "=" * 80)
    print("LTM 提取状态检查")
    print("=" * 80)
    print(f"Memory ID: {memory_id}")
    print(f"Actor ID: {actor_id}")
    print(f"Session ID: {session_id}")
    print("=" * 80)

    client = get_memory_client(region)

    # 1. 检查 STM 中的 ltm_experience 类型消息
    print("\n--- Step 1: 检查 STM 中的经验数据 ---")
    stm_experiences = []

    try:
        events = client.get_last_k_turns(
            memory_id=memory_id,
            actor_id=actor_id,
            session_id=session_id,
            k=100
        )

        for event in events:
            messages = event if isinstance(event, list) else [event]
            for msg in messages:
                content = msg.get('content', {})
                if isinstance(content, dict):
                    content_text = content.get('text', '')
                else:
                    content_text = str(content)

                try:
                    data = json.loads(content_text)
                    if data.get('type') == 'ltm_experience':
                        stm_experiences.append(data)
                        print(f"  Found ltm_experience: {data.get('experience_id')}")
                        print(f"    Control ID: {data.get('control_id')}")
                        print(f"    Task ID: {data.get('task_id')}")
                except:
                    pass

        print(f"\nSTM 中找到 {len(stm_experiences)} 条 ltm_experience 记录")

    except Exception as e:
        print(f"检查 STM 失败: {e}")

    # 2. 检查 LTM 中的提取结果
    print("\n--- Step 2: 检查 LTM 中的提取结果 ---")
    ltm_results = []

    for exp in stm_experiences:
        control_id = exp.get('control_id', '')
        query = f"Control ID {control_id} security remediation"

        # 使用正确的 namespace（包含 actorId）
        episode_namespace = EPISODE_NAMESPACE_PATTERN.replace("{actorId}", actor_id)
        try:
            results = client.retrieve_memories(
                memory_id=memory_id,
                namespace=episode_namespace,
                query=query,
                actor_id=actor_id,
                top_k=5
            )

            if results:
                for r in results:
                    content = r.get('content', '')
                    if control_id in str(content):
                        ltm_results.append(r)
                        print(f"  Found LTM record for {control_id}")
                        print(f"    Score: {r.get('score', 0):.4f}")

        except Exception as e:
            print(f"  搜索 {control_id} 失败: {e}")

    print(f"\nLTM 中找到 {len(ltm_results)} 条相关记录")

    # 3. 分析
    print("\n--- 分析结果 ---")
    if not stm_experiences:
        print("❌ STM 中没有找到 ltm_experience 记录")
        print("   可能原因: Validator 没有调用 save_experience_to_ltm")
    elif not ltm_results:
        print("⏳ STM 有经验数据但 LTM 中未找到")
        print("   可能原因:")
        print("   1. LTM 提取正在进行中 (异步，可能需要几分钟)")
        print("   2. Namespace 不匹配")
        print("   3. Actor ID 不一致")
    else:
        extraction_rate = len(ltm_results) / len(stm_experiences) * 100
        print(f"✓ 提取率: {extraction_rate:.1f}% ({len(ltm_results)}/{len(stm_experiences)})")

    print("\n" + "=" * 80)


def export_results(results, output_file: str):
    """导出查询结果到文件。"""
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str, ensure_ascii=False)
    print(f"\n结果已导出到: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="SHARA Memory 查询工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 查询 LTM (搜索修复经验)
  python query_memory.py ltm --memory-id shara_memory-eQ5Cx9Cfzv --actor-id 870414140965 --query "S3 Block Public Access"

  # 查询 STM (查看 session 中的 events)
  python query_memory.py stm --memory-id shara_memory-eQ5Cx9Cfzv --actor-id 870414140965 --session-id task-abc123

  # 检查 LTM 提取状态
  python query_memory.py check --memory-id shara_memory-eQ5Cx9Cfzv --actor-id 870414140965 --session-id task-abc123

  # 查看 memory 状态
  python query_memory.py status --memory-id shara_memory-eQ5Cx9Cfzv 

  # 导出结果到文件
  python query_memory.py ltm --memory-id shara_memory-eQ5Cx9Cfzv --actor-id 870414140965 --query "S3" --output results.json
"""
    )

    subparsers = parser.add_subparsers(dest='command', help='命令')

    # Common arguments
    region_kwargs = {
        'default': os.environ.get('AWS_REGION', DEFAULT_REGION),
        'help': f'AWS Region (default: from AWS_REGION env or {DEFAULT_REGION})'
    }

    # ltm command
    ltm_parser = subparsers.add_parser('ltm', help='查询 LTM (长期记忆)')
    ltm_parser.add_argument('--memory-id', required=True, help='Memory ID')
    ltm_parser.add_argument('--actor-id', required=True, help='Actor ID (通常是 AWS Account ID)')
    ltm_parser.add_argument('--query', '-q', required=True, help='搜索查询')
    ltm_parser.add_argument('--namespace', '-n', help='命名空间前缀 (默认尝试多个)')
    ltm_parser.add_argument('--top-k', '-k', type=int, default=10, help='返回结果数量 (default: 10)')
    ltm_parser.add_argument('--full', '-f', action='store_true', help='显示完整内容而非截取预览')
    ltm_parser.add_argument('--region', **region_kwargs)
    ltm_parser.add_argument('--output', '-o', help='导出结果到文件')

    # stm command
    stm_parser = subparsers.add_parser('stm', help='查询 STM (短期记忆)')
    stm_parser.add_argument('--memory-id', required=True, help='Memory ID')
    stm_parser.add_argument('--actor-id', required=True, help='Actor ID')
    stm_parser.add_argument('--session-id', required=True, help='Session ID (任务 ID)')
    stm_parser.add_argument('--k', type=int, default=50, help='返回最近 k 条消息 (default: 50)')
    stm_parser.add_argument('--region', **region_kwargs)
    stm_parser.add_argument('--output', '-o', help='导出结果到文件')

    # status command
    status_parser = subparsers.add_parser('status', help='查看 Memory 状态')
    status_parser.add_argument('--memory-id', required=True, help='Memory ID')
    status_parser.add_argument('--region', **region_kwargs)

    # check command
    check_parser = subparsers.add_parser('check', help='检查 LTM 提取状态')
    check_parser.add_argument('--memory-id', required=True, help='Memory ID')
    check_parser.add_argument('--actor-id', required=True, help='Actor ID')
    check_parser.add_argument('--session-id', required=True, help='Session ID')
    check_parser.add_argument('--region', **region_kwargs)

    # records command
    records_parser = subparsers.add_parser('records', help='列出 Memory Records')
    records_parser.add_argument('--memory-id', required=True, help='Memory ID')
    records_parser.add_argument('--actor-id', required=True, help='Actor ID')
    records_parser.add_argument('--namespace', '-n', help='命名空间')
    records_parser.add_argument('--region', **region_kwargs)

    args = parser.parse_args()

    if args.command == 'ltm':
        results = query_ltm(
            memory_id=args.memory_id,
            actor_id=args.actor_id,
            query=args.query,
            namespace=args.namespace,
            top_k=args.top_k,
            region=args.region,
            show_full=args.full
        )
        if args.output:
            export_results(results, args.output)

    elif args.command == 'stm':
        results = query_stm(
            memory_id=args.memory_id,
            actor_id=args.actor_id,
            session_id=args.session_id,
            k=args.k,
            region=args.region
        )
        if args.output:
            export_results(results, args.output)

    elif args.command == 'status':
        get_memory_status(
            memory_id=args.memory_id,
            region=args.region
        )

    elif args.command == 'check':
        check_ltm_extraction_status(
            memory_id=args.memory_id,
            actor_id=args.actor_id,
            session_id=args.session_id,
            region=args.region
        )

    elif args.command == 'records':
        list_memory_records(
            memory_id=args.memory_id,
            actor_id=args.actor_id,
            namespace=args.namespace,
            region=args.region
        )

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
