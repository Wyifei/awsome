package com.authplatform.userservice.service;

import com.authplatform.userservice.exception.EmailAlreadyExistsException;
import com.authplatform.userservice.logging.LogEvent;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import software.amazon.awssdk.services.cognitoidentityprovider.CognitoIdentityProviderClient;
import software.amazon.awssdk.services.cognitoidentityprovider.model.*;

@Service
@RequiredArgsConstructor
@Slf4j
public class CognitoService {

    private final CognitoIdentityProviderClient cognitoClient;

    @Value("${cognito.user-pool-id}")
    private String userPoolId;

    /**
     * Create a new user in Cognito (without auto email verification)
     * @return Cognito user sub (UUID)
     */
    public String createUser(String email, String password) {
        try {
            // Create user with email as username, email_verified=false
            AdminCreateUserRequest createRequest = AdminCreateUserRequest.builder()
                    .userPoolId(userPoolId)
                    .username(email)
                    .temporaryPassword(password)
                    .userAttributes(
                            AttributeType.builder().name("email").value(email).build(),
                            AttributeType.builder().name("email_verified").value("false").build()
                    )
                    .messageAction(MessageActionType.SUPPRESS) // Don't send welcome email from Cognito
                    .build();

            AdminCreateUserResponse createResponse = cognitoClient.adminCreateUser(createRequest);
            String userId = createResponse.user().attributes().stream()
                    .filter(attr -> "sub".equals(attr.name()))
                    .findFirst()
                    .map(AttributeType::value)
                    .orElseThrow(() -> new RuntimeException("User sub not found in Cognito response"));

            // Set permanent password (skip force change password flow)
            AdminSetUserPasswordRequest passwordRequest = AdminSetUserPasswordRequest.builder()
                    .userPoolId(userPoolId)
                    .username(email)
                    .password(password)
                    .permanent(true)
                    .build();
            cognitoClient.adminSetUserPassword(passwordRequest);

            LogEvent.integration("COGNITO_USER_CREATED")
                    .with("user_id", userId)
                    .with("email", maskEmail(email))
                    .info("User created in Cognito");

            return userId;

        } catch (UsernameExistsException e) {
            LogEvent.business("COGNITO_USER_EXISTS")
                    .with("email", maskEmail(email))
                    .warn("User already exists in Cognito");
            throw new EmailAlreadyExistsException("邮箱已被注册", e);

        } catch (CognitoIdentityProviderException e) {
            LogEvent.integration("COGNITO_CREATE_USER_FAILED")
                    .with("email", maskEmail(email))
                    .with("error_code", e.awsErrorDetails().errorCode())
                    .error("Failed to create user in Cognito", e);
            throw new RuntimeException("注册失败: " + e.awsErrorDetails().errorMessage(), e);
        }
    }

    /**
     * Update user's email_verified attribute to true
     */
    public void verifyUserEmail(String userId) {
        try {
            AdminUpdateUserAttributesRequest request = AdminUpdateUserAttributesRequest.builder()
                    .userPoolId(userPoolId)
                    .username(userId)
                    .userAttributes(
                            AttributeType.builder().name("email_verified").value("true").build()
                    )
                    .build();

            cognitoClient.adminUpdateUserAttributes(request);

            LogEvent.integration("COGNITO_EMAIL_VERIFIED")
                    .with("user_id", userId)
                    .info("Email verified in Cognito");

        } catch (CognitoIdentityProviderException e) {
            LogEvent.integration("COGNITO_VERIFY_EMAIL_FAILED")
                    .with("user_id", userId)
                    .with("error_code", e.awsErrorDetails().errorCode())
                    .error("Failed to verify email in Cognito", e);
            throw new RuntimeException("邮箱验证失败", e);
        }
    }

    /**
     * Set user password (for password reset)
     */
    public void adminSetUserPassword(String userId, String newPassword) {
        try {
            AdminSetUserPasswordRequest request = AdminSetUserPasswordRequest.builder()
                    .userPoolId(userPoolId)
                    .username(userId)
                    .password(newPassword)
                    .permanent(true)
                    .build();

            cognitoClient.adminSetUserPassword(request);

            LogEvent.integration("COGNITO_PASSWORD_SET")
                    .with("user_id", userId)
                    .info("Password set in Cognito");

        } catch (CognitoIdentityProviderException e) {
            LogEvent.integration("COGNITO_SET_PASSWORD_FAILED")
                    .with("user_id", userId)
                    .with("error_code", e.awsErrorDetails().errorCode())
                    .error("Failed to set password in Cognito", e);
            throw new RuntimeException("密码设置失败: " + e.awsErrorDetails().errorMessage(), e);
        }
    }

    /**
     * Change password (user-initiated)
     */
    public void changePassword(String accessToken, String oldPassword, String newPassword) {
        try {
            ChangePasswordRequest request = ChangePasswordRequest.builder()
                    .accessToken(accessToken)
                    .previousPassword(oldPassword)
                    .proposedPassword(newPassword)
                    .build();

            cognitoClient.changePassword(request);

            LogEvent.integration("COGNITO_PASSWORD_CHANGED")
                    .info("Password changed in Cognito");

        } catch (NotAuthorizedException e) {
            LogEvent.business("COGNITO_WRONG_PASSWORD")
                    .warn("Wrong password provided");
            throw new RuntimeException("原密码错误", e);

        } catch (CognitoIdentityProviderException e) {
            LogEvent.integration("COGNITO_CHANGE_PASSWORD_FAILED")
                    .with("error_code", e.awsErrorDetails().errorCode())
                    .error("Failed to change password in Cognito", e);
            throw new RuntimeException("密码修改失败: " + e.awsErrorDetails().errorMessage(), e);
        }
    }

    /**
     * Delete user from Cognito
     */
    public void deleteUser(String userId) {
        try {
            AdminDeleteUserRequest request = AdminDeleteUserRequest.builder()
                    .userPoolId(userPoolId)
                    .username(userId)
                    .build();

            cognitoClient.adminDeleteUser(request);

            LogEvent.integration("COGNITO_USER_DELETED")
                    .with("user_id", userId)
                    .info("User deleted from Cognito");

        } catch (CognitoIdentityProviderException e) {
            LogEvent.integration("COGNITO_DELETE_USER_FAILED")
                    .with("user_id", userId)
                    .with("error_code", e.awsErrorDetails().errorCode())
                    .error("Failed to delete user from Cognito", e);
            throw new RuntimeException("账号删除失败", e);
        }
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
