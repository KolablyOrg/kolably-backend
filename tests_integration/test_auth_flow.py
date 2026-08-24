"""
Signup and login against a real local Supabase Auth instance + Postgres.

This is exactly the layer tests/test_auth_service.py can't cover — there,
Supabase and the repositories are faked, so a broken auth trigger, a wrong
column name, or a real Supabase Auth API change would never fail a test.
"""

from app.repositories.profile_repo import ProfileRepository
from tests_integration.conftest import unique_email


async def test_creator_signup_creates_profile_and_returns_session(client):
    email = unique_email("creator")
    response = client.post(
        "/api/v1/auth/signup/creator",
        json={
            "name": "Integration Creator",
            "username": f"creator_{uid(email)}",
            "email": email,
            "password": "correct horse battery staple",
            "city": "Mumbai",
            "niche": "fitness",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["access_token"]
    assert body["user"]["email"] == email
    assert body["user"]["role"] == "creator"

    # Confirms the DB trigger that creates public.profiles on auth.users
    # insert actually ran — a mocked-repo unit test can't exercise this.
    profile = await ProfileRepository().get_by_id(body["user"]["id"])
    assert profile is not None
    assert profile.email == email
    assert profile.role.value == "creator"


async def test_business_signup_then_login_round_trip(client):
    email = unique_email("business")
    password = "correct horse battery staple"

    signup = client.post(
        "/api/v1/auth/signup/business",
        json={"name": "Integration Business Owner", "email": email, "password": password},
    )
    assert signup.status_code == 200, signup.text
    assert signup.json()["user"]["role"] == "business"

    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    body = login.json()
    assert body["access_token"]
    assert body["user"]["role"] == "business"


async def test_login_with_wrong_password_is_rejected(client):
    email = unique_email("creator")
    client.post(
        "/api/v1/auth/signup/creator",
        json={
            "name": "Integration Creator",
            "username": f"creator_{uid(email)}",
            "email": email,
            "password": "correct horse battery staple",
            "city": "Mumbai",
            "niche": "fitness",
        },
    )

    response = client.post("/api/v1/auth/login", json={"email": email, "password": "wrong password entirely"})
    assert response.status_code in (400, 401)


def uid(email: str) -> str:
    return email.split("@")[0].split("-")[-1]
