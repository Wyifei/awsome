# Security Hub Auto-Remediation Agent 智能体设计文档

## 1. 概述

本文档详细描述 SHARA 系统中各智能体（Agent）的设计，包括职责、能力、工具集、Prompt 设计以及协作方式。

---

## 2. Agent 框架选型

### 2.1 Strands Agent Framework

选择 AWS Strands Agent 框架作为基础，主要原因：

| 特性 | 说明 |
|------|------|
| AWS 原生集成 | 与 Bedrock、Lambda、DynamoDB 等深度集成 |
| 多 Agent 支持 | 内置 Agent 协作和通信机制 |
| 工具扩展 | 易于注册自定义工具 |
| 可观测性 | 内置追踪和日志支持 |
| 开源 | 社区活跃，持续迭代 |

### 2.2 运行环境

```
┌─────────────────────────────────────────────────────────────┐
│                    AWS AgentCore Runtime                     │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                  Strands Agent SDK                     │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐  │  │
│  │  │   Agent     │ │    Tool     │ │    Memory       │  │  │
│  │  │   Runtime   │ │   Registry  │ │    Store        │  │  │
│  │  └─────────────┘ └─────────────┘ └─────────────────┘  │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐  │  │
│  │  │   LLM       │ │  Callback   │ │    Tracing      │  │  │
│  │  │   Client    │ │  Handler    │ │    Integration  │  │  │
│  │  └─────────────┘ └─────────────┘ └─────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                  Amazon Bedrock                        │  │
│  │          Claude 3.5 Sonnet / Claude 3 Opus            │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Agent 详细设计

### 3.1 Orchestrator Agent (编排智能体)

#### 3.1.1 职责

| 职责 | 描述 |
|------|------|
| 任务接收 | 接收来自 Lambda 的处理请求 |
| 任务分解 | 将复杂任务分解为子任务 |
| Agent 调度 | 根据任务类型调用相应的子 Agent |
| 状态管理 | 维护整体处理状态 |
| 异常处理 | 处理子 Agent 的错误和超时 |
| 结果聚合 | 汇总各 Agent 的处理结果 |

#### 3.1.2 System Prompt

```markdown
# Role
You are the Orchestrator Agent for the Security Hub Auto-Remediation Agent (SHARA) system.
Your role is to coordinate the analysis and remediation of AWS Security Hub findings.

# Responsibilities
1. Receive security findings from AWS Security Hub
2. Coordinate the analysis process by delegating to the Analyzer Agent
3. Coordinate remediation planning by delegating to the Remediator Agent
4. Manage the approval workflow
5. Oversee remediation execution
6. Coordinate validation by delegating to the Validator Agent

# Guidelines
- Always validate input data before processing
- Maintain detailed state for each task
- Handle errors gracefully and provide clear error messages
- Never skip the approval step for actual remediation
- Log all significant actions for audit purposes

# Task Flow
1. ANALYZE: Delegate to Analyzer Agent to understand the finding
2. PLAN: Delegate to Remediator Agent to create remediation plan
3. APPROVE: Request approval via email notification
4. EXECUTE: After approval, delegate execution to Remediator Agent
5. VALIDATE: Delegate to Validator Agent to verify the fix

