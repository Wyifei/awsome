package com.authplatform.userservice.exception;

import com.authplatform.userservice.dto.ApiResponse;
import com.authplatform.userservice.logging.LogEvent;
import com.authplatform.userservice.metrics.BusinessMetrics;
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
import software.amazon.awssdk.services.cognitoidentityprovider.model.CognitoIdentityProviderException;

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
                .body(ApiResponse.error("USER_NOT_FOUND", e.getMessage()));
    }

    @ExceptionHandler(EmailAlreadyExistsException.class)
    public ResponseEntity<ApiResponse<Void>> handleEmailAlreadyExists(EmailAlreadyExistsException e) {
        LogEvent.business("EMAIL_ALREADY_EXISTS")
            .with("error_message", e.getMessage())
            .warn("Email already exists");

        businessMetrics.incrementError("EmailAlreadyExists", 409);

        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(ApiResponse.error("EMAIL_ALREADY_EXISTS", e.getMessage()));
    }

    @ExceptionHandler(InvalidVerificationCodeException.class)
    public ResponseEntity<ApiResponse<Void>> handleInvalidVerificationCode(InvalidVerificationCodeException e) {
        LogEvent.business("INVALID_VERIFICATION_CODE")
            .with("error_message", e.getMessage())
            .warn("Invalid verification code");

        businessMetrics.incrementError("InvalidVerificationCode", 400);

        return ResponseEntity.badRequest()
                .body(ApiResponse.error("INVALID_VERIFICATION_CODE", e.getMessage()));
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

    @ExceptionHandler(CognitoIdentityProviderException.class)
    public ResponseEntity<ApiResponse<Void>> handleCognitoException(CognitoIdentityProviderException e) {
        String errorCode = e.awsErrorDetails().errorCode();
        String errorMessage = e.awsErrorDetails().errorMessage();

        LogEvent.business("COGNITO_ERROR")
            .with("error_code", errorCode)
            .with("error_message", errorMessage)
            .warn("Cognito operation failed");

        businessMetrics.incrementError("CognitoError", 400);

        // Map Cognito error codes to user-friendly messages
        String code = mapCognitoErrorCode(errorCode);
        String message = mapCognitoErrorMessage(errorCode, errorMessage);

        return ResponseEntity.badRequest()
                .body(ApiResponse.error(code, message));
    }

    private String mapCognitoErrorCode(String cognitoErrorCode) {
        return switch (cognitoErrorCode) {
            case "NotAuthorizedException" -> "INVALID_PASSWORD";
            case "InvalidPasswordException" -> "PASSWORD_POLICY_ERROR";
            case "LimitExceededException" -> "TOO_MANY_REQUESTS";
            default -> "PASSWORD_CHANGE_FAILED";
        };
    }

    private String mapCognitoErrorMessage(String cognitoErrorCode, String originalMessage) {
        return switch (cognitoErrorCode) {
            case "NotAuthorizedException" -> "原密码错误";
            case "InvalidPasswordException" -> "新密码不符合要求";
            case "LimitExceededException" -> "请求过于频繁，请稍后重试";
            default -> "密码修改失败：" + originalMessage;
        };
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
