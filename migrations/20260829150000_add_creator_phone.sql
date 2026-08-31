-- Migration: creator phone number
-- Description: creators had no phone field anywhere (confirmed: not on
-- creators, not on businesses, not in any prior migration). Brands
-- repeatedly need an off-platform contact for shoot coordination, and
-- support needs one for payout disputes.
--
-- Nullable with no default and no backfill: every existing creator
-- genuinely has no phone on record, and inventing one — even an empty
-- string — would make "never provided" indistinguishable from "provided
-- blank". NULL is the honest representation.
--
-- PRIVACY: this is deliberately NOT exposed on CreatorPublicResponse, which
-- is what unauthenticated discovery and brand-facing profile views return.
-- It is owner-only, in the same category as payout_method_type / upi_id /
-- pan_number. If a future feature needs to share it with a brand, that must
-- be an explicit, consented disclosure — not a schema-level default.
-- Applied: 2026-08-29

ALTER TABLE creators
  ADD COLUMN IF NOT EXISTS phone TEXT;

COMMENT ON COLUMN creators.phone IS
  'Creator contact number, stored normalised (leading + optional, digits only — formatting is stripped on write by CreatorUpdateRequest''s validator). Owner-visible only: excluded from CreatorPublicResponse alongside payout/KYC fields. NULL means never provided.';
