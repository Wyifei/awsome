package com.authplatform.userservice.dto;

import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;
import lombok.Builder;

import java.time.LocalDateTime;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class UserDto {
    private String id;
    private String username;
    private String email;
    private String phoneNumber;
    private Boolean emailVerified;
    private Boolean phoneNumberVerified;
    private String status;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
