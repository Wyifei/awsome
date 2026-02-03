# 统一身份认证平台 - 设计文档

## 1. 架构概述

### 1.1 系统架构

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                    微服务架构                                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                         前端微服务 (Frontend Service)                     │   │
│   │                              部署: S3 + CloudFront                       │   │
│   │                              技术: React + TypeScript + Ant Design       │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
│                                         │                                       │
│                                         │ API 调用                              │
│                                         ▼                                       │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                              API Gateway (ALB)                           │   │
│   └───────────────────┬─────────────────┬─────────────────┬─────────────────┘   │
│                       │                 │                 │                     │
│                       ▼                 ▼                 ▼                     │
│   ┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐       │
│   │   User Service      │ │  Profile Service    │ │Notification Service │       │
│   │   (Spring Boot)     │ │   (Spring Boot)     │ │   (Spring Boot)     │       │
│   │   部署: EKS         │ │   部署: EKS         │ │   部署: EKS         │       │
│   └──────────┬──────────┘ └──────────┬──────────┘ └──────────┬──────────┘       │
│              │                       │                       │                  │
│              ▼                       ▼                       ▼                  │
│   ┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐       │
│   │     Cognito         │ │      Aurora         │ │     Amazon SES      │       │
│   │   (Admin API)       │ │   (PostgreSQL)      │ │    (邮件发送)        │       │
│   └─────────────────────┘ └─────────────────────┘ └─────────────────────┘       │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 技术栈

| 层级 | 技术选型 | 版本 |
|------|---------|------|
| 前端框架 | React + TypeScript | 18.x / 5.x |
| UI 组件库 | Ant Design | 5.x |
| 构建工具 | Vite | 5.x |
| 认证 SDK | AWS Amplify | 6.x |
| 后端框架 | Spring Boot | 3.2 |
| 运行时 | Java | 21 |
| 数据库 | Aurora PostgreSQL | 15.x |
| 认证服务 | Amazon Cognito | - |
| 邮件服务 | Amazon SES | - |
| 容器编排 | Amazon EKS | 1.31 |
| CDN | CloudFront | - |

## 2. 服务设计

### 2.1 Frontend Service

**职责：** 用户界面、Cognito 认证集成

**技术栈：** React 18 + TypeScript + Vite + Ant Design

**部署：** S3 + CloudFront

**项目结构：**
```
frontend/
├── src/
│   ├── components/           # 通用组件
│   │   ├── LoadingSpinner.tsx
│   │   └── MainLayout.tsx
│   ├── contexts/             # React Context
│   │   └── AuthContext.tsx
│   ├── hooks/                # 自定义 Hooks
│   │   └── useAuth.ts
│   ├── pages/                # 页面组件
│   │   ├── LoginPage.tsx
│   │   ├── RegisterPage.tsx
│   │   ├── DashboardPage.tsx
│   │   ├── ProfilePage.tsx
│   │   └── DeleteAccountPage.tsx
│   ├── services/             # API 服务
│   │   ├── api.ts
│   │   ├── authService.ts
│   │   ├── userService.ts
│   │   └── profileService.ts
│   ├── types/                # 类型定义
│   │   └── index.ts
│   ├── App.tsx
│   └── main.tsx
```

**认证流程：**
1. 用户通过 Amplify SDK 与 Cognito 交互
2. 登录成功后获取 JWT Token
3. API 请求自动携带 Authorization Header
4. Token 过期自动刷新

### 2.2 User Service

**职责：** 用户身份管理、注册流程、验证码管理、账户生命周期

**技术栈：** Spring Boot 3.2 + AWS SDK

**端口：** 8080

**API 前缀：** /api/users

**项目结构：**
```
user-service/
├── controller/
│   ├── AuthController.java      # 注册/验证 API
│   └── UserController.java      # 已认证用户 API
├── service/
│   ├── AuthService.java         # 注册/验证业务逻辑
│   ├── UserService.java         # 用户业务逻辑
│   ├── CognitoService.java      # Cognito 操作封装
│   └── VerificationCodeService.java
├── entity/
│   ├── User.java
│   └── VerificationCode.java
├── repository/
│   ├── UserRepository.java
│   └── VerificationCodeRepository.java
├── dto/
│   ├── RegisterRequest.java
│   ├── VerifyEmailRequest.java
│   ├── ForgotPasswordRequest.java
│   ├── ResetPasswordRequest.java
│   ├── ChangePasswordRequest.java
│   └── ApiResponse.java
├── client/
│   └── NotificationServiceClient.java
└── exception/
    ├── EmailAlreadyExistsException.java
    ├── InvalidVerificationCodeException.java
    └── ResourceNotFoundException.java
```