# Output Format
Always respond with a structured JSON containing:
- status: current processing status
- phase: current phase (analyze, plan, approve, execute, validate)
- result: phase-specific results
- nextAction: what happens next
- errors: any errors encountered
```

#### 3.1.3 工具集

```python
ORCHESTRATOR_TOOLS = [
    # 子 Agent 调用
    Tool(
        name="invoke_analyzer",
        description="调用 Analyzer Agent 分析 Finding",
        parameters={
            "finding": "Security Hub finding object",
            "context": "Additional context"
        }
    ),
    Tool(
        name="invoke_remediator",
        description="调用 Remediator Agent 生成/执行修复方案",
        parameters={
            "analysis": "Analysis result from Analyzer",
            "action": "plan | execute"
        }
    ),
    Tool(
        name="invoke_validator",
        description="调用 Validator Agent 验证修复结果",
        parameters={
            "remediation": "Executed remediation details",
            "expectedState": "Expected resource state"
        }
    ),

    # 状态管理
    Tool(
        name="update_task_status",
        description="更新任务状态",
        parameters={
            "taskId": "Task ID",
            "status": "New status",
            "details": "Status details"
        }
    ),
    Tool(
        name="get_task_status",
        description="获取任务当前状态",
        parameters={"taskId": "Task ID"}
    ),

    # 通知
    Tool(
        name="send_approval_request",
        description="发送审批请求邮件",
        parameters={
            "taskId": "Task ID",
            "remediation": "Remediation plan",
            "recipients": "Email recipients"
        }
    ),
    Tool(
        name="send_notification",
        description="发送状态通知",
        parameters={
            "type": "success | failure | info",
            "message": "Notification message",
            "recipients": "Email recipients"
        }
    )
]
```

#### 3.1.4 状态转换逻辑

```python
class OrchestratorStateMachine:
    async def process(self, task_id: str, finding: dict):
        try:
            # 1. 分析阶段
            await self.update_status(task_id, "analyzing")
            analysis = await self.invoke_analyzer(finding)

            if analysis.skip_remediation:
                await self.update_status(task_id, "skipped", analysis.reason)
                return

            # 2. 方案生成阶段
            await self.update_status(task_id, "planning")
            plan = await self.invoke_remediator(analysis, action="plan")

            # 3. 审批阶段
            await self.update_status(task_id, "pending_approval")
            await self.send_approval_request(task_id, plan)

            # 等待审批回调...

        except Exception as e:
            await self.handle_error(task_id, e)

    async def handle_approval(self, task_id: str, approved: bool, reason: str = None):
        if not approved:
            await self.update_status(task_id, "rejected", reason)
            return

        try:
            # 4. 执行阶段
            await self.update_status(task_id, "executing")
            result = await self.invoke_remediator(task_id, action="execute")

            # 5. 验证阶段
            await self.update_status(task_id, "validating")
            validation = await self.invoke_validator(result)

            if validation.success:
                await self.update_status(task_id, "completed")
                await self.update_finding_status(task_id, "RESOLVED")
            else:
                await self.handle_validation_failure(task_id, validation)

        except Exception as e:
            await self.handle_execution_error(task_id, e)
```

---

### 3.2 Analyzer Agent (分析智能体)

#### 3.2.1 职责

| 职责 | 描述 |
|------|------|
| Finding 解析 | 解析 ASFF 格式的 Finding 数据 |
| 上下文收集 | 获取相关资源的配置信息 |
| 风险评估 | 评估 Finding 的实际风险等级 |
| 影响分析 | 分析修复可能带来的影响 |
| 分类判断 | 确定 Finding 类型和修复策略 |

#### 3.2.2 System Prompt

```markdown
# Role
You are the Analyzer Agent for the SHARA system. Your job is to deeply analyze
AWS Security Hub findings and provide comprehensive analysis for remediation planning.

# Capabilities
1. Parse and understand AWS Security Finding Format (ASFF)
2. Query AWS services to gather resource context
3. Assess actual security risk based on resource configuration
4. Identify the root cause of the security issue
5. Determine the appropriate remediation strategy

# Analysis Process
1. **Parse Finding**: Extract key information from the ASFF finding
2. **Identify Resource**: Determine the affected AWS resource(s)
3. **Gather Context**: Query AWS APIs to get current resource configuration
4. **Assess Risk**: Evaluate the actual risk level considering:
   - Data sensitivity
   - Network exposure
   - Compliance requirements
   - Business criticality
5. **Classify Issue**: Categorize the finding type for remediation routing
6. **Recommend Strategy**: Suggest the appropriate remediation approach

# Supported Finding Types
- S3: Public access, encryption, logging, versioning
- EC2: Security groups, instance metadata, EBS encryption
- IAM: Overprivileged roles, access keys, MFA
- RDS: Public access, encryption, backup
- Lambda: VPC configuration, permissions
- CloudTrail: Logging configuration
- GuardDuty: Threat detections
- Inspector: Vulnerability findings

# Output Format
Provide analysis in the following JSON structure:
{
  "findingType": "category of the finding",
  "resourceType": "AWS resource type",
  "resourceId": "resource ARN",
  "currentState": {...},
  "riskAssessment": {
    "level": "LOW|MEDIUM|HIGH|CRITICAL",
    "factors": [...],
    "justification": "..."
  },
  "rootCause": "description of the security issue",
  "remediationStrategy": "recommended approach",
  "additionalContext": {...}
}

