package com.authplatform.userservice.controller;

import com.authplatform.userservice.dto.*;
import com.authplatform.userservice.service.AuthService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * Auth Controller - Registration and verification APIs (no authentication required)
 *
 * Endpoints:
 * - POST /users/register - User registration
 * - POST /users/verify-email - Email verification
 * - POST /users/resend-verification - Resend verification code
 * - POST /users/forgot-password - Request password reset
 * - POST /users/reset-password - Reset password with code
 */
@RestController
@RequestMapping("/users")
@RequiredArgsConstructor
public class AuthController {

    private final AuthService authService;

    /**
     * User registration
     */
    @PostMapping("/register")
    public ResponseEntity<ApiResponse<Map<String, String>>> register(
            @Valid @RequestBody RegisterRequest request) {
        Map<String, String> result = authService.register(
                request.getEmail(),
                request.getPassword(),
                request.getNickname()
        );
        return ResponseEntity.ok(ApiResponse.success(
                "REGISTRATION_PENDING",
                "注册成功，请查收验证码邮件",
                result
        ));
    }

    /**
     * Email verification
     */
    @PostMapping("/verify-email")
    public ResponseEntity<ApiResponse<Void>> verifyEmail(
            @Valid @RequestBody VerifyEmailRequest request) {
        authService.verifyEmail(request.getEmail(), request.getCode());
        return ResponseEntity.ok(ApiResponse.success(
                "EMAIL_VERIFIED",
                "邮箱验证成功",
                null
        ));
    }

    /**
     * Resend verification code
     */
    @PostMapping("/resend-verification")
    public ResponseEntity<ApiResponse<Void>> resendVerification(
            @RequestBody Map<String, String> request) {
        authService.resendVerificationCode(request.get("email"));
        return ResponseEntity.ok(ApiResponse.success(
                "VERIFICATION_SENT",
                "验证码已发送",
                null
        ));
    }

    /**
     * Forgot password - send reset code
     */
    @PostMapping("/forgot-password")
    public ResponseEntity<ApiResponse<Void>> forgotPassword(
            @Valid @RequestBody ForgotPasswordRequest request) {
        authService.forgotPassword(request.getEmail());
        return ResponseEntity.ok(ApiResponse.success(
                "RESET_CODE_SENT",
                "密码重置验证码已发送",
                null
        ));
    }

    /**
     * Reset password with code
     */
    @PostMapping("/reset-password")
    public ResponseEntity<ApiResponse<Void>> resetPassword(
            @Valid @RequestBody ResetPasswordRequest request) {
        authService.resetPassword(
                request.getEmail(),
                request.getCode(),
                request.getNewPassword()
        );
        return ResponseEntity.ok(ApiResponse.success(
                "PASSWORD_RESET",
                "密码重置成功",
                null
        ));
    }
}
