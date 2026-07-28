-- Migration: 019 - Alter Portfolio Items Table
-- Description: Add optional title — lets a creator label manual portfolio
--              additions (Instagram imports leave it NULL; caption comes from
--              the IG permalink, not stored)
-- Applied: 2026-07-28

ALTER TABLE portfolio_items
  ADD COLUMN IF NOT EXISTS title TEXT;
