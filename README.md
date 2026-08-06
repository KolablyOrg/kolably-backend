# Kolably Backend

Local Business × Creator Collaboration Marketplace — **FastAPI Backend**

## Quick Start

```bash
# 1. Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy env and configure
cp .env.example .env

# 4. Run development server
uvicorn app.main:app --reload

# 5. Open docs
# → http://127.0.0.1:8000/docs
```

## Project Structure

```
kolably_backend/
├── app/
│   ├── main.py                  # FastAPI entry point
│   ├── api/
│   │   ├── router.py            # Aggregate API router (/api/v1)
│   │   └── routes/
│   │       ├── auth.py           # Signup, login, tokens, /me
│   │       ├── users.py          # Current-user operations
│   │       ├── creators.py       # Creator profiles, portfolio, payout, identity
│   │       ├── businesses.py     # Business profiles, settings, KYB verification
│   │       ├── campaigns.py      # Campaign CRUD, feed, invites
│   │       ├── applications.py   # Apply / accept / reject
│   │       ├── collaborations.py # Collab lifecycle
│   │       ├── chat.py           # Messaging
│   │       ├── notifications.py  # In-app notifications
│   │       ├── upload.py         # Supabase Storage uploads (avatar/logo/docs)
│   │       └── meta.py           # Meta/Instagram webhooks (data deletion, deauth)
│   ├── core/
│   │   ├── config.py             # Pydantic settings
│   │   ├── security.py           # JWT & password utils
│   │   ├── supabase.py           # Supabase client init
│   │   ├── dependencies.py       # FastAPI DI (auth, RBAC, onboarding gates)
│   │   └── exceptions.py         # Custom HTTP exceptions
│   ├── schemas/                  # Pydantic request/response models
│   │   ├── auth.py
│   │   ├── user.py
│   │   ├── creator.py
│   │   ├── business.py
│   │   ├── campaign.py
│   │   ├── application.py
│   │   ├── collaboration.py
│   │   ├── chat.py
│   │   ├── notification.py
│   │   ├── meta.py
│   │   └── common.py
│   ├── repositories/              # Supabase query layer (one per domain)
│   │   ├── base.py               # Generic select/insert/update/delete/count
│   │   ├── profile_repo.py, creator_repo.py, business_repo.py
│   │   ├── campaign_repo.py, application_repo.py, collaboration_repo.py
│   │   ├── chat_repo.py, notification_repo.py, data_deletion_repo.py
│   └── services/                 # Business logic layer
│       ├── auth_service.py, creator_service.py, business_service.py
│       ├── campaign_service.py, application_service.py, collaboration_service.py
│       ├── chat_service.py, notification_service.py
│       ├── google_oauth_service.py, instagram_service.py, meta_webhook_service.py
├── migrations/                   # Database migrations (timestamped SQL files)
│   ├── README.md                 # Migration usage guide
│   └── 20260726150000_*.sql      # Applied in chronological order for the full schema
├── docs/
│   ├── schema.sql                # Source-of-truth DDL (may lag recent migrations — see migrations/ for ground truth)
│   ├── DB_DESIGN.md              # Design decisions & rationale
│   ├── API_REQUIREMENTS.md       # API contracts & endpoints
│   ├── PROJECT_STATUS.md         # Implementation status
│   ├── DEPLOYMENT.md             # Production deployment guide
│   └── kolably_mvp_erd.html      # Entity relationship diagram
├── scripts/
│   ├── seed_superadmin.sql       # Promote user to superadmin
│   └── test_campaign_flow.py     # Manual smoke test
├── tests/                        # ~20 files, one per service/repository/dependency
│   ├── conftest.py               # Shared fixtures
│   └── test_*.py
├── pyproject.toml
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

Layering convention: `routes/` handle HTTP + auth only, `services/` hold business logic and are unit-tested against fake repositories (no live Supabase needed), `repositories/` are the only layer that talks to Supabase. When adding a feature, follow the existing pattern for the closest domain (e.g. `businesses.py` route → `business_service.py` → `business_repo.py`) rather than reaching into Supabase directly from a route or service.

## Database

The backend uses **Supabase** (PostgreSQL) for data storage and authentication.

### Running Migrations

For a fresh Supabase instance, apply all migrations in order:

**Option 1: Supabase CLI (Recommended)**
```bash
# Install Supabase CLI: https://supabase.com/docs/guides/cli
supabase login
supabase link --project-ref YOUR_PROJECT_REF
supabase db push
```

**Option 2: Supabase Dashboard**
1. Go to your Supabase project → SQL Editor
2. Copy and run each migration file from `migrations/` in chronological order

See [`migrations/README.md`](migrations/README.md) for full details.

### Schema Documentation

- **Complete DDL**: [`docs/schema.sql`](docs/schema.sql) — all tables, constraints, indexes, triggers (treat `migrations/` as the ground truth if the two ever disagree)
- **Design Decisions**: [`docs/DB_DESIGN.md`](docs/DB_DESIGN.md) — why we chose TEXT+CHECK over ENUM, identity model, etc.
- **API Requirements**: [`docs/API_REQUIREMENTS.md`](docs/API_REQUIREMENTS.md) — endpoints that drive the schema

### Key Tables

| Table | Purpose |
|-------|---------|
| `profiles` | Single identity table (1:1 with `auth.users`); `role` is `creator`/`business`/`superadmin` |
| `creators` | Creator-specific data (Instagram OAuth, payout/identity, notification prefs, stats) |
| `portfolio_items` | Creator portfolio media (imported from Instagram or added manually) |
| `businesses` | Business profiles (logo, category, KYB verification, notification prefs, discoverability) |
| `campaigns` | Campaign details (4-step create → publish flow) |
| `campaign_applications` | Creator applications & business invites (`direction` distinguishes the two) |
| `saved_campaigns` | Creator bookmarks on campaigns |
| `collaborations` | Accepted applications, active partnerships |
| `content_submissions` | Creator-submitted content with metrics |
| `conversations` / `messages` / `conversation_reads` | Chat system, keyed off `collaboration_id` |
| `notifications` | User notifications |

## API Docs

Once running, visit:

| Docs | URL |
|------|-----|
| Swagger UI | `http://127.0.0.1:8000/docs` |
| ReDoc | `http://127.0.0.1:8000/redoc` |
| Health Check | `http://127.0.0.1:8000/health` |

## Running Tests

```bash
pip install -e ".[dev]"
pytest
```

## Deployment

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for production deployment details (EC2, Docker, nginx, CI/CD).
