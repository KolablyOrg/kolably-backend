# Mobile Realtime was dead for the same reason web's was — nobody checked the mobile half

parent:: [[context]]
source:: investigating "chat doesn't auto-refresh / no push when app is minimised"
date:: 2026-08-29
saved-because:: this is the actual root cause of every "mobile isn't live" report, it fails completely silently, and the web version of this exact bug was already found and documented on 2026-08-23 without anyone thinking to check mobile.

## Summary
`mobile/.env` contains `EXPO_PUBLIC_API_BASE_URL`, the Google client IDs and
the Instagram client ID — but **not** `EXPO_PUBLIC_SUPABASE_URL` or
`EXPO_PUBLIC_SUPABASE_ANON_KEY`. In `mobile/lib/supabase.ts`:

```ts
if (!url || !key) return null;   // ← every Realtime feature silently off
```

Every consumer treats `null` as "don't subscribe" and returns early, so:
- `useConversationRealtime` never opens a channel → **no live chat messages,
  no typing indicator, no presence**
- `useNotificationsRealtime` (added 2026-08-29) never opens a channel → the
  badge falls back to polling

Nothing logs, nothing errors, nothing shows in Supabase's realtime logs
(the client never connects at all, so there's no connection to see failing).

## This is the same bug as the web one, on the other platform
[[knowledge/references/kolably-ui-missing-supabase-env-vars]] documents the
identical failure on web (`VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY`
missing from Vercel). That doc was written 2026-08-23 and correctly
predicted "if any *other* live/Realtime feature is reported as not updating
without a refresh, check this first" — but the check was never extended to
mobile, which has its own `.env`, its own prefix (`EXPO_PUBLIC_`), and its
own copy of `getSupabase()`.

**Lesson: when a config bug is found in one app of a monorepo-style pair,
check the sibling app for the same class of bug immediately.** The two
`getSupabase()` implementations are near-identical, so the bug was
guaranteed to be symmetrical.

## Why it survived so long
Chat's REST resync fallback makes the feature *appear* functional — messages
show up on open, on pull-to-refresh, and on app-foreground. Only the "live"
part is missing, which reads as slowness rather than breakage. The
2026-08-29 session even correctly diagnosed and fixed a *real, separate*
Supabase presence rate-limit bug (`8205fd5`) in `useConversationRealtime`
while this was the actual blocker — worth noting that the presence bug was
real and worth fixing, it just could never have been the cause, because on
that device the channel was never created in the first place.

## Fix
Values (anon/publishable key — safe to commit, not the service-role key):
```
EXPO_PUBLIC_SUPABASE_URL=https://uxngcuyrdmajydkqpiyi.supabase.co
EXPO_PUBLIC_SUPABASE_ANON_KEY=sb_publishable_Vt_Rt-c57DRKCQVQfI9DGg_uS_xP34H
```

1. Add both to `mobile/.env` (gitignored — must be done per-machine).
2. Restart Metro with `--clear`; `EXPO_PUBLIC_*` vars are inlined at bundle
   time, so a hot reload will not pick them up.
3. **For EAS builds**, set them on the build profile in `eas.json` or as EAS
   environment variables. `.env` is gitignored, so a cloud build gets
   nothing — otherwise Realtime works in local dev and ships dead.

Guardrails added 2026-08-29 so this can't fail silently again:
- `getSupabase()` now emits a one-shot `__DEV__` `console.warn` naming the
  two vars and the exact consequences.
- `mobile/.env.example` documents them as **required**, uncommented, with
  the EAS caveat.

## Relevance to this project
Single point of failure for all mobile Realtime. Check this before
investigating any "mobile isn't live" report — it costs one `grep` and rules
out (or confirms) the most likely cause instantly.

## Used in
- [[logs/2026-08-29]]
