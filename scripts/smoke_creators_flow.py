"""Standalone end-to-end smoke test for the Creators API against a live server.

Prereqs:
  - uvicorn running on 127.0.0.1:8000 with a valid .env
  - Seed data present (scripts/seed_sample_data.sql): creator Priya Sharma
    (kolablyofficial@gmail.com) + business Kolably Cafe (kolably.cafe@gmail.com),
    password TestPass123! for both
  - Migration 019 applied (portfolio_items.title)

Run: .venv\\Scripts\\python.exe scripts/smoke_creators_flow.py
Not a pytest file — manual verification only.
"""

import sys
import uuid

import httpx

sys.path.insert(0, ".")
from app.core.config import settings  # noqa: E402

BASE = "http://127.0.0.1:8000/api/v1"
CREATOR_EMAIL = "kolablyofficial@gmail.com"
BUSINESS_EMAIL = "kolably.cafe@gmail.com"
PASSWORD = "TestPass123!"
PRIYA_ID = "c1111111-1111-1111-1111-111111111111"
CAFE_ACTIVE_ID = "cafe1111-1111-1111-1111-111111111111"

passed = failed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {detail}")


def login(client: httpx.Client, email: str) -> dict:
    r = client.post(f"{BASE}/auth/login", json={"email": email, "password": PASSWORD})
    body = r.json()
    token = body.get("access_token") or (body.get("session") or {}).get("access_token")
    return {"Authorization": f"Bearer {token}"} if r.status_code == 200 and token else {}


