-- Migration: add business settings fields
-- Description: notification_preferences (JSONB) and is_discoverable, mirroring
--   the creators.notification_preferences / creators.is_discoverable pattern
--   from 20260802_alter_creators_settings_fields.sql.

ALTER TABLE businesses
  ADD COLUMN IF NOT EXISTS notification_preferences JSONB
    NOT NULL DEFAULT '{"new_applications": true, "creator_messages": true, "payment_alerts": true}'::jsonb,
  ADD COLUMN IF NOT EXISTS is_discoverable BOOLEAN NOT NULL DEFAULT true;

COMMENT ON COLUMN businesses.notification_preferences IS
  'User-controlled toggles: {"new_applications": bool, "creator_messages": bool, "payment_alerts": bool}';
COMMENT ON COLUMN businesses.is_discoverable IS
  'Whether the business appears in creator-facing business discovery/listing — stored but not read-side enforced yet (same known gap as creators.is_discoverable).';
