package com.authplatform.notificationservice.exception;

import com.authplatform.notificationservice.dto.ApiResponse;
import com.authplatform.notificationservice.logging.LogEvent;
import com.authplatform.notificationservice.metrics.BusinessMetrics;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.stream.Collectors;

@RestControllerAdvice
@RequiredArgsConstructor
@Slf4j
public class GlobalExceptionHandler {

    private final BusinessMetrics businessMetrics;

    @ExceptionHandler(EmailSendException.class)
    public ResponseEntity<ApiResponse<Void>> handleEmailSendException(EmailSendException e) {
        LogEvent.integration("EMAIL_SEND_FAILED")
            .with("error_message", e.getMessage())
            .error("Failed to send email");

        businessMetrics.incrementError("EmailSendFailed", 500);

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ApiResponse.error(500, "Failed to send email"));
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
                .body(ApiResponse.error(400, message));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiResponse<Void>> handleException(Exception e) {
        LogEvent.business("UNEXPECTED_ERROR")
            .with("error_type", e.getClass().getSimpleName())
            .with("error_message", e.getMessage())
            .error("Unexpected error occurred", e);

        businessMetrics.incrementError("UnexpectedError", 500);

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ApiResponse.error(500, "Internal server error"));
    }
}