# Important Notes
- Always use the appropriate AWS API tools to gather context
- Do not assume resource state - always verify
- Consider the blast radius of potential remediation
- Flag findings that may require manual intervention
```

#### 3.2.3 工具集

```python
ANALYZER_TOOLS = [
    # S3 分析工具
    Tool(
        name="get_s3_bucket_info",
        description="获取 S3 bucket 的完整配置信息",
        handler=get_s3_bucket_info,
        parameters={
            "bucket_name": "S3 bucket name"
        }
    ),
    Tool(
        name="get_s3_bucket_policy",
        description="获取 S3 bucket policy",
        handler=get_s3_bucket_policy,
        parameters={
            "bucket_name": "S3 bucket name"
        }
    ),
    Tool(
        name="analyze_s3_policy_risks",
        description="分析 S3 bucket policy 的风险点",
        handler=analyze_s3_policy_risks,
        parameters={
            "policy": "Bucket policy JSON"
        }
    ),

    # EC2 分析工具
    Tool(
        name="get_security_group_rules",
        description="获取安全组规则详情",
        handler=get_security_group_rules,
        parameters={
            "security_group_id": "Security group ID"
        }
    ),
    Tool(
        name="get_instance_info",
        description="获取 EC2 实例详情",
        handler=get_instance_info,
        parameters={
            "instance_id": "EC2 instance ID"
        }
    ),
    Tool(
        name="analyze_security_group_exposure",
        description="分析安全组的网络暴露风险",
        handler=analyze_security_group_exposure,
        parameters={
            "security_group_id": "Security group ID"
        }
    ),

    # IAM 分析工具
    Tool(
        name="get_iam_role_info",
        description="获取 IAM role 详情",
        handler=get_iam_role_info,
        parameters={
            "role_name": "IAM role name"
        }
    ),
    Tool(
        name="analyze_iam_permissions",
        description="分析 IAM 权限范围",
        handler=analyze_iam_permissions,
        parameters={
            "policy_document": "IAM policy JSON"
        }
    ),

    # 通用分析工具
    Tool(
        name="get_resource_tags",
        description="获取资源标签用于业务上下文判断",
        handler=get_resource_tags,
        parameters={
            "resource_arn": "Resource ARN"
        }
    ),
    Tool(
        name="get_cloudtrail_events",
        description="获取资源相关的 CloudTrail 事件",
        handler=get_cloudtrail_events,
        parameters={
            "resource_arn": "Resource ARN",
            "hours": "Hours to look back"
        }
    ),
    Tool(
        name="query_config_history",
        description="获取资源的配置变更历史",
        handler=query_config_history,
        parameters={
            "resource_type": "AWS Config resource type",
            "resource_id": "Resource identifier"
        }
    )
]
```

#### 3.2.4 分析流程示例

```python
class AnalyzerAgent:
    async def analyze(self, finding: dict) -> AnalysisResult:
        # 1. 解析 Finding
        finding_type = self.classify_finding(finding)
        resource = finding['Resources'][0]

        # 2. 获取资源上下文
        context = await self.gather_context(resource)

        # 3. 风险评估
        risk = await self.assess_risk(finding, context)

        # 4. 生成分析结果
        return AnalysisResult(
            finding_type=finding_type,
            resource_type=resource['Type'],
            resource_id=resource['Id'],
            current_state=context,
            risk_assessment=risk,
            root_cause=self.identify_root_cause(finding, context),
            remediation_strategy=self.recommend_strategy(finding_type, risk)
        )

    async def gather_context(self, resource: dict) -> dict:
        """根据资源类型收集上下文"""
        handlers = {
            'AwsS3Bucket': self.gather_s3_context,
            'AwsEc2SecurityGroup': self.gather_sg_context,
            'AwsIamRole': self.gather_iam_context,
            # ...
        }
        handler = handlers.get(resource['Type'])
        if handler:
            return await handler(resource['Id'])
        return {}
```

---

### 3.3 Remediator Agent (修复智能体)

#### 3.3.1 职责

| 职责 | 描述 |
|------|------|
| 方案生成 | 根据分析结果生成修复方案 |
| 代码生成 | 生成可执行的 AWS CLI/IaC 代码 |
| 影响评估 | 评估修复操作的潜在影响 |
| 回滚设计 | 设计回滚方案 |
| 执行修复 | 执行审批通过的修复操作 |

#### 3.3.2 System Prompt

```markdown
# Role
You are the Remediator Agent for the SHARA system. Your job is to generate and
execute remediation plans for AWS Security Hub findings.

