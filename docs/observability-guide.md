# 可观测性实践指南

## 1. 概述

本文档定义了身份认证平台所有微服务的可观测性标准，包括日志（Logging）、指标（Metrics）和追踪（Tracing）的实现规范。所有微服务必须遵循本指南以确保一致性和可维护性。

### 1.1 设计原则

| 原则 | 说明 |
|------|------|
| 结构化 | 所有日志使用 JSON 格式，便于机器解析和查询 |
| 上下文丰富 | 每条日志包含足够的上下文信息（trace_id, user_id 等） |
| 可追踪 | 支持分布式追踪，可跨服务关联请求 |
| 低侵入 | 通过 AOP/Filter 自动采集，减少业务代码污染 |
| 安全 | 敏感信息（密码、token）不记录或脱敏处理 |

### 1.2 技术栈

| 组件 | 技术选型 | 版本 |
|------|---------|------|
| 日志框架 | SLF4J + Logback | Spring Boot 内置 |
| JSON 编码 | logstash-logback-encoder | 7.4+ |
| Metrics | Micrometer + Prometheus | 1.12+ |
| 日志收集 | Fluent Bit | 2.x |
| 日志存储 | CloudWatch Logs / OpenSearch | - |
| 指标存储 | Prometheus / CloudWatch | - |

### 1.3 架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              EKS Cluster                                    │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐              │
│  │  user-service   │  │ profile-service │  │notification-svc │              │
│  │                 │  │                 │  │                 │              │
│  │ ┌─────────────┐ │  │ ┌─────────────┐ │  │ ┌─────────────┐ │              │
│  │ │ App (JSON)  │ │  │ │ App (JSON)  │ │  │ │ App (JSON)  │ │              │
│  │ │   stdout    │ │  │ │   stdout    │ │  │ │   stdout    │ │              │
│  │ └──────┬──────┘ │  │ └──────┬──────┘ │  │ └──────┬──────┘ │              │
│  │        │        │  │        │        │  │        │        │              │
│  │ ┌──────▼──────┐ │  │ ┌──────▼──────┐ │  │ ┌──────▼──────┐ │              │
│  │ │ :8080/metrics│ │  │ │ :8080/metrics│ │  │ │ :8080/metrics│ │            │
│  │ └─────────────┘ │  │ └─────────────┘ │  │ └─────────────┘ │              │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘              │
│           │                    │                    │                       │
│  ┌────────▼────────────────────▼────────────────────▼────────┐              │
│  │                      Fluent Bit (DaemonSet)               │              │
│  │                   收集 stdout JSON 日志                    │              │
│  └────────────────────────────┬──────────────────────────────┘              │
│                               │                                             │
│  ┌────────────────────────────▼──────────────────────────────┐              │
│  │                    Prometheus (Deployment)                 │              │
│  │                     抓取 /actuator/prometheus              │              │
│  └────────────────────────────┬──────────────────────────────┘              │
└───────────────────────────────┼─────────────────────────────────────────────┘
                                │
            ┌───────────────────┼───────────────────┐
            │                   │                   │
            ▼                   ▼                   ▼
    ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
    │CloudWatch Logs│   │  OpenSearch   │   │ Amazon Managed│
    │               │   │  (可选)       │   │  Prometheus   │
    └───────────────┘   └───────────────┘   └───────────────┘
```

---

## 2. 日志（Logging）

### 2.1 依赖配置

在 `pom.xml` 中添加以下依赖：

```xml
<!-- 日志: JSON 格式输出 -->
<dependency>
    <groupId>net.logstash.logback</groupId>
    <artifactId>logstash-logback-encoder</artifactId>
    <version>7.4</version>
