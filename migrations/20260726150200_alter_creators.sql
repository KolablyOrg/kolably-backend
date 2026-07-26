-- Migration: 003 - Alter Creators Table
-- Description: Add Instagram OAuth fields, social handles, engagement_rate, updated_at, indexes
-- Applied: 2026-07-26

ALTER TABLE creators
  ADD COLUMN IF NOT EXISTS engagement_rate NUMERIC,
  ADD COLUMN IF NOT EXISTS youtube_handle TEXT,
  ADD COLUMN IF NOT EXISTS tiktok_handle TEXT,
  ADD COLUMN IF NOT EXISTS instagram_user_id TEXT,
  ADD COLUMN IF NOT EXISTS instagram_access_token TEXT,
  ADD COLUMN IF NOT EXISTS instagram_token_expires_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS instagram_synced_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM creators WHERE name IS NULL) THEN
    ALTER TABLE creators ALTER COLUMN name SET NOT NULL;
  END IF;
END $$;

ALTER TABLE creators ALTER COLUMN follower_count SET DEFAULT 0;

ALTER TABLE creators DROP CONSTRAINT IF EXISTS creators_profile_id_fkey;
ALTER TABLE creators
  ADD CONSTRAINT creators_profile_id_fkey
  FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_creators_niche ON creators(niche);
CREATE INDEX IF NOT EXISTS idx_creators_city ON creators(city);
CREATE INDEX IF NOT EXISTS idx_creators_follower_count ON creators(follower_count);

DROP TRIGGER IF EXISTS trg_creators_updated_at ON creators;
CREATE TRIGGER trg_creators_updated_at
  BEFORE UPDATE ON creators
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
