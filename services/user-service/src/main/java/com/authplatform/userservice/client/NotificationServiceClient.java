package com.authplatform.userservice.client;

import com.authplatform.userservice.logging.LogEvent;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

import java.util.Map;

@Component
@Slf4j
public class NotificationServiceClient {

    private final RestTemplate restTemplate;

    @Value("${services.notification.url:http://notification-service:8080}")
    private String notificationServiceUrl;

    @Value("${internal.api-key:}")
    private String apiKey;

    public NotificationServiceClient() {
        this.restTemplate = new RestTemplate();
    }

    /**
     * Send verification code email (registration or password reset)
     */
    public void sendVerificationCode(String email, String code, String type, int expiresInMinutes) {
        Map<String, Object> request = Map.of(
                "to", email,
                "code", code,
                "type", type,
                "expiresInMinutes", expiresInMinutes
        );
        post("/api/v1/notifications/verification-code", request, "verification_code");
    }

    /**
     * Send welcome email
     */
    public void sendWelcomeEmail(String email, String nickname) {
        Map<String, String> request = Map.of(
                "to", email,
                "firstName", nickname != null ? nickname : ""
        );
        post("/api/v1/notifications/welcome", request, "welcome");
    }

    /**
     * Send password changed notification
     */
    public void sendPasswordChangedEmail(String email, String nickname) {
        Map<String, String> request = Map.of(
                "to", email,
                "firstName", nickname != null ? nickname : ""
        );
        post("/api/v1/notifications/password-changed", request, "password_changed");
    }

    /**
     * Send account deleted notification
     */
    public void sendAccountDeletedEmail(String email, String nickname) {
        Map<String, String> request = Map.of(
                "to", email,
                "firstName", nickname != null ? nickname : ""
        );
        post("/api/v1/notifications/account-deleted", request, "account_deleted");
    }

    private void post(String path, Map<String, ?> request, String emailType) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        if (apiKey != null && !apiKey.isEmpty()) {
            headers.set("X-Internal-Api-Key", apiKey);
        }

        HttpEntity<Map<String, ?>> entity = new HttpEntity<>(request, headers);

        try {
            restTemplate.postForEntity(notificationServiceUrl + path, entity, Void.class);
            LogEvent.integration("NOTIFICATION_SENT")
                    .with("email_type", emailType)
                    .with("to", maskEmail((String) request.get("to")))
                    .info("Notification email sent");
        } catch (Exception e) {
            LogEvent.integration("NOTIFICATION_FAILED")
                    .with("email_type", emailType)
                    .with("to", maskEmail((String) request.get("to")))
                    .with("error", e.getMessage())
                    .error("Failed to send notification email", e);
            // Don't throw - email failures should not block main flow
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