</dependency>
```

### 2.2 Logback 配置

创建 `src/main/resources/logback-spring.xml`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration scan="true" scanPeriod="30 seconds">

    <!-- ========================================================================== -->
    <!-- 属性定义                                                                    -->
    <!-- ========================================================================== -->

    <springProperty scope="context" name="APP_NAME" source="spring.application.name" defaultValue="unknown-service"/>
    <springProperty scope="context" name="APP_ENV" source="spring.profiles.active" defaultValue="default"/>

    <!-- 从环境变量获取 (K8s 部署时通过 Downward API 注入) -->
    <property name="LOG_LEVEL" value="${LOG_LEVEL:-INFO}"/>
    <property name="POD_NAME" value="${HOSTNAME:-unknown}"/>
    <property name="POD_NAMESPACE" value="${POD_NAMESPACE:-default}"/>
    <property name="NODE_NAME" value="${NODE_NAME:-unknown}"/>

    <!-- ========================================================================== -->
    <!-- JSON Console Appender (生产环境)                                            -->
    <!-- ========================================================================== -->

    <appender name="JSON_CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder class="net.logstash.logback.encoder.LogstashEncoder">
            <!-- 时间戳格式: ISO8601 -->
            <timestampPattern>yyyy-MM-dd'T'HH:mm:ss.SSSXXX</timestampPattern>

            <!-- 字段名称映射 -->
            <fieldNames>
                <timestamp>timestamp</timestamp>
                <version>[ignore]</version>
                <message>message</message>
                <logger>logger</logger>
                <thread>thread</thread>
                <level>level</level>
                <levelValue>[ignore]</levelValue>
                <stackTrace>stack_trace</stackTrace>
            </fieldNames>

            <!-- 静态字段 -->
            <customFields>
                {"service":"${APP_NAME}","environment":"${APP_ENV}","pod_name":"${POD_NAME}","pod_namespace":"${POD_NAMESPACE}","node_name":"${NODE_NAME}"}
            </customFields>

            <!-- MDC 字段 -->
            <includeMdcKeyName>trace_id</includeMdcKeyName>
            <includeMdcKeyName>span_id</includeMdcKeyName>
            <includeMdcKeyName>user_id</includeMdcKeyName>
            <includeMdcKeyName>request_id</includeMdcKeyName>
            <includeMdcKeyName>client_ip</includeMdcKeyName>
            <includeMdcKeyName>request_method</includeMdcKeyName>
            <includeMdcKeyName>request_uri</includeMdcKeyName>
            <includeMdcKeyName>response_status</includeMdcKeyName>
            <includeMdcKeyName>response_time_ms</includeMdcKeyName>
            <includeMdcKeyName>event_type</includeMdcKeyName>
            <includeMdcKeyName>event_name</includeMdcKeyName>

            <!-- 异常处理 -->
            <throwableConverter class="net.logstash.logback.stacktrace.ShortenedThrowableConverter">
                <maxDepthPerThrowable>30</maxDepthPerThrowable>
                <maxLength>2048</maxLength>
                <shortenedClassNameLength>20</shortenedClassNameLength>
                <rootCauseFirst>true</rootCauseFirst>
                <inlineHash>true</inlineHash>
            </throwableConverter>
        </encoder>
    </appender>

    <!-- ========================================================================== -->
    <!-- 可读格式 Console Appender (开发环境)                                        -->
    <!-- ========================================================================== -->

    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{yyyy-MM-dd HH:mm:ss.SSS} %highlight(%-5level) [%thread] [%X{trace_id:-}] [%X{user_id:-}] %cyan(%logger{36}) - %msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <!-- ========================================================================== -->
    <!-- 异步 Appender                                                              -->
    <!-- ========================================================================== -->

    <appender name="ASYNC_JSON" class="ch.qos.logback.classic.AsyncAppender">
        <queueSize>512</queueSize>
        <discardingThreshold>0</discardingThreshold>
        <includeCallerData>true</includeCallerData>
        <neverBlock>false</neverBlock>
        <appender-ref ref="JSON_CONSOLE"/>
    </appender>

    <!-- ========================================================================== -->
    <!-- Logger 配置                                                                 -->
    <!-- ========================================================================== -->

    <!-- 应用日志 -->
    <logger name="com.authplatform" level="${LOG_LEVEL}" additivity="false">
        <springProfile name="local,dev">
            <appender-ref ref="CONSOLE"/>
        </springProfile>
        <springProfile name="!local &amp; !dev">
            <appender-ref ref="ASYNC_JSON"/>
        </springProfile>
    </logger>

    <!-- 框架日志 -->
    <logger name="org.springframework" level="INFO"/>
    <logger name="org.springframework.security" level="INFO"/>
    <logger name="org.hibernate" level="WARN"/>
    <logger name="com.zaxxer.hikari" level="INFO"/>

    <!-- ========================================================================== -->
    <!-- Root Logger                                                                 -->
    <!-- ========================================================================== -->

    <root level="INFO">
        <springProfile name="local,dev">
            <appender-ref ref="CONSOLE"/>
        </springProfile>
        <springProfile name="!local &amp; !dev">
            <appender-ref ref="ASYNC_JSON"/>
        </springProfile>
    </root>

</configuration>
```

### 2.3 请求日志过滤器

创建 `src/main/java/com/authplatform/{service}/logging/LoggingFilter.java`：

```java
package com.authplatform.userservice.logging;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.util.ContentCachingRequestWrapper;
import org.springframework.web.util.ContentCachingResponseWrapper;

import java.io.IOException;
import java.util.UUID;

/**
 * HTTP 请求日志过滤器
 *
 * 功能:
 * - 为每个请求生成/提取 trace_id
 * - 记录请求开始和结束日志
 * - 将关键信息放入 MDC
 * - 计算请求处理时间
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
@Slf4j
public class LoggingFilter extends OncePerRequestFilter {

    private static final String TRACE_ID = "trace_id";
    private static final String SPAN_ID = "span_id";
    private static final String REQUEST_ID = "request_id";
    private static final String USER_ID = "user_id";
    private static final String CLIENT_IP = "client_ip";
    private static final String REQUEST_METHOD = "request_method";
    private static final String REQUEST_URI = "request_uri";
    private static final String RESPONSE_STATUS = "response_status";
    private static final String RESPONSE_TIME_MS = "response_time_ms";

    // Trace header 优先级列表
    private static final String[] TRACE_HEADERS = {
        "X-Request-ID",
        "X-Trace-ID",
        "X-Correlation-ID",
        "X-Amzn-Trace-Id"  // AWS ALB/CloudFront
    };

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {

        // 跳过健康检查
        if (shouldSkip(request)) {
            filterChain.doFilter(request, response);
            return;
        }

        long startTime = System.currentTimeMillis();
        setupMDC(request);

        ContentCachingRequestWrapper wrappedRequest = new ContentCachingRequestWrapper(request);
        ContentCachingResponseWrapper wrappedResponse = new ContentCachingResponseWrapper(response);

        try {
            logRequestStart(wrappedRequest);
            filterChain.doFilter(wrappedRequest, wrappedResponse);
            updateUserContext();
        } finally {
            long duration = System.currentTimeMillis() - startTime;
            MDC.put(RESPONSE_STATUS, String.valueOf(wrappedResponse.getStatus()));
            MDC.put(RESPONSE_TIME_MS, String.valueOf(duration));
            logRequestEnd(wrappedRequest, wrappedResponse, duration);
            wrappedResponse.copyBodyToResponse();
            MDC.clear();
        }
    }

    private boolean shouldSkip(HttpServletRequest request) {
        String uri = request.getRequestURI();
        return uri.contains("/actuator/health")
            || uri.contains("/actuator/prometheus")
            || uri.contains("/favicon.ico");
    }

    private void setupMDC(HttpServletRequest request) {
        MDC.put(TRACE_ID, getTraceId(request));
        MDC.put(SPAN_ID, UUID.randomUUID().toString().substring(0, 8));
        MDC.put(REQUEST_ID, UUID.randomUUID().toString());
        MDC.put(CLIENT_IP, getClientIP(request));
        MDC.put(REQUEST_METHOD, request.getMethod());
        MDC.put(REQUEST_URI, request.getRequestURI());
    }

    private String getTraceId(HttpServletRequest request) {
        for (String header : TRACE_HEADERS) {
            String value = request.getHeader(header);
            if (value != null && !value.isEmpty()) {
                if (header.equals("X-Amzn-Trace-Id") && value.contains("Root=")) {
                    return extractAwsTraceId(value);
                }
                return value;
            }
        }
        return UUID.randomUUID().toString().replace("-", "");
    }

    private String extractAwsTraceId(String amznTraceId) {
        for (String part : amznTraceId.split(";")) {
            if (part.startsWith("Root=")) {
                return part.substring(5);
            }
        }
        return amznTraceId;
    }

    private String getClientIP(HttpServletRequest request) {
        String[] headers = {"X-Forwarded-For", "X-Real-IP", "Proxy-Client-IP"};
        for (String header : headers) {
            String ip = request.getHeader(header);
            if (ip != null && !ip.isEmpty() && !"unknown".equalsIgnoreCase(ip)) {
                return ip.split(",")[0].trim();
            }
        }
        return request.getRemoteAddr();
    }

    private void updateUserContext() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth != null && auth.getPrincipal() instanceof Jwt jwt) {
            MDC.put(USER_ID, jwt.getSubject());
        }
    }

    private void logRequestStart(ContentCachingRequestWrapper request) {
        String queryString = request.getQueryString();
        String fullPath = queryString != null
            ? request.getRequestURI() + "?" + queryString
            : request.getRequestURI();
        log.info("Request started: {} {}", request.getMethod(), fullPath);
    }

    private void logRequestEnd(ContentCachingRequestWrapper request,
                               ContentCachingResponseWrapper response,
                               long duration) {
        int status = response.getStatus();
        String msg = String.format("Request completed: %s %s - %d (%dms)",
            request.getMethod(), request.getRequestURI(), status, duration);

        if (status >= 500) {
            log.error(msg);
        } else if (status >= 400) {
            log.warn(msg);
        } else {
            log.info(msg);
        }
    }
}
```

