package com.authplatform.profileservice.client;

import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Client for calling Notification Service
 */
@Component
@Slf4j
public class NotificationServiceClient {

    private final RestTemplate restTemplate;
    private final String notificationServiceUrl;
    private final String internalApiKey;

    public NotificationServiceClient(
            @Value("${services.notification.url}") String notificationServiceUrl,
            @Value("${internal.api-key:}") String internalApiKey) {
        this.restTemplate = new RestTemplate();
        this.notificationServiceUrl = notificationServiceUrl;
        this.internalApiKey = internalApiKey;
    }

    /**
     * Send profile updated notification email
     *
     * @param email      User's email address
     * @param nickname   User's nickname (can be null)
     * @param fields     List of updated fields
     */
    public void sendProfileUpdatedEmail(String email, String nickname, List<String> fields) {
        try {
            String url = notificationServiceUrl + "/api/notifications/profile-updated";

            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            if (internalApiKey != null && !internalApiKey.isEmpty()) {
                headers.set("X-Internal-Api-Key", internalApiKey);
            }

            Map<String, Object> body = new HashMap<>();
            body.put("to", email);
            body.put("nickname", nickname);
            body.put("updatedFields", fields);

            HttpEntity<Map<String, Object>> request = new HttpEntity<>(body, headers);

            ResponseEntity<String> response = restTemplate.exchange(
                    url,
                    HttpMethod.POST,
                    request,
                    String.class
            );

            if (response.getStatusCode().is2xxSuccessful()) {
                log.debug("Profile updated email sent successfully to: {}", maskEmail(email));
            } else {
                log.warn("Failed to send profile updated email: status={}", response.getStatusCode());
            }
        } catch (Exception e) {
            log.error("Error sending profile updated email to {}: {}", maskEmail(email), e.getMessage());
            // Don't throw - notification failure should not block profile update
        }
    }

    private String maskEmail(String email) {
        if (email == null || !email.contains("@")) {
            return "***";
        }
        int atIndex = email.indexOf("@");
        if (atIndex <= 3) {
            return "***" + email.substring(atIndex);
        }
        return email.substring(0, 3) + "***" + email.substring(atIndex);
    }
}
