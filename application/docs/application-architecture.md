# 应用架构文档

## 1. 系统概述

### 1.1 背景

为电动自行车制造企业构建基于 OIDC 协议的统一身份认证平台，服务于官网、移动 APP 等多端应用。

### 1.2 目标

- 提供统一的用户身份认证服务
- 支持密码登录（标准 OAuth2 流程）
- 支持多端接入（Web、移动 APP、第三方应用）
- 符合 OIDC/OAuth 2.0 标准
- 高可用、可扩展、安全可靠

### 1.3 核心功能

| 功能模块 | 实现方式 | 说明 |
|---------|---------|------|
| 用户注册 | User Service + Cognito | 账号创建，User Service 生成验证码 |
| 邮箱验证 | User Service + Notification Service | User Service 验证，Notification Service 发送邮件 |
| 用户登录 | Cognito | 用户名+密码，标准 OAuth2 流程 |
| OIDC 认证 | Cognito | 标准 OIDC/OAuth2 流程 |
| 密码重置 | User Service + Notification Service | User Service 生成验证码，Notification Service 发送邮件 |
| 用户资料管理 | Profile Service | 用户基本档案修改 |
| 账号管理 | User Service | 用户账号注册/删除 |
| 邮件通知 | Notification Service | 所有邮件通知 (验证码/欢迎/密码变更/资料变更/账号删除) |

---

## 2. 微服务架构

### 2.1 服务总览

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                    微服务架构                                     │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                         前端微服务 (Frontend Service)                     │   │
│   │                              部署: S3 + CloudFront                       │   │
│   │                              技术: React + TypeScript                    │   │
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
│   │                     │ │                     │ │                     │       │
│   │ • 用户注册           │ │ • 资料查看/修改      │ │ • 账号修改通知       │       │
│   │ • 用户删除/注销      │ │ • 基本信息维护       │ │ • 账号删除通知       │       │
│   │ • 账号状态管理       │ │                     │ │                     │       │
│   │                     │ │                     │ │                     │       │
│   │ 部署: EKS           │ │ 部署: EKS           │ │ 部署: EKS           │       │
│   └──────────┬──────────┘ └──────────┬──────────┘ └──────────┬──────────┘       │
│              │                       │                       │                  │
│              ▼                       ▼                       ▼                  │
│   ┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐       │
│   │     Cognito         │ │      Aurora         │ │     Amazon SES      │       │
│   │   (Admin API)       │ │    (user_profiles)  │ │    (邮件发送)        │       │
│   └─────────────────────┘ └─────────────────────┘ └─────────────────────┘       │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 服务职责划分

| 服务 | 职责 | 部署位置 | 数据存储 |
|------|------|---------|---------|
| Frontend Service | 用户界面、Cognito 认证集成 | S3 + CloudFront | - |
| User Service | 用户身份管理、认证状态同步、账户生命周期、密码修改 | EKS | Cognito + Aurora |
| Profile Service | 用户个人资料管理、头像文件处理 | EKS | Aurora + S3 |
| Notification Service | 账号修改/删除通知邮件 | EKS | SES |

### 2.3 User Service 与 Profile Service 职责边界

```
┌─────────────────────────────────────────────────────────────┐
│                    users 表 (共享)                           │
├─────────────────────────────┬───────────────────────────────┤
│   user-service 管理 (R/W)   │   profile-service 管理 (R/W)  │
│   ─────────────────────────┼───────────────────────────────│
│   id (PK)                   │   nickname                    │
│   username                  │   avatar                      │
│   email                     │   gender                      │
│   phone_number              │   birthday                    │
│   email_verified            │   address                     │
│   phone_number_verified     │   preferences                 │
│   status                    │                               │
│   created_at                │   updated_at (共享)           │
└─────────────────────────────┴───────────────────────────────┘

读写权限说明：
- user-service：Identity 字段 (R/W)，Profile 字段 (R)
- profile-service：Identity 字段 (R)，Profile 字段 (R/W)
```

---

## 3. 前端微服务 (Frontend Service)

### 3.1 服务概述

| 属性 | 值 |
|------|-----|
| 服务名称 | frontend |
| 部署位置 | S3 + CloudFront |
| 技术栈 | React 18 + TypeScript + Vite + Ant Design |
| 访问域名 | CloudFront 默认域名 (*.cloudfront.net) |

### 3.2 职责

```
Frontend
├── 用户界面 (Ant Design 组件库)
│   ├── 登录页面 (自定义 UI，使用 Amplify SDK 认证)
│   ├── 注册页面 (含邮箱验证码确认)
│   ├── 仪表盘页面
│   └── 用户资料页面
│
├── Cognito 认证集成
│   ├── AWS Amplify SDK 集成 (仅客户端库，不使用 Amplify 托管)
│   ├── 用户名密码认证
│   ├── Token 自动管理
│   └── 登出处理
│
└── API 调用
    ├── User Service API (获取用户身份信息、修改密码、注销账户)
    └── Profile Service API (获取/更新用户资料、头像管理)
```

### 3.3 技术栈

| 层级 | 技术选型 | 版本 | 说明 |
|------|---------|------|------|
| 框架 | React | 18.x | UI 框架 |
| 语言 | TypeScript | 5.x | 类型安全 |
| 构建工具 | Vite | 5.x | 快速构建 |
| 路由 | React Router | 6.x | 路由管理 |
| 状态管理 | React Hooks | - | 自定义 Hooks 管理状态 |
| HTTP 客户端 | Fetch API | - | 原生 API 请求 |
| Cognito SDK | AWS Amplify | 6.x | 认证集成 (仅 SDK，不使用 Amplify 托管) |
| UI 组件库 | Ant Design | 5.x | 企业级 UI 组件 |
| 表单 | Ant Design Form | 5.x | 表单处理与验证 |
| 国际化 | Ant Design Locale | 5.x | 中文本地化 |

### 3.4 技术选型说明

相比初始设计方案，前端技术栈在实现过程中进行了调整：

| 类别 | 初始设计 | 最终实现 | 变更原因 |
|------|---------|---------|---------|
| 样式框架 | Tailwind CSS | Ant Design | Ant Design 提供完整的企业级 UI 组件，开发效率更高，无需从零构建组件 |
| HTTP 客户端 | Axios | Fetch API | 原生 Fetch API 已足够满足需求，减少外部依赖 |
| 状态管理 | Zustand | React Hooks | 项目规模较小，React 内置 Hooks (useState, useContext) 足以应对，无需引入额外状态管理库 |
| 表单处理 | React Hook Form + Zod | Ant Design Form | 使用 Ant Design 组件库后，其内置的 Form 组件提供完整的表单验证能力，保持技术栈统一 |

> **设计决策**: 优先选择成熟的企业级组件库（Ant Design），以加快开发速度并保证 UI 一致性。对于中小型项目，避免过度引入第三方库，优先使用框架原生能力。

### 3.5 项目结构

```
frontend/
├── src/
│   ├── components/               # 组件
│   │   ├── LoadingSpinner.tsx    # 加载组件
│   │   └── MainLayout.tsx        # 主布局 (侧边栏 + 头部)
│   │
│   ├── hooks/                    # 自定义 Hooks
│   │   └── useAuth.ts            # 认证状态管理 (Amplify 集成)
│   │
│   ├── pages/                    # 页面
│   │   ├── LoginPage.tsx         # 登录页
│   │   ├── RegisterPage.tsx      # 注册页 (含验证码确认)
│   │   ├── DashboardPage.tsx     # 仪表盘
│   │   └── ProfilePage.tsx       # 个人资料
│   │
│   ├── services/                 # API 服务
│   │   ├── api.ts                # Fetch API 封装 (自动携带 JWT)
│   │   └── userService.ts        # 用户服务 API
│   │
│   ├── types/                    # 类型定义
│   │   └── index.ts              # User, UserProfile, ApiResponse
│   │
│   ├── App.tsx                   # 路由配置
│   ├── main.tsx                  # 入口 (Amplify 配置 + Ant Design)
│   ├── index.css                 # 全局样式
│   └── vite-env.d.ts             # 环境变量类型
│
├── public/
├── index.html
├── package.json
├── tsconfig.json
├── tsconfig.node.json
├── vite.config.ts
├── .env.example                  # 环境变量模板
└── .gitignore
```

### 3.6 Cognito 集成配置

```typescript
// src/main.tsx
import { Amplify } from 'aws-amplify';

// 使用环境变量配置 Cognito (部署到 S3，通过 CloudFront 分发)
Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId: import.meta.env.VITE_COGNITO_USER_POOL_ID,
      userPoolClientId: import.meta.env.VITE_COGNITO_CLIENT_ID,
      loginWith: {
        oauth: {
          domain: import.meta.env.VITE_COGNITO_DOMAIN,
          scopes: ['openid', 'email', 'profile'],
          redirectSignIn: [window.location.origin],
          redirectSignOut: [window.location.origin],
          responseType: 'code',
        },
      },
    },
  },
});
```

**环境变量 (.env.example):**

```bash
# Cognito Configuration
VITE_COGNITO_USER_POOL_ID=ap-northeast-1_xxxxxxxxx
VITE_COGNITO_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx
VITE_COGNITO_DOMAIN=auth-platform-production-xxxxxxxx.auth.ap-northeast-1.amazoncognito.com

# API Configuration
VITE_API_BASE_URL=http://localhost:8080/api
```

### 3.7 API 客户端配置

```typescript
// src/services/api.ts
import { fetchAuthSession } from 'aws-amplify/auth';
import type { ApiResponse } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

async function getAuthHeaders(): Promise<Record<string, string>> {
  try {
    const session = await fetchAuthSession();
    const token = session.tokens?.idToken?.toString();
    if (token) {
      return { Authorization: `Bearer ${token}` };
    }
  } catch {
    // 未登录状态
  }
  return {};
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  const authHeaders = await getAuthHeaders();

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders,
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Request failed' }));
    throw new Error(error.message || `HTTP error! status: ${response.status}`);
  }

  return response.json();
}

export const api = {
  get: <T>(endpoint: string) => request<T>(endpoint, { method: 'GET' }),
  post: <T>(endpoint: string, data?: unknown) =>
    request<T>(endpoint, { method: 'POST', body: data ? JSON.stringify(data) : undefined }),
  put: <T>(endpoint: string, data?: unknown) =>
    request<T>(endpoint, { method: 'PUT', body: data ? JSON.stringify(data) : undefined }),
  delete: <T>(endpoint: string) => request<T>(endpoint, { method: 'DELETE' }),
};
```

### 3.8 部署配置