# Capabilities
1. Generate comprehensive remediation plans based on analysis
2. Create executable AWS CLI commands
3. Generate Infrastructure as Code (CloudFormation/Terraform)
4. Assess potential impact of remediation actions
5. Design rollback procedures
6. Execute approved remediation actions safely

# Remediation Planning Guidelines
1. **Safety First**: Always design reversible changes when possible
2. **Minimal Impact**: Choose the least disruptive remediation approach
3. **Best Practices**: Follow AWS security best practices
4. **Documentation**: Provide clear descriptions for each step
5. **Validation**: Include validation steps in the plan

# Supported Remediation Types

## S3 Remediations
- Block public access
- Enable encryption (SSE-S3, SSE-KMS)
- Update bucket policy
- Enable versioning
- Configure logging

## EC2/Network Remediations
- Restrict security group rules
- Enable VPC flow logs
- Configure IMDS v2
- Enable EBS encryption

## IAM Remediations
- Reduce permissions (least privilege)
- Enable MFA
- Rotate access keys
- Update trust policies

# Plan Output Format
{
  "summary": "Brief description of remediation",
  "steps": [
    {
      "order": 1,
      "name": "step_identifier",
      "description": "Human readable description",
      "action": {
        "service": "aws_service",
        "operation": "api_operation",
        "parameters": {...}
      },
      "rollback": {...},
      "validation": {...}
    }
  ],
  "impactAssessment": {
    "serviceImpact": "none|minimal|significant",
    "downtime": "none|brief|extended",
    "dataLoss": false
  },
  "rollbackPlan": {...},
  "generatedCode": {
    "awsCli": "...",
    "cloudformation": "..."
  }
}

# Execution Guidelines
- Always verify current state before making changes
- Execute one step at a time
- Verify each step before proceeding
- Stop immediately on any error
- Preserve all evidence for audit
```

#### 3.3.3 工具集

```python
REMEDIATOR_TOOLS = [
    # 知识库查询
    Tool(
        name="search_playbook",
        description="搜索修复方案知识库",
        handler=search_playbook,
        parameters={
            "finding_type": "Finding type identifier",
            "resource_type": "AWS resource type"
        }
    ),
    Tool(
        name="get_remediation_template",
        description="获取修复模板",
        handler=get_remediation_template,
        parameters={
            "template_id": "Template identifier",
            "parameters": "Template parameters"
        }
    ),

    # S3 修复工具
    Tool(
        name="s3_put_public_access_block",
        description="配置 S3 Block Public Access",
        handler=s3_put_public_access_block,
        parameters={
            "bucket": "Bucket name",
            "config": "Block public access configuration"
        }
    ),
    Tool(
        name="s3_put_bucket_policy",
        description="更新 S3 bucket policy",
        handler=s3_put_bucket_policy,
        parameters={
            "bucket": "Bucket name",
            "policy": "New policy document"
        }
    ),
    Tool(
        name="s3_put_bucket_encryption",
        description="配置 S3 bucket 加密",
        handler=s3_put_bucket_encryption,
        parameters={
            "bucket": "Bucket name",
            "encryption_config": "Encryption configuration"
        }
    ),

    # EC2 修复工具
    Tool(
        name="ec2_revoke_security_group_ingress",
        description="移除安全组入站规则",
        handler=ec2_revoke_security_group_ingress,
        parameters={
            "group_id": "Security group ID",
            "rule": "Rule to remove"
        }
    ),
    Tool(
        name="ec2_authorize_security_group_ingress",
        description="添加安全组入站规则",
        handler=ec2_authorize_security_group_ingress,
        parameters={
            "group_id": "Security group ID",
            "rule": "Rule to add"
        }
    ),

    # IAM 修复工具
    Tool(
        name="iam_put_role_policy",
        description="更新 IAM role 内联策略",
        handler=iam_put_role_policy,
        parameters={
            "role_name": "Role name",
            "policy_name": "Policy name",
            "policy_document": "Policy JSON"
        }
    ),

    # Security Hub 更新
    Tool(
        name="update_finding_status",
        description="更新 Security Hub Finding 状态",
        handler=update_finding_status,
        parameters={
            "finding_id": "Finding ID",
            "status": "RESOLVED | SUPPRESSED",
            "note": "Status change note"
        }
    ),

    # 代码生成
    Tool(
        name="generate_cli_command",
        description="生成 AWS CLI 命令",
        handler=generate_cli_command,
        parameters={
            "service": "AWS service",
            "operation": "API operation",
            "parameters": "Operation parameters"
        }
    ),
    Tool(
        name="generate_cloudformation",
        description="生成 CloudFormation 模板片段",
        handler=generate_cloudformation,
        parameters={
            "resource_type": "CloudFormation resource type",
            "properties": "Resource properties"
        }
    )
]
```

#### 3.3.4 修复执行流程

```python
class RemediatorAgent:
    async def generate_plan(self, analysis: AnalysisResult) -> RemediationPlan:
        # 1. 查询知识库
        playbook = await self.search_playbook(
            analysis.finding_type,
            analysis.resource_type
        )

        # 2. 定制化方案
        plan = await self.customize_plan(playbook, analysis)

        # 3. 生成可执行代码
        plan.generated_code = await self.generate_code(plan)

        # 4. 设计回滚方案
        plan.rollback_plan = await self.design_rollback(plan)

        return plan

    async def execute(self, task_id: str) -> ExecutionResult:
        task = await self.get_task(task_id)
        plan = task.remediation

        results = []
        for step in plan.steps:
            try:
                # 执行步骤
                result = await self.execute_step(step)
                results.append(result)

                # 验证步骤结果
                if step.validation:
                    await self.validate_step(step.validation)

            except Exception as e:
                # 记录错误
                await self.log_error(task_id, step, e)

                # 决定是否回滚
                if self.should_rollback(e):
                    await self.rollback(task_id, results)

                raise

        return ExecutionResult(success=True, steps=results)
