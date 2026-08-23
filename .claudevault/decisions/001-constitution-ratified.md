# 001 — Ratify Project Constitution v1.0.0 via spec-kit

parent:: [[context]]
date:: 2026-08-23
status:: accepted

## Context
The project adopted [GitHub spec-kit](https://github.com/github/spec-kit) for
spec → plan → tasks → implement workflow (`speckit-*` skills). As part of
install, a project constitution was ratified at `.specify/memory/constitution.md`,
codifying architectural rules that were previously only implicit in the
codebase/AGENTS.md. Commit: `d859ec3` — "chore: install spec-kit and ratify
project constitution v1.0.0".

## Research that informed this
- Derived from existing patterns in `app/`, `AGENTS.md`, and `README.md` (per the constitution's own Sync Impact Report — no external research, a codification pass)

## Decision
Ratified Constitution v1.0.0 with six core principles (I–VI):
1. **Layered Architecture**: routes → services → repositories, one file per domain per layer, no Supabase calls or business rules in routes.
2. **Authorization verified in Python, never assumed from the DB (NON-NEGOTIABLE)**: the service-role Supabase client bypasses RLS, so every write path touching another user's row needs an explicit ownership/role check (`_ensure_campaign_owner` pattern: 404 if missing, 403 if not owned, never leak existence).
3. **No silent stubs, no leaked internal fields**: unimplemented routes must raise `HTTPException(501)` instead of bare `pass` (which FastAPI silently serializes as `200 OK` / `null`); every route declares `response_model`; sensitive columns (e.g. `instagram_access_token`) must never appear in response schemas.
4. **Status values and notifications are modeled, not improvised**: all status/type fields are `str, Enum` in `app/core/enums.py`, mapped to `TEXT + CHECK` columns (never native Postgres enums).
5. (+ two more principles — see full text in `.specify/memory/constitution.md` for complete wording)

## Consequences
- Any new domain (e.g. Businesses, Applications, Collaborations, Chat — currently stubbed per [[context#Module status]]) must follow this shape from the start rather than improvising.
- The `501`-not-`pass` rule directly affects how the still-unimplemented modules should be finished — a bare `pass` merged today would violate the constitution.
- Future `speckit-plan`/`speckit-tasks` runs will be checked against this constitution as a gate.

## Related decisions
_none yet — first ADR in this vault_

## Session
- [[logs/2026-08-23]]
