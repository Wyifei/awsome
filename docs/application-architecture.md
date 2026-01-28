# 应用架构文档

## 1. 系统概述

### 1.1 背景

为电动自行车制造企业构建基于 OIDC 协议的统一身份认证平台，服务于官网、移动 APP 等多端应用。

### 1.2 目标

- 提供统一的用户身份认证服务
- 支持多种登录方式（密码登录、邮件 OTP 无密码登录）
- 支持多端接入（Web、移动 APP、第三方应用）
- 符合 OIDC/OAuth 2.0 标准
- 高可用、可扩展、安全可靠

### 1.3 核心功能

| 功能模块 | 实现方式 | 说明 |
|---------|---------|------|
| 用户注册 | User Service + Cognito | 账号创建与验证 |
| 用户登录 | Cognito | 用户名+密码、邮件 OTP |
| OIDC 认证 | Cognito | 标准 OIDC/OAuth2 流程 |
| 用户资料管理 | Profile Service | 用户基本档案修改 |
| 账号管理 | User Service | 用户账号注册/删除 |
| 邮件通知 | Notification Service | 账号修改/删除通知 |
| 验证码发送 | Cognito | 注册/登录验证码 (自动) |

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
| User Service | 用户账号注册、删除、状态管理 | EKS | Cognito + Aurora |
| Profile Service | 用户基本档案查看与修改 | EKS | Aurora |
| Notification Service | 账号修改/删除通知邮件 | EKS | SES |

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
    ├── User Service API (获取/更新用户信息)
    └── Profile Service API (获取/更新用户资料)
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
| API 前缀 | /api/v1/users |

### 4.2 职责

```
User Service
├── 用户注册
│   ├── 接收注册请求
│   ├── 业务规则验证 (邮箱域名限制等)
│   └── 调用 Cognito 创建用户 (Cognito 自动发送验证码)
│
├── 用户删除/注销
│   ├── 用户自助注销
│   ├── 管理员删除用户
│   ├── 调用 Cognito 删除用户
│   ├── 清理关联数据 (通知 Profile Service)
│   └── 发送删除通知邮件 (调用 Notification Service)
│
└── 账号状态管理
    ├── 启用/禁用用户
    ├── 锁定/解锁账号
    └── 管理员用户列表查询
```

### 4.3 API 设计

```yaml
# 用户注册
POST /api/v1/users/register
Request:
  {
    "email": "user@example.com",
    "password": "Password123!",
    "firstName": "John",
    "lastName": "Doe"
  }
Response:
  {
    "success": true,
    "userId": "cognito-sub-uuid",
    "message": "Registration successful. Please verify your email."
  }

# 用户注销 (当前用户)
DELETE /api/v1/users/me
Headers:
  Authorization: Bearer {access_token}
Response:
  {
    "success": true,
    "message": "Account deleted successfully"
  }

# 获取用户列表 (管理员)
GET /api/v1/users?page=0&size=20&status=CONFIRMED
Headers:
  Authorization: Bearer {admin_token}
Response:
  {
    "users": [
      {
        "userId": "cognito-sub-uuid",
        "email": "user@example.com",
        "status": "CONFIRMED",
        "enabled": true,
        "createdAt": "2024-01-01T00:00:00Z"
      }
    ],
    "pagination": {
      "page": 0,
      "size": 20,
      "totalElements": 100,
      "totalPages": 5
    }
  }

# 获取单个用户 (管理员)
GET /api/v1/users/{userId}
Headers:
  Authorization: Bearer {admin_token}
Response:
  {
    "userId": "cognito-sub-uuid",
    "email": "user@example.com",
    "firstName": "John",
    "lastName": "Doe",
    "status": "CONFIRMED",
    "enabled": true,
    "emailVerified": true,
    "createdAt": "2024-01-01T00:00:00Z",
    "lastModifiedAt": "2024-01-01T00:00:00Z"
  }

# 禁用用户 (管理员)
POST /api/v1/users/{userId}/disable
Headers:
  Authorization: Bearer {admin_token}
Request:
  {
    "reason": "Violation of terms of service"
  }
Response:
  {
    "success": true,
    "message": "User disabled"
  }

# 启用用户 (管理员)
POST /api/v1/users/{userId}/enable
Headers:
  Authorization: Bearer {admin_token}
Response:
  {
    "success": true,
    "message": "User enabled"
  }

# 删除用户 (管理员)
DELETE /api/v1/users/{userId}
Headers:
  Authorization: Bearer {admin_token}
Response:
  {
    "success": true,
    "message": "User deleted"
  }
```

