-- Migration: chat realtime broadcast + presence authorization
-- Description: AFTER INSERT trigger broadcasts new public.messages rows
--   (typed chat and kind=event system rows) to private Realtime topic
--   conversation:{uuid}. RLS on realtime.messages lets participants join;
--   profile_id is profiles.id, auth.uid() is profiles.auth_id.
-- Applied: 2026-08-22

CREATE OR REPLACE FUNCTION public.chat_broadcast_new_message()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  PERFORM realtime.broadcast_changes(
    'conversation:' || NEW.conversation_id::text,
    TG_OP,
    TG_OP,
    TG_TABLE_NAME,
    TG_TABLE_SCHEMA,
    NEW,
    OLD
  );
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_chat_broadcast_new_message ON public.messages;
CREATE TRIGGER trg_chat_broadcast_new_message
AFTER INSERT ON public.messages
FOR EACH ROW
EXECUTE FUNCTION public.chat_broadcast_new_message();

REVOKE EXECUTE ON FUNCTION public.chat_broadcast_new_message() FROM PUBLIC, anon, authenticated;

GRANT SELECT ON public.profiles TO authenticated;
GRANT SELECT ON public.conversation_participants TO authenticated;

DROP POLICY IF EXISTS "profiles_select_own" ON public.profiles;
CREATE POLICY "profiles_select_own"
ON public.profiles
FOR SELECT
TO authenticated
USING (auth_id = (SELECT auth.uid()));

DROP POLICY IF EXISTS "conversation_participants_select_own" ON public.conversation_participants;
CREATE POLICY "conversation_participants_select_own"
ON public.conversation_participants
FOR SELECT
TO authenticated
USING (
  profile_id = (
    SELECT p.id FROM public.profiles p WHERE p.auth_id = (SELECT auth.uid())
  )
);

-- Fail closed: only well-formed conversation:<uuid> topics are considered.
CREATE OR REPLACE FUNCTION public.is_conversation_realtime_participant()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = public
AS $$
  SELECT
    (SELECT realtime.topic()) ~ '^conversation:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    AND EXISTS (
      SELECT 1
      FROM public.conversation_participants cp
      JOIN public.profiles p ON p.id = cp.profile_id
      WHERE cp.conversation_id = split_part((SELECT realtime.topic()), ':', 2)::uuid
        AND p.auth_id = (SELECT auth.uid())
    );
$$;

REVOKE EXECUTE ON FUNCTION public.is_conversation_realtime_participant() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.is_conversation_realtime_participant() TO authenticated;

DROP POLICY IF EXISTS "chat_participants_can_receive_broadcast_and_presence" ON realtime.messages;
CREATE POLICY "chat_participants_can_receive_broadcast_and_presence"
ON realtime.messages
FOR SELECT
TO authenticated
USING (
  public.is_conversation_realtime_participant()
  AND realtime.messages.extension IN ('broadcast', 'presence')
);

DROP POLICY IF EXISTS "chat_participants_can_track_presence" ON realtime.messages;
CREATE POLICY "chat_participants_can_track_presence"
ON realtime.messages
FOR INSERT
TO authenticated
WITH CHECK (
  public.is_conversation_realtime_participant()
  AND realtime.messages.extension = 'presence'
);
