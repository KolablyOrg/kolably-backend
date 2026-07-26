# AGENTS.md — Coding guide & standards for `kolably_backend`

This file is the contract for anyone (human or AI agent) writing code in this
repo. Read it before touching `app/`. It codifies patterns already
established by the working Auth and Campaigns modules — new domains
(Creators, Businesses, Applications, Collaborations, Chat, Notifications)
must follow the same shape, not invent a new one.

Related reading before starting any task:
- `docs/PROJECT_STATUS.md` — what's real vs. stub, right now
- `docs/API_REQUIREMENTS.md` — the target contract for the MVP
- `docs/DEPLOYMENT.md` — how this actually runs in production
- `docs/schema.sql` / `docs/DB_DESIGN.md` — the target DB design

---

## 1. Stack

- **Framework**: FastAPI, `async def` routes, Uvicorn.
- **DB/Auth**: Supabase (Postgres + Supabase Auth). Two client types — see §5.
- **Payments**: Razorpay keys exist in config but are **unused** in MVP. Do
  not build payment flows unless explicitly asked — display-only offer text.
- **External data**: Meta Graph API for Instagram (see §9). YouTube/TikTok
  are self-reported only — do not attempt to integrate them.
- **Media**: client uploads directly to Supabase Storage; backend only ever
  stores the resulting URL string. Never proxy file uploads through FastAPI.
- **Chat/notifications**: polled by the client. Do not add websockets.

---

## 2. Repo layout

```
app/
  api/
    router.py            # mounts every domain router under /api/v1
    routes/               # one file per domain: auth.py, campaigns.py, creators.py, ...
  core/
    config.py             # Settings (pydantic-settings), env vars
    enums.py              # every status/type enum — see §4
    exceptions.py         # shared HTTPException subclasses (NotFoundError, ForbiddenError, ...)
    security.py           # JWT decode/verify (HS256 + JWKS-based ES256/RS256)
    dependencies.py       # get_current_user, require_role(*roles)
    supabase.py            # get_supabase_client() (anon) + get_supabase_admin_client() (service-role) — both async
  schemas/                 # one file per domain: campaign.py, creator.py, ...
  services/                 # one file per domain: campaign_service.py, ...
  repositories/             # one file per domain (creator_repo.py, ...) over base.py's BaseRepository
  docs/                    # auth_implementation.md, db_schema.md — regenerate from schema.sql, see §11
docs/                      # PROJECT_STATUS.md, API_REQUIREMENTS.md, DEPLOYMENT.md, DB_DESIGN.md, schema.sql
migrations/                 # timestamped Supabase-CLI-style SQL migrations — see §11
scripts/                   # seed scripts + standalone smoke scripts (not schema migrations, see §11)
tests/                      # pytest suite (thin today — grow this, see §7)
```

**Rule:** a new domain gets exactly one file in each of `routes/`, `schemas/`,
`services/` — mirror `campaigns.py` / `campaign.py` / `campaign_service.py`.
Don't scatter logic across files or put service logic in the route file.

---

## 3. Layering — routes are thin, services do the work, repositories do the DB

Routes: parse/validate input (Pydantic + path/query params), call the auth
dependency, call **one** service function, return its result. No Supabase
calls, no business rules, no manual status-code branching beyond what the
service tells you to raise.

Services: own all business rules and `HTTPException` raises. Repositories:
own all Supabase access. Every domain repo extends `BaseRepository`
(`app/repositories/base.py`), which provides generic CRUD (`select`,
`select_one`, `insert`, `update`, `delete`, `count`, `upsert`) and a single
`_execute()` funnel that awaits the async client and translates postgrest
`APIError` into `DatabaseError` (HTTP 500). Complex queries (joins, `ilike`,
`gte`/`lte`, `.range()` pagination) are built directly in the repo method via
`await self._table(...)` and always executed through `self._execute(...)` —
never call `.execute()` yourself. Service functions take their repos as
keyword-only optional params (`repo: CreatorRepository | None = None`) so
tests can inject fakes without monkeypatching.

```python
# app/api/routes/campaigns.py
@router.post(
    "/{campaign_id}/invite",
    response_model=ApplicationResponse,
    dependencies=[Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))],
)
async def invite_creator(
    campaign_id: str,
    data: InviteRequest,
    user: UserInToken = Depends(get_current_user),
):
    return await campaign_service.invite_creator(
        campaign_id=campaign_id, profile_id=user.id,
        creator_id=data.creator_id, message=data.message,
    )
```

