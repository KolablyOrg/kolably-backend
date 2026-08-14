-- Migration: durable collaboration revision history and server-side limit
-- Description: keeps every brand revision request and records the number of
-- free revision rounds consumed by a collaboration.

ALTER TABLE collaborations
  ADD COLUMN IF NOT EXISTS revision_rounds INTEGER NOT NULL DEFAULT 0;

ALTER TABLE collaborations
  DROP CONSTRAINT IF EXISTS collaborations_revision_rounds_check;

ALTER TABLE collaborations
  ADD CONSTRAINT collaborations_revision_rounds_check
  CHECK (revision_rounds >= 0);

CREATE TABLE IF NOT EXISTS collaboration_revision_history (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  collaboration_id UUID NOT NULL REFERENCES collaborations(id) ON DELETE CASCADE,
  revision_number  INTEGER NOT NULL,
  requested_by     UUID NOT NULL REFERENCES profiles(id) ON DELETE RESTRICT,
  notes            JSONB NOT NULL DEFAULT '[]'::jsonb,
  overall_note     TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (collaboration_id, revision_number),
  CHECK (revision_number > 0)
);

CREATE INDEX IF NOT EXISTS idx_collab_revision_history_collaboration
  ON collaboration_revision_history(collaboration_id, created_at DESC);

COMMENT ON COLUMN collaborations.revision_rounds IS
  'Number of brand revision rounds consumed. MVP allows one free round.';

COMMENT ON TABLE collaboration_revision_history IS
  'Immutable audit history of brand revision requests for collaborations.';
