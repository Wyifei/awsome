-- ============================================================================
-- Migration: Store avatar in database instead of S3
-- ============================================================================

-- Add columns for avatar binary data
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_data BYTEA;
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_content_type VARCHAR(100);

-- Comment
COMMENT ON COLUMN users.avatar_data IS 'Avatar image binary data stored directly in database';
COMMENT ON COLUMN users.avatar_content_type IS 'MIME type of the avatar image (e.g., image/jpeg, image/png)';

-- Clear existing avatar URLs since they will no longer be valid
-- (Optional: you may want to keep them for reference during migration)
-- UPDATE users SET avatar = NULL WHERE avatar IS NOT NULL;
