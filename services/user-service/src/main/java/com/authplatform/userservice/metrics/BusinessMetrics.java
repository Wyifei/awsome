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

    @PostConstruct
    public void init() {
        // 初始化固定的计数器
        userSyncedCounter = Counter.builder(METRIC_USER_SYNCED + "_total")
                .description("Total number of user sync operations from Cognito")
                .register(meterRegistry);

        profileFetchedCounter = Counter.builder(METRIC_PROFILE_FETCHED + "_total")
                .description("Total number of profile fetch operations")
                .register(meterRegistry);

        log.info("Business metrics initialized");
    }

    // ==================== 用户创建指标 ====================

    /**
     * 记录用户创建
     *
     * @param clientInfo 客户端信息（包含渠道、设备、平台）
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
        log.debug("Metric: user_created incremented [channel={}, device={}, platform={}]",
                channel, device, platform);
    }

    // ==================== 用户删除指标 ====================

    /**
     * 删除原因常量
     */
    public static final String DELETE_REASON_USER_REQUEST = "user_request";
    public static final String DELETE_REASON_ADMIN_ACTION = "admin_action";
    public static final String DELETE_REASON_POLICY_VIOLATION = "policy_violation";
    public static final String DELETE_REASON_INACTIVE = "inactive";

    /**
     * 记录用户删除
     *
     * @param reason 删除原因
     */
    public void incrementUserDeleted(String reason) {
        final String finalReason = (reason == null || reason.isBlank()) ? "unknown" : reason;

        String cacheKey = "user_deleted_" + finalReason;

        Counter counter = counterCache.computeIfAbsent(cacheKey, k ->
                Counter.builder(METRIC_USER_DELETED + "_total")
                        .description("Total number of users deleted")
                        .tag(TAG_REASON, finalReason)
                        .register(meterRegistry)
        );

        counter.increment();
        log.debug("Metric: user_deleted incremented [reason={}]", finalReason);
    }

    // ==================== 用户同步指标 ====================

    /**
     * 记录用户同步（从 Cognito Token 同步用户信息）
     */
    public void incrementUserSynced() {
        userSyncedCounter.increment();
    }

    // ==================== 资料更新指标 ====================

    /**
     * 记录资料更新
     *
     * @param field 更新的字段名
     */
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

    /**
     * 批量记录资料更新（多个字段）
     *
     * @param fields 更新的字段列表，逗号分隔
     */
    public void incrementProfileUpdated(String[] fields) {
        if (fields == null || fields.length == 0) {
            return;
        }
        for (String field : fields) {
            incrementProfileUpdated(field.trim());
        }
    }

    // ==================== 资料查询指标 ====================

    /**
     * 记录资料查询
     */
    public void incrementProfileFetched() {
        profileFetchedCounter.increment();
    }

    // ==================== 错误指标 ====================

    /**
     * 记录错误
     *
     * @param errorType  错误类型（如 ValidationError, ResourceNotFound）
     * @param statusCode HTTP 状态码
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

    // ==================== 外部服务调用指标 ====================

    /**
     * 开始计时外部服务调用
     *
     * @return Timer.Sample 用于后续记录
     */
    public Timer.Sample startExternalCall() {
        return Timer.start(meterRegistry);
    }

    /**
     * 记录外部服务调用完成
     *
     * @param sample    开始时获取的 Timer.Sample
     * @param service   服务名称（如 cognito, ses, s3）
     * @param operation 操作名称（如 getUser, sendEmail）
     * @param success   是否成功
     */
    public void recordExternalCall(Timer.Sample sample, String service, String operation, boolean success) {
        Timer timer = Timer.builder(METRIC_EXTERNAL_CALL + "_seconds")
                .description("External service call duration in seconds")
                .tag(TAG_SERVICE, service)
                .tag(TAG_OPERATION, operation)
                .tag(TAG_SUCCESS, String.valueOf(success))
                .register(meterRegistry);

        sample.stop(timer);

        log.debug("Metric: external_call recorded [service={}, operation={}, success={}]",
                service, operation, success);
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
