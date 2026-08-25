-- Migration: two-sided collaboration close
-- Description: a collaboration could previously reach 'completed' from the
-- business side alone — both PATCH /complete and POST /confirm-payment set
-- 'completed' directly, and neither required the creator to acknowledge
-- anything. A brand could therefore close out (and permanently terminate)
-- a collaboration without the creator ever confirming they were paid.
--
-- This adds the missing half of the handshake:
--   'payment_confirmed' — a new intermediate state. The business has said
--   they sent the money, but the creator hasn't confirmed receiving it.
--   The collaboration is NOT over yet.
--   creator_confirmed_at — set when the creator confirms receipt, which is
--   what now actually moves the row to 'completed'.
--
-- Ordering is deliberate: money moves first, creator confirms second.
-- Kolably never holds the funds (see confirm_payment's docstring), so the
-- creator confirming *receipt* is the only signal that the payment
-- actually landed. A creator sign-off taken before payment would confirm
-- nothing useful.
-- Applied: 2026-08-25

-- 1. New lifecycle state, inserted between live_submitted and completed.
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
    'payment_confirmed'::text,
    'completed'::text,
    'cancelled'::text
  ]));

-- 2. The creator's half of the handshake.
ALTER TABLE collaborations
  ADD COLUMN IF NOT EXISTS creator_confirmed_at TIMESTAMP WITH TIME ZONE;

COMMENT ON COLUMN collaborations.creator_confirmed_at IS
  'When the creator confirmed they received payment and the collaboration is done — set by POST /collaborations/{id}/confirm-completion, or by the 7-day auto-confirm job when the creator never responds. This, not payment_confirmed_at, is what moves the row to ''completed''.';

COMMENT ON COLUMN collaborations.payment_confirmed_at IS
  'When the business confirmed they paid the creator directly (Kolably does not process payment) — set by POST /collaborations/{id}/confirm-payment, which moves the row to ''payment_confirmed'', NOT to ''completed''. The creator must still confirm receipt.';

-- 3. Backfill. Existing 'completed' rows closed under the old one-sided
--    rules and must stay closed — reopening live collaborations to chase a
--    confirmation that was never asked for would be worse than the bug.
--    They get creator_confirmed_at = completed_at so the column is never
--    ambiguously NULL on a terminal row, and so the auto-confirm job below
--    can rely on "payment_confirmed status" alone to find its candidates.
--    collaborations has no updated_at column (verified against live schema
--    2026-08-25) — falls back to created_at only.
UPDATE collaborations
   SET creator_confirmed_at = COALESCE(completed_at, created_at)
 WHERE status = 'completed'
   AND creator_confirmed_at IS NULL;

-- 4. Index for the daily auto-confirm sweep, which scans for
--    payment_confirmed rows older than the grace window. Partial index —
--    only a handful of rows sit in this state at any time.
CREATE INDEX IF NOT EXISTS idx_collaborations_awaiting_creator_confirmation
    ON collaborations (payment_confirmed_at)
 WHERE status = 'payment_confirmed';

-- 5. New notification type for "the business says they paid you, please
--    confirm". notifications.type is CHECK-constrained (see migration
--    20260815120000), so the insert in confirm_payment would fail outright
--    without this — the full list has to be restated, Postgres has no
--    "add a value to an existing CHECK" syntax.
ALTER TABLE notifications
  DROP CONSTRAINT IF EXISTS notifications_type_check;

ALTER TABLE notifications
  ADD CONSTRAINT notifications_type_check CHECK (
    type IN (
      'application_received', 'application_accepted', 'application_rejected',
      'revision_requested', 'application_resubmitted', 'campaign_invite_received',
      'new_message', 'collaboration_completed', 'invoice_received',
      'collaboration_content_submitted', 'collaboration_draft_approved',
      'collaboration_live_verified', 'collaboration_payment_confirmed'
    )
  );
