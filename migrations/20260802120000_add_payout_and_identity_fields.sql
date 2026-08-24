-- Migration: Add payout method and identity verification fields to creators table
-- Description: Supports PayoutSetup (Bank account / UPI / PAN / GST) and Identity Verification
-- Applied: 2026-08-02

ALTER TABLE creators
  ADD COLUMN IF NOT EXISTS payout_method_type     TEXT CHECK (payout_method_type IN ('bank', 'upi')),
  ADD COLUMN IF NOT EXISTS account_holder_name    TEXT,
  ADD COLUMN IF NOT EXISTS account_number_last4   TEXT,
  ADD COLUMN IF NOT EXISTS ifsc_code             TEXT,
  ADD COLUMN IF NOT EXISTS bank_name              TEXT,
  ADD COLUMN IF NOT EXISTS upi_id                 TEXT,
  ADD COLUMN IF NOT EXISTS pan_number             TEXT,
  ADD COLUMN IF NOT EXISTS has_gst                BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS gst_number             TEXT,
  ADD COLUMN IF NOT EXISTS payout_verified        BOOLEAN NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS identity_status        TEXT NOT NULL DEFAULT 'unverified'
    CHECK (identity_status IN ('unverified', 'pending', 'verified', 'rejected')),
  ADD COLUMN IF NOT EXISTS identity_document_url  TEXT,
  ADD COLUMN IF NOT EXISTS identity_submitted_at  TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS identity_verified_at   TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_creators_identity_status ON creators(identity_status);
