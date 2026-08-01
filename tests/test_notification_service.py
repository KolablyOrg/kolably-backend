"""
Unit tests for notification_service — repositories injected as fakes, no Supabase.
"""

import pytest
from fastapi import HTTPException

from app.core.enums import NotificationType
from app.models.notification import Notification
from app.services import notification_service

NOTIF_ROW = {
    "id": "n1",
    "profile_id": "p1",
    "type": "new_message",
    "title": "New message",
    "body": "Hi!",
    "related_id": "conv1",
    "is_read": False,
    "created_at": "2024-01-01T00:00:00+00:00",
}


class FakeNotificationRepo:
    def __init__(self, rows=(), total=0, unread=0):
        self._rows = list(rows)
        self._total = total
        self._unread = unread
        self.inserted = None
        self.marked_read = None
        self.marked_all_read_for = None

    async def list_by_profile(self, profile_id: str, page: int = 1, page_size: int = 20):
        return [Notification.from_row(r) for r in self._rows], self._total

    async def count_unread(self, profile_id: str):
        return self._unread

    async def insert_notification(self, data: dict):
        self.inserted = data
        return Notification.from_row({**data, "id": "n-new", "created_at": "2024-01-01T00:00:00+00:00"})

    async def mark_read(self, notification_id: str, profile_id: str):
        self.marked_read = (notification_id, profile_id)
        if notification_id == "missing":
            return None
        return Notification.from_row({**NOTIF_ROW, "id": notification_id, "is_read": True})

    async def mark_all_read(self, profile_id: str):
        self.marked_all_read_for = profile_id


async def test_list_notifications_maps_profile_id_and_is_read_correctly():
    """Regression: the model previously read user_id/read_at, which don't
    exist on the real table (profile_id/is_read) — this pins the fix."""
    repo = FakeNotificationRepo(rows=[dict(NOTIF_ROW)], total=1)

    result = await notification_service.list_notifications("p1", repo=repo)

    assert result["total"] == 1
    item = result["items"][0]
    assert item["profile_id"] == "p1"
    assert item["is_read"] is False
    assert item["related_id"] == "conv1"


async def test_get_unread_count():
    repo = FakeNotificationRepo(unread=3)
    result = await notification_service.get_unread_count("p1", repo=repo)
    assert result == {"unread_count": 3}


async def test_create_notification_writes_expected_row():
    repo = FakeNotificationRepo()

    await notification_service.create_notification(
        profile_id="p1",
        type=NotificationType.NEW_MESSAGE,
        title="New message",
        body="Hey!",
        related_id="conv1",
        repo=repo,
    )

    assert repo.inserted == {
        "profile_id": "p1",
        "type": "new_message",
        "title": "New message",
        "body": "Hey!",
        "related_id": "conv1",
    }


async def test_create_notification_swallows_repo_errors():
    class ExplodingRepo:
        async def insert_notification(self, data):
            raise RuntimeError("db is down")

    # Should not raise — the caller's own action must not fail just because
    # the notification side-effect did.
    await notification_service.create_notification(
        profile_id="p1",
        type=NotificationType.NEW_MESSAGE,
        title="x",
        body="y",
        repo=ExplodingRepo(),
    )


async def test_mark_notification_read():
    repo = FakeNotificationRepo()
    result = await notification_service.mark_notification_read("n1", "p1", repo=repo)
    assert result["is_read"] is True
    assert repo.marked_read == ("n1", "p1")


async def test_mark_notification_read_404_when_not_found_or_not_owned():
    repo = FakeNotificationRepo()
    with pytest.raises(HTTPException) as exc:
        await notification_service.mark_notification_read("missing", "p1", repo=repo)
    assert exc.value.status_code == 404


async def test_mark_all_notifications_read():
    repo = FakeNotificationRepo()
    result = await notification_service.mark_all_notifications_read("p1", repo=repo)
    assert result["message"]
    assert repo.marked_all_read_for == "p1"
