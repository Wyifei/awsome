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
     * Send account modified notification email
     */
    public EmailResponse sendAccountModifiedEmail(String to, String firstName) {
        String subject = "您的账户信息已更新";
        String body = buildAccountModifiedEmailBody(firstName);

        return sendEmail(to, subject, body, BusinessMetrics.EMAIL_TYPE_ACCOUNT_MODIFIED);
    }

    /**
     * Send account deleted notification email
     */
    public EmailResponse sendAccountDeletedEmail(String to, String firstName) {
        String subject = "您的账号已删除";
        String body = buildAccountDeletedEmailBody(firstName);

        return sendEmail(to, subject, body, BusinessMetrics.EMAIL_TYPE_ACCOUNT_DELETED);
    }

    /**
     * Send welcome email (for future use)
     */
    public EmailResponse sendWelcomeEmail(String to, String firstName) {
        String subject = "欢迎加入 " + companyName;
        String body = buildWelcomeEmailBody(firstName);

        return sendEmail(to, subject, body, BusinessMetrics.EMAIL_TYPE_WELCOME);
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

    private String buildAccountModifiedEmailBody(String firstName) {
        String name = firstName != null && !firstName.isBlank() ? firstName : "用户";

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
                        <p style="color: #666666; line-height: 1.6;">您的账户信息已成功更新。</p>
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

    private String buildAccountDeletedEmailBody(String firstName) {
        String name = firstName != null && !firstName.isBlank() ? firstName : "用户";

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

    private String buildWelcomeEmailBody(String firstName) {
        String name = firstName != null && !firstName.isBlank() ? firstName : "用户";

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
                        <p style="color: #666666; line-height: 1.6;">感谢您注册 %s。</p>
                        <p style="color: #666666; line-height: 1.6;">我们很高兴您加入我们的平台，希望您能享受我们提供的服务。</p>
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
