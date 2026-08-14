-- Migration: create waitlist_signups table
-- Description: landing-page email capture — no third-party mailing-list
--   service is wired up yet, so this just stores signups for later outreach.
-- Applied: 2026-08-14

CREATE TABLE IF NOT EXISTS waitlist_signups (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text NOT NULL UNIQUE,
  role text NOT NULL CHECK (role IN ('creator', 'business')),
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE waitlist_signups ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE waitlist_signups IS
  'Landing-page email capture (public POST /waitlist) — plain storage, no mailing-list integration yet.';