```yaml
# S3 存储桶配置
S3:
  bucketName: auth-platform-frontend
  region: ap-northeast-1
  websiteConfiguration:
    indexDocument: index.html
    errorDocument: index.html
  publicAccessBlock:
    blockPublicAcls: true
    blockPublicPolicy: true
    ignorePublicAcls: true
    restrictPublicBuckets: true

# CloudFront 配置
CloudFront:
  origins:
    - id: S3Origin
      domainName: auth-platform-frontend.s3.ap-northeast-1.amazonaws.com
      s3OriginConfig:
        originAccessIdentity: origin-access-identity/cloudfront/XXXXX
  defaultCacheBehavior:
    targetOriginId: S3Origin
    viewerProtocolPolicy: redirect-to-https
    cachePolicyId: 658327ea-f89d-4fab-a63d-7e88639e58f6  # CachingOptimized
  customErrorResponses:
    - errorCode: 403
      responseCode: 200
      responsePagePath: /index.html
    - errorCode: 404
      responseCode: 200
      responsePagePath: /index.html
```

---

## 4. 用户微服务 (User Service)

### 4.1 服务概述

| 属性 | 值 |
|------|-----|
| 服务名称 | user-service |
| 部署位置 | EKS |
| 技术栈 | Spring Boot 3.2 + AWS SDK |
| 端口 | 8080 |
| API 前缀 | /api/users |

### 4.2 职责

**核心职责**：用户身份管理、注册流程、验证码管理、账户生命周期

```
User Service
├── 用户注册
│   ├── 创建 Cognito 用户 (禁用自动邮箱验证)
│   ├── 创建本地数据库用户记录
│   ├── 生成验证码并存储到 verification_codes 表
│   └── 调用 Notification Service 发送验证码邮件
│
├── 邮箱验证
│   ├── 验证用户提交的验证码
│   ├── 验证通过后删除验证码记录
│   └── 更新 Cognito 和本地数据库的 email_verified 状态
│
├── 密码重置
│   ├── 生成重置验证码并存储
│   ├── 调用 Notification Service 发送重置邮件
│   ├── 验证重置验证码
│   └── 调用 Cognito 设置新密码
│
├── 身份同步
│   └── 从 Cognito Token 自动创建/更新用户记录
│
├── 身份信息管理
│   ├── 管理 username, email, phone
│   └── 管理验证状态 (email_verified, phone_number_verified)
│
├── 账户状态管理
│   └── 管理 status (ACTIVE/INACTIVE/SUSPENDED)
│
├── 账户删除
│   ├── 发送账号注销验证码
│   ├── 验证注销验证码后删除账户
│   └── 调用 Notification Service 发送删除通知邮件
│
└── 密码修改
    ├── 调用 Cognito 修改密码
    └── 调用 Notification Service 发送密码变更通知
```

**管理的数据字段**：
- id (UUID)
- username
- email
- phone_number
- email_verified
- phone_number_verified
- status
- created_at
- updated_at

**不再负责的功能**（移至 Profile Service）：
- ~~获取用户资料~~ → Profile Service
- ~~更新用户资料~~ → Profile Service

### 4.3 API 设计

```yaml
# =====================================================
# 用户注册相关 API (无需认证)
# =====================================================

# 用户注册
POST /api/users/register
Request:
  {
    "email": "user@example.com",
    "password": "Password123!",
    "nickname": "John"
  }
Response:
  {
    "success": true,
    "code": "REGISTRATION_PENDING",
    "message": "注册成功，请查收验证码邮件",
    "data": {
      "userId": "cognito-sub-uuid",
      "email": "user@example.com"
    },
    "timestamp": "2024-01-28T10:30:00Z"
  }

# 验证邮箱
POST /api/users/verify-email
Request:
  {
    "email": "user@example.com",
    "code": "123456"
  }
Response:
  {
    "success": true,
    "code": "EMAIL_VERIFIED",
    "message": "邮箱验证成功",
    "data": null,
    "timestamp": "2024-01-28T10:30:00Z"
  }

# 重新发送验证码
POST /api/users/resend-verification
Request:
  {
    "email": "user@example.com"
  }
Response:
  {
    "success": true,
    "code": "VERIFICATION_SENT",
    "message": "验证码已发送",
    "data": null,
    "timestamp": "2024-01-28T10:30:00Z"
  }

# 忘记密码 (发送重置验证码)
POST /api/users/forgot-password
Request:
  {
    "email": "user@example.com"
  }
Response:
  {
    "success": true,
    "code": "RESET_CODE_SENT",
    "message": "密码重置验证码已发送",
    "data": null,
    "timestamp": "2024-01-28T10:30:00Z"
  }

# 重置密码
POST /api/users/reset-password
Request:
  {
    "email": "user@example.com",
    "code": "123456",
    "newPassword": "NewPassword456!"
  }
Response:
  {
    "success": true,
    "code": "PASSWORD_RESET",
    "message": "密码重置成功",
    "data": null,
    "timestamp": "2024-01-28T10:30:00Z"
  }

# =====================================================
# 已认证用户 API (需要 JWT Token)
# =====================================================

# 获取当前用户身份信息
GET /api/users/me
Headers:
  Authorization: Bearer {access_token}
Response:
  {
    "success": true,
    "code": "SUCCESS",
    "message": "操作成功",
    "data": {
      "id": "cognito-sub-uuid",
      "username": "user@example.com",
      "email": "user@example.com",
      "phoneNumber": "+1234567890",
      "emailVerified": true,
      "phoneNumberVerified": false,
      "status": "ACTIVE",
      "createdAt": "2024-01-01T00:00:00Z",
      "updatedAt": "2024-01-01T00:00:00Z"
    },
    "timestamp": "2024-01-28T10:30:00Z"
  }

# 用户注销 (当前用户)
DELETE /api/users/me
Headers:
  Authorization: Bearer {access_token}
Response:
  {
    "success": true,
    "code": "ACCOUNT_DELETED",
    "message": "账户已成功删除",
    "data": null,
    "timestamp": "2024-01-28T10:30:00Z"
  }

# 修改密码
POST /api/users/me/change-password
Headers:
  Authorization: Bearer {access_token}
Request:
  {
    "oldPassword": "OldPassword123!",
    "newPassword": "NewPassword456!"
  }
Response:
  {
    "success": true,
    "code": "PASSWORD_CHANGED",
    "message": "密码修改成功",
    "data": null,
    "timestamp": "2024-01-28T10:30:00Z"
  }

# 发送账号注销验证码
POST /api/users/delete-account/send-code
Headers:
  Authorization: Bearer {access_token}
Request:
  {
    "email": "user@example.com"
  }
Response:
  {
    "success": true,
    "code": "DELETE_CODE_SENT",
    "message": "验证码已发送到您的邮箱",
    "data": null,
    "timestamp": "2024-01-28T10:30:00Z"
  }

# 确认注销账号
POST /api/users/delete-account/confirm
Headers:
  Authorization: Bearer {access_token}
Request:
  {
    "email": "user@example.com",
    "code": "123456"
  }
Response:
  {
    "success": true,
    "code": "ACCOUNT_DELETED",
    "message": "账户已成功删除",
    "data": null,
    "timestamp": "2024-01-28T10:30:00Z"
  }
```

### 4.4 统一响应格式

```json
{
  "success": true,
  "code": "SUCCESS",
  "message": "操作成功",
  "data": { ... },
  "timestamp": "2024-01-28T10:30:00Z"
}
```

**错误响应**：
```json
{
  "success": false,
  "code": "USER_NOT_FOUND",
  "message": "用户不存在",
  "data": null,
  "timestamp": "2024-01-28T10:30:00Z"
}
```

**错误码定义**：

| 错误码 | HTTP 状态 | 说明 |
|--------|----------|------|
| SUCCESS | 200 | 操作成功 |
| REGISTRATION_PENDING | 200 | 注册成功，待邮箱验证 |
| EMAIL_VERIFIED | 200 | 邮箱验证成功 |
| VERIFICATION_SENT | 200 | 验证码已发送 |
| RESET_CODE_SENT | 200 | 密码重置验证码已发送 |
| PASSWORD_RESET | 200 | 密码重置成功 |
| PASSWORD_CHANGED | 200 | 密码已修改 |
| DELETE_CODE_SENT | 200 | 账号注销验证码已发送 |
| ACCOUNT_DELETED | 200 | 账户已删除 |
| USER_NOT_FOUND | 404 | 用户不存在 |
| EMAIL_ALREADY_EXISTS | 409 | 邮箱已被注册 |
| INVALID_VERIFICATION_CODE | 400 | 验证码无效或已过期 |
| INVALID_PASSWORD | 400 | 密码格式不正确 |
| PASSWORD_MISMATCH | 400 | 原密码错误 |
| EMAIL_NOT_VERIFIED | 400 | 邮箱未验证 |
| UNAUTHORIZED | 401 | 未授权 |
| FORBIDDEN | 403 | 禁止访问 |
| INTERNAL_ERROR | 500 | 服务器内部错误 |

### 4.5 项目结构

```
user-service/
├── src/main/java/com/authplatform/userservice/
│   ├── UserServiceApplication.java
│   │
│   ├── config/
│   │   ├── SecurityConfig.java         # OAuth2 JWT 安全配置
│   │   └── CognitoConfig.java          # Cognito 客户端配置
│   │
│   ├── controller/
│   │   ├── UserController.java         # 已认证用户 API (/api/users/me)
│   │   └── AuthController.java         # 注册/验证 API (/api/users/register等)
│   │
│   ├── service/
│   │   ├── AuthService.java            # 注册/验证业务逻辑
│   │   ├── UserService.java            # 用户业务逻辑
│   │   ├── VerificationCodeService.java # 验证码管理
│   │   └── CognitoService.java         # Cognito 操作封装
│   │
│   ├── client/
│   │   └── NotificationServiceClient.java # Notification Service 调用
│   │
│   ├── repository/
│   │   ├── UserRepository.java         # 用户数据库访问
│   │   └── VerificationCodeRepository.java # 验证码数据库访问
│   │
│   ├── entity/
│   │   ├── User.java                   # 用户实体
│   │   └── VerificationCode.java       # 验证码实体
│   │
│   ├── dto/
│   │   ├── UserDto.java                # 用户信息响应
│   │   ├── RegisterRequest.java        # 注册请求
│   │   ├── VerifyEmailRequest.java     # 邮箱验证请求
│   │   ├── ForgotPasswordRequest.java  # 忘记密码请求
│   │   ├── ResetPasswordRequest.java   # 重置密码请求
│   │   ├── ChangePasswordRequest.java  # 修改密码请求
│   │   ├── DeleteAccountSendCodeRequest.java  # 发送注销验证码请求
│   │   ├── DeleteAccountConfirmRequest.java   # 确认注销账号请求
│   │   └── ApiResponse.java            # 统一响应格式
│   │
│   ├── exception/
│   │   ├── ResourceNotFoundException.java
│   │   ├── EmailAlreadyExistsException.java
│   │   ├── InvalidVerificationCodeException.java
│   │   └── GlobalExceptionHandler.java
│   │
│   ├── metrics/
│   │   └── BusinessMetrics.java        # Prometheus 业务指标
│   │
│   └── logging/
│       ├── LoggingFilter.java          # HTTP 日志过滤器
│       └── LogEvent.java               # 结构化日志事件
│
├── src/main/resources/
│   ├── application.yml
│   ├── application-production.yml
│   └── db/migration/                   # Flyway 数据库迁移
│       ├── V1__create_users_table.sql
│       └── V2__create_verification_codes_table.sql
│
├── build.gradle
└── Dockerfile
```

