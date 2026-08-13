-- Migration: add creator "open to" compensation preference
-- Description: which compensation types a creator is open to (paid / barter / affiliate)
-- Applied: 2026-08-12

ALTER TABLE creators
  ADD COLUMN IF NOT EXISTS open_to TEXT[];

COMMENT ON COLUMN creators.open_to IS
  'Compensation types the creator is open to, e.g. ["paid", "barter"] — self-declared during onboarding, editable later in profile settings';
