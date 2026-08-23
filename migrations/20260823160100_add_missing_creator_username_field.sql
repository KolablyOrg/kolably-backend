-- Migration: Add creators.username, missing from migrations/ and docs/schema.sql
-- Description: app/models/creator.py, auth_service.signup_creator, and
--   creator_repo's search filter have referenced `username` for a while
--   (every creator signup writes it) — the real database already has it,
--   but no migration file or docs/schema.sql ever created it, so replaying
--   migrations/ against a fresh database failed with PGRST204 "Could not
--   find the 'username' column of 'creators' in the schema cache" on the
--   first creator signup. Same class of gap as
--   20260823160000_add_missing_business_fields.sql — discovered building
--   the hermetic integration-test harness (tests_integration/).
--
--   No UNIQUE constraint: nothing in app/ currently looks up creators by
--   username or checks it for collisions before insert, so adding one here
--   would risk failing on any real duplicate that already exists.
-- Applied: 2026-08-23

ALTER TABLE creators
  ADD COLUMN IF NOT EXISTS username TEXT;
