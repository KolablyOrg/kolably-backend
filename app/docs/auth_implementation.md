# Auth Implementation Plan — Kolably Backend

> **Status:** ✅ Finalized (v3 — backend facade pattern)

## Decisions Locked

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Identity + sessions | **Supabase Auth** | Free tier (50k MAU), handles passwords, email verification, sessions |
| Token strategy | **Verify Supabase JWT directly** | No custom JWT minting — single source of truth |
| Auth API pattern | **Backend facade** | Frontend calls our API only — Supabase is a hidden implementation detail, swappable later |
| Role storage | **Postgres ENUM in `profiles` table** | Type-safe, fast, no typos |
| Profile creation | **Postgres trigger on `auth.users` INSERT** | Atomic, no race conditions |
| Superadmin creation | **SQL seed script** | Auditable, no public endpoint |

---

## 1. Goals

- Supabase Auth as the auth engine (identity, sessions, tokens)
- **All auth goes through our backend API** — frontend never calls Supabase Auth directly
- FastAPI verifies Supabase JWT → loads role from `profiles` → RBAC
- Three user roles: **`superadmin`** / **`business`** / **`creator`**
- If we migrate off Supabase later, only the backend service layer changes — frontend untouched

---

## 2. Architecture

```
Frontend (Next.js)
      │
      │  All auth calls go to our API
      ▼
FastAPI Backend (auth facade)
      │
      │  Proxies to Supabase behind the scenes
      ▼
Supabase Auth (hidden implementation detail)
      │
      ▼
Supabase PostgreSQL (profiles, creators, businesses)
```

**Key principle:** The frontend treats our API as the only auth provider. Supabase is an implementation detail that can be swapped without frontend changes.

---

## 3. User Roles & Permissions Matrix

| Capability | `creator` | `business` | `superadmin` |
|---|:---:|:---:|:---:|
| View / edit own creator profile | ✅ | — | ✅ |
| View / edit own business profile | — | ✅ | ✅ |
| Browse campaigns & apply | ✅ | — | ✅ |
| Create / manage campaigns | — | ✅ | ✅ |
| Accept / reject applications | — | ✅ | ✅ |
| Submit content for collab | ✅ | — | ✅ |
| Mark collab as complete | — | ✅ | ✅ |
| Access admin dashboard | — | — | ✅ |
| Manage all users | — | — | ✅ |
| View platform-wide analytics | — | — | ✅ |

> **Superadmin** inherits both `creator` and `business` permissions, plus exclusive admin capabilities.

---

## 4. Database Schema

### 4.1 Role ENUM

```sql
CREATE TYPE user_role AS ENUM ('creator', 'business', 'superadmin');
```

### 4.2 `profiles` table

```sql
CREATE TABLE public.profiles (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_id     UUID UNIQUE NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    email       TEXT UNIQUE NOT NULL,
    role        user_role NOT NULL,
    is_active   BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);
```

### 4.3 Auto-create profile via Postgres trigger

```sql
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.profiles (auth_id, email, role)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(
            (NEW.raw_user_meta_data ->> 'role')::user_role,
            'creator'::user_role
        )
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();
```

> Role is passed via `raw_user_meta_data` during signup. Default fallback: `creator`.

### 4.4 Profile table relationships

```
public.profiles.id  ──→  public.creators.profile_id    (1:1, optional)
public.profiles.id  ──→  public.businesses.profile_id  (1:1, optional)
```

- `creator` → has a `creators` row
- `business` → has a `businesses` row
- `superadmin` → can have both, or neither

---

## 5. Auth API Endpoints (Backend Facade)

All endpoints live under `/api/v1/auth`. Internally they proxy to Supabase Auth.

| Endpoint | Method | Auth Required | Internal Action |
|----------|--------|:---:|---------|
| `/auth/signup/creator` | POST | No | `supabase.auth.sign_up()` + insert `creators` row |
| `/auth/signup/business` | POST | No | `supabase.auth.sign_up()` + insert `businesses` row |
| `/auth/login` | POST | No | `supabase.auth.sign_in_with_password()` → return tokens |
| `/auth/logout` | POST | Yes | `supabase.auth.sign_out()` |
| `/auth/refresh` | POST | No | `supabase.auth.refresh_session()` → return new tokens |
| `/auth/forgot-password` | POST | No | `supabase.auth.reset_password_email()` |
| `/auth/reset-password` | POST | No | `supabase.auth.update_user(password=...)` |
| `/auth/me` | GET | Yes | Load profile + role-specific data |
| `/auth/me` | PATCH | Yes | Update profile fields |

**What the frontend sees:** A standard REST auth API.
**What's behind it:** Supabase Auth calls. Swappable without frontend changes.

---

## 6. Auth Flows

### 6.1 Signup

