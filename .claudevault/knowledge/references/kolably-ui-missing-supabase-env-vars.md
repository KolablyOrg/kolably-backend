# kolably_ui production Realtime was broken by TWO stacked bugs: missing env vars, then a CSP block

parent:: [[context]]
source:: diagnosed via progressively more granular [[decisions/002-notifications-realtime-via-supabase]] debug logging
date:: 2026-08-23
saved-because:: this is the actual root cause of "live notifications don't work" and very likely also explains chat's live delivery never having worked in production either — a standing, previously-undetected bug, not something this session introduced.

## Summary
`getSupabase()` in `src/lib/supabase.ts` requires both `VITE_SUPABASE_URL`
and `VITE_SUPABASE_ANON_KEY` to be truthy or it returns `null` (no
fallback). Confirmed via console logging added to
`useNotificationsRealtime.ts` (see [[decisions/002-notifications-realtime-via-supabase]])
that in production (`kolably.com`), `getSupabase()` returns `null` — i.e.
these two env vars are `undefined` in the deployed build.

Root cause: `.env` is gitignored in `kolably_ui` (only the empty
`.env.example` template is tracked), so Vercel's build has zero access to
the real values unless someone separately entered them into the Vercel
project's **Environment Variables** settings. That was evidently never
done. Since these are `VITE_`-prefixed, Vite bakes them into the bundle
**at build time** — there's no way to fix this by just redeploying the
same build; a fresh build with the vars present is required, and a plain
"Redeploy" that reuses build cache may not pick up newly-added env vars.

## Relevance to this project
**This silently breaks Realtime for the entire webapp, not just
notifications.** Chat's live delivery (`useConversationRealtime`) uses the
exact same `getSupabase()` — it has almost certainly never actually
delivered a live message in production either. Nobody caught it because
chat's REST-based resync fallback (`resyncConversation`, polling on
visibilitychange/channel-error) still makes the feature *appear* to work,
just not live — the same symptom the user reported for notifications
("not popping until I refresh").

**Values needed in Vercel → kolably_ui project → Settings → Environment
Variables (Production)**:
```
VITE_SUPABASE_URL=https://uxngcuyrdmajydkqpiyi.supabase.co
VITE_SUPABASE_ANON_KEY=sb_publishable_Vt_Rt-c57DRKCQVQfI9DGg_uS_xP34H
```
(These are the publishable/anon key and project URL — safe to store openly,
not secrets, unlike the service-role key.)

If any *other* live/Realtime feature in `kolably_ui` is reported as "not
updating without a refresh," check this first — it's the single point of
failure for anything going through `getSupabase()`.

## Second bug, found immediately after fixing the first
Once the user added the env vars to Vercel and redeployed, the
`[notif-debug]` logging showed the effect now runs, `getSupabase()`
succeeds, and `syncSupabaseRealtimeAuth()` completes — but the channel
then immediately fails: `CHANNEL_ERROR ... Error: channel error: transport
failure`, followed by `CLOSED`/`TIMED_OUT` on retry. This is the classic
signature of a **Content-Security-Policy blocking the WebSocket
connection** — confirmed: `vercel.json`'s `connect-src` directive listed
`https://api.kolably.com` and various third-party origins, but never the
Supabase project origin at all, in either `https://` or `wss://` scheme.
Browsers enforce CSP `connect-src` against WebSocket connections too, so
the browser was silently refusing to even attempt the Realtime socket.

Fixed by adding both schemes to `connect-src`:
```
https://uxngcuyrdmajydkqpiyi.supabase.co wss://uxngcuyrdmajydkqpiyi.supabase.co
```
Committed as `da310a2` in `kolably_ui`, no other file needed changing (no
duplicate CSP `<meta>` tag exists in `index.html` — `vercel.json`'s header
is the single source of truth).

**Both bugs had to be fixed together** for Realtime to work at all — the
missing env vars alone would have caused `getSupabase()` to keep returning
`null` even with a correct CSP; the CSP block alone would have caused
`CHANNEL_ERROR` even with correct env vars. Either one alone fully explains
"live updates don't work, only REST fallback does," so if this regresses
again, check both independently rather than assuming it's "the same" issue
as before.

## Consequences for future work
Once this is fixed and redeployed, re-verify with the curl+grep technique
from [[knowledge/references/kolably-ui-vercel-deploy-gap]] (check the new
bundle is actually live), then have the user re-test both notifications
and chat live delivery. The temporary `[notif-debug]` logging in
`useNotificationsRealtime.ts` should be removed once confirmed working —
don't forget it's still in the deployed bundle as of this writing.

## Used in
- [[decisions/002-notifications-realtime-via-supabase]]
- [[logs/2026-08-23]]
