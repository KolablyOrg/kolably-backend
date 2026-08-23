"""
Seeds a running local backend (pointed at a local Supabase instance — see
tests_integration/README.md for how to start one) with the fixed accounts,
campaign, and application the kolably_ui Playwright regression suite needs.

Not a pytest file — run once before `npx playwright test`:

    .venv/bin/python scripts/seed_e2e_fixtures.py

Idempotent: signing up an already-existing email is treated as "already
seeded" and the script moves on rather than failing.
"""

import sys

import httpx

sys.path.insert(0, ".")
from app.repositories.creator_repo import CreatorRepository  # noqa: E402

BASE = "http://127.0.0.1:8000/api/v1"

CREATOR_EMAIL = "e2e-creator@kolably.com"
CREATOR_PASSWORD = "correct horse battery staple"
BUSINESS_EMAIL = "e2e-business@kolably.com"
BUSINESS_PASSWORD = "correct horse battery staple"

CAMPAIGN_TITLE = "E2E Regression Campaign"


def signup_or_login(client: httpx.Client, path: str, email: str, password: str, **extra) -> dict:
    resp = client.post(f"{BASE}/auth/signup/{path}", json={"email": email, "password": password, **extra})
    if resp.status_code == 200:
        print(f"  created {email}")
        return resp.json()
    # Local Supabase Auth (CLI/self-hosted GoTrue) rejects a re-signup with
    # a genuine 400 "User already registered" — unlike the hosted project,
    # which (per auth_service.signup_creator's own comment) returns 200
    # with no session instead, letting the app's own 409 duplicate-check
    # handle it. Treat both shapes as "already seeded" so this script is
    # idempotent in either environment.
    already_exists = resp.status_code == 409 or (
        resp.status_code == 400 and "already registered" in resp.text.lower()
    )
    if already_exists:
        print(f"  {email} already exists, logging in")
        resp = client.post(f"{BASE}/auth/login", json={"email": email, "password": password})
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()
    raise AssertionError("unreachable")  # raise_for_status always raises on a non-2xx status


def main() -> int:
    client = httpx.Client(timeout=30.0)

    health = httpx.get("http://127.0.0.1:8000/health", timeout=10.0)
    health.raise_for_status()

    print("Seeding creator...")
    creator_auth = signup_or_login(
        client,
        "creator",
        CREATOR_EMAIL,
        CREATOR_PASSWORD,
        name="E2E Creator",
        username="e2e_creator",
        city="Mumbai",
        niche="fitness",
    )
    creator_profile_id = creator_auth["user"]["id"]
    creator_headers = {"Authorization": f"Bearer {creator_auth['access_token']}"}

    print("Seeding business...")
    business_auth = signup_or_login(client, "business", BUSINESS_EMAIL, BUSINESS_PASSWORD, name="E2E Business Owner")
    business_headers = {"Authorization": f"Bearer {business_auth['access_token']}"}

    # Bypass real Instagram OAuth — same shortcut as tests_integration/,
    # see that folder's README for why this is the right call here.
    import asyncio

    async def _connect_instagram():
        # Both columns, not just instagram_access_token: the backend's own
        # require_instagram_connected gate checks instagram_access_token,
        # but the frontend's "Instagram connected" banner logic checks
        # instagram_connected, which Creator.from_row computes from
        # instagram_user_id instead (see app/models/creator.py) — a real
        # connect_instagram() call always sets both together, so only a
        # synthetic bypass like this one can end up with them out of sync.
        await CreatorRepository().update_by_profile_id(
            creator_profile_id,
            {
                "instagram_access_token": "e2e-seed-fake-token",
                "instagram_user_id": "e2e-seed-fake-ig-user-id",
                "instagram_handle": "e2e_seed_creator",
            },
        )

    asyncio.run(_connect_instagram())

    print("Checking for existing campaign...")
    existing = client.get(f"{BASE}/businesses/me/campaigns", headers=business_headers).json()
    campaign = next((c for c in existing.get("items", []) if c["title"] == CAMPAIGN_TITLE), None)

    if campaign:
        print(f"  campaign already exists: {campaign['id']}")
        campaign_id = campaign["id"]
    else:
        print("Creating campaign...")
        create = client.post(
            f"{BASE}/campaigns/",
            headers=business_headers,
            json={
                "title": CAMPAIGN_TITLE,
                "objective": "brand_awareness",
                "description": "Seeded for the Playwright regression suite — safe to apply/withdraw repeatedly.",
            },
        )
        create.raise_for_status()
        campaign_id = create.json()["id"]

        client.patch(
            f"{BASE}/campaigns/{campaign_id}/deliverables",
            headers=business_headers,
            json={
                "deliverables": [{"platform": "instagram", "content_type": "reel", "quantity": 1, "required": True}],
                "compensation_type": "cash",
                "cash_amount_min": 1000,
                "cash_amount_max": 2000,
            },
        ).raise_for_status()
        client.patch(
            f"{BASE}/campaigns/{campaign_id}/targeting",
            headers=business_headers,
            json={"creator_category": "fitness", "location": "Mumbai", "max_creators": 5},
        ).raise_for_status()
        client.patch(
            f"{BASE}/campaigns/{campaign_id}",
            headers=business_headers,
            json={"deadline": "2027-01-01T00:00:00Z"},
        ).raise_for_status()
        client.post(f"{BASE}/campaigns/{campaign_id}/publish", headers=business_headers).raise_for_status()
        print(f"  created and published: {campaign_id}")

    print("Applying creator to campaign (if not already applied)...")
    apply = client.post(
        f"{BASE}/applications/",
        headers=creator_headers,
        json={"campaign_id": campaign_id, "message": "Seeded application for the regression suite."},
    )
    if apply.status_code == 200:
        print("  applied")
    elif apply.status_code == 409:
        print("  already applied")
    else:
        apply.raise_for_status()

    print("\nSeed complete.")
    print(f"  Creator: {CREATOR_EMAIL} / {CREATOR_PASSWORD}")
    print(f"  Business: {BUSINESS_EMAIL} / {BUSINESS_PASSWORD}")
    print(f"  Campaign: {CAMPAIGN_TITLE} ({campaign_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
