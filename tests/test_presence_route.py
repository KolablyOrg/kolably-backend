from datetime import UTC, datetime

import pytest

from app.api.routes import presence
from app.core.enums import UserRole
from app.schemas.user import UserInToken


@pytest.mark.asyncio
async def test_heartbeat_route_calls_authenticated_service(monkeypatch):
    user = UserInToken(id="p1", auth_id="a1", email="p1@example.com", role=UserRole.CREATOR, is_active=True)
    called = []

    async def fake_update(profile_id):
        called.append(profile_id)
        return {"last_seen_at": datetime.now(UTC)}

    monkeypatch.setattr(presence.presence_service, "update_last_seen", fake_update)
    result = await presence.heartbeat(user)
    assert called == ["p1"]
    assert result["last_seen_at"].tzinfo == UTC
