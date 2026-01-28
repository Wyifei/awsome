package com.authplatform.profileservice.exception;

import com.authplatform.profileservice.dto.ApiResponse;
import com.authplatform.profileservice.logging.LogEvent;
import com.authplatform.profileservice.metrics.BusinessMetrics;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

import java.util.stream.Collectors;

@RestControllerAdvice
@RequiredArgsConstructor
@Slf4j
public class GlobalExceptionHandler {

    private final BusinessMetrics businessMetrics;

    @ExceptionHandler(ResourceNotFoundException.class)
    public ResponseEntity<ApiResponse<Void>> handleResourceNotFound(ResourceNotFoundException e) {
        LogEvent.business("RESOURCE_NOT_FOUND")
            .with("error_message", e.getMessage())
            .warn("Resource not found");

        businessMetrics.incrementError("ResourceNotFound", 404);

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(ApiResponse.error("PROFILE_NOT_FOUND", e.getMessage()));
    }

    @ExceptionHandler(AvatarUploadException.class)
    public ResponseEntity<ApiResponse<Void>> handleAvatarUpload(AvatarUploadException e) {
        LogEvent.business("AVATAR_UPLOAD_FAILED")
            .with("error_message", e.getMessage())
            .error("Avatar upload failed");

        businessMetrics.incrementError("AvatarUploadFailed", 500);

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ApiResponse.error("UPLOAD_FAILED", "头像上传失败"));
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<ApiResponse<Void>> handleMaxUploadSize(MaxUploadSizeExceededException e) {
        LogEvent.business("FILE_TOO_LARGE")
            .with("error_message", e.getMessage())
            .warn("File size exceeded limit");

        businessMetrics.incrementError("FileTooLarge", 413);

        return ResponseEntity.status(HttpStatus.PAYLOAD_TOO_LARGE)
                .body(ApiResponse.error("FILE_TOO_LARGE", "文件大小超过限制（最大5MB）"));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiResponse<Void>> handleIllegalArgument(IllegalArgumentException e) {
        LogEvent.business("INVALID_FILE_TYPE")
            .with("error_message", e.getMessage())
            .warn("Invalid file type");

        businessMetrics.incrementError("InvalidFileType", 400);

        return ResponseEntity.badRequest()
                .body(ApiResponse.error("INVALID_FILE_TYPE", e.getMessage()));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiResponse<Void>> handleValidationException(MethodArgumentNotValidException e) {
        String message = e.getBindingResult().getFieldErrors().stream()
                .map(FieldError::getDefaultMessage)
                .collect(Collectors.joining(", "));

        String fields = e.getBindingResult().getFieldErrors().stream()
                .map(FieldError::getField)
                .collect(Collectors.joining(", "));

        LogEvent.business("VALIDATION_ERROR")
            .with("invalid_fields", fields)
            .with("error_message", message)
            .warn("Request validation failed");

        businessMetrics.incrementError("ValidationError", 400);

        return ResponseEntity.badRequest()
                .body(ApiResponse.error("VALIDATION_ERROR", message));
    }

    @ExceptionHandler(AccessDeniedException.class)
    public ResponseEntity<ApiResponse<Void>> handleAccessDenied(AccessDeniedException e) {
        LogEvent.security("ACCESS_DENIED")
            .with("error_message", e.getMessage())
            .warn("Access denied");

        businessMetrics.incrementError("AccessDenied", 403);

        return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .body(ApiResponse.error("FORBIDDEN", "访问被拒绝"));
    }

    @ExceptionHandler(AuthenticationException.class)
    public ResponseEntity<ApiResponse<Void>> handleAuthentication(AuthenticationException e) {
        LogEvent.security("AUTHENTICATION_FAILED")
            .with("error_type", e.getClass().getSimpleName())
            .warn("Authentication failed");

        businessMetrics.incrementError("AuthenticationFailed", 401);

        return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(ApiResponse.error("UNAUTHORIZED", "认证失败"));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiResponse<Void>> handleException(Exception e) {
        LogEvent.business("UNEXPECTED_ERROR")
            .with("error_type", e.getClass().getSimpleName())
            .with("error_message", e.getMessage())
            .error("Unexpected error occurred", e);

        businessMetrics.incrementError("UnexpectedError", 500);

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ApiResponse.error("INTERNAL_ERROR", "服务器内部错误"));
    }
}
