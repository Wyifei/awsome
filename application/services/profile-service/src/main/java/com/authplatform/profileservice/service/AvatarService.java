package com.authplatform.profileservice.service;

import com.authplatform.profileservice.exception.AvatarUploadException;
import com.authplatform.profileservice.logging.LogEvent;
import com.authplatform.profileservice.metrics.BusinessMetrics;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.util.Set;

/**
 * Avatar Service - handles avatar storage in database
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class AvatarService {

    private final BusinessMetrics businessMetrics;

    private static final Set<String> ALLOWED_CONTENT_TYPES = Set.of(
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp"
    );

    private static final long MAX_FILE_SIZE = 5 * 1024 * 1024; // 5MB

    /**
     * Validate and extract avatar data from uploaded file
     *
     * @param file Avatar file
     * @return Avatar data as byte array
     */
    public byte[] processAvatar(MultipartFile file) {
        validateFile(file);

        try {
            byte[] data = file.getBytes();

            LogEvent.audit("AVATAR_PROCESSED")
                .with("file_size", file.getSize())
                .with("content_type", file.getContentType())
                .info("Avatar processed successfully");

            businessMetrics.incrementAvatarUploaded();

            return data;

        } catch (IOException e) {
            LogEvent.integration("AVATAR_PROCESS_FAILED")
                .with("error_message", e.getMessage())
                .error("Failed to process avatar", e);

            throw new AvatarUploadException("Failed to process avatar", e);
        }
    }

    /**
     * Validate uploaded file
     *
     * @param file File to validate
     */
    public void validateFile(MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new AvatarUploadException("File is empty");
        }

        if (file.getSize() > MAX_FILE_SIZE) {
            throw new AvatarUploadException("File size exceeds maximum allowed (5MB)");
        }

        String contentType = file.getContentType();
        if (contentType == null || !ALLOWED_CONTENT_TYPES.contains(contentType)) {
            throw new AvatarUploadException("Invalid file type. Allowed: JPEG, PNG, GIF, WebP");
        }
    }

    /**
     * Check if content type is valid
     *
     * @param contentType Content type to check
     * @return true if valid
     */
    public boolean isValidContentType(String contentType) {
        return contentType != null && ALLOWED_CONTENT_TYPES.contains(contentType);
    }
}
