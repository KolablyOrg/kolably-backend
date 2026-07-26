"""
End-to-end smoke test for the Campaigns API 4-step create/publish flow.

Prerequisites:
  - Backend running on http://127.0.0.1:8000
  - A confirmed business account (see EMAIL/PASSWORD below)

Usage:
  .venv/Scripts/python.exe scripts/test_campaign_flow.py
"""

import sys

import httpx

BASE = "http://127.0.0.1:8000/api/v1"
EMAIL = "kolably.cafe@gmail.com"
PASSWORD = "TestPass123!"
TIMEOUT = 60.0


def step(name: str, ok: bool, detail: str = "") -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    return ok


def main() -> int:
    results: list[bool] = []
    client = httpx.Client(base_url=BASE, timeout=TIMEOUT)

    # Health
    try:
        r = httpx.get("http://127.0.0.1:8000/health", timeout=TIMEOUT)
        results.append(step("health", r.status_code == 200, r.json().get("status", "")))
    except Exception as e:
        results.append(step("health", False, str(e)))
        print("Server unreachable — aborting.")
        return 1

    # Login
    r = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    ok = r.status_code == 200 and r.json().get("access_token")
    results.append(step("login", bool(ok), f"status={r.status_code}"))
    if not ok:
        print(r.text)
        return 1
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Step 1: create draft
    r = client.post(
        "/campaigns/",
        headers=headers,
        json={
            "title": "Cafe Launch Collab",
            "objective": "foot_traffic",
            "description": "Promote our new cafe in Delhi",
        },
    )
    ok = r.status_code in (200, 201)
    results.append(step("step1 create draft", ok, f"status={r.status_code}"))
    if not ok:
        print(r.text)
        return 1
    campaign = r.json()
    cid = campaign["id"]
    results.append(step("step1 is draft", campaign.get("status") == "draft"))

    # Step 2: deliverables & offer
    r = client.patch(
        f"/campaigns/{cid}/deliverables",
        headers=headers,
        json={
            "deliverables": [
                {"platform": "instagram", "content_type": "reel", "quantity": 1},
                {"platform": "instagram", "content_type": "story", "quantity": 3},
            ],
            "compensation_type": "cash_and_product",
            "cash_amount_min": 2000,
            "cash_amount_max": 5000,
            "free_product_description": "Free meal for two",
        },
    )
    ok = r.status_code == 200 and len(r.json().get("deliverables", [])) == 2
    results.append(step("step2 deliverables", ok, f"status={r.status_code}"))
    if not ok:
        print(r.text)

    # Step 3: targeting
    r = client.patch(
        f"/campaigns/{cid}/targeting",
        headers=headers,
        json={
            "creator_category": "food",
            "follower_range_min": 5000,
            "follower_range_max": 100000,
            "min_engagement_rate": 2.5,
            "location": "Delhi",
            "max_creators": 5,
            "additional_requirements": "Must visit in person",
        },
    )
    ok = r.status_code == 200 and r.json().get("location") == "Delhi"
    results.append(step("step3 targeting", ok, f"status={r.status_code}"))
    if not ok:
        print(r.text)

    # Publish too early (no deadline) should fail with 422 missing_fields
    r = client.post(f"/campaigns/{cid}/publish", headers=headers)
    ok = r.status_code == 422 and "deadline" in r.text
    results.append(step("publish guard (missing deadline -> 422)", ok, f"status={r.status_code}"))

    # Step 4: set deadline, then publish
    r = client.patch(
        f"/campaigns/{cid}",
        headers=headers,
        json={"deadline": "2026-09-01T00:00:00Z"},
    )
    results.append(step("step4 set deadline", r.status_code == 200, f"status={r.status_code}"))
    if r.status_code != 200:
        print(r.text)

    r = client.post(f"/campaigns/{cid}/publish", headers=headers)
    ok = r.status_code == 200 and r.json().get("status") == "active"
    results.append(step("step4 publish -> active", ok, f"status={r.status_code}"))
    if not ok:
        print(r.text)

    # Feed
    r = client.get("/campaigns/", params={"page": 1, "page_size": 10})
    ok = r.status_code == 200 and any(i["id"] == cid for i in r.json().get("items", []))
    results.append(step("feed lists published campaign", ok, f"status={r.status_code}"))
    if r.status_code == 200:
        print(f"      feed total={r.json().get('total')}")

    # Detail
    r = client.get(f"/campaigns/{cid}")
    ok = r.status_code == 200 and r.json().get("id") == cid
    results.append(step("get campaign detail", ok, f"status={r.status_code}"))

    # Categories
    r = client.get("/campaigns/categories")
    ok = r.status_code == 200 and len(r.json()) == 12
    results.append(step("categories (12)", ok, f"status={r.status_code}"))

    print()
    passed = sum(results)
    print(f"{passed}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
