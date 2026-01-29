package com.authplatform.userservice.service;

import com.authplatform.userservice.client.NotificationServiceClient;
import com.authplatform.userservice.dto.ClientInfo;
import com.authplatform.userservice.dto.UserDto;
import com.authplatform.userservice.entity.User;
import com.authplatform.userservice.entity.VerificationCode.VerificationType;
import com.authplatform.userservice.exception.ResourceNotFoundException;
import com.authplatform.userservice.logging.LogEvent;
import com.authplatform.userservice.metrics.BusinessMetrics;
import com.authplatform.userservice.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Slf4j
public class UserService {

    private final UserRepository userRepository;
    private final BusinessMetrics businessMetrics;
    private final CognitoService cognitoService;
    private final NotificationServiceClient notificationClient;
    private final VerificationCodeService verificationCodeService;

    public UserDto getUserById(String userId) {
        log.debug("Fetching user by ID: {}", userId);
        User user = userRepository.findById(userId)
                .orElseThrow(() -> {
                    LogEvent.business("USER_NOT_FOUND")
                        .with("target_user_id", userId)
                        .warn("User not found");
                    return new ResourceNotFoundException("User not found: " + userId);
                });
        return toUserDto(user);
    }

    /**
     * 创建或更新用户（从 Cognito Token 同步）
     */
    @Transactional
    public UserDto createOrUpdateUser(String userId, String username, String email,
                                      Boolean emailVerified, ClientInfo clientInfo) {
        User user = userRepository.findById(userId).orElse(null);
        boolean isNewUser = (user == null);

        if (isNewUser) {
            user = User.builder()
                    .id(userId)
                    .username(username)
                    .email(email)
                    .emailVerified(emailVerified != null ? emailVerified : false)
                    .status(User.UserStatus.ACTIVE)
                    .build();

            LogEvent.audit("USER_CREATED")
                .with("target_user_id", userId)
                .with("username", username)
                .with("email", maskEmail(email))
                .with("email_verified", emailVerified)
                .with("channel", clientInfo != null ? clientInfo.getSafeChannel() : "unknown")
                .with("device", clientInfo != null ? clientInfo.getSafeDevice() : "unknown")
                .with("platform", clientInfo != null ? clientInfo.getSafePlatform() : "unknown")
                .info("New user created from Cognito token");

            businessMetrics.incrementUserCreated(clientInfo);
        } else {
            user.setUsername(username);
            user.setEmail(email);
            if (emailVerified != null) {
                user.setEmailVerified(emailVerified);
            }

            LogEvent.audit("USER_SYNCED")
                .with("target_user_id", userId)
                .with("email_verified", emailVerified)
                .debug("User data synced from Cognito token");

            businessMetrics.incrementUserSynced();
        }

        user = userRepository.save(user);
        return toUserDto(user);
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

    /**
     * 修改密码（调用 Cognito API）
     */
    public void changePassword(String userId, String accessToken, String oldPassword, String newPassword) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new ResourceNotFoundException("User not found: " + userId));

        cognitoService.changePassword(accessToken, oldPassword, newPassword);

        LogEvent.audit("PASSWORD_CHANGED")
            .with("user_id", userId)
            .info("User password changed successfully");

        businessMetrics.incrementPasswordChanged();

        // Send password changed notification
        notificationClient.sendPasswordChangedEmail(user.getEmail(), user.getNickname());
    }

    @Transactional
    public void deleteUser(String userId, String reason) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new ResourceNotFoundException("User not found: " + userId));

        String email = user.getEmail();
        String nickname = user.getNickname();

        // Delete from Cognito first
        cognitoService.deleteUser(userId);

        // Then delete from local database
        userRepository.delete(user);

        LogEvent.audit("USER_DELETED")
            .with("target_user_id", userId)
            .with("reason", reason)
            .info("User deleted");

        businessMetrics.incrementUserDeleted(reason);

        // Send account deleted notification
        notificationClient.sendAccountDeletedEmail(email, nickname);
    }

    /**
     * Send account deletion verification code
     */
    @Transactional
    public void sendDeleteAccountCode(String userId, String email) {
        // Verify user exists
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new ResourceNotFoundException("User not found: " + userId));

        // Verify email matches
        if (!user.getEmail().equalsIgnoreCase(email)) {
            throw new IllegalArgumentException("邮箱不匹配");
        }

        // Generate and send verification code
        String code = verificationCodeService.generateCode(email, VerificationType.ACCOUNT_DELETION);
        notificationClient.sendVerificationCode(
                email,
                code,
                "ACCOUNT_DELETION",
                verificationCodeService.getExpiryMinutes()
        );

        LogEvent.audit("DELETE_ACCOUNT_CODE_SENT")
                .with("user_id", userId)
                .with("email", maskEmail(email))
                .info("Account deletion verification code sent");
    }

    /**
     * Confirm account deletion with verification code
     */
    @Transactional
    public void confirmDeleteAccount(String userId, String email, String code) {
        // Verify user exists
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new ResourceNotFoundException("User not found: " + userId));

        // Verify email matches
        if (!user.getEmail().equalsIgnoreCase(email)) {
            throw new IllegalArgumentException("邮箱不匹配");
        }

        // Verify the code
        verificationCodeService.verifyCode(email, code, VerificationType.ACCOUNT_DELETION);

        // Delete verification code
        verificationCodeService.deleteCode(email, VerificationType.ACCOUNT_DELETION);

        // Delete user (this will handle Cognito and DB deletion)
        deleteUser(userId, BusinessMetrics.DELETE_REASON_USER_REQUEST);
    }

    private UserDto toUserDto(User user) {
        return UserDto.builder()
                .id(user.getId())
                .username(user.getUsername())
                .email(user.getEmail())
                .phoneNumber(user.getPhoneNumber())
                .emailVerified(user.getEmailVerified())
                .phoneNumberVerified(user.getPhoneNumberVerified())
                .status(user.getStatus().name())
                .createdAt(user.getCreatedAt())
                .updatedAt(user.getUpdatedAt())
                .build();
    }
}