**API 设计：**

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| POST | /api/users/register | 否 | 用户注册 |
| POST | /api/users/verify-email | 否 | 邮箱验证 |
| POST | /api/users/resend-verification | 否 | 重发验证码 |
| POST | /api/users/forgot-password | 否 | 忘记密码 |
| POST | /api/users/reset-password | 否 | 重置密码 |
| GET | /api/users/me | 是 | 获取当前用户 |
| POST | /api/users/me/change-password | 是 | 修改密码 |
| DELETE | /api/users/me | 是 | 删除账户 |
| POST | /api/users/delete-account/send-code | 是 | 发送注销验证码 |
| POST | /api/users/delete-account/confirm | 是 | 确认注销 |

### 2.3 Profile Service

**职责：** 用户个人资料管理、头像处理

**技术栈：** Spring Boot 3.2

**端口：** 8080

**API 前缀：** /api/profiles

**项目结构：**
```
profile-service/
├── controller/
│   └── ProfileController.java
├── service/
│   ├── ProfileService.java
│   └── AvatarService.java
├── entity/
│   └── UserProfile.java
├── repository/
│   └── UserProfileRepository.java
├── dto/
│   ├── ProfileResponse.java
│   ├── UpdateProfileRequest.java
│   └── AvatarResponse.java
├── client/
│   └── NotificationServiceClient.java
└── exception/
    ├── ResourceNotFoundException.java
    └── AvatarUploadException.java
```

**API 设计：**

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| GET | /api/profiles/me | 是 | 获取当前用户资料 |
| PUT | /api/profiles/me | 是 | 更新用户资料 |
| POST | /api/profiles/me/avatar | 是 | 上传头像 |
| DELETE | /api/profiles/me/avatar | 是 | 删除头像 |

### 2.4 Notification Service

**职责：** 邮件通知发送

**技术栈：** Spring Boot 3.2 + Amazon SES

**端口：** 8080

**API 前缀：** /api/notifications

**项目结构：**
```
notification-service/
├── controller/
│   └── NotificationController.java
├── service/
│   └── EmailService.java
├── dto/
│   ├── EmailRequest.java
│   ├── EmailResponse.java
│   └── VerificationCodeRequest.java
├── config/
│   └── SesConfig.java
└── exception/
    └── EmailSendException.java
```

**API 设计：**

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| POST | /api/notifications/verification-code | 内部 | 发送验证码邮件 |
| POST | /api/notifications/welcome | 内部 | 发送欢迎邮件 |
| POST | /api/notifications/password-changed | 内部 | 发送密码变更通知 |
| POST | /api/notifications/profile-updated | 内部 | 发送资料变更通知 |
| POST | /api/notifications/account-deleted | 内部 | 发送账号删除通知 |

## 3. 数据模型

### 3.1 Users 表 (users)

用户数据采用单表设计，身份信息由 user-service 管理，资料信息由 profile-service 管理。

```sql
CREATE TABLE users (
    -- 身份信息 (由 user-service 管理)
    id                    VARCHAR(36) PRIMARY KEY,  -- Cognito user sub (UUID)
    email                 VARCHAR(256) NOT NULL UNIQUE,
    username              VARCHAR(128) NOT NULL UNIQUE,
    phone_number          VARCHAR(20),              -- E.164 格式
    status                VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE, INACTIVE, SUSPENDED
    email_verified        BOOLEAN NOT NULL DEFAULT FALSE,
    phone_number_verified BOOLEAN DEFAULT FALSE,

    -- 资料信息 (由 profile-service 管理)
    nickname              VARCHAR(64),
    avatar                VARCHAR(512),             -- S3/CloudFront URL (已弃用)
    avatar_data           BYTEA,                    -- 头像二进制数据
    avatar_content_type   VARCHAR(100),             -- 头像 MIME 类型
    gender                VARCHAR(10),              -- MALE, FEMALE, OTHER
    birthday              DATE,
    address               VARCHAR(256),
    preferences           JSONB,                    -- 用户偏好设置 JSON

    -- 时间戳
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_status ON users(status);
CREATE INDEX idx_users_created_at ON users(created_at);
```

**字段说明：**
- `id`: Cognito 用户 sub (UUID)，主键标识
- `status`: 账户状态，可选值：ACTIVE（活跃）、INACTIVE（未激活）、SUSPENDED（已暂停）
- `avatar_data`: 头像图片直接存储在数据库中的二进制数据
- `avatar_content_type`: 头像图片的 MIME 类型（如 image/jpeg, image/png）
- `preferences`: JSON 格式的用户偏好设置

### 3.2 VerificationCodes 表 (verification_codes)

用于存储邮箱验证码和密码重置码。

```sql
CREATE TABLE verification_codes (
    id          BIGSERIAL PRIMARY KEY,
    email       VARCHAR(256) NOT NULL,
    code        VARCHAR(6) NOT NULL,
    type        VARCHAR(20) NOT NULL,       -- EMAIL_VERIFICATION, PASSWORD_RESET
    expires_at  TIMESTAMP NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 索引
CREATE INDEX idx_verification_codes_email_type ON verification_codes(email, type);
CREATE INDEX idx_verification_codes_expires_at ON verification_codes(expires_at);
```

**字段说明：**
- `code`: 6位数字验证码
- `type`: 验证码类型，可选值：EMAIL_VERIFICATION（邮箱验证）、PASSWORD_RESET（密码重置）
- `expires_at`: 验证码过期时间，通常为创建后15分钟

## 4. 统一响应格式

```json
{
  "success": true,
  "code": "SUCCESS",
  "message": "操作成功",
  "data": { ... },
  "timestamp": "2024-01-28T10:30:00Z"
}
```

**错误码定义：**

| 错误码 | HTTP 状态 | 说明 |
|--------|----------|------|
| SUCCESS | 200 | 操作成功 |
| REGISTRATION_PENDING | 200 | 注册成功，待验证 |
| EMAIL_VERIFIED | 200 | 邮箱验证成功 |
| USER_NOT_FOUND | 404 | 用户不存在 |
| EMAIL_ALREADY_EXISTS | 409 | 邮箱已注册 |
| INVALID_VERIFICATION_CODE | 400 | 验证码无效 |
| INVALID_PASSWORD | 400 | 密码格式错误 |
| PASSWORD_MISMATCH | 400 | 原密码错误 |
| UNAUTHORIZED | 401 | 未授权 |
| INTERNAL_ERROR | 500 | 服务器错误 |

## 5. 安全设计

### 5.1 认证机制

- 使用 Amazon Cognito 作为身份提供者
- 前端通过 Amplify SDK 进行认证
- 后端通过 JWT 验证（OAuth2 Resource Server）
- Token 配置：Access Token 1小时，Refresh Token 30天

### 5.2 API 安全

- 所有 API 通过 HTTPS
- 需要认证的 API 验证 JWT Token
- 使用 Spring Security 配置访问控制
- Actuator 端点允许匿名访问（健康检查）

### 5.3 数据安全

- 密码由 Cognito 托管，使用 SRP 协议
- 验证码有效期15分钟
- 敏感信息不记录到日志
- 数据库使用 Aurora 加密存储

## 6. 可观测性设计

### 6.1 日志规范

- 使用 JSON 格式输出
- 包含 trace_id 支持分布式追踪
- 记录请求开始/结束、响应时间
- 业务事件使用 LogEvent 工具类

### 6.2 指标暴露

- 端点：/actuator/prometheus
- 包含 HTTP 请求指标
- 包含业务指标（注册数、登录数等）
- 使用 Micrometer + Prometheus

### 6.3 健康检查

- Liveness: /actuator/health/liveness
- Readiness: /actuator/health/readiness

## 7. 部署架构

### 7.1 Kubernetes 部署

- 命名空间：auth-platform
- 每个服务独立 Deployment
- 使用 Kustomize 管理配置
- 支持 dev/production 环境

### 7.2 资源配置

| 环境 | 副本数 | CPU | 内存 |
|------|--------|-----|------|
| Dev | 1 | 50m | 128Mi |
| Production | 2-10 | 250m | 512Mi |

### 7.3 自动扩缩

- HPA 基于 CPU (70%) 和内存 (80%)
- 最小副本：2，最大副本：10
- PDB：minAvailable: 1

## 8. 正确性属性

### 8.1 用户注册属性

- **P1**: 相同邮箱不能重复注册
- **P2**: 注册成功后用户状态为 PENDING_VERIFICATION
- **P3**: 注册成功后必须发送验证码邮件

### 8.2 邮箱验证属性

- **P4**: 验证码过期后不能使用
- **P5**: 验证码只能使用一次
- **P6**: 验证成功后用户状态变为 ACTIVE

### 8.3 密码管理属性

- **P7**: 密码必须满足强度要求
- **P8**: 修改密码需要验证原密码
- **P9**: 重置密码需要有效验证码

### 8.4 账号注销属性

- **P10**: 注销需要验证码确认
- **P11**: 注销后 Cognito 和本地数据同时删除
- **P12**: 注销操作不可逆

## 9. 依赖关系

```
Frontend
    └── Cognito (认证)
    └── User Service (身份信息)
    └── Profile Service (资料管理)

User Service
    └── Cognito (用户管理)
    └── Aurora (数据存储)
    └── Notification Service (邮件发送)

Profile Service
    └── Aurora (数据存储)
    └── Notification Service (邮件发送)

Notification Service
    └── Amazon SES (邮件发送)
```
