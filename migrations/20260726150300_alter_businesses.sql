-- Migration: 004 - Alter Businesses Table
-- Description: Add logo_url, industry, is_verified, updated_at columns and trigger
-- Applied: 2026-07-26

ALTER TABLE businesses
  ADD COLUMN IF NOT EXISTS logo_url TEXT,
  ADD COLUMN IF NOT EXISTS industry TEXT,
  ADD COLUMN IF NOT EXISTS is_verified BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

ALTER TABLE businesses DROP CONSTRAINT IF EXISTS businesses_profile_id_fkey;
ALTER TABLE businesses
  ADD CONSTRAINT businesses_profile_id_fkey
  FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_businesses_is_verified ON businesses(is_verified);

DROP TRIGGER IF EXISTS trg_businesses_updated_at ON businesses;
CREATE TRIGGER trg_businesses_updated_at
  BEFORE UPDATE ON businesses
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
