-- Migration: Business lightweight signup + KYB (Know-Your-Business) verification
-- Description: business_name becomes optional (now collected post-signup via
--   PATCH /auth/me instead of at signup time); adds the KYB verification fields,
--   mirroring the creators.identity_* pattern from 20260802_add_payout_and_identity_fields.sql.
-- Applied: 2026-08-04

ALTER TABLE businesses ALTER COLUMN business_name DROP NOT NULL;

ALTER TABLE businesses
  ADD COLUMN IF NOT EXISTS legal_entity_name          TEXT,
  ADD COLUMN IF NOT EXISTS business_type              TEXT CHECK (business_type IN ('company', 'individual')),
  ADD COLUMN IF NOT EXISTS pan_number                 TEXT,
  ADD COLUMN IF NOT EXISTS gst_number                 TEXT,
  ADD COLUMN IF NOT EXISTS business_proof_document_url TEXT,
  ADD COLUMN IF NOT EXISTS kyb_status                 TEXT NOT NULL DEFAULT 'unverified'
    CHECK (kyb_status IN ('unverified', 'pending', 'verified', 'rejected')),
  ADD COLUMN IF NOT EXISTS kyb_submitted_at           TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS kyb_verified_at            TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_businesses_kyb_status ON businesses(kyb_status);
