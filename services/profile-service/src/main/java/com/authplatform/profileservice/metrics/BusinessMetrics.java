package com.authplatform.profileservice.metrics;

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
 * Business metrics for Profile Service
 *
 * Metrics:
 * - profile_created_total: Profile creation count
 * - profile_updated_total: Profile update count (by field)
 * - profile_fetched_total: Profile fetch count
 * - profile_deleted_total: Profile deletion count (by reason)
 * - avatar_uploaded_total: Avatar upload count
 * - profile_errors_total: Error count (by type, status code)
 * - external_call_duration_seconds: External service call duration
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class BusinessMetrics {

    private final MeterRegistry meterRegistry;

    private static final String METRIC_PROFILE_CREATED = "profile_created";
    private static final String METRIC_PROFILE_UPDATED = "profile_updated";
    private static final String METRIC_PROFILE_FETCHED = "profile_fetched";
    private static final String METRIC_PROFILE_DELETED = "profile_deleted";
    private static final String METRIC_AVATAR_UPLOADED = "profile_avatar_uploaded";
    private static final String METRIC_ERRORS = "profile_errors";
    private static final String METRIC_EXTERNAL_CALL = "profile_external_call_duration";

    private static final String TAG_FIELD = "field";
    private static final String TAG_REASON = "reason";
    private static final String TAG_ERROR_TYPE = "error_type";
    private static final String TAG_STATUS_CODE = "status_code";
    private static final String TAG_SERVICE = "service";
    private static final String TAG_OPERATION = "operation";
    private static final String TAG_SUCCESS = "success";

    private final ConcurrentHashMap<String, Counter> counterCache = new ConcurrentHashMap<>();

    private Counter profileCreatedCounter;
    private Counter profileFetchedCounter;
    private Counter avatarUploadedCounter;

    public static final String DELETE_REASON_USER_REQUEST = "user_request";
    public static final String DELETE_REASON_ADMIN_ACTION = "admin_action";
    public static final String DELETE_REASON_ACCOUNT_DELETED = "account_deleted";

    @PostConstruct
    public void init() {
        profileCreatedCounter = Counter.builder(METRIC_PROFILE_CREATED + "_total")
                .description("Total number of profiles created")
                .register(meterRegistry);

        profileFetchedCounter = Counter.builder(METRIC_PROFILE_FETCHED + "_total")
                .description("Total number of profile fetch operations")
                .register(meterRegistry);

        avatarUploadedCounter = Counter.builder(METRIC_AVATAR_UPLOADED + "_total")
                .description("Total number of avatar uploads")
                .register(meterRegistry);

        log.info("Business metrics initialized");
    }

    public void incrementProfileCreated() {
        profileCreatedCounter.increment();
    }

    public void incrementProfileFetched() {
        profileFetchedCounter.increment();
    }

    public void incrementAvatarUploaded() {
        avatarUploadedCounter.increment();
    }

    public void incrementProfileUpdated(String field) {
        final String finalField = (field == null || field.isBlank()) ? "unknown" : field;

        String cacheKey = "profile_updated_" + finalField;

        Counter counter = counterCache.computeIfAbsent(cacheKey, k ->
                Counter.builder(METRIC_PROFILE_UPDATED + "_total")
                        .description("Total number of profile update operations")
                        .tag(TAG_FIELD, finalField)
                        .register(meterRegistry)
        );

        counter.increment();
    }

    public void incrementProfileUpdated(String[] fields) {
        if (fields == null || fields.length == 0) {
            return;
        }
        for (String field : fields) {
            incrementProfileUpdated(field.trim());
        }
    }

    public void incrementProfileDeleted(String reason) {
        final String finalReason = (reason == null || reason.isBlank()) ? "unknown" : reason;

        String cacheKey = "profile_deleted_" + finalReason;

        Counter counter = counterCache.computeIfAbsent(cacheKey, k ->
                Counter.builder(METRIC_PROFILE_DELETED + "_total")
                        .description("Total number of profiles deleted")
                        .tag(TAG_REASON, finalReason)
                        .register(meterRegistry)
        );

        counter.increment();
    }

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

    public Timer.Sample startExternalCall() {
        return Timer.start(meterRegistry);
    }

    public void recordExternalCall(Timer.Sample sample, String service, String operation, boolean success) {
        Timer timer = Timer.builder(METRIC_EXTERNAL_CALL + "_seconds")
                .description("External service call duration in seconds")
                .tag(TAG_SERVICE, service)
                .tag(TAG_OPERATION, operation)
                .tag(TAG_SUCCESS, String.valueOf(success))
                .register(meterRegistry);

        sample.stop(timer);
    }

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
