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
 * - 为每个请求生成唯一 trace_id
 * - 记录请求开始和结束日志
 * - 将关键信息放入 MDC 供日志使用
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

    // 常见的 trace header 名称
    private static final String[] TRACE_HEADERS = {
        "X-Request-ID",
        "X-Trace-ID",
        "X-Correlation-ID",
        "X-Amzn-Trace-Id"  // AWS ALB/CloudFront trace header
    };

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {

        // 跳过健康检查和静态资源
        if (shouldSkip(request)) {
            filterChain.doFilter(request, response);
            return;
        }

        long startTime = System.currentTimeMillis();

        // 设置 MDC 上下文
        setupMDC(request);

        // 包装请求和响应以支持内容缓存
        ContentCachingRequestWrapper wrappedRequest = new ContentCachingRequestWrapper(request);
        ContentCachingResponseWrapper wrappedResponse = new ContentCachingResponseWrapper(response);

        try {
            // 记录请求开始
            logRequestStart(wrappedRequest);

            // 执行请求
            filterChain.doFilter(wrappedRequest, wrappedResponse);

            // 更新用户信息 (在 Security Filter 执行后)
            updateUserContext();

        } finally {
            long duration = System.currentTimeMillis() - startTime;

            // 更新响应相关的 MDC
            MDC.put(RESPONSE_STATUS, String.valueOf(wrappedResponse.getStatus()));
            MDC.put(RESPONSE_TIME_MS, String.valueOf(duration));

            // 记录请求结束
            logRequestEnd(wrappedRequest, wrappedResponse, duration);

            // 复制响应内容到实际响应
            wrappedResponse.copyBodyToResponse();

            // 清理 MDC
            MDC.clear();
        }
    }

    private boolean shouldSkip(HttpServletRequest request) {
        String uri = request.getRequestURI();
        return uri.contains("/actuator/health")
            || uri.contains("/actuator/prometheus")
            || uri.contains("/favicon.ico")
            || uri.endsWith(".css")
            || uri.endsWith(".js");
    }

    private void setupMDC(HttpServletRequest request) {
        // 生成或获取 trace_id
        String traceId = getTraceId(request);
        MDC.put(TRACE_ID, traceId);

        // 生成 span_id
        MDC.put(SPAN_ID, UUID.randomUUID().toString().substring(0, 8));

        // 请求 ID
        MDC.put(REQUEST_ID, UUID.randomUUID().toString());

        // 客户端 IP
        MDC.put(CLIENT_IP, getClientIP(request));

        // 请求方法和 URI
        MDC.put(REQUEST_METHOD, request.getMethod());
        MDC.put(REQUEST_URI, request.getRequestURI());
    }

    private String getTraceId(HttpServletRequest request) {
        // 尝试从常见的 trace header 获取
        for (String header : TRACE_HEADERS) {
            String value = request.getHeader(header);
            if (value != null && !value.isEmpty()) {
                // AWS X-Amzn-Trace-Id 格式: Root=1-xxx-xxx;Parent=xxx;Sampled=1
                if (header.equals("X-Amzn-Trace-Id") && value.contains("Root=")) {
                    return extractAwsTraceId(value);
                }
                return value;
            }
        }
        // 生成新的 trace_id
        return UUID.randomUUID().toString().replace("-", "");
    }

    private String extractAwsTraceId(String amznTraceId) {
        // 从 "Root=1-xxx-xxx;Parent=xxx" 中提取 Root 值
        for (String part : amznTraceId.split(";")) {
            if (part.startsWith("Root=")) {
                return part.substring(5);
            }
        }
        return amznTraceId;
    }

    private String getClientIP(HttpServletRequest request) {
        // 按优先级检查各种代理 header
        String[] headers = {
            "X-Forwarded-For",
            "X-Real-IP",
            "Proxy-Client-IP",
            "WL-Proxy-Client-IP"
        };

        for (String header : headers) {
            String ip = request.getHeader(header);
            if (ip != null && !ip.isEmpty() && !"unknown".equalsIgnoreCase(ip)) {
                // X-Forwarded-For 可能包含多个 IP，取第一个
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
        String logMessage = String.format("Request completed: %s %s - %d (%dms)",
            request.getMethod(),
            request.getRequestURI(),
            status,
            duration);

        if (status >= 500) {
            log.error(logMessage);
        } else if (status >= 400) {
            log.warn(logMessage);
        } else {
            log.info(logMessage);
        }
    }
}
