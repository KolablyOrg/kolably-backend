# Project Status — What's Actually Implemented

A honest snapshot of what works vs. what's scaffolding, based on reading the
code as of 2026-07-21 (not on what the README/route names imply). All routes
below live under the `/api/v1` prefix and are wired up in
[`app/api/router.py`](../app/api/router.py).

## Summary

| Module | Status |
|---|---|
| Auth (signup, login, sessions, profile) | ✅ Fully implemented |
| Users | ⚠️ Stub only (dead code — superseded by `/auth/me`) |
| Creators | ❌ Not implemented (routes exist, return nothing) |
| Businesses | ❌ Not implemented |
| Campaigns | ❌ Not implemented |
| Applications | ❌ Not implemented |
| Collaborations | ❌ Not implemented |
| Chat | ❌ Not implemented |

**Only Auth is real end-to-end.** Every other domain has a route file that
defines the endpoint shape (path, method) and a matching Pydantic schema, but
the handler bodies are literally `# TODO: Implement` / `pass`, and the
corresponding `*_service.py` files contain nothing but TODO comments — no
function bodies at all. Calling any of these currently returns `null` with a
`200 OK` (FastAPI's default for a bare `pass`), not an error — worth knowing so
it isn't mistaken for "working but empty."

## ✅ Implemented: Auth (`/api/v1/auth`)

Backed by [`app/services/auth_service.py`](../app/services/auth_service.py),
a full facade over Supabase Auth + Postgres (`profiles`/`creators`/`businesses`
tables).

| Method | Path | Description |
|---|---|---|
| POST | `/auth/signup/creator` | Create Supabase auth user (role=creator) → insert `creators` row → return tokens |
| POST | `/auth/signup/business` | Same, for businesses |
| POST | `/auth/login` | Email/password login. Rejects unverified email or deactivated account |
| POST | `/auth/logout` | Invalidate current session |
| POST | `/auth/refresh` | Exchange refresh token for a new pair |
| POST | `/auth/forgot-password` | Sends Supabase password-reset email |
| POST | `/auth/reset-password` | Sets new password using the reset token |
| GET | `/auth/me` | Current user's profile + role-specific (`creator`/`business`) data |
| PATCH | `/auth/me` | Update profile fields on the role-specific table |

Supporting infra that's also done:
- **JWT verification** — [`app/core/security.py`](../app/core/security.py) decodes/validates the Supabase-issued JWT (HS256, `SUPABASE_JWT_SECRET`)
- **Auth dependency + RBAC** — [`app/core/dependencies.py`](../app/core/dependencies.py): `get_current_user` (checks JWT validity, email verified, account active) and `require_role(*roles)` factory for role-gating routes
- **Supabase clients** — anon client (auth ops) and service-role admin client (RLS-bypassing DB ops), in [`app/core/supabase.py`](../app/core/supabase.py)
- **Roles** — `creator`, `business`, `superadmin` ([`app/core/enums.py`](../app/core/enums.py))
- **DB side**: a Postgres trigger auto-creates a `profiles` row on Supabase auth signup; superadmin promotion is a manual SQL script ([`scripts/seed_superadmin.sql`](../scripts/seed_superadmin.sql)) run by hand in the Supabase dashboard
- `GET /health` — plain liveness check
- CORS middleware, configurable via `CORS_ORIGINS` env var

## ⚠️ Dead stub: Users (`/api/v1/users`)

`GET/PATCH/DELETE /users/me` are empty placeholders. They appear to
**duplicate** `/auth/me` (which is the one actually used) and have no service
file behind them at all. Worth deciding whether to delete this module or
repurpose it — right now it's dead code that could confuse whoever picks up
the next feature.

## ❌ Not implemented (route shape + schema only, no logic)

For each of these, the endpoint signatures and Pydantic request/response
schemas already exist (see `app/schemas/`), so the API *contract* is designed —
only the handler + service logic is missing.

**Creators** (`/api/v1/creators`, schema: [`app/schemas/creator.py`](../app/schemas/creator.py))
- `GET /` — list/search creators (filters: location, niche, follower range)
- `GET /{creator_id}` — public profile
- `PATCH /{creator_id}` — update own profile
- `GET /{creator_id}/portfolio`, `POST /{creator_id}/portfolio`, `DELETE /{creator_id}/portfolio/{item_id}` — portfolio CRUD

**Businesses** (`/api/v1/businesses`, schema: [`app/schemas/business.py`](../app/schemas/business.py))
- `GET /` — list/search
- `GET /{business_id}` — public profile
- `PATCH /{business_id}` — update own profile
- `GET /{business_id}/campaigns` — campaigns for a business

**Campaigns** (`/api/v1/campaigns`, schema: [`app/schemas/campaign.py`](../app/schemas/campaign.py))
- `POST /` — create (business only)
- `GET /` — list/feed (filters: location, category, follower range)
- `GET /{campaign_id}`, `PATCH /{campaign_id}`, `DELETE /{campaign_id}`
- `GET /{campaign_id}/applications` — applications for a campaign (business only)

**Applications** (`/api/v1/applications`, schema: [`app/schemas/application.py`](../app/schemas/application.py))
- `POST /` — creator applies to a campaign
- `GET /{application_id}`
- `PATCH /{application_id}/accept`, `PATCH /{application_id}/reject`
- `GET /me/sent` — applications sent by current creator

**Collaborations** (`/api/v1/collaborations`, schema: [`app/schemas/collaboration.py`](../app/schemas/collaboration.py))
- `GET /` — list for current user (role-filtered)
- `GET /{collaboration_id}`
- `POST /{collaboration_id}/submit` — creator submits content
- `PATCH /{collaboration_id}/complete`, `PATCH /{collaboration_id}/cancel`
- Planned but not started: affiliate URL generation & tracking (per TODO comment in `collaboration_service.py`)

**Chat** (`/api/v1/chat`, schema: [`app/schemas/chat.py`](../app/schemas/chat.py))
- `GET /conversations`, `GET /conversations/{conversation_id}`
- `POST /conversations/{conversation_id}/messages`
- Planned: conversation auto-created on application acceptance (per TODO in `chat_service.py`)

## Testing

- `tests/test_health.py` — the only real automated test (smoke test on `/health`)
- `test_login.py` / `test_signup.py` at the repo root are **manual debug
  scripts**, not part of the `tests/` suite and not run in CI — they call
  Supabase directly and print the result. No automated coverage exists for
  auth or anything else yet.

> ⚠️ **Security issue found while writing this doc:** `test_login.py` (repo
> root) hardcoded a real email + password and this repo is **public** on
> GitHub. That credential was exposed. The scripts have since been removed
> from the repo, but `git rm` alone leaves them in history — rotate that
> password immediately (and anywhere else it's reused), and treat it as
> compromised rather than relying on history rewriting alone.

## Suggested build order for what's left

Given the dependency chain (a campaign needs a business; an application needs
a campaign + creator; a collaboration needs an accepted application; chat
needs a collaboration/application context):

1. Creators + Businesses (read-only profile/discovery first — unblocks everything else and is the simplest slice)
2. Campaigns (CRUD + feed)
3. Applications (apply/accept/reject)
4. Collaborations (submission/completion lifecycle)
5. Chat (can piggyback on Collaboration/Application IDs once those exist)

Delete or repurpose the `Users` module while doing this pass, since it's
currently unused dead code sitting alongside a working `/auth/me`.
