# kolably_ui production deploy lags behind `main` — verify before trusting a push fixed something live

parent:: [[context]]
source:: discovered while verifying the Inbox crash fix on kolably.com
date:: 2026-08-23
saved-because:: pushing a fix to `main` does NOT mean it's live on kolably.com — confirmed concretely, not assumed. Anyone (including a future session) who tells the user "should be fixed now" right after a push, without checking the actual deployed bundle, will be wrong.

## Summary
`kolably_ui` deploys to **kolably.com** via Vercel (`vercel.json` present in
repo root; no deploy step in `.github/workflows/ci.yml`, which only runs
lint+test). After pushing a fix to `main` (commit `c7cb993`, see
[[decisions/002-notifications-realtime-via-supabase]]'s incident log in
[[logs/2026-08-23]]) and the user reporting the bug still reproduced live,
I verified directly against production and confirmed **the deploy had not
picked up the fix** — Vercel was still serving a build from an earlier
commit (`5066a19`), one that predates the merge containing the fix. This
was not a caching illusion on the user's end; the CDN was correctly serving
the actual latest *deployed* build, which simply wasn't the actual latest
*pushed* commit.

## How to verify this without Vercel dashboard/API access
This session had no Vercel credentials, yet could still get a definitive
answer by fetching the production bundle directly and checking it byte-for-byte:

```bash
curl -s https://kolably.com/ | grep -oE '/assets/index-[a-zA-Z0-9_-]+\.js'
curl -s https://kolably.com/assets/index-<hash>.js -o /tmp/prod-bundle.js
grep -o "<a string unique to your fix's commit>" /tmp/prod-bundle.js
grep -o "<a string unique to a commit BEFORE your fix>" /tmp/prod-bundle.js
```
Pick string literals (toast messages, labels) that are unique to specific
commits — they survive minification even though variable names don't. If
the bundle has strings from a commit that came chronologically *after* your
fix's parent but the actual buggy logic is still present in the minified
JS around a recognizable literal (e.g. search for a `"loading..."` label
string, then read the boolean expression immediately preceding its ternary
`?`), that proves the deployed build is a *different, in-between* commit —
not simply an old cached one. `curl -sI` cache headers (`x-vercel-cache`,
`age`) confirm whether the CDN itself is fresh, but only bundle-content
inspection tells you *which commit* is actually live.

## Relevance to this project
**After pushing a fix meant to resolve a live/production-reported bug in
`kolably_ui`, don't tell the user "should be fixed now" based on the git
push alone.** Either:
1. Ask the user to verify live (what happened here), or
2. Proactively curl-verify the production bundle using the technique above
   before claiming the fix is live.

This also means: **Vercel's deploy-per-push is not guaranteed to complete
promptly, or at all, without the user separately checking/triggering it in
the Vercel dashboard** — this session has no way to see or trigger Vercel
deploys directly (no Vercel MCP/CLI auth). If a live bug persists after a
push that should have fixed it, deploy lag/failure is a real, now-confirmed
possibility to check before re-diagnosing the code.

## Used in
- [[decisions/002-notifications-realtime-via-supabase]] — the Inbox crash
  incident this was discovered while verifying.
- [[logs/2026-08-23]]
