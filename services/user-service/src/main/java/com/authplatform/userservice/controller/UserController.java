package com.authplatform.userservice.controller;

import com.authplatform.userservice.dto.ApiResponse;
import com.authplatform.userservice.dto.ChangePasswordRequest;
import com.authplatform.userservice.dto.ClientInfo;
import com.authplatform.userservice.dto.DeleteAccountConfirmRequest;
import com.authplatform.userservice.dto.DeleteAccountSendCodeRequest;
import com.authplatform.userservice.dto.UserDto;
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
     * 获取当前用户身份信息
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
     * 修改密码
     */
    @PostMapping("/me/change-password")
    public ResponseEntity<ApiResponse<Void>> changePassword(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody ChangePasswordRequest request) {
        String userId = jwt.getSubject();
        String accessToken = jwt.getTokenValue();
        userService.changePassword(userId, accessToken, request.getOldPassword(), request.getNewPassword());
        return ResponseEntity.ok(ApiResponse.success("PASSWORD_CHANGED", "密码修改成功", null));
    }

    /**
     * 注销当前用户账号
     */
    @DeleteMapping("/me")
    public ResponseEntity<ApiResponse<Void>> deleteCurrentUser(@AuthenticationPrincipal Jwt jwt) {
        String userId = jwt.getSubject();
        userService.deleteUser(userId, BusinessMetrics.DELETE_REASON_USER_REQUEST);
        return ResponseEntity.ok(ApiResponse.success("ACCOUNT_DELETED", "账户已成功删除", null));
    }

    /**
     * 发送账号注销验证码
     */
    @PostMapping("/delete-account/send-code")
    public ResponseEntity<ApiResponse<Void>> sendDeleteAccountCode(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody DeleteAccountSendCodeRequest request) {
        String userId = jwt.getSubject();
        userService.sendDeleteAccountCode(userId, request.getEmail());
        return ResponseEntity.ok(ApiResponse.success("DELETE_CODE_SENT", "验证码已发送到您的邮箱", null));
    }

    /**
     * 确认注销账号
     */
    @PostMapping("/delete-account/confirm")
    public ResponseEntity<ApiResponse<Void>> confirmDeleteAccount(
            @AuthenticationPrincipal Jwt jwt,
            @Valid @RequestBody DeleteAccountConfirmRequest request) {
        String userId = jwt.getSubject();
        userService.confirmDeleteAccount(userId, request.getEmail(), request.getCode());
        return ResponseEntity.ok(ApiResponse.success("ACCOUNT_DELETED", "账户已成功删除", null));
    }
}
