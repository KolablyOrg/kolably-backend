<!--
Sync Impact Report
Version change: [TEMPLATE] → 1.0.0
Modified principles: n/a (initial ratification)
Added sections: Core Principles (I-VI), Technology & Scope Constraints, Development Workflow, Governance
Removed sections: none
Deferred TODOs: none — all placeholders resolved from app/, AGENTS.md, and README.md.
Templates requiring follow-up: none (plan/spec/tasks templates already reference "Constitution Check" generically; no template text names a specific principle that would drift).
-->

# Kolably Backend Constitution

## Core Principles

### I. Layered Architecture: Routes → Services → Repositories
Every domain has exactly one file in each of `routes/`, `schemas/`, and `services/`,
plus a repository extending `BaseRepository`. Routes parse/validate input, enforce
auth via a dependency, call exactly one service function, and return its result —
no Supabase calls, no business rules, no manual status-code branching in routes.
Services own all business rules and raise `HTTPException`; repositories are the
only layer that talks to Supabase, always through `self._execute(...)`, never a
bare `.execute()`. A new domain mirrors the shape of the closest existing one
(e.g. `campaigns.py` → `campaign_service.py` → `campaign_repo.py`) rather than
inventing a new pattern.
**Rationale**: this separation is what makes services unit-testable against fake
repositories without a live Supabase instance, and keeps authorization logic in
one auditable place instead of scattered across HTTP handlers.

### II. Authorization Is Verified in Python, Never Assumed From the Database (NON-NEGOTIABLE)
The service-role Supabase client bypasses Row Level Security, so there is no
database-level backstop — every write path that touches another user's row
(an application, a collaboration, a conversation) MUST perform an explicit
ownership or role check before the query, following the `_ensure_campaign_owner`
pattern: 404 if the resource doesn't exist, 403 if it exists but isn't
owned/accessible by the caller, and never a 403 that leaks the existence of a
resource that doesn't exist. `require_role(*roles)` is used as a dependency
factory instead of hand-rolled `if current_user.role != ...` checks, but role
alone is insufficient where a transition is gated by direction (e.g.
`creator_applied` vs. `business_invited` on applications) — that logic belongs
in the service function, not the route dependency.
**Rationale**: "the DB would reject it anyway" is false under a service-role
client; treating authorization as a Python-only concern prevents the class of
bug where a path/body ID reaches a query unverified.

### III. No Silent Stubs, No Leaked Internal Fields
A route left as a bare `pass` returns `None`, which FastAPI serializes as a
silent `200 OK` — indistinguishable from "working but empty." An unimplemented
route MUST raise `HTTPException(status_code=501, detail="Not implemented")`
instead of being merged in a bare-`pass` state. Symmetrically, every route
declares `response_model=...` (never a raw dict), and internal-only fields
(e.g. `instagram_access_token`, `instagram_user_id`) never appear in a
`*Response` schema — any new sensitive column is checked against every
response schema that could accidentally serialize it.
**Rationale**: both failure modes are silent by default (a 200 with no body,
or a response that leaks a token) and only caught by discipline at write time,
not by any framework guardrail.

