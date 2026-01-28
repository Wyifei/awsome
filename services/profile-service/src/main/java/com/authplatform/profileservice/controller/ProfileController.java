package com.authplatform.profileservice.controller;

import com.authplatform.profileservice.dto.ApiResponse;
import com.authplatform.profileservice.dto.AvatarResponse;
import com.authplatform.profileservice.dto.ProfileResponse;
import com.authplatform.profileservice.dto.UpdateProfileRequest;
import com.authplatform.profileservice.service.ProfileService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

/**
 * Profile API Controller
 *
 * Endpoints:
 * - GET /api/v1/profiles/me - Get current user's profile
 * - PUT /api/v1/profiles/me - Update current user's profile
 * - POST /api/v1/profiles/me/avatar - Upload avatar
 * - DELETE /api/v1/profiles/me/avatar - Delete avatar
 */
@RestController
@RequestMapping("/api/v1/profiles")
@RequiredArgsConstructor
public class ProfileController {

    private final ProfileService profileService;

    /**
     * Get current user's profile
     */
    @GetMapping("/me")
    public ApiResponse<ProfileResponse> getCurrentProfile(@AuthenticationPrincipal Jwt jwt) {
        String userId = jwt.getSubject();
        ProfileResponse profile = profileService.getProfile(userId);
        return ApiResponse.success(profile);
    }

    /**
     * Update current user's profile
     */
    @PutMapping("/me")
    public ApiResponse<ProfileResponse> updateProfile(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody UpdateProfileRequest request) {
        String userId = jwt.getSubject();
        ProfileResponse profile = profileService.updateProfile(userId, request);
        return ApiResponse.success(profile, "Profile updated successfully");
    }

    /**
     * Upload avatar
     */
    @PostMapping(value = "/me/avatar", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ApiResponse<AvatarResponse> uploadAvatar(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam("file") MultipartFile file) {
        String userId = jwt.getSubject();
        String avatarUrl = profileService.uploadAvatar(userId, file);

        AvatarResponse response = AvatarResponse.builder()
                .success(true)
                .avatarUrl(avatarUrl)
                .build();

        return ApiResponse.success(response);
    }

    /**
     * Delete avatar
     */
    @DeleteMapping("/me/avatar")
    public ApiResponse<Void> deleteAvatar(@AuthenticationPrincipal Jwt jwt) {
        String userId = jwt.getSubject();
        profileService.deleteAvatar(userId);
        return ApiResponse.success(null, "Avatar deleted successfully");
    }
}
