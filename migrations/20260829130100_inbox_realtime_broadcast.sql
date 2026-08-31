-- Broadcast committed messages to each participant's private inbox topic.

CREATE OR REPLACE FUNCTION public.is_inbox_realtime_owner()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = public
AS $$
  SELECT
    (SELECT realtime.topic()) ~ '^inbox:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    AND EXISTS (
      SELECT 1
      FROM public.profiles p
      WHERE p.id = split_part((SELECT realtime.topic()), ':', 2)::uuid
        AND p.auth_id = (SELECT auth.uid())
    );
$$;

REVOKE EXECUTE ON FUNCTION public.is_inbox_realtime_owner() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.is_inbox_realtime_owner() TO authenticated;

DROP POLICY IF EXISTS "inbox_owner_can_receive_broadcast" ON realtime.messages;
CREATE POLICY "inbox_owner_can_receive_broadcast"
ON realtime.messages FOR SELECT TO authenticated
USING (
  public.is_inbox_realtime_owner()
  AND realtime.messages.extension = 'broadcast'
);

CREATE OR REPLACE FUNCTION public.inbox_broadcast_new_message()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  participant RECORD;
BEGIN
  FOR participant IN
    SELECT profile_id
    FROM public.conversation_participants
    WHERE conversation_id = NEW.conversation_id
  LOOP
    PERFORM realtime.broadcast_changes(
      'inbox:' || participant.profile_id::text,
      TG_OP,
      TG_OP,
      TG_TABLE_NAME,
      TG_TABLE_SCHEMA,
      NEW,
      OLD
    );
  END LOOP;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_inbox_broadcast_new_message ON public.messages;
CREATE TRIGGER trg_inbox_broadcast_new_message
AFTER INSERT ON public.messages
FOR EACH ROW
EXECUTE FUNCTION public.inbox_broadcast_new_message();

REVOKE EXECUTE ON FUNCTION public.inbox_broadcast_new_message() FROM PUBLIC, anon, authenticated;
