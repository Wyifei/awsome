#!/bin/bash
# SHARA Agent 本地测试脚本 - EKS.1 测试

set -e

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ANALYZER_URL="http://localhost:8080"
REMEDIATOR_URL="http://localhost:8081"
TASK_ID="test-$(date +%s)"
MEMORY_SESSION_ID="session-task-${TASK_ID}"
ACTOR_ID="870414140965"

echo "=========================================="
echo "SHARA Agent Local Test - EKS.1"
echo "=========================================="
echo "Task ID: ${TASK_ID}"
echo "Memory Session: ${MEMORY_SESSION_ID}"
echo ""

# 检查 Agent 是否运行
echo "1. 检查 Agent 健康状态..."
echo ""

echo "Analyzer:"
curl -s ${ANALYZER_URL}/ping | jq .
echo ""

echo "Remediator:"
curl -s ${REMEDIATOR_URL}/ping | jq .
echo ""

# 测试 Analyzer
echo "=========================================="
echo "2. 调用 Analyzer Agent (Phase 1)"
echo "=========================================="
echo ""

FINDING=$(cat "${SCRIPT_DIR}/test_finding_eks_public.json")

curl -s -X POST ${ANALYZER_URL}/invocations \
  -H "Content-Type: application/json" \
  -d @- <<EOF | jq .
{
  "task_id": "${TASK_ID}",
  "memory_session_id": "${MEMORY_SESSION_ID}",
  "actor_id": "${ACTOR_ID}",
  "finding": ${FINDING},
  "control_id": "EKS.1"
}
EOF

echo ""
echo "=========================================="
echo "Analyzer 完成"
echo "=========================================="
echo ""

# 提示用户是否继续测试 Remediator
read -p "是否继续测试 Remediator Agent? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
  echo "=========================================="
  echo "3. 调用 Remediator Agent (Phase 2)"
  echo "=========================================="
  echo ""

  curl -s -X POST ${REMEDIATOR_URL}/invocations \
    -H "Content-Type: application/json" \
    -d @- <<EOF | jq .
{
  "task_id": "${TASK_ID}",
  "memory_session_id": "${MEMORY_SESSION_ID}",
  "actor_id": "${ACTOR_ID}",
  "resource_arn": "arn:aws:eks:ap-northeast-1:870414140965:cluster/auth-platform-production",
  "resource_type": "AwsEksCluster",
  "control_id": "EKS.1"
}
EOF

  echo ""
  echo "=========================================="
  echo "Remediator 完成"
  echo "=========================================="
fi
