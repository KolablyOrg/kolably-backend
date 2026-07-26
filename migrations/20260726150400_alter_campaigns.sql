-- Migration: 005 - Alter Campaigns Table
-- Description: Add updated_at, FK ON DELETE CASCADE, trigram index for title search
-- Applied: 2026-07-26

ALTER TABLE campaigns
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

ALTER TABLE campaigns DROP CONSTRAINT IF EXISTS campaigns_business_id_fkey;
ALTER TABLE campaigns
  ADD CONSTRAINT campaigns_business_id_fkey
  FOREIGN KEY (business_id) REFERENCES businesses(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_campaigns_title_trgm ON campaigns USING gin (title gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_campaigns_created_at ON campaigns(created_at DESC);

DROP TRIGGER IF EXISTS trg_campaigns_updated_at ON campaigns;
CREATE TRIGGER trg_campaigns_updated_at
  BEFORE UPDATE ON campaigns
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