Services: own all business rules and `HTTPException` raises; all Supabase
access goes through the domain repository. A service function's job is to
return a schema-shaped dict/object or raise — never a bare `pass`.

```python
# app/services/campaign_service.py
async def invite_creator(campaign_id: str, profile_id: str, creator_id: str,
                          message: str | None, *,
                          campaign_repo: CampaignRepository | None = None,
                          app_repo: ApplicationRepository | None = None) -> dict:
    campaign_repo = campaign_repo or CampaignRepository()
    business_id = await _get_business_id_for_user(profile_id)
    await _ensure_campaign_owner(campaign_repo, campaign_id, business_id)
    existing = await app_repo.get_existing(campaign_id, creator_id)
    if existing:
        raise HTTPException(status_code=409, detail="Creator already invited/applied")
    return await app_repo.insert_application({...})  # direction=BUSINESS_INVITED
```

Note `UserInToken` (`app/schemas/user.py`) is the shape returned by
`get_current_user`/`require_role` — its `id` field is the caller's
`profiles.id` row, not a Supabase auth UID (that's `auth_id`). Resolve it to
a `creators.id`/`businesses.id` via a helper like `_get_business_id_for_user`
before using it as a foreign key — don't assume `user.id` is directly a
`business_id`/`creator_id`.

**No bare `pass` handlers.** A stub route returning `None` comes back as a
silent `200 OK` — indistinguishable from "working but empty" (this is the
exact confusion `docs/PROJECT_STATUS.md` flags for Creators/Businesses/etc.).
While a route is genuinely unimplemented, raise instead:

```python
raise HTTPException(status_code=501, detail="Not implemented")
```

Never merge a route left in the bare-`pass` state — either finish it or make
its non-implementation explicit with a `501`.

---

## 4. Enums

All status/type fields are Python `str, Enum` in `app/core/enums.py`, mapped
1:1 to `TEXT + CHECK` columns in Postgres (see `docs/schema.sql`) — **not**
native Postgres enum types. Adding a new value:

1. Add it to the enum in `app/core/enums.py`.
2. `ALTER TABLE ... DROP CONSTRAINT ...; ALTER TABLE ... ADD CONSTRAINT ...
   CHECK (col IN (...))` — a new timestamped file in `migrations/` (see
   §11), never hand-edit `docs/schema.sql` in place once it's applied to a
   live environment.

Never introduce a new enum as a bare string scattered across files — add it
to `app/core/enums.py` even if it's only used in one place, so schemas and
services both import the same source of truth.

---

## 5. Supabase clients — anon vs. service-role (both async)

Both getters are `async` and return `supabase.AsyncClient`
(`create_async_client`) — every `.execute()` and `supabase.auth.*` call must
be `await`ed so the event loop is never blocked. Clients are created fresh
per call, never cached as module singletons (httpx clients bind to the event
loop that created them, which breaks under pytest/TestClient).

- **Anon client** (`app/core/supabase.py: get_supabase_client()`) — auth
  operations only (signup, login, password reset). Respects RLS.
- **Service-role admin client** (`get_supabase_admin_client()`) — all other DB
  reads/writes, used as the default in `BaseRepository`. Bypasses RLS, so
  **every ownership/role check happens in Python**, not in the database —
  there is no DB-level backstop. This is why `_ensure_campaign_owner`-style
  helpers exist — do not skip them because "the DB would reject it anyway."
  It won't. Never let a path/body ID reach a query unverified.

Every new service function that touches another user's row (an
application, a collaboration, a conversation) must include an explicit
ownership or role check before the query, following the
`_ensure_campaign_owner` pattern: **404** if the resource doesn't exist,
**403** if it exists but isn't owned/accessible by the caller. Don't leak
existence via a 403 on something that isn't even there.

---

## 6. Auth & RBAC

- `get_current_user` (in `app/core/dependencies.py`) verifies the JWT
  (`app/core/security.py`, HS256 secret or JWKS-based ES256/RS256), loads the
  matching `profiles` row, and checks `is_active` — every authenticated route
  depends on it, directly or via `require_role`. Email verification is
  enforced at **login** (Supabase Auth won't issue a session to an unverified
  user), not re-checked on every request — the JWT has no
  `email_confirmed_at` claim to check against.