```
Frontend                        Backend                          Supabase
  │                               │                                │
  │  POST /api/v1/auth/signup/creator                              │
  │  { name, email, password,     │                                │
  │    city, niche, ... }         │                                │
  │──────────────────────────────→│                                │
  │                               │  supabase.auth.sign_up(        │
  │                               │    email, password,             │
  │                               │    data: { role: 'creator' }   │
  │                               │  )                              │
  │                               │───────────────────────────────→│
  │                               │  ← { session, user }           │
  │                               │                                │
  │                               │  (trigger auto-creates profile)│
  │                               │  INSERT public.creators         │
  │                               │                                │
  │  ← { access_token,           │                                │
  │       refresh_token,          │                                │
  │       user: { role, ... } }   │                                │
```

**Steps:**
1. Frontend sends all data to our backend endpoint
2. Backend validates via Pydantic schema
3. Backend calls `supabase.auth.sign_up()` with role in `user_metadata`
4. Postgres trigger auto-creates `profiles` row
5. Backend inserts `creators` or `businesses` row with profile data
6. Backend returns Supabase tokens + user profile to frontend

### 6.2 Login

```
Frontend                        Backend                          Supabase
  │                               │                                │
  │  POST /api/v1/auth/login      │                                │
  │  { email, password }          │                                │
  │──────────────────────────────→│                                │
  │                               │  supabase.auth.sign_in_with_   │
  │                               │    password(email, password)   │
  │                               │───────────────────────────────→│
  │                               │  ← { session, user }           │
  │                               │                                │
  │                               │  Load profile (role, is_active)│
  │                               │  Check email_confirmed_at      │
  │                               │  Check is_active               │
  │                               │                                │
  │  ← { access_token,           │                                │
  │       refresh_token,          │                                │
  │       user: { role, ... } }   │                                │
```

**Steps:**
1. Frontend sends credentials to our endpoint
2. Backend calls `supabase.auth.sign_in_with_password()`
3. Backend loads profile from DB, checks `email_confirmed_at` and `is_active`
4. Returns Supabase tokens + user profile (with role)

### 6.3 Token Refresh

```
Frontend                        Backend                          Supabase
  │                               │                                │
  │  POST /api/v1/auth/refresh    │                                │
  │  { refresh_token }            │                                │
  │──────────────────────────────→│                                │
  │                               │  supabase.auth.refresh_session │
  │                               │    (refresh_token)             │
  │                               │───────────────────────────────→│
  │                               │  ← { new session }             │
  │                               │                                │
  │  ← { access_token,           │                                │
  │       refresh_token }         │                                │
```

### 6.4 Logout

```
Frontend                        Backend                          Supabase
  │                               │                                │
  │  POST /api/v1/auth/logout     │                                │
  │  Authorization: Bearer <jwt>  │                                │
  │──────────────────────────────→│                                │
  │                               │  supabase.auth.sign_out()      │
  │                               │───────────────────────────────→│
  │                               │                                │
  │  ← { message: "Logged out" } │                                │
```

### 6.5 Password Reset

```
# Step 1: Request reset email
Frontend → POST /api/v1/auth/forgot-password { email }
Backend  → supabase.auth.reset_password_email(email)
Frontend ← { message: "Reset link sent" }

# Step 2: User clicks email link → redirected to frontend with token

# Step 3: Set new password
Frontend → POST /api/v1/auth/reset-password { access_token, new_password }
Backend  → supabase.auth.update_user(password=new_password)  # using the token
Frontend ← { message: "Password updated" }
```

---

## 7. RBAC System Design

### 7.1 Role Enum (Python)

```python
# app/core/enums.py
from enum import Enum


class UserRole(str, Enum):
    CREATOR = "creator"
    BUSINESS = "business"
    SUPERADMIN = "superadmin"
```

### 7.2 UserInToken Schema

```python
# app/schemas/user.py
from pydantic import BaseModel
from app.core.enums import UserRole


class UserInToken(BaseModel):
    id: str  # profiles.id
    auth_id: str  # auth.users.id (from JWT "sub")
    email: str
    role: UserRole
    is_active: bool
```

### 7.3 Dependency Chain

```
Request (Authorization: Bearer <supabase_jwt>)
  │
  ▼
get_current_user(token)
  │  → Decode Supabase JWT using SUPABASE_JWT_SECRET
  │  → Extract auth_id from "sub" claim
  │  → Check email_confirmed_at is not null
  │  → Query profiles table by auth_id
  │  → Check is_active = true
  │  → Return UserInToken
  │
  ▼
require_role(*allowed_roles)
  │  → Check user.role in allowed_roles
  │  → Raise 403 if not
  │  → Return user
  │
  ▼
Route handler
```

### 7.4 Dependencies (pseudocode)

