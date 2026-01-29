package com.authplatform.profileservice.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDate;
import java.time.LocalDateTime;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class ProfileResponse {

    private String userId;
    private String email;       // Read-only, from users table
    private String username;    // Read-only, from users table
    private String nickname;
    private String avatar;
    private String gender;
    private LocalDate birthday;
    private String address;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
