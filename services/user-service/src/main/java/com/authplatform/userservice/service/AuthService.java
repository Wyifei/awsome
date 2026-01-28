package com.authplatform.userservice.service;

import com.authplatform.userservice.client.NotificationServiceClient;
import com.authplatform.userservice.entity.User;
import com.authplatform.userservice.entity.VerificationCode.VerificationType;
import com.authplatform.userservice.exception.EmailAlreadyExistsException;
import com.authplatform.userservice.exception.ResourceNotFoundException;
import com.authplatform.userservice.logging.LogEvent;
import com.authplatform.userservice.metrics.BusinessMetrics;
import com.authplatform.userservice.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Map;

@Service
@RequiredArgsConstructor
@Slf4j
public class AuthService {

    private final UserRepository userRepository;
    private final VerificationCodeService verificationCodeService;
    private final CognitoService cognitoService;
    private final NotificationServiceClient notificationClient;
    private final BusinessMetrics businessMetrics;

    /**
     * Register a new user
     */
    @Transactional
    public Map<String, String> register(String email, String password, String nickname) {
        // 1. Check if email already exists
        if (userRepository.existsByEmail(email)) {
            LogEvent.business("REGISTRATION_EMAIL_EXISTS")
                    .with("email", maskEmail(email))
                    .warn("Registration failed - email already exists");
            throw new EmailAlreadyExistsException("邮箱已被注册");
        }

        // 2. Create user in Cognito (with email_verified=false, suppress welcome email)
        String userId = cognitoService.createUser(email, password);

        // 3. Create user in local database
        User user = User.builder()
                .id(userId)
                .username(email)
                .email(email)
                .nickname(nickname)
                .emailVerified(false)
                .status(User.UserStatus.PENDING_VERIFICATION)
                .build();
        userRepository.save(user);

        // 4. Generate verification code and send email
        String code = verificationCodeService.generateCode(email, VerificationType.EMAIL_VERIFICATION);
        notificationClient.sendVerificationCode(
                email,
                code,
                "EMAIL_VERIFICATION",
                verificationCodeService.getExpiryMinutes()
        );

        LogEvent.audit("USER_REGISTERED")
                .with("user_id", userId)
                .with("email", maskEmail(email))
                .info("User registered successfully, pending email verification");

        businessMetrics.incrementUserCreated(null);

        return Map.of(
                "userId", userId,
                "email", email
        );
    }

    /**
     * Verify email with code
     */
    @Transactional
    public void verifyEmail(String email, String code) {
        // 1. Verify the code
        verificationCodeService.verifyCode(email, code, VerificationType.EMAIL_VERIFICATION);

        // 2. Get user
        User user = userRepository.findByEmail(email)
                .orElseThrow(() -> new ResourceNotFoundException("用户不存在"));

        // 3. Update local database
        user.setEmailVerified(true);
        user.setStatus(User.UserStatus.ACTIVE);
        userRepository.save(user);

        // 4. Update Cognito
        cognitoService.verifyUserEmail(user.getId());

        // 5. Delete verification code
        verificationCodeService.deleteCode(email, VerificationType.EMAIL_VERIFICATION);

        // 6. Send welcome email
        notificationClient.sendWelcomeEmail(email, user.getNickname());

        LogEvent.audit("EMAIL_VERIFIED")
                .with("user_id", user.getId())
                .with("email", maskEmail(email))
                .info("Email verified successfully");

        businessMetrics.incrementEmailVerified();
    }

    /**
     * Resend verification code
     */
    @Transactional
    public void resendVerificationCode(String email) {
        // Check user exists and is pending verification
        User user = userRepository.findByEmail(email)
                .orElseThrow(() -> new ResourceNotFoundException("用户不存在"));

        if (user.getEmailVerified()) {
            throw new RuntimeException("邮箱已验证");
        }

        // Generate new code and send
        String code = verificationCodeService.generateCode(email, VerificationType.EMAIL_VERIFICATION);
        notificationClient.sendVerificationCode(
                email,
                code,
                "EMAIL_VERIFICATION",
                verificationCodeService.getExpiryMinutes()
        );

        LogEvent.audit("VERIFICATION_CODE_RESENT")
                .with("user_id", user.getId())
                .with("email", maskEmail(email))
                .info("Verification code resent");
    }

    /**
     * Forgot password - send reset code
     */
    @Transactional
    public void forgotPassword(String email) {
        // Check user exists
        User user = userRepository.findByEmail(email)
                .orElseThrow(() -> new ResourceNotFoundException("用户不存在"));

        // Generate reset code and send
        String code = verificationCodeService.generateCode(email, VerificationType.PASSWORD_RESET);
        notificationClient.sendVerificationCode(
                email,
                code,
                "PASSWORD_RESET",
                verificationCodeService.getExpiryMinutes()
        );

        LogEvent.audit("PASSWORD_RESET_REQUESTED")
                .with("user_id", user.getId())
                .with("email", maskEmail(email))
                .info("Password reset code sent");
    }

    /**
     * Reset password with code
     */
    @Transactional
    public void resetPassword(String email, String code, String newPassword) {
        // 1. Verify the code
        verificationCodeService.verifyCode(email, code, VerificationType.PASSWORD_RESET);

        // 2. Get user
        User user = userRepository.findByEmail(email)
                .orElseThrow(() -> new ResourceNotFoundException("用户不存在"));

        // 3. Set new password in Cognito
        cognitoService.adminSetUserPassword(user.getId(), newPassword);

        // 4. Delete verification code
        verificationCodeService.deleteCode(email, VerificationType.PASSWORD_RESET);

        LogEvent.audit("PASSWORD_RESET_COMPLETED")
                .with("user_id", user.getId())
                .with("email", maskEmail(email))
                .info("Password reset completed");

        businessMetrics.incrementPasswordReset();
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
