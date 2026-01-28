package com.authplatform.notificationservice.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * Filter to validate internal API requests using API key
 */
@Component
@Slf4j
public class InternalApiKeyFilter extends OncePerRequestFilter {

    @Value("${internal.api-key:}")
    private String expectedApiKey;

    private static final String API_KEY_HEADER = "X-Internal-Api-Key";

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {

        String path = request.getRequestURI();

        // Check all notification API paths (they are all internal)
        if (path.contains("/api/v1/notifications")) {
            String apiKey = request.getHeader(API_KEY_HEADER);

            if (expectedApiKey == null || expectedApiKey.isBlank()) {
                log.warn("Internal API key not configured");
                response.setStatus(HttpServletResponse.SC_INTERNAL_SERVER_ERROR);
                response.setContentType("application/json");
                response.getWriter().write("{\"success\": false, \"message\": \"Internal API not configured\"}");
                return;
            }

            if (!expectedApiKey.equals(apiKey)) {
                log.warn("Invalid internal API key from IP: {}", request.getRemoteAddr());
                response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                response.setContentType("application/json");
                response.getWriter().write("{\"success\": false, \"message\": \"Invalid API Key\"}");
                return;
            }
        }

        filterChain.doFilter(request, response);
    }
}