```

---

### 3.4 Validator Agent (验证智能体)

#### 3.4.1 职责

| 职责 | 描述 |
|------|------|
| 状态验证 | 验证资源达到预期安全状态 |
| 合规检查 | 确认修复满足合规要求 |
| 回归测试 | 确保修复未引入新问题 |
| 结果报告 | 生成验证报告 |

#### 3.4.2 System Prompt

```markdown
# Role
You are the Validator Agent for the SHARA system. Your job is to verify that
remediation actions have been successful and the security finding has been resolved.

# Responsibilities
1. Verify resource state matches expected secure configuration
2. Run additional security checks to ensure no regression
3. Update Security Hub finding status
4. Generate validation report

# Validation Process
1. **State Check**: Verify resource configuration matches expected state
2. **Security Scan**: Run additional security checks if applicable
3. **Side Effect Check**: Ensure no unintended changes occurred
4. **Compliance Verify**: Confirm compliance requirements are met
5. **Report Generation**: Document validation results

# Output Format
{
  "success": true|false,
  "checks": [
    {
      "name": "check_name",
      "passed": true|false,
      "expected": {...},
      "actual": {...},
      "message": "..."
    }
  ],
  "findingStatus": "RESOLVED|FAILED",
  "recommendations": [...],
  "report": {...}
}
```

#### 3.4.3 工具集

```python
VALIDATOR_TOOLS = [
    # 状态验证
    Tool(
        name="verify_s3_configuration",
        description="验证 S3 bucket 配置",
        handler=verify_s3_configuration,
        parameters={
            "bucket": "Bucket name",
            "expected_state": "Expected configuration"
        }
    ),
    Tool(
        name="verify_security_group",
        description="验证安全组规则",
        handler=verify_security_group,
        parameters={
            "group_id": "Security group ID",
            "expected_rules": "Expected rule set"
        }
    ),

    # 安全扫描
    Tool(
        name="run_config_evaluation",
        description="触发 AWS Config 规则重新评估",
        handler=run_config_evaluation,
        parameters={
            "resource_type": "Resource type",
            "resource_id": "Resource ID"
        }
    ),
    Tool(
        name="check_access_analyzer",
        description="检查 IAM Access Analyzer 结果",
        handler=check_access_analyzer,
        parameters={
            "resource_arn": "Resource ARN"
        }
    ),

    # Finding 更新
    Tool(
        name="update_security_hub_finding",
        description="更新 Security Hub Finding 状态",
        handler=update_security_hub_finding,
        parameters={
            "finding_id": "Finding ID",
            "workflow_status": "RESOLVED | NOTIFIED",
            "note": "Status note"
        }
    )
]
```

---

## 4. Agent 协作设计

### 4.1 通信协议

```python
@dataclass
class AgentMessage:
    """Agent 间通信消息格式"""
    message_id: str
    source_agent: str
    target_agent: str
    action: str
    payload: dict
    context: dict
    timestamp: str
    trace_id: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'AgentMessage':
        return cls(**data)
