package com.authplatform.userservice.service;

import com.authplatform.userservice.dto.ClientInfo;
import com.authplatform.userservice.dto.UpdateProfileRequest;
import com.authplatform.userservice.dto.UserDto;
import com.authplatform.userservice.dto.UserProfileDto;
import com.authplatform.userservice.entity.User;
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

    public UserProfileDto getProfile(String userId) {
        log.debug("Fetching profile for user: {}", userId);
        businessMetrics.incrementProfileFetched();

        User user = userRepository.findById(userId)
                .orElseThrow(() -> {
                    LogEvent.business("USER_NOT_FOUND")
                        .with("target_user_id", userId)
                        .warn("User not found for profile");
                    return new ResourceNotFoundException("User not found: " + userId);
                });
        return toProfileDto(user);
    }

    @Transactional
    public UserProfileDto updateProfile(String userId, UpdateProfileRequest request) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new ResourceNotFoundException("User not found: " + userId));

        StringBuilder updatedFields = new StringBuilder();

        if (request.getNickname() != null) {
            user.setNickname(request.getNickname());
            updatedFields.append("nickname,");
        }
        if (request.getAvatar() != null) {
            user.setAvatar(request.getAvatar());
            updatedFields.append("avatar,");
        }
        if (request.getGender() != null) {
            user.setGender(User.Gender.valueOf(request.getGender().toUpperCase()));
            updatedFields.append("gender,");
        }
        if (request.getBirthday() != null) {
            user.setBirthday(request.getBirthday());
            updatedFields.append("birthday,");
        }
        if (request.getAddress() != null) {
            user.setAddress(request.getAddress());
            updatedFields.append("address,");
        }

        user = userRepository.save(user);

        String fields = updatedFields.length() > 0
            ? updatedFields.substring(0, updatedFields.length() - 1)
            : "none";

        LogEvent.audit("PROFILE_UPDATED")
            .with("target_user_id", userId)
            .with("updated_fields", fields)
            .info("User profile updated");

        if (updatedFields.length() > 0) {
            businessMetrics.incrementProfileUpdated(fields.split(","));
        }

        return toProfileDto(user);
    }

    @Transactional
    public void deleteUser(String userId, String reason) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new ResourceNotFoundException("User not found: " + userId));

        userRepository.delete(user);

        LogEvent.audit("USER_DELETED")
            .with("target_user_id", userId)
            .with("reason", reason)
            .info("User deleted");

        businessMetrics.incrementUserDeleted(reason);
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

    private UserProfileDto toProfileDto(User user) {
        return UserProfileDto.builder()
                .userId(user.getId())
                .nickname(user.getNickname())
                .avatar(user.getAvatar())
                .gender(user.getGender() != null ? user.getGender().name().toLowerCase() : null)
                .birthday(user.getBirthday())
                .address(user.getAddress())
                .build();
    }
}
