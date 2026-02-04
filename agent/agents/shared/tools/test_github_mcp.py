#!/usr/bin/env python3
"""
GitHub MCP Client 测试脚本

测试 GitHub MCP 集成是否正常工作：
1. Secrets Manager PAT 获取
2. GitHub MCP Server 连接
3. 基本 API 调用

使用方法：
    # 本地测试 (需要 AWS 凭证)
    cd /Users/yifeiwf/Code/awsome2/agent/agents
    PYTHONPATH=.. python -m shared.tools.test_github_mcp

    # 或直接运行
    python test_github_mcp.py
"""
import os
import sys
import logging

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_secrets_manager():
    """测试 Secrets Manager PAT 获取"""
    print("\n" + "="*60)
    print("Test 1: Secrets Manager PAT 获取")
    print("="*60)

    try:
        from shared.tools.github_mcp_client import get_github_pat

        pat = get_github_pat()

        # 只显示前后几个字符，保护 token
        masked_pat = pat[:10] + "..." + pat[-4:] if len(pat) > 14 else "***"
        print(f"✓ 成功获取 GitHub PAT: {masked_pat}")
        print(f"  PAT 长度: {len(pat)} 字符")
        return True

    except Exception as e:
        print(f"✗ 获取 PAT 失败: {e}")
        return False


def test_mcp_client_creation():
    """测试 MCP Client 创建"""
    print("\n" + "="*60)
    print("Test 2: GitHub MCP Client 创建")
    print("="*60)

    try:
        from shared.tools.github_mcp_client import get_github_mcp_client, reset_github_mcp_client

        # 重置以确保创建新客户端
        reset_github_mcp_client()

        client = get_github_mcp_client()
        print(f"✓ 成功创建 MCP Client: {type(client).__name__}")
        return True

    except ImportError as e:
        print(f"✗ 导入 MCP 依赖失败: {e}")
        print("  请确保已安装: pip install mcp strands")
        return False
    except Exception as e:
        print(f"✗ 创建 MCP Client 失败: {e}")
        return False


def test_read_file():
    """测试读取 GitHub 文件"""
    print("\n" + "="*60)
    print("Test 3: 读取 GitHub 文件 (agent/infra/README.md)")
    print("="*60)

    try:
        from shared.tools.github_mcp_client import read_github_file

        # 注意: awsome 仓库默认分支是 master
        result = read_github_file(
            owner="Wyifei",
            repo="awsome",
            path="agent/infra/README.md",
            ref="master"
        )

        if result.get("success"):
            content = result.get("content", "")
            print(f"✓ 成功读取文件")
            print(f"  内容长度: {len(content)} 字符")
            print(f"  前 100 字符: {content[:100]}...")
            return True
        else:
            print(f"✗ 读取文件失败: {result.get('error')}")
            return False

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_search_container_inventory():
    """测试搜索容器清单"""
    print("\n" + "="*60)
    print("Test 4: 搜索容器清单")
    print("="*60)

    try:
        from shared.tools.github_mcp_client import search_container_inventory

        # 测试搜索 shara-analyzer (container-inventory.json 中定义的 ECR pattern)
        result = search_container_inventory(
            ecr_repository="shara-analyzer",
            github_owner="Wyifei",
            github_repo="awsome"
        )

        if result.get("success"):
            if result.get("found"):
                service = result.get("service", {})
                print(f"✓ 找到匹配的服务")
                print(f"  服务名称: {service.get('name')}")
                print(f"  服务路径: {service.get('path')}")
                print(f"  编程语言: {service.get('language')}")
            else:
                print(f"⚠ 未找到匹配的服务 (可能是正常的)")
                print(f"  可用模式: {result.get('available_patterns')}")
            return True
        else:
            print(f"✗ 搜索失败: {result.get('error')}")
            return False

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_get_service_metadata():
    """测试获取服务元数据"""
    print("\n" + "="*60)
    print("Test 5: 获取服务元数据 (SERVICE.yaml)")
    print("="*60)

    try:
        from shared.tools.github_mcp_client import get_service_metadata, reset_github_mcp_client

        # 重置客户端以避免会话问题
        reset_github_mcp_client()

        result = get_service_metadata(
            service_path="agent/agents/analyzer",
            github_owner="Wyifei",
            github_repo="awsome"
        )

        if result.get("success"):
            metadata = result.get("metadata", {})
            print(f"✓ 成功读取 SERVICE.yaml")
            print(f"  服务名称: {metadata.get('name')}")
            print(f"  服务类型: {metadata.get('type')}")
            if metadata.get('vulnerability_remediation'):
                print(f"  漏洞修复配置: 已定义")
            return True
        else:
            print(f"✗ 读取失败: {result.get('error')}")
            # 如果文件不存在，这可能是预期的
            if "not found" in result.get('error', '').lower():
                print("  (SERVICE.yaml 可能尚未创建)")
            return False

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """运行所有测试"""
    print("\n")
    print("="*60)
    print("GitHub MCP Client 集成测试")
    print("="*60)

    results = {}

    # Test 1: Secrets Manager
    results["secrets_manager"] = test_secrets_manager()

    if not results["secrets_manager"]:
        print("\n⚠ Secrets Manager 测试失败，跳过后续测试")
        return results

    # Test 2: MCP Client Creation
    results["mcp_client"] = test_mcp_client_creation()

    if not results["mcp_client"]:
        print("\n⚠ MCP Client 创建失败，跳过后续测试")
        return results

    # Test 3: Read File
    results["read_file"] = test_read_file()

    # Test 4: Search Container Inventory
    results["search_inventory"] = test_search_container_inventory()

    # Test 5: Get Service Metadata
    results["service_metadata"] = test_get_service_metadata()

    # Summary
    print("\n")
    print("="*60)
    print("测试结果汇总")
    print("="*60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {name}: {status}")

    print(f"\n总计: {passed}/{total} 测试通过")

    if passed == total:
        print("\n🎉 所有测试通过! GitHub MCP 集成工作正常。")
    else:
        print(f"\n⚠ {total - passed} 个测试失败，请检查配置。")

    return results


if __name__ == "__main__":
    # 添加父目录到 Python 路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(os.path.dirname(current_dir))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    results = run_all_tests()

    # 如果有测试失败，返回非零退出码
    if not all(results.values()):
        sys.exit(1)
