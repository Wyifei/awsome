#!/bin/bash
# SHARA Agent 回滚测试脚本
# 用于测试回滚流程: Remediator (is_rollback=true) → (A2A) → Validator
#
# 使用方法:
# 1. 先运行 test_agents.sh 完成正常修复流程
# 2. 运行此脚本，它会自动读取上次测试的参数
#
# 或者手动指定参数:
#   ./test_rollback.sh <task_id>

set -e

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REMEDIATOR_URL="http://localhost:8081"
VALIDATOR_URL="http://localhost:8082"

# 尝试从上次测试保存的参数文件读取
PARAMS_FILE="${SCRIPT_DIR}/.last_test_params"

if [ -n "$1" ]; then
  # 如果提供了参数，使用参数作为 TASK_ID，其他值使用默认
  TASK_ID="$1"
  MEMORY_SESSION_ID="session-task-${TASK_ID}"
  ACTOR_ID="870414140965"
  CONTROL_ID="S3.1"
  FINDING_ID="arn:aws:securityhub:ap-northeast-1:870414140965:finding/test-finding-id"
  RESOURCE_ARN="arn:aws:s3:::test-agent-bucket-870414140965"
  RESOURCE_TYPE="AwsS3Bucket"
elif [ -f "$PARAMS_FILE" ]; then
  # 从参数文件读取
  echo "=========================================="
  echo "SHARA Agent 回滚测试"
  echo "=========================================="
  echo ""
  echo "发现上次测试的参数文件..."
  source "$PARAMS_FILE"
  echo ""
  echo "上次测试参数:"
  echo "  Task ID:        ${TASK_ID}"
  echo "  Memory Session: ${MEMORY_SESSION_ID}"
  echo "  Actor ID:       ${ACTOR_ID}"
  echo "  Resource ARN:   ${RESOURCE_ARN}"
  echo ""
  read -p "使用这些参数进行回滚? (y/n) " -n 1 -r
  echo ""

  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    read -p "请输入新的 TASK_ID: " TASK_ID
    MEMORY_SESSION_ID="session-task-${TASK_ID}"
    # 其他参数使用默认值
    ACTOR_ID="${ACTOR_ID:-870414140965}"
    CONTROL_ID="${CONTROL_ID:-S3.1}"
    FINDING_ID="${FINDING_ID:-arn:aws:securityhub:ap-northeast-1:870414140965:finding/test-finding-id}"
    RESOURCE_ARN="${RESOURCE_ARN:-arn:aws:s3:::test-agent-bucket-870414140965}"
    RESOURCE_TYPE="${RESOURCE_TYPE:-AwsS3Bucket}"
  fi
else
  # 没有参数文件，提示用户
  echo "=========================================="
  echo "SHARA Agent 回滚测试"
  echo "=========================================="
  echo ""
  echo "未找到上次测试的参数文件。"
  echo "请先运行 test_agents.sh 完成一次修复流程，"
  echo "或手动输入参数。"
  echo ""
  read -p "请输入 TASK_ID: " TASK_ID

  if [ -z "$TASK_ID" ]; then
    echo "错误: TASK_ID 不能为空"
    exit 1
  fi

  MEMORY_SESSION_ID="session-task-${TASK_ID}"
  ACTOR_ID="870414140965"
  CONTROL_ID="S3.1"
  FINDING_ID="arn:aws:securityhub:ap-northeast-1:870414140965:finding/test-finding-id"
  RESOURCE_ARN="arn:aws:s3:::test-agent-bucket-870414140965"
  RESOURCE_TYPE="AwsS3Bucket"
fi

echo ""
echo "=========================================="
echo "回滚参数 (与 Lambda 传入参数一致):"
echo "=========================================="
echo "  task_id:           ${TASK_ID}"
echo "  memory_session_id: ${MEMORY_SESSION_ID}"
echo "  actor_id:          ${ACTOR_ID}"
echo "  resource_arn:      ${RESOURCE_ARN}"
echo "  resource_type:     ${RESOURCE_TYPE}"
echo "  control_id:        ${CONTROL_ID}"
echo "  finding_id:        ${FINDING_ID}"
echo "  is_rollback:       true"
echo "=========================================="
echo ""

# 检查 Agent 是否运行
echo "1. 检查 Agent 健康状态..."
echo ""

echo "Remediator:"
curl -s ${REMEDIATOR_URL}/ping | jq .
echo ""

echo "Validator:"
curl -s ${VALIDATOR_URL}/ping | jq .
echo ""

# 确认执行回滚
read -p "确认执行回滚? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "已取消"
  exit 0
fi

echo "=========================================="
echo "2. 调用 Remediator Agent (回滚模式)"
echo "   is_rollback=true"
echo "   Remediator 会从 Memory 获取回滚数据"
echo "   然后通过 A2A 调用 Validator"
echo "=========================================="
echo ""

# 构建与 Lambda 相同格式的请求
# Lambda `run_phase2_remediation` 发送的 agent_input:
# {
#   'task_id': task_id,
#   'memory_session_id': memory_session_id,
#   'actor_id': actor_id,
#   'finding_id': finding_id,
#   'resource_arn': resource_arn,
#   'resource_type': resource_type,
#   'control_id': control_id,
#   'is_rollback': is_rollback
# }

# 记录开始时间
START_TIME=$(date +%s)

curl -s -X POST ${REMEDIATOR_URL}/invocations \
  -H "Content-Type: application/json" \
  -d @- <<EOF | jq .
{
  "task_id": "${TASK_ID}",
  "memory_session_id": "${MEMORY_SESSION_ID}",
  "actor_id": "${ACTOR_ID}",
  "finding_id": "${FINDING_ID}",
  "resource_arn": "${RESOURCE_ARN}",
  "resource_type": "${RESOURCE_TYPE}",
  "control_id": "${CONTROL_ID}",
  "is_rollback": true
}
EOF

# 记录结束时间
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo "=========================================="
echo "回滚流程完成 (耗时: ${DURATION}秒)"
echo "=========================================="
echo ""
echo "请检查以下内容:"
echo ""
echo "1. Remediator 日志 - 查看 Memory 搜索:"
echo "   docker logs shara-remediator 2>&1 | grep -E '(Retrieved|rollback|get_rollback)'"
echo ""
echo "2. Validator 日志 - 查看回滚处理:"
echo "   docker logs shara-validator 2>&1 | grep -E '(rollback|email)'"
echo ""
echo "3. 是否收到回滚结果邮件 (应无回滚链接)"
echo ""
echo "关键日志:"
echo "- 'Retrieved X turns from Memory' - 搜索了多少条记录"
echo "- 'Found rollback_data' - 是否找到回滚数据"
echo "- 'Rollback data not found' - 回滚数据未找到"
echo ""
