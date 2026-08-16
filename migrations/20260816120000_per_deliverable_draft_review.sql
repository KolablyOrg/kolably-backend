-- Migration: per-deliverable draft review
-- Description: lets a brand approve or request revision on individual draft
-- submissions (reel vs story) instead of the whole collaboration at once.
-- Applied: 2026-08-16

ALTER TABLE content_submissions
  ADD COLUMN IF NOT EXISTS content_type TEXT,
  ADD COLUMN IF NOT EXISTS deliverable_index INT,
  ADD COLUMN IF NOT EXISTS draft_status TEXT NOT NULL DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS revision_notes JSONB,
  ADD COLUMN IF NOT EXISTS revision_overall_note TEXT;

ALTER TABLE content_submissions
  DROP CONSTRAINT IF EXISTS content_submissions_draft_status_check;

ALTER TABLE content_submissions
  ADD CONSTRAINT content_submissions_draft_status_check
  CHECK (draft_status = ANY (ARRAY['pending'::text, 'approved'::text, 'needs_revision'::text]));

COMMENT ON COLUMN content_submissions.content_type IS
  'reel/story/post — mirrors the campaign deliverable this submission fulfils.';
COMMENT ON COLUMN content_submissions.deliverable_index IS
  'Zero-based slot in the expanded deliverable list (reel 1, reel 2, story 1, …).';
COMMENT ON COLUMN content_submissions.draft_status IS
  'Brand review state for draft submissions only: pending → approved or needs_revision.';
COMMENT ON COLUMN content_submissions.revision_notes IS
  'Timestamped feedback for this specific deliverable when draft_status = needs_revision.';
COMMENT ON COLUMN content_submissions.revision_overall_note IS
  'Free-text feedback for this specific deliverable when draft_status = needs_revision.';
