-- Migration: 029 - Notifications Realtime broadcast
-- Description: AFTER INSERT trigger broadcasts new public.notifications rows
--   to private Realtime topic notifications:{profile_id}. RLS on
--   realtime.messages lets only the owning profile subscribe;
--   profile_id is profiles.id, auth.uid() is profiles.auth_id.
--   Mirrors migrations/20260822100000_chat_realtime_broadcast.sql.
-- Applied: 2026-08-23

CREATE OR REPLACE FUNCTION public.notifications_broadcast_new()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  PERFORM realtime.broadcast_changes(
    'notifications:' || NEW.profile_id::text,
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

DROP TRIGGER IF EXISTS trg_notifications_broadcast_new ON public.notifications;
CREATE TRIGGER trg_notifications_broadcast_new
AFTER INSERT ON public.notifications
FOR EACH ROW
EXECUTE FUNCTION public.notifications_broadcast_new();

REVOKE EXECUTE ON FUNCTION public.notifications_broadcast_new() FROM PUBLIC, anon, authenticated;

-- profiles_select_own already exists (created by
-- 20260822100000_chat_realtime_broadcast.sql) and is reused here so the
-- ownership check below can resolve auth.uid() -> profiles.id.

-- Fail closed: only well-formed notifications:<uuid> topics are considered,
-- and only when that uuid is the caller's own profile id.
CREATE OR REPLACE FUNCTION public.is_notification_realtime_owner()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = public
AS $$
  SELECT
    (SELECT realtime.topic()) ~ '^notifications:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
    AND EXISTS (
      SELECT 1
      FROM public.profiles p
      WHERE p.id = split_part((SELECT realtime.topic()), ':', 2)::uuid
        AND p.auth_id = (SELECT auth.uid())
    );
$$;

REVOKE EXECUTE ON FUNCTION public.is_notification_realtime_owner() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.is_notification_realtime_owner() TO authenticated;

DROP POLICY IF EXISTS "notification_owner_can_receive_broadcast" ON realtime.messages;
CREATE POLICY "notification_owner_can_receive_broadcast"
ON realtime.messages
FOR SELECT
TO authenticated
USING (
  public.is_notification_realtime_owner()
  AND realtime.messages.extension = 'broadcast'
);
