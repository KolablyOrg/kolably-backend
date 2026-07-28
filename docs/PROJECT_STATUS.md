# Project Status — What's Actually Implemented

A honest snapshot of what works vs. what's scaffolding, based on reading the
code. Auth is current as of 2026-07-21; the Campaigns section was refreshed on
2026-07-25 after reviewing [`app/services/campaign_service.py`](../app/services/campaign_service.py)
and [`app/api/routes/campaigns.py`](../app/api/routes/campaigns.py); the
Creators section was added on 2026-07-28 after completing the module
end-to-end. All routes below live under the `/api/v1` prefix and are wired up
in [`app/api/router.py`](../app/api/router.py).

## Summary

| Module | Status |
|---|---|
| Auth (signup, login, sessions, profile) | ✅ Fully implemented |
| Users | ⚠️ Stub only (dead code — superseded by `/auth/me`) |
| Creators | ✅ Fully implemented (end-to-end, persisted) |
| Businesses | ❌ Not implemented |
| Campaigns | ✅ Fully implemented (end-to-end, persisted) |
| Applications | ❌ Not implemented |
| Collaborations | ❌ Not implemented |
| Chat | ❌ Not implemented |

Auth, Creators, and Campaigns are real end-to-end. The remaining domains
(Businesses, Applications, Collaborations, Chat) still only define route signatures and
Pydantic schemas — handler bodies are `# TODO: Implement` / `pass` and the
corresponding `*_service.py` files contain nothing but TODO comments. Calling
any of those returns `null` with a `200 OK` (FastAPI's default for a bare
`pass`), not an error — worth knowing so it isn't mistaken for "working but
empty."

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

## ✅ Implemented: Campaigns (`/api/v1/campaigns`)

Backed by [`app/services/campaign_service.py`](../app/services/campaign_service.py)
(547 lines) — a full persistence layer using the Supabase service-role admin
client against the `campaigns` and `campaign_applications` tables, plus
[`app/api/routes/campaigns.py`](../app/api/routes/campaigns.py) (183 lines)
and [`app/schemas/campaign.py`](../app/schemas/campaign.py).
All write operations are role-gated with `require_role(BUSINESS, SUPERADMIN)`
and ownership is enforced via `_ensure_campaign_owner` (404 if not found, 403
if not owner).

### Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/campaigns/` | BUSINESS / SUPERADMIN | Step 1 — create `draft` campaign (title + objective + description) |
| PATCH | `/campaigns/{id}/deliverables` | BUSINESS / SUPERADMIN | Step 2 — set deliverables JSON, compensation type, cash range / free-product description |
| PATCH | `/campaigns/{id}/targeting` | BUSINESS / SUPERADMIN | Step 3 — set creator targeting (category, follower range, min engagement rate, location, max creators, additional requirements) |
| PATCH | `/campaigns/{id}` | BUSINESS / SUPERADMIN | Step 4 — general update (cover image, deadline, or any field) |
| POST | `/campaigns/{id}/publish` | BUSINESS / SUPERADMIN | Validate completeness and flip status `draft → active`; returns `422` with `missing_fields` if incomplete |
| GET | `/campaigns/` | authenticated | Paginated feed of `active` campaigns; filters: `search`, `category`, `recommended` (creator niche match), `page`, `page_size` |
| GET | `/campaigns/categories` | public | Static list of 12 categories |
| GET | `/campaigns/{id}` | public | Full campaign detail |
| DELETE | `/campaigns/{id}` | BUSINESS / SUPERADMIN (owner) | Hard delete |
| GET | `/campaigns/{id}/applications` | BUSINESS / SUPERADMIN (owner) | List applications joined with creator info (`ApplicationWithCreator`) |
| POST | `/campaigns/{id}/invite` | BUSINESS / SUPERADMIN (owner) | Invite a creator — inserts a `campaign_applications` row with `direction = business_invited`; 409 on duplicate |

### What works
- Real Supabase reads/writes across the full 4-step create → publish flow with drafts.
- Feed, search, category filter, single detail, hard delete, applications list, creator invite — all backed by working service functions.
- Aggregate counts (`applicant_count`, `accepted_count`) computed per campaign.
- Migration script [`scripts/migrate_campaigns.sql`](../scripts/migrate_campaigns.sql) adds the columns and indexes the service relies on (idempotent).
- Manual end-to-end smoke script [`scripts/test_campaign_flow.py`](../scripts/test_campaign_flow.py) walks login → Step 1–4 → 422 early-publish guard → feed → detail → categories. Standalone (`python scripts/test_campaign_flow.py`), requires a live server — **not** part of the `tests/` suite.

### Known gaps / drift
- **No automated tests.** No `tests/test_campaigns*.py` exists; only the standalone smoke script.
- **Schema drift.** [`app/docs/db_schema.md`](../app/docs/db_schema.md) §5/§6 still documents `city`, `campaign_status`, `cash_payment`, `min_followers`/`max_followers`, `free_product`, while the code and migration use `location`, `status`, `cash_amount_min`/`cash_amount_max`, `follower_range_min`/`follower_range_max`, `free_product_description`. Docs need refreshing.
- **Migration coverage.** The service also reads/writes `direction`, `instagram_handle`, `example_content_url`, `revision_reason` on `campaign_applications`, but neither `db_schema.md` nor `migrate_campaigns.sql` defines those columns. They must have been added out-of-band in Supabase (or are missing) — list-applications and invite will fail at runtime otherwise. Worth adding a follow-up migration.
- **Unused schema.** `CampaignPublishRequest` in `app/schemas/campaign.py` is dead code — the publish route takes no body.
- **No notifications.** `NotificationType.CAMPAIGN_INVITE_RECEIVED` exists in enums but inviting a creator does not fire any notification.
- **`recommended` mode** only narrows by exact `creator_category == niche` for callers with role `creator`; it does not rank and silently returns the unfiltered feed for other roles.
- **Business-owned listing stub.** `GET /businesses/{business_id}/campaigns` (in `businesses.py`) is still a `# TODO: Implement` stub — a business cannot list its own `draft`/`closed` campaigns through `/businesses`; only `active` ones surface via the feed.

