package com.authplatform.userservice.controller;

import com.authplatform.userservice.dto.ApiResponse;
import com.authplatform.userservice.dto.ClientInfo;
import com.authplatform.userservice.dto.UpdateProfileRequest;
import com.authplatform.userservice.dto.UserDto;
import com.authplatform.userservice.dto.UserProfileDto;
import com.authplatform.userservice.metrics.BusinessMetrics;
import com.authplatform.userservice.metrics.ClientInfoResolver;
import com.authplatform.userservice.service.UserService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/users")
@RequiredArgsConstructor
public class UserController {

    private final UserService userService;
    private final ClientInfoResolver clientInfoResolver;

    /**
     * 获取当前用户信息
     * 会自动从 Cognito Token 同步用户数据到本地数据库
     */
    @GetMapping("/me")
    public ApiResponse<UserDto> getCurrentUser(
            @AuthenticationPrincipal Jwt jwt,
            HttpServletRequest request) {
        String userId = jwt.getSubject();
        String username = jwt.getClaimAsString("cognito:username");
        String email = jwt.getClaimAsString("email");
        Boolean emailVerified = jwt.getClaimAsBoolean("email_verified");

        // 解析客户端信息（用于 metrics）
        ClientInfo clientInfo = clientInfoResolver.resolve(request);

        UserDto user = userService.createOrUpdateUser(userId, username, email, emailVerified, clientInfo);
        return ApiResponse.success(user);
    }

    /**
     * 获取当前用户资料
     */
    @GetMapping("/me/profile")
    public ApiResponse<UserProfileDto> getProfile(@AuthenticationPrincipal Jwt jwt) {
        String userId = jwt.getSubject();
        UserProfileDto profile = userService.getProfile(userId);
        return ApiResponse.success(profile);
    }

    /**
     * 更新当前用户资料
     */
    @PutMapping("/me/profile")
    public ApiResponse<UserProfileDto> updateProfile(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody UpdateProfileRequest request) {
        String userId = jwt.getSubject();
        UserProfileDto profile = userService.updateProfile(userId, request);
        return ApiResponse.success(profile);
    }

    /**
     * 注销当前用户账号
     */
    @DeleteMapping("/me")
    public ResponseEntity<ApiResponse<Void>> deleteCurrentUser(@AuthenticationPrincipal Jwt jwt) {
        String userId = jwt.getSubject();
        userService.deleteUser(userId, BusinessMetrics.DELETE_REASON_USER_REQUEST);
        return ResponseEntity.ok(ApiResponse.success(null));
    }
}