### 2.4 业务事件日志工具

创建 `src/main/java/com/authplatform/{service}/logging/LogEvent.java`：

```java
package com.authplatform.userservice.logging;

import lombok.extern.slf4j.Slf4j;
import org.slf4j.MDC;

import java.util.Map;

/**
 * 结构化日志事件工具类
 *
 * 使用示例:
 * <pre>
 * LogEvent.audit("USER_CREATED")
 *     .with("user_id", userId)
 *     .with("email", email)
 *     .info("New user registered");
 *
 * LogEvent.security("LOGIN_FAILED")
 *     .with("reason", "invalid_password")
 *     .warn("Login attempt failed");
 * </pre>
 */
@Slf4j
public class LogEvent {

    public static final String TYPE_BUSINESS = "BUSINESS";
    public static final String TYPE_AUDIT = "AUDIT";
    public static final String TYPE_SECURITY = "SECURITY";
    public static final String TYPE_PERFORMANCE = "PERFORMANCE";
    public static final String TYPE_INTEGRATION = "INTEGRATION";

    /** 业务事件 */
    public static LogEventBuilder business(String eventName) {
        return new LogEventBuilder(TYPE_BUSINESS, eventName);
    }

    /** 审计事件 (用户操作记录) */
    public static LogEventBuilder audit(String eventName) {
        return new LogEventBuilder(TYPE_AUDIT, eventName);
    }

    /** 安全事件 */
    public static LogEventBuilder security(String eventName) {
        return new LogEventBuilder(TYPE_SECURITY, eventName);
    }

    /** 性能事件 */
    public static LogEventBuilder performance(String eventName) {
        return new LogEventBuilder(TYPE_PERFORMANCE, eventName);
    }

    /** 集成事件 (外部服务调用) */
    public static LogEventBuilder integration(String eventName) {
        return new LogEventBuilder(TYPE_INTEGRATION, eventName);
    }

    public static class LogEventBuilder {
        private final String eventType;
        private final String eventName;

        LogEventBuilder(String eventType, String eventName) {
            this.eventType = eventType;
            this.eventName = eventName;
        }

        public LogEventBuilder with(String key, Object value) {
            if (value != null) {
                MDC.put(key, String.valueOf(value));
            }
            return this;
        }

        public LogEventBuilder withAll(Map<String, Object> fields) {
            if (fields != null) {
                fields.forEach((k, v) -> {
                    if (v != null) MDC.put(k, String.valueOf(v));
                });
            }
            return this;
        }

        public void debug(String message) {
            logWithContext(() -> log.debug(formatMessage(message)));
        }

        public void info(String message) {
            logWithContext(() -> log.info(formatMessage(message)));
        }

        public void warn(String message) {
            logWithContext(() -> log.warn(formatMessage(message)));
        }

        public void warn(String message, Throwable throwable) {
            logWithContext(() -> log.warn(formatMessage(message), throwable));
        }

        public void error(String message) {
            logWithContext(() -> log.error(formatMessage(message)));
        }

        public void error(String message, Throwable throwable) {
            logWithContext(() -> log.error(formatMessage(message), throwable));
        }

        private String formatMessage(String message) {
            return String.format("[%s] %s", eventName, message);
        }

        private void logWithContext(Runnable logAction) {
            MDC.put("event_type", eventType);
            MDC.put("event_name", eventName);
            try {
                logAction.run();
            } finally {
                MDC.remove("event_type");
                MDC.remove("event_name");
            }
        }
    }
}
```

