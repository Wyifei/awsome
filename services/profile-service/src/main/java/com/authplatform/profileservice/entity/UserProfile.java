package com.authplatform.profileservice.entity;

import jakarta.persistence.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.AllArgsConstructor;
import lombok.Builder;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

import java.time.LocalDate;
import java.time.LocalDateTime;

/**
 * User entity - maps to the shared 'users' table
 * profile-service only manages profile fields (nickname, avatar, gender, birthday, address, preferences)
 * Identity fields (id, email, username, status) are managed by user-service
 */
@Entity
@Table(name = "users")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class UserProfile {

    // ==================== Identity Fields (READ-ONLY for profile-service) ====================

    @Id
    @Column(name = "id", length = 36)
    private String id;

    @Column(name = "email", unique = true, nullable = false, length = 256, updatable = false, insertable = false)
    private String email;

    @Column(name = "username", unique = true, nullable = false, length = 128, updatable = false, insertable = false)
    private String username;

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

    public enum Gender {
        MALE,
        FEMALE,
        OTHER
    }
}
