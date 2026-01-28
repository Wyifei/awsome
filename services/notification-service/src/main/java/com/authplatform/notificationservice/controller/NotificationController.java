package com.authplatform.notificationservice.controller;

import com.authplatform.notificationservice.dto.ApiResponse;
import com.authplatform.notificationservice.dto.EmailRequest;
import com.authplatform.notificationservice.dto.EmailResponse;
import com.authplatform.notificationservice.service.EmailService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

/**
 * Notification API Controller
 *
 * All endpoints are internal APIs protected by X-Internal-Api-Key header.
 *
 * Endpoints:
 * - POST /api/v1/notifications/account-modified - Send account modified email
 * - POST /api/v1/notifications/account-deleted - Send account deleted email
 * - POST /api/v1/notifications/welcome - Send welcome email
 */
@RestController
@RequestMapping("/api/v1/notifications")
@RequiredArgsConstructor
public class NotificationController {

    private final EmailService emailService;

    /**
     * Send account modified notification email
     *
     * Called by Profile Service when user profile is updated
     */
    @PostMapping("/account-modified")
    public ResponseEntity<ApiResponse<EmailResponse>> sendAccountModifiedEmail(
            @Valid @RequestBody EmailRequest request) {
        EmailResponse response = emailService.sendAccountModifiedEmail(
                request.getTo(),
                request.getFirstName()
        );
        return ResponseEntity.ok(ApiResponse.success(response));
    }

    /**
     * Send account deleted notification email
     *
     * Called by User Service when user account is deleted
     */
    @PostMapping("/account-deleted")
    public ResponseEntity<ApiResponse<EmailResponse>> sendAccountDeletedEmail(
            @Valid @RequestBody EmailRequest request) {
        EmailResponse response = emailService.sendAccountDeletedEmail(
                request.getTo(),
                request.getFirstName()
        );
        return ResponseEntity.ok(ApiResponse.success(response));
    }

    /**
     * Send welcome email
     *
     * Called by User Service or Lambda trigger after user registration
     */
    @PostMapping("/welcome")
    public ResponseEntity<ApiResponse<EmailResponse>> sendWelcomeEmail(
            @Valid @RequestBody EmailRequest request) {
        EmailResponse response = emailService.sendWelcomeEmail(
                request.getTo(),
                request.getFirstName()
        );
        return ResponseEntity.ok(ApiResponse.success(response));
    }
}
