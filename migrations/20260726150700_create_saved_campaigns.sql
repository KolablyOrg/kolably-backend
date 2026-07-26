-- Migration: 008 - Create Saved Campaigns Table
-- Description: Many-to-many relationship for creators bookmarking campaigns
-- Applied: 2026-07-26

CREATE TABLE IF NOT EXISTS saved_campaigns (
  creator_id   UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
  campaign_id  UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (creator_id, campaign_id)
);
