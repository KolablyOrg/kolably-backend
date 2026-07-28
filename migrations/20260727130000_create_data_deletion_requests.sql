-- Migration: 018 - Create Data Deletion Requests
-- Description: Log table for Meta's Data Deletion Request Callback
--              (docs/API_REQUIREMENTS.md / Kolably_Legal_Documentation_Kit.docx
--              Account Deletion & Data Retention Policy §3)
-- Applied: 2026-07-27

CREATE TABLE IF NOT EXISTS data_deletion_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  confirmation_code TEXT UNIQUE NOT NULL,
  instagram_user_id TEXT NOT NULL,
  profile_id UUID REFERENCES profiles(id) ON DELETE SET NULL,
  status TEXT NOT NULL DEFAULT 'completed',
  requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_data_deletion_requests_instagram_user_id
  ON data_deletion_requests(instagram_user_id);
