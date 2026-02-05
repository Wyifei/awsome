"""
GitHub MCP Client - 通过 Strands SDK 调用 GitHub 远程 MCP Server

用于容器漏洞修复工作流：
- 读取 GitHub 仓库文件 (requirements.txt, pom.xml, package.json 等)
- 创建 Pull Request 修复依赖版本
- 验证 PR 是否创建成功

架构：Agent → Secrets Manager (获取 PAT) → GitHub Remote MCP Server
"""
import json
import logging
import threading
from typing import Optional, Any
from datetime import datetime, timezone

import boto3
from strands import tool

from shared.config import get_config

logger = logging.getLogger(__name__)

# Global MCP client instance (singleton)
_github_mcp_client = None
# Lock for serializing MCP client access (GitHub MCP doesn't support concurrent requests)
_github_mcp_lock = threading.Lock()

# GitHub MCP Server configuration
GITHUB_MCP_URL = "https://api.githubcopilot.com/mcp/"
GITHUB_PAT_SECRET_NAME = "shara/github-pat"
SECRETS_MANAGER_REGION = "ap-northeast-1"


def get_github_pat() -> str:
    """从 AWS Secrets Manager 获取 GitHub Personal Access Token。

    Returns:
        str: GitHub PAT

    Raises:
        Exception: 获取 secret 失败时抛出
    """
    try:
        client = boto3.client('secretsmanager', region_name=SECRETS_MANAGER_REGION)
        response = client.get_secret_value(SecretId=GITHUB_PAT_SECRET_NAME)
        pat = response['SecretString']
        logger.info(f"Successfully retrieved GitHub PAT from Secrets Manager")
        return pat
    except Exception as e:
        logger.error(f"Failed to get GitHub PAT from Secrets Manager: {e}")
        raise


def get_github_mcp_client():
    """获取或创建 GitHub MCP Client (单例模式)。

    Returns:
        MCPClient: 配置好的 GitHub MCP 客户端

    Note:
        使用单例模式避免重复创建连接。
        首次调用时会从 Secrets Manager 获取 PAT。
    """
    global _github_mcp_client

    if _github_mcp_client is None:
        try:
            from mcp.client.streamable_http import streamablehttp_client
            from strands.tools.mcp.mcp_client import MCPClient

            pat = get_github_pat()

            def transport_factory():
                return streamablehttp_client(
                    url=GITHUB_MCP_URL,
                    headers={"Authorization": f"Bearer {pat}"}
                )

            _github_mcp_client = MCPClient(transport_factory)
            logger.info(f"GitHub MCP Client created successfully, endpoint: {GITHUB_MCP_URL}")
        except ImportError as e:
            logger.error(f"Failed to import MCP client dependencies: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to create GitHub MCP Client: {e}")
            raise

    return _github_mcp_client


def reset_github_mcp_client():
    """重置 GitHub MCP Client (用于测试或 token 刷新)。"""
    global _github_mcp_client
    _github_mcp_client = None
    logger.info("GitHub MCP Client reset")