### 2.5 使用示例

```java
// Service 层使用示例
@Service
@Slf4j
public class UserService {

    public void createUser(String userId, String email) {
        // 普通日志
        log.debug("Creating user: {}", userId);

        // 业务操作完成后记录审计日志
        LogEvent.audit("USER_CREATED")
            .with("target_user_id", userId)
            .with("email", maskEmail(email))
            .info("New user created");
    }

    public void updateProfile(String userId, List<String> fields) {
        LogEvent.audit("PROFILE_UPDATED")
            .with("target_user_id", userId)
            .with("updated_fields", String.join(",", fields))
            .info("User profile updated");
    }

    // 调用外部服务时
    public void callCognito(String operation) {
        long start = System.currentTimeMillis();
        try {
            // 调用 Cognito...
            LogEvent.integration("COGNITO_CALL")
                .with("operation", operation)
                .with("duration_ms", System.currentTimeMillis() - start)
                .info("Cognito call succeeded");
        } catch (Exception e) {
            LogEvent.integration("COGNITO_CALL_FAILED")
                .with("operation", operation)
                .with("error_type", e.getClass().getSimpleName())
                .error("Cognito call failed", e);
            throw e;
        }
    }

    private String maskEmail(String email) {
        if (email == null || !email.contains("@")) return "***";
        int at = email.indexOf("@");
        return (at <= 3 ? "***" : email.substring(0, 3) + "***") + email.substring(at);
    }
}
```

### 2.6 日志字段规范

#### 必须字段

| 字段 | 说明 | 来源 |
|------|------|------|
| timestamp | ISO8601 时间戳 | 自动 |
| level | 日志级别 | 自动 |
| logger | Logger 名称 | 自动 |
| message | 日志消息 | 代码 |
| service | 服务名称 | 配置 |
| environment | 环境 | 配置 |
| trace_id | 追踪 ID | Filter |

#### 请求相关字段

| 字段 | 说明 |
|------|------|
| request_id | 请求唯一 ID |
| user_id | 当前用户 ID |
| client_ip | 客户端 IP |
| request_method | HTTP 方法 |
| request_uri | 请求 URI |
| response_status | 响应状态码 |
| response_time_ms | 处理时间 (ms) |

#### 事件相关字段

| 字段 | 说明 |
|------|------|
| event_type | 事件类型 (AUDIT/SECURITY/...) |
| event_name | 事件名称 (USER_CREATED/...) |
| target_user_id | 操作目标用户 |
| updated_fields | 更新的字段列表 |

### 2.7 事件命名规范

| 类型 | 命名模式 | 示例 |
|------|---------|------|
| AUDIT | `{RESOURCE}_{ACTION}` | USER_CREATED, PROFILE_UPDATED, ACCOUNT_DELETED |
| SECURITY | `{ACTION}_{STATUS}` | LOGIN_FAILED, ACCESS_DENIED, TOKEN_EXPIRED |
| BUSINESS | `{RESOURCE}_{STATUS}` | USER_NOT_FOUND, VALIDATION_ERROR |
| INTEGRATION | `{SERVICE}_{ACTION}` | COGNITO_CALL, SES_SEND_EMAIL |
| PERFORMANCE | `{OPERATION}_{METRIC}` | DB_QUERY_SLOW, API_TIMEOUT |

---

## 3. 指标（Metrics）

### 3.1 依赖配置

```xml
<!-- Actuator -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<!-- Prometheus -->
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
```

### 3.2 Application 配置

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus,loggers
      base-path: /actuator
  endpoint:
    health:
      show-details: when-authorized
      probes:
        enabled: true
    loggers:
      enabled: true
    prometheus:
      enabled: true
  health:
    livenessState:
      enabled: true
    readinessState:
      enabled: true
  metrics:
    tags:
      application: ${spring.application.name}
      environment: ${ENVIRONMENT:local}
    export:
      prometheus:
        enabled: true
    distribution:
      percentiles-histogram:
        http.server.requests: true
        auth.external.call.duration: true
      percentiles:
        http.server.requests: 0.5, 0.95, 0.99
        auth.external.call.duration: 0.5, 0.95, 0.99
```

### 3.3 客户端信息 DTO

创建 `src/main/java/com/authplatform/{service}/dto/ClientInfo.java`：

```java
package com.authplatform.userservice.dto;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 客户端信息 DTO
 * 用于追踪用户来源渠道和设备信息
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ClientInfo {

    /** 触点渠道: website, wechat, app_ios, app_android, admin */
    private String channel;

    /** 设备类型: desktop, mobile, tablet */
    private String device;

    /** 操作系统/平台: windows, macos, linux, ios, android */
    private String platform;

    /** 应用版本号 (App 场景) */
    private String appVersion;

    // 渠道常量
    public static final String CHANNEL_WEBSITE = "website";
    public static final String CHANNEL_WECHAT = "wechat";
    public static final String CHANNEL_APP_IOS = "app_ios";
    public static final String CHANNEL_APP_ANDROID = "app_android";
    public static final String CHANNEL_ADMIN = "admin";
    public static final String CHANNEL_UNKNOWN = "unknown";

    // 设备常量
    public static final String DEVICE_DESKTOP = "desktop";
    public static final String DEVICE_MOBILE = "mobile";
    public static final String DEVICE_TABLET = "tablet";
    public static final String DEVICE_UNKNOWN = "unknown";

    // 平台常量
    public static final String PLATFORM_WINDOWS = "windows";
    public static final String PLATFORM_MACOS = "macos";
    public static final String PLATFORM_LINUX = "linux";
    public static final String PLATFORM_IOS = "ios";
    public static final String PLATFORM_ANDROID = "android";
    public static final String PLATFORM_UNKNOWN = "unknown";

    /**
     * 获取安全的 channel 值（用于 metrics 标签）
     */
    public String getSafeChannel() {
        if (channel == null || channel.isBlank()) {
            return CHANNEL_UNKNOWN;
        }
        return switch (channel.toLowerCase()) {
            case "website", "web" -> CHANNEL_WEBSITE;
            case "wechat", "weixin", "wx" -> CHANNEL_WECHAT;
            case "app_ios", "ios" -> CHANNEL_APP_IOS;
            case "app_android", "android" -> CHANNEL_APP_ANDROID;
            case "admin", "backend" -> CHANNEL_ADMIN;
            default -> CHANNEL_UNKNOWN;
        };
    }

    /**
     * 获取安全的 device 值（用于 metrics 标签）
     */
    public String getSafeDevice() {
        if (device == null || device.isBlank()) {
            return DEVICE_UNKNOWN;
        }
        return switch (device.toLowerCase()) {
            case "desktop", "pc" -> DEVICE_DESKTOP;
            case "mobile", "phone" -> DEVICE_MOBILE;
            case "tablet", "pad" -> DEVICE_TABLET;
            default -> DEVICE_UNKNOWN;
        };
    }

    /**
     * 获取安全的 platform 值（用于 metrics 标签）
     */
    public String getSafePlatform() {
        if (platform == null || platform.isBlank()) {
            return PLATFORM_UNKNOWN;
        }
        return switch (platform.toLowerCase()) {
            case "windows", "win" -> PLATFORM_WINDOWS;
            case "macos", "mac", "osx" -> PLATFORM_MACOS;
            case "linux" -> PLATFORM_LINUX;
            case "ios", "iphone", "ipad" -> PLATFORM_IOS;
            case "android" -> PLATFORM_ANDROID;
            default -> PLATFORM_UNKNOWN;
        };
    }

    /**
     * 创建默认的未知客户端信息
     */
    public static ClientInfo unknown() {
        return ClientInfo.builder()
                .channel(CHANNEL_UNKNOWN)
                .device(DEVICE_UNKNOWN)
                .platform(PLATFORM_UNKNOWN)
                .build();
    }
}
```

### 3.4 客户端信息解析器

创建 `src/main/java/com/authplatform/{service}/metrics/ClientInfoResolver.java`：

```java
package com.authplatform.userservice.metrics;

import com.authplatform.userservice.dto.ClientInfo;
import jakarta.servlet.http.HttpServletRequest;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

/**
 * 客户端信息解析器
 * 从 HTTP 请求头中提取客户端信息
 *
 * 支持的请求头:
 * - X-Client-Channel: website | wechat | app_ios | app_android | admin
 * - X-Client-Device: desktop | mobile | tablet
 * - X-Client-Platform: windows | macos | linux | ios | android
 * - X-App-Version: 应用版本号
 *
 * 也支持从 User-Agent 自动推断设备和平台信息
 */
@Component
@Slf4j
public class ClientInfoResolver {

    public static final String HEADER_CHANNEL = "X-Client-Channel";
    public static final String HEADER_DEVICE = "X-Client-Device";
    public static final String HEADER_PLATFORM = "X-Client-Platform";
    public static final String HEADER_APP_VERSION = "X-App-Version";

    /**
     * 从当前请求上下文解析客户端信息
     */
    public ClientInfo resolve() {
        ServletRequestAttributes attrs = (ServletRequestAttributes) RequestContextHolder.getRequestAttributes();
        if (attrs == null) {
            return ClientInfo.unknown();
        }
        return resolve(attrs.getRequest());
    }

    /**
     * 从 HTTP 请求解析客户端信息
     */
    public ClientInfo resolve(HttpServletRequest request) {
        if (request == null) {
            return ClientInfo.unknown();
        }

        // 优先从自定义 Header 获取
        String channel = request.getHeader(HEADER_CHANNEL);
        String device = request.getHeader(HEADER_DEVICE);
        String platform = request.getHeader(HEADER_PLATFORM);
        String appVersion = request.getHeader(HEADER_APP_VERSION);

        // 如果没有自定义 Header，尝试从 User-Agent 推断
        String userAgent = request.getHeader("User-Agent");
        if (userAgent != null && !userAgent.isBlank()) {
            if (device == null || device.isBlank()) {
                device = inferDeviceFromUserAgent(userAgent);
            }
            if (platform == null || platform.isBlank()) {
                platform = inferPlatformFromUserAgent(userAgent);
            }
            if (channel == null || channel.isBlank()) {
                channel = inferChannelFromUserAgent(userAgent, request);
            }
        }

        return ClientInfo.builder()
                .channel(channel)
                .device(device)
                .platform(platform)
                .appVersion(appVersion)
                .build();
    }

    private String inferDeviceFromUserAgent(String userAgent) {
        String ua = userAgent.toLowerCase();
        if (ua.contains("ipad") || ua.contains("tablet") ||
            (ua.contains("android") && !ua.contains("mobile"))) {
            return ClientInfo.DEVICE_TABLET;
        }
        if (ua.contains("mobile") || ua.contains("iphone") ||
            ua.contains("android") || ua.contains("phone")) {
            return ClientInfo.DEVICE_MOBILE;
        }
        return ClientInfo.DEVICE_DESKTOP;
    }

    private String inferPlatformFromUserAgent(String userAgent) {
        String ua = userAgent.toLowerCase();
        if (ua.contains("iphone") || ua.contains("ipad") || ua.contains("ios")) {
            return ClientInfo.PLATFORM_IOS;
        }
        if (ua.contains("android")) {
            return ClientInfo.PLATFORM_ANDROID;
        }
        if (ua.contains("windows")) {
            return ClientInfo.PLATFORM_WINDOWS;
        }
        if (ua.contains("macintosh") || ua.contains("mac os")) {
            return ClientInfo.PLATFORM_MACOS;
        }
        if (ua.contains("linux") && !ua.contains("android")) {
            return ClientInfo.PLATFORM_LINUX;
        }
        return ClientInfo.PLATFORM_UNKNOWN;
    }

