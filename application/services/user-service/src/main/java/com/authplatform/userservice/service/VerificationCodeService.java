package com.authplatform.userservice.service;

import com.authplatform.userservice.entity.VerificationCode;
import com.authplatform.userservice.entity.VerificationCode.VerificationType;
import com.authplatform.userservice.exception.InvalidVerificationCodeException;
import com.authplatform.userservice.logging.LogEvent;
import com.authplatform.userservice.repository.VerificationCodeRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.security.SecureRandom;
import java.time.LocalDateTime;

@Service
@RequiredArgsConstructor
@Slf4j
public class VerificationCodeService {

    private final VerificationCodeRepository repository;

    private static final int CODE_LENGTH = 6;
    private static final int CODE_EXPIRY_MINUTES = 15;
    private final SecureRandom secureRandom = new SecureRandom();

    /**
     * Generate and save a verification code
     */
    @Transactional
    public String generateCode(String email, VerificationType type) {
        // Delete any existing code for this email and type
        repository.deleteByEmailAndType(email, type);

        // Generate new code
        String code = generateRandomCode();
        VerificationCode entity = VerificationCode.builder()
                .email(email)
                .code(code)
                .type(type)
                .expiresAt(LocalDateTime.now().plusMinutes(CODE_EXPIRY_MINUTES))
                .build();

        repository.save(entity);

        LogEvent.audit("VERIFICATION_CODE_GENERATED")
                .with("email", maskEmail(email))
                .with("type", type.name())
                .info("Verification code generated");

        return code;
    }

    /**
     * Verify a code
     * @throws InvalidVerificationCodeException if code is invalid or expired
     */
    public void verifyCode(String email, String code, VerificationType type) {
        VerificationCode entity = repository.findByEmailAndType(email, type)
                .orElseThrow(() -> {
                    LogEvent.business("VERIFICATION_CODE_NOT_FOUND")
                            .with("email", maskEmail(email))
                            .with("type", type.name())
                            .warn("Verification code not found");
                    return new InvalidVerificationCodeException("验证码无效");
                });

        if (entity.isExpired()) {
            LogEvent.business("VERIFICATION_CODE_EXPIRED")
                    .with("email", maskEmail(email))
                    .with("type", type.name())
                    .warn("Verification code expired");
            throw new InvalidVerificationCodeException("验证码已过期");
        }

        if (!entity.getCode().equals(code)) {
            LogEvent.business("VERIFICATION_CODE_MISMATCH")
                    .with("email", maskEmail(email))
                    .with("type", type.name())
                    .warn("Verification code mismatch");
            throw new InvalidVerificationCodeException("验证码错误");
        }

        LogEvent.audit("VERIFICATION_CODE_VERIFIED")
                .with("email", maskEmail(email))
                .with("type", type.name())
                .info("Verification code verified successfully");
    }

    /**
     * Delete a verification code (call after successful verification)
     */
    @Transactional
    public void deleteCode(String email, VerificationType type) {
        repository.deleteByEmailAndType(email, type);
        LogEvent.audit("VERIFICATION_CODE_DELETED")
                .with("email", maskEmail(email))
                .with("type", type.name())
                .debug("Verification code deleted");
    }

    /**
     * Get code expiry time in minutes
     */
    public int getExpiryMinutes() {
        return CODE_EXPIRY_MINUTES;
    }

    /**
     * Cleanup expired verification codes (run every hour)
     */
    @Scheduled(fixedRate = 3600000)
    @Transactional
    public void cleanupExpiredCodes() {
        int deleted = repository.deleteExpiredCodes(LocalDateTime.now());
        if (deleted > 0) {
            LogEvent.business("EXPIRED_CODES_CLEANED")
                    .with("deleted_count", deleted)
                    .info("Expired verification codes cleaned up");
        }
    }

    private String generateRandomCode() {
        StringBuilder sb = new StringBuilder(CODE_LENGTH);
        for (int i = 0; i < CODE_LENGTH; i++) {
            sb.append(secureRandom.nextInt(10));
        }
        return sb.toString();
    }

    private String maskEmail(String email) {
        if (email == null || !email.contains("@")) {
            return "***";
        }
        int atIndex = email.indexOf("@");
        if (atIndex <= 3) {
            return "***" + email.substring(atIndex);
        }
        return email.substring(0, 3) + "***" + email.substring(atIndex);
    }
}