### 4.6 核心代码示例

```java
// AuthController.java - 注册/验证相关 API (无需认证)
@RestController
@RequestMapping("/users")
@RequiredArgsConstructor
public class AuthController {

    private final AuthService authService;

    /**
     * 用户注册
     */
    @PostMapping("/register")
    public ResponseEntity<ApiResponse<Map<String, String>>> register(
            @Valid @RequestBody RegisterRequest request) {
        Map<String, String> result = authService.register(
                request.getEmail(),
                request.getPassword(),
                request.getNickname()
        );
        return ResponseEntity.ok(ApiResponse.success(
                "REGISTRATION_PENDING",
                "注册成功，请查收验证码邮件",
                result
        ));
    }

    /**
     * 验证邮箱
     */
    @PostMapping("/verify-email")
    public ResponseEntity<ApiResponse<Void>> verifyEmail(
            @Valid @RequestBody VerifyEmailRequest request) {
        authService.verifyEmail(request.getEmail(), request.getCode());
        return ResponseEntity.ok(ApiResponse.success("EMAIL_VERIFIED", "邮箱验证成功", null));
    }

    /**
     * 重发验证码
     */
    @PostMapping("/resend-verification")
    public ResponseEntity<ApiResponse<Void>> resendVerification(
            @RequestBody Map<String, String> request) {
        authService.resendVerificationCode(request.get("email"));
        return ResponseEntity.ok(ApiResponse.success("VERIFICATION_SENT", "验证码已发送", null));
    }

    /**
     * 忘记密码
     */
    @PostMapping("/forgot-password")
    public ResponseEntity<ApiResponse<Void>> forgotPassword(
            @Valid @RequestBody ForgotPasswordRequest request) {
        authService.forgotPassword(request.getEmail());
        return ResponseEntity.ok(ApiResponse.success("RESET_CODE_SENT", "密码重置验证码已发送", null));
    }

    /**
     * 重置密码
     */
    @PostMapping("/reset-password")
    public ResponseEntity<ApiResponse<Void>> resetPassword(
            @Valid @RequestBody ResetPasswordRequest request) {
        authService.resetPassword(
                request.getEmail(),
                request.getCode(),
                request.getNewPassword()
        );
        return ResponseEntity.ok(ApiResponse.success("PASSWORD_RESET", "密码重置成功", null));
    }
}
```

```java
// UserController.java - 已认证用户 API
@RestController
@RequestMapping("/users")
@RequiredArgsConstructor
public class UserController {

    private final UserService userService;

    /**
     * 获取当前用户身份信息
     */
    @GetMapping("/me")
    public ApiResponse<UserDto> getCurrentUser(@AuthenticationPrincipal Jwt jwt) {
        String userId = jwt.getSubject();
        String username = jwt.getClaimAsString("cognito:username");
        String email = jwt.getClaimAsString("email");
        Boolean emailVerified = jwt.getClaimAsBoolean("email_verified");
        UserDto user = userService.createOrUpdateUser(userId, username, email, emailVerified, null);
        return ApiResponse.success(user);
    }

    /**
     * 修改密码
     */
    @PostMapping("/me/change-password")
    public ResponseEntity<ApiResponse<Void>> changePassword(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody ChangePasswordRequest request) {
        String userId = jwt.getSubject();
        String accessToken = jwt.getTokenValue();
        userService.changePassword(userId, accessToken, request.getOldPassword(), request.getNewPassword());
        return ResponseEntity.ok(ApiResponse.success("PASSWORD_CHANGED", "密码修改成功", null));
    }

    /**
     * 删除当前用户账户 (直接删除)
     */
    @DeleteMapping("/me")
    public ResponseEntity<ApiResponse<Void>> deleteCurrentUser(@AuthenticationPrincipal Jwt jwt) {
        String userId = jwt.getSubject();
        userService.deleteUser(userId, "USER_REQUEST");
        return ResponseEntity.ok(ApiResponse.success("ACCOUNT_DELETED", "账户已成功删除", null));
    }

    /**
     * 发送账号注销验证码
     */
    @PostMapping("/delete-account/send-code")
    public ResponseEntity<ApiResponse<Void>> sendDeleteAccountCode(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody DeleteAccountSendCodeRequest request) {
        String userId = jwt.getSubject();
        userService.sendDeleteAccountCode(userId, request.getEmail());
        return ResponseEntity.ok(ApiResponse.success("DELETE_CODE_SENT", "验证码已发送到您的邮箱", null));
    }

    /**
     * 确认注销账号
     */
    @PostMapping("/delete-account/confirm")
    public ResponseEntity<ApiResponse<Void>> confirmDeleteAccount(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody DeleteAccountConfirmRequest request) {
        String userId = jwt.getSubject();
        userService.confirmDeleteAccount(userId, request.getEmail(), request.getCode());
        return ResponseEntity.ok(ApiResponse.success("ACCOUNT_DELETED", "账户已成功删除", null));
    }
}
```

```java
// UserService.java
@Service
@RequiredArgsConstructor
@Slf4j
public class UserService {

    private final UserRepository userRepository;
    private final VerificationCodeService verificationCodeService;
    private final CognitoService cognitoService;
    private final NotificationServiceClient notificationClient;
    private final BusinessMetrics metrics;

    /**
     * 用户注册
     */
    @Transactional
    public String register(String email, String password, String nickname) {
        // 1. 检查邮箱是否已存在
        if (userRepository.existsByEmail(email)) {
            throw new EmailAlreadyExistsException("邮箱已被注册");
        }

        // 2. 在 Cognito 创建用户 (禁用自动邮箱验证)
        String userId = cognitoService.createUser(email, password);

        // 3. 创建本地数据库记录
        User user = User.builder()
            .id(userId)
            .username(email)
            .email(email)
            .nickname(nickname)
            .emailVerified(false)
            .status(UserStatus.PENDING_VERIFICATION)
            .build();
        userRepository.save(user);

        // 4. 生成验证码并发送邮件
        String code = verificationCodeService.generateCode(email, VerificationType.EMAIL_VERIFICATION);
        notificationClient.sendVerificationCode(email, code, "EMAIL_VERIFICATION", 15);

        metrics.incrementUserRegistered();
        log.info("User registered: email={}, userId={}", email, userId);
        return userId;
    }

    /**
     * 验证邮箱
     */
    @Transactional
    public void verifyEmail(String email, String code) {
        // 1. 验证验证码
        verificationCodeService.verifyCode(email, code, VerificationType.EMAIL_VERIFICATION);

        // 2. 更新本地数据库
        User user = userRepository.findByEmail(email)
            .orElseThrow(() -> new ResourceNotFoundException("用户不存在"));
        user.setEmailVerified(true);
        user.setStatus(UserStatus.ACTIVE);
        userRepository.save(user);

        // 3. 更新 Cognito 邮箱验证状态
        cognitoService.verifyUserEmail(user.getId());

        // 4. 删除验证码记录
        verificationCodeService.deleteCode(email, VerificationType.EMAIL_VERIFICATION);

        // 5. 发送欢迎邮件
        notificationClient.sendWelcomeEmail(email, user.getNickname());

        metrics.incrementEmailVerified();
        log.info("Email verified: email={}", email);
    }

    /**
     * 忘记密码
     */
    public void forgotPassword(String email) {
        // 验证用户存在
        userRepository.findByEmail(email)
            .orElseThrow(() -> new ResourceNotFoundException("用户不存在"));

        // 生成重置验证码并发送
        String code = verificationCodeService.generateCode(email, VerificationType.PASSWORD_RESET);
        notificationClient.sendVerificationCode(email, code, "PASSWORD_RESET", 15);

        log.info("Password reset code sent: email={}", email);
    }

    /**
     * 重置密码
     */
    @Transactional
    public void resetPassword(String email, String code, String newPassword) {
        // 1. 验证验证码
        verificationCodeService.verifyCode(email, code, VerificationType.PASSWORD_RESET);

        // 2. 获取用户
        User user = userRepository.findByEmail(email)
            .orElseThrow(() -> new ResourceNotFoundException("用户不存在"));

        // 3. 在 Cognito 设置新密码
        cognitoService.adminSetUserPassword(user.getId(), newPassword);

        // 4. 删除验证码记录
        verificationCodeService.deleteCode(email, VerificationType.PASSWORD_RESET);

        metrics.incrementPasswordReset();
        log.info("Password reset: email={}", email);
    }

    /**
     * 修改密码 (已登录用户)
     */
    public void changePassword(String userId, String accessToken, String oldPassword, String newPassword) {
        User user = userRepository.findById(userId)
            .orElseThrow(() -> new ResourceNotFoundException("用户不存在"));

        cognitoService.changePassword(accessToken, oldPassword, newPassword);

        // 发送密码变更通知
        notificationClient.sendPasswordChangedEmail(user.getEmail(), user.getNickname());

        log.info("Password changed: userId={}", userId);
    }

    /**
     * 删除用户
     */
    @Transactional
    public void deleteUser(String userId) {
        User user = userRepository.findById(userId)
            .orElseThrow(() -> new ResourceNotFoundException("用户不存在"));

        // 删除 Cognito 用户
        cognitoService.deleteUser(userId);

        // 删除本地记录
        userRepository.deleteById(userId);

        // 发送账号删除通知
        notificationClient.sendAccountDeletedEmail(user.getEmail(), user.getNickname());

        metrics.incrementUserDeleted();
        log.info("User deleted: userId={}", userId);
    }
}
```

