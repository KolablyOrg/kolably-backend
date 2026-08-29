-- Migration: 027 - Add is_visible to portfolio_items
-- Description: Lets a creator import a post but keep it out of the public
--   Portfolio brands see, without deleting it — the "Manage Videos" screen
--   lists everything and toggles this; the public/default portfolio fetch
--   filters to is_visible = true.
-- Applied: 2026-08-28

ALTER TABLE portfolio_items ADD COLUMN IF NOT EXISTS is_visible BOOLEAN NOT NULL DEFAULT true;

CREATE INDEX IF NOT EXISTS idx_portfolio_items_is_visible ON portfolio_items(is_visible);