@tool
def read_github_file(
    owner: str,
    repo: str,
    path: str,
    ref: str = "main"
) -> dict:
    """读取 GitHub 仓库中的文件内容。

    用于获取需要修改的依赖文件内容，如 requirements.txt、pom.xml 等。

    Args:
        owner: 仓库所有者 (用户名或组织名)
        repo: 仓库名称
        path: 文件路径 (相对于仓库根目录)
        ref: Git 引用 (分支名、tag 或 commit SHA)，默认 "main"

    Returns:
        dict: 文件内容信息
            - success: bool - 是否成功
            - content: str - 文件内容 (base64 解码后)
            - sha: str - 文件的 blob SHA (用于后续更新)
            - path: str - 文件路径
            - error: str - 错误信息 (如有)

    Example:
        >>> result = read_github_file("Wyifei", "awsome", "agent/agents/analyzer/requirements.txt")
        >>> print(result['content'])
        strands-agents==0.1.0
        boto3>=1.34.0
        ...
    """
    logger.info(f"[GitHub MCP] Reading file: {owner}/{repo}/{path}@{ref}")

    try:
        # 使用锁序列化 MCP 调用，避免并发连接问题
        with _github_mcp_lock:
            mcp_client = get_github_mcp_client()

            with mcp_client:
                result = mcp_client.call_tool_sync(
                    tool_use_id=f"read-file-{datetime.now(timezone.utc).timestamp()}",
                    name="get_file_contents",
                    arguments={
                        "owner": owner,
                        "repo": repo,
                        "path": path,
                        "ref": ref
                    }
                )

            # 解析 MCP 返回结果
            if result.get("status") == "success":
                content_list = result.get("content", [])
                if content_list and len(content_list) > 0:
                    # GitHub MCP 返回的 content 是一个列表:
                    # - 第一个元素是状态信息: "successfully downloaded text file (SHA: ...)"
                    # - 第二个元素是实际文件内容
                    if len(content_list) >= 2:
                        # 实际文件内容在第二个元素
                        text_content = content_list[1].get("text", "")
                        status_msg = content_list[0].get("text", "")
                        # 从状态消息中提取 SHA
                        sha = None
                        if "SHA:" in status_msg:
                            sha = status_msg.split("SHA:")[1].strip().rstrip(")")
                    else:
                        # 如果只有一个元素，可能是错误或目录列表
                        text_content = content_list[0].get("text", "")
                        sha = None

                    logger.info(f"[GitHub MCP] Successfully read file: {path}")
                    return {
                        "success": True,
                        "content": text_content,
                        "sha": sha,
                        "path": path,
                        "ref": ref,
                        "owner": owner,
                        "repo": repo
                    }

            error_msg = result.get("content", [{}])[0].get("text", "Unknown error")
            logger.error(f"[GitHub MCP] Failed to read file: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "path": path
            }

    except Exception as e:
        logger.exception(f"[GitHub MCP] Error reading file {path}: {e}")
        return {
            "success": False,
            "error": str(e),
            "path": path
        }


@tool
def create_github_branch(
    owner: str,
    repo: str,
    branch: str,
    from_branch: str = "main"
) -> dict:
    """在 GitHub 仓库中创建新分支。

    Args:
        owner: 仓库所有者
        repo: 仓库名称
        branch: 新分支名称
        from_branch: 基于哪个分支创建，默认 "main"

    Returns:
        dict: 创建结果
            - success: bool - 是否成功
            - branch: str - 分支名称
            - error: str - 错误信息 (如有)
    """
    logger.info(f"[GitHub MCP] Creating branch: {owner}/{repo}:{branch} from {from_branch}")

    try:
        with _github_mcp_lock:
            mcp_client = get_github_mcp_client()

            with mcp_client:
                result = mcp_client.call_tool_sync(
                    tool_use_id=f"create-branch-{datetime.now(timezone.utc).timestamp()}",
                    name="create_branch",
                    arguments={
                        "owner": owner,
                        "repo": repo,
                        "branch": branch,
                        "from_branch": from_branch
                    }
                )

            if result.get("status") == "success":
                logger.info(f"[GitHub MCP] Successfully created branch: {branch}")
                return {
                    "success": True,
                    "branch": branch,
                    "from_branch": from_branch
                }

            error_msg = result.get("content", [{}])[0].get("text", "Unknown error")
            logger.error(f"[GitHub MCP] Failed to create branch: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "branch": branch
            }

    except Exception as e:
        logger.exception(f"[GitHub MCP] Error creating branch {branch}: {e}")
        return {
            "success": False,
            "error": str(e),
            "branch": branch
        }


