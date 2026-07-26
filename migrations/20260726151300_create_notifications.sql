-- Migration: 014 - Create Notifications Table
-- Description: User notifications for applications, messages, collaborations
-- Applied: 2026-07-26

CREATE TABLE IF NOT EXISTS notifications (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id   UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  type         TEXT NOT NULL CHECK (type IN (
               'application_received', 'application_accepted', 'application_rejected',
               'revision_requested', 'application_resubmitted', 'campaign_invite_received',
               'new_message', 'collaboration_completed'
             )),
  title        TEXT NOT NULL,
  body         TEXT NOT NULL,
  related_id   UUID,
  is_read      BOOLEAN NOT NULL DEFAULT false,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notifications_profile_unread ON notifications(profile_id, is_read);
CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at DESC);