    private String inferChannelFromUserAgent(String userAgent, HttpServletRequest request) {
        String ua = userAgent.toLowerCase();
        if (ua.contains("micromessenger") || ua.contains("wechat")) {
            return ClientInfo.CHANNEL_WECHAT;
        }
        if (ua.contains("authplatform-ios") || ua.contains("authplatform/ios")) {
            return ClientInfo.CHANNEL_APP_IOS;
        }
        if (ua.contains("authplatform-android") || ua.contains("authplatform/android")) {
            return ClientInfo.CHANNEL_APP_ANDROID;
        }
        return ClientInfo.CHANNEL_WEBSITE;
    }
}
```

### 3.5 业务指标管理器

创建 `src/main/java/com/authplatform/{service}/metrics/BusinessMetrics.java`：

```java
package com.authplatform.userservice.metrics;

import com.authplatform.userservice.dto.ClientInfo;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import jakarta.annotation.PostConstruct;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

/**
 * 业务指标管理器
 *
 * 提供以下指标:
 * - auth_user_created_total: 用户创建计数（按渠道、设备、平台分组）
 * - auth_user_deleted_total: 用户删除计数（按原因分组）
 * - auth_user_synced_total: 用户同步计数
 * - auth_profile_updated_total: 资料更新计数（按字段分组）
 * - auth_profile_fetched_total: 资料查询计数
 * - auth_errors_total: 错误计数（按类型、状态码分组）
 * - auth_external_call_duration_seconds: 外部服务调用耗时
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class BusinessMetrics {

    private final MeterRegistry meterRegistry;

    // 指标名称常量
    private static final String METRIC_USER_CREATED = "auth_user_created";
    private static final String METRIC_USER_DELETED = "auth_user_deleted";
    private static final String METRIC_USER_SYNCED = "auth_user_synced";
    private static final String METRIC_PROFILE_UPDATED = "auth_profile_updated";
    private static final String METRIC_PROFILE_FETCHED = "auth_profile_fetched";
    private static final String METRIC_ERRORS = "auth_errors";
    private static final String METRIC_EXTERNAL_CALL = "auth_external_call_duration";

    // 标签名称常量
    private static final String TAG_CHANNEL = "channel";
    private static final String TAG_DEVICE = "device";
    private static final String TAG_PLATFORM = "platform";
    private static final String TAG_REASON = "reason";
    private static final String TAG_FIELD = "field";
    private static final String TAG_ERROR_TYPE = "error_type";
    private static final String TAG_STATUS_CODE = "status_code";
    private static final String TAG_SERVICE = "service";
    private static final String TAG_OPERATION = "operation";
    private static final String TAG_SUCCESS = "success";

    // 缓存 Counter 避免重复创建
    private final ConcurrentHashMap<String, Counter> counterCache = new ConcurrentHashMap<>();

    // 基础计数器
    private Counter userSyncedCounter;
    private Counter profileFetchedCounter;

    // 删除原因常量
    public static final String DELETE_REASON_USER_REQUEST = "user_request";
    public static final String DELETE_REASON_ADMIN_ACTION = "admin_action";
    public static final String DELETE_REASON_POLICY_VIOLATION = "policy_violation";
    public static final String DELETE_REASON_INACTIVE = "inactive";

    @PostConstruct
    public void init() {
        userSyncedCounter = Counter.builder(METRIC_USER_SYNCED + "_total")
                .description("Total number of user sync operations from Cognito")
                .register(meterRegistry);

        profileFetchedCounter = Counter.builder(METRIC_PROFILE_FETCHED + "_total")
                .description("Total number of profile fetch operations")
                .register(meterRegistry);

        log.info("Business metrics initialized");
    }

    /**
     * 记录用户创建（带渠道、设备、平台标签）
     */
    public void incrementUserCreated(ClientInfo clientInfo) {
        if (clientInfo == null) {
            clientInfo = ClientInfo.unknown();
        }

        String channel = clientInfo.getSafeChannel();
        String device = clientInfo.getSafeDevice();
        String platform = clientInfo.getSafePlatform();

        String cacheKey = String.format("user_created_%s_%s_%s", channel, device, platform);

        Counter counter = counterCache.computeIfAbsent(cacheKey, k ->
                Counter.builder(METRIC_USER_CREATED + "_total")
                        .description("Total number of users created")
                        .tag(TAG_CHANNEL, channel)
                        .tag(TAG_DEVICE, device)
                        .tag(TAG_PLATFORM, platform)
                        .register(meterRegistry)
        );

        counter.increment();
    }

    /**
     * 记录用户删除（带原因标签）
     */
    public void incrementUserDeleted(String reason) {
        if (reason == null || reason.isBlank()) {
            reason = "unknown";
        }

        String cacheKey = "user_deleted_" + reason;

        Counter counter = counterCache.computeIfAbsent(cacheKey, k ->
                Counter.builder(METRIC_USER_DELETED + "_total")
                        .description("Total number of users deleted")
                        .tag(TAG_REASON, reason)
                        .register(meterRegistry)
        );

        counter.increment();
    }

    /**
     * 记录用户同步
     */
    public void incrementUserSynced() {
        userSyncedCounter.increment();
    }

    /**
     * 记录资料更新（按字段分组）
     */
    public void incrementProfileUpdated(String field) {
        if (field == null || field.isBlank()) {
            field = "unknown";
        }

        String cacheKey = "profile_updated_" + field;

        Counter counter = counterCache.computeIfAbsent(cacheKey, k ->
                Counter.builder(METRIC_PROFILE_UPDATED + "_total")
                        .description("Total number of profile update operations")
                        .tag(TAG_FIELD, field)
                        .register(meterRegistry)
        );

        counter.increment();
    }

    /**
     * 批量记录资料更新（多个字段）
     */
    public void incrementProfileUpdated(String[] fields) {
        if (fields == null || fields.length == 0) {
            return;
        }
        for (String field : fields) {
            incrementProfileUpdated(field.trim());
        }
    }

    /**
     * 记录资料查询
     */
    public void incrementProfileFetched() {
        profileFetchedCounter.increment();
    }

    /**
     * 记录错误（按类型和状态码分组）
     */
    public void incrementError(String errorType, int statusCode) {
        String cacheKey = String.format("error_%s_%d", errorType, statusCode);

        Counter counter = counterCache.computeIfAbsent(cacheKey, k ->
                Counter.builder(METRIC_ERRORS + "_total")
                        .description("Total number of errors")
                        .tag(TAG_ERROR_TYPE, errorType)
                        .tag(TAG_STATUS_CODE, String.valueOf(statusCode))
                        .register(meterRegistry)
        );

        counter.increment();
    }

    /**
     * 开始计时外部服务调用
     */
    public Timer.Sample startExternalCall() {
        return Timer.start(meterRegistry);
    }

    /**
     * 记录外部服务调用完成
     */
    public void recordExternalCall(Timer.Sample sample, String service, String operation, boolean success) {
        Timer timer = Timer.builder(METRIC_EXTERNAL_CALL + "_seconds")
                .description("External service call duration in seconds")
                .tag(TAG_SERVICE, service)
                .tag(TAG_OPERATION, operation)
                .tag(TAG_SUCCESS, String.valueOf(success))
                .register(meterRegistry);

        sample.stop(timer);
    }

    /**
     * 简便方法：记录外部调用耗时（毫秒）
     */
    public void recordExternalCallDuration(String service, String operation, boolean success, long durationMs) {
        Timer timer = Timer.builder(METRIC_EXTERNAL_CALL + "_seconds")
                .description("External service call duration in seconds")
                .tag(TAG_SERVICE, service)
                .tag(TAG_OPERATION, operation)
                .tag(TAG_SUCCESS, String.valueOf(success))
                .register(meterRegistry);

        timer.record(durationMs, TimeUnit.MILLISECONDS);
    }
}
```

### 3.6 user-service 指标清单

| 指标名称 | 类型 | 标签 | 说明 |
|---------|------|------|------|
| `auth_user_created_total` | Counter | channel, device, platform | 用户创建数 |
| `auth_user_deleted_total` | Counter | reason | 用户删除数 |
| `auth_user_synced_total` | Counter | - | 用户信息同步数（从 Cognito） |
| `auth_profile_updated_total` | Counter | field | 资料更新数（按字段） |
| `auth_profile_fetched_total` | Counter | - | 资料查询数 |
| `auth_errors_total` | Counter | error_type, status_code | 错误计数 |
| `auth_external_call_duration_seconds` | Timer | service, operation, success | 外部服务调用耗时 |

#### 标签值说明

**channel（触点渠道）:**
- `website` - 官网
- `wechat` - 微信公众号/小程序
- `app_ios` - iOS App
- `app_android` - Android App
- `admin` - 管理后台
- `unknown` - 未知

**device（设备类型）:**
- `desktop` - 桌面端
- `mobile` - 移动端
- `tablet` - 平板
- `unknown` - 未知

**platform（操作系统）:**
- `windows`, `macos`, `linux`, `ios`, `android`, `unknown`

**reason（删除原因）:**
- `user_request` - 用户主动注销
- `admin_action` - 管理员操作
- `policy_violation` - 违反政策
- `inactive` - 长期不活跃

**error_type（错误类型）:**
- `ResourceNotFound` - 资源不存在
- `ValidationError` - 参数校验失败
- `AccessDenied` - 访问被拒绝
- `AuthenticationFailed` - 认证失败
- `UnexpectedError` - 未知错误

### 3.7 Prometheus 抓取配置

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'auth-platform'
    kubernetes_sd_configs:
      - role: pod
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        regex: (user-service|notification-service|...)
        action: keep
      - source_labels: [__meta_kubernetes_namespace]
        action: replace
        target_label: namespace
      - source_labels: [__meta_kubernetes_pod_name]
        action: replace
        target_label: pod
    metrics_path: /api/actuator/prometheus
    scheme: http
```