## ✅ Implemented: Creators (`/api/v1/creators`)

Backed by [`app/services/creator_service.py`](../app/services/creator_service.py),
[`app/repositories/creator_repo.py`](../app/repositories/creator_repo.py),
[`app/api/routes/creators.py`](../app/api/routes/creators.py), and
[`app/schemas/creator.py`](../app/schemas/creator.py). All write paths are
ownership-checked in the service layer (`_ensure_creator_access` — 404 if the
creator doesn't exist, 403 if it belongs to someone else; superadmin bypass).
Covers the full `docs/API_REQUIREMENTS.md §2` contract, including the
Instagram connection flow (Instagram API with Instagram Login, confirmed
working against tester accounts).

### Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/creators/` | public | Paginated discovery list; filters: `search`, `niche`, `city`, `follower_min`, `follower_max` |
| GET | `/creators/{id}` | public | Public creator profile |
| PATCH | `/creators/{id}` | CREATOR (owner) / SUPERADMIN | Update profile fields (name, username, city, niche, bio, handles, photo, follower_count) |
| GET | `/creators/{id}/portfolio` | public | Paginated portfolio; `media_type` filter |
| POST | `/creators/{id}/portfolio` | CREATOR (owner) / SUPERADMIN | Manual portfolio add (`media_url` from client-side Storage upload) |
| DELETE | `/creators/{id}/portfolio/{item_id}` | CREATOR (owner) / SUPERADMIN | Delete a portfolio item (404s if the item belongs to another creator) |
| GET | `/creators/me/stats` | authenticated | `active_collaborations_count` + `engagement_growth_pct` (always null — no data source) |
| GET | `/creators/me/saved-campaigns` | authenticated | Paginated saved campaigns, full `CampaignResponse` items |
| POST | `/creators/me/saved-campaigns/{campaign_id}` | CREATOR + Instagram-connected | Save a campaign (idempotent upsert; 404 on unknown campaign) |
| DELETE | `/creators/me/saved-campaigns/{campaign_id}` | CREATOR | Unsave a campaign (idempotent) |
| GET | `/creators/me/instagram/auth-url` | authenticated | Build the `instagram.com/oauth/authorize` URL |
| POST | `/creators/me/instagram/connect` | authenticated | Exchange code → long-lived token (Fernet-encrypted at rest) → one-time full profile pre-fill; 422 for personal accounts, 409 if the IG account is connected elsewhere |
| POST | `/creators/me/instagram/sync` | authenticated | Stats-only re-fetch (followers/following/photo/engagement); proactively refreshes the long-lived token when <10 days remain |
| DELETE | `/creators/me/instagram/disconnect` | authenticated | Clear the stored connection locally |
| POST | `/creators/me/instagram/import-portfolio` | authenticated | Pull recent IG media into `portfolio_items` |

### Notes
- Token fields (`instagram_access_token`, `instagram_user_id`) are never
  serialized — `CreatorResponse` doesn't include them, and there's a
  regression test for it.
- `portfolio_items.title` (migration `019`) backs optional labels on manual
  additions; Instagram imports leave it NULL.
- `POST /creators/me/saved-campaigns/{id}` is gated by
  `require_instagram_connected` per `API_REQUIREMENTS.md §1` ("campaign
  save/apply"); unsave is deliberately not gated so a disconnected creator can
  still clean up.
- Unit-tested via `tests/test_creator_service.py` (repo fakes, no Supabase)
  and `tests/test_instagram_connect.py` (Graph API faked).

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

**Businesses** (`/api/v1/businesses`, schema: [`app/schemas/business.py`](../app/schemas/business.py))
- `GET /` — list/search
- `GET /{business_id}` — public profile
- `PATCH /{business_id}` — update own profile
- `GET /{business_id}/campaigns` — campaigns for a business

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

- `tests/` is a real pytest suite with repo-faked unit tests (no Supabase
  calls): creator service (`test_creator_service.py`), Instagram connect/sync
  flow (`test_instagram_connect.py`), Instagram auth (`test_instagram_auth.py`),
  business service, auth service, repositories, dependencies, Meta webhook +
  signed-request parsing, and a `/health` smoke test. `tests/conftest.py`
  generates a throwaway `TOKEN_ENCRYPTION_KEY` per run so the suite doesn't
  depend on local `.env` contents.
- Standalone smoke scripts (`scripts/test_campaign_flow.py`) require a live
  server and are **not** part of the `tests/` suite.

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

1. ~~Creators~~ — **done.** Businesses (read-only profile/discovery first — unblocks everything else and is the simplest slice). Campaigns already leans on these via `businesses.id` resolution, so making them real will tighten the campaigns flow too.
2. ~~Campaigns (CRUD + feed)~~ — **done.**
3. Applications (apply/accept/reject) — campaigns already exposes `GET /campaigns/{id}/applications` and `POST /campaigns/{id}/invite`, so the creator-side application endpoints are the natural next step.
4. Collaborations (submission/completion lifecycle)
5. Chat (can piggyback on Collaboration/Application IDs once those exist)

Delete or repurpose the `Users` module while doing this pass, since it's
currently unused dead code sitting alongside a working `/auth/me`.
