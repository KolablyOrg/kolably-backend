"""Create two test accounts and seed data around them:

  1. A Superadmin-as-Business account (admin@kolably.com by default) --
     a real auth user with role='superadmin' that's ALSO linked to a
     businesses row, so business-only endpoints are testable from the
     same login as superadmin-only endpoints.

  2. A dedicated Creator account (creator.test@kolably.com by default)
     with a full creators row (bio, niche, follower/engagement stats,
     Instagram pre-fill fields) and enough linked data to exercise the
     creator flow end-to-end without any manual setup:
       - portfolio items already populated
       - a PENDING application on the admin business's active campaign
         (so you can test both sides of accept/reject)
       - a COMPLETED collaboration on the admin business's completed
         campaign, with a content submission already logged
       - a saved campaign
       - a conversation + messages tied to that collaboration
       - notifications on both the creator and business side

Why not just use Priya from seed_sample_data.sql?
--------------------------------------------------
Priya already has history baked into seed_sample_data.sql, which is fine
for read-path testing but awkward once you start mutating state (e.g.
accepting a pending application, marking a collab complete) because
you'd be editing data another test script/script depends on. This script
creates a second, independent creator specifically so you have a
disposable, fully-owned sandbox for the creator side.

Idempotent: safe to re-run. Uses fixed UUIDs + upsert (ignore-duplicates),
so it will not create duplicate rows.

Prereqs
-------
  - All migrations applied (incl. 002/003/015/017/018 in this repo)
  - .env configured with SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY
  - Running this script alone is enough -- it does NOT require
    seed_sample_data.sql to have been run first.

Usage
-----
  .venv\\Scripts\\python.exe scripts/seed_superadmin_business.py
  .venv\\Scripts\\python.exe scripts/seed_superadmin_business.py --skip-creator
  .venv\\Scripts\\python.exe scripts/seed_superadmin_business.py \\
      --admin-email admin@kolably.com --admin-password AdminPass123! \\
      --creator-email creator.test@kolably.com --creator-password CreatorPass123!

Not a pytest file -- manual/dev seeding only. Never run against production.
"""

import argparse
import sys

import httpx

sys.path.insert(0, ".")
from app.core.config import settings  # noqa: E402

DEFAULT_ADMIN_EMAIL = "admin@kolably.com"
DEFAULT_ADMIN_PASSWORD = "AdminPass123!"
DEFAULT_CREATOR_EMAIL = "creator.test@kolably.com"
DEFAULT_CREATOR_PASSWORD = "CreatorPass123!"

# ── Fixed IDs (admin/business side) ─────────────────────────────────────
BUSINESS_ID = "adb00000-0000-0000-0000-000000000001"
CAMPAIGN_DRAFT_ID = "adc00000-0000-0000-0000-000000000001"
CAMPAIGN_ACTIVE_ID = "adc00000-0000-0000-0000-000000000002"
CAMPAIGN_COMPLETED_ID = "adc00000-0000-0000-0000-000000000003"

# ── Fixed IDs (Priya cross-account data, from seed_sample_data.sql) ─────
PRIYA_CREATOR_ID = "c1111111-1111-1111-1111-111111111111"
PRIYA_PROFILE_ID = "4417a424-386b-4fae-8d98-36e5787359bd"
PRIYA_APPLICATION_ID = "ada00000-0000-0000-0000-000000000001"
PRIYA_COLLAB_ID = "adcb0000-0000-0000-0000-000000000001"
PRIYA_CONTENT_SUBMISSION_ID = "adcs0000-0000-0000-0000-000000000001"
PRIYA_CONVERSATION_ID = "adcv0000-0000-0000-0000-000000000001"
PRIYA_MESSAGE_1_ID = "adms0000-0000-0000-0000-000000000001"
PRIYA_MESSAGE_2_ID = "adms0000-0000-0000-0000-000000000002"
PRIYA_NOTIF_APPLICATION_ID = "adn00000-0000-0000-0000-000000000001"
PRIYA_NOTIF_MESSAGE_ID = "adn00000-0000-0000-0000-000000000002"