### 3.8 Grafana Dashboard 查询示例

```promql
# 新用户注册趋势（按渠道）
sum(rate(auth_user_created_total[5m])) by (channel)

# 用户删除趋势（按原因）
sum(rate(auth_user_deleted_total[5m])) by (reason)

# 错误率
sum(rate(auth_errors_total[5m])) by (error_type, status_code)

# 资料更新热度（按字段）
topk(5, sum(rate(auth_profile_updated_total[1h])) by (field))

# 外部服务调用成功率
sum(rate(auth_external_call_duration_seconds_count{success="true"}[5m]))
/
sum(rate(auth_external_call_duration_seconds_count[5m]))

# 外部服务调用 P99 延迟
histogram_quantile(0.99, sum(rate(auth_external_call_duration_seconds_bucket[5m])) by (le, service))
```

### 3.9 前端请求头规范

前端应用在调用 API 时需要设置以下请求头，以便服务端正确记录用户来源：

```javascript
// 示例: React 前端
const headers = {
  'X-Client-Channel': 'website',  // 或 'wechat', 'app_ios', 'app_android'
  'X-Client-Device': 'desktop',   // 或 'mobile', 'tablet'
  'X-Client-Platform': 'windows', // 或 'macos', 'linux', 'ios', 'android'
  'X-App-Version': '1.0.0',       // 可选，App 场景使用
};

fetch('/api/users/me', {
  headers: {
    ...headers,
    'Authorization': `Bearer ${token}`
  }
});
```

