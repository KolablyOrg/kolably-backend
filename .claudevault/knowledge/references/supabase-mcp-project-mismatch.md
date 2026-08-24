# Supabase MCP connection points to a different project than kolably_backend

parent:: [[context]]
source:: discovered while trying to apply migrations/20260823150000_notifications_realtime_broadcast.sql
date:: 2026-08-23
saved-because:: nearly caused a migration to be run against the wrong live database — this must be checked every time before any Supabase MCP write (apply_migration, execute_sql, etc.) in this repo, and re-checked after the user reconnects MCP since the mismatch may or may not be resolved.

## Summary
The Supabase MCP tool connection available in this session (`mcp__claude_ai_Supabase__*`)
only has access to **one project: "LIFT"** (ref `msffgbuwnlemuoantcet`, org
`shawbtakjknqpwvdssnw`, region ap-south-1). `list_tables` on it returns
`exercises`, `workout_templates`, `workout_days`, `workout_sessions`,
`exercise_sessions`, `sets`, `body_metrics`, `cardio_sessions`,
`personal_records`, `exercise_notes` — a fitness/workout-tracking app, with
real data (607 exercise_sessions rows, 94 personal_records, etc.). This is
almost certainly the Supabase project behind the peer session named
`getfitwithsky-5b` seen via `ListAgents`, **not** Kolably.

**The actual `kolably_backend` Supabase project** is
`https://uxngcuyrdmajydkqpiyi.supabase.co` (from `.env`'s `SUPABASE_URL` —
confirmed live/current value; a second, commented-out `SUPABASE_URL` for
`wxylbgvzlqhvnwssnqcl.supabase.co` also exists in `.env`, likely an older or
staging project — don't assume which one is authoritative without asking).
Its project ref (the `xxxx` in the URL) was not resolved to a Supabase
project ref via MCP, since MCP can't see it — `list_projects` only returned
"LIFT".

## Relevance to this project
**Any use of `mcp__claude_ai_Supabase__*` tools in a `kolably_backend`
session must first confirm `list_projects` includes a project whose ref
resolves to `uxngcuyrdmajydkqpiyi` (or whatever `.env`'s current
`SUPABASE_URL` says) before calling anything mutating** (`apply_migration`,
`execute_sql`, `pause_project`, etc.). If only "LIFT" (or another
unrelated project) shows up, stop and ask the user rather than proceeding —
running Kolably migrations/queries against LIFT would fail on missing
tables at best, and risk touching unrelated real user data at worst.

The user was asked (this session) how to apply
`migrations/20260823150000_notifications_realtime_broadcast.sql`, and chose
to reconnect the Supabase MCP to the correct project rather than apply it
manually or skip. **Re-check `list_projects` after any "I've reconnected
Supabase" signal from the user** — don't assume the old "LIFT"-only result
still holds, and don't assume the reconnect fixed it either.

## Used in
- [[decisions/002-notifications-realtime-via-supabase]] — the migration this
  mismatch blocked from being applied.
- [[logs/2026-08-23]]