```java
// VerificationCodeService.java
@Service
@RequiredArgsConstructor
@Slf4j
public class VerificationCodeService {

    private final VerificationCodeRepository repository;

    private static final int CODE_LENGTH = 6;
    private static final int CODE_EXPIRY_MINUTES = 15;

    /**
     * 生成验证码
     */
    @Transactional
    public String generateCode(String email, VerificationType type) {
        // 删除旧的验证码
        repository.deleteByEmailAndType(email, type);

        // 生成新验证码
        String code = generateRandomCode();
        VerificationCode entity = VerificationCode.builder()
            .email(email)
            .code(code)
            .type(type)
            .expiresAt(LocalDateTime.now().plusMinutes(CODE_EXPIRY_MINUTES))
            .build();

        repository.save(entity);
        log.info("Verification code generated: email={}, type={}", email, type);
        return code;
    }

    /**
     * 验证验证码
     */
    public void verifyCode(String email, String code, VerificationType type) {
        VerificationCode entity = repository.findByEmailAndType(email, type)
            .orElseThrow(() -> new InvalidVerificationCodeException("验证码无效"));

        if (entity.getExpiresAt().isBefore(LocalDateTime.now())) {
            throw new InvalidVerificationCodeException("验证码已过期");
        }

        if (!entity.getCode().equals(code)) {
            throw new InvalidVerificationCodeException("验证码错误");
        }
    }

    /**
     * 删除验证码 (验证成功后调用)
     */
    @Transactional
    public void deleteCode(String email, VerificationType type) {
        repository.deleteByEmailAndType(email, type);
        log.info("Verification code deleted: email={}, type={}", email, type);
    }

    private String generateRandomCode() {
        SecureRandom random = new SecureRandom();
        StringBuilder sb = new StringBuilder(CODE_LENGTH);
        for (int i = 0; i < CODE_LENGTH; i++) {
            sb.append(random.nextInt(10));
        }
        return sb.toString();
    }
}
```

---

## 5. Profile 微服务 (Profile Service)

### 5.1 服务概述

| 属性 | 值 |
|------|-----|
| 服务名称 | profile-service |
| 部署位置 | EKS |
| 技术栈 | Spring Boot 3.2 + Spring Data JPA |
| 端口 | 8080 |
| API 前缀 | /api/profiles |

### 5.2 职责

**核心职责**：用户个人资料管理、头像文件处理

```
Profile Service
├── 资料管理
│   ├── 获取当前用户资料
│   ├── 更新用户资料 (nickname, gender, birthday, address)
│   └── 调用 Notification Service 发送资料修改通知邮件
│
├── 头像管理
│   ├── 上传头像文件 (验证类型、大小)
│   ├── 存储到数据库 (avatar_data BYTEA 字段)
│   ├── 获取头像图片 (公开 API，无需认证)
│   └── 删除头像
│
└── 偏好设置（预留）
    └── 用户偏好 JSON 存储
```

**管理的数据字段**：
- nickname
- avatar (头像 API URL)
- avatar_data (头像二进制数据)
- avatar_content_type (头像 MIME 类型)
- gender
- birthday
- address
- preferences (JSONB)
- updated_at

**只读字段**（从 users 表读取，不可修改）：
- id
- email
- username

### 5.3 API 设计

```yaml
# 获取当前用户资料
GET /api/profiles/me
Headers:
  Authorization: Bearer {access_token}
Response:
  {
    "success": true,
    "code": "SUCCESS",
    "message": "操作成功",
    "data": {
      "userId": "cognito-sub-uuid",
      "email": "user@example.com",
      "username": "user@example.com",
      "nickname": "John",
      "avatar": "https://cdn.xxx.com/avatars/xxx.jpg",
      "gender": "MALE",
      "birthday": "1990-01-15",
      "address": "Tokyo, Japan",
      "createdAt": "2024-01-01T00:00:00Z",
      "updatedAt": "2024-01-01T00:00:00Z"
    },
    "timestamp": "2024-01-28T10:30:00Z"
  }

# 更新用户资料
PUT /api/profiles/me
Headers:
  Authorization: Bearer {access_token}
Request:
  {
    "nickname": "Johnny",
    "gender": "MALE",
    "birthday": "1990-01-15",
    "address": "Osaka, Japan"
  }
Response:
  {
    "success": true,
    "code": "PROFILE_UPDATED",
    "message": "资料更新成功",
    "data": {
      "userId": "cognito-sub-uuid",
      "nickname": "Johnny",
      "avatar": "https://cdn.xxx.com/avatars/xxx.jpg",
      "gender": "MALE",
      "birthday": "1990-01-15",
      "address": "Osaka, Japan",
      "updatedAt": "2024-01-28T10:30:00Z"
    },
    "timestamp": "2024-01-28T10:30:00Z"
  }

# 上传头像
POST /api/profiles/me/avatar
Headers:
  Authorization: Bearer {access_token}
  Content-Type: multipart/form-data
Request:
  file: (binary, max 5MB, image/jpeg|image/png|image/gif|image/webp)
Response:
  {
    "success": true,
    "code": "AVATAR_UPLOADED",
    "message": "头像上传成功",
    "data": {
      "success": true,
      "avatarUrl": "/api/profiles/{userId}/avatar/image"
    },
    "timestamp": "2024-01-28T10:30:00Z"
  }

# 删除头像
DELETE /api/profiles/me/avatar
Headers:
  Authorization: Bearer {access_token}
Response:
  {
    "success": true,
    "code": "AVATAR_DELETED",
    "message": "头像删除成功",
    "data": null,
    "timestamp": "2024-01-28T10:30:00Z"
  }

# 获取头像图片 (公开 API，无需认证)
GET /api/profiles/{userId}/avatar/image
Response:
  Content-Type: image/jpeg|image/png|image/gif|image/webp
  Cache-Control: max-age=3600, public
  Body: (binary image data)

# 头像不存在时返回 404
```

### 5.4 统一响应格式

与 User Service 保持一致：

```json
{
  "success": true,
  "code": "SUCCESS",
  "message": "操作成功",
  "data": { ... },
  "timestamp": "2024-01-28T10:30:00Z"
}
```

**错误码定义**：

| 错误码 | HTTP 状态 | 说明 |
|--------|----------|------|
| SUCCESS | 200 | 操作成功 |
| PROFILE_NOT_FOUND | 404 | 用户资料不存在 |
| PROFILE_UPDATED | 200 | 资料更新成功 |
| AVATAR_UPLOADED | 200 | 头像上传成功 |
| AVATAR_DELETED | 200 | 头像删除成功 |
| INVALID_FILE_TYPE | 400 | 文件类型不支持 |
| FILE_TOO_LARGE | 413 | 文件大小超过限制 |
| UPLOAD_FAILED | 500 | 文件上传失败 |
| UNAUTHORIZED | 401 | 未授权 |
| INTERNAL_ERROR | 500 | 服务器内部错误 |

### 5.5 数据库设计

Profile Service 与 User Service **共享同一张 users 表**，通过字段权限划分职责：

```sql
-- users 表（共享，由 user-service 的 Flyway 管理 schema）
CREATE TABLE users (
    -- Identity 字段 (user-service 管理)
    id                      VARCHAR(36) PRIMARY KEY,  -- Cognito sub
    username                VARCHAR(255) NOT NULL UNIQUE,
    email                   VARCHAR(255) NOT NULL UNIQUE,
    phone_number            VARCHAR(20),
    email_verified          BOOLEAN DEFAULT FALSE,
    phone_number_verified   BOOLEAN DEFAULT FALSE,
    status                  VARCHAR(20) DEFAULT 'ACTIVE',  -- PENDING_VERIFICATION/ACTIVE/INACTIVE/SUSPENDED

    -- Profile 字段 (profile-service 管理)
    nickname                VARCHAR(64),
    avatar                  VARCHAR(512),             -- 头像 API URL
    avatar_data             BYTEA,                    -- 头像二进制数据
    avatar_content_type     VARCHAR(100),             -- 头像 MIME 类型
    gender                  VARCHAR(10),              -- MALE/FEMALE/OTHER
    birthday                DATE,
    address                 VARCHAR(256),
    preferences             JSONB,                    -- 用户偏好设置

    -- 时间戳（共享）
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_users_email (email),
    INDEX idx_users_username (username)
);

-- verification_codes 表（验证码管理，由 user-service 管理）
CREATE TABLE verification_codes (
    id              BIGSERIAL PRIMARY KEY,
    email           VARCHAR(255) NOT NULL,
    code            VARCHAR(6) NOT NULL,
    type            VARCHAR(20) NOT NULL,        -- EMAIL_VERIFICATION / PASSWORD_RESET / ACCOUNT_DELETION
    expires_at      TIMESTAMP NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_verification_codes_email_type (email, type),
    INDEX idx_verification_codes_expires_at (expires_at)
);

-- 注意: 验证码验证成功后应立即删除记录，而不是标记为已使用
-- 定期清理过期验证码：DELETE FROM verification_codes WHERE expires_at < NOW()
```

**重要说明**：
- Schema 由 user-service 的 Flyway 迁移管理
- profile-service 的 Flyway 设置为 `enabled: false`
- profile-service 的 Entity 中 Identity 字段标记为 `updatable=false, insertable=false`

### 5.6 项目结构

```
profile-service/
├── src/main/java/com/authplatform/profileservice/
│   ├── ProfileServiceApplication.java
│   │
│   ├── config/
│   │   └── SecurityConfig.java         # OAuth2 JWT 安全配置
│   │
│   ├── controller/
│   │   └── ProfileController.java      # 用户资料 API (/api/profiles)
│   │
│   ├── client/
│   │   └── NotificationServiceClient.java # Notification Service 调用
│   │
│   ├── service/
│   │   ├── ProfileService.java         # 资料管理业务逻辑
│   │   └── AvatarService.java          # 头像处理/验证
│   │
│   ├── repository/
│   │   └── UserProfileRepository.java
│   │
│   ├── entity/
│   │   └── UserProfile.java            # 用户资料实体
│   │
│   ├── dto/
│   │   ├── ProfileResponse.java        # 资料响应
│   │   ├── UpdateProfileRequest.java   # 更新资料请求
│   │   ├── AvatarResponse.java         # 头像上传响应
│   │   └── ApiResponse.java            # 统一响应格式
│   │
│   ├── exception/
│   │   ├── ResourceNotFoundException.java
│   │   ├── AvatarUploadException.java
│   │   └── GlobalExceptionHandler.java
│   │
│   ├── metrics/
│   │   └── BusinessMetrics.java        # Prometheus 业务指标
│   │
│   └── logging/
│       ├── LoggingFilter.java
│       └── LogEvent.java
│
├── src/main/resources/
│   ├── application.yml
│   └── application-production.yml
│
├── build.gradle
└── Dockerfile
```

### 5.7 核心代码示例