**注意**: 如果前端未设置这些请求头，服务端会尝试从 User-Agent 自动推断设备和平台信息。

---

## 4. Kubernetes 部署配置

### 4.1 环境变量注入

```yaml
# deployment.yaml
spec:
  template:
    spec:
      containers:
        - name: user-service
          env:
            # 日志级别
            - name: LOG_LEVEL
              value: "INFO"
            # Spring Profile
            - name: SPRING_PROFILES_ACTIVE
              value: "production"
            # Pod 信息 (Downward API)
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
            - name: POD_NAMESPACE
              valueFrom:
                fieldRef:
                  fieldPath: metadata.namespace
            - name: NODE_NAME
              valueFrom:
                fieldRef:
                  fieldPath: spec.nodeName
```

### 4.2 Fluent Bit 配置

```yaml
# fluent-bit-configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: fluent-bit-config
data:
  fluent-bit.conf: |
    [SERVICE]
        Flush         1
        Log_Level     info
        Parsers_File  parsers.conf

    [INPUT]
        Name              tail
        Tag               kube.*
        Path              /var/log/containers/*auth-platform*.log
        Parser            docker
        Refresh_Interval  5
        Mem_Buf_Limit     5MB

    [FILTER]
        Name         kubernetes
        Match        kube.*
        Merge_Log    On
        K8S-Logging.Parser  On

    [OUTPUT]
        Name                  cloudwatch_logs
        Match                 *
        region                ap-northeast-1
        log_group_name        /aws/eks/auth-platform/application
        log_stream_prefix     ${POD_NAME}-
        auto_create_group     true
```

---

## 5. CloudWatch Logs Insights 查询

### 5.1 常用查询

```sql
-- 查询特定用户的所有操作
fields @timestamp, level, message, event_name, updated_fields
| filter user_id = "USER_ID_HERE"
| sort @timestamp desc
| limit 100

-- 查询所有错误
fields @timestamp, message, error_type, stack_trace, trace_id
| filter level = "ERROR"
| sort @timestamp desc
| limit 50

-- API 响应时间统计
fields request_uri, response_time_ms
| filter ispresent(response_time_ms)
| stats avg(response_time_ms) as avg_ms,
        max(response_time_ms) as max_ms,
        count() as count
  by request_uri
| sort avg_ms desc

-- 慢请求 (>500ms)
fields @timestamp, request_method, request_uri, response_time_ms, user_id
| filter response_time_ms > 500
| sort response_time_ms desc

-- 按 trace_id 追踪请求
fields @timestamp, level, logger, message
| filter trace_id = "TRACE_ID_HERE"
| sort @timestamp asc

-- 审计日志查询
fields @timestamp, event_name, target_user_id, updated_fields
| filter event_type = "AUDIT"
| sort @timestamp desc
| limit 100

-- 安全事件查询
fields @timestamp, event_name, user_id, client_ip, message
| filter event_type = "SECURITY"
| sort @timestamp desc
```

---

## 6. 新服务接入检查清单

创建新微服务时，请确保完成以下检查项：

### 6.1 依赖

- [ ] 添加 `logstash-logback-encoder` 依赖
- [ ] 添加 `spring-boot-starter-actuator` 依赖
- [ ] 添加 `micrometer-registry-prometheus` 依赖

### 6.2 配置文件

- [ ] 创建 `logback-spring.xml`
- [ ] 创建 `application-local.yml` (开发环境)
- [ ] 创建 `application-production.yml` (生产环境)
- [ ] 配置 management endpoints (含 prometheus)

### 6.3 代码 - 日志

- [ ] 创建 `logging/LoggingFilter.java`
- [ ] 创建 `logging/LogEvent.java`
- [ ] 在 Service 层使用 `LogEvent` 记录业务事件
- [ ] 在 ExceptionHandler 中使用结构化日志

### 6.4 代码 - 指标

- [ ] 创建 `dto/ClientInfo.java` (如需追踪用户来源)
- [ ] 创建 `metrics/ClientInfoResolver.java` (如需追踪用户来源)
- [ ] 创建 `metrics/BusinessMetrics.java`
- [ ] 在 Service 层注入 `BusinessMetrics` 并记录业务指标
- [ ] 在 ExceptionHandler 中记录错误指标

### 6.5 K8s 部署

- [ ] 配置环境变量 (LOG_LEVEL, POD_NAME, ENVIRONMENT 等)
- [ ] 配置 Fluent Bit 日志收集
- [ ] 配置 Prometheus ServiceMonitor 或 PodMonitor

---

## 7. 参考实现

完整的参考实现请查看 `services/user-service` 目录：

```
services/user-service/
├── pom.xml                                    # 依赖配置
├── src/main/resources/
│   ├── logback-spring.xml                     # 日志配置
│   ├── application.yml                        # 主配置 (含 metrics 配置)
│   ├── application-local.yml                  # 本地开发
│   └── application-production.yml             # 生产环境
└── src/main/java/com/authplatform/userservice/
    ├── dto/
    │   └── ClientInfo.java                    # 客户端信息 DTO
    ├── logging/
    │   ├── LoggingFilter.java                 # 请求日志
    │   └── LogEvent.java                      # 事件日志
    ├── metrics/
    │   ├── BusinessMetrics.java               # 业务指标
    │   └── ClientInfoResolver.java            # 客户端信息解析
    ├── service/
    │   └── UserService.java                   # 使用示例
    ├── controller/
    │   └── UserController.java                # 控制器 (含 ClientInfo)
    └── exception/
        └── GlobalExceptionHandler.java        # 异常日志 + 错误指标
```
