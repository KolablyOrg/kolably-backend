# Notification system architecture — what's built vs. missing

parent:: [[context]]
source:: full-repo sweep by Explore subagent, this session
date:: 2026-08-23
saved-because:: answers a recurring question ("does live notification work for the webapp?") that requires a cross-file sweep to re-derive — DB migrations, service code, and docs all had to be cross-checked against each other.

## Summary

**In-app notifications (the `notifications` table) are fully built for CRUD/polling, but there is no live push channel for them — this is a deliberate, documented design decision, not a gap.**

### Fully built
- `notifications` table (`app/models/notification.py`, `notification_repo.py`,
  `notification_service.py`, `api/routes/notifications.py`), 12 typed
  `NotificationType` values (`app/core/enums.py:85-97`).
- 4 REST endpoints, all auth-gated: `GET /notifications/`, `GET
  /notifications/unread-count`, `PATCH /notifications/{id}/read`, `PATCH
  /notifications/read-all`. Matches `docs/API_REQUIREMENTS.md:596-634`.
- Producers wired into `application_service.py`, `collaboration_service.py`,
  `chat_service.py` (new message → notify other participants),
  `campaign_service.py` (invite received), `invoice_service.py`.
- Full unit test coverage (`tests/test_notification_service.py`), including
  the "swallow repo errors, fire-and-forget" contract.

### Gap: preferences are stored but not enforced
`creators.notification_preferences` / `businesses.notification_preferences`
(JSONB, e.g. `brand_messages`, `payment_alerts`) are read/written via the
profile-settings endpoints, but **never read by `notification_service.py` or
any producer**. Toggling a preference off in the UI has zero backend effect —
every notification still fires. Flag this before anyone builds a
"notification settings" screen that expects real suppression.

### Live delivery — the key finding
- `docs/API_REQUIREMENTS.md:31-32`: *"Chat and notifications are polled by
  the client, not pushed over a websocket."* — explicit design decision.
- **Chat has Supabase Realtime wired**: an `AFTER INSERT` trigger on
  `messages` (`migrations/20260822100000_chat_realtime_broadcast.sql`,
  `chat_broadcast_new_message()`) calls `realtime.broadcast_changes` to a
  private `conversation:{uuid}` topic, with matching RLS on
  `realtime.messages` scoping to actual participants.
- **The generic `notifications` table has no equivalent** — RLS is enabled
  on it but zero SELECT/UPDATE policies exist, no broadcast trigger, no
  publication wiring.
- No WebSocket, SSE, or push integration (FCM/APNs/OneSignal/web-push/
  Pusher/Ably) exists anywhere in the backend — no dependency installed, no
  device/token table. Confirmed via broad grep across `app/`.
- **Net effect for the webapp**: chat can be made live via Supabase Realtime
  today; generic notifications (applications, collaborations, invoices,
  campaign invites) are poll-only — the client must interval-poll
  `GET /notifications/unread-count` / `GET /notifications`.

### If live notifications are wanted later
Known path: replicate the chat pattern for `notifications` — add an `AFTER
INSERT` trigger broadcasting to a private `notifications:{profile_id}` topic
via `realtime.broadcast_changes`, plus an RLS policy on `realtime.messages`
scoping to `profiles.auth_id = auth.uid()`, mirroring
`migrations/20260822100000_chat_realtime_broadcast.sql`.

### Doc drift found (minor, but resolves an open question from vault init)
- `docs/PROJECT_STATUS.md` claims campaign invites don't fire notifications —
  stale; `campaign_service.py:836` fires `CAMPAIGN_INVITE_RECEIVED` now.
- `docs/schema.sql`'s CHECK constraint on `notifications.type` is missing 4
  types added in `migrations/20260815120000_add_collaboration_notifications.sql`.
- This also resolves the open question logged in
  [[logs/2026-08-23]] about whether chat was actually implemented despite
  `docs/PROJECT_STATUS.md` marking it "❌ Not implemented" — it is
  implemented, including the Realtime broadcast trigger; the status doc is
  stale there too.

## Relevance to this project
Directly answers "is notification delivery live for the webapp" — it is not,
by design, except chat. Any future work on a live notification bell should
start from the chat broadcast migration as a template.

## Used in
- [[logs/2026-08-23]]
- [[decisions/002-notifications-realtime-via-supabase]] — acted on this finding by adding the Realtime broadcast migration