```

### 4.2 协作流程

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        Multi-Agent Collaboration Flow                         │
│                                                                               │
│   Lambda                                                                      │
│     │                                                                         │
│     │ 1. ProcessFinding(finding)                                              │
│     ▼                                                                         │
│  Orchestrator                                                                 │
│     │                                                                         │
│     │ 2. AnalyzeFinding(finding)                                              │
│     ├────────────────────────────▶ Analyzer                                   │
│     │                                   │                                     │
│     │◀──────────────────────────────────┤ 3. AnalysisResult                   │
│     │                                                                         │
│     │ 4. GeneratePlan(analysis)                                               │
│     ├────────────────────────────▶ Remediator                                 │
│     │                                   │                                     │
│     │◀──────────────────────────────────┤ 5. RemediationPlan                  │
│     │                                                                         │
│     │ 6. SendApprovalEmail(plan)                                              │
│     │────────────▶ SES ────────────▶ Admin                                    │
│     │                                                                         │
│     │           ... wait for approval ...                                     │
│     │                                                                         │
│     │◀──────────────────────────────────────── 7. ApprovalCallback            │
│     │                                                                         │
│     │ 8. ExecutePlan(plan)                                                    │
│     ├────────────────────────────▶ Remediator                                 │
│     │                                   │                                     │
│     │◀──────────────────────────────────┤ 9. ExecutionResult                  │
│     │                                                                         │
│     │ 10. ValidateFix(result)                                                 │
│     ├────────────────────────────▶ Validator                                  │
│     │                                   │                                     │
│     │◀──────────────────────────────────┤ 11. ValidationResult                │
│     │                                                                         │
│     │ 12. Complete                                                            │
│     ▼                                                                         │
│   Done                                                                        │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 4.3 错误处理与重试

```python
class AgentCoordinator:
    """Agent 协调器，处理 Agent 间的通信和错误"""

    async def invoke_agent(
        self,
        agent_type: str,
        action: str,
        payload: dict,
        max_retries: int = 3
    ) -> dict:
        for attempt in range(max_retries):
            try:
                result = await self._invoke(agent_type, action, payload)
                return result

            except RetryableError as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # 指数退避
                    continue
                raise

            except NonRetryableError as e:
                # 记录错误，不重试
                await self.log_error(agent_type, action, e)
                raise

    async def handle_agent_failure(
        self,
        task_id: str,
        agent_type: str,
        error: Exception
    ):
        """处理 Agent 执行失败"""
        # 更新任务状态
        await self.update_task_status(
            task_id,
            f"{agent_type}_failed",
            str(error)
        )

        # 发送告警
        await self.send_alert(
            f"Agent {agent_type} failed for task {task_id}",
            error
        )

        # 决定是否需要人工干预
        if self.requires_manual_intervention(error):
            await self.escalate_to_human(task_id, error)
