-- Migration: 013 - Create Conversation Reads Table
-- Description: Tracks last read timestamp per user per conversation for unread counts
-- Applied: 2026-07-26

CREATE TABLE IF NOT EXISTS conversation_reads (
  conversation_id  UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  profile_id       UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  last_read_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (conversation_id, profile_id)
);
