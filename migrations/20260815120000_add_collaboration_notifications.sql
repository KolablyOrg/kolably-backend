-- Migration: add collaboration lifecycle notification types
-- Description: supports notifications for content submission, draft approval,
-- and live-post verification side effects.

ALTER TABLE notifications
  DROP CONSTRAINT IF EXISTS notifications_type_check;

ALTER TABLE notifications
  ADD CONSTRAINT notifications_type_check CHECK (
    type IN (
      'application_received', 'application_accepted', 'application_rejected',
      'revision_requested', 'application_resubmitted', 'campaign_invite_received',
      'new_message', 'collaboration_completed', 'invoice_received',
      'collaboration_content_submitted', 'collaboration_draft_approved',
      'collaboration_live_verified'
    )
  );