- `require_role(*roles)` is a dependency **factory** — call it with the
  roles allowed for that route: `Depends(require_role(UserRole.BUSINESS,
  UserRole.SUPERADMIN))`. Don't hand-roll `if current_user.role != ...`
  checks in route bodies.
- `direction`-gated actions (accept/reject/request-revision on applications)
  are **not** pure role checks — the same status transition is gated by
  *which side* initiated (`creator_applied` vs. `business_invited`). Encode
  this in the service function, not the route dependency; `require_role`
  alone can't express it.

---

## 7. Pagination

Every list endpoint uses the shared envelope — don't return a bare list or
invent a one-off shape:

```python
# app/schemas/common.py
class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
```

Route signature: `page: int = 1, page_size: int = 20` via the existing
`PaginationParams` dependency — don't redefine pagination params per route.

---

## 8. Response models & schemas

- Every route declares `response_model=...`. Never return a raw dict from a
  route and let FastAPI guess.
- Internal-only fields (`instagram_access_token`, `instagram_user_id`)
  **never** appear in a `*Response` schema — keep them on the internal
  service-layer object only. If you add a new sensitive field to a table,
  check every `*Response` schema that could accidentally serialize it.
- Prefer composition over duplicating fields: `ApplicationWithCampaign(ApplicationResponse)`,
  not a hand-copied set of fields.
- Money fields are `float`/`Decimal` in schemas, `NUMERIC` in Postgres —
  never `int` cents unless a specific integer-currency requirement appears.

---

## 9. Instagram / Meta Graph API integration

- Token fields are internal-only (§8) and must be encrypted at rest — do
  not store `instagram_access_token` as plaintext even in dev.
  Long-lived tokens expire (~60 days); `instagram_token_expires_at` exists
  so a background job or on-demand check can catch this — don't assume the
  token is always valid.
- `sync` semantics: re-fetch on demand when `instagram_synced_at` is stale
  (>24h) — don't hit the Graph API on every profile read.
  Content-submission `sync` behaves the same way but per-submission.
- For `platform=instagram` submissions, ignore/reject client-supplied
  `views`/`likes`/`comments` — always fetch from the Graph API. For any
  other platform, trust the client-supplied values (self-reported,
  unintegrated — this is intentional MVP scope, not a shortcut to fix).
- The connect flow only works for Instagram **Business/Creator** accounts
  linked to a Facebook Page — a personal account must be told to convert
  first, not silently fail.

---

## 10. Notifications as side effects

Notifications are never created from a route — they're a side effect fired
from inside the relevant service function (e.g. `application_service`
creates a `NotificationType.APPLICATION_ACCEPTED` row when it flips an
application's status). When you add a new state transition that
`docs/API_REQUIREMENTS.md §8` says should notify someone, add the
`notifications` insert inside that same service function, in the same
transaction/flow — don't add a separate "notification service call" from
the route layer, and don't forget it exists as an event source (grep
`NotificationType` before shipping any status-changing endpoint).

---

## 11. Database & migrations

- `docs/schema.sql` is the source of truth for the target shape. Table/column
  names follow the **code's** naming, not `app/docs/db_schema.md` if the two
  ever disagree — regenerate the docs from the schema, not the other way
  around (this exact drift already happened once, see `docs/PROJECT_STATUS.md`).
- New schema changes go in `migrations/` as timestamped, Supabase-CLI-style
  `.sql` files: `YYYYMMDDHHMMSS_description.sql` (see `migrations/README.md`
  for the convention and full history). Prefer idempotent DDL (`ADD COLUMN
  IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`, guarded `DO $$ ... $$` blocks)
  even though these are timestamped, single-run files — don't assume a
  migration can't be re-run against a partially migrated DB.
- Apply migrations via the Supabase CLI (`supabase db push`) or by hand in
  the Supabase SQL Editor, in chronological order — there's no ORM-managed
  migration runner in this project. Add a row to the table in
  `migrations/README.md` describing what changed.
- `scripts/` is for one-off seed data (`seed_superadmin.sql`,
  `seed_sample_data.sql`) and standalone smoke scripts — not schema
  migrations. Don't put new DDL there.
- Every new FK gets an explicit `ON DELETE` behavior. Think about it, don't
  default to the Postgres default (`NO ACTION`).

---

## 12. Config & secrets

