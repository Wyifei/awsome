# SHARA Agent 开发 TODO

> 上次更新: 2025-01-29
> 状态: 文档设计阶段完成，待开始代码实现

---

## 已完成

- [x] 创建项目目录结构 `agent/doc/`
- [x] 需求文档 `requirements.md`
- [x] 架构设计文档 `architecture.md`
- [x] API 设计文档 `api-design.md`
- [x] 数据模型文档 `data-model.md`
- [x] 智能体设计文档 `agent-design.md`
- [x] 部署指南 `deployment-guide.md`
- [x] 修复方案知识库 `remediation-playbooks.md`
- [x] AgentCore 集成指南 `agentcore-integration.md`

---

## 待完成

### Phase 1: 项目框架搭建

- [ ] 创建 Python 项目结构
  ```
  agent/
  ├── src/
  │   ├── agents/           # Agent 实现
  │   ├── tools/            # AWS API 工具
  │   ├── playbooks/        # Playbook 加载器
  │   ├── handlers/         # Lambda handlers
  │   └── utils/            # 工具函数
  ├── infrastructure/       # CDK 代码
  ├── knowledge-base/       # Playbook YAML 文件
  └── tests/               # 测试代码
  ```

- [ ] 配置 `pyproject.toml` / `requirements.txt`
- [ ] 配置 CDK 项目 (`cdk.json`, `package.json`)

### Phase 2: 基础设施代码

- [ ] Network Stack (VPC, Endpoints)
- [ ] Storage Stack (DynamoDB, S3)
- [ ] Agent Stack (Lambda functions)
- [ ] API Stack (API Gateway)
- [ ] Event Stack (EventBridge rules)

### Phase 3: Agent 实现

- [ ] 实现 Orchestrator Agent
  - [ ] System prompt 配置
  - [ ] 状态机逻辑
  - [ ] 子 Agent 调用
- [ ] 实现 Analyzer Agent
  - [ ] Finding 解析
  - [ ] 上下文收集工具
  - [ ] 风险评估逻辑
- [ ] 实现 Remediator Agent
  - [ ] Playbook 检索
  - [ ] 方案生成
  - [ ] 修复执行
- [ ] 实现 Validator Agent
  - [ ] 状态验证
  - [ ] Finding 更新

### Phase 4: 工具实现

- [ ] S3 操作工具
- [ ] EC2/Security Group 工具
- [ ] IAM 工具
- [ ] Security Hub 工具
- [ ] SES 邮件工具

### Phase 5: 审批流程

- [ ] 邮件模板设计
- [ ] Token 生成/验证
- [ ] API Gateway 回调端点
- [ ] 审批状态管理

### Phase 6: 知识库

- [ ] 创建 Playbook YAML 文件结构
- [ ] S3 Playbooks (public access, encryption, logging)
- [ ] EC2 Playbooks (security groups, IMDS)
- [ ] IAM Playbooks (MFA, permissions)
- [ ] 配置 Bedrock Knowledge Base

### Phase 7: 测试

- [ ] 单元测试
- [ ] 集成测试
- [ ] E2E 测试
- [ ] 测试 Finding 生成脚本

### Phase 8: 部署与验证

- [ ] 开发环境部署
- [ ] 功能验证
- [ ] 性能测试
- [ ] 文档更新

---

## 注意事项

1. **Strands Agent SDK** - 需要确认最新版本和 API
2. **Bedrock 模型访问** - 确保 Claude 模型已申请
3. **SES 验证** - 需要验证发送域名
4. **IAM 权限** - 注意最小权限原则

---

## 参考资源

- [AWS Strands Agent](https://github.com/strands-agents/strands-agents)
- [Amazon Bedrock](https://docs.aws.amazon.com/bedrock/)
- [Security Hub ASFF](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-findings-format.html)
- [AWS CDK](https://docs.aws.amazon.com/cdk/)
