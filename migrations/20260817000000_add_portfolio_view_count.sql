-- Migration: 026 - Add view_count to portfolio_items
-- Description: Store Instagram's per-media view/play count (video content
--   only) alongside the existing like_count/comment_count, so the "Work"
--   section can show real views instead of mislabeling likes as views.
-- Applied: 2026-08-17

ALTER TABLE portfolio_items ADD COLUMN IF NOT EXISTS view_count INT;