- All config through `app/core/config.py` (`pydantic-settings`), reading
  from `.env`. Never `os.environ.get(...)` scattered in route/service files.
- Never commit `.env` or print/log secrets — the production `.env` lives
  only on the EC2 instance (see `docs/DEPLOYMENT.md`) and is never in git.
- If you add a new required env var, update `.env.example` in the same
  commit, and call it out in the PR description — the CI/CD pipeline only
  copies forward an existing `.env` on deploy (see `docs/DEPLOYMENT.md` §CI/CD);
  a new var silently missing on the server will break production, not fail
  the deploy.
- Treat any credential that ever touched a public repo as compromised —
  rotate, don't just remove the file (see `docs/PROJECT_STATUS.md`'s
  `test_login.py` incident). This applies to any accidental commit, not
  just that specific one.

---

## 13. Testing

- Real automated tests live in `tests/`, run with `pytest`, and **are**
  part of CI (in spirit — wire this in if it isn't yet). Every new service
  function that isn't a trivial passthrough gets a test.
- Standalone debug/smoke scripts (`scripts/test_campaign_flow.py`-style) are
  fine for manual end-to-end verification against a live server, but they
  are **not** a substitute for `tests/` coverage and must never hit
  Supabase with hardcoded real credentials (see §12). Prefix new ones
  clearly (`scripts/smoke_*.py`) so they're not mistaken for pytest cases.
- Minimum bar for a new domain's PR: happy-path test for each write
  endpoint (create/accept/reject/etc.), one 403/404 ownership test, one
  validation-failure test (e.g. `publish` with missing required fields).
- Don't hand-roll assertions against Supabase directly in a test when a
  service function already exists — test through the service layer so the
  test doesn't silently drift from what the route actually calls.

---

## 14. Code style

- `async def` for every route and every service function that does I/O.
  Never a blocking call (`requests`, sync Supabase client methods) inside
  an `async def` — use the async client / `httpx.AsyncClient`.
- Type hints everywhere, including internal service function signatures —
  not just route signatures. Return types on every function.
- Formatting/linting: `ruff` only (see `[tool.ruff]` in `pyproject.toml` —
  `black` is **not** a dependency here; don't add it or a second formatter
  without updating `pyproject.toml` and this doc). Run `ruff check` (and
  `ruff format` if you introduce it) before finishing any task — note CI
  (`.github/workflows/deploy.yml`) currently only builds and deploys, it does
  not run `ruff`/`pytest`, so this is on you locally until that's wired in.
- Docstrings on service functions that aren't self-explanatory from the
  name + type hints — especially anything with a non-obvious side effect
  (notification fan-out, Graph API calls, status auto-transitions).
- Prefer explicit `HTTPException(status_code=..., detail=...)` over
  generic exceptions bubbling up — the client needs a real status code,
  not a 500 with a stack trace.

---

## 15. Deployment awareness

You probably aren't deploying directly, but code changes here have real
consequences on the box described in `docs/DEPLOYMENT.md`:

- There's no image versioning — every deploy overwrites
  `kolably-backend-cicd:latest` with no built-in rollback. Don't ship
  anything you're not confident in reverting-by-hand if needed.
- `.env` on the server is never touched by CI/CD except being copied
  forward — a schema migration and a code change that depends on a new env
  var must be sequenced by a human, not assumed atomic.
- `git` is not installed on the EC2 box — don't write deploy-time logic or
  docs that assume `git pull`/`git log` works over SSH there.

---

## 16. Before you open a PR / finish a task

- [ ] New routes have `response_model`, live in the right domain file, and
      call exactly one service function.
- [ ] Every write path has an explicit ownership/role check — no route
      trusts a path/body ID without verifying the caller can act on it.
- [ ] No bare `pass` / silent `null` 200s left behind.
- [ ] New enum values added to `app/core/enums.py`, and a matching
      `CHECK` constraint migration exists in `migrations/`.
- [ ] Any new sensitive column checked against every `*Response` schema
      that could leak it.
- [ ] Notification side effects added for any new state transition listed
      in `docs/API_REQUIREMENTS.md §8`.
- [ ] Tests added under `tests/`, not just a standalone smoke script.
- [ ] `.env.example` updated if a new env var was introduced.
- [ ] `app/docs/db_schema.md` regenerated/updated if the schema changed —
      don't let it drift again.
