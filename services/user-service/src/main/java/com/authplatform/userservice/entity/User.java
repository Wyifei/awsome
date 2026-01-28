package com.authplatform.userservice.entity;

import jakarta.persistence.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;
import lombok.Builder;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

import java.time.LocalDate;
import java.time.LocalDateTime;

@Entity
@Table(name = "users")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class User {

    // ==================== Identity Fields (managed by user-service) ====================

    @Id
    @Column(name = "id", length = 36)
    private String id;

    @Column(name = "username", unique = true, nullable = false, length = 128)
    private String username;

    @Column(name = "email", unique = true, nullable = false, length = 256)
    private String email;

    @Column(name = "phone_number", length = 20)
    private String phoneNumber;

    @Column(name = "email_verified", nullable = false)
    private Boolean emailVerified = false;

    @Column(name = "phone_number_verified")
    private Boolean phoneNumberVerified = false;

    @Column(name = "status", nullable = false, length = 20)
    @Enumerated(EnumType.STRING)
    private UserStatus status = UserStatus.ACTIVE;

    // ==================== Profile Fields (managed by profile-service) ====================

    @Column(name = "nickname", length = 64)
    private String nickname;

    @Column(name = "avatar", length = 512)
    private String avatar;

    @Column(name = "gender", length = 10)
    @Enumerated(EnumType.STRING)
    private Gender gender;

    @Column(name = "birthday")
    private LocalDate birthday;

    @Column(name = "address", length = 256)
    private String address;

    @Column(name = "preferences", columnDefinition = "jsonb")
    private String preferences;

    // ==================== Timestamps ====================

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at", nullable = false)
    private LocalDateTime updatedAt;

    // ==================== Enums ====================

    public enum UserStatus {
        ACTIVE,
        INACTIVE,
        SUSPENDED
    }

    public enum Gender {
        MALE,
        FEMALE,
        OTHER
    }
}
