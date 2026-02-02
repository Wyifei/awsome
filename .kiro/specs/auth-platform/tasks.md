# 统一身份认证平台 - 任务清单

> 状态说明：[x] 已完成 | [ ] 未开始 | [-] 进行中

## 1. 基础设施搭建

- [x] 1.1 VPC 网络配置
  - [x] 1.1.1 创建 VPC (10.0.0.0/16)
  - [x] 1.1.2 配置公有子网和私有子网
  - [x] 1.1.3 配置 NAT Gateway
  - [x] 1.1.4 配置 VPC Endpoints

- [x] 1.2 安全配置
  - [x] 1.2.1 配置安全组
  - [x] 1.2.2 配置 WAF 规则
  - [x] 1.2.3 配置 IAM 角色和策略

- [x] 1.3 数据库配置
  - [x] 1.3.1 创建 Aurora PostgreSQL 集群
  - [x] 1.3.2 配置数据库参数组
  - [x] 1.3.3 配置 Secrets Manager

- [x] 1.4 Cognito 配置
  - [x] 1.4.1 创建 User Pool
  - [x] 1.4.2 配置 App Client
  - [x] 1.4.3 配置密码策略
  - [x] 1.4.4 配置邮箱验证

- [x] 1.5 EKS 集群配置
  - [x] 1.5.1 创建 EKS 集群
  - [x] 1.5.2 配置节点组
  - [x] 1.5.3 安装 Add-ons (vpc-cni, coredns, kube-proxy)
  - [x] 1.5.4 配置 ALB Controller
  - [x] 1.5.5 配置 IRSA

- [x] 1.6 监控配置
  - [x] 1.6.1 配置 Prometheus
  - [x] 1.6.2 配置 Grafana
  - [x] 1.6.3 配置 CloudWatch 日志组

- [x] 1.7 CDN 配置
  - [x] 1.7.1 创建 S3 存储桶
  - [x] 1.7.2 配置 CloudFront Distribution
  - [x] 1.7.3 配置 OAC

## 2. User Service 开发

- [x] 2.1 项目初始化
  - [x] 2.1.1 创建 Spring Boot 项目
  - [x] 2.1.2 配置 pom.xml 依赖
  - [x] 2.1.3 配置 application.yml

- [x] 2.2 数据层实现
  - [x] 2.2.1 创建 User 实体
  - [x] 2.2.2 创建 VerificationCode 实体
  - [x] 2.2.3 创建 UserRepository
  - [x] 2.2.4 创建 VerificationCodeRepository
  - [x] 2.2.5 配置 Flyway 数据库迁移

- [x] 2.3 Cognito 集成
  - [x] 2.3.1 配置 CognitoConfig
  - [x] 2.3.2 实现 CognitoService
  - [x] 2.3.3 实现用户创建
  - [x] 2.3.4 实现邮箱验证状态更新
  - [x] 2.3.5 实现密码管理

- [x] 2.4 注册功能实现
  - [x] 2.4.1 实现 RegisterRequest DTO
  - [x] 2.4.2 实现 AuthService.register()
  - [x] 2.4.3 实现 AuthController.register()
  - [x] 2.4.4 实现邮箱重复检查

- [x] 2.5 邮箱验证功能实现
  - [x] 2.5.1 实现 VerificationCodeService
  - [x] 2.5.2 实现验证码生成
  - [x] 2.5.3 实现验证码验证
  - [x] 2.5.4 实现 AuthController.verifyEmail()
  - [x] 2.5.5 实现重发验证码

- [x] 2.6 密码管理功能实现
  - [x] 2.6.1 实现 ForgotPasswordRequest DTO
  - [x] 2.6.2 实现 ResetPasswordRequest DTO
  - [x] 2.6.3 实现 AuthService.forgotPassword()
  - [x] 2.6.4 实现 AuthService.resetPassword()
  - [x] 2.6.5 实现 UserService.changePassword()

- [x] 2.7 用户信息功能实现
  - [x] 2.7.1 实现 UserDto
  - [x] 2.7.2 实现 UserController.getCurrentUser()
  - [x] 2.7.3 实现 JWT Token 解析

