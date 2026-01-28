package com.authplatform.profileservice.service;

import com.authplatform.profileservice.dto.*;
import com.authplatform.profileservice.entity.UserProfile;
import com.authplatform.profileservice.exception.ResourceNotFoundException;
import com.authplatform.profileservice.logging.LogEvent;
import com.authplatform.profileservice.metrics.BusinessMetrics;
import com.authplatform.profileservice.repository.UserProfileRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.util.ArrayList;
import java.util.List;

@Service
@RequiredArgsConstructor
@Slf4j
public class ProfileService {

    private final UserProfileRepository profileRepository;
    private final AvatarService avatarService;
    private final BusinessMetrics businessMetrics;

    /**
     * Get user profile by user ID
     */
    public ProfileResponse getProfile(String userId) {
        log.debug("Fetching profile for user: {}", userId);

        businessMetrics.incrementProfileFetched();

        UserProfile profile = profileRepository.findById(userId)
                .orElseThrow(() -> {
                    LogEvent.business("USER_NOT_FOUND")
                        .with("target_user_id", userId)
                        .warn("User not found");
                    return new ResourceNotFoundException("User not found: " + userId);
                });

        return mapToResponse(profile);
    }

    /**
     * Update user profile (only profile fields)
     */
    @Transactional
    public ProfileResponse updateProfile(String userId, UpdateProfileRequest request) {
        UserProfile profile = profileRepository.findById(userId)
                .orElseThrow(() -> new ResourceNotFoundException("User not found: " + userId));

        List<String> updatedFields = new ArrayList<>();

        if (request.getNickname() != null) {
            profile.setNickname(request.getNickname());
            updatedFields.add("nickname");
        }
        if (request.getGender() != null) {
            profile.setGender(UserProfile.Gender.valueOf(request.getGender().toUpperCase()));
            updatedFields.add("gender");
        }
        if (request.getBirthday() != null) {
            profile.setBirthday(request.getBirthday());
            updatedFields.add("birthday");
        }
        if (request.getAddress() != null) {
            profile.setAddress(request.getAddress());
            updatedFields.add("address");
        }

        profile = profileRepository.save(profile);

        String fields = updatedFields.isEmpty() ? "none" : String.join(",", updatedFields);

        LogEvent.audit("PROFILE_UPDATED")
            .with("target_user_id", userId)
            .with("updated_fields", fields)
            .info("User profile updated");

        if (!updatedFields.isEmpty()) {
            businessMetrics.incrementProfileUpdated(updatedFields.toArray(new String[0]));
        }

        return mapToResponse(profile);
    }

    /**
     * Upload avatar
     */
    @Transactional
    public String uploadAvatar(String userId, MultipartFile file) {
        UserProfile profile = profileRepository.findById(userId)
                .orElseThrow(() -> new ResourceNotFoundException("User not found: " + userId));

        // Delete old avatar if exists
        if (profile.getAvatar() != null) {
            avatarService.deleteAvatar(profile.getAvatar());
        }

        // Upload new avatar
        String avatarUrl = avatarService.uploadAvatar(userId, file);

        // Update profile
        profile.setAvatar(avatarUrl);
        profileRepository.save(profile);

        LogEvent.audit("AVATAR_UPLOADED")
            .with("target_user_id", userId)
            .info("Avatar uploaded");

        return avatarUrl;
    }

    /**
     * Delete avatar
     */
    @Transactional
    public void deleteAvatar(String userId) {
        UserProfile profile = profileRepository.findById(userId)
                .orElseThrow(() -> new ResourceNotFoundException("User not found: " + userId));

        if (profile.getAvatar() != null) {
            avatarService.deleteAvatar(profile.getAvatar());
            profile.setAvatar(null);
            profileRepository.save(profile);

            LogEvent.audit("AVATAR_DELETED")
                .with("target_user_id", userId)
                .info("Avatar deleted");
        }
    }

    private ProfileResponse mapToResponse(UserProfile profile) {
        return ProfileResponse.builder()
                .userId(profile.getId())
                .email(profile.getEmail())
                .username(profile.getUsername())
                .nickname(profile.getNickname())
                .avatar(profile.getAvatar())
                .gender(profile.getGender() != null ? profile.getGender().name().toLowerCase() : null)
                .birthday(profile.getBirthday())
                .address(profile.getAddress())
                .createdAt(profile.getCreatedAt())
                .updatedAt(profile.getUpdatedAt())
                .build();
    }
}