```java
// ProfileController.java
@RestController
@RequestMapping("/profiles")
@RequiredArgsConstructor
public class ProfileController {

    private final ProfileService profileService;

    /**
     * 获取当前用户资料
     */
    @GetMapping("/me")
    public ApiResponse<ProfileResponse> getCurrentProfile(@AuthenticationPrincipal Jwt jwt) {
        String userId = jwt.getSubject();
        ProfileResponse profile = profileService.getProfile(userId);
        return ApiResponse.success(profile);
    }

    /**
     * 更新用户资料
     */
    @PutMapping("/me")
    public ApiResponse<ProfileResponse> updateProfile(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody UpdateProfileRequest request) {
        String userId = jwt.getSubject();
        ProfileResponse profile = profileService.updateProfile(userId, request);
        return ApiResponse.success("PROFILE_UPDATED", "资料更新成功", profile);
    }

    /**
     * 上传头像 (存储到数据库)
     */
    @PostMapping(value = "/me/avatar", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ApiResponse<AvatarResponse> uploadAvatar(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam("file") MultipartFile file) {
        String userId = jwt.getSubject();
        String avatarUrl = profileService.uploadAvatar(userId, file);
        AvatarResponse response = AvatarResponse.builder()
                .success(true)
                .avatarUrl(avatarUrl)
                .build();
        return ApiResponse.success("AVATAR_UPLOADED", "头像上传成功", response);
    }

    /**
     * 删除头像
     */
    @DeleteMapping("/me/avatar")
    public ApiResponse<Void> deleteAvatar(@AuthenticationPrincipal Jwt jwt) {
        String userId = jwt.getSubject();
        profileService.deleteAvatar(userId);
        return ApiResponse.success("AVATAR_DELETED", "头像删除成功", null);
    }

    /**
     * 获取头像图片 (公开 API，无需认证)
     * 配置为 SecurityConfig 中的 permitAll
     */
    @GetMapping(value = "/{userId}/avatar/image",
            produces = {MediaType.IMAGE_JPEG_VALUE, MediaType.IMAGE_PNG_VALUE,
                       MediaType.IMAGE_GIF_VALUE, "image/webp"})
    public ResponseEntity<byte[]> getAvatarImage(@PathVariable String userId) {
        ProfileService.AvatarData avatarData = profileService.getAvatarData(userId);

        if (avatarData == null || avatarData.data() == null) {
            return ResponseEntity.notFound().build();
        }

        MediaType mediaType = MediaType.parseMediaType(
            avatarData.contentType() != null ? avatarData.contentType() : MediaType.IMAGE_JPEG_VALUE
        );

        return ResponseEntity.ok()
                .contentType(mediaType)
                .cacheControl(CacheControl.maxAge(1, TimeUnit.HOURS).cachePublic())
                .body(avatarData.data());
    }
}
```

```java
// ProfileService.java
@Service
@RequiredArgsConstructor
@Slf4j
public class ProfileService {

    private final UserProfileRepository profileRepository;
    private final AvatarService avatarService;
    private final BusinessMetrics businessMetrics;
    private final NotificationServiceClient notificationClient;

    public ProfileResponse getProfile(String userId) {
        UserProfile profile = profileRepository.findById(userId)
            .orElseThrow(() -> new ResourceNotFoundException("User not found: " + userId));

        businessMetrics.incrementProfileFetched();
        return mapToResponse(profile);
    }

    @Transactional
    public ProfileResponse updateProfile(String userId, UpdateProfileRequest request) {
        UserProfile profile = profileRepository.findById(userId)
            .orElseThrow(() -> new ResourceNotFoundException("User not found: " + userId));

        List<String> updatedFields = new ArrayList<>();

        if (request.getNickname() != null) {
            profile.setNickname(request.getNickname());
            updatedFields.add("nickname");
        }
        if (request.getGender() != null) {
            profile.setGender(UserProfile.Gender.valueOf(request.getGender().toUpperCase()));
            updatedFields.add("gender");
        }
        if (request.getBirthday() != null) {
            profile.setBirthday(request.getBirthday());
            updatedFields.add("birthday");
        }
        if (request.getAddress() != null) {
            profile.setAddress(request.getAddress());
            updatedFields.add("address");
        }

        profile = profileRepository.save(profile);

        if (!updatedFields.isEmpty()) {
            businessMetrics.incrementProfileUpdated(updatedFields.toArray(new String[0]));
            // 发送资料更新通知邮件
            notificationClient.sendProfileUpdatedEmail(profile.getEmail(), profile.getNickname(), updatedFields);
        }

        log.info("Profile updated: userId={}, fields={}", userId, updatedFields);
        return mapToResponse(profile);
    }

    /**
     * 上传头像 - 存储到数据库
     */
    @Transactional
    public String uploadAvatar(String userId, MultipartFile file) {
        UserProfile profile = profileRepository.findById(userId)
            .orElseThrow(() -> new ResourceNotFoundException("User not found: " + userId));

        // 处理并验证头像
        byte[] avatarData = avatarService.processAvatar(file);
        String contentType = file.getContentType();

        // 存储到数据库
        profile.setAvatarData(avatarData);
        profile.setAvatarContentType(contentType);
        String avatarUrl = "/api/profiles/" + userId + "/avatar/image";
        profile.setAvatar(avatarUrl);
        profileRepository.save(profile);

        log.info("Avatar uploaded to database: userId={}, size={}", userId, avatarData.length);
        return avatarUrl;
    }

    /**
     * 获取头像数据（用于服务端返回）
     */
    @Transactional(readOnly = true)
    public AvatarData getAvatarData(String userId) {
        UserProfile profile = profileRepository.findById(userId)
            .orElseThrow(() -> new ResourceNotFoundException("User not found: " + userId));

        if (profile.getAvatarData() == null) {
            return null;
        }
        return new AvatarData(profile.getAvatarData(), profile.getAvatarContentType());
    }

    @Transactional
    public void deleteAvatar(String userId) {
        UserProfile profile = profileRepository.findById(userId)
            .orElseThrow(() -> new ResourceNotFoundException("User not found: " + userId));

        if (profile.getAvatarData() != null || profile.getAvatar() != null) {
            profile.setAvatarData(null);
            profile.setAvatarContentType(null);
            profile.setAvatar(null);
            profileRepository.save(profile);
            log.info("Avatar deleted: userId={}", userId);
        }
    }

    /**
     * 头像数据记录类
     */
    public record AvatarData(byte[] data, String contentType) {}
}
```

```java
// UserProfile.java - Entity (映射到 users 表)
@Entity
@Table(name = "users")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class UserProfile {

    @Id
    @Column(length = 36)
    private String id;

    // Identity 字段 - 只读 (由 user-service 管理)
    @Column(nullable = false, unique = true, updatable = false, insertable = false)
    private String email;

    @Column(nullable = false, unique = true, updatable = false, insertable = false)
    private String username;

    // Profile 字段 - 可读写 (由 profile-service 管理)
    @Column(length = 64)
    private String nickname;

    @Column(length = 512)
    private String avatar;                    // 头像 API URL

    @Basic(fetch = FetchType.LAZY)
    @Column(name = "avatar_data")
    private byte[] avatarData;                // 头像二进制数据

    @Column(name = "avatar_content_type", length = 100)
    private String avatarContentType;         // 头像 MIME 类型

    @Enumerated(EnumType.STRING)
    @Column(length = 10)
    private Gender gender;

    private LocalDate birthday;

    @Column(length = 256)
    private String address;

    @Column(columnDefinition = "jsonb")
    private String preferences;

    // 时间戳
    @CreationTimestamp
    @Column(name = "created_at", updatable = false)
    private LocalDateTime createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    public enum Gender {
        MALE,
        FEMALE,
        OTHER
    }
}
```

---

## 6. 通知微服务 (Notification Service)

### 6.1 服务概述

| 属性 | 值 |
|------|-----|
| 服务名称 | notification-service |
| 部署位置 | EKS |
| 技术栈 | Spring Boot 3.2 + AWS SES SDK |
| 端口 | 8080 |
| API 前缀 | /api/v1/notifications |

### 6.2 职责

```
Notification Service (统一邮件通知服务)
├── 验证码邮件
│   ├── 注册邮箱验证码
│   ├── 密码重置验证码
│   └── 账号注销验证码
│
├── 欢迎邮件
│   └── 用户完成注册验证后发送
│
├── 密码变更通知
│   └── 用户修改密码后发送确认邮件
│
├── 资料修改通知
│   └── 用户修改个人资料时发送确认邮件
│
└── 账号删除通知
    └── 用户删除账户时发送确认邮件

注: 所有邮件通知均通过本服务发送，Cognito 邮箱自动验证已禁用
```

### 6.3 API 设计

```yaml
# =====================================================
# 所有 API 均为内部调用，需要 X-Internal-Api-Key 认证
# =====================================================

# 发送验证码邮件 (注册/密码重置/账号注销)
POST /api/v1/notifications/verification-code
Headers:
  X-Internal-Api-Key: {internal_api_key}
Request:
  {
    "to": "user@example.com",
    "code": "123456",
    "type": "EMAIL_VERIFICATION",  # 或 "PASSWORD_RESET" 或 "ACCOUNT_DELETION"
    "expiresInMinutes": 15
  }
Response:
  {
    "success": true,
    "messageId": "ses-message-id"
  }

# 发送欢迎邮件 (注册验证完成后)
POST /api/v1/notifications/welcome
Headers:
  X-Internal-Api-Key: {internal_api_key}
Request:
  {
    "to": "user@example.com",
    "nickname": "John"
  }
Response:
  {
    "success": true,
    "messageId": "ses-message-id"
  }

# 发送密码变更通知邮件
POST /api/v1/notifications/password-changed
Headers:
  X-Internal-Api-Key: {internal_api_key}
Request:
  {
    "to": "user@example.com",
    "nickname": "John"
  }
Response:
  {
    "success": true,
    "messageId": "ses-message-id"
  }

# 发送资料修改通知邮件
POST /api/v1/notifications/profile-updated
Headers:
  X-Internal-Api-Key: {internal_api_key}
Request:
  {
    "to": "user@example.com",
    "nickname": "John"
  }
Response:
  {
    "success": true,
    "messageId": "ses-message-id"
  }

# 发送账号删除通知邮件
POST /api/v1/notifications/account-deleted
Headers:
  X-Internal-Api-Key: {internal_api_key}
Request:
  {
    "to": "user@example.com",
    "nickname": "John"
  }
Response:
  {
    "success": true,
    "messageId": "ses-message-id"
  }
```

### 6.4 项目结构

```
notification-service/
├── src/main/java/com/authplatform/notificationservice/
│   ├── NotificationServiceApplication.java
│   │
│   ├── config/
│   │   ├── SecurityConfig.java
│   │   └── SesConfig.java
│   │
│   ├── controller/
│   │   └── NotificationController.java
│   │
│   ├── service/
│   │   └── EmailService.java
│   │
│   ├── dto/
│   │   ├── VerificationCodeRequest.java    # 验证码邮件请求
│   │   ├── WelcomeEmailRequest.java        # 欢迎邮件请求
│   │   ├── PasswordChangedRequest.java     # 密码变更通知请求
│   │   ├── ProfileUpdatedRequest.java      # 资料修改通知请求
│   │   ├── AccountDeletedRequest.java      # 账号删除通知请求
│   │   └── EmailResponse.java              # 统一响应
│   │
│   └── exception/
│       └── GlobalExceptionHandler.java
│
├── src/main/resources/
│   └── application.yml
│
├── build.gradle
└── Dockerfile
```

