#!/bin/bash
# SHARA Agent 本地测试脚本
# 测试流程: Analyzer → Remediator → (A2A) → Validator

set -e

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ANALYZER_URL="http://localhost:8080"
REMEDIATOR_URL="http://localhost:8081"
VALIDATOR_URL="http://localhost:8082"
TASK_ID="test-$(date +%s)"
MEMORY_SESSION_ID="session-task-${TASK_ID}"
ACTOR_ID="870414140965"
CONTROL_ID="S3.1"
FINDING_ID="arn:aws:securityhub:ap-northeast-1:870414140965:finding/test-finding-id"

echo "=========================================="
echo "SHARA Agent Local Test"
echo "=========================================="
echo "Task ID: ${TASK_ID}"
echo "Memory Session: ${MEMORY_SESSION_ID}"
echo ""

# 保存所有测试参数到文件供回滚测试使用
cat > "${SCRIPT_DIR}/.last_test_params" <<PARAMS_EOF
TASK_ID="${TASK_ID}"
MEMORY_SESSION_ID="${MEMORY_SESSION_ID}"
ACTOR_ID="${ACTOR_ID}"
CONTROL_ID="${CONTROL_ID}"
FINDING_ID="${FINDING_ID}"
RESOURCE_ARN="arn:aws:s3:::test-agent-bucket-870414140965"
RESOURCE_TYPE="AwsS3Bucket"
PARAMS_EOF
echo "(测试参数已保存到 ${SCRIPT_DIR}/.last_test_params)"
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

echo "Validator:"
curl -s ${VALIDATOR_URL}/ping | jq .
echo ""

# 测试 Analyzer
echo "=========================================="
echo "2. 调用 Analyzer Agent (Phase 1)"
echo "=========================================="
echo ""

FINDING=$(cat "${SCRIPT_DIR}/test_finding_s3_public.json")

curl -s -X POST ${ANALYZER_URL}/invocations \
  -H "Content-Type: application/json" \
  -d @- <<EOF | jq .
{
  "task_id": "${TASK_ID}",
  "memory_session_id": "${MEMORY_SESSION_ID}",
  "actor_id": "${ACTOR_ID}",
  "finding": ${FINDING},
  "control_id": "S3.1"
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
  echo "   Remediator 会通过 A2A 自动调用 Validator"
  echo "=========================================="
  echo ""

  curl -s -X POST ${REMEDIATOR_URL}/invocations \
    -H "Content-Type: application/json" \
    -d @- <<EOF | jq .
{
  "task_id": "${TASK_ID}",
  "memory_session_id": "${MEMORY_SESSION_ID}",
  "actor_id": "${ACTOR_ID}",
  "resource_arn": "arn:aws:s3:::test-agent-bucket-870414140965",
  "resource_type": "AwsS3Bucket",
  "control_id": "${CONTROL_ID}",
  "finding_id": "${FINDING_ID}",
  "is_rollback": false
}
EOF

  echo ""
  echo "=========================================="
  echo "Remediator + Validator (A2A) 完成"
  echo "=========================================="
fi

# 单独测试 Validator (可选)
echo ""
read -p "是否单独测试 Validator Agent (直接调用)? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
  echo "=========================================="
  echo "4. 直接调用 Validator Agent"
  echo "   注意: Validator 从 Memory 获取代码和执行结果"
  echo "   直接调用时需要先通过 Remediator 保存数据到 Memory"
  echo "=========================================="
  echo ""

  curl -s -X POST ${VALIDATOR_URL}/invocations \
    -H "Content-Type: application/json" \
    -d @- <<EOF | jq .
{
  "task_id": "${TASK_ID}",
  "memory_session_id": "${MEMORY_SESSION_ID}",
  "actor_id": "${ACTOR_ID}",
  "resource_arn": "arn:aws:s3:::test-agent-bucket-870414140965",
  "resource_type": "AwsS3Bucket",
  "control_id": "${CONTROL_ID}",
  "finding_id": "${FINDING_ID}",
  "is_rollback": false
}
EOF

  echo ""
  echo "=========================================="
  echo "Validator 完成"
  echo "   (如果失败，可能是因为 Memory 中没有 Remediator 保存的数据)"
  echo "=========================================="
fi

echo ""
echo "=========================================="
echo "测试回滚功能"
echo "=========================================="
echo ""
echo "如果你收到了修复完成邮件，可以测试回滚功能:"
echo ""
echo "  ./test_rollback.sh ${TASK_ID}"
echo ""
echo "或者直接运行 ./test_rollback.sh 并手动输入 Task ID"
echo ""
