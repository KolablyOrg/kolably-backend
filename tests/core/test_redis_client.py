from app.core import redis_client


def test_redis_client_is_singleton(monkeypatch):
    created = []

    class FakeRedis:
        @classmethod
        def from_url(cls, url, decode_responses):
            created.append((url, decode_responses))
            return object()

    monkeypatch.setattr(redis_client, "Redis", FakeRedis)
    monkeypatch.setattr(redis_client.settings, "REDIS_URL", "rediss://redis.example/0")
    monkeypatch.setattr(redis_client, "_client", None)

    first = redis_client.get_redis_client()
    second = redis_client.get_redis_client()

    assert first is second
    assert created == [("rediss://redis.example/0", True)]


def test_redis_client_is_disabled_without_url(monkeypatch):
    monkeypatch.setattr(redis_client, "_client", None)
    monkeypatch.setattr(redis_client.settings, "REDIS_URL", "")
    assert redis_client.get_redis_client() is None
