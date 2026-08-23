"""
Boots the app against a real local Supabase instance and confirms the
health endpoint responds — proves Settings() picked up working DB/auth
config, not just that the route exists (tests/test_health.py already
covers that against a fully mocked app).
"""


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