```

---

## 5. LLM 配置

### 5.1 模型选择

| Agent | 模型 | 理由 |
|-------|------|------|
| Orchestrator | Claude 3.5 Sonnet | 平衡性能和成本，适合任务调度 |
| Analyzer | Claude 3.5 Sonnet | 需要强大的推理能力 |
| Remediator | Claude 3 Opus | 需要最强的代码生成能力 |
| Validator | Claude 3.5 Sonnet | 验证任务相对简单 |

### 5.2 模型参数

```python
MODEL_CONFIGS = {
    "orchestrator": {
        "model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "temperature": 0.3,
        "max_tokens": 4096,
        "top_p": 0.9
    },
    "analyzer": {
        "model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "temperature": 0.2,
        "max_tokens": 8192,
        "top_p": 0.9
    },
    "remediator": {
        "model_id": "anthropic.claude-3-opus-20240229-v1:0",
        "temperature": 0.1,  # 低温度确保代码生成稳定
        "max_tokens": 8192,
        "top_p": 0.95
    },
    "validator": {
        "model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "temperature": 0.1,
        "max_tokens": 4096,
        "top_p": 0.9
    }
}
```

---

## 6. 知识库集成

### 6.1 RAG (检索增强生成) 设计

```
┌─────────────────────────────────────────────────────────────┐
│                    Knowledge Base Integration                │
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   Playbook   │    │   Bedrock    │    │   Vector     │  │
│  │   Storage    │───▶│   Embedding  │───▶│   Store      │  │
│  │   (S3)       │    │              │    │   (OpenSearch│  │
│  └──────────────┘    └──────────────┘    │   Serverless)│  │
│                                           └───────┬──────┘  │
│                                                   │         │
│                                                   ▼         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   Agent      │◀───│   Bedrock    │◀───│   Semantic   │  │
│  │   (Query)    │    │   KB API     │    │   Search     │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 知识库查询示例

```python
async def search_remediation_playbook(
    finding_type: str,
    resource_type: str,
    context: dict
) -> List[Playbook]:
    """搜索最相关的修复 Playbook"""

    # 构建查询
    query = f"""
    Finding Type: {finding_type}
    Resource Type: {resource_type}
    Context: {json.dumps(context)}

    Find the most relevant remediation playbook for this security finding.
    """

    # 调用 Bedrock Knowledge Base
    response = await bedrock_kb.retrieve(
        knowledgeBaseId=KNOWLEDGE_BASE_ID,
        retrievalQuery={"text": query},
        retrievalConfiguration={
            "vectorSearchConfiguration": {
                "numberOfResults": 5
            }
        }
    )

    # 解析结果
    playbooks = []
    for result in response['retrievalResults']:
        playbook = await load_playbook(result['location']['s3Location'])
        playbooks.append(playbook)

    return playbooks
```

---

## 7. 监控与调试

### 7.1 Agent 执行追踪

```python
@dataclass
class AgentTrace:
    trace_id: str
    agent_type: str
    action: str
    start_time: datetime
    end_time: Optional[datetime]
    status: str
    input_tokens: int
    output_tokens: int
    tool_calls: List[dict]
    llm_calls: List[dict]
    errors: List[dict]

class AgentTracer:
    """Agent 执行追踪器"""

    def start_trace(self, agent_type: str, action: str) -> AgentTrace:
        return AgentTrace(
            trace_id=str(uuid.uuid4()),
            agent_type=agent_type,
            action=action,
            start_time=datetime.utcnow(),
            end_time=None,
            status="running",
            input_tokens=0,
            output_tokens=0,
            tool_calls=[],
            llm_calls=[],
            errors=[]
        )

    def record_tool_call(self, trace: AgentTrace, tool: str, input: dict, output: dict):
        trace.tool_calls.append({
            "tool": tool,
            "input": input,
            "output": output,
            "timestamp": datetime.utcnow().isoformat()
        })

    def record_llm_call(self, trace: AgentTrace, prompt: str, response: str, tokens: dict):
        trace.llm_calls.append({
            "prompt_preview": prompt[:500],
            "response_preview": response[:500],
            "tokens": tokens,
            "timestamp": datetime.utcnow().isoformat()
        })
        trace.input_tokens += tokens.get("input", 0)
        trace.output_tokens += tokens.get("output", 0)
```

### 7.2 日志格式

```json
{
  "timestamp": "2025-01-28T10:30:00.123Z",
  "level": "INFO",
  "logger": "shara.agent.analyzer",
  "trace_id": "1-abc123-def456",
  "span_id": "span-789",
  "task_id": "task-12345",
  "agent": "analyzer",
  "action": "analyze_finding",
  "message": "Starting finding analysis",
  "context": {
    "finding_id": "arn:aws:securityhub:...",
    "finding_type": "S3PublicAccess",
    "resource_type": "AwsS3Bucket"
  },
  "metrics": {
    "duration_ms": null,
    "tool_calls": 0,
    "llm_tokens": 0
  }
}
```

---

## 8. 文档版本

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| 1.0 | 2025-01-28 | - | 初始版本 |
