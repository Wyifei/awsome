package com.authplatform.notificationservice.service;

import com.authplatform.notificationservice.dto.EmailResponse;
import com.authplatform.notificationservice.exception.EmailSendException;
import com.authplatform.notificationservice.logging.LogEvent;
import com.authplatform.notificationservice.metrics.BusinessMetrics;
import io.micrometer.core.instrument.Timer;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import software.amazon.awssdk.services.ses.SesClient;
import software.amazon.awssdk.services.ses.model.*;

@Service
@RequiredArgsConstructor
@Slf4j
public class EmailService {

    private final SesClient sesClient;
    private final BusinessMetrics businessMetrics;

    @Value("${ses.from-address}")
    private String fromAddress;

    @Value("${ses.from-name:Auth Platform}")
    private String fromName;

    @Value("${app.company-name:Auth Platform}")
    private String companyName;

    /**
     * Send verification code email (for registration, password reset, or account deletion)
     */
    public EmailResponse sendVerificationCodeEmail(String to, String code, String type, int expiresInMinutes) {
        String subject;
        String body;
        String emailType;

        if ("EMAIL_VERIFICATION".equals(type)) {
            subject = "您的邮箱验证码";
            body = buildEmailVerificationCodeBody(code, expiresInMinutes);
            emailType = BusinessMetrics.EMAIL_TYPE_VERIFICATION_CODE;
        } else if ("ACCOUNT_DELETION".equals(type)) {
            subject = "您的账号注销验证码";
            body = buildAccountDeletionCodeBody(code, expiresInMinutes);
            emailType = BusinessMetrics.EMAIL_TYPE_ACCOUNT_DELETION_CODE;
        } else {
            subject = "您的密码重置验证码";
            body = buildPasswordResetCodeBody(code, expiresInMinutes);
            emailType = BusinessMetrics.EMAIL_TYPE_PASSWORD_RESET_CODE;
        }

        return sendEmail(to, subject, body, emailType);
    }

    /**
     * Send welcome email after registration verification
     */
    public EmailResponse sendWelcomeEmail(String to, String nickname) {
        String subject = "欢迎加入 " + companyName;
        String body = buildWelcomeEmailBody(nickname);

        return sendEmail(to, subject, body, BusinessMetrics.EMAIL_TYPE_WELCOME);
    }

    /**
     * Send password changed notification email
     */
    public EmailResponse sendPasswordChangedEmail(String to, String nickname) {
        String subject = "您的密码已修改";
        String body = buildPasswordChangedEmailBody(nickname);

        return sendEmail(to, subject, body, BusinessMetrics.EMAIL_TYPE_PASSWORD_CHANGED);
    }

    /**
     * Send profile updated notification email
     */
    public EmailResponse sendProfileUpdatedEmail(String to, String nickname) {
        String subject = "您的个人资料已更新";
        String body = buildProfileUpdatedEmailBody(nickname);

        return sendEmail(to, subject, body, BusinessMetrics.EMAIL_TYPE_PROFILE_UPDATED);
    }

    /**
     * Send account deleted notification email
     */
    public EmailResponse sendAccountDeletedEmail(String to, String nickname) {
        String subject = "您的账号已删除";
        String body = buildAccountDeletedEmailBody(nickname);

        return sendEmail(to, subject, body, BusinessMetrics.EMAIL_TYPE_ACCOUNT_DELETED);
    }