# ── Fixed IDs (new dedicated test creator) ──────────────────────────────
TEST_CREATOR_ID = "cd000000-0000-0000-0000-000000000001"
TEST_PORTFOLIO_1_ID = "cdp00000-0000-0000-0000-000000000001"
TEST_PORTFOLIO_2_ID = "cdp00000-0000-0000-0000-000000000002"
TEST_PORTFOLIO_3_ID = "cdp00000-0000-0000-0000-000000000003"
TEST_APPLICATION_PENDING_ID = "cda00000-0000-0000-0000-000000000001"
TEST_APPLICATION_ACCEPTED_ID = "cda00000-0000-0000-0000-000000000002"
TEST_COLLAB_ID = "cdcb0000-0000-0000-0000-000000000001"
TEST_CONTENT_SUBMISSION_ID = "cdcs0000-0000-0000-0000-000000000001"
TEST_CONVERSATION_ID = "cdcv0000-0000-0000-0000-000000000001"
TEST_MESSAGE_1_ID = "cdms0000-0000-0000-0000-000000000001"
TEST_MESSAGE_2_ID = "cdms0000-0000-0000-0000-000000000002"
TEST_MESSAGE_3_ID = "cdms0000-0000-0000-0000-000000000003"
TEST_NOTIF_APPLICATION_ID = "cdn00000-0000-0000-0000-000000000001"
TEST_NOTIF_ACCEPTED_ID = "cdn00000-0000-0000-0000-000000000002"
TEST_NOTIF_MESSAGE_ID = "cdn00000-0000-0000-0000-000000000003"


# ── helpers ──────────────────────────────────────────────────────────────

