-- Migration: 006 - Alter Campaign Applications Table
-- Description: Add updated_at, UNIQUE constraint, FK ON DELETE CASCADE, indexes
-- Applied: 2026-07-26

ALTER TABLE campaign_applications
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

ALTER TABLE campaign_applications DROP CONSTRAINT IF EXISTS campaign_applications_campaign_id_fkey;
ALTER TABLE campaign_applications
  ADD CONSTRAINT campaign_applications_campaign_id_fkey
  FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE;

ALTER TABLE campaign_applications DROP CONSTRAINT IF EXISTS campaign_applications_creator_id_fkey;
ALTER TABLE campaign_applications
  ADD CONSTRAINT campaign_applications_creator_id_fkey
  FOREIGN KEY (creator_id) REFERENCES creators(id) ON DELETE CASCADE;

ALTER TABLE campaign_applications
  DROP CONSTRAINT IF EXISTS campaign_applications_campaign_id_creator_id_key;
ALTER TABLE campaign_applications
  ADD CONSTRAINT campaign_applications_campaign_id_creator_id_key
  UNIQUE (campaign_id, creator_id);

CREATE INDEX IF NOT EXISTS idx_campaign_applications_campaign_id ON campaign_applications(campaign_id);
CREATE INDEX IF NOT EXISTS idx_campaign_applications_creator_id ON campaign_applications(creator_id);
CREATE INDEX IF NOT EXISTS idx_campaign_applications_status ON campaign_applications(status);

DROP TRIGGER IF EXISTS trg_campaign_applications_updated_at ON campaign_applications;
CREATE TRIGGER trg_campaign_applications_updated_at
  BEFORE UPDATE ON campaign_applications
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