@tool
def push_files_to_github(
    owner: str,
    repo: str,
    branch: str,
    files: list,
    commit_message: str
) -> dict:
    """推送文件到 GitHub 仓库。

    将多个文件的更改一次性推送到指定分支。

    Args:
        owner: 仓库所有者
        repo: 仓库名称
        branch: 目标分支
        files: 文件列表，每个文件为 dict: {"path": "...", "content": "..."}
        commit_message: 提交信息

    Returns:
        dict: 推送结果
            - success: bool - 是否成功
            - commit_sha: str - 提交的 SHA
            - files_count: int - 推送的文件数量
            - error: str - 错误信息 (如有)

    Example:
        >>> files = [
        ...     {"path": "requirements.txt", "content": "requests==2.31.0\\nurllib3==1.26.18"},
        ...     {"path": "setup.py", "content": "..."}
        ... ]
        >>> result = push_files_to_github("Wyifei", "awsome", "fix/cve-2024", files, "fix: update dependencies")
    """
    logger.info(f"[GitHub MCP] Pushing {len(files)} files to {owner}/{repo}:{branch}")

    try:
        with _github_mcp_lock:
            mcp_client = get_github_mcp_client()

            with mcp_client:
                result = mcp_client.call_tool_sync(
                    tool_use_id=f"push-files-{datetime.now(timezone.utc).timestamp()}",
                    name="push_files",
                    arguments={
                        "owner": owner,
                        "repo": repo,
                        "branch": branch,
                        "files": files,
                        "message": commit_message
                    }
                )

            if result.get("status") == "success":
                logger.info(f"[GitHub MCP] Successfully pushed {len(files)} files")
                return {
                    "success": True,
                    "files_count": len(files),
                    "branch": branch,
                    "message": commit_message
                }

            error_msg = result.get("content", [{}])[0].get("text", "Unknown error")
            logger.error(f"[GitHub MCP] Failed to push files: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "files_count": len(files)
            }

    except Exception as e:
        logger.exception(f"[GitHub MCP] Error pushing files: {e}")
        return {
            "success": False,
            "error": str(e),
            "files_count": len(files)
        }


@tool
def create_pull_request(
    owner: str,
    repo: str,
    title: str,
    body: str,
    head: str,
    base: str = "main"
) -> dict:
    """创建 GitHub Pull Request。

    在推送文件后调用此工具创建 PR。

    Args:
        owner: 仓库所有者
        repo: 仓库名称
        title: PR 标题
        body: PR 描述 (支持 Markdown)
        head: 源分支 (包含更改的分支)
        base: 目标分支，默认 "main"

    Returns:
        dict: PR 创建结果
            - success: bool - 是否成功
            - pr_number: int - PR 编号
            - pr_url: str - PR 链接
            - html_url: str - PR 网页链接
            - state: str - PR 状态 (open)
            - error: str - 错误信息 (如有)

    Example:
        >>> result = create_pull_request(
        ...     owner="Wyifei",
        ...     repo="awsome",
        ...     title="fix(security): Update dependencies for CVE-2024-1234",
        ...     body="## Summary\\n- Update requests to 2.31.0\\n\\n## CVEs Fixed\\n- CVE-2024-1234",
        ...     head="fix/cve-2024-1234",
        ...     base="main"
        ... )
        >>> print(result['pr_url'])
        https://github.com/Wyifei/awsome/pull/1
    """
    logger.info(f"[GitHub MCP] Creating PR: {head} -> {base} in {owner}/{repo}")

    try:
        with _github_mcp_lock:
            mcp_client = get_github_mcp_client()

            with mcp_client:
                result = mcp_client.call_tool_sync(
                    tool_use_id=f"create-pr-{datetime.now(timezone.utc).timestamp()}",
                    name="create_pull_request",
                    arguments={
                        "owner": owner,
                        "repo": repo,
                        "title": title,
                        "body": body,
                        "head": head,
                        "base": base
                    }
                )

            if result.get("status") == "success":
                content_text = result.get("content", [{}])[0].get("text", "{}")
                try:
                    pr_data = json.loads(content_text)
                    pr_number = pr_data.get("number")
                    pr_url = pr_data.get("url") or pr_data.get("html_url")
                    html_url = pr_data.get("html_url", f"https://github.com/{owner}/{repo}/pull/{pr_number}")

                    logger.info(f"[GitHub MCP] Successfully created PR #{pr_number}: {html_url}")
                    return {
                        "success": True,
                        "pr_number": pr_number,
                        "pr_url": pr_url,
                        "html_url": html_url,
                        "state": "open",
                        "title": title,
                        "head": head,
                        "base": base
                    }
                except json.JSONDecodeError:
                    # 如果返回的不是 JSON，尝试从 text 中提取信息
                    logger.info(f"[GitHub MCP] PR created, response: {content_text[:200]}")
                    return {
                        "success": True,
                        "pr_url": f"https://github.com/{owner}/{repo}/pulls",
                        "title": title,
                        "head": head,
                        "base": base,
                        "raw_response": content_text[:500]
                    }

            error_msg = result.get("content", [{}])[0].get("text", "Unknown error")
            logger.error(f"[GitHub MCP] Failed to create PR: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "title": title
            }

    except Exception as e:
        logger.exception(f"[GitHub MCP] Error creating PR: {e}")
        return {
            "success": False,
            "error": str(e),
            "title": title
        }


