-- Migration: create business_members table
-- Description: multi-user team accounts for businesses (Owner/Editor/Viewer roles).
--   `businesses.profile_id` stays the original owner (unchanged) — this table
--   adds *additional* profiles with access to the same business, resolved
--   alongside owner-equality checks in app/services/business_access.py.
-- Applied: 2026-08-14

CREATE TABLE IF NOT EXISTS business_members (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id uuid NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  profile_id uuid REFERENCES profiles(id) ON DELETE CASCADE,
  role text NOT NULL CHECK (role IN ('owner', 'editor', 'viewer')),
  invited_email text NOT NULL,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'revoked')),
  invited_by uuid REFERENCES profiles(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  accepted_at timestamptz
);

-- A profile can only hold one membership row per business (once accepted).
CREATE UNIQUE INDEX IF NOT EXISTS business_members_business_profile_unique
  ON business_members(business_id, profile_id)
  WHERE profile_id IS NOT NULL;

-- A pending invite is looked up by email at accept-time (POST /businesses/join).
CREATE INDEX IF NOT EXISTS business_members_invited_email_idx
  ON business_members(invited_email);

CREATE INDEX IF NOT EXISTS business_members_business_id_idx
  ON business_members(business_id);

ALTER TABLE business_members ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE business_members IS
  'Team members (beyond the original owner in businesses.profile_id) with access to a business account. profile_id is NULL until the invited email completes signup and calls POST /businesses/join.';
