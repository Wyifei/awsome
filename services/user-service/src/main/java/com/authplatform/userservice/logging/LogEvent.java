package com.authplatform.userservice.logging;

import lombok.extern.slf4j.Slf4j;
import org.slf4j.MDC;

import java.util.Map;
import java.util.function.Supplier;

/**
 * 结构化日志事件工具类
 *
 * 使用示例:
 * <pre>
 * LogEvent.business("USER_CREATED")
 *     .with("user_id", userId)
 *     .with("email", email)
 *     .info("New user registered successfully");
 *
 * LogEvent.audit("PROFILE_UPDATED")
 *     .with("user_id", userId)
 *     .with("fields_changed", changedFields)
 *     .info("User profile updated");
 *
 * LogEvent.security("LOGIN_FAILED")
 *     .with("reason", "invalid_password")
 *     .with("attempt_count", attempts)
 *     .warn("Login attempt failed");
 * </pre>
 */
@Slf4j
public class LogEvent {

    // 事件类型常量
    public static final String TYPE_BUSINESS = "BUSINESS";
    public static final String TYPE_AUDIT = "AUDIT";
    public static final String TYPE_SECURITY = "SECURITY";
    public static final String TYPE_PERFORMANCE = "PERFORMANCE";
    public static final String TYPE_INTEGRATION = "INTEGRATION";

    private final String eventType;
    private final String eventName;

    private LogEvent(String eventType, String eventName) {
        this.eventType = eventType;
        this.eventName = eventName;
    }

    /**
     * 创建业务事件日志
     */
    public static LogEventBuilder business(String eventName) {
        return new LogEventBuilder(TYPE_BUSINESS, eventName);
    }

    /**
     * 创建审计事件日志 (用户操作记录)
     */
    public static LogEventBuilder audit(String eventName) {
        return new LogEventBuilder(TYPE_AUDIT, eventName);
    }

    /**
     * 创建安全事件日志
     */
    public static LogEventBuilder security(String eventName) {
        return new LogEventBuilder(TYPE_SECURITY, eventName);
    }

    /**
     * 创建性能事件日志
     */
    public static LogEventBuilder performance(String eventName) {
        return new LogEventBuilder(TYPE_PERFORMANCE, eventName);
    }

    /**
     * 创建集成事件日志 (外部服务调用)
     */
    public static LogEventBuilder integration(String eventName) {
        return new LogEventBuilder(TYPE_INTEGRATION, eventName);
    }

    /**
     * 日志事件构建器
     */
    public static class LogEventBuilder {
        private final String eventType;
        private final String eventName;

        LogEventBuilder(String eventType, String eventName) {
            this.eventType = eventType;
            this.eventName = eventName;
        }

        /**
         * 添加上下文字段到 MDC
         */
        public LogEventBuilder with(String key, Object value) {
            if (value != null) {
                MDC.put(key, String.valueOf(value));
            }
            return this;
        }

        /**
         * 添加多个上下文字段
         */
        public LogEventBuilder withAll(Map<String, Object> fields) {
            if (fields != null) {
                fields.forEach((k, v) -> {
                    if (v != null) {
                        MDC.put(k, String.valueOf(v));
                    }
                });
            }
            return this;
        }

        /**
         * 记录 DEBUG 级别日志
         */
        public void debug(String message) {
            logWithContext(() -> log.debug(formatMessage(message)));
        }

        /**
         * 记录 INFO 级别日志
         */
        public void info(String message) {
            logWithContext(() -> log.info(formatMessage(message)));
        }

        /**
         * 记录 WARN 级别日志
         */
        public void warn(String message) {
            logWithContext(() -> log.warn(formatMessage(message)));
        }

        /**
         * 记录 WARN 级别日志 (带异常)
         */
        public void warn(String message, Throwable throwable) {
            logWithContext(() -> log.warn(formatMessage(message), throwable));
        }

        /**
         * 记录 ERROR 级别日志
         */
        public void error(String message) {
            logWithContext(() -> log.error(formatMessage(message)));
        }

        /**
         * 记录 ERROR 级别日志 (带异常)
         */
        public void error(String message, Throwable throwable) {
            logWithContext(() -> log.error(formatMessage(message), throwable));
        }

        private String formatMessage(String message) {
            return String.format("[%s] %s", eventName, message);
        }

        private void logWithContext(Runnable logAction) {
            // 添加事件元数据到 MDC
            MDC.put("event_type", eventType);
            MDC.put("event_name", eventName);
            try {
                logAction.run();
            } finally {
                // 清理事件特定的 MDC 字段
                MDC.remove("event_type");
                MDC.remove("event_name");
            }
        }
    }
}
