package com.authplatform.profileservice.dto;

import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDate;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class UpdateProfileRequest {

    @Size(max = 64, message = "Nickname must not exceed 64 characters")
    private String nickname;

    private String gender;  // MALE, FEMALE, OTHER

    private LocalDate birthday;

    @Size(max = 256, message = "Address must not exceed 256 characters")
    private String address;
}
