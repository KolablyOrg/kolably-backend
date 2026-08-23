-- Migration: Add composite index for conversation queries
-- Description: Index on (conversation_id, sender_id, created_at) to support
--   count_unread and list_messages queries that filter by sender_id and
--   range-scan created_at. Without this index, .neq("sender_id") forces a
--   full table scan of all messages in the conversation.

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id_sender_created_at
ON messages (conversation_id, sender_id, created_at);