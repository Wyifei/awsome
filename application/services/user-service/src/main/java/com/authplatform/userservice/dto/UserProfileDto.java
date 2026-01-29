package com.authplatform.userservice.dto;

import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;
import lombok.Builder;

import java.time.LocalDate;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class UserProfileDto {
    private String userId;
    private String nickname;
    private String avatar;
    private String gender;
    private LocalDate birthday;
    private String address;
}