- [x] 2.8 账号注销功能实现
  - [x] 2.8.1 实现 DeleteAccountSendCodeRequest DTO
  - [x] 2.8.2 实现 DeleteAccountConfirmRequest DTO
  - [x] 2.8.3 实现 UserService.sendDeleteAccountCode()
  - [x] 2.8.4 实现 UserService.confirmDeleteAccount()
  - [x] 2.8.5 实现 UserController.deleteCurrentUser()

- [x] 2.9 安全配置
  - [x] 2.9.1 配置 SecurityConfig
  - [x] 2.9.2 配置 OAuth2 Resource Server
  - [x] 2.9.3 配置 Actuator 端点放行

- [x] 2.10 可观测性实现
  - [x] 2.10.1 配置 logback-spring.xml
  - [x] 2.10.2 实现 LoggingFilter
  - [x] 2.10.3 实现 LogEvent 工具类
  - [x] 2.10.4 实现 BusinessMetrics
  - [x] 2.10.5 配置 Prometheus 端点

## 3. Profile Service 开发

- [x] 3.1 项目初始化
  - [x] 3.1.1 创建 Spring Boot 项目
  - [x] 3.1.2 配置 pom.xml 依赖
  - [x] 3.1.3 配置 application.yml

- [x] 3.2 数据层实现
  - [x] 3.2.1 创建 UserProfile 实体
  - [x] 3.2.2 创建 UserProfileRepository

- [x] 3.3 资料管理功能实现
  - [x] 3.3.1 实现 ProfileResponse DTO
  - [x] 3.3.2 实现 UpdateProfileRequest DTO
  - [x] 3.3.3 实现 ProfileService.getProfile()
  - [x] 3.3.4 实现 ProfileService.updateProfile()
  - [x] 3.3.5 实现 ProfileController

- [x] 3.4 头像管理功能实现
  - [x] 3.4.1 实现 AvatarService
  - [x] 3.4.2 实现头像上传（Base64 存储）
  - [x] 3.4.3 实现头像删除
  - [x] 3.4.4 实现 AvatarResponse DTO

- [x] 3.5 通知集成
  - [x] 3.5.1 实现 NotificationServiceClient
  - [x] 3.5.2 资料更新后发送通知

- [x] 3.6 安全配置
  - [x] 3.6.1 配置 SecurityConfig
  - [x] 3.6.2 配置 OAuth2 Resource Server

- [x] 3.7 可观测性实现
  - [x] 3.7.1 配置 logback-spring.xml
  - [x] 3.7.2 实现 LoggingFilter
  - [x] 3.7.3 实现 BusinessMetrics

## 4. Notification Service 开发

- [x] 4.1 项目初始化
  - [x] 4.1.1 创建 Spring Boot 项目
  - [x] 4.1.2 配置 pom.xml 依赖
  - [x] 4.1.3 配置 application.yml

- [x] 4.2 SES 集成
  - [x] 4.2.1 配置 SesConfig
  - [x] 4.2.2 实现 EmailService

- [x] 4.3 邮件功能实现
  - [x] 4.3.1 实现 VerificationCodeRequest DTO
  - [x] 4.3.2 实现 EmailRequest DTO
  - [x] 4.3.3 实现验证码邮件发送
  - [x] 4.3.4 实现欢迎邮件发送
  - [x] 4.3.5 实现密码变更通知
  - [x] 4.3.6 实现资料变更通知
  - [x] 4.3.7 实现账号删除通知

- [x] 4.4 API 实现
  - [x] 4.4.1 实现 NotificationController
  - [x] 4.4.2 实现各类邮件发送端点

- [x] 4.5 可观测性实现
  - [x] 4.5.1 配置 logback-spring.xml
  - [x] 4.5.2 实现 LoggingFilter
  - [x] 4.5.3 实现 BusinessMetrics

## 5. Frontend 开发

- [x] 5.1 项目初始化
  - [x] 5.1.1 创建 Vite + React + TypeScript 项目
  - [x] 5.1.2 配置 Ant Design
  - [x] 5.1.3 配置 AWS Amplify
  - [x] 5.1.4 配置环境变量

