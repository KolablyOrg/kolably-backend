-- Migration: brand-side collaboration management workflow
-- Description: extends collaborations/content_submissions so a business can
-- request a revision, approve a draft, and confirm a live post + payment —
-- the loop the creator side already has (submit/complete/cancel only
-- covered the creator's half). Mirrors the existing revision_requested
-- pattern already used on campaign_applications.status.
-- Applied: 2026-08-14

-- New collaboration lifecycle states, added to the existing 4:
--   revision_requested — business asked for changes on a submitted draft
--   approved           — draft approved, creator should now post live
--   live_submitted      — creator submitted the live post link, awaiting verification
ALTER TABLE collaborations
  DROP CONSTRAINT IF EXISTS collaborations_status_check;

ALTER TABLE collaborations
  ADD CONSTRAINT collaborations_status_check
  CHECK (status = ANY (ARRAY[
    'active'::text,
    'content_submitted'::text,
    'revision_requested'::text,
    'approved'::text,
    'live_submitted'::text,
    'completed'::text,
    'cancelled'::text
  ]));

ALTER TABLE collaborations
  ADD COLUMN IF NOT EXISTS revision_notes JSONB,
  ADD COLUMN IF NOT EXISTS revision_overall_note TEXT,
  ADD COLUMN IF NOT EXISTS payment_confirmed_at TIMESTAMP WITH TIME ZONE;

COMMENT ON COLUMN collaborations.revision_notes IS
  'Array of {"timestamp": "0:04", "note": "..."} objects from the business''s most recent revision request — overwritten on each new request, only the latest round is kept.';
COMMENT ON COLUMN collaborations.revision_overall_note IS
  'Free-text overall note accompanying the most recent revision request (tone, pacing, caption, etc.), separate from the timestamped notes.';
COMMENT ON COLUMN collaborations.payment_confirmed_at IS
  'When the business confirmed they paid the creator directly (Kolably does not process payment) — set by POST /collaborations/{id}/confirm-payment.';

-- content_submissions needs to distinguish a draft submission from the
-- final live-post submission (same table, two phases of the same loop),
-- plus somewhere to store the live-post verification result.
ALTER TABLE content_submissions
  ADD COLUMN IF NOT EXISTS submission_type TEXT NOT NULL DEFAULT 'draft',
  ADD COLUMN IF NOT EXISTS verification_checks JSONB,
  ADD COLUMN IF NOT EXISTS verified_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE content_submissions
  DROP CONSTRAINT IF EXISTS content_submissions_submission_type_check;

ALTER TABLE content_submissions
  ADD CONSTRAINT content_submissions_submission_type_check
  CHECK (submission_type = ANY (ARRAY['draft'::text, 'live'::text]));

COMMENT ON COLUMN content_submissions.submission_type IS
  '"draft" = pre-approval cut submitted for review; "live" = the actual published post submitted for verification + payout. Existing rows default to draft (the only kind that existed before this migration).';
COMMENT ON COLUMN content_submissions.verification_checks IS
  'Best-effort automated checks against the Instagram Graph API for a "live" submission, e.g. {"post_live": true, "tagged_business": true, "paid_partnership_label": null}. null means "not reliably checkable via this API tier — needs manual confirmation," not "failed."';
