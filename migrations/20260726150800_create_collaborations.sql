-- Migration: 009 - Create Collaborations Table
-- Description: Tracks accepted applications and active creator-business partnerships
-- Applied: 2026-07-26

CREATE TABLE IF NOT EXISTS collaborations (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id   UUID UNIQUE REFERENCES campaign_applications(id) ON DELETE SET NULL,
  campaign_id      UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
  creator_id       UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
  business_id      UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,

  status           TEXT NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active', 'content_submitted', 'completed', 'cancelled')),
  affiliate_url    TEXT,

  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_collaborations_creator_id ON collaborations(creator_id);
CREATE INDEX IF NOT EXISTS idx_collaborations_business_id ON collaborations(business_id);
CREATE INDEX IF NOT EXISTS idx_collaborations_campaign_id ON collaborations(campaign_id);
CREATE INDEX IF NOT EXISTS idx_collaborations_status ON collaborations(status);
