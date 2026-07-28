-- Migration: 017 - Alter Creators Table (Instagram pre-fill fields)
-- Description: Add website + following_count, populated from Instagram profile
--              data on connect/signup (name/bio/instagram_* columns already exist)
-- Applied: 2026-07-27

ALTER TABLE creators
  ADD COLUMN IF NOT EXISTS website TEXT,
  ADD COLUMN IF NOT EXISTS following_count INT;
