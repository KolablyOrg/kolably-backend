-- Migration: 028 - Drop is_visible from portfolio_items
-- Description: Reverts 027 — the show/hide-without-deleting model was
--   dropped in favor of a single "Manage" screen where importing/removing
--   an Instagram post is the only visibility state (see PortfolioItem
--   model and get_creator_portfolio).
-- Applied: 2026-08-28

DROP INDEX IF EXISTS idx_portfolio_items_is_visible;
ALTER TABLE portfolio_items DROP COLUMN IF EXISTS is_visible;
