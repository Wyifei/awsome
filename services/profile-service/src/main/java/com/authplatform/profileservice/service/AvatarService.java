package com.authplatform.profileservice.service;

import com.authplatform.profileservice.exception.AvatarUploadException;
import com.authplatform.profileservice.logging.LogEvent;
import com.authplatform.profileservice.metrics.BusinessMetrics;
import io.micrometer.core.instrument.Timer;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

import java.io.IOException;
import java.util.Set;
import java.util.UUID;

@Service
@RequiredArgsConstructor
@Slf4j
public class AvatarService {

    private final S3Client s3Client;
    private final BusinessMetrics businessMetrics;

    @Value("${aws.s3.avatar-bucket}")
    private String avatarBucket;

    @Value("${aws.s3.avatar-prefix:avatars/}")
    private String avatarPrefix;

    @Value("${aws.cloudfront.domain:}")
    private String cloudfrontDomain;

    private static final Set<String> ALLOWED_CONTENT_TYPES = Set.of(
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp"
    );

    private static final long MAX_FILE_SIZE = 5 * 1024 * 1024; // 5MB

    /**
     * Upload avatar to S3
     *
     * @param userId User ID
     * @param file   Avatar file
     * @return Avatar URL
     */
    public String uploadAvatar(String userId, MultipartFile file) {
        validateFile(file);

        String contentType = file.getContentType();
        String extension = getExtension(contentType);
        String key = avatarPrefix + userId + "/" + UUID.randomUUID() + extension;

        Timer.Sample sample = businessMetrics.startExternalCall();
        boolean success = false;

        try {
            PutObjectRequest putRequest = PutObjectRequest.builder()
                    .bucket(avatarBucket)
                    .key(key)
                    .contentType(contentType)
                    .build();

            s3Client.putObject(putRequest, RequestBody.fromInputStream(file.getInputStream(), file.getSize()));
            success = true;

            String avatarUrl = buildAvatarUrl(key);

            LogEvent.audit("AVATAR_UPLOADED")
                .with("target_user_id", userId)
                .with("avatar_key", key)
                .with("file_size", file.getSize())
                .info("Avatar uploaded successfully");

            businessMetrics.incrementAvatarUploaded();

            return avatarUrl;

        } catch (IOException e) {
            LogEvent.integration("S3_UPLOAD_FAILED")
                .with("target_user_id", userId)
                .with("error_message", e.getMessage())
                .error("Failed to upload avatar to S3", e);

            throw new AvatarUploadException("Failed to upload avatar", e);
        } finally {
            businessMetrics.recordExternalCall(sample, "s3", "putObject", success);
        }
    }

    /**
     * Delete avatar from S3
     *
     * @param avatarUrl Avatar URL to delete
     */
    public void deleteAvatar(String avatarUrl) {
        if (avatarUrl == null || avatarUrl.isBlank()) {
            return;
        }

        String key = extractKeyFromUrl(avatarUrl);
        if (key == null) {
            return;
        }

        Timer.Sample sample = businessMetrics.startExternalCall();
        boolean success = false;

        try {
            DeleteObjectRequest deleteRequest = DeleteObjectRequest.builder()
                    .bucket(avatarBucket)
                    .key(key)
                    .build();

            s3Client.deleteObject(deleteRequest);
            success = true;

            log.debug("Avatar deleted: {}", key);

        } catch (Exception e) {
            log.warn("Failed to delete avatar: {}", key, e);
        } finally {
            businessMetrics.recordExternalCall(sample, "s3", "deleteObject", success);
        }
    }

    private void validateFile(MultipartFile file) {
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

    private String getExtension(String contentType) {
        return switch (contentType) {
            case "image/jpeg" -> ".jpg";
            case "image/png" -> ".png";
            case "image/gif" -> ".gif";
            case "image/webp" -> ".webp";
            default -> ".jpg";
        };
    }

    private String buildAvatarUrl(String key) {
        if (cloudfrontDomain != null && !cloudfrontDomain.isBlank()) {
            return "https://" + cloudfrontDomain + "/" + key;
        }
        return "https://" + avatarBucket + ".s3.amazonaws.com/" + key;
    }

    private String extractKeyFromUrl(String url) {
        if (url.contains(cloudfrontDomain)) {
            return url.substring(url.indexOf(cloudfrontDomain) + cloudfrontDomain.length() + 1);
        }
        if (url.contains(".s3.amazonaws.com/")) {
            return url.substring(url.indexOf(".s3.amazonaws.com/") + 18);
        }
        return null;
    }
}