def rest_headers(prefer: str | None = None) -> dict:
    h = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def admin_headers() -> dict:
    return {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


def find_profile_by_email(client: httpx.Client, email: str) -> dict | None:
    r = client.get(
        f"{settings.SUPABASE_URL}/rest/v1/profiles",
        headers=rest_headers(),
        params={"email": f"eq.{email}", "select": "*"},
        timeout=15,
    )
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def create_auth_user(client: httpx.Client, email: str, password: str, role: str) -> str:
    """Create the auth user with `role` baked into user_metadata, so the
    on_auth_user_created trigger creates the profiles row at the right
    role already. Returns the auth uid."""
    r = client.post(
        f"{settings.SUPABASE_URL}/auth/v1/admin/users",
        headers=admin_headers(),
        json={
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {"role": role},
        },
        timeout=15,
    )
    if r.status_code in (200, 201):
        return r.json()["id"]
    # Already exists -> look it up instead of failing.
    if r.status_code in (400, 422) and "already" in r.text.lower():
        existing = find_profile_by_email(client, email)
        if existing:
            return existing["auth_id"]
    raise RuntimeError(f"create_auth_user failed: {r.status_code} {r.text}")


def upsert(client: httpx.Client, table: str, rows: list[dict], on_conflict: str) -> None:
    r = client.post(
        f"{settings.SUPABASE_URL}/rest/v1/{table}",
        headers=rest_headers(prefer="resolution=ignore-duplicates,return=minimal"),
        params={"on_conflict": on_conflict},
        json=rows,
        timeout=15,
    )
    if r.status_code not in (200, 201, 204):
        raise RuntimeError(f"upsert into {table} failed: {r.status_code} {r.text}")


# ── admin/business side ──────────────────────────────────────────────────

def ensure_superadmin_profile(client: httpx.Client, auth_id: str, email: str) -> dict:
    profile = find_profile_by_email(client, email)
    if profile is None:
        raise RuntimeError(
            "Auth user was created but no profiles row appeared. "
            "Check that migration 015 (auth_user_trigger) is applied."
        )
    if profile.get("role") != "superadmin":
        r = client.patch(
            f"{settings.SUPABASE_URL}/rest/v1/profiles",
            headers=rest_headers(prefer="return=representation"),
            params={"auth_id": f"eq.{auth_id}"},
            json={"role": "superadmin"},
            timeout=15,
        )
        r.raise_for_status()
        profile = r.json()[0]
    return profile


def ensure_business(client: httpx.Client, profile_id: str) -> str:
    r = client.get(
        f"{settings.SUPABASE_URL}/rest/v1/businesses",
        headers=rest_headers(),
        params={"profile_id": f"eq.{profile_id}", "select": "id"},
        timeout=15,
    )
    r.raise_for_status()
    rows = r.json()
    if rows:
        return rows[0]["id"]

    r = client.post(
        f"{settings.SUPABASE_URL}/rest/v1/businesses",
        headers=rest_headers(prefer="return=representation"),
        json={
            "id": BUSINESS_ID,
            "profile_id": profile_id,
            "business_name": "Kolably HQ (Admin Test Business)",
            "owner_name": "Kolably Admin",
            "category": "Platform",
            "description": "Internal superadmin account used for cross-role API testing.",
            "website": "https://kolably.com",
            "instagram_handle": "@kolablyofficial",
            "city": "Delhi",
            "address": "Kolably Office, New Delhi",
            "logo_url": "https://example.com/logos/kolably-admin.png",
            "industry": "technology",
            "is_verified": True,
        },
        timeout=15,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"business insert failed: {r.status_code} {r.text}")
    return r.json()[0]["id"]


def seed_campaigns(client: httpx.Client, business_id: str) -> None:
    upsert(
        client,
        "campaigns",
        [
            {
                "id": CAMPAIGN_DRAFT_ID,
                "business_id": business_id,
                "title": "Admin Draft Campaign (edit/targeting flow)",
                "objective": "brand_awareness",
                "description": "Draft campaign for testing the create/deliverables/targeting/publish flow.",
                "deliverables": None,
                "compensation_type": None,
                "creator_category": None,
                "status": "draft",
            },
            {
                "id": CAMPAIGN_ACTIVE_ID,
                "business_id": business_id,
                "title": "Admin Active Campaign (application flow)",
                "objective": "product_launch",
                "description": "Active campaign for testing creator applications, saves, and browsing.",
                "deliverables": [
                    {"platform": "instagram", "content_type": "reel", "quantity": 1,
                     "description": "Feature the product", "required": True},
                ],
                "compensation_type": "cash",
                "cash_amount_min": 2500,
                "cash_amount_max": 6000,
                "creator_category": "tech",
                "follower_range_min": 5000,
                "follower_range_max": 200000,
                "min_engagement_rate": 2.0,
                "location": "Delhi",
                "max_creators": 5,
                "additional_requirements": "Must have posted tech content before.",
                "deadline": "2026-11-30T23:59:59Z",
                "status": "active",
            },
            {
                "id": CAMPAIGN_COMPLETED_ID,
                "business_id": business_id,
                "title": "Admin Completed Campaign (collaboration/history flow)",
                "objective": "engagement",
                "description": "Completed campaign for testing collaboration history and content submissions.",
                "deliverables": [
                    {"platform": "instagram", "content_type": "post", "quantity": 1, "required": True},
                ],
                "compensation_type": "cash_and_product",
                "cash_amount_min": 1500,
                "cash_amount_max": 3000,
                "free_product_description": "Free product bundle",
                "creator_category": "food",
                "follower_range_min": 10000,
                "follower_range_max": 100000,
                "min_engagement_rate": 3.0,
                "location": "Delhi",
                "max_creators": 2,
                "deadline": "2026-05-31T23:59:59Z",
                "status": "completed",
            },
        ],
        on_conflict="id",
    )


def seed_priya_cross_account_data(client: httpx.Client, business_id: str, superadmin_profile_id: str) -> bool:
    """Everything that links the admin business to the existing Priya
    creator from seed_sample_data.sql. Returns False (and skips) if that
    creator doesn't exist yet -- this is optional, not required."""
    r = client.get(
        f"{settings.SUPABASE_URL}/rest/v1/creators",
        headers=rest_headers(),
        params={"id": f"eq.{PRIYA_CREATOR_ID}", "select": "id"},
        timeout=15,
    )
    r.raise_for_status()
    if not r.json():
        print("  SKIP  Priya creator (from seed_sample_data.sql) not found — "
              "run that script first if you also want this cross-account data.")
        return False

    upsert(
        client,
        "campaign_applications",
        [{
            "id": PRIYA_APPLICATION_ID,
            "campaign_id": CAMPAIGN_COMPLETED_ID,
            "creator_id": PRIYA_CREATOR_ID,
            "direction": "creator_applied",
            "message": "Would love to be part of this one too!",
            "instagram_handle": "@priya.eats",
            "example_content_url": "https://instagram.com/reel/example-admin",
            "status": "accepted",
        }],
        on_conflict="id",
    )
    upsert(
        client,
        "collaborations",
        [{
            "id": PRIYA_COLLAB_ID,
            "application_id": PRIYA_APPLICATION_ID,
            "campaign_id": CAMPAIGN_COMPLETED_ID,
            "creator_id": PRIYA_CREATOR_ID,
            "business_id": business_id,
            "status": "completed",
            "completed_at": "2026-06-01T10:00:00Z",
        }],
        on_conflict="id",
    )
    upsert(
        client,
        "content_submissions",
        [{
            "id": PRIYA_CONTENT_SUBMISSION_ID,
            "collaboration_id": PRIYA_COLLAB_ID,
            "content_url": "https://instagram.com/p/admin-collab-post",
            "platform": "instagram",
            "views": 18000,
            "likes": 1200,
            "comments": 95,
            "notes": "Seeded content submission for admin/business testing.",
        }],
        on_conflict="id",
    )
    upsert(
        client,
        "saved_campaigns",
        [{"creator_id": PRIYA_CREATOR_ID, "campaign_id": CAMPAIGN_ACTIVE_ID}],
        on_conflict="creator_id,campaign_id",
    )
    upsert(
        client, "conversations", [{"id": PRIYA_CONVERSATION_ID, "collaboration_id": PRIYA_COLLAB_ID}], on_conflict="id"
    )
    upsert(
        client,
        "conversation_participants",
        [
            {"conversation_id": PRIYA_CONVERSATION_ID, "profile_id": PRIYA_PROFILE_ID},
            {"conversation_id": PRIYA_CONVERSATION_ID, "profile_id": superadmin_profile_id},
        ],
        on_conflict="conversation_id,profile_id",
    )
    upsert(
        client,
        "messages",
        [
            {"id": PRIYA_MESSAGE_1_ID, "conversation_id": PRIYA_CONVERSATION_ID, "sender_id": superadmin_profile_id,
             "content": "Hi Priya, thanks for the collab — the post looks great!"},
            {"id": PRIYA_MESSAGE_2_ID, "conversation_id": PRIYA_CONVERSATION_ID, "sender_id": PRIYA_PROFILE_ID,
             "content": "Thank you! Happy to work together again."},
        ],
        on_conflict="id",
    )
    upsert(
        client,
        "conversation_reads",
        [
            {"conversation_id": PRIYA_CONVERSATION_ID, "profile_id": PRIYA_PROFILE_ID},
            {"conversation_id": PRIYA_CONVERSATION_ID, "profile_id": superadmin_profile_id},
        ],
        on_conflict="conversation_id,profile_id",
    )
    upsert(
        client,
        "notifications",
        [
            {"id": PRIYA_NOTIF_APPLICATION_ID, "profile_id": superadmin_profile_id, "type": "application_received",
             "title": "New Application Received",
             "body": "Priya Sharma applied to your Admin Completed Campaign.",
             "related_id": PRIYA_APPLICATION_ID, "is_read": True},
            {"id": PRIYA_NOTIF_MESSAGE_ID, "profile_id": PRIYA_PROFILE_ID, "type": "new_message",
             "title": "New Message", "body": "Kolably HQ sent you a message.",
             "related_id": PRIYA_CONVERSATION_ID, "is_read": False},
        ],
        on_conflict="id",
    )
    return True


# ── creator side ──────────────────────────────────────────────────────────

def ensure_creator_profile(client: httpx.Client, email: str) -> dict:
    """Trigger already defaults role to 'creator' via COALESCE(...,'creator'),
    and we also pass user_metadata.role='creator' explicitly -- no escalation
    step needed here, just fetch the row."""
    profile = find_profile_by_email(client, email)
    if profile is None:
        raise RuntimeError(
            "Auth user was created but no profiles row appeared. "
            "Check that migration 015 (auth_user_trigger) is applied."
        )
    return profile


def ensure_creator_row(client: httpx.Client, profile_id: str) -> str:
    r = client.get(
        f"{settings.SUPABASE_URL}/rest/v1/creators",
        headers=rest_headers(),
        params={"profile_id": f"eq.{profile_id}", "select": "id"},
        timeout=15,
    )
    r.raise_for_status()
    rows = r.json()
    if rows:
        return rows[0]["id"]

    r = client.post(
        f"{settings.SUPABASE_URL}/rest/v1/creators",
        headers=rest_headers(prefer="return=representation"),
        json={
            "id": TEST_CREATOR_ID,
            "profile_id": profile_id,
            "name": "Arjun Verma",
            "username": "arjun.codes",
            "bio": "Tech reviewer and gadget unboxer. Testing account for the creator flow end-to-end.",
            "instagram_handle": "@arjun.codes",
            "follower_count": 32000,
            "engagement_rate": 3.9,
            "profile_photo_url": "https://example.com/photos/arjun.jpg",
            "city": "Bengaluru",
            "niche": "tech",
            "youtube_handle": "@arjunverma",
            "tiktok_handle": None,
            "website": "https://arjunverma.dev",
            "following_count": 512,
            # Pre-set so Instagram-gated actions (e.g. saving campaigns) work
            # out of the box in local/dev testing without a real OAuth round trip.
            "instagram_user_id": "17841400000000000",
            "instagram_access_token": "dev-seeded-token-not-real",
            "instagram_token_expires_at": "2026-12-31T23:59:59Z",
            "instagram_synced_at": "2026-08-01T00:00:00Z",
        },
        timeout=15,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"creator insert failed: {r.status_code} {r.text}")
    return r.json()[0]["id"]


def seed_creator_portfolio(client: httpx.Client, creator_id: str) -> None:
    upsert(
        client,
        "portfolio_items",
        [
            {"id": TEST_PORTFOLIO_1_ID, "creator_id": creator_id,
             "media_url": "https://example.com/portfolio/arjun-unboxing.mp4",
             "post_link": "https://instagram.com/reel/arjun-example1",
             "media_type": "video", "title": "Unboxing the latest flagship phone",
             "like_count": 5400, "comment_count": 310},
            {"id": TEST_PORTFOLIO_2_ID, "creator_id": creator_id,
             "media_url": "https://example.com/portfolio/arjun-review.jpg",
             "post_link": "https://instagram.com/p/arjun-example2",
             "media_type": "photo", "title": "Laptop review — desk setup shot",
             "like_count": 2200, "comment_count": 90},
            {"id": TEST_PORTFOLIO_3_ID, "creator_id": creator_id,
             "media_url": "https://example.com/portfolio/arjun-comparison.mp4",
             "post_link": "https://instagram.com/reel/arjun-example3",
             "media_type": "video", "title": "Budget earbuds comparison",
             "like_count": 3100, "comment_count": 145},
        ],
        on_conflict="id",
    )


def seed_creator_journey(client: httpx.Client, creator_id: str, creator_profile_id: str,
                          business_id: str, business_profile_id: str) -> None:
    """Gives the test creator one PENDING application (to test the
    apply -> business reviews -> accept/reject loop) and one already
    COMPLETED collaboration (to test history, content submissions, and
    messaging without extra setup)."""

    # Pending application on the active campaign -- test creator applying
    # and business accepting/rejecting from the same starting point.
    upsert(
        client,
        "campaign_applications",
        [{
            "id": TEST_APPLICATION_PENDING_ID,
            "campaign_id": CAMPAIGN_ACTIVE_ID,
            "creator_id": creator_id,
            "direction": "creator_applied",
            "message": (
                "Hi! I cover tech/gadget content and think this campaign is a great fit — "
                "32K followers, 3.9% engagement."
            ),
            "instagram_handle": "@arjun.codes",
            "example_content_url": "https://instagram.com/reel/arjun-example1",
            "status": "pending",
        }],
        on_conflict="id",
    )

    # Already-accepted application + completed collaboration on the
    # completed campaign -- test collaboration history / content review.
    upsert(
        client,
        "campaign_applications",
        [{
            "id": TEST_APPLICATION_ACCEPTED_ID,
            "campaign_id": CAMPAIGN_COMPLETED_ID,
            "creator_id": creator_id,
            "direction": "creator_applied",
            "message": "Excited to try the product bundle and share an honest review.",
            "instagram_handle": "@arjun.codes",
            "example_content_url": "https://instagram.com/p/arjun-example2",
            "status": "accepted",
        }],
        on_conflict="id",
    )
    upsert(
        client,
        "collaborations",
        [{
            "id": TEST_COLLAB_ID,
            "application_id": TEST_APPLICATION_ACCEPTED_ID,
            "campaign_id": CAMPAIGN_COMPLETED_ID,
            "creator_id": creator_id,
            "business_id": business_id,
            "status": "completed",
            "completed_at": "2026-06-10T12:00:00Z",
        }],
        on_conflict="id",
    )
    upsert(
        client,
        "content_submissions",
        [{
            "id": TEST_CONTENT_SUBMISSION_ID,
            "collaboration_id": TEST_COLLAB_ID,
            "content_url": "https://instagram.com/p/arjun-collab-post",
            "platform": "instagram",
            "views": 24500,
            "likes": 1800,
            "comments": 130,
            "notes": "Seeded content submission for creator flow testing.",
            "synced_at": "2026-06-11T09:00:00Z",
        }],
        on_conflict="id",
    )

    # Save the still-active campaign for testing the saved-campaigns list.
    upsert(
        client,
        "saved_campaigns",
        [{"creator_id": creator_id, "campaign_id": CAMPAIGN_ACTIVE_ID}],
        on_conflict="creator_id,campaign_id",
    )

    # Conversation + messages tied to the completed collaboration.
    upsert(
        client, "conversations", [{"id": TEST_CONVERSATION_ID, "collaboration_id": TEST_COLLAB_ID}], on_conflict="id"
    )
    upsert(
        client,
        "conversation_participants",
        [
            {"conversation_id": TEST_CONVERSATION_ID, "profile_id": business_profile_id},
            {"conversation_id": TEST_CONVERSATION_ID, "profile_id": creator_profile_id},
        ],
        on_conflict="conversation_id,profile_id",
    )
    upsert(
        client,
        "messages",
        [
            {"id": TEST_MESSAGE_1_ID, "conversation_id": TEST_CONVERSATION_ID, "sender_id": business_profile_id,
             "content": "Hi Arjun! Excited to have you on board for the product bundle review."},
            {"id": TEST_MESSAGE_2_ID, "conversation_id": TEST_CONVERSATION_ID, "sender_id": creator_profile_id,
             "content": "Thanks! The bundle arrived, I'll have the review post up by the weekend."},
            {"id": TEST_MESSAGE_3_ID, "conversation_id": TEST_CONVERSATION_ID, "sender_id": business_profile_id,
             "content": "Sounds great, looking forward to it!"},
        ],
        on_conflict="id",
    )
    upsert(
        client,
        "conversation_reads",
        [
            {"conversation_id": TEST_CONVERSATION_ID, "profile_id": business_profile_id},
            {"conversation_id": TEST_CONVERSATION_ID, "profile_id": creator_profile_id},
        ],
        on_conflict="conversation_id,profile_id",
    )

    # Notifications on both sides.
    upsert(
        client,
        "notifications",
        [
            {"id": TEST_NOTIF_APPLICATION_ID, "profile_id": business_profile_id, "type": "application_received",
             "title": "New Application Received",
             "body": "Arjun Verma applied to your Admin Active Campaign.",
             "related_id": TEST_APPLICATION_PENDING_ID, "is_read": False},
            {"id": TEST_NOTIF_ACCEPTED_ID, "profile_id": creator_profile_id, "type": "application_accepted",
             "title": "Application Accepted!",
             "body": "Your application to Admin Completed Campaign has been accepted. Check your collaborations.",
             "related_id": TEST_COLLAB_ID, "is_read": True},
            {"id": TEST_NOTIF_MESSAGE_ID, "profile_id": creator_profile_id, "type": "new_message",
             "title": "New Message", "body": "Kolably HQ sent you a message.",
             "related_id": TEST_CONVERSATION_ID, "is_read": False},
        ],
        on_conflict="id",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-email", default=DEFAULT_ADMIN_EMAIL)
    parser.add_argument("--admin-password", default=DEFAULT_ADMIN_PASSWORD)
    parser.add_argument("--creator-email", default=DEFAULT_CREATOR_EMAIL)
    parser.add_argument("--creator-password", default=DEFAULT_CREATOR_PASSWORD)
    parser.add_argument("--skip-creator", action="store_true", help="Only seed the admin/business account.")
    args = parser.parse_args()

    client = httpx.Client()

    print(f"== auth user: {args.admin_email} ==")
    auth_id = create_auth_user(client, args.admin_email, args.admin_password, role="superadmin")
    print(f"  auth_id = {auth_id}")

    print("\n== profile: role -> superadmin ==")
    admin_profile = ensure_superadmin_profile(client, auth_id, args.admin_email)
    admin_profile_id = admin_profile["id"]
    print(f"  profile_id = {admin_profile_id}  role = {admin_profile['role']}")

    print("\n== business linked to superadmin profile ==")
    business_id = ensure_business(client, admin_profile_id)
    print(f"  business_id = {business_id}")

    print("\n== campaigns (draft / active / completed) ==")
    seed_campaigns(client, business_id)
    print("  done")

    print("\n== optional cross-account data with Priya (seed_sample_data.sql) ==")
    seed_priya_cross_account_data(client, business_id, admin_profile_id)

    if not args.skip_creator:
        print(f"\n== auth user: {args.creator_email} ==")
        creator_auth_id = create_auth_user(client, args.creator_email, args.creator_password, role="creator")
        print(f"  auth_id = {creator_auth_id}")

        print("\n== creator profile ==")
        creator_profile = ensure_creator_profile(client, args.creator_email)
        creator_profile_id = creator_profile["id"]
        print(f"  profile_id = {creator_profile_id}  role = {creator_profile['role']}")

        print("\n== creators row (bio, niche, Instagram fields) ==")
        creator_id = ensure_creator_row(client, creator_profile_id)
        print(f"  creator_id = {creator_id}")

        print("\n== portfolio items ==")
        seed_creator_portfolio(client, creator_id)
        print("  done")

        print("\n== creator journey (application -> collab -> messages -> notifications) ==")
        seed_creator_journey(client, creator_id, creator_profile_id, business_id, admin_profile_id)
        print("  done")

    print("\n== summary ==")
    print(
        f"  ADMIN login:    {args.admin_email} / {args.admin_password}  "
        f"(role: superadmin, business_id: {business_id})"
    )
    if not args.skip_creator:
        print(
            f"  CREATOR login:  {args.creator_email} / {args.creator_password}  "
            f"(role: creator, creator_id: {creator_id})"
        )
    print(f"\n  campaigns:      {CAMPAIGN_DRAFT_ID} (draft)")
    print(f"                  {CAMPAIGN_ACTIVE_ID} (active — has a pending creator application + a save)")
    print(f"                  {CAMPAIGN_COMPLETED_ID} (completed — has a finished collaboration + content submission)")
    print("\nCreator account can now test end-to-end:")
    print("  - profile + portfolio management (3 items already seeded)")
    print("  - browsing/discovering campaigns, saving one")
    print("  - a PENDING application awaiting the business's decision")
    print("  - a COMPLETED collaboration with content submission + message history")
    print("  - notifications (accepted app, new message)")
    print("  - Instagram-gated actions work immediately (dummy token pre-seeded)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
