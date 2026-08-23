# Project Context

parent:: (root)

## Overview
**Kolably Backend** — FastAPI backend for the Kolably marketplace connecting
local businesses with content creators for collaboration campaigns
(business posts a campaign → creator applies/gets invited → collaboration →
content submission → chat). This repo is the API only; the web/mobile
frontend (`kolably_ui`) lives in a sibling repo under `/Users/sky/Documents/Kolably/`.

## Stack
- **Language/framework**: Python 3.11+, FastAPI
- **DB/Auth**: Supabase (Postgres + GoTrue auth), accessed via `supabase-py`
  - Service-role client bypasses RLS — auth checks are enforced in Python, not the DB (see [[decisions/001-constitution-ratified]])
- **Other deps**: pydantic v2, python-jose (JWT), passlib/bcrypt, pyotp (2FA), apscheduler, slowapi (rate limiting), pillow, httpx
- **Testing**: pytest + pytest-asyncio, services unit-tested against fake repositories (no live Supabase in tests today)
- **Lint**: ruff (line-length 120, py311)
- **Deploy**: Docker + nginx on EC2, GitHub Actions CI (`ruff` + `pytest` gate before deploy)
- **Governance**: managed via [GitHub spec-kit](https://github.com/) (`.specify/`) — `speckit-*` skills drive spec → plan → tasks → implement workflow; project constitution lives at `.specify/memory/constitution.md`

## Architecture
Layered: `routes/` (HTTP + auth dependency only) → `services/` (business logic,
unit-tested against fakes) → `repositories/` (only layer touching Supabase,
one per domain, extending `BaseRepository`). New domains mirror the closest
existing one (e.g. `campaigns.py` → `campaign_service.py` → `campaign_repo.py`).
Full rationale in [[decisions/001-constitution-ratified]].

## Goals
Ship a working MVP marketplace: auth → creator/business profiles → campaign
lifecycle → applications → collaborations → chat → notifications, then harden
for public launch (security, testing, staging).

## Module status (per `docs/PROJECT_STATUS.md`, last refreshed 2026-07-28 in that doc — verify against code before trusting for anything recent)
| Module | Status |
|---|---|
| Auth | ✅ Fully implemented |
| Creators | ✅ Fully implemented |
| Campaigns | ✅ Fully implemented |
| Businesses | ❌ Not implemented (route/schema stubs only) |
| Applications | ❌ Not implemented |
| Collaborations | ❌ Not implemented |
| Chat | ❌ Not implemented (though a Realtime broadcast migration for chat messages was added 2026-08-22 — recheck actual status) |

## Related repo: testing automation plan
A cross-repo testing automation plan exists at
`/Users/sky/Documents/Kolably/TESTING_AUTOMATION_PLAN.md` (covers both
`kolably_backend` and `kolably_ui`, dated 2026-08-23). Key gaps it identifies
for this repo: no integration tests against a real Supabase/Postgres (unit
tests use fakes only), no staging environment, no post-deploy smoke check.
See [[knowledge/references/testing-automation-plan]].

## Key People / Teams
See [[knowledge/people-and-teams/overview]]

---

## Decisions
- [[decisions/001-constitution-ratified]] — project constitution v1.0.0 ratified via spec-kit

## Session Logs
- [[logs/2026-08-23]]

## Knowledge
- [[knowledge/references/testing-automation-plan]]

## Raw Intake
_[[raw/]] — unprocessed material awaiting classification_

## Outputs
_[[outputs/]] — AI-generated reports and analyses_
