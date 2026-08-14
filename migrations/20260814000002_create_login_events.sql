-- Migration: create login_events table
-- Description: lightweight login history for the "Active sessions" settings
--   panel. This is NOT a session-revocation mechanism — Supabase's admin API
--   has no per-session revoke, only sign-out scope global/local/others (see
--   app/api/routes/auth.py's /sessions/revoke-others, which uses "others").
--   This table is purely for display.
-- Applied: 2026-08-14

CREATE TABLE IF NOT EXISTS login_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id uuid NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  ip_address text,
  user_agent text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS login_events_profile_id_created_at_idx
  ON login_events(profile_id, created_at DESC);

ALTER TABLE login_events ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE login_events IS
  'Display-only login history (device/IP/time) for the Settings "Active sessions" panel — not a revocation mechanism.';
