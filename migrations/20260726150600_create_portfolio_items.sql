-- Migration: 007 - Create Portfolio Items Table
-- Description: Creator portfolio media (photos/videos) with engagement stats
-- Applied: 2026-07-26

CREATE TABLE IF NOT EXISTS portfolio_items (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  creator_id      UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
  media_url       TEXT NOT NULL,
  post_link       TEXT,
  media_type      TEXT NOT NULL DEFAULT 'photo' CHECK (media_type IN ('photo', 'video')),
  like_count      INT,
  comment_count   INT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_portfolio_items_creator_id ON portfolio_items(creator_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_items_media_type ON portfolio_items(media_type);
