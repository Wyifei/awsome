#!/bin/bash
# Test Analyzer Agent in Docker Compose environment
#
# Usage:
#   cd agents
#   docker-compose up -d
#   ./test/test_analyzer_docker.sh [TRAIL_NAME]
#
# Example:
#   ./test/test_analyzer_docker.sh my-cloudtrail

set -e

ANALYZER_URL="${ANALYZER_URL:-http://localhost:8080}"
ACCOUNT_ID="${AWS_ACCOUNT_ID:-870414140965}"
REGION="${AWS_REGION:-ap-northeast-1}"

# Allow specifying trail name as argument
TRAIL_NAME="${1:-}"

if [ -z "$TRAIL_NAME" ]; then
    echo "Finding existing CloudTrail trails..."
    TRAIL_NAME=$(aws cloudtrail describe-trails --region $REGION --query 'trailList[0].Name' --output text 2>/dev/null || echo "")

    if [ -z "$TRAIL_NAME" ] || [ "$TRAIL_NAME" == "None" ]; then
        echo "ERROR: No CloudTrail trail found. Please specify a trail name:"
        echo "  ./test/test_analyzer_docker.sh <TRAIL_NAME>"
        echo ""
        echo "Or create a test trail first:"
        echo "  aws cloudtrail create-trail --name test-mcp-trail --s3-bucket-name <YOUR_BUCKET>"
        exit 1
    fi
    echo "Found trail: $TRAIL_NAME"
fi

TRAIL_ARN="arn:aws:cloudtrail:${REGION}:${ACCOUNT_ID}:trail/${TRAIL_NAME}"

echo "=============================================="
echo "Testing Analyzer Agent with MCP Integration"
echo "=============================================="
echo "Endpoint: ${ANALYZER_URL}/invocations"
echo "Control ID: CloudTrail.7 (No ASR playbook)"
echo "Trail: ${TRAIL_NAME}"
echo "Trail ARN: ${TRAIL_ARN}"
echo "Scenario: Agent should use MCP tools to search AWS docs"
echo "=============================================="
echo ""

# CloudTrail.7 test finding - no ASR playbook, should trigger MCP usage
REQUEST_BODY=$(cat <<EOF
{
  "task_id": "test-mcp-docker-$(date +%s)",
  "control_id": "CloudTrail.7",
  "memory_session_id": "test-session-mcp-docker",
  "finding": {
    "SchemaVersion": "2018-10-08",
    "Id": "arn:aws:securityhub:${REGION}:${ACCOUNT_ID}:security-control/CloudTrail.7/finding/test-mcp-001",
    "ProductArn": "arn:aws:securityhub:${REGION}::product/aws/securityhub",
    "GeneratorId": "security-control/CloudTrail.7",
    "AwsAccountId": "${ACCOUNT_ID}",
    "Region": "${REGION}",
    "Severity": {
      "Label": "MEDIUM",
      "Normalized": 40
    },
    "Title": "CloudTrail trails should be integrated with CloudWatch Logs",
    "Description": "This control checks whether CloudTrail trails are configured to send logs to CloudWatch Logs.",
    "Remediation": {
      "Recommendation": {
        "Text": "For information on how to correct this issue, consult the AWS Security Hub controls documentation.",
        "Url": "https://docs.aws.amazon.com/console/securityhub/CloudTrail.7/remediation"
      }
    },
    "ProductFields": {
      "ControlId": "CloudTrail.7",
      "RecommendationUrl": "https://docs.aws.amazon.com/console/securityhub/CloudTrail.7/remediation"
    },
    "Resources": [
      {
        "Type": "AwsCloudTrailTrail",
        "Id": "${TRAIL_ARN}",
        "Partition": "aws",
        "Region": "${REGION}",
        "Details": {
          "AwsCloudTrailTrail": {
            "Name": "${TRAIL_NAME}"
          }
        }
      }
    ],
    "Compliance": {
      "Status": "FAILED",
      "SecurityControlId": "CloudTrail.7"
    },
    "WorkflowState": "NEW",
    "Workflow": {"Status": "NEW"},
    "RecordState": "ACTIVE"
  }
}
EOF
)

echo "Sending request to Analyzer Agent..."
echo ""

# Send request and capture response
RESPONSE=$(curl -s -X POST "${ANALYZER_URL}/invocations" \
  -H "Content-Type: application/json" \
  -d "${REQUEST_BODY}")

# Pretty print response
echo "=============================================="
echo "RESPONSE"
echo "=============================================="
echo "${RESPONSE}" | jq . 2>/dev/null || echo "${RESPONSE}"
echo ""
echo "=============================================="
