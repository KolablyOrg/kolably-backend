-- Migration: Add businesses columns missing from migrations/ and docs/schema.sql
-- Description: app/models/business.py, auth_service.signup_business, and
--   business_repo have referenced owner_name, category, address, and
--   instagram_handle for a while (owner_name is written on every business
--   signup) — the real database already has them, but no migration file or
--   docs/schema.sql ever created them, so replaying migrations/ against a
--   fresh database failed with PGRST204 "Could not find the 'owner_name'
--   column of 'businesses' in the schema cache" on the very first business
--   signup. Discovered building the hermetic integration-test harness
--   (tests_integration/), which is the first thing to ever replay this
--   directory against a genuinely empty database.
--
--   `industry` (in docs/schema.sql's original businesses table) is left
--   alone rather than dropped/renamed — nothing in app/ reads or writes it
--   any more (category replaced it), but there's no evidence either way for
--   whether production still has real data in it.
-- Applied: 2026-08-23

ALTER TABLE businesses
  ADD COLUMN IF NOT EXISTS owner_name        TEXT NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS category          TEXT,
  ADD COLUMN IF NOT EXISTS address           TEXT,
  ADD COLUMN IF NOT EXISTS instagram_handle  TEXT;
