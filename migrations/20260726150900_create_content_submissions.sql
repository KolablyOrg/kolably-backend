-- Migration: 010 - Create Content Submissions Table
-- Description: Creator-submitted content for collaborations with platform-specific metrics
-- Applied: 2026-07-26

CREATE TABLE IF NOT EXISTS content_submissions (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  collaboration_id  UUID NOT NULL REFERENCES collaborations(id) ON DELETE CASCADE,
  content_url       TEXT NOT NULL,
  platform          TEXT NOT NULL CHECK (platform IN ('instagram', 'youtube', 'tiktok')),

  views             INT,
  likes             INT,
  comments          INT,
  notes             TEXT,
  synced_at         TIMESTAMPTZ,

  submitted_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_content_submissions_collaboration_id ON content_submissions(collaboration_id);
CREATE INDEX IF NOT EXISTS idx_content_submissions_platform ON content_submissions(platform);