def main() -> int:
    global failed
    client = httpx.Client(timeout=30)

    print("\n== public: discovery ==")
    r = client.get(f"{BASE}/creators/")
    body = r.json()
    envelope_ok = {"items", "total", "page", "page_size"} <= set(body)
    check("GET /creators/ 200 + envelope", r.status_code == 200 and envelope_ok, str(r.status_code))
    check("  total >= 2", body.get("total", 0) >= 2, str(body.get("total")))

    r = client.get(f"{BASE}/creators/", params={"niche": "food"})
    items = r.json().get("items", [])
    check("filter niche=food", r.status_code == 200 and items and all(i.get("niche") == "food" for i in items))

    r = client.get(f"{BASE}/creators/", params={"city": "Delhi"})
    check("filter city=Delhi includes Priya", any(i["id"] == PRIYA_ID for i in r.json().get("items", [])))

    r = client.get(f"{BASE}/creators/", params={"search": "Priya"})
    check("search=Priya", any(i["id"] == PRIYA_ID for i in r.json().get("items", [])))

    r = client.get(f"{BASE}/creators/", params={"follower_min": 10000, "follower_max": 100000})
    items = r.json().get("items", [])
    in_range = all(10000 <= (i.get("follower_count") or 0) <= 100000 for i in items)
    check("follower range filter", any(i["id"] == PRIYA_ID for i in items) and in_range)

    print("\n== public: profile + portfolio ==")
    r = client.get(f"{BASE}/creators/{PRIYA_ID}")
    body = r.json()
    check("GET /creators/{id} 200", r.status_code == 200, str(r.status_code))
    check("  instagram_handle mapped", bool(body.get("instagram_handle")), repr(body.get("instagram_handle")))
    check("  no token leak", "instagram_access_token" not in body and "instagram_user_id" not in body)

    r = client.get(f"{BASE}/creators/{uuid.uuid4()}")
    check("GET unknown creator 404", r.status_code == 404, str(r.status_code))

    r = client.get(f"{BASE}/creators/{PRIYA_ID}/portfolio")
    items = r.json().get("items", [])
    check("GET portfolio 200, >=2 items", r.status_code == 200 and len(items) >= 2, f"count={len(items)}")
    check("  items expose title key", all("title" in i for i in items))

    print("\n== auth ==")
    creator_h = login(client, CREATOR_EMAIL)
    check("creator login", bool(creator_h))
    business_h = login(client, BUSINESS_EMAIL)
    check("business login", bool(business_h))
    if not creator_h or not business_h:
        print("cannot continue without tokens")
        return 1

    r = client.get(f"{BASE}/creators/{PRIYA_ID}", headers=creator_h)
    check("JWT accepted on authed request", r.status_code == 200, str(r.status_code))

    print("\n== stats ==")
    r = client.get(f"{BASE}/creators/me/stats", headers=creator_h)
    check("GET /me/stats 200", r.status_code == 200, str(r.status_code))

    print("\n== update profile ==")
    original_bio = client.get(f"{BASE}/creators/{PRIYA_ID}").json().get("bio")
    r = client.patch(f"{BASE}/creators/{PRIYA_ID}", headers=creator_h, json={"bio": "smoke bio"})
    applied = r.status_code == 200 and r.json().get("bio") == "smoke bio"
    check("PATCH own profile 200 + applied", applied, str(r.status_code))
    client.patch(f"{BASE}/creators/{PRIYA_ID}", headers=creator_h, json={"bio": original_bio})

    r = client.patch(f"{BASE}/creators/{PRIYA_ID}", headers=business_h, json={"bio": "nope"})
    check("PATCH as business 403", r.status_code == 403, str(r.status_code))

    other_id = next(i["id"] for i in client.get(f"{BASE}/creators/").json()["items"] if i["id"] != PRIYA_ID)
    r = client.patch(f"{BASE}/creators/{other_id}", headers=creator_h, json={"bio": "nope"})
    check("PATCH someone else's profile 403", r.status_code == 403, str(r.status_code))

    r = client.patch(f"{BASE}/creators/{uuid.uuid4()}", headers=creator_h, json={"bio": "nope"})
    check("PATCH unknown creator 404", r.status_code == 404, str(r.status_code))

    print("\n== portfolio write ==")
    r = client.post(f"{BASE}/creators/{PRIYA_ID}/portfolio", headers=creator_h,
                    json={"title": "smoke item", "media_url": "https://example.com/smoke.mp4", "media_type": "video"})
    body = r.json() if r.status_code == 201 else {}
    new_item = body.get("id")
    check("POST portfolio 201 (migration 019 live)", r.status_code == 201, str(r.status_code) + " " + r.text[:200])
    check("  title echoed", body.get("title") == "smoke item", repr(body.get("title")))

    r = client.get(f"{BASE}/creators/{PRIYA_ID}/portfolio")
    check("  new item listed", any(i["id"] == new_item for i in r.json().get("items", [])))

    r = client.post(f"{BASE}/creators/{PRIYA_ID}/portfolio", headers=business_h,
                    json={"media_url": "https://example.com/x.mp4"})
    check("POST portfolio as business 403", r.status_code == 403, str(r.status_code))

    r = client.post(f"{BASE}/creators/{PRIYA_ID}/portfolio", headers=creator_h, json={"media_type": "video"})
    check("POST portfolio missing media_url 422", r.status_code == 422, str(r.status_code))

    foreign = client.get(f"{BASE}/creators/{other_id}/portfolio").json().get("items", [])
    if foreign:
        r = client.delete(f"{BASE}/creators/{PRIYA_ID}/portfolio/{foreign[0]['id']}", headers=creator_h)
        check("DELETE someone else's item 404", r.status_code == 404, str(r.status_code))

    r = client.delete(f"{BASE}/creators/{PRIYA_ID}/portfolio/{new_item}", headers=creator_h)
    check("DELETE own item 204", r.status_code == 204, str(r.status_code))
    r = client.get(f"{BASE}/creators/{PRIYA_ID}/portfolio")
    check("  item gone", not any(i["id"] == new_item for i in r.json().get("items", [])))

    print("\n== saved campaigns ==")
    r = client.get(f"{BASE}/creators/me/saved-campaigns", headers=creator_h)
    items = r.json().get("items", [])
    check("GET saved-campaigns 200, seeded item", r.status_code == 200 and len(items) >= 1, str(r.status_code))
    full_shape = bool(items) and {"title", "description", "deliverables", "status"} <= set(items[0])
    check("  full campaign shape", full_shape, str(set(items[0]) if items else None))

    r = client.post(f"{BASE}/creators/me/saved-campaigns/{CAFE_ACTIVE_ID}", headers=creator_h)
    check("POST save w/o instagram 403", r.status_code == 403, str(r.status_code))

    # test setup: give Priya a dummy IG token so the gate passes, then clean up
    sb = {"apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
          "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
          "Content-Type": "application/json", "Prefer": "return=minimal"}
    r = httpx.patch(f"{settings.SUPABASE_URL}/rest/v1/creators?id=eq.{PRIYA_ID}",
                    headers=sb, json={"instagram_access_token": "smoke-token"}, timeout=15)
    check("  setup: dummy IG token set", r.status_code in (200, 204), str(r.status_code))

    r = client.post(f"{BASE}/creators/me/saved-campaigns/{CAFE_ACTIVE_ID}", headers=creator_h)
    check("POST save 204", r.status_code == 204, str(r.status_code))
    r = client.post(f"{BASE}/creators/me/saved-campaigns/{CAFE_ACTIVE_ID}", headers=creator_h)
    check("POST save idempotent 204", r.status_code == 204, str(r.status_code))
    r = client.get(f"{BASE}/creators/me/saved-campaigns", headers=creator_h)
    check("  saved campaign listed", any(i["id"] == CAFE_ACTIVE_ID for i in r.json().get("items", [])))

    r = client.delete(f"{BASE}/creators/me/saved-campaigns/{CAFE_ACTIVE_ID}", headers=creator_h)
    check("DELETE unsave 204", r.status_code == 204, str(r.status_code))
    r = client.delete(f"{BASE}/creators/me/saved-campaigns/{CAFE_ACTIVE_ID}", headers=creator_h)
    check("DELETE unsave idempotent 204", r.status_code == 204, str(r.status_code))

    r = client.post(f"{BASE}/creators/me/saved-campaigns/{uuid.uuid4()}", headers=creator_h)
    check("POST save unknown campaign 404", r.status_code == 404, str(r.status_code))
    r = client.post(f"{BASE}/creators/me/saved-campaigns/{CAFE_ACTIVE_ID}", headers=business_h)
    check("POST save as business 403", r.status_code == 403, str(r.status_code))

    httpx.patch(f"{settings.SUPABASE_URL}/rest/v1/creators?id=eq.{PRIYA_ID}",
                headers=sb, json={"instagram_access_token": None}, timeout=15)

    print("\n== instagram auth-url ==")
    r = client.get(f"{BASE}/creators/me/instagram/auth-url", headers=creator_h,
                   params={"redirect_uri": "http://localhost/callback"})
    check("GET instagram auth-url 200", r.status_code == 200, str(r.status_code))
    url = (r.json().get("url") or r.json().get("auth_url") or "")
    check("  url looks like an oauth url", "oauth" in url or "authorize" in url, url[:120])
    if "client_id=&" in url or "client_id=" not in url:
        print("  NOTE: INSTAGRAM_APP_ID missing from .env — client_id is empty")

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
