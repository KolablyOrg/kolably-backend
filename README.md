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
│   │       ├── auth.py           # Signup, login, tokens
│   │       ├── users.py          # Current-user operations
│   │       ├── creators.py       # Creator profiles & portfolio
│   │       ├── businesses.py     # Business profiles
│   │       ├── campaigns.py      # Campaign CRUD & feed
│   │       ├── applications.py   # Apply / accept / reject
│   │       ├── collaborations.py # Collab lifecycle
│   │       └── chat.py           # Messaging
│   ├── core/
│   │   ├── config.py             # Pydantic settings
│   │   ├── security.py           # JWT & password utils
│   │   ├── supabase.py           # Supabase client init
│   │   ├── dependencies.py       # FastAPI DI (auth, DB)
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
│   │   └── common.py
│   └── services/                 # Business logic layer
│       ├── auth_service.py
│       ├── creator_service.py
│       ├── business_service.py
│       ├── campaign_service.py
│       ├── application_service.py
│       ├── collaboration_service.py
│       └── chat_service.py
├── migrations/                   # Database migrations (timestamped SQL files)
│   ├── README.md                 # Migration usage guide
│   └── 20260726150000_*.sql      # 16 migrations for complete schema
├── docs/
│   ├── schema.sql                # Complete source-of-truth DDL
│   ├── DB_DESIGN.md              # Design decisions & rationale
│   ├── API_REQUIREMENTS.md       # API contracts & endpoints
│   ├── PROJECT_STATUS.md         # Implementation status
│   ├── DEPLOYMENT.md             # Production deployment guide
│   └── kolably_mvp_erd.html      # Entity relationship diagram
├── scripts/
│   ├── seed_superadmin.sql       # Promote user to superadmin
│   └── test_campaign_flow.py     # Manual smoke test
├── tests/
│   ├── conftest.py               # Shared fixtures
│   └── test_health.py            # Smoke test
├── pyproject.toml
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

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

- **Complete DDL**: [`docs/schema.sql`](docs/schema.sql) — 14 tables, all constraints, indexes, triggers
- **Design Decisions**: [`docs/DB_DESIGN.md`](docs/DB_DESIGN.md) — why we chose TEXT+CHECK over ENUM, identity model, etc.
- **API Requirements**: [`docs/API_REQUIREMENTS.md`](docs/API_REQUIREMENTS.md) — endpoints that drive the schema

### Key Tables

| Table | Purpose |
|-------|---------|
| `profiles` | Single identity table (1:1 with `auth.users`) |
| `creators` | Creator-specific data (Instagram OAuth, portfolio, stats) |
| `businesses` | Business profiles (logo, industry, verification) |
| `campaigns` | Campaign details (4-step create → publish flow) |
| `campaign_applications` | Creator applications & business invites |
| `collaborations` | Accepted applications, active partnerships |
| `content_submissions` | Creator-submitted content with metrics |
| `conversations` / `messages` | Chat system |
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