@tool
def get_pull_request(
    owner: str,
    repo: str,
    pr_number: int
) -> dict:
    """获取 Pull Request 详情。

    用于验证 PR 是否创建成功，以及获取 PR 的最新状态。

    Args:
        owner: 仓库所有者
        repo: 仓库名称
        pr_number: PR 编号

    Returns:
        dict: PR 详情
            - success: bool - 是否成功获取
            - pr_number: int - PR 编号
            - title: str - PR 标题
            - state: str - PR 状态 (open/closed/merged)
            - html_url: str - PR 网页链接
            - head: str - 源分支
            - base: str - 目标分支
            - mergeable: bool - 是否可合并
            - error: str - 错误信息 (如有)
    """
    logger.info(f"[GitHub MCP] Getting PR #{pr_number} from {owner}/{repo}")

    try:
        with _github_mcp_lock:
            mcp_client = get_github_mcp_client()

            with mcp_client:
                result = mcp_client.call_tool_sync(
                    tool_use_id=f"get-pr-{datetime.now(timezone.utc).timestamp()}",
                    name="pull_request_read",
                    arguments={
                        "owner": owner,
                        "repo": repo,
                        "pullNumber": pr_number,
                        "method": "get"
                    }
                )

            if result.get("status") == "success":
                content_text = result.get("content", [{}])[0].get("text", "{}")
                try:
                    pr_data = json.loads(content_text)
                    logger.info(f"[GitHub MCP] Successfully retrieved PR #{pr_number}")
                    return {
                        "success": True,
                        "pr_number": pr_data.get("number", pr_number),
                        "title": pr_data.get("title"),
                        "state": pr_data.get("state"),
                        "html_url": pr_data.get("html_url"),
                        "head": pr_data.get("head", {}).get("ref") if isinstance(pr_data.get("head"), dict) else pr_data.get("head"),
                        "base": pr_data.get("base", {}).get("ref") if isinstance(pr_data.get("base"), dict) else pr_data.get("base"),
                        "mergeable": pr_data.get("mergeable"),
                        "created_at": pr_data.get("created_at"),
                        "updated_at": pr_data.get("updated_at")
                    }
                except json.JSONDecodeError:
                    return {
                        "success": True,
                        "pr_number": pr_number,
                        "raw_response": content_text[:500]
                    }

            error_msg = result.get("content", [{}])[0].get("text", "Unknown error")
            logger.error(f"[GitHub MCP] Failed to get PR: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "pr_number": pr_number
            }

    except Exception as e:
        logger.exception(f"[GitHub MCP] Error getting PR #{pr_number}: {e}")
        return {
            "success": False,
            "error": str(e),
            "pr_number": pr_number
        }


@tool
def get_pull_request_files(
    owner: str,
    repo: str,
    pr_number: int
) -> dict:
    """获取 Pull Request 修改的文件列表。

    用于验证 PR 是否包含预期的文件变更。

    Args:
        owner: 仓库所有者
        repo: 仓库名称
        pr_number: PR 编号

    Returns:
        dict: 文件列表
            - success: bool - 是否成功获取
            - files: list - 修改的文件列表，每个文件包含:
                - filename: str - 文件路径
                - status: str - 修改状态 (added/modified/removed)
                - additions: int - 添加的行数
                - deletions: int - 删除的行数
            - total_files: int - 文件总数
            - error: str - 错误信息 (如有)
    """
    logger.info(f"[GitHub MCP] Getting files for PR #{pr_number} from {owner}/{repo}")

    try:
        with _github_mcp_lock:
            mcp_client = get_github_mcp_client()

            with mcp_client:
                result = mcp_client.call_tool_sync(
                    tool_use_id=f"get-pr-files-{datetime.now(timezone.utc).timestamp()}",
                    name="pull_request_read",
                    arguments={
                        "owner": owner,
                        "repo": repo,
                        "pullNumber": pr_number,
                        "method": "get_files"
                    }
                )

            if result.get("status") == "success":
                content_text = result.get("content", [{}])[0].get("text", "[]")
                try:
                    files_data = json.loads(content_text)
                    files = []
                    if isinstance(files_data, list):
                        for f in files_data:
                            files.append({
                                "filename": f.get("filename"),
                                "status": f.get("status"),
                                "additions": f.get("additions", 0),
                                "deletions": f.get("deletions", 0),
                                "changes": f.get("changes", 0)
                            })

                    logger.info(f"[GitHub MCP] PR #{pr_number} has {len(files)} changed files")
                    return {
                        "success": True,
                        "files": files,
                        "total_files": len(files),
                        "pr_number": pr_number
                    }
                except json.JSONDecodeError:
                    return {
                        "success": True,
                        "pr_number": pr_number,
                        "raw_response": content_text[:500]
                    }

            error_msg = result.get("content", [{}])[0].get("text", "Unknown error")
            logger.error(f"[GitHub MCP] Failed to get PR files: {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "pr_number": pr_number
            }

    except Exception as e:
        logger.exception(f"[GitHub MCP] Error getting PR #{pr_number} files: {e}")
        return {
            "success": False,
            "error": str(e),
            "pr_number": pr_number
        }


