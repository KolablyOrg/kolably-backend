"""
Business creates + publishes a campaign, a creator applies, the business
accepts — end to end against real Postgres.

This is the flow tests/ can't cover: campaign_service, application_service
and collaboration_service are unit-tested against fake repositories there,
so a real FK constraint, a wrong filter in a repository join, or a broken
RLS policy would never surface. Here it runs against the same schema
`migrations/` ships to production.

Instagram connection is a hard precondition for POST /applications/ (see
require_instagram_connected in app/core/dependencies.py) and can't be
satisfied through a real OAuth flow in a hermetic test, so it's set
directly via the repository — the same shortcut a seed script would take,
just inline.
"""

from datetime import UTC, datetime, timedelta

from app.repositories.creator_repo import CreatorRepository
from tests_integration.conftest import unique_email


async def test_business_creates_campaign_creator_applies_business_accepts(client):
    business_email = unique_email("business")
    business_signup = client.post(
        "/api/v1/auth/signup/business",
        json={
            "name": "Integration Business Owner",
            "email": business_email,
            "password": "correct horse battery staple",
        },
    )
    assert business_signup.status_code == 200, business_signup.text
    business_token = business_signup.json()["access_token"]
    business_headers = {"Authorization": f"Bearer {business_token}"}

    # Step 1 — draft
    create = client.post(
        "/api/v1/campaigns/",
        headers=business_headers,
        json={
            "title": "Integration Test Campaign",
            "objective": "brand_awareness",
            "description": "Created by the integration suite, not a real campaign.",
        },
    )
    assert create.status_code == 200, create.text
    campaign_id = create.json()["id"]
    assert create.json()["status"] == "draft"

    # Step 2 — deliverables & compensation
    deliverables = client.patch(
        f"/api/v1/campaigns/{campaign_id}/deliverables",
        headers=business_headers,
        json={
            "deliverables": [
                {"platform": "instagram", "content_type": "reel", "quantity": 1, "required": True},
            ],
            "compensation_type": "cash",
            "cash_amount_min": 1000,
            "cash_amount_max": 2000,
        },
    )
    assert deliverables.status_code == 200, deliverables.text

    # Step 3 — targeting
    targeting = client.patch(
        f"/api/v1/campaigns/{campaign_id}/targeting",
        headers=business_headers,
        json={
            "creator_category": "fitness",
            "location": "Mumbai",
            "max_creators": 1,
        },
    )
    assert targeting.status_code == 200, targeting.text

    # Step 4 — finalise (deadline) then publish
    deadline = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    finalise = client.patch(
        f"/api/v1/campaigns/{campaign_id}",
        headers=business_headers,
        json={"deadline": deadline},
    )
    assert finalise.status_code == 200, finalise.text

    publish = client.post(f"/api/v1/campaigns/{campaign_id}/publish", headers=business_headers)
    assert publish.status_code == 200, publish.text
    assert publish.json()["status"] == "active"

    # Creator signs up and applies
    creator_email = unique_email("creator")
    creator_signup = client.post(
        "/api/v1/auth/signup/creator",
        json={
            "name": "Integration Creator",
            "username": f"creator_{creator_email.split('-')[-1].split('@')[0]}",
            "email": creator_email,
            "password": "correct horse battery staple",
            "city": "Mumbai",
            "niche": "fitness",
        },
    )
    assert creator_signup.status_code == 200, creator_signup.text
    creator_profile_id = creator_signup.json()["user"]["id"]
    creator_token = creator_signup.json()["access_token"]
    creator_headers = {"Authorization": f"Bearer {creator_token}"}

    # Bypass the real Instagram OAuth flow — see module docstring.
    await CreatorRepository().update_by_profile_id(
        creator_profile_id, {"instagram_access_token": "integration-test-fake-token"}
    )

    apply = client.post(
        "/api/v1/applications/",
        headers=creator_headers,
        json={"campaign_id": campaign_id, "message": "Would love to collaborate."},
    )
    assert apply.status_code == 200, apply.text
    application_id = apply.json()["id"]
    assert apply.json()["status"] == "pending"

    # Business accepts — this is what actually creates the Collaboration row.
    accept = client.patch(f"/api/v1/applications/{application_id}/accept", headers=business_headers)
    assert accept.status_code == 200, accept.text
    assert accept.json()["status"] == "accepted"

    collaborations = client.get("/api/v1/collaborations/", headers=business_headers)
    assert collaborations.status_code == 200, collaborations.text
    collab_campaign_ids = [c["campaign_id"] for c in collaborations.json()["items"]]
    assert campaign_id in collab_campaign_ids
