package com.authplatform.notificationservice.logging;

import lombok.extern.slf4j.Slf4j;
import org.slf4j.MDC;

import java.util.Map;

/**
 * Structured log event utility class
 */
@Slf4j
public class LogEvent {

    public static final String TYPE_BUSINESS = "BUSINESS";
    public static final String TYPE_AUDIT = "AUDIT";
    public static final String TYPE_SECURITY = "SECURITY";
    public static final String TYPE_PERFORMANCE = "PERFORMANCE";
    public static final String TYPE_INTEGRATION = "INTEGRATION";

    public static LogEventBuilder business(String eventName) {
        return new LogEventBuilder(TYPE_BUSINESS, eventName);
    }

    public static LogEventBuilder audit(String eventName) {
        return new LogEventBuilder(TYPE_AUDIT, eventName);
    }

    public static LogEventBuilder security(String eventName) {
        return new LogEventBuilder(TYPE_SECURITY, eventName);
    }

    public static LogEventBuilder performance(String eventName) {
        return new LogEventBuilder(TYPE_PERFORMANCE, eventName);
    }

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