@tool
def search_repo_for_container(
    ecr_repository: str,
    github_owner: str
) -> dict:
    """通过 GitHub 代码搜索，查找包含指定 ECR 镜像映射的仓库。

    搜索包含 container-inventory.json 且定义了该 ECR 镜像的仓库。
    用于动态发现镜像对应的源代码仓库，无需硬编码仓库名称。

    Args:
        ecr_repository: ECR 仓库名称 (如 "shara-dev-validator-agent")
        github_owner: GitHub 用户名或组织名 (如 "Wyifei")

    Returns:
        dict: 搜索结果
            - success: bool - 是否成功
            - found: bool - 是否找到匹配的仓库
            - repo: str - 找到的仓库名称
            - file_path: str - container-inventory.json 的路径
            - error: str - 错误信息 (如有)

    Example:
        >>> result = search_repo_for_container("shara-dev-validator-agent", "Wyifei")
        >>> print(result['repo'])
        awsome
    """
    logger.info(f"[GitHub MCP] Searching for repo containing ECR: {ecr_repository} in org: {github_owner}")

    try:
        with _github_mcp_lock:
            mcp_client = get_github_mcp_client()

            # 搜索包含该 ECR 名称的 container-inventory.json 文件
            # 使用 GitHub 代码搜索语法
            # ECR 名称可能包含前缀 (如 auth-platform-production/user-service)
            # 需要同时尝试完整名称和基础名称
            search_names = [ecr_repository]
            if "/" in ecr_repository:
                # 提取最后一段作为基础名称 (user-service)
                base_name = ecr_repository.split("/")[-1]
                search_names.append(base_name)
                logger.info(f"[GitHub MCP] ECR has prefix, will also search for base name: {base_name}")

            result = None
            for search_name in search_names:
                search_query = f"{search_name} filename:container-inventory.json user:{github_owner}"
                logger.info(f"[GitHub MCP] Searching with query: {search_query}")

                with mcp_client:
                    result = mcp_client.call_tool_sync(
                        tool_use_id=f"search-code-{datetime.now(timezone.utc).timestamp()}",
                        name="search_code",
                        arguments={
                            "query": search_query,
                            "perPage": 5
                        }
                    )

                # 检查是否找到结果
                if result.get("status") == "success":
                    content_text = result.get("content", [{}])[0].get("text", "")
                    try:
                        search_data = json.loads(content_text)
                        items = search_data.get("items", [])
                        if items and len(items) > 0:
                            logger.info(f"[GitHub MCP] Found match with search name: {search_name}")
                            break  # 找到结果，退出循环
                    except json.JSONDecodeError:
                        pass

            if result.get("status") == "success":
                content_text = result.get("content", [{}])[0].get("text", "")
                try:
                    # 解析搜索结果
                    search_data = json.loads(content_text)
                    items = search_data.get("items", [])

                    if items and len(items) > 0:
                        # 取第一个匹配的结果
                        first_match = items[0]
                        repo_full_name = first_match.get("repository", {}).get("full_name", "")
                        repo_name = first_match.get("repository", {}).get("name", "")
                        file_path = first_match.get("path", ".github/container-inventory.json")

                        # 如果 full_name 格式为 owner/repo，提取 repo
                        if "/" in repo_full_name:
                            repo_name = repo_full_name.split("/")[1]

                        logger.info(f"[GitHub MCP] Found repo: {repo_name} containing {ecr_repository}")
                        return {
                            "success": True,
                            "found": True,
                            "repo": repo_name,
                            "full_name": repo_full_name,
                            "file_path": file_path,
                            "owner": github_owner
                        }

                    logger.warning(f"[GitHub MCP] No repo found containing ECR: {ecr_repository}")
                    return {
                        "success": True,
                        "found": False,
                        "error": f"No repository found containing {ecr_repository} in container-inventory.json"
                    }

                except json.JSONDecodeError:
                    # 尝试从文本中提取信息
                    logger.warning(f"[GitHub MCP] Could not parse search result as JSON: {content_text[:200]}")
                    return {
                        "success": True,
                        "found": False,
                        "raw_response": content_text[:500]
                    }

            error_msg = result.get("content", [{}])[0].get("text", "Unknown error")
            logger.error(f"[GitHub MCP] Search failed: {error_msg}")
            return {
                "success": False,
                "found": False,
                "error": error_msg
            }

    except Exception as e:
        logger.exception(f"[GitHub MCP] Error searching for repo: {e}")
        return {
            "success": False,
            "found": False,
            "error": str(e)
        }