### 4.4 项目结构

```
user-service/
├── src/main/java/com/xxx/user/
│   ├── UserServiceApplication.java
│   │
│   ├── config/
│   │   ├── SecurityConfig.java        # Spring Security 配置
│   │   ├── CognitoConfig.java          # Cognito 客户端配置
│   │   └── WebConfig.java              # Web 配置
│   │
│   ├── controller/
│   │   ├── UserController.java         # 用户 API
│   │   └── AdminUserController.java    # 管理员 API
│   │
│   ├── service/
│   │   ├── UserService.java            # 用户业务逻辑
│   │   ├── CognitoService.java         # Cognito 交互
│   │   └── UserEventPublisher.java     # 事件发布 (通知其他服务)
│   │
│   ├── dto/
│   │   ├── RegisterRequest.java
│   │   ├── RegisterResponse.java
│   │   ├── UserResponse.java
│   │   └── UserListResponse.java
│   │
│   ├── exception/
│   │   ├── UserNotFoundException.java
│   │   ├── RegistrationException.java
│   │   └── GlobalExceptionHandler.java
│   │
│   └── client/
│       ├── ProfileServiceClient.java   # Profile Service 调用
│       └── NotificationServiceClient.java # Notification Service 调用
│
├── src/main/resources/
│   ├── application.yml
│   └── application-production.yml
│
├── build.gradle
└── Dockerfile
```

### 4.5 核心代码示例

```java
// UserService.java
@Service
@RequiredArgsConstructor
@Slf4j
public class UserService {

    private final CognitoService cognitoService;
    private final ProfileServiceClient profileServiceClient;
    private final NotificationServiceClient notificationServiceClient;

    /**
     * 用户注册
     * 注: 验证码邮件由 Cognito 自动发送
     */
    @Transactional
    public RegisterResponse register(RegisterRequest request) {
        // 1. 业务规则验证
        validateRegistration(request);

        // 2. 调用 Cognito 创建用户 (Cognito 会自动发送验证码邮件)
        String userId = cognitoService.createUser(
            request.getEmail(),
            request.getPassword(),
            request.getFirstName(),
            request.getLastName()
        );

        log.info("User registered successfully: {}", userId);

        return RegisterResponse.builder()
            .success(true)
            .userId(userId)
            .message("Registration successful. Please verify your email.")
            .build();
    }

    /**
     * 删除当前用户
     */
    @Transactional
    public void deleteCurrentUser(String userId, String email, String firstName) {
        // 1. 删除 Cognito 用户
        cognitoService.deleteUser(userId);

        // 2. 通知 Profile Service 清理数据
        profileServiceClient.deleteProfile(userId);

        // 3. 发送账号删除通知邮件
        notificationServiceClient.sendAccountDeletedEmail(email, firstName);

        log.info("User deleted: {}", userId);
    }

    /**
     * 禁用用户 (管理员)
     */
    public void disableUser(String userId, String reason) {
        cognitoService.disableUser(userId);
        log.info("User disabled: {}, reason: {}", userId, reason);
    }

    /**
     * 启用用户 (管理员)
     */
    public void enableUser(String userId) {
        cognitoService.enableUser(userId);
        log.info("User enabled: {}", userId);
    }

    private void validateRegistration(RegisterRequest request) {
        // 邮箱域名限制等业务规则
        String email = request.getEmail();
        // 可添加自定义验证逻辑
    }
}
```

