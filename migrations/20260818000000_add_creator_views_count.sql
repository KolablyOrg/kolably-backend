-- Migration: 027 - Add views_count to creators
-- Description: Real aggregate view count (summed from portfolio_items.
--   view_count) so the Engagement section's "Total views" and its growth
--   comparison are backed by real data instead of an always-0 placeholder.
--   creator_stats_history.views_count already existed as a column but every
--   snapshot hardcoded 0 into it — there was nothing on `creators` itself to
--   snapshot from.
-- Applied: 2026-08-18

ALTER TABLE creators ADD COLUMN IF NOT EXISTS views_count INT;