### 6.5 核心代码示例

```java
// NotificationController.java
@RestController
@RequestMapping("/api/v1/notifications")
@RequiredArgsConstructor
public class NotificationController {

    private final EmailService emailService;

    /**
     * 发送验证码邮件 (注册邮箱验证 / 密码重置)
     */
    @PostMapping("/verification-code")
    public ResponseEntity<EmailResponse> sendVerificationCode(
            @RequestBody VerificationCodeRequest request) {
        return ResponseEntity.ok(emailService.sendVerificationCodeEmail(
            request.getTo(),
            request.getCode(),
            request.getType(),
            request.getExpiresInMinutes()
        ));
    }

    /**
     * 发送欢迎邮件
     */
    @PostMapping("/welcome")
    public ResponseEntity<EmailResponse> sendWelcomeEmail(
            @RequestBody WelcomeEmailRequest request) {
        return ResponseEntity.ok(emailService.sendWelcomeEmail(
            request.getTo(),
            request.getNickname()
        ));
    }

    /**
     * 发送密码变更通知
     */
    @PostMapping("/password-changed")
    public ResponseEntity<EmailResponse> sendPasswordChangedEmail(
            @RequestBody PasswordChangedRequest request) {
        return ResponseEntity.ok(emailService.sendPasswordChangedEmail(
            request.getTo(),
            request.getNickname()
        ));
    }

    /**
     * 发送资料修改通知
     */
    @PostMapping("/profile-updated")
    public ResponseEntity<EmailResponse> sendProfileUpdatedEmail(
            @RequestBody ProfileUpdatedRequest request) {
        return ResponseEntity.ok(emailService.sendProfileUpdatedEmail(
            request.getTo(),
            request.getNickname()
        ));
    }

    /**
     * 发送账号删除通知
     */
    @PostMapping("/account-deleted")
    public ResponseEntity<EmailResponse> sendAccountDeletedEmail(
            @RequestBody AccountDeletedRequest request) {
        return ResponseEntity.ok(emailService.sendAccountDeletedEmail(
            request.getTo(),
            request.getNickname()
        ));
    }
}
```

```java
// EmailService.java
@Service
@RequiredArgsConstructor
@Slf4j
public class EmailService {

    private final SesClient sesClient;

    @Value("${ses.from-address}")
    private String fromAddress;

    @Value("${app.name:Auth Platform}")
    private String appName;

    /**
     * 发送验证码邮件 (注册/密码重置/账号注销)
     */
    public EmailResponse sendVerificationCodeEmail(String to, String code, String type, int expiresInMinutes) {
        String subject;
        String body;

        if ("EMAIL_VERIFICATION".equals(type)) {
            subject = "邮箱验证码";
            body = String.format("""
                <html>
                <body style="font-family: Arial, sans-serif;">
                    <h2>欢迎注册 %s</h2>
                    <p>您的邮箱验证码是：</p>
                    <h1 style="color: #4CAF50; letter-spacing: 5px;">%s</h1>
                    <p>验证码将在 %d 分钟后过期。</p>
                    <p>如果这不是您本人的操作，请忽略此邮件。</p>
                    <p>祝好，<br>%s 团队</p>
                </body>
                </html>
                """, appName, code, expiresInMinutes, appName);
        } else if ("ACCOUNT_DELETION".equals(type)) {
            subject = "账号注销验证码";
            body = String.format("""
                <html>
                <body style="font-family: Arial, sans-serif;">
                    <h2 style="color: #e74c3c;">账号注销请求</h2>
                    <p>您正在申请注销 %s 账号，验证码是：</p>
                    <h1 style="color: #e74c3c; letter-spacing: 5px;">%s</h1>
                    <p>验证码将在 %d 分钟后过期。</p>
                    <p style="color: #e65100;"><strong>警告：</strong>账号注销后，您的所有数据将被永久删除，无法恢复。</p>
                    <p style="color: #e74c3c;">如果这不是您本人的操作，请立即修改密码并联系客服。</p>
                    <p>祝好，<br>%s 团队</p>
                </body>
                </html>
                """, appName, code, expiresInMinutes, appName);
        } else {
            subject = "密码重置验证码";
            body = String.format("""
                <html>
                <body style="font-family: Arial, sans-serif;">
                    <h2>密码重置请求</h2>
                    <p>您正在重置 %s 账号密码，验证码是：</p>
                    <h1 style="color: #FF9800; letter-spacing: 5px;">%s</h1>
                    <p>验证码将在 %d 分钟后过期。</p>
                    <p>如果这不是您本人的操作，请立即联系客服。</p>
                    <p>祝好，<br>%s 团队</p>
                </body>
                </html>
                """, appName, code, expiresInMinutes, appName);
        }

        return sendEmail(to, subject, body);
    }

    /**
     * 发送欢迎邮件
     */
    public EmailResponse sendWelcomeEmail(String to, String nickname) {
        String subject = String.format("欢迎加入 %s", appName);
        String body = String.format("""
            <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>您好，%s</h2>
                <p>欢迎加入 %s！您的账号已成功创建。</p>
                <p>现在您可以登录并开始使用我们的服务。</p>
                <p>祝好，<br>%s 团队</p>
            </body>
            </html>
            """, nickname, appName, appName);

        return sendEmail(to, subject, body);
    }

    /**
     * 发送密码变更通知
     */
    public EmailResponse sendPasswordChangedEmail(String to, String nickname) {
        String subject = "密码已修改";
        String body = String.format("""
            <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>您好，%s</h2>
                <p>您的账户密码已成功修改。</p>
                <p>如果这不是您本人的操作，请立即联系我们的客服团队。</p>
                <p>祝好，<br>%s 团队</p>
            </body>
            </html>
            """, nickname, appName);

        return sendEmail(to, subject, body);
    }

    /**
     * 发送资料修改通知
     */
    public EmailResponse sendProfileUpdatedEmail(String to, String nickname) {
        String subject = "个人资料已更新";
        String body = String.format("""
            <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>您好，%s</h2>
                <p>您的个人资料已成功更新。</p>
                <p>如果这不是您本人的操作，请立即联系我们的客服团队。</p>
                <p>祝好，<br>%s 团队</p>
            </body>
            </html>
            """, nickname, appName);

        return sendEmail(to, subject, body);
    }

    /**
     * 发送账号删除通知
     */
    public EmailResponse sendAccountDeletedEmail(String to, String nickname) {
        String subject = "账号已删除";
        String body = String.format("""
            <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>您好，%s</h2>
                <p>您的账号已成功删除。</p>
                <p>感谢您使用我们的服务。如有任何问题，请联系客服。</p>
                <p>祝好，<br>%s 团队</p>
            </body>
            </html>
            """, nickname, appName);

        return sendEmail(to, subject, body);
    }

    private EmailResponse sendEmail(String to, String subject, String body) {
        try {
            SendEmailRequest request = SendEmailRequest.builder()
                .source(fromAddress)
                .destination(Destination.builder().toAddresses(to).build())
                .message(Message.builder()
                    .subject(Content.builder().data(subject).charset("UTF-8").build())
                    .body(Body.builder()
                        .html(Content.builder().data(body).charset("UTF-8").build())
                        .build())
                    .build())
                .build();

            SendEmailResponse response = sesClient.sendEmail(request);
            log.info("Email sent: to={}, messageId={}", to, response.messageId());

            return new EmailResponse(true, response.messageId());

        } catch (SesException e) {
            log.error("Failed to send email: to={}, error={}", to, e.getMessage());
            throw new RuntimeException("Failed to send email", e);
        }
    }
}
```

```java
// DTO 示例

// VerificationCodeRequest.java
@Data
public class VerificationCodeRequest {
    private String to;
    private String code;
    private String type;  // EMAIL_VERIFICATION, PASSWORD_RESET, or ACCOUNT_DELETION
    private int expiresInMinutes;
}

// WelcomeEmailRequest.java
@Data
public class WelcomeEmailRequest {
    private String to;
    private String nickname;
}

// PasswordChangedRequest.java
@Data
public class PasswordChangedRequest {
    private String to;
    private String nickname;
}

// ProfileUpdatedRequest.java
@Data
public class ProfileUpdatedRequest {
    private String to;
    private String nickname;
}

// AccountDeletedRequest.java
@Data
public class AccountDeletedRequest {
    private String to;
    private String nickname;
}

// EmailResponse.java
@Data
@AllArgsConstructor
public class EmailResponse {
    private boolean success;
    private String messageId;
}
```

---

## 7. 服务间通信

### 7.1 通信方式