    private EmailResponse sendEmail(String to, String subject, String body, String emailType) {
        Timer.Sample sample = businessMetrics.startSesCall();
        boolean success = false;

        try {
            String fromFormatted = String.format("%s <%s>", fromName, fromAddress);

            SendEmailRequest request = SendEmailRequest.builder()
                    .source(fromFormatted)
                    .destination(Destination.builder()
                            .toAddresses(to)
                            .build())
                    .message(Message.builder()
                            .subject(Content.builder()
                                    .data(subject)
                                    .charset("UTF-8")
                                    .build())
                            .body(Body.builder()
                                    .html(Content.builder()
                                            .data(body)
                                            .charset("UTF-8")
                                            .build())
                                    .build())
                            .build())
                    .build();

            SendEmailResponse response = sesClient.sendEmail(request);
            success = true;

            LogEvent.integration("EMAIL_SENT")
                .with("email_type", emailType)
                .with("to", maskEmail(to))
                .with("message_id", response.messageId())
                .info("Email sent successfully");

            businessMetrics.incrementEmailSent(emailType);

            return EmailResponse.builder()
                    .success(true)
                    .messageId(response.messageId())
                    .build();

        } catch (SesException e) {
            LogEvent.integration("EMAIL_SEND_FAILED")
                .with("email_type", emailType)
                .with("to", maskEmail(to))
                .with("error_code", e.awsErrorDetails().errorCode())
                .with("error_message", e.awsErrorDetails().errorMessage())
                .error("Failed to send email via SES", e);

            businessMetrics.incrementEmailFailed(emailType);

            throw new EmailSendException("Failed to send email: " + e.awsErrorDetails().errorMessage(), e);
        } finally {
            businessMetrics.recordSesCall(sample, "sendEmail", success);
        }
    }

    private String buildEmailVerificationCodeBody(String code, int expiresInMinutes) {
        return String.format("""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background-color: #ffffff; border-radius: 8px; padding: 40px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <h2 style="color: #333333; margin-bottom: 20px;">欢迎注册 %s</h2>
                        <p style="color: #666666; line-height: 1.6;">您的邮箱验证码是：</p>
                        <div style="background-color: #f0f0f0; padding: 20px; border-radius: 8px; text-align: center; margin: 20px 0;">
                            <span style="font-size: 32px; font-weight: bold; color: #4CAF50; letter-spacing: 8px;">%s</span>
                        </div>
                        <p style="color: #666666; line-height: 1.6;">验证码将在 <strong>%d 分钟</strong>后过期。</p>
                        <p style="color: #999999; line-height: 1.6;">如果这不是您本人的操作，请忽略此邮件。</p>
                        <hr style="border: none; border-top: 1px solid #eeeeee; margin: 30px 0;">
                        <p style="color: #999999; font-size: 14px;">
                            此邮件由系统自动发送，请勿直接回复。<br>
                            %s 团队
                        </p>
                    </div>
                </div>
            </body>
            </html>
            """, companyName, code, expiresInMinutes, companyName);
    }

    private String buildPasswordResetCodeBody(String code, int expiresInMinutes) {
        return String.format("""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background-color: #ffffff; border-radius: 8px; padding: 40px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <h2 style="color: #333333; margin-bottom: 20px;">密码重置请求</h2>
                        <p style="color: #666666; line-height: 1.6;">您正在重置 %s 账号密码，验证码是：</p>
                        <div style="background-color: #fff3e0; padding: 20px; border-radius: 8px; text-align: center; margin: 20px 0;">
                            <span style="font-size: 32px; font-weight: bold; color: #FF9800; letter-spacing: 8px;">%s</span>
                        </div>
                        <p style="color: #666666; line-height: 1.6;">验证码将在 <strong>%d 分钟</strong>后过期。</p>
                        <p style="color: #e74c3c; line-height: 1.6;">如果这不是您本人的操作，请立即联系客服。</p>
                        <hr style="border: none; border-top: 1px solid #eeeeee; margin: 30px 0;">
                        <p style="color: #999999; font-size: 14px;">
                            此邮件由系统自动发送，请勿直接回复。<br>
                            %s 团队
                        </p>
                    </div>
                </div>
            </body>
            </html>
            """, companyName, code, expiresInMinutes, companyName);
    }

    private String buildAccountDeletionCodeBody(String code, int expiresInMinutes) {
        return String.format("""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background-color: #ffffff; border-radius: 8px; padding: 40px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <h2 style="color: #e74c3c; margin-bottom: 20px;">账号注销请求</h2>
                        <p style="color: #666666; line-height: 1.6;">您正在申请注销 %s 账号，验证码是：</p>
                        <div style="background-color: #ffebee; padding: 20px; border-radius: 8px; text-align: center; margin: 20px 0;">
                            <span style="font-size: 32px; font-weight: bold; color: #e74c3c; letter-spacing: 8px;">%s</span>
                        </div>
                        <p style="color: #666666; line-height: 1.6;">验证码将在 <strong>%d 分钟</strong>后过期。</p>
                        <div style="background-color: #fff3e0; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #FF9800;">
                            <p style="color: #e65100; margin: 0; line-height: 1.6;"><strong>警告：</strong>账号注销后，您的所有数据将被永久删除，无法恢复。</p>
                        </div>
                        <p style="color: #e74c3c; line-height: 1.6;">如果这不是您本人的操作，请立即修改密码并联系客服。</p>
                        <hr style="border: none; border-top: 1px solid #eeeeee; margin: 30px 0;">
                        <p style="color: #999999; font-size: 14px;">
                            此邮件由系统自动发送，请勿直接回复。<br>
                            %s 团队
                        </p>
                    </div>
                </div>
            </body>
            </html>
            """, companyName, code, expiresInMinutes, companyName);
    }

