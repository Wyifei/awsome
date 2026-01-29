package com.authplatform.userservice.dto;

import jakarta.validation.constraints.Size;
import lombok.Data;

import java.time.LocalDate;

@Data
public class UpdateProfileRequest {

    @Size(max = 64, message = "昵称不能超过64个字符")
    private String nickname;

    @Size(max = 512, message = "头像URL不能超过512个字符")
    private String avatar;

    private String gender;

    private LocalDate birthday;

    @Size(max = 256, message = "地址不能超过256个字符")
    private String address;
}
