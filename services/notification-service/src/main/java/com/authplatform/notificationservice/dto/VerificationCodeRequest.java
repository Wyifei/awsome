package com.authplatform.notificationservice.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class VerificationCodeRequest {

    @NotBlank(message = "Email address is required")
    @Email(message = "Invalid email format")
    private String to;

    @NotBlank(message = "Verification code is required")
    private String code;

    @NotBlank(message = "Type is required")
    @Pattern(regexp = "EMAIL_VERIFICATION|PASSWORD_RESET", message = "Type must be EMAIL_VERIFICATION or PASSWORD_RESET")
    private String type;

    @Positive(message = "Expiry minutes must be positive")
    private int expiresInMinutes;
}
