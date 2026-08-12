-- Migration: Business KYB rejection reason
-- Description: get_kyb_status has always hardcoded rejection_reason to None
--   since there was nowhere to store it. Adds the column so an admin
--   approve/reject action (PATCH /businesses/{id}/verification/review) can
--   actually record why a submission was rejected.
-- Applied: 2026-08-09

ALTER TABLE businesses
  ADD COLUMN IF NOT EXISTS kyb_rejection_reason TEXT;
