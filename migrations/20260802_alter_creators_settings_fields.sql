-- Migration: add creator settings fields
-- Description: notification_preferences (JSONB), is_discoverable, rate card fields, categories
-- Applied: 2026-08-02

ALTER TABLE creators
  ADD COLUMN IF NOT EXISTS notification_preferences JSONB
    NOT NULL DEFAULT '{"campaign_alerts": true, "brand_messages": true, "payout_updates": true}'::jsonb,
  ADD COLUMN IF NOT EXISTS is_discoverable   BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS rate_per_reel     INT     CHECK (rate_per_reel >= 0),
  ADD COLUMN IF NOT EXISTS rate_per_story    INT     CHECK (rate_per_story >= 0),
  ADD COLUMN IF NOT EXISTS show_rate_card    BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS categories        TEXT[];

-- Back-fill existing rows so notification_preferences is never null
UPDATE creators
SET notification_preferences = '{"campaign_alerts": true, "brand_messages": true, "payout_updates": true}'::jsonb
WHERE notification_preferences IS NULL;

COMMENT ON COLUMN creators.notification_preferences IS
  'User-controlled toggles: {"campaign_alerts": bool, "brand_messages": bool, "payout_updates": bool}';
COMMENT ON COLUMN creators.is_discoverable IS
  'Whether the creator appears in brand discovery search results';
COMMENT ON COLUMN creators.rate_per_reel IS
  'Self-declared rate (INR) for one reel deliverable';
COMMENT ON COLUMN creators.rate_per_story IS
  'Self-declared rate (INR) for one story-set deliverable';
COMMENT ON COLUMN creators.show_rate_card IS
  'Whether the rate card is visible to brands on the public profile';
COMMENT ON COLUMN creators.categories IS
  'Content categories / niches the creator tags themselves with (e.g. ["Fashion", "Travel"])';
