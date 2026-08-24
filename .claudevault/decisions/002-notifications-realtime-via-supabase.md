# 002 — Deliver live notifications via Supabase Realtime broadcast, not webhooks

parent:: [[context]]
date:: 2026-08-23
status:: accepted (implemented + applied)

## Context
Generic `notifications` (applications, collaborations, invoices, campaign
invites) were poll-only by explicit design (`docs/API_REQUIREMENTS.md:31-32`
— see [[knowledge/references/notification-architecture]]). The user asked
for the best procedure to make notifications live for the webapp — Supabase
Realtime or webhooks — and to draft it.

## Research that informed this
- [[knowledge/references/notification-architecture]] — full sweep confirming
  chat already has a Supabase Realtime broadcast trigger + RLS pattern
  (`migrations/20260822100000_chat_realtime_broadcast.sql`), while
  `notifications` had none.

## Decision
Use Supabase Realtime (DB trigger → `realtime.broadcast_changes` → private
topic, gated by RLS on `realtime.messages`), mirroring the existing chat
pattern — **not** Database Webhooks — as the mechanism for pushing live
notification updates to the webapp.

Rationale:
1. Webhooks are a server-to-server callback (Postgres → HTTP endpoint); they
   don't push to a connected browser. Reaching the browser still requires
   Realtime/WebSocket/SSE downstream, so webhooks alone don't solve "live in
   the webapp" — they'd just add a redundant hop.
2. Chat already proves this exact pattern works in this codebase and this
   Supabase project; reusing it means one subscription model for the
   frontend instead of two.
3. No new infrastructure/dependency — pure SQL migration, same deploy path
   as every other schema change here.
4. Same RLS/security convention as chat (`profiles.auth_id = auth.uid()`
   scoping), so no new auth pattern to teach the frontend.

Implemented as `migrations/20260823150000_notifications_realtime_broadcast.sql`:
- `notifications_broadcast_new()` — `AFTER INSERT` trigger function broadcasting
  to topic `notifications:{profile_id}`.
- `is_notification_realtime_owner()` — fail-closed check: topic must be
  `notifications:<uuid>` and that uuid must be the caller's own `profiles.id`.
- RLS policy `notification_owner_can_receive_broadcast` on `realtime.messages`
  (SELECT-only, broadcast extension) — reuses the `profiles_select_own`
  policy already created by the chat migration.
- Also fixed doc drift found while touching this: `docs/schema.sql`'s
  `notifications.type` CHECK was missing 4 types added in
  `migrations/20260815120000_add_collaboration_notifications.sql`; added a
  Realtime note there and to `migrations/README.md`'s history table.

Webhooks were noted as the *right* tool for a different, later need: relaying
to genuinely server-side channels (mobile push via FCM/APNs, outbound email)
where there's no browser WebSocket involved — that's additive, not a
replacement for this.

## Consequences
- Webapp subscription code is now written (in the sibling repo `kolably_ui`,
  not this repo): `src/lib/notificationRealtime.ts` +
  `src/hooks/useNotificationsRealtime.ts` mirror the existing chat realtime
  files 1:1, wired into `src/components/dashboard/NotificationBell.tsx`
  (subscribes to `notifications:{profileId}` off `user.id` from
  `useAuth()`, which is confirmed to be `profiles.id`). Typechecked and
  linted clean.
- `GET /notifications/unread-count` polling stays in place as a correctness
  backstop on load/reconnect — Realtime is the "instant nudge," not the sole
  source of truth. Implemented as the existing fetch logic extracted into a
  `refresh()` callback, reused as both the mount-time fetch and the
  realtime-hook's `onResync`.
- **Known scoping limit, left as a decision for the user**:
  `NotificationBell` only mounts on the two Overview pages (brand/creator),
  not a shared layout — so the live subscription (and the unread badge)
  only stays live while on Overview. Lifting it into a shared context/layout
  for app-wide live updates was flagged but not done — awaiting user
  direction.
- **Applied**: once the user reconnected Supabase MCP to the correct
  project (`uxngcuyrdmajydkqpiyi`, confirmed via `list_projects` and
  `list_tables` matching this repo's known schema — `notifications` had 118
  rows, `chat_realtime_broadcast` migration already present), the migration
  was run via `apply_migration` and verified live: trigger
  `trg_notifications_broadcast_new` exists on `public.notifications`
  (enabled), and RLS policy `notification_owner_can_receive_broadcast`
  exists on `realtime.messages` alongside the pre-existing chat policies.
  Recorded in Supabase's migration history as
  `20260823113653_notifications_realtime_broadcast`.
- The still-unenforced `notification_preferences` gap ([[knowledge/references/notification-architecture]])
  is unaffected by this — a muted notification still gets created and
  broadcast; that's a separate fix in `notification_service.py`/producers.

## Related decisions
- [[decisions/001-constitution-ratified]] — this migration follows the
  constitution's "one migration, timestamped, idempotent" convention and its
  RLS/auth conventions.

## Session
- [[logs/2026-08-23]]
