package com.authplatform.notificationservice.controller;

import com.authplatform.notificationservice.dto.ApiResponse;
import com.authplatform.notificationservice.dto.EmailRequest;
import com.authplatform.notificationservice.dto.EmailResponse;
import com.authplatform.notificationservice.dto.VerificationCodeRequest;
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
 * - POST /api/v1/notifications/verification-code - Send verification code email
 * - POST /api/v1/notifications/welcome - Send welcome email
 * - POST /api/v1/notifications/password-changed - Send password changed notification
 * - POST /api/v1/notifications/profile-updated - Send profile updated notification
 * - POST /api/v1/notifications/account-deleted - Send account deleted notification
 */
@RestController
@RequestMapping("/api/v1/notifications")
@RequiredArgsConstructor
public class NotificationController {

    private final EmailService emailService;

    /**
     * Send verification code email
     *
     * Called by User Service for email verification or password reset
     */
    @PostMapping("/verification-code")
    public ResponseEntity<ApiResponse<EmailResponse>> sendVerificationCode(
            @Valid @RequestBody VerificationCodeRequest request) {
        EmailResponse response = emailService.sendVerificationCodeEmail(
                request.getTo(),
                request.getCode(),
                request.getType(),
                request.getExpiresInMinutes()
        );
        return ResponseEntity.ok(ApiResponse.success(response));
    }

    /**
     * Send welcome email
     *
     * Called by User Service after email verification is complete
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

    /**
     * Send password changed notification email
     *
     * Called by User Service after password is changed
     */
    @PostMapping("/password-changed")
    public ResponseEntity<ApiResponse<EmailResponse>> sendPasswordChangedEmail(
            @Valid @RequestBody EmailRequest request) {
        EmailResponse response = emailService.sendPasswordChangedEmail(
                request.getTo(),
                request.getFirstName()
        );
        return ResponseEntity.ok(ApiResponse.success(response));
    }

    /**
     * Send profile updated notification email
     *
     * Called by Profile Service when user profile is updated
     */
    @PostMapping("/profile-updated")
    public ResponseEntity<ApiResponse<EmailResponse>> sendProfileUpdatedEmail(
            @Valid @RequestBody EmailRequest request) {
        EmailResponse response = emailService.sendProfileUpdatedEmail(
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
}
