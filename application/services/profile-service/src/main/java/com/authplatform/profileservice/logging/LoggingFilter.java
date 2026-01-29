package com.authplatform.profileservice.logging;

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
 * HTTP request logging filter
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

    private static final String[] TRACE_HEADERS = {
        "X-Request-ID",
        "X-Trace-ID",
        "X-Correlation-ID",
        "X-Amzn-Trace-Id"
    };

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {

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