| 调用方 | 被调用方 | 方式 | 说明 |
|-------|---------|------|------|
| Frontend | User Service | HTTP REST | /api/users/* 通过 ALB 路由 |
| Frontend | Profile Service | HTTP REST | /api/profiles/* 通过 ALB 路由 |
| User Service | Cognito | AWS SDK | 用户创建、密码管理、邮箱验证状态更新 |
| User Service | Notification Service | HTTP REST | 内部 API (验证码/欢迎/密码变更/账号删除邮件) |
| Profile Service | Notification Service | HTTP REST | 内部 API (资料修改通知邮件) |

### 7.2 前端 API 调用映射

| 前端功能 | HTTP 方法 | API URI | 目标服务 | 认证 |
|----------|----------|---------|----------|------|
| 用户注册 | POST | /api/users/register | user-service | 无需 |
| 验证邮箱 | POST | /api/users/verify-email | user-service | 无需 |
| 重发验证码 | POST | /api/users/resend-verification | user-service | 无需 |
| 忘记密码 | POST | /api/users/forgot-password | user-service | 无需 |
| 重置密码 | POST | /api/users/reset-password | user-service | 无需 |
| 获取用户身份信息 | GET | /api/users/me | user-service | JWT |
| 修改密码 | POST | /api/users/me/change-password | user-service | JWT |
| 发送注销验证码 | POST | /api/users/delete-account/send-code | user-service | JWT |
| 确认注销账户 | POST | /api/users/delete-account/confirm | user-service | JWT |
| 注销账户 (直接) | DELETE | /api/users/me | user-service | JWT |
| 获取用户资料 | GET | /api/profiles/me | profile-service | JWT |
| 更新用户资料 | PUT | /api/profiles/me | profile-service | JWT |
| 上传头像 | POST | /api/profiles/me/avatar | profile-service | JWT |
| 删除头像 | DELETE | /api/profiles/me/avatar | profile-service | JWT |
| 获取头像图片 | GET | /api/profiles/{userId}/avatar/image | profile-service | 无需 |

### 7.3 内部 API 认证

```yaml
# 内部 API 使用 API Key 认证
内部调用:
  认证方式: X-Internal-Api-Key Header
  存储位置: AWS Secrets Manager
  验证: 每个服务启动时加载并验证
```

```java
// InternalApiKeyFilter.java
@Component
public class InternalApiKeyFilter extends OncePerRequestFilter {

    @Value("${internal.api-key}")
    private String expectedApiKey;

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {

        String path = request.getRequestURI();

        // 只检查内部 API 路径
        if (path.startsWith("/api/v1/internal/") || path.startsWith("/internal/")) {
            String apiKey = request.getHeader("X-Internal-Api-Key");

            if (!expectedApiKey.equals(apiKey)) {
                response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                response.getWriter().write("{\"error\": \"Invalid API Key\"}");
                return;
            }
        }

        filterChain.doFilter(request, response);
    }
}
```

### 7.4 服务间调用客户端

```java
// NotificationServiceClient.java (在 User Service 中)
@Component
@RequiredArgsConstructor
@Slf4j
public class NotificationServiceClient {

    private final RestTemplate restTemplate;

    @Value("${services.notification.url}")
    private String notificationServiceUrl;

    @Value("${internal.api-key}")
    private String apiKey;

    /**
     * 发送验证码邮件 (注册或密码重置)
     */
    public void sendVerificationCode(String email, String code, String type, int expiresInMinutes) {
        Map<String, Object> request = Map.of(
            "to", email,
            "code", code,
            "type", type,
            "expiresInMinutes", expiresInMinutes
        );
        post("/api/v1/notifications/verification-code", request);
    }

    /**
     * 发送欢迎邮件
     */
    public void sendWelcomeEmail(String email, String nickname) {
        Map<String, String> request = Map.of(
            "to", email,
            "nickname", nickname
        );
        post("/api/v1/notifications/welcome", request);
    }

    /**
     * 发送密码变更通知
     */
    public void sendPasswordChangedEmail(String email, String nickname) {
        Map<String, String> request = Map.of(
            "to", email,
            "nickname", nickname
        );
        post("/api/v1/notifications/password-changed", request);
    }

    /**
     * 发送账号删除通知
     */
    public void sendAccountDeletedEmail(String email, String nickname) {
        Map<String, String> request = Map.of(
            "to", email,
            "nickname", nickname
        );
        post("/api/v1/notifications/account-deleted", request);
    }

    private void post(String path, Map<String, ?> request) {
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Internal-Api-Key", apiKey);
        headers.setContentType(MediaType.APPLICATION_JSON);

        HttpEntity<Map<String, ?>> entity = new HttpEntity<>(request, headers);

        try {
            restTemplate.postForEntity(notificationServiceUrl + path, entity, Void.class);
            log.info("Notification sent: path={}, to={}", path, request.get("to"));
        } catch (Exception e) {
            log.error("Failed to send notification: path={}, error={}", path, e.getMessage());
            // 不抛出异常，邮件发送失败不应阻断主流程
        }
    }
}
```

```java
// NotificationServiceClient.java (在 Profile Service 中)
@Component
@RequiredArgsConstructor
@Slf4j
public class NotificationServiceClient {

    private final RestTemplate restTemplate;

    @Value("${services.notification.url}")
    private String notificationServiceUrl;

    @Value("${internal.api-key}")
    private String apiKey;

    /**
     * 发送资料修改通知
     */
    public void sendProfileUpdatedEmail(String email, String nickname) {
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Internal-Api-Key", apiKey);
        headers.setContentType(MediaType.APPLICATION_JSON);

        Map<String, String> request = Map.of(
            "to", email,
            "nickname", nickname
        );

        HttpEntity<Map<String, String>> entity = new HttpEntity<>(request, headers);

        try {
            restTemplate.postForEntity(
                notificationServiceUrl + "/api/v1/notifications/profile-updated",
                entity,
                Void.class
            );
            log.info("Profile update notification sent: to={}", email);
        } catch (Exception e) {
            log.error("Failed to send profile update notification: error={}", e.getMessage());
        }
    }
}
```

---

## 8. Kubernetes 部署

### 8.1 服务部署配置

```yaml
# user-service/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: user-service
  namespace: auth-platform
spec:
  replicas: 2
  selector:
    matchLabels:
      app: user-service
  template:
    metadata:
      labels:
        app: user-service
    spec:
      serviceAccountName: user-service-sa
      containers:
        - name: user-service
          image: xxx.dkr.ecr.ap-northeast-1.amazonaws.com/user-service:latest
          ports:
            - containerPort: 8080
          env:
            - name: SPRING_PROFILES_ACTIVE
              value: "production"
            - name: COGNITO_USER_POOL_ID
              valueFrom:
                configMapKeyRef:
                  name: auth-platform-config
                  key: cognito-user-pool-id
          envFrom:
            - secretRef:
                name: user-service-secrets
          resources:
            requests:
              memory: "512Mi"
              cpu: "250m"
            limits:
              memory: "1Gi"
              cpu: "1000m"
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            initialDelaySeconds: 60
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            initialDelaySeconds: 30
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: user-service
  namespace: auth-platform
spec:
  selector:
    app: user-service
  ports:
    - port: 8080
      targetPort: 8080
  type: ClusterIP
```

### 8.2 Ingress 配置

```yaml
# ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: auth-platform-ingress
  namespace: auth-platform
  annotations:
    kubernetes.io/ingress.class: alb
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:ap-northeast-1:xxx:certificate/xxx
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTPS":443}]'
    alb.ingress.kubernetes.io/healthcheck-path: /actuator/health
spec:
  rules:
    - host: api.xxx.com
      http:
        paths:
          - path: /api/users
            pathType: Prefix
            backend:
              service:
                name: user-service
                port:
                  number: 8080
          - path: /api/profiles
            pathType: Prefix
            backend:
              service:
                name: profile-service
                port:
                  number: 8080
          - path: /api/v1/notifications
            pathType: Prefix
            backend:
              service:
                name: notification-service
                port:
                  number: 8080
```

---

## 9. 认证流程

### 9.1 用户注册流程

```
┌────────┐     ┌──────────┐     ┌─────────────┐     ┌─────────────┐     ┌───────────────────┐
│  用户   │     │  Frontend │     │User Service │     │   Cognito   │     │Notification Service│
└───┬────┘     └─────┬─────┘     └──────┬──────┘     └──────┬──────┘     └─────────┬─────────┘
    │                │                  │                   │                      │
    │ 1.填写注册表单   │                  │                   │                      │
    │───────────────▶│                  │                   │                      │
    │                │                  │                   │                      │
    │                │ 2.POST /register │                   │                      │
    │                │─────────────────▶│                   │                      │
    │                │                  │                   │                      │
    │                │                  │ 3.业务验证         │                      │
    │                │                  │                   │                      │
    │                │                  │ 4.创建用户(禁用自动邮箱验证)               │
    │                │                  │──────────────────▶│                      │
    │                │                  │◀──────────────────│                      │
    │                │                  │   userId          │                      │
    │                │                  │                   │                      │
    │                │                  │ 5.生成验证码并存储到 verification_codes 表 │
    │                │                  │                   │                      │
    │                │                  │ 6.发送验证码邮件   │                      │
    │                │                  │─────────────────────────────────────────▶│
    │                │                  │◀─────────────────────────────────────────│
    │                │                  │   发送成功         │                      │
    │                │                  │                   │                      │
    │                │◀─────────────────│                   │                      │
    │                │ 注册待验证        │                   │                      │
    │                │                  │                   │                      │
    │◀───────────────│                  │                   │                      │
    │  显示验证页面    │                  │                   │                      │
    │                │                  │                   │                      │
    │◀────────────────────────────────────────────────────────────────────────────│
    │  收到验证码邮件  │                  │                   │                      │
    │                │                  │                   │                      │
    │ 7.输入验证码     │                  │                   │                      │
    │───────────────▶│                  │                   │                      │
    │                │                  │                   │                      │
    │                │ 8.POST /verify-email                 │                      │
    │                │─────────────────▶│                   │                      │
    │                │                  │                   │                      │
    │                │                  │ 9.验证验证码       │                      │
    │                │                  │ 10.删除验证码记录  │                      │
    │                │                  │                   │                      │
    │                │                  │ 11.更新 email_verified                   │
    │                │                  │──────────────────▶│                      │
    │                │                  │                   │                      │
    │                │                  │ 12.发送欢迎邮件    │                      │
    │                │                  │─────────────────────────────────────────▶│
    │                │                  │                   │                      │
    │                │◀─────────────────│                   │                      │
    │                │ 验证成功          │                   │                      │
    │                │                  │                   │                      │
    │◀───────────────│                  │                   │                      │
    │  跳转登录页面    │                  │                   │                      │
```

### 9.2 密码重置流程

```
┌────────┐     ┌──────────┐     ┌─────────────┐     ┌─────────────┐     ┌───────────────────┐
│  用户   │     │  Frontend │     │User Service │     │   Cognito   │     │Notification Service│
└───┬────┘     └─────┬─────┘     └──────┬──────┘     └──────┬──────┘     └─────────┬─────────┘
    │                │                  │                   │                      │
    │ 1.点击忘记密码   │                  │                   │                      │
    │───────────────▶│                  │                   │                      │
    │                │                  │                   │                      │
    │                │ 2.POST /forgot-password              │                      │
    │                │─────────────────▶│                   │                      │
    │                │                  │                   │                      │
    │                │                  │ 3.验证邮箱是否存在 │                      │
    │                │                  │                   │                      │
    │                │                  │ 4.生成重置验证码并存储                    │
    │                │                  │                   │                      │
    │                │                  │ 5.发送重置验证码邮件                      │
    │                │                  │─────────────────────────────────────────▶│
    │                │                  │◀─────────────────────────────────────────│
    │                │                  │                   │                      │
    │                │◀─────────────────│                   │                      │
    │                │ 验证码已发送      │                   │                      │
    │                │                  │                   │                      │
    │◀───────────────│                  │                   │                      │
    │  显示重置页面    │                  │                   │                      │
    │                │                  │                   │                      │
    │◀────────────────────────────────────────────────────────────────────────────│
    │  收到重置邮件    │                  │                   │                      │
    │                │                  │                   │                      │
    │ 6.输入验证码和新密码                │                   │                      │
    │───────────────▶│                  │                   │                      │
    │                │                  │                   │                      │
    │                │ 7.POST /reset-password               │                      │
    │                │─────────────────▶│                   │                      │
    │                │                  │                   │                      │
    │                │                  │ 8.验证重置验证码   │                      │
    │                │                  │ 9.删除验证码记录   │                      │
    │                │                  │                   │                      │
    │                │                  │ 10.设置新密码      │                      │
    │                │                  │──────────────────▶│                      │
    │                │                  │                   │                      │
    │                │◀─────────────────│                   │                      │
    │                │ 重置成功          │                   │                      │
    │                │                  │                   │                      │
    │◀───────────────│                  │                   │                      │
    │  跳转登录页面    │                  │                   │                      │
