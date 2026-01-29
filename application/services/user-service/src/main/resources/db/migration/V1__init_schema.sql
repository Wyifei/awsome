-- ============================================================================
-- User Service Schema
-- Owner: user-service (primary), profile-service (shared access)
-- Purpose: Complete user data including identity and profile
-- ============================================================================

-- Users table: Complete user information
CREATE TABLE IF NOT EXISTS users (
    -- Identity (managed by user-service)
    id                    VARCHAR(36) PRIMARY KEY,  -- Cognito user sub (UUID)
    email                 VARCHAR(256) NOT NULL UNIQUE,
    username              VARCHAR(128) NOT NULL UNIQUE,
    phone_number          VARCHAR(20),              -- E.164 format
    status                VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    email_verified        BOOLEAN NOT NULL DEFAULT FALSE,
    phone_number_verified BOOLEAN DEFAULT FALSE,

    -- Profile (managed by profile-service)
    nickname              VARCHAR(64),
    avatar                VARCHAR(512),             -- S3/CloudFront URL
    gender                VARCHAR(10),              -- MALE, FEMALE, OTHER
    birthday              DATE,
    address               VARCHAR(256),
    preferences           JSONB,                    -- User preferences JSON

    -- Timestamps
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Status enum: ACTIVE, INACTIVE, SUSPENDED

-- Indexes
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);

-- Comments
COMMENT ON TABLE users IS 'User data table, identity by user-service, profile by profile-service';
COMMENT ON COLUMN users.id IS 'Cognito user sub (UUID), primary identifier';
COMMENT ON COLUMN users.email IS 'User email address, synced from Cognito';
COMMENT ON COLUMN users.status IS 'Account status: ACTIVE, INACTIVE, SUSPENDED';
COMMENT ON COLUMN users.nickname IS 'Display nickname, managed by profile-service';
COMMENT ON COLUMN users.avatar IS 'Avatar image URL from S3 via CloudFront';
COMMENT ON COLUMN users.preferences IS 'User preferences in JSON format';