@tool
def search_container_inventory(
    ecr_repository: str,
    github_owner: str = "Wyifei",
    github_repo: str = "",
    ref: str = "master"
) -> dict:
    """搜索容器清单，匹配 ECR 仓库到服务目录。

    读取 .github/container-inventory.json 文件，查找与 ECR 仓库名称匹配的服务。
    如果未指定 github_repo，会自动通过 GitHub 搜索 API 查找包含该镜像的仓库。

    Args:
        ecr_repository: ECR 仓库名称 (如 "shara-analyzer", "user-service")
        github_owner: GitHub 仓库所有者，默认 "Wyifei"
        github_repo: GitHub 仓库名称，留空则自动搜索
        ref: Git 引用 (分支名)，默认 "master"

    Returns:
        dict: 匹配结果
            - success: bool - 是否成功
            - found: bool - 是否找到匹配的服务
            - github_repo: str - 仓库名称 (动态发现或传入的)
            - service: dict - 服务信息 (如果找到)
                - name: str - 服务名称
                - path: str - 服务目录路径
                - dockerfile: str - Dockerfile 路径
                - language: str - 编程语言
                - framework: str - 框架
                - dependencies: list - 依赖文件列表
            - error: str - 错误信息 (如有)

    Example:
        >>> # 自动搜索仓库
        >>> result = search_container_inventory("shara-analyzer", github_owner="Wyifei")
        >>> print(result['github_repo'])  # 动态发现的仓库名
        awsome
        >>> print(result['service']['path'])
        agent/agents/analyzer
    """
    logger.info(f"[GitHub MCP] Searching container inventory for ECR: {ecr_repository}")

    # 如果未指定 repo，先通过搜索 API 查找
    if not github_repo:
        logger.info(f"[GitHub MCP] No repo specified, searching for repo containing {ecr_repository}")
        search_result = search_repo_for_container(ecr_repository, github_owner)
        if search_result.get("found"):
            github_repo = search_result.get("repo")
            logger.info(f"[GitHub MCP] Found repo via search: {github_repo}")
        else:
            return {
                "success": False,
                "found": False,
                "error": f"Could not find repository containing {ecr_repository}. Error: {search_result.get('error', 'Unknown')}"
            }

    try:
        # 读取 container-inventory.json
        inventory_result = read_github_file(
            owner=github_owner,
            repo=github_repo,
            path=".github/container-inventory.json",
            ref=ref
        )

        if not inventory_result.get("success"):
            return {
                "success": False,
                "found": False,
                "error": f"Failed to read container-inventory.json: {inventory_result.get('error')}"
            }

        # 解析 JSON
        try:
            inventory = json.loads(inventory_result.get("content", "{}"))
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "found": False,
                "error": f"Invalid container-inventory.json format: {e}"
            }

        # 搜索匹配的容器
        containers = inventory.get("containers", [])
        for container in containers:
            ecr_pattern = container.get("ecr_pattern", "")
            if not ecr_pattern:
                continue
            # 支持多种匹配方式：
            # 1. 精确匹配: user-service == user-service
            # 2. 带前缀匹配: auth-platform-production/user-service 匹配 user-service
            #    检查以 /<pattern> 结尾，避免 admin-user-service 错误匹配 user-service
            is_match = (
                ecr_pattern == ecr_repository or  # 精确匹配
                ecr_repository.endswith(f"/{ecr_pattern}")  # 带前缀匹配
            )
            if is_match:
                logger.info(f"[GitHub MCP] Found matching service: {container.get('name')}")
                return {
                    "success": True,
                    "found": True,
                    "github_owner": github_owner,
                    "github_repo": github_repo,
                    "service": {
                        "name": container.get("name"),
                        "description": container.get("description"),
                        "ecr_pattern": ecr_pattern,
                        "path": container.get("path"),
                        "dockerfile": container.get("dockerfile"),
                        "base_image": container.get("base_image"),
                        "language": container.get("language"),
                        "framework": container.get("framework"),
                        "port": container.get("port"),
                        "dependencies": container.get("dependencies", [])
                    },
                    "remediation_patterns": inventory.get("remediation_patterns", {})
                }

        logger.warning(f"[GitHub MCP] No matching service found for ECR: {ecr_repository}")
        return {
            "success": True,
            "found": False,
            "error": f"No service found matching ECR repository: {ecr_repository}",
            "available_patterns": [c.get("ecr_pattern") for c in containers if c.get("ecr_pattern")]
        }

    except Exception as e:
        logger.exception(f"[GitHub MCP] Error searching container inventory: {e}")
        return {
            "success": False,
            "found": False,
            "error": str(e)
        }