    private String buildWelcomeEmailBody(String nickname) {
        String name = nickname != null && !nickname.isBlank() ? nickname : "用户";

        return String.format("""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background-color: #ffffff; border-radius: 8px; padding: 40px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <h2 style="color: #333333; margin-bottom: 20px;">欢迎加入，%s！</h2>
                        <p style="color: #666666; line-height: 1.6;">感谢您注册 %s。您的账号已成功创建。</p>
                        <p style="color: #666666; line-height: 1.6;">现在您可以登录并开始使用我们的服务。</p>
                        <hr style="border: none; border-top: 1px solid #eeeeee; margin: 30px 0;">
                        <p style="color: #999999; font-size: 14px;">
                            此邮件由系统自动发送，请勿直接回复。<br>
                            %s 团队
                        </p>
                    </div>
                </div>
            </body>
            </html>
            """, name, companyName, companyName);
    }

    private String buildPasswordChangedEmailBody(String nickname) {
        String name = nickname != null && !nickname.isBlank() ? nickname : "用户";

        return String.format("""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background-color: #ffffff; border-radius: 8px; padding: 40px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <h2 style="color: #333333; margin-bottom: 20px;">您好，%s</h2>
                        <p style="color: #666666; line-height: 1.6;">您的账户密码已成功修改。</p>
                        <p style="color: #e74c3c; line-height: 1.6;">如果这不是您本人的操作，请立即联系我们的客服团队。</p>
                        <hr style="border: none; border-top: 1px solid #eeeeee; margin: 30px 0;">
                        <p style="color: #999999; font-size: 14px;">
                            此邮件由系统自动发送，请勿直接回复。<br>
                            %s 团队
                        </p>
                    </div>
                </div>
            </body>
            </html>
            """, name, companyName);
    }

    private String buildProfileUpdatedEmailBody(String nickname) {
        String name = nickname != null && !nickname.isBlank() ? nickname : "用户";

        return String.format("""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background-color: #ffffff; border-radius: 8px; padding: 40px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <h2 style="color: #333333; margin-bottom: 20px;">您好，%s</h2>
                        <p style="color: #666666; line-height: 1.6;">您的个人资料已成功更新。</p>
                        <p style="color: #666666; line-height: 1.6;">如果这不是您本人的操作，请立即联系我们的客服团队。</p>
                        <hr style="border: none; border-top: 1px solid #eeeeee; margin: 30px 0;">
                        <p style="color: #999999; font-size: 14px;">
                            此邮件由系统自动发送，请勿直接回复。<br>
                            %s 团队
                        </p>
                    </div>
                </div>
            </body>
            </html>
            """, name, companyName);
    }

    private String buildAccountDeletedEmailBody(String nickname) {
        String name = nickname != null && !nickname.isBlank() ? nickname : "用户";

        return String.format("""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background-color: #ffffff; border-radius: 8px; padding: 40px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <h2 style="color: #333333; margin-bottom: 20px;">您好，%s</h2>
                        <p style="color: #666666; line-height: 1.6;">您的账号已成功删除。</p>
                        <p style="color: #666666; line-height: 1.6;">感谢您使用我们的服务。如有任何问题，请联系客服。</p>
                        <hr style="border: none; border-top: 1px solid #eeeeee; margin: 30px 0;">
                        <p style="color: #999999; font-size: 14px;">
                            此邮件由系统自动发送，请勿直接回复。<br>
                            %s 团队
                        </p>
                    </div>
                </div>
            </body>
            </html>
            """, name, companyName);
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
