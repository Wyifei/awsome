-- ============================================================================
-- Verification Codes Table
-- Purpose: Store email verification codes and password reset codes
-- Owner: user-service
-- ============================================================================

CREATE TABLE IF NOT EXISTS verification_codes (
    id          BIGSERIAL PRIMARY KEY,
    email       VARCHAR(256) NOT NULL,
    code        VARCHAR(6) NOT NULL,
    type        VARCHAR(20) NOT NULL,       -- EMAIL_VERIFICATION, PASSWORD_RESET
    expires_at  TIMESTAMP NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_verification_codes_email_type ON verification_codes(email, type);
CREATE INDEX IF NOT EXISTS idx_verification_codes_expires_at ON verification_codes(expires_at);

-- Comments
COMMENT ON TABLE verification_codes IS 'Temporary storage for verification codes, deleted after use';
COMMENT ON COLUMN verification_codes.email IS 'User email address';
COMMENT ON COLUMN verification_codes.code IS '6-digit verification code';
COMMENT ON COLUMN verification_codes.type IS 'Code type: EMAIL_VERIFICATION or PASSWORD_RESET';
COMMENT ON COLUMN verification_codes.expires_at IS 'Code expiration timestamp, typically 15 minutes from creation';