```python
# app/core/dependencies.py

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserInToken:
    token = credentials.credentials

    # 1. Decode Supabase JWT
    payload = jwt.decode(
        token,
        settings.SUPABASE_JWT_SECRET,
        algorithms=["HS256"],
        audience="authenticated",
    )

    # 2. Check email verified
    if not payload.get("email_confirmed_at"):
        raise HTTPException(403, "Email not verified")

    # 3. Load profile by auth_id
    auth_id = payload.get("sub")
    profile = await get_profile_by_auth_id(auth_id)

    # 4. Check active
    if not profile.is_active:
        raise HTTPException(403, "Account deactivated")

    return UserInToken(...)


def require_role(*allowed_roles: UserRole):
    async def _check(user: UserInToken = Depends(get_current_user)):
        if user.role not in allowed_roles:
            raise HTTPException(403, "Insufficient permissions")
        return user

    return _check
```

### 7.5 Usage in Routes

```python
@router.post("/")
async def create_campaign(user: UserInToken = Depends(require_role(UserRole.BUSINESS, UserRole.SUPERADMIN))): ...


@router.post("/")
async def create_application(user: UserInToken = Depends(require_role(UserRole.CREATOR, UserRole.SUPERADMIN))): ...
```

### 7.6 Superadmin Data Access

```python
if user.role == UserRole.SUPERADMIN:
    # No ownership filter — return all data
else:
    # Filter by profile_id ownership
```

---

## 8. Superadmin Seeding

```sql
-- scripts/seed_superadmin.sql
-- Step 1: Create user in Supabase Auth dashboard
-- Step 2: Copy auth.users.id
-- Step 3: Run:

INSERT INTO public.profiles (auth_id, email, role, is_active)
VALUES (
    '<supabase-auth-uid>',
    'admin@kolably.com',
    'superadmin',
    true
);
```

---

## 9. Config

Add to `.env` / `config.py`:

```env
SUPABASE_JWT_SECRET=your-jwt-secret-from-supabase-dashboard
```

Found in: **Supabase Dashboard → Settings → API → JWT Secret**

---

## 10. Files to Create / Modify

### New Files

| File | Purpose |
|------|---------|
| `app/core/enums.py` | `UserRole` enum |
| `app/schemas/user.py` | `UserInToken`, `UserResponse` |
| `scripts/seed_superadmin.sql` | Superadmin seed |

### Files to Modify

| File | Changes |
|------|---------|
| `app/core/config.py` | Add `SUPABASE_JWT_SECRET` |
| `app/core/security.py` | `verify_supabase_token()` — decode + validate |
| `app/core/dependencies.py` | `get_current_user`, `require_role()` |
| `app/core/supabase.py` | Supabase client singleton |
| `app/schemas/auth.py` | Request/response schemas for all auth endpoints |
| `app/api/routes/auth.py` | All 8 facade endpoints |
| `app/services/auth_service.py` | Thin service proxying to Supabase Auth |

### Database Migrations

| Migration | What |
|-----------|------|
| `001_create_role_enum_and_profiles` | `user_role` ENUM + `profiles` table + trigger |
| `002_create_creators` | `creators` table with `profile_id` FK |
| `003_create_businesses` | `businesses` table with `profile_id` FK |

---

## 11. Security Considerations

| Concern | Mitigation |
|---------|------------|
| Token verification | Verify Supabase JWT with `SUPABASE_JWT_SECRET` + `audience: "authenticated"` |
| Brute-force login | Supabase Auth built-in rate limiting |
| Password storage | Supabase Auth (bcrypt) |
| Email verification | Check `email_confirmed_at` before allowing access |
| Session management | Supabase handles refresh, rotation, multi-device |
| CORS | Strict origin whitelist |
| Superadmin creation | SQL seed only |
| Auth migration | Backend facade pattern — swap Supabase for any provider, frontend unchanged |

---

## 12. Implementation Order

```
Step 1  → Database migrations (role enum, profiles + trigger, creators, businesses)
Step 2  → app/core/enums.py
Step 3  → app/core/config.py (add SUPABASE_JWT_SECRET)
Step 4  → app/schemas/user.py (UserInToken)
Step 5  → app/core/supabase.py (client init)
Step 6  → app/core/security.py (verify_supabase_token)
Step 7  → app/core/dependencies.py (get_current_user, require_role)
Step 8  → app/schemas/auth.py (all auth request/response schemas)
Step 9  → app/services/auth_service.py (facade over Supabase Auth)
Step 10 → app/api/routes/auth.py (all 8 endpoints)
Step 11 → scripts/seed_superadmin.sql
Step 12 → Tests
```

---

## 13. Verification Plan

### Automated Tests
- `test_auth.py` — test all facade endpoints with mocked Supabase client
- `test_rbac.py` — test `require_role` with different roles

### Manual Verification
1. Create user via signup endpoint → verify trigger creates `profiles`
2. Login → verify tokens returned with role
3. Call protected endpoint with valid JWT → 200
4. Call protected endpoint with wrong role → 403
5. Call with unverified email → 403
6. Refresh token → new tokens returned
7. Logout → session cleared
