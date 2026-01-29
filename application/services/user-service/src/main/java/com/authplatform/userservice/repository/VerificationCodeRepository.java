package com.authplatform.userservice.repository;

import com.authplatform.userservice.entity.VerificationCode;
import com.authplatform.userservice.entity.VerificationCode.VerificationType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.stereotype.Repository;

import java.time.LocalDateTime;
import java.util.Optional;

@Repository
public interface VerificationCodeRepository extends JpaRepository<VerificationCode, Long> {

    Optional<VerificationCode> findByEmailAndType(String email, VerificationType type);

    void deleteByEmailAndType(String email, VerificationType type);

    @Modifying
    @Query("DELETE FROM VerificationCode v WHERE v.expiresAt < :now")
    int deleteExpiredCodes(LocalDateTime now);
}
