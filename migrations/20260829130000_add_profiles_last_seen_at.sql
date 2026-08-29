-- Global presence persistence and private global presence authorization.

ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ;

COMMENT ON COLUMN public.profiles.last_seen_at IS
  'Last server-side presence heartbeat; NULL means no heartbeat has been received.';

DROP POLICY IF EXISTS "global_presence_authenticated_select" ON realtime.messages;
CREATE POLICY "global_presence_authenticated_select"
ON realtime.messages FOR SELECT TO authenticated
USING (
  realtime.topic() = 'global:online-users'
  AND realtime.messages.extension = 'presence'
);

DROP POLICY IF EXISTS "global_presence_authenticated_insert" ON realtime.messages;
CREATE POLICY "global_presence_authenticated_insert"
ON realtime.messages FOR INSERT TO authenticated
WITH CHECK (
  realtime.topic() = 'global:online-users'
  AND realtime.messages.extension = 'presence'
);