```

### 9.3 用户登录流程

```
┌────────┐     ┌──────────┐     ┌─────────────┐
│  用户   │     │  Frontend │     │   Cognito   │
└───┬────┘     └─────┬─────┘     └──────┬──────┘
    │                │                  │
    │ 1.点击登录      │                  │
    │───────────────▶│                  │
    │                │                  │
    │                │ 2.重定向到Cognito │
    │◀───────────────│                  │
    │                │                  │
    │ 3.输入凭证      │                  │
    │─────────────────────────────────▶│
    │                │                  │
    │                │                  │ 4.验证
    │                │                  │
    │◀─────────────────────────────────│
    │   重定向callback │                  │
    │                │                  │
    │───────────────▶│                  │
    │                │                  │
    │                │ 5.交换Token      │
    │                │─────────────────▶│
    │                │◀─────────────────│
    │                │   tokens         │
    │                │                  │
    │◀───────────────│                  │
    │   登录成功      │                  │
```

---

## 10. 配置管理

### 10.1 环境变量

```yaml
# 各服务共用的配置
common:
  COGNITO_USER_POOL_ID: ap-northeast-1_xxxxxxxx
  COGNITO_REGION: ap-northeast-1
  DB_HOST: auth-platform-db.cluster-xxx.ap-northeast-1.rds.amazonaws.com
  DB_NAME: auth_platform

# User Service 配置
user-service:
  NOTIFICATION_SERVICE_URL: http://notification-service:8080
  INTERNAL_API_KEY: ${SECRET}

# Profile Service 配置
profile-service:
  NOTIFICATION_SERVICE_URL: http://notification-service:8080
  INTERNAL_API_KEY: ${SECRET}

# Notification Service 配置
notification-service:
  SES_FROM_ADDRESS: noreply@xxx.com
  SES_REGION: ap-northeast-1
  INTERNAL_API_KEY: ${SECRET}
```

### 10.2 Kubernetes ConfigMap & Secrets

```yaml
# configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: auth-platform-config
  namespace: auth-platform
data:
  cognito-user-pool-id: "ap-northeast-1_xxxxxxxx"
  cognito-region: "ap-northeast-1"
  db-host: "auth-platform-db.cluster-xxx.ap-northeast-1.rds.amazonaws.com"
  db-name: "auth_platform"

---
# secrets.yaml (实际值从 Secrets Manager 获取)
apiVersion: v1
kind: Secret
metadata:
  name: auth-platform-secrets
  namespace: auth-platform
type: Opaque
data:
  db-password: <base64>
  internal-api-key: <base64>
```

---

## 11. 监控与日志

### 11.1 各服务监控指标

| 服务 | 指标 | 说明 |
|------|------|------|
| User Service | user_registrations_total | 注册总数 |
| User Service | user_deletions_total | 删除总数 |
| Profile Service | profile_updates_total | 资料更新总数 |
| Notification Service | emails_sent_total | 邮件发送总数 |
| Notification Service | emails_failed_total | 邮件发送失败数 |

### 11.2 日志架构

```
应用容器 ──▶ stdout (JSON) ──▶ Fluent Bit ──▶ CloudWatch Logs ──▶ OpenSearch
                                   │
                                   └──▶ 直接发送到 OpenSearch (可选)
```

### 11.3 日志格式 (JSON)

使用 `logstash-logback-encoder` 生成结构化 JSON 日志，便于 CloudWatch Logs Insights 和 OpenSearch 查询。

**请求日志示例:**

```json
{
  "timestamp": "2024-01-15T10:30:45.123+09:00",
  "level": "INFO",
  "logger": "c.a.u.logging.LoggingFilter",
  "thread": "http-nio-8080-exec-1",
  "message": "Request completed: PUT /api/users/me/profile - 200 (45ms)",
  "service": "user-service",
  "environment": "production",
  "pod_name": "user-service-7d4f8b9c6-x2k9m",
  "pod_namespace": "auth-platform",
  "node_name": "ip-10-0-11-45.ap-northeast-1.compute.internal",
  "trace_id": "1-65a4b2c3-abcdef1234567890",
  "span_id": "a1b2c3d4",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "cognito-sub-uuid",
  "client_ip": "203.0.113.45",
  "request_method": "PUT",
  "request_uri": "/api/users/me/profile",
  "response_status": "200",
  "response_time_ms": "45"
}
```

**业务事件日志示例:**

```json
{
  "timestamp": "2024-01-15T10:30:45.100+09:00",
  "level": "INFO",
  "logger": "c.a.u.service.UserService",
  "message": "[PROFILE_UPDATED] User profile updated",
  "service": "user-service",
  "environment": "production",
  "trace_id": "1-65a4b2c3-abcdef1234567890",
  "user_id": "cognito-sub-uuid",
  "event_type": "AUDIT",
  "event_name": "PROFILE_UPDATED",
  "target_user_id": "cognito-sub-uuid",
  "updated_fields": "nickname,avatar,address"
}
```

**异常日志示例:**

```json
{
  "timestamp": "2024-01-15T10:30:45.500+09:00",
  "level": "ERROR",
  "logger": "c.a.u.exception.GlobalExceptionHandler",
  "message": "[UNEXPECTED_ERROR] Unexpected error occurred",
  "service": "user-service",
  "trace_id": "1-65a4b2c3-abcdef1234567890",
  "event_type": "BUSINESS",
  "event_name": "UNEXPECTED_ERROR",
  "error_type": "NullPointerException",
  "error_message": "Cannot invoke method on null object",
  "stack_trace": "java.lang.NullPointerException: Cannot invoke...\n\tat com.authplatform..."
}
```

### 11.4 日志字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| timestamp | string | ISO8601 格式时间戳 |
| level | string | 日志级别 (DEBUG/INFO/WARN/ERROR) |
| logger | string | Logger 名称 |
| message | string | 日志消息 |
| service | string | 服务名称 |
| environment | string | 环境 (local/dev/production) |
| pod_name | string | K8s Pod 名称 |
| trace_id | string | 分布式追踪 ID (来自 ALB 或自动生成) |
| span_id | string | 请求 Span ID |
| user_id | string | 当前用户 ID (从 JWT 提取) |
| client_ip | string | 客户端 IP |
| request_method | string | HTTP 方法 |
| request_uri | string | 请求 URI |
| response_status | string | HTTP 响应状态码 |
| response_time_ms | string | 请求处理时间 (毫秒) |
| event_type | string | 事件类型 (BUSINESS/AUDIT/SECURITY/PERFORMANCE) |
| event_name | string | 事件名称 |

### 11.5 日志事件类型

| 类型 | 用途 | 示例 |
|------|------|------|
| BUSINESS | 业务逻辑事件 | 资源未找到、验证失败 |
| AUDIT | 审计跟踪 | 用户创建、资料更新、账号删除 |
| SECURITY | 安全事件 | 认证失败、访问拒绝 |
| PERFORMANCE | 性能相关 | 慢查询、外部调用超时 |
| INTEGRATION | 外部集成 | Cognito 调用、SES 发送 |

### 11.6 CloudWatch Logs Insights 查询示例

```sql
-- 查询特定用户的所有操作
fields @timestamp, level, message, event_name, updated_fields
| filter user_id = "cognito-sub-uuid"
| sort @timestamp desc
| limit 100

-- 查询所有错误日志
fields @timestamp, message, error_type, error_message, trace_id
| filter level = "ERROR"
| sort @timestamp desc
| limit 50

-- 统计各 API 的平均响应时间
fields request_uri, response_time_ms
| filter ispresent(response_time_ms)
| stats avg(response_time_ms) as avg_time, count() as count by request_uri
| sort avg_time desc

-- 查询慢请求 (>500ms)
fields @timestamp, request_method, request_uri, response_time_ms, user_id
| filter response_time_ms > 500
| sort response_time_ms desc
| limit 50

-- 按 trace_id 追踪完整请求链
fields @timestamp, level, message
| filter trace_id = "1-65a4b2c3-abcdef1234567890"
| sort @timestamp asc
```

---

## 12. 项目总结

### 12.1 微服务列表

| 服务 | 职责 | 技术栈 | 部署 |
|------|------|--------|------|
| Frontend | 用户界面、认证集成 | React + TypeScript + Ant Design + Amplify SDK | S3 + CloudFront |
| User Service | 用户注册、邮箱验证、密码重置、身份管理、账户删除 | Spring Boot + AWS SDK | EKS |
| Profile Service | 用户资料管理、头像上传/删除 | Spring Boot + JPA + S3 | EKS |
| Notification Service | 统一邮件通知 (验证码/欢迎/密码变更/资料变更/账号删除) | Spring Boot + SES | EKS |

### 12.2 数据流向

```
用户 ──▶ CloudFront ──▶ S3 (Frontend)
              │
              │ /api/*
              ▼
           ALB ────┬──▶ User Service ──┬──▶ Cognito (用户创建/密码管理)
                   │                   │
                   │                   ├──▶ Aurora (users + verification_codes)
                   │                   │
                   │                   └──▶ Notification Service ──▶ SES
                   │                        (验证码/欢迎/密码变更/账号删除邮件)
                   │
                   ├──▶ Profile Service ──┬──▶ Aurora (用户资料)
                   │                      │
                   │                      ├──▶ S3 (头像文件)
                   │                      │
                   │                      └──▶ Notification Service ──▶ SES
                   │                           (资料修改通知)
                   │
                   └──▶ Notification Service ──▶ SES (所有邮件通知)
```

### 12.3 数据职责划分

| 数据类型 | 存储位置 | 管理服务 |
|---------|---------|----------|
| 用户凭证 (密码) | Cognito | Cognito |
| Token/Session | Cognito | Cognito |
| 用户身份信息 (username, email, status) | Aurora (users 表) | User Service |
| 验证码 (注册/密码重置) | Aurora (verification_codes 表) | User Service |
| 用户资料 (nickname, avatar, gender, birthday, address) | Aurora (users 表) | Profile Service |
| 头像文件 | S3 | Profile Service |
| 邮件发送 | SES | Notification Service |

### 12.4 邮件通知职责

| 邮件类型 | 触发场景 | 调用方 |
|---------|---------|--------|
| 邮箱验证码 | 用户注册 | User Service |
| 密码重置验证码 | 忘记密码 | User Service |
| 欢迎邮件 | 邮箱验证完成 | User Service |
| 密码变更通知 | 修改密码 | User Service |
| 资料修改通知 | 更新个人资料 | Profile Service |
| 账号删除通知 | 注销账户 | User Service |

> **注意**: Cognito 的自动邮箱验证功能已禁用，所有邮件通知统一由 Notification Service 发送。
