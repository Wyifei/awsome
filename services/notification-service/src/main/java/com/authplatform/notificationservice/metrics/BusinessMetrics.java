package com.authplatform.notificationservice.metrics;

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
 * Business metrics for Notification Service
 *
 * Metrics:
 * - notification_emails_sent_total: Email sent count (by type)
 * - notification_emails_failed_total: Email failed count (by type)
 * - notification_errors_total: Error count (by type, status code)
 * - notification_ses_call_duration_seconds: SES call duration
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class BusinessMetrics {

    private final MeterRegistry meterRegistry;

    private static final String METRIC_EMAILS_SENT = "notification_emails_sent";
    private static final String METRIC_EMAILS_FAILED = "notification_emails_failed";
    private static final String METRIC_ERRORS = "notification_errors";
    private static final String METRIC_SES_CALL = "notification_ses_call_duration";

    private static final String TAG_EMAIL_TYPE = "email_type";
    private static final String TAG_ERROR_TYPE = "error_type";
    private static final String TAG_STATUS_CODE = "status_code";
    private static final String TAG_OPERATION = "operation";
    private static final String TAG_SUCCESS = "success";

    private final ConcurrentHashMap<String, Counter> counterCache = new ConcurrentHashMap<>();

    // Email types
    public static final String EMAIL_TYPE_VERIFICATION_CODE = "verification_code";
    public static final String EMAIL_TYPE_PASSWORD_RESET_CODE = "password_reset_code";
    public static final String EMAIL_TYPE_ACCOUNT_DELETION_CODE = "account_deletion_code";
    public static final String EMAIL_TYPE_WELCOME = "welcome";
    public static final String EMAIL_TYPE_PASSWORD_CHANGED = "password_changed";
    public static final String EMAIL_TYPE_PROFILE_UPDATED = "profile_updated";
    public static final String EMAIL_TYPE_ACCOUNT_DELETED = "account_deleted";

    @PostConstruct
    public void init() {
        log.info("Business metrics initialized");
    }

    /**
     * Record email sent successfully
     */
    public void incrementEmailSent(String emailType) {
        final String finalEmailType = (emailType == null || emailType.isBlank()) ? "unknown" : emailType;

        String cacheKey = "email_sent_" + finalEmailType;

        Counter counter = counterCache.computeIfAbsent(cacheKey, k ->
                Counter.builder(METRIC_EMAILS_SENT + "_total")
                        .description("Total number of emails sent successfully")
                        .tag(TAG_EMAIL_TYPE, finalEmailType)
                        .register(meterRegistry)
        );

        counter.increment();
        log.debug("Metric: email_sent incremented [type={}]", finalEmailType);
    }

    /**
     * Record email send failure
     */
    public void incrementEmailFailed(String emailType) {
        final String finalEmailType = (emailType == null || emailType.isBlank()) ? "unknown" : emailType;

        String cacheKey = "email_failed_" + finalEmailType;

        Counter counter = counterCache.computeIfAbsent(cacheKey, k ->
                Counter.builder(METRIC_EMAILS_FAILED + "_total")
                        .description("Total number of emails failed to send")
                        .tag(TAG_EMAIL_TYPE, finalEmailType)
                        .register(meterRegistry)
        );

        counter.increment();
        log.debug("Metric: email_failed incremented [type={}]", finalEmailType);
    }

    /**
     * Record error
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
     * Start timing SES call
     */
    public Timer.Sample startSesCall() {
        return Timer.start(meterRegistry);
    }

    /**
     * Record SES call completion
     */
    public void recordSesCall(Timer.Sample sample, String operation, boolean success) {
        Timer timer = Timer.builder(METRIC_SES_CALL + "_seconds")
                .description("SES call duration in seconds")
                .tag(TAG_OPERATION, operation)
                .tag(TAG_SUCCESS, String.valueOf(success))
                .register(meterRegistry);

        sample.stop(timer);
        log.debug("Metric: ses_call recorded [operation={}, success={}]", operation, success);
    }

    /**
     * Record SES call duration directly (in milliseconds)
     */
    public void recordSesCallDuration(String operation, boolean success, long durationMs) {
        Timer timer = Timer.builder(METRIC_SES_CALL + "_seconds")
                .description("SES call duration in seconds")
                .tag(TAG_OPERATION, operation)
                .tag(TAG_SUCCESS, String.valueOf(success))
                .register(meterRegistry);

        timer.record(durationMs, TimeUnit.MILLISECONDS);
    }
}