- [x] 5.2 认证模块实现
  - [x] 5.2.1 实现 AuthContext
  - [x] 5.2.2 实现 useAuth Hook
  - [x] 5.2.3 实现 authService

- [x] 5.3 页面实现
  - [x] 5.3.1 实现 LoginPage
  - [x] 5.3.2 实现 RegisterPage（含验证码确认）
  - [x] 5.3.3 实现 DashboardPage
  - [x] 5.3.4 实现 ProfilePage
  - [x] 5.3.5 实现 DeleteAccountPage

- [x] 5.4 组件实现
  - [x] 5.4.1 实现 MainLayout
  - [x] 5.4.2 实现 LoadingSpinner

- [x] 5.5 API 服务实现
  - [x] 5.5.1 实现 api.ts（Fetch 封装）
  - [x] 5.5.2 实现 userService.ts
  - [x] 5.5.3 实现 profileService.ts

- [x] 5.6 路由配置
  - [x] 5.6.1 配置 React Router
  - [x] 5.6.2 配置路由守卫

- [x] 5.7 类型定义
  - [x] 5.7.1 定义 User 类型
  - [x] 5.7.2 定义 UserProfile 类型
  - [x] 5.7.3 定义 ApiResponse 类型

## 6. Kubernetes 部署配置

- [x] 6.1 User Service 部署
  - [x] 6.1.1 创建 Dockerfile
  - [x] 6.1.2 创建 Kustomize base 配置
  - [x] 6.1.3 创建 production overlay
  - [x] 6.1.4 配置 HPA
  - [x] 6.1.5 配置 PDB

- [x] 6.2 Profile Service 部署
  - [x] 6.2.1 创建 Dockerfile
  - [x] 6.2.2 创建 Kustomize base 配置
  - [x] 6.2.3 创建 production overlay
  - [x] 6.2.4 配置 HPA
  - [x] 6.2.5 配置 PDB

- [x] 6.3 Notification Service 部署
  - [x] 6.3.1 创建 Dockerfile
  - [x] 6.3.2 创建 Kustomize base 配置
  - [x] 6.3.3 创建 production overlay
  - [x] 6.3.4 配置 HPA
  - [x] 6.3.5 配置 PDB

- [x] 6.4 Ingress 配置
  - [x] 6.4.1 配置 ALB Ingress
  - [x] 6.4.2 配置 SSL 证书
  - [x] 6.4.3 配置路由规则

## 7. 部署脚本

- [x] 7.1 后端部署脚本
  - [x] 7.1.1 创建 build-backend.sh
  - [x] 7.1.2 创建 deploy-backend.sh
  - [x] 7.1.3 实现 Terraform 输出获取
  - [x] 7.1.4 实现 Secrets 自动创建

- [x] 7.2 前端部署脚本
  - [x] 7.2.1 创建 deploy-frontend.sh
  - [x] 7.2.2 创建 generate-frontend-env.sh
  - [x] 7.2.3 实现 S3 同步
  - [x] 7.2.4 实现 CloudFront 缓存失效

## 8. 文档编写

- [x] 8.1 架构文档
  - [x] 8.1.1 编写 application-architecture.md
  - [x] 8.1.2 编写 infrastructure-architecture.md

- [x] 8.2 运维文档
  - [x] 8.2.1 编写 deployment-guide.md
  - [x] 8.2.2 编写 observability-guide.md

- [x] 8.3 Spec 文档
  - [x] 8.3.1 编写 requirements.md
  - [x] 8.3.2 编写 design.md
  - [x] 8.3.3 编写 tasks.md

## 9. 测试（可选）

- [ ]* 9.1 单元测试
  - [ ]* 9.1.1 User Service 单元测试
  - [ ]* 9.1.2 Profile Service 单元测试
  - [ ]* 9.1.3 Notification Service 单元测试

- [ ]* 9.2 集成测试
  - [ ]* 9.2.1 API 集成测试
  - [ ]* 9.2.2 数据库集成测试

- [ ]* 9.3 端到端测试
  - [ ]* 9.3.1 注册流程测试
  - [ ]* 9.3.2 登录流程测试
  - [ ]* 9.3.3 资料管理测试