### IV. Status Values and Notifications Are Modeled, Not Improvised
All status/type fields are `str, Enum` in `app/core/enums.py`, mapped 1:1 to
`TEXT + CHECK` columns (never native Postgres enums) — a new value is added to
the enum and shipped as a timestamped migration that drops and re-adds the
`CHECK` constraint, never a bare string scattered across files. Notifications
are created as a side effect inside the service function that drives the state
transition (e.g. `application_service` inserts a `NotificationType.*` row when
it flips an application's status), never from the route layer and never as a
separately-called "notification service" step. Any new status-changing
endpoint is checked against `docs/API_REQUIREMENTS.md §8` for a required
notification before it ships.
**Rationale**: a single source of truth for enums keeps schemas and services
in sync; colocating the notification insert with the transition that causes it
keeps the two from drifting apart as new transitions are added.

### V. Tests Live in `tests/`, Not Just in Smoke Scripts
Every new service function that isn't a trivial passthrough gets a test in
`tests/`, run with `pytest`, testing through the service layer (not
hand-rolled assertions directly against Supabase) so tests don't silently
drift from what the route actually calls. The minimum bar for a new domain's
PR is: a happy-path test per write endpoint, one 403/404 ownership test, and
one validation-failure test. Standalone scripts (`scripts/test_*.py`,
`scripts/smoke_*.py`) are acceptable for manual end-to-end verification
against a live server but are never a substitute for `tests/` coverage, and
must never embed real credentials.
**Rationale**: the ownership-check pattern in Principle II is exactly the kind
of logic that silently regresses without a dedicated 403/404 test — smoke
scripts against a live server don't run in CI and don't catch it.

### VI. Config, Secrets, and Async I/O Discipline
All configuration flows through `app/core/config.py` (`pydantic-settings`);
no `os.environ.get(...)` scattered in route/service files. `.env` is never
committed, and any credential that ever touched a public repo is treated as
compromised and rotated, not just removed from the file. Every route and every
service function that performs I/O is `async def`; no blocking call (`requests`,
a sync Supabase client method) runs inside an `async def` — use the async
client or `httpx.AsyncClient`. Formatting and linting is `ruff` only
(`[tool.ruff]` in `pyproject.toml`) — no second formatter is added without
updating both `pyproject.toml` and `AGENTS.md`.
**Rationale**: Supabase clients bind to the event loop that created them, so a
blocking call or a cached client silently breaks under pytest/TestClient in a
way that's hard to diagnose after the fact; secret hygiene here is the only
thing standing between a leaked key and a compromised production database.

## Technology & Scope Constraints

- **Stack**: FastAPI (`async def` routes) on Uvicorn; Supabase (Postgres +
  Supabase Auth) for data and auth, accessed via anon client (auth operations,
  RLS-respecting) or service-role admin client (everything else, RLS-bypassing
  — see Principle II).
- **Out of scope for MVP**: Razorpay payment flows (keys exist in config but
  are unused — display-only offer text), websockets (chat/notifications are
  polled by the client), proxied file uploads (clients upload directly to
  Supabase Storage; the backend only stores the resulting URL), and
  YouTube/TikTok integration (self-reported only). Do not build these unless
  explicitly asked.
- **Instagram/Meta integration**: token fields are internal-only (Principle
  III) and must be encrypted at rest; `sync` re-fetches from the Graph API
  only when stale (>24h), not on every read; for `platform=instagram`
  submissions, metrics always come from the Graph API, never client-supplied
  values.
- **Migrations**: schema changes are timestamped, idempotent SQL files in
  `migrations/` (`YYYYMMDDHHMMSS_description.sql`), applied via Supabase CLI
  or the SQL Editor in chronological order — there is no ORM-managed migration
  runner. Every new foreign key gets an explicit `ON DELETE` behavior chosen
  deliberately, never the Postgres default.

## Development Workflow

- New env vars are added to `.env.example` in the same commit and called out
  in the PR description — CI/CD only copies forward an existing `.env` on
  deploy, so a missing var breaks production silently rather than failing the
  deploy.
- `docs/schema.sql` and `app/docs/db_schema.md` are regenerated from applied
  migrations, not hand-edited ahead of them; migrations are the ground truth
  when the two disagree.
- Before a PR is considered done: new routes have `response_model` and call
  exactly one service function; every write path has an explicit
  ownership/role check; no bare `pass` or silent-`None` 200s remain; new enum
  values have a matching `CHECK`-constraint migration; new sensitive columns
  are checked against every response schema; required notification side
  effects are added; tests exist under `tests/`; `.env.example` is updated if
  needed.
- `ruff check` (and `ruff format` if introduced) runs locally before a task is
  considered finished — CI currently only builds and deploys, it does not run
  `ruff`/`pytest`, so this step is not enforced automatically yet.

## Governance

This constitution supersedes ad hoc convention for anything it covers;
`AGENTS.md` is the detailed implementation guide that operationalizes these
principles and is expected to evolve more frequently than this document.
Where the two conflict, this constitution wins and `AGENTS.md` is updated to
match in the same change.

Amendments are made by editing this file directly, incrementing the version
per semantic versioning (MAJOR: a principle is removed or redefined
incompatibly; MINOR: a principle or section is added or materially expanded;
PATCH: wording/clarification with no rule change), and updating the Sync
Impact Report comment at the top of the file. Every PR that changes behavior
covered by a Core Principle is expected to comply with it or state explicitly
in the PR description why an exception applies.

**Version**: 1.0.0 | **Ratified**: 2026-08-22 | **Last Amended**: 2026-08-22