@tool
def get_service_metadata(
    service_path: str,
    github_owner: str = "Wyifei",
    github_repo: str = "awsome",
    ref: str = "master"
) -> dict:
    """读取服务的 SERVICE.yaml 元数据。

    获取服务的详细配置信息，包括依赖文件位置、漏洞修复模式等。

    Args:
        service_path: 服务目录路径 (如 "agent/agents/analyzer")
        github_owner: GitHub 仓库所有者，默认 "Wyifei"
        github_repo: GitHub 仓库名称，默认 "awsome"
        ref: Git 引用 (分支名)，默认 "master"

    Returns:
        dict: 服务元数据
            - success: bool - 是否成功
            - metadata: dict - SERVICE.yaml 内容
                - name: str - 服务名称
                - type: str - 服务类型
                - language: str - 编程语言
                - dependencies: list - 依赖配置
                - vulnerability_remediation: dict - 漏洞修复配置
            - error: str - 错误信息 (如有)

    Example:
        >>> result = get_service_metadata("agent/agents/analyzer")
        >>> print(result['metadata']['vulnerability_remediation'])
        {'packages': [{'file': './requirements.txt', 'type': 'pip', ...}]}
    """
    logger.info(f"[GitHub MCP] Reading SERVICE.yaml from: {service_path}")

    try:
        # 读取 SERVICE.yaml
        service_yaml_path = f"{service_path}/SERVICE.yaml"
        file_result = read_github_file(
            owner=github_owner,
            repo=github_repo,
            path=service_yaml_path,
            ref=ref
        )

        if not file_result.get("success"):
            return {
                "success": False,
                "error": f"Failed to read SERVICE.yaml: {file_result.get('error')}"
            }

        # 解析 YAML
        try:
            import yaml
            metadata = yaml.safe_load(file_result.get("content", ""))
        except ImportError:
            # 如果没有 yaml 模块，尝试简单解析
            logger.warning("PyYAML not available, using simple parsing")
            content = file_result.get("content", "")
            metadata = {"raw_content": content}
        except Exception as e:
            return {
                "success": False,
                "error": f"Invalid SERVICE.yaml format: {e}"
            }

        logger.info(f"[GitHub MCP] Successfully read SERVICE.yaml for: {metadata.get('name', service_path)}")
        return {
            "success": True,
            "metadata": metadata,
            "service_path": service_path
        }

    except Exception as e:
        logger.exception(f"[GitHub MCP] Error reading SERVICE.yaml: {e}")
        return {
            "success": False,
            "error": str(e)
        }
