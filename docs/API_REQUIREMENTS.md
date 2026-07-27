# API Requirements for MVP

**Legend:**
- ✅ scaffolded, no changes needed
- 🔧 scaffolded, needs schema/query changes
- 🆕 new endpoint, no scaffold exists
- 🧩 proposed — screen not in Figma (Create Campaign steps 2–4, business applicant-review, chat/inbox, collaboration/content-submission, signup/login forms); contract defined here so the backend isn't blocked

---

## MVP scope

1. No payment processing. Campaigns show an agreed offer (cash and/or
   product) as display text; payment happens off-platform between business
   and creator. `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` exist in
   `config.py`/`.env.example` but are unused — leave them alone.
2. Instagram data is fetched via the Meta Graph API, not typed in — profile
   stats (follower count, engagement rate, profile photo, portfolio content,
   §2) and campaign content-submission performance (views/likes/comments on
   a submitted Instagram post, §6). Requires the creator to have connected
   Instagram (§2) before submitting Instagram content. YouTube/TikTok stay
   self-reported — not integrated.
3. Media the client controls directly (`media_url`, `content_url`, business
   `logo_url`, etc. — anything not fetched from Instagram per point 2 above)
   is uploaded straight to Supabase Storage; the backend only ever stores
   the resulting URL string. Requires Storage buckets: `avatars` (business
   logos, and creator profile photo as a pre-Instagram-connection fallback),
   `campaign-covers`, `portfolio` (manual additions only — Instagram imports
   don't need one), `content-submissions`, each with an RLS policy scoping
   writes to the owning user.
4. Chat and notifications are polled by the client, not pushed over a
   websocket.

---

## Pagination

Use the existing `PaginationParams` (`page`, `page_size`) from
`app/schemas/common.py` on every list endpoint below. Add a shared envelope:

```python
# app/schemas/common.py
from typing import Generic, TypeVar
T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
```

---

## New enums (`app/core/enums.py`)

```python
class CampaignStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"
    COMPLETED = "completed"

class CompensationType(str, Enum):
    CASH = "cash"
    PRODUCT = "product"
    CASH_AND_PRODUCT = "cash_and_product"

class ApplicationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"

class ApplicationDirection(str, Enum):
    CREATOR_APPLIED = "creator_applied"
    BUSINESS_INVITED = "business_invited"

class CollaborationStatus(str, Enum):
    ACTIVE = "active"
    CONTENT_SUBMITTED = "content_submitted"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class Platform(str, Enum):
    INSTAGRAM = "instagram"
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"

class ContentType(str, Enum):
    POST = "post"
    REEL = "reel"
    STORY = "story"
    VIDEO = "video"
    SHORT = "short"

class CampaignObjective(str, Enum):
    BRAND_AWARENESS = "brand_awareness"
    PRODUCT_LAUNCH = "product_launch"
    FOOT_TRAFFIC = "foot_traffic"
    USER_GENERATED_CONTENT = "user_generated_content"
    SALES_CONVERSION = "sales_conversion"
    EVENT_PROMOTION = "event_promotion"
    OTHER = "other"

class NotificationType(str, Enum):
    APPLICATION_RECEIVED = "application_received"
    APPLICATION_ACCEPTED = "application_accepted"
    APPLICATION_REJECTED = "application_rejected"
    REVISION_REQUESTED = "revision_requested"
    APPLICATION_RESUBMITTED = "application_resubmitted"
    CAMPAIGN_INVITE_RECEIVED = "campaign_invite_received"
    NEW_MESSAGE = "new_message"
    COLLABORATION_COMPLETED = "collaboration_completed"
```

---

## 1. Auth (`/api/v1/auth`)

Everything below `/auth/google` is unchanged. New:

```
POST /auth/instagram   { code: str, redirect_uri: str, role?: "creator" }
→ InstagramAuthResponse (access_token, refresh_token, user, is_new_user)
```

Third signup/login method, creator-only, mirrors `/auth/google`'s
new-vs-returning shape. Uses the Instagram service/token-exchange flow from
§2 directly — not Supabase's native ID-token verification, since Instagram
isn't a Supabase-recognized OAuth provider and returns no email address.
Implementation: `auth_service.instagram_auth()` (see `app/services/auth_service.py`).

- **First-time sign-in** (`role="creator"` required, 400 otherwise): full
  one-tap pre-fill — `name`/`bio`/`website`/`profile_photo_url`/
  `follower_count`/`following_count`/`engagement_rate` all populated from
  Instagram immediately, plus a portfolio import from recent media. No
  separate "connect Instagram" onboarding step needed — unlike Google/email
  signups (see the mandatory gate below).
- **Returning sign-in**: only the stats subset refreshes (matches `sync`'s
  scope in §2) — `name`/`bio`/`website` aren't touched, same reasoning as
  the connect-once/sync-stats-only split there.
- No email address is ever returned by Instagram, but `profiles.email` is
  `NOT NULL UNIQUE` — a placeholder (`ig_{instagram_user_id}@users.kolably.instagram`)
  is used at signup; nothing currently prompts the creator for a real one
  (a good candidate for a later settings-page nudge, not implemented here).
- Session minting has no natural fit in Supabase's normal
  `sign_up`/`sign_in_with_id_token` calls (no password, not a recognized ID
  token) — bridged via `admin.generate_link` + `verify_otp`, entirely
  server-side, nothing emailed anywhere.

**Mandatory onboarding gate:** creators who sign up via Google/email have no
Instagram data yet, so `app/core/dependencies.py` exposes
`require_instagram_connected` — 403 (`instagram_not_connected`) for any
creator without a stored `instagram_access_token`. Superadmins bypass. Add
it alongside `require_role(UserRole.CREATOR)` on creator-action routes as
they get built (`POST /applications`, `POST /collaborations/{id}/submit`,
`POST /chat/conversations`, campaign save/apply) — not on `/auth/me`,
`PATCH /me`, or the `/creators/me/instagram/*` connect endpoints themselves,
since a gated creator still needs to reach those. `GET /campaigns` stays
public/ungated; routing a freshly-Google-signed-up creator straight to the
connect screen before they see the rest of the app is a frontend concern,
not a backend one.

---

## 2. Creators (`/api/v1/creators`)

| Status | Method | Path |
|---|---|---|
| ✅ | GET | `/creators` |
| ✅ | GET | `/creators/{creator_id}` |
| ✅ | PATCH | `/creators/{creator_id}` |
| ✅ | GET | `/creators/{creator_id}/portfolio` |
| ✅ | POST / DELETE | `/creators/{creator_id}/portfolio(/{item_id})` |
| ✅ | GET | `/creators/me/stats` |
| ✅ | GET | `/creators/me/saved-campaigns` |
| 🔧 | POST / DELETE | `/creators/me/saved-campaigns(/{campaign_id})` |
| 🆕 | GET | `/creators/me/instagram/auth-url` |
| 🆕 | POST | `/creators/me/instagram/connect` |
| 🆕 | POST | `/creators/me/instagram/sync` |
| 🆕 | DELETE | `/creators/me/instagram/disconnect` |
| 🆕 | POST | `/creators/me/instagram/import-portfolio` |

`GET /creators` params: `search`, `niche`, `city`, `follower_min`,
`follower_max`, `page`, `page_size` → `PaginatedResponse[CreatorResponse]`.

```python
class CreatorResponse(CreatorBase):
    id: str
    user_id: str
    created_at: datetime
    tiktok_handle: str | None = None
    instagram_connected: bool = False       # NEW
    instagram_synced_at: datetime | None = None   # NEW
    website: str | None = None              # NEW — from Instagram profile
    following_count: int | None = None      # NEW — from Instagram profile
```
`name` and `bio` already exist on `CreatorBase` (self-reported at signup) —
Instagram connect/sync overwrites them in place, see below, rather than
adding separate `instagram_name`/`instagram_bio` fields.

`PortfolioItemResponse` gains `media_type: Literal["photo","video"] = "photo"`,
`like_count: int | None = None`, `comment_count: int | None = None`
(`GET /creators/{id}/portfolio?media_type=video`).

### Instagram connection (Instagram API with Instagram Login)

Uses **Instagram API with Instagram Login** (`graph.instagram.com` /
`instagram.com/oauth/authorize`), not the classic Facebook Login for
Business flow — confirmed by live testing (2026-07-27) against a Business
account added as an Instagram Tester. This flow does **not** require the
creator's Instagram to be linked to a Facebook Page, so the personal-account
conversion prompt only needs to say "convert to Business/Creator," not
"...and link a Facebook Page."

Prerequisite: Meta Developer account + app with the **Instagram API** product
added, Business Verification (✅ done). App Review approval for
`instagram_business_basic` + `instagram_business_manage_insights` is still
required before real (non-Tester) creators can connect — that part remains
real calendar time, start alongside engineering. Until then, engineering/QA
can build and test end-to-end using accounts added as Instagram Testers
(App dashboard → Instagram API → Roles), which get full scope access
immediately without waiting on App Review.

Config: `INSTAGRAM_APP_ID` / `INSTAGRAM_APP_SECRET` (not the generic
`APP_ID`/`APP_SECRET`, which belong to a separate, unused Facebook Login
product on the same Meta app).

```
GET    /creators/me/instagram/auth-url        → { "url": str }
POST   /creators/me/instagram/connect         { "code": str }        → CreatorResponse
POST   /creators/me/instagram/sync            → CreatorResponse
DELETE /creators/me/instagram/disconnect      → 204
POST   /creators/me/instagram/import-portfolio → list[PortfolioItemResponse]
```

- `auth-url` returns the `instagram.com/oauth/authorize` URL (client_id=
  `INSTAGRAM_APP_ID`, scope=`instagram_business_basic,instagram_business_manage_insights`)
  for the client to redirect to.
- `connect` exchanges the returned `code` for a short-lived token, then
  exchanges that for a long-lived token via `GET
  graph.instagram.com/access_token?grant_type=ig_exchange_token` (~60-day
  expiry, confirmed by testing: `expires_in=5183854`s). Immediately calls
  `graph.instagram.com/me?fields=followers_count,follows_count,profile_picture_url,name,biography,website`
  plus media insights for `engagement_rate`, and does a **one-time full
  pre-fill**: `follower_count`/`following_count`/`profile_photo_url`/
  `engagement_rate`/`name`/`bio`/`website`, replacing whatever was
  self-reported/uploaded at signup.
- `sync` only re-fetches the pure-stats subset —
  `follower_count`/`following_count`/`profile_photo_url`/`engagement_rate` —
  on demand (call on profile view if `instagram_synced_at` is stale, e.g.
  >24h). It deliberately does **not** re-fetch `name`/`bio`/`website` on
  every sync: those are one-time pre-fill only, so a creator who
  customizes their Kolably bio/name after connecting (e.g. adds a
  Kolably-specific pitch) doesn't get silently overwritten by their
  Instagram bio on the next sync. Should also proactively refresh the
  long-lived token via `grant_type=ig_refresh_token` well before its 60-day
  expiry (e.g. whenever <10 days remain).
- `import-portfolio` pulls the creator's recent IG media
  (`/{ig-user-id}/media`) into `portfolio_items` — `media_url`, `post_link`
  (permalink), `media_type`, `like_count`, `comment_count` all come from the
  Graph API response. The response's `media_product_type` field
  (`FEED`/`REELS`/`STORY`) reliably distinguishes Reels from regular
  feed posts/carousels if finer-grained typing than `photo`/`video` is
  ever wanted.
- Token fields (`instagram_access_token`, `instagram_user_id`) are never
  serialized in `CreatorResponse` — internal only.

```
GET /creators/me/stats
{ "active_collaborations_count": 3, "engagement_growth_pct": null }
```
`active_collaborations_count` = count of `collaborations` where
`creator_id = me AND status = 'active'`. `engagement_growth_pct` has no data
source (would need historical snapshots) — always `null`, client hides that
stat tile.

```
POST   /creators/me/saved-campaigns/{campaign_id}   → 204
DELETE /creators/me/saved-campaigns/{campaign_id}   → 204
GET    /creators/me/saved-campaigns                 → PaginatedResponse[CampaignResponse]
```
```sql
CREATE TABLE saved_campaigns (
  creator_id UUID REFERENCES creators(id) ON DELETE CASCADE,
  campaign_id UUID REFERENCES campaigns(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (creator_id, campaign_id)
);
```

---

## 3. Businesses (`/api/v1/businesses`)

| Status | Method | Path |
|---|---|---|
| ✅ | GET | `/businesses` |
| ✅ | GET | `/businesses/{business_id}` |
| ✅ | PATCH | `/businesses/{business_id}` |
| ✅ | GET | `/businesses/{business_id}/campaigns` |
| ✅ | GET | `/businesses/me/stats` |
| ✅ | GET | `/businesses/me/campaigns` |
| ✅ | GET | `/businesses/me/applications` |

`BusinessResponse` gains `is_verified: bool = False` — manual flag, set by
superadmin via the existing `PATCH /businesses/{id}` path.

```
GET /businesses/me/stats
{
  "total_reach": 1200000,
  "reach_change_pct": 12.4,
  "avg_engagement_rate": 4.8,
  "engagement_series": [3.9, 4.1, 4.6, 4.4, 5.0, 4.8, 4.8]
}
```
Computed from `content_submissions` joined through `collaborations` for this
business: `total_reach` = `SUM(views)` all-time; `reach_change_pct` = last 30
days vs. the prior 30; `avg_engagement_rate` = `AVG((likes+comments)/NULLIF(views,0))`
over the last 30 days; `engagement_series` = same ratio bucketed per day, last
7 days, `0` (not `null`) on days with no submissions. Zero submissions →
all-zero response, not an error.

`GET /businesses/me/applications` → `PaginatedResponse[ApplicationWithCreator]` (§5).

---

## 4. Campaigns (`/api/v1/campaigns`)

| Status | Method | Path |
|---|---|---|
| 🔧 | POST | `/campaigns` |
| 🧩 | PATCH | `/campaigns/{id}/deliverables` |
| 🧩 | PATCH | `/campaigns/{id}/targeting` |
| 🧩 | POST | `/campaigns/{id}/publish` |
| ✅ | GET | `/campaigns` |
| ✅ | GET | `/campaigns/{campaign_id}` |
| ✅ | PATCH / DELETE | `/campaigns/{campaign_id}` |
| ✅ | GET | `/campaigns/{campaign_id}/applications` |
| ✅ | GET | `/campaigns/categories` |
| 🔧 | POST | `/campaigns/{campaign_id}/invite` |

### Create flow — 4 steps, draft on step 1, publish at the end

**Step 1** (confirmed — "Campaign Foundations"):
```
POST /campaigns
{ "title": str, "objective": CampaignObjective, "description": str }
→ CampaignResponse (status="draft")
```

**Step 2** 🧩 (deliverables & offer):
```
PATCH /campaigns/{id}/deliverables
{
  "deliverables": [
    { "platform": Platform, "content_type": ContentType, "quantity": int,
      "description": str | null, "required": bool = true }
  ],
  "compensation_type": CompensationType,
  "cash_amount_min": float | null,
  "cash_amount_max": float | null,
  "free_product_description": str | null
}
```

**Step 3** 🧩 (targeting):
```
PATCH /campaigns/{id}/targeting
{
  "creator_category": str, "follower_range_min": int | null,
  "follower_range_max": int | null, "min_engagement_rate": float | null,
  "location": str, "max_creators": int,
  "additional_requirements": str | null
}
```

**Step 4** 🧩 (publish):
```
PATCH /campaigns/{id}   // cover_image_url, deadline
POST  /campaigns/{id}/publish
→ CampaignResponse (status="active")
```
`publish` validates all required fields from steps 1–3 are present; 422 with
the missing fields listed if not.

```python
class CampaignResponse(BaseModel):
    id: str
    business_id: str
    title: str
    objective: CampaignObjective
    description: str
    cover_image_url: str | None = None
    deliverables: list[DeliverableItem]
    compensation_type: CompensationType
    cash_amount_min: float | None = None
    cash_amount_max: float | None = None
    free_product_description: str | None = None
    creator_category: str
    follower_range_min: int | None = None
    follower_range_max: int | None = None
    min_engagement_rate: float | None = None
    location: str
    max_creators: int
    additional_requirements: str | None = None
    deadline: datetime | None = None
    status: CampaignStatus
    created_at: datetime
    applicant_count: int | None = None   # computed, list endpoints only
    accepted_count: int | None = None    # computed, list endpoints only
```

`GET /campaigns` params: `search`, `category`, `recommended=true` (filters by
the requesting creator's `niche`), `page`, `page_size`.

`GET /campaigns/categories` — static list backing the category filter chips.

```
POST /campaigns/{campaign_id}/invite
{ "creator_id": str, "message": str | null }
→ ApplicationResponse (direction="business_invited", status="pending")
```
Uses the `campaign_applications` table (§5), not a separate table.

---

## 5. Applications (`/api/v1/applications`)

| Status | Method | Path |
|---|---|---|
| 🔧 | POST | `/applications` |
| ✅ | GET | `/applications/{application_id}` |
| 🔧 | PATCH | `/applications/{application_id}/accept` |
| 🔧 | PATCH | `/applications/{application_id}/reject` |
| 🧩 | PATCH | `/applications/{application_id}/request-revision` |
| 🧩 | PATCH | `/applications/{application_id}` (resubmit) |
| ✅ | GET | `/applications/me/sent` |

```python
class ApplicationResponse(BaseModel):
    id: str
    campaign_id: str
    creator_id: str
    direction: ApplicationDirection = ApplicationDirection.CREATOR_APPLIED
    message: str | None = None
    instagram_handle: str | None = None
    example_content_url: str | None = None
    status: ApplicationStatus
    revision_reason: str | None = None
    created_at: datetime

class ApplicationWithCampaign(ApplicationResponse):
    """GET /applications/me/sent"""
    campaign: CampaignSummary   # id, title, cover_image_url, deadline, compensation_type, cash_amount_min/max
    business: BusinessSummary   # id, business_name, logo_url

class ApplicationWithCreator(ApplicationResponse):
    """GET /campaigns/{id}/applications, GET /businesses/me/applications"""
    creator: CreatorSummary     # id, name, profile_photo_url, follower_count, niche
```

```
PATCH /applications/{id}/request-revision   { "reason": str }   — business only
→ status = "revision_requested"

PATCH /applications/{id}   { message?, instagram_handle?, example_content_url? }   — creator only,
                                                                only when status == "revision_requested"
→ status = "pending"
```

Authorization:
- `POST /applications` — creator only, `direction=creator_applied`.
- `POST /campaigns/{id}/invite` — business only, `direction=business_invited`.
- `accept`/`reject`/`request-revision` — gated by `direction`: for
  `creator_applied`, the business decides; for `business_invited`, the
  creator decides.
- Accepting an application (either direction) creates the `Collaboration` row.

---

## 6. Collaborations (`/api/v1/collaborations`)

| Status | Method | Path |
|---|---|---|
| ✅ | GET | `/collaborations` |
| ✅ | GET | `/collaborations/{collaboration_id}` |
| 🧩 | POST | `/collaborations/{collaboration_id}/submit` |
| 🧩 | POST | `/collaborations/{collaboration_id}/content-submissions/{submission_id}/sync` |
| ✅ | PATCH | `/collaborations/{collaboration_id}/complete` |
| ✅ | PATCH | `/collaborations/{collaboration_id}/cancel` |

A campaign can require multiple deliverables, so a collaboration can have
multiple content submissions — `submit` appends, it doesn't replace.

```python
class ContentSubmissionResponse(BaseModel):
    id: str
    collaboration_id: str
    content_url: str
    platform: Platform
    views: int | None = None       # fetched from Meta Graph API for platform=instagram; self-reported for other platforms
    likes: int | None = None
    comments: int | None = None
    synced_at: datetime | None = None   # NEW — when views/likes/comments were last fetched from Instagram
    submitted_at: datetime

class ContentSubmitRequest(BaseModel):
    content_url: str
    platform: Platform
    views: int | None = None       # required for non-instagram platforms; ignored/rejected for platform=instagram
    likes: int | None = None
    comments: int | None = None
    notes: str | None = None

class CollaborationResponse(BaseModel):
    id: str
    campaign_id: str
    creator_id: str
    business_id: str
    status: CollaborationStatus
    content_submissions: list[ContentSubmissionResponse] = []
    affiliate_url: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
```

For `platform=instagram`: the creator must already be Instagram-connected
(§2) — `submit` resolves the IG media object from `content_url` via the
Graph API (using the stored access token) and fetches `views` (impressions/
reach), `likes`, `comments` directly, ignoring/rejecting any values passed in
the request. Not connected → 422, tell the creator to connect Instagram
first. For any other `platform`, the request's `views`/`likes`/`comments`
are stored as given (self-reported, unintegrated).

`POST .../content-submissions/{submission_id}/sync` re-fetches
`views`/`likes`/`comments` for an `instagram` submission (posts keep
accumulating engagement after submission) — no-op / 400 for non-Instagram
submissions.

`POST /collaborations/{id}/submit` appends a row; once submissions cover all
`required` deliverables, status auto-flips to `content_submitted`. Business
then calls `complete` or `cancel` — no per-submission approval step.

---

## 7. Chat (`/api/v1/chat`)

| Status | Method | Path |
|---|---|---|
| ✅ | GET | `/chat/conversations` |
| ✅ | GET | `/chat/conversations/{conversation_id}` |
| ✅ | POST | `/chat/conversations/{conversation_id}/messages` |
| 🧩 | POST | `/chat/conversations` |
| ✅ | GET | `/chat/unread-count` |

```
POST /chat/conversations
{ "participant_id": str, "collaboration_id": str | null }
```
Get-or-create: returns the existing conversation (200) between the two
participants for that `collaboration_id` if one exists, else creates (201).

```python
class ConversationResponse(BaseModel):
    id: str
    participant_ids: list[str]
    other_participant: ParticipantSummary   # id, name/business_name, avatar url
    collaboration_id: str | None = None
    last_message: str | None = None
    last_message_at: datetime | None = None
    unread_count: int = 0
    created_at: datetime
```

`GET /chat/unread-count` → `{ "unread_count": int }`, total across all
conversations for the current user.

```sql
CREATE TABLE conversation_reads (
  conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
  profile_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
  last_read_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (conversation_id, profile_id)
);
```
`last_read_at` updates whenever `GET /chat/conversations/{id}` is called —
no separate mark-read endpoint.

---

## 8. Notifications

| Status | Method | Path |
|---|---|---|
| ✅ | GET | `/notifications` |
| ✅ | GET | `/notifications/unread-count` |
| 🆕 | PATCH | `/notifications/{notification_id}/read` |
| 🆕 | PATCH | `/notifications/read-all` |

```python
class NotificationResponse(BaseModel):
    id: str
    profile_id: str
    type: NotificationType
    title: str
    body: str
    related_id: str | None = None
    is_read: bool = False
    created_at: datetime
```

```sql
CREATE TABLE notifications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  profile_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  related_id UUID,
  is_read BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_notifications_profile_unread ON notifications(profile_id, is_read);
```

Emitted as a side effect from existing services: `application_service` (on
create → notify business; on accept/reject/revision-request → notify
creator; on resubmit → notify business), `chat_service` (on new message →
notify other participant), `collaboration_service` (on complete → notify
creator).

---

## New DB tables/columns — full summary

```sql
-- creators
ALTER TABLE creators ADD COLUMN tiktok_handle TEXT;
ALTER TABLE creators ADD COLUMN instagram_user_id TEXT;
ALTER TABLE creators ADD COLUMN instagram_access_token TEXT;   -- encrypted at rest
ALTER TABLE creators ADD COLUMN instagram_token_expires_at TIMESTAMPTZ;
ALTER TABLE creators ADD COLUMN instagram_synced_at TIMESTAMPTZ;
ALTER TABLE creators ADD COLUMN website TEXT;
ALTER TABLE creators ADD COLUMN following_count INT;

-- portfolio_items
ALTER TABLE portfolio_items ADD COLUMN media_type TEXT DEFAULT 'photo';
ALTER TABLE portfolio_items ADD COLUMN like_count INT;
ALTER TABLE portfolio_items ADD COLUMN comment_count INT;

-- businesses
ALTER TABLE businesses ADD COLUMN is_verified BOOLEAN DEFAULT FALSE;

-- campaigns
ALTER TABLE campaigns ADD COLUMN cover_image_url TEXT;
ALTER TABLE campaigns ADD COLUMN objective TEXT;
ALTER TABLE campaigns ALTER COLUMN deliverables TYPE JSONB USING deliverables::JSONB;
ALTER TABLE campaigns ADD COLUMN compensation_type TEXT;
ALTER TABLE campaigns ADD COLUMN cash_amount_min NUMERIC;
ALTER TABLE campaigns ADD COLUMN cash_amount_max NUMERIC;
ALTER TABLE campaigns ADD COLUMN free_product_description TEXT;
ALTER TABLE campaigns ADD COLUMN min_engagement_rate NUMERIC;
ALTER TABLE campaigns ADD COLUMN max_creators INT;
ALTER TABLE campaigns ADD COLUMN additional_requirements TEXT;

-- campaign_applications
ALTER TABLE campaign_applications ADD COLUMN direction TEXT DEFAULT 'creator_applied';
ALTER TABLE campaign_applications ADD COLUMN revision_reason TEXT;
ALTER TABLE campaign_applications DROP CONSTRAINT campaign_applications_application_status_check;
ALTER TABLE campaign_applications ADD CONSTRAINT campaign_applications_application_status_check
  CHECK (application_status IN ('pending','accepted','rejected','revision_requested'));

-- content_submissions
ALTER TABLE content_submissions ADD COLUMN synced_at TIMESTAMPTZ;

-- new tables
CREATE TABLE saved_campaigns ( ... );        -- see §2
CREATE TABLE conversation_reads ( ... );     -- see §7
CREATE TABLE notifications ( ... );          -- see §8
```

---

## Build order

0. **Business Verification done ✅. Submit App Review immediately** for
   `instagram_business_basic`/`instagram_business_manage_insights` on the
   Instagram API product — this is calendar time (1–4+ weeks), not
   engineering time. It gates real (non-Tester) creators connecting, but not
   engineering — see §2 for the confirmed-working Instagram Tester testing
   path in the meantime.
1. Creators + Businesses read paths (`GET /creators`, `GET /creators/{id}`, `GET /businesses/{id}`)
2. Instagram connection flow (`/creators/me/instagram/*`) — build and test
   end-to-end now against accounts added as Instagram Testers (confirmed
   working: profile stats, media list, insights all return correctly); can't
   go live for real creators until App Review is approved
3. Campaigns — full 4-step create/publish flow
4. Applications — including `direction` and revision workflow
5. Collaborations — multi-submission content tracking
6. Dashboard aggregates (`businesses/me/campaigns`, `businesses/me/applications`, `creators/me/stats`, `businesses/me/stats`)
7. Chat — get-or-create, unread counts, auto-create on acceptance
8. Notifications — last, once the events to notify on already exist