```java
// CognitoService.java
@Service
@RequiredArgsConstructor
public class CognitoService {

    private final CognitoIdentityProviderClient cognitoClient;

    @Value("${cognito.user-pool-id}")
    private String userPoolId;

    public String createUser(String email, String password, String firstName, String lastName) {
        AdminCreateUserRequest request = AdminCreateUserRequest.builder()
            .userPoolId(userPoolId)
            .username(email)
            .temporaryPassword(password)
            .userAttributes(
                AttributeType.builder().name("email").value(email).build(),
                AttributeType.builder().name("email_verified").value("true").build(),
                AttributeType.builder().name("given_name").value(firstName).build(),
                AttributeType.builder().name("family_name").value(lastName).build()
            )
            .messageAction(MessageActionType.SUPPRESS)  // 不发送临时密码邮件
            .build();

        AdminCreateUserResponse response = cognitoClient.adminCreateUser(request);

        // 设置永久密码
        AdminSetUserPasswordRequest passwordRequest = AdminSetUserPasswordRequest.builder()
            .userPoolId(userPoolId)
            .username(email)
            .password(password)
            .permanent(true)
            .build();

        cognitoClient.adminSetUserPassword(passwordRequest);

        return response.user().attributes().stream()
            .filter(attr -> "sub".equals(attr.name()))
            .findFirst()
            .map(AttributeType::value)
            .orElseThrow();
    }

    public void deleteUser(String userId) {
        AdminDeleteUserRequest request = AdminDeleteUserRequest.builder()
            .userPoolId(userPoolId)
            .username(userId)
            .build();

        cognitoClient.adminDeleteUser(request);
    }

    public void disableUser(String userId) {
        AdminDisableUserRequest request = AdminDisableUserRequest.builder()
            .userPoolId(userPoolId)
            .username(userId)
            .build();

        cognitoClient.adminDisableUser(request);
    }

    public void enableUser(String userId) {
        AdminEnableUserRequest request = AdminEnableUserRequest.builder()
            .userPoolId(userPoolId)
            .username(userId)
            .build();

        cognitoClient.adminEnableUser(request);
    }

    public List<CognitoUser> listUsers(String paginationToken, int limit) {
        ListUsersRequest.Builder requestBuilder = ListUsersRequest.builder()
            .userPoolId(userPoolId)
            .limit(limit);

        if (paginationToken != null) {
            requestBuilder.paginationToken(paginationToken);
        }

        ListUsersResponse response = cognitoClient.listUsers(requestBuilder.build());

        return response.users().stream()
            .map(this::mapToCognitoUser)
            .collect(Collectors.toList());
    }

    private CognitoUser mapToCognitoUser(UserType user) {
        Map<String, String> attrs = user.attributes().stream()
            .collect(Collectors.toMap(AttributeType::name, AttributeType::value));

        return CognitoUser.builder()
            .userId(attrs.get("sub"))
            .email(attrs.get("email"))
            .firstName(attrs.get("given_name"))
            .lastName(attrs.get("family_name"))
            .emailVerified(Boolean.parseBoolean(attrs.getOrDefault("email_verified", "false")))
            .status(user.userStatusAsString())
            .enabled(user.enabled())
            .createdAt(user.userCreateDate())
            .lastModifiedAt(user.userLastModifiedDate())
            .build();
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
| API 前缀 | /api/v1/profiles |

### 5.2 职责

```
Profile Service
├── 资料查看
│   └── 获取当前用户资料
│
├── 资料修改
│   ├── 更新基本信息 (姓名、电话等)
│   ├── 更新地址信息
│   ├── 上传/更新头像
│   └── 发送修改通知邮件 (调用 Notification Service)
│
└── 数据同步
    ├── 接收 Cognito Post Confirmation 事件
    └── 创建初始用户资料记录
```

### 5.3 API 设计

```yaml
# 获取当前用户资料
GET /api/v1/profiles/me
Headers:
  Authorization: Bearer {access_token}
Response:
  {
    "userId": "cognito-sub-uuid",
    "email": "user@example.com",
    "firstName": "John",
    "lastName": "Doe",
    "phone": "+1234567890",
    "avatar": "https://cdn.xxx.com/avatars/xxx.jpg",
    "address": {
      "street": "123 Main St",
      "city": "Tokyo",
      "country": "Japan",
      "postalCode": "100-0001"
    },
    "createdAt": "2024-01-01T00:00:00Z",
    "updatedAt": "2024-01-01T00:00:00Z"
  }

# 更新用户资料
PUT /api/v1/profiles/me
Headers:
  Authorization: Bearer {access_token}
Request:
  {
    "firstName": "John",
    "lastName": "Smith",
    "phone": "+1234567890",
    "address": {
      "street": "456 Oak Ave",
      "city": "Tokyo",
      "country": "Japan",
      "postalCode": "100-0002"
    }
  }
Response:
  {
    "success": true,
    "message": "Profile updated successfully"
  }

# 上传头像
POST /api/v1/profiles/me/avatar
Headers:
  Authorization: Bearer {access_token}
  Content-Type: multipart/form-data
Request:
  file: (binary)
Response:
  {
    "success": true,
    "avatarUrl": "https://cdn.xxx.com/avatars/xxx.jpg"
  }

