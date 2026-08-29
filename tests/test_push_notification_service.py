"""
Unit tests for push_notification_service — repository injected as a fake,
Expo's HTTP API mocked at the `_post` boundary, no real network calls.
"""

from app.services import push_notification_service


class FakeToken:
    def __init__(self, expo_push_token, profile_id="p1", platform="ios"):
        self.expo_push_token = expo_push_token
        self.profile_id = profile_id
        self.platform = platform


class FakePushTokenRepo:
    def __init__(self, tokens=()):
        self._tokens = list(tokens)
        self.upserted = None
        self.deleted = []

    async def list_tokens_for_profile(self, profile_id: str):
        return [t for t in self._tokens if t.profile_id == profile_id]

    async def upsert_token(self, profile_id: str, token: str, platform: str):
        self.upserted = (profile_id, token, platform)
        return FakeToken(token, profile_id, platform)

    async def delete_by_token(self, token: str):
        self.deleted.append(token)


async def test_send_push_noop_when_no_tokens_registered(monkeypatch):
    called = False

    async def fake_post(messages):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(push_notification_service, "_post", fake_post)
    repo = FakePushTokenRepo(tokens=[])

    await push_notification_service.send_push_to_profile("p1", "Title", "Body", repo=repo)

    assert called is False


async def test_send_push_sends_one_message_per_registered_device(monkeypatch):
    sent = {}

    async def fake_post(messages):
        sent["messages"] = messages
        return [{"status": "ok"} for _ in messages]

    monkeypatch.setattr(push_notification_service, "_post", fake_post)
    repo = FakePushTokenRepo(tokens=[FakeToken("tok-a"), FakeToken("tok-b")])

    await push_notification_service.send_push_to_profile(
        "p1", "New message", "Hi there", data={"type": "new_message", "related_id": "conv1"}, repo=repo
    )

    assert len(sent["messages"]) == 2
    assert {m["to"] for m in sent["messages"]} == {"tok-a", "tok-b"}
    assert sent["messages"][0]["title"] == "New message"
    assert sent["messages"][0]["data"] == {"type": "new_message", "related_id": "conv1"}


async def test_send_push_deletes_token_on_device_not_registered(monkeypatch):
    async def fake_post(messages):
        return [{"status": "error", "details": {"error": "DeviceNotRegistered"}}]

    monkeypatch.setattr(push_notification_service, "_post", fake_post)
    repo = FakePushTokenRepo(tokens=[FakeToken("stale-tok")])

    await push_notification_service.send_push_to_profile("p1", "Title", "Body", repo=repo)

    assert repo.deleted == ["stale-tok"]


async def test_send_push_keeps_token_on_other_error_types(monkeypatch):
    """A rate limit or malformed-token error shouldn't delete a token that
    might still be valid on the next attempt — only DeviceNotRegistered means
    "this token will never work again"."""

    async def fake_post(messages):
        return [{"status": "error", "details": {"error": "MessageRateExceeded"}}]

    monkeypatch.setattr(push_notification_service, "_post", fake_post)
    repo = FakePushTokenRepo(tokens=[FakeToken("tok-a")])

    await push_notification_service.send_push_to_profile("p1", "Title", "Body", repo=repo)

    assert repo.deleted == []


async def test_send_push_never_raises_when_expo_api_is_unreachable(monkeypatch):
    async def fake_post(messages):
        raise ConnectionError("boom")

    monkeypatch.setattr(push_notification_service, "_post", fake_post)
    repo = FakePushTokenRepo(tokens=[FakeToken("tok-a")])

    # Must not raise — same fire-and-forget contract as notification_service.create_notification.
    await push_notification_service.send_push_to_profile("p1", "Title", "Body", repo=repo)


async def test_register_token_upserts_via_repo():
    repo = FakePushTokenRepo()

    await push_notification_service.register_token("p1", "tok-a", "android", repo=repo)

    assert repo.upserted == ("p1", "tok-a", "android")


async def test_unregister_token_never_raises_on_repo_failure():
    class FailingRepo(FakePushTokenRepo):
        async def delete_by_token(self, token: str):
            raise RuntimeError("db down")

    await push_notification_service.unregister_token("tok-a", repo=FailingRepo())
