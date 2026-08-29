-- Migration: push notification tokens
-- Description: new table to hold one row per (profile, device) Expo push
-- token, so notification_service can fan a notification out to every
-- device a profile is logged in on, in addition to writing the in-app
-- notification row. `expo_push_token` is UNIQUE rather than
-- (profile_id, token) — a token belongs to one app install; if the same
-- device logs into a different account, re-registering reassigns the
-- existing row to the new profile_id rather than leaving a stale row
-- pointed at the old account (upsert is keyed on this constraint).

CREATE TABLE IF NOT EXISTS push_tokens (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  expo_push_token TEXT NOT NULL UNIQUE,
  platform TEXT NOT NULL CHECK (platform IN ('ios', 'android')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_used_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_push_tokens_profile_id ON push_tokens (profile_id);

COMMENT ON TABLE push_tokens IS
  'Expo push tokens, one row per app install. Populated by POST
   /notifications/register-token on login, removed by DELETE
   /notifications/register-token on logout. A row surviving with a token
   Expo reports as DeviceNotRegistered (app uninstalled, or a stale
   simulator token) is deleted opportunistically by push_notification_service
   the next time a send to it fails that way.';