# 删除用户资料 (内部 API，由 User Service 调用)
DELETE /api/v1/profiles/{userId}
Headers:
  X-Internal-Api-Key: {internal_api_key}
Response:
  {
    "success": true
  }

# 创建用户资料 (内部 API，由 Lambda Trigger 调用)
POST /api/v1/profiles
Headers:
  X-Internal-Api-Key: {internal_api_key}
Request:
  {
    "userId": "cognito-sub-uuid",
    "email": "user@example.com",
    "firstName": "John",
    "lastName": "Doe"
  }
Response:
  {
    "success": true
  }
```

### 5.4 数据库设计

```sql
-- 用户资料表
CREATE TABLE user_profiles (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id         VARCHAR(36) NOT NULL UNIQUE,     -- Cognito sub
    email           VARCHAR(255) NOT NULL,
    first_name      VARCHAR(100),
    last_name       VARCHAR(100),
    phone           VARCHAR(20),
    avatar_url      VARCHAR(500),
    street          VARCHAR(255),
    city            VARCHAR(100),
    country         VARCHAR(100),
    postal_code     VARCHAR(20),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_profiles_user_id (user_id),
    INDEX idx_profiles_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### 5.5 项目结构

```
profile-service/
├── src/main/java/com/xxx/profile/
│   ├── ProfileServiceApplication.java
│   │
│   ├── config/
│   │   ├── SecurityConfig.java
│   │   └── S3Config.java              # S3 头像存储配置
│   │
│   ├── controller/
│   │   ├── ProfileController.java     # 用户资料 API
│   │   └── InternalProfileController.java # 内部 API
│   │
│   ├── service/
│   │   ├── ProfileService.java
│   │   └── AvatarService.java         # 头像上传服务
│   │
│   ├── repository/
│   │   └── UserProfileRepository.java
│   │
│   ├── entity/
│   │   └── UserProfile.java
│   │
│   ├── dto/
│   │   ├── ProfileResponse.java
│   │   ├── UpdateProfileRequest.java
│   │   └── CreateProfileRequest.java
│   │
│   ├── client/
│   │   └── NotificationServiceClient.java # Notification Service 调用
│   │
│   └── exception/
│       ├── ProfileNotFoundException.java
│       └── GlobalExceptionHandler.java
│
├── src/main/resources/
│   └── application.yml
│
├── build.gradle
└── Dockerfile
```

### 5.6 核心代码示例

```java
// ProfileService.java
@Service
@RequiredArgsConstructor
@Transactional
public class ProfileService {

    private final UserProfileRepository profileRepository;
    private final AvatarService avatarService;
    private final NotificationServiceClient notificationServiceClient;

    public ProfileResponse getProfile(String userId) {
        UserProfile profile = profileRepository.findByUserId(userId)
            .orElseThrow(() -> new ProfileNotFoundException("Profile not found: " + userId));

        return mapToResponse(profile);
    }

    public void updateProfile(String userId, UpdateProfileRequest request) {
        UserProfile profile = profileRepository.findByUserId(userId)
            .orElseThrow(() -> new ProfileNotFoundException("Profile not found: " + userId));

        if (request.getFirstName() != null) {
            profile.setFirstName(request.getFirstName());
        }
        if (request.getLastName() != null) {
            profile.setLastName(request.getLastName());
        }
        if (request.getPhone() != null) {
            profile.setPhone(request.getPhone());
        }
        if (request.getAddress() != null) {
            profile.setStreet(request.getAddress().getStreet());
            profile.setCity(request.getAddress().getCity());
            profile.setCountry(request.getAddress().getCountry());
            profile.setPostalCode(request.getAddress().getPostalCode());
        }

        profileRepository.save(profile);

        // 发送账号修改通知邮件
        notificationServiceClient.sendAccountModifiedEmail(profile.getEmail(), profile.getFirstName());
    }

    public String uploadAvatar(String userId, MultipartFile file) {
        UserProfile profile = profileRepository.findByUserId(userId)
            .orElseThrow(() -> new ProfileNotFoundException("Profile not found: " + userId));

        String avatarUrl = avatarService.uploadAvatar(userId, file);

        profile.setAvatarUrl(avatarUrl);
        profileRepository.save(profile);

        return avatarUrl;
    }

    public void createProfile(CreateProfileRequest request) {
        UserProfile profile = UserProfile.builder()
            .userId(request.getUserId())
            .email(request.getEmail())
            .firstName(request.getFirstName())
            .lastName(request.getLastName())
            .build();

        profileRepository.save(profile);
    }

    public void deleteProfile(String userId) {
        profileRepository.deleteByUserId(userId);
    }

    private ProfileResponse mapToResponse(UserProfile profile) {
        return ProfileResponse.builder()
            .userId(profile.getUserId())
            .email(profile.getEmail())
            .firstName(profile.getFirstName())
            .lastName(profile.getLastName())
            .phone(profile.getPhone())
            .avatar(profile.getAvatarUrl())
            .address(AddressDto.builder()
                .street(profile.getStreet())
                .city(profile.getCity())
                .country(profile.getCountry())
                .postalCode(profile.getPostalCode())
                .build())
            .createdAt(profile.getCreatedAt())
            .updatedAt(profile.getUpdatedAt())
            .build();
    }
}
```

```java
// UserProfile.java
@Entity
@Table(name = "user_profiles")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class UserProfile {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id", nullable = false, unique = true, length = 36)
    private String userId;

    @Column(nullable = false)
    private String email;

    @Column(name = "first_name", length = 100)
    private String firstName;

    @Column(name = "last_name", length = 100)
    private String lastName;

    @Column(length = 20)
    private String phone;

    @Column(name = "avatar_url", length = 500)
    private String avatarUrl;

    @Column(length = 255)
    private String street;

    @Column(length = 100)
    private String city;

    @Column(length = 100)
    private String country;

    @Column(name = "postal_code", length = 20)
    private String postalCode;

    @Column(name = "created_at")
    @CreationTimestamp
    private Instant createdAt;

    @Column(name = "updated_at")
    @UpdateTimestamp
    private Instant updatedAt;
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
Notification Service (精简版)
├── 账号修改通知
│   └── 用户修改账户信息时发送确认邮件
│
└── 账号删除通知
    └── 用户删除账户时发送确认邮件

注: 用户注册/登录时的验证码由 Cognito 自动发送，无需本服务处理
```

### 6.3 API 设计

```yaml
# 发送账号修改通知邮件 (内部 API)
POST /api/v1/notifications/account-modified
Headers:
  X-Internal-Api-Key: {internal_api_key}
Request:
  {
    "to": "user@example.com",
    "firstName": "John"
  }
Response:
  {
    "success": true,
    "messageId": "ses-message-id"
  }

# 发送账号删除通知邮件 (内部 API)
POST /api/v1/notifications/account-deleted
Headers:
  X-Internal-Api-Key: {internal_api_key}
Request:
  {
    "to": "user@example.com",
    "firstName": "John"
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
├── src/main/java/com/xxx/notification/
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
│   │   ├── EmailRequest.java
│   │   └── EmailResponse.java
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

    @PostMapping("/account-modified")
    public ResponseEntity<EmailResponse> sendAccountModifiedEmail(@RequestBody EmailRequest request) {
        return ResponseEntity.ok(emailService.sendAccountModifiedEmail(request.getTo(), request.getFirstName()));
    }

    @PostMapping("/account-deleted")
    public ResponseEntity<EmailResponse> sendAccountDeletedEmail(@RequestBody EmailRequest request) {
        return ResponseEntity.ok(emailService.sendAccountDeletedEmail(request.getTo(), request.getFirstName()));
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

    /**
     * 发送账号修改通知邮件
     */
    public EmailResponse sendAccountModifiedEmail(String to, String firstName) {
        String subject = "您的账户信息已更新";
        String body = String.format("""
            <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>您好，%s</h2>
                <p>您的账户信息已成功更新。</p>
                <p>如果这不是您本人的操作，请立即联系我们的客服团队。</p>
                <p>祝好，<br>XXX 团队</p>
            </body>
            </html>
            """, firstName);

        return sendEmail(to, subject, body);
    }

    /**
     * 发送账号删除通知邮件
     */
    public EmailResponse sendAccountDeletedEmail(String to, String firstName) {
        String subject = "您的账号已删除";
        String body = String.format("""
            <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>您好，%s</h2>
                <p>您的账号已成功删除。</p>
                <p>感谢您使用我们的服务。如有任何问题，请联系客服。</p>
                <p>祝好，<br>XXX 团队</p>
            </body>
            </html>
            """, firstName);

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
// EmailRequest.java
@Data
public class EmailRequest {
    private String to;
    private String firstName;
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
| Frontend | User Service | HTTP REST | 通过 ALB 路由 |
| Frontend | Profile Service | HTTP REST | 通过 ALB 路由 |
| User Service | Profile Service | HTTP REST | 内部 API |
| User Service | Notification Service | HTTP REST | 内部 API (账号删除通知) |
| Profile Service | Notification Service | HTTP REST | 内部 API (账号修改通知) |
| Lambda Trigger | Profile Service | HTTP REST | 内部 API |

### 7.2 内部 API 认证

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

### 7.3 服务间调用客户端

```java
// ProfileServiceClient.java (在 User Service 中)
@Component
@RequiredArgsConstructor
public class ProfileServiceClient {

    private final RestTemplate restTemplate;

    @Value("${services.profile.url}")
    private String profileServiceUrl;

    @Value("${internal.api-key}")
    private String apiKey;

    public void createProfile(CreateProfileRequest request) {
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Internal-Api-Key", apiKey);
        headers.setContentType(MediaType.APPLICATION_JSON);

        HttpEntity<CreateProfileRequest> entity = new HttpEntity<>(request, headers);

        restTemplate.postForEntity(
            profileServiceUrl + "/api/v1/profiles",
            entity,
            Void.class
        );
    }

    public void deleteProfile(String userId) {
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Internal-Api-Key", apiKey);

        HttpEntity<Void> entity = new HttpEntity<>(headers);

        restTemplate.exchange(
            profileServiceUrl + "/api/v1/profiles/" + userId,
            HttpMethod.DELETE,
            entity,
            Void.class
        );
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
          - path: /api/v1/users
            pathType: Prefix
            backend:
              service:
                name: user-service
                port:
                  number: 8080
          - path: /api/v1/profiles
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
┌────────┐     ┌──────────┐     ┌─────────────┐     ┌─────────────┐
│  用户   │     │  Frontend │     │User Service │     │   Cognito   │
└───┬────┘     └─────┬─────┘     └──────┬──────┘     └──────┬──────┘
    │                │                  │                   │
    │ 1.填写注册表单   │                  │                   │
    │───────────────▶│                  │                   │
    │                │                  │                   │
    │                │ 2.POST /register │                   │
    │                │─────────────────▶│                   │
    │                │                  │                   │
    │                │                  │ 3.业务验证         │
    │                │                  │                   │
    │                │                  │ 4.创建用户         │
    │                │                  │──────────────────▶│
    │                │                  │◀──────────────────│
    │                │                  │   userId          │
    │                │                  │                   │
    │                │◀─────────────────│                   │
    │                │   注册成功        │                   │
    │                │                  │                   │
    │◀───────────────│                  │                   │
    │  显示成功页面    │                  │                   │
    │                │                  │                   │
    │                │                  │  5.Cognito 自动发送验证码邮件
    │◀─────────────────────────────────────────────────────│
    │  收到验证码邮件  │                  │                   │
```

### 9.2 用户登录流程

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
  PROFILE_SERVICE_URL: http://profile-service:8080
  NOTIFICATION_SERVICE_URL: http://notification-service:8080
  INTERNAL_API_KEY: ${SECRET}

# Profile Service 配置
profile-service:
  S3_BUCKET: auth-platform-avatars
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
| User Service | 账号注册、删除、管理 | Spring Boot + AWS SDK | EKS |
| Profile Service | 用户资料查看与修改 | Spring Boot + JPA | EKS |
| Notification Service | 账号修改/删除通知 | Spring Boot + SES | EKS |

### 12.2 数据流向

```
用户 ──▶ CloudFront ──▶ S3 (Frontend)
              │
              │ /api/*
              ▼
           ALB ────┬──▶ User Service ──────▶ Cognito
                   │         │
                   │         ├──▶ Profile Service ──▶ Aurora
                   │         │
                   │         └──▶ Notification Service ──▶ SES
                   │
                   ├──▶ Profile Service ──▶ Aurora
                   │
                   └──▶ Notification Service ──▶ SES
```

### 12.3 认证数据 vs 业务数据

| 数据类型 | 存储位置 | 管理方 |
|---------|---------|-------|
| 用户凭证 (密码) | Cognito | Cognito |
| 用户基本属性 (姓名、邮箱) | Cognito | Cognito |
| Token/Session | Cognito | Cognito |
| 用户扩展资料 (地址、电话) | Aurora | Profile Service |
| 邮件发送记录 | Aurora | Notification Service |
