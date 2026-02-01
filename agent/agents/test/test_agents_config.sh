#!/bin/bash
# SHARA Agent 本地测试脚本 - Config.1 修复测试
# 测试 AWS Config 记录器配置更新
# 测试流程: Analyzer → Remediator → (A2A) → Validator

set -e

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ANALYZER_URL="http://localhost:8080"
REMEDIATOR_URL="http://localhost:8081"
VALIDATOR_URL="http://localhost:8082"
TASK_ID="test-config-$(date +%s)"
MEMORY_SESSION_ID="session-task-${TASK_ID}"
ACTOR_ID="870414140965"
CONTROL_ID="Config.1"
FINDING_ID="arn:aws:securityhub:ap-northeast-1:870414140965:finding/test-config-finding-id"
RESOURCE_ARN="AWS::::Account:870414140965"
RESOURCE_TYPE="AwsAccount"

echo "=========================================="
echo "SHARA Agent Local Test - Config.1"
echo "=========================================="
echo "Task ID: ${TASK_ID}"
echo "Memory Session: ${MEMORY_SESSION_ID}"
echo "Control ID: ${CONTROL_ID}"
echo ""
echo "测试场景: AWS Config 未记录所有必需的 IAM 资源类型"
echo "缺失资源类型: AWS::IAM::User, AWS::IAM::Policy, AWS::IAM::Role, AWS::IAM::Group"
echo ""

# 保存所有测试参数到文件供回滚测试使用
cat > "${SCRIPT_DIR}/.last_test_params" <<PARAMS_EOF
TASK_ID="${TASK_ID}"
MEMORY_SESSION_ID="${MEMORY_SESSION_ID}"
ACTOR_ID="${ACTOR_ID}"
CONTROL_ID="${CONTROL_ID}"
FINDING_ID="${FINDING_ID}"
RESOURCE_ARN="${RESOURCE_ARN}"
RESOURCE_TYPE="${RESOURCE_TYPE}"
PARAMS_EOF
echo "(测试参数已保存到 ${SCRIPT_DIR}/.last_test_params)"
echo ""

# 检查 Agent 是否运行
echo "1. 检查 Agent 健康状态..."
echo ""

echo "Analyzer:"
curl -s ${ANALYZER_URL}/ping | jq . || echo "Analyzer 未运行"
echo ""

echo "Remediator:"
curl -s ${REMEDIATOR_URL}/ping | jq . || echo "Remediator 未运行"
echo ""

echo "Validator:"
curl -s ${VALIDATOR_URL}/ping | jq . || echo "Validator 未运行"
echo ""

# 检查当前 AWS Config 状态
echo "=========================================="
echo "2. 检查当前 AWS Config 记录器状态"
echo "=========================================="
echo ""

echo "当前 Config 记录器配置:"
aws configservice describe-configuration-recorders --region ap-northeast-1 --output json | jq '.ConfigurationRecorders[0].recordingGroup' || echo "无法获取 Config 记录器配置"
echo ""

echo "当前 Config 记录器状态:"
aws configservice describe-configuration-recorder-status --region ap-northeast-1 --output json | jq '.ConfigurationRecordersStatus[0]' || echo "无法获取 Config 记录器状态"
echo ""

# 测试 Analyzer
echo "=========================================="
echo "3. 调用 Analyzer Agent (Phase 1)"
echo "=========================================="
echo ""

FINDING=$(cat "${SCRIPT_DIR}/test_finding_config.json")

curl -s -X POST ${ANALYZER_URL}/invocations \
  -H "Content-Type: application/json" \
  -d @- <<EOF | jq .
{
  "task_id": "${TASK_ID}",
  "memory_session_id": "${MEMORY_SESSION_ID}",
  "actor_id": "${ACTOR_ID}",
  "finding": ${FINDING},
  "control_id": "${CONTROL_ID}"
}
EOF

echo ""
echo "=========================================="
echo "Analyzer 完成"
echo "=========================================="
echo ""

# 提示用户是否继续测试 Remediator
read -p "是否继续测试 Remediator Agent (将实际执行修复)? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
  echo ""
  echo "⚠️  警告: Remediator 将实际修改 AWS Config 记录器配置!"
  echo "   这将添加 IAM 资源类型到记录器配置中。"
  echo ""
  read -p "确认继续? (y/n) " -n 1 -r
  echo ""

  if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "=========================================="
    echo "4. 调用 Remediator Agent (Phase 2)"
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
  "resource_arn": "${RESOURCE_ARN}",
  "resource_type": "${RESOURCE_TYPE}",
  "control_id": "${CONTROL_ID}",
  "finding_id": "${FINDING_ID}",
  "is_rollback": false
}
EOF

    echo ""
    echo "=========================================="
    echo "Remediator + Validator (A2A) 完成"
    echo "=========================================="
    echo ""

    # 检查修复后的 Config 状态
    echo "=========================================="
    echo "5. 检查修复后 AWS Config 记录器状态"
    echo "=========================================="
    echo ""

    echo "修复后 Config 记录器配置:"
    aws configservice describe-configuration-recorders --region ap-northeast-1 --output json | jq '.ConfigurationRecorders[0].recordingGroup' || echo "无法获取 Config 记录器配置"
    echo ""
  fi
fi

echo ""
echo "=========================================="
echo "测试完成"
echo "=========================================="
echo ""
echo "如果修复成功，AWS Config 记录器现在应该包含以下 IAM 资源类型:"
echo "  - AWS::IAM::User"
echo "  - AWS::IAM::Policy"
echo "  - AWS::IAM::Role"
echo "  - AWS::IAM::Group"
echo ""
echo "如果你收到了修复完成邮件，可以测试回滚功能:"
echo ""
echo "  ./test_rollback.sh ${TASK_ID}"
echo ""
