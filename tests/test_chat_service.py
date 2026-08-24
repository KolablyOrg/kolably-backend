"""
Unit tests for chat_service — repositories injected as fakes, no Supabase.

Chat spans four tables (conversations, conversation_participants, messages,
conversation_reads) with no denormalized columns on `conversations` itself,
so these tests exercise the service's in-memory joining of that data.
"""

import pytest
from fastapi import HTTPException

from app.core.chat_message_cache import chat_message_cache
from app.models.business import Business
from app.models.campaign import Campaign
from app.models.chat import Conversation, Message
from app.models.collaboration import Collaboration
from app.models.creator import Creator
from app.models.user import UserProfile
from app.services import chat_service

CREATOR_PROFILE_ROW = {
    "id": "p-creator",
    "auth_id": "auth-creator",
    "email": "creator@example.com",
    "role": "creator",
    "created_at": "2024-01-01T00:00:00+00:00",
}

BUSINESS_PROFILE_ROW = {
    "id": "p-business",
    "auth_id": "auth-business",
    "email": "business@example.com",
    "role": "business",
    "created_at": "2024-01-01T00:00:00+00:00",
}

CREATOR_ROW = {
    "id": "c1",
    "profile_id": "p-creator",
    "name": "Alice",
    "profile_photo_url": "https://example.com/alice.jpg",
    "created_at": "2024-01-01T00:00:00+00:00",
}

BUSINESS_ROW = {
    "id": "b1",
    "profile_id": "p-business",
    "business_name": "Acme Co",
    "logo_url": "https://example.com/acme.png",
    "city": "Springfield",
    "category": "food",
    "created_at": "2024-01-01T00:00:00+00:00",
}


class FakeProfileRepo:
    def __init__(self, rows=None):
        self._by_id = {r["id"]: r for r in (rows or [CREATOR_PROFILE_ROW, BUSINESS_PROFILE_ROW])}

    async def get_by_id(self, profile_id: str):
        row = self._by_id.get(profile_id)
        return UserProfile.from_row(row) if row else None


class FakeCreatorRepo:
    async def get_by_profile_id(self, profile_id: str):
        if profile_id == "p-creator":
            return Creator.from_row(CREATOR_ROW)
        return None


class FakeBusinessRepo:
    def __init__(self, row=None):
        self._row = row or BUSINESS_ROW

    async def get_by_profile_id(self, profile_id: str):
        if profile_id == "p-business":
            return Business.from_row(self._row)
        return None


class FakeChatRepo:
    def __init__(
        self,
        conversation_id="conv1",
        participants=("p-creator", "p-business"),
        messages=(),
        collaboration_id=None,
    ):
        self.conversations = {
            conversation_id: Conversation.from_row({
                "id": conversation_id,
                "collaboration_id": collaboration_id,
                "created_at": "2024-01-01T00:00:00+00:00",
            })
        }
        self.participants = {conversation_id: list(participants)}
        self.messages = {conversation_id: list(messages)}
        self.reads: dict[tuple[str, str], str] = {}
        self.added_participants = []
        self.inserted_messages = []
        self.inserted_conversations = []

    async def list_conversation_ids_for_profile(self, profile_id: str):
        return [cid for cid, members in self.participants.items() if profile_id in members]

    async def get_conversations_by_ids(self, ids):
        return [self.conversations[i] for i in ids if i in self.conversations]

    async def get_conversation(self, conversation_id: str):
        return self.conversations.get(conversation_id)

    async def get_participant_ids(self, conversation_id: str):
        return list(self.participants.get(conversation_id, []))

    async def add_participants(self, conversation_id: str, profile_ids):
        existing = set(self.participants.setdefault(conversation_id, []))
        for pid in profile_ids:
            if pid not in existing:
                self.participants[conversation_id].append(pid)
                existing.add(pid)
        self.added_participants.append((conversation_id, list(profile_ids)))

    async def find_conversation_by_collaboration(self, collaboration_id: str):
        for conv in self.conversations.values():
            if conv.collaboration_id == collaboration_id:
                return conv
        return None

    async def find_shared_conversation_without_collaboration(self, profile_id, other_profile_id):
        for cid, members in self.participants.items():
            conv = self.conversations[cid]
            if conv.collaboration_id is None and profile_id in members and other_profile_id in members:
                return conv
        return None

    async def insert_conversation(self, collaboration_id):
        new_id = f"conv-new-{len(self.conversations) + 1}"
        conv = Conversation.from_row({
            "id": new_id,
            "collaboration_id": collaboration_id,
            "created_at": "2024-01-01T00:00:00+00:00",
        })
        self.conversations[new_id] = conv
        self.participants[new_id] = []
        self.inserted_conversations.append(new_id)
        return conv

    async def get_message(self, conversation_id: str, message_id: str):
        for msg in self.messages.get(conversation_id, []):
            if msg.id == message_id:
                return msg
        return None

    async def list_messages(self, conversation_id: str, *, after_id: str | None = None, limit: int = 100):
        msgs = list(self.messages.get(conversation_id, []))
        if after_id:
            cursor = await self.get_message(conversation_id, after_id)
            if cursor is None:
                after_id = None
            else:
                from app.repositories.chat_repo import ChatRepository
                filtered = [m for m in msgs if ChatRepository._is_strictly_after(m, cursor)]
                return filtered[:limit]
        if not after_id:
            return msgs[-limit:] if len(msgs) > limit else msgs

    async def get_last_message(self, conversation_id: str):
        msgs = self.messages.get(conversation_id, [])
        return msgs[-1] if msgs else None

    async def insert_message(self, data: dict):
        msg = Message.from_row({
            **data,
            "id": f"msg{len(self.inserted_messages) + 1}",
            "created_at": "2024-01-02T00:00:00+00:00",
        })
        self.messages.setdefault(data["conversation_id"], []).append(msg)
        self.inserted_messages.append(msg)
        return msg

    async def upsert_read(self, conversation_id: str, profile_id: str):
        self.reads[(conversation_id, profile_id)] = "2024-01-02T00:00:00+00:00"

    async def get_last_read_at(self, conversation_id: str, profile_id: str):
        return self.reads.get((conversation_id, profile_id))

    async def count_unread(self, conversation_id: str, profile_id: str):
        last_read = self.reads.get((conversation_id, profile_id))
        count = 0
        for msg in self.messages.get(conversation_id, []):
            if msg.sender_id == profile_id:
                continue
            if last_read is None or msg.created_at > last_read:
                count += 1
        return count


class FakeCollaborationRepo:
    def __init__(self, rows=None):
        self._by_id = rows or {}

    async def get_by_id(self, collaboration_id: str):
        return self._by_id.get(collaboration_id)


class FakeCampaignRepo:
    def __init__(self, rows=None):
        self._by_id = rows or {}

    async def get_by_id(self, campaign_id: str):
        return self._by_id.get(campaign_id)


def _repos(collab_repo=None, campaign_repo=None):
    return dict(
        profile_repo=FakeProfileRepo(),
        creator_repo=FakeCreatorRepo(),
        business_repo=FakeBusinessRepo(),
        collab_repo=collab_repo or FakeCollaborationRepo(),
        campaign_repo=campaign_repo or FakeCampaignRepo(),
    )


@pytest.fixture(autouse=True)
async def _clear_chat_cache():
    await chat_message_cache.clear_all()
    yield
    await chat_message_cache.clear_all()


async def test_list_conversations_resolves_other_participant_and_last_message():
    repo = FakeChatRepo(messages=[Message.from_row({
        "id": "m1", "conversation_id": "conv1", "sender_id": "p-business",
        "content": "Hi there!", "created_at": "2024-01-01T12:00:00+00:00",
    })])

    result = await chat_service.list_conversations("p-creator", repo=repo, **_repos())

    assert len(result) == 1
    conv = result[0]
    assert conv["other_participant"]["name"] == "Acme Co"
    assert conv["other_participant"]["avatar_url"] == "https://example.com/acme.png"
    assert conv["other_participant"]["business_id"] == "b1"
    assert conv["last_message"] == "Hi there!"
    assert conv["last_message_sender_id"] == "p-business"
    assert conv["unread_count"] == 1  # from business, never read by creator


async def test_list_conversations_omits_empty_non_collaboration_conversation():
    """Regression (#24): get_or_create_conversation makes a real, visible
    row the instant someone taps "Message" — before they've sent anything.
    If they never follow through, the other person shouldn't see an empty,
    un-actionable thread show up in their inbox."""
    repo = FakeChatRepo(messages=(), collaboration_id=None)

    result = await chat_service.list_conversations("p-creator", repo=repo, **_repos())

    assert result == []


async def test_list_conversations_keeps_empty_collaboration_conversation():
    """A collaboration-linked conversation is the one legitimate exception
    — those are meant to exist as a standing thread from the moment the
    collaboration starts, message or not."""
    collab_repo = FakeCollaborationRepo({
        "collab1": Collaboration.from_row({
            "id": "collab1", "campaign_id": "camp1", "creator_id": "c1",
            "business_id": "b1", "status": "active",
            "created_at": "2024-01-01T00:00:00+00:00",
        }),
    })
    campaign_repo = FakeCampaignRepo({
        "camp1": Campaign.from_row({
            "id": "camp1", "business_id": "b1", "title": "Summer Drop",
            "objective": "brand_awareness", "description": "...",
            "compensation_type": "cash", "cash_amount_min": 5000, "cash_amount_max": 12000,
            "deadline": "2026-09-01T00:00:00+00:00", "status": "active",
            "created_at": "2024-01-01T00:00:00+00:00",
        }),
    })
    repo = FakeChatRepo(messages=(), collaboration_id="collab1")

    result = await chat_service.list_conversations(
        "p-creator", repo=repo, **_repos(collab_repo=collab_repo, campaign_repo=campaign_repo)
    )

    assert len(result) == 1
    assert result[0]["last_message"] is None


async def test_get_conversation_includes_collaboration_context_and_verified_badge():
    """The chat thread's banner needs the campaign title/compensation/
    deadline for whatever collaboration the conversation is scoped to, and
    the inbox's Active tag needs to know if the business side is verified."""
    verified_business_row = {**BUSINESS_ROW, "is_verified": True}
    repo = FakeChatRepo(collaboration_id="collab1")
    collab_repo = FakeCollaborationRepo({
        "collab1": Collaboration.from_row({
            "id": "collab1", "campaign_id": "camp1", "creator_id": "c1",
            "business_id": "b1", "status": "active",
            "created_at": "2024-01-01T00:00:00+00:00",
        }),
    })
    campaign_repo = FakeCampaignRepo({
        "camp1": Campaign.from_row({
            "id": "camp1", "business_id": "b1", "title": "Summer Drop",
            "objective": "brand_awareness", "description": "...",
            "compensation_type": "cash", "cash_amount_min": 5000, "cash_amount_max": 12000,
            "deadline": "2026-09-01T00:00:00+00:00", "status": "active",
            "created_at": "2024-01-01T00:00:00+00:00",
        }),
    })

    result = await chat_service.get_conversation(
        "conv1", "p-creator", repo=repo,
        profile_repo=FakeProfileRepo(), creator_repo=FakeCreatorRepo(),
        business_repo=FakeBusinessRepo(verified_business_row),
        collab_repo=collab_repo, campaign_repo=campaign_repo,
    )

    assert result["other_participant"]["is_verified"] is True
    assert result["collaboration"]["campaign_title"] == "Summer Drop"
    assert result["collaboration"]["compensation_type"] == "cash"
    assert result["collaboration"]["cash_amount_max"] == 12000
    assert result["collaboration"]["status"] == "active"


async def test_get_conversation_omits_collaboration_context_when_not_scoped_to_one():
    repo = FakeChatRepo(collaboration_id=None)

    result = await chat_service.get_conversation("conv1", "p-creator", repo=repo, **_repos())

    assert result["collaboration"] is None


async def test_list_conversations_omits_business_id_when_other_participant_is_a_creator():
    """The service returns a raw dict — no business_id key at all here for a
    creator participant. The Pydantic response schema fills in None for the
    HTTP response (see test_conversation_response_schema_round_trips_messages
    for that layer)."""
    repo = FakeChatRepo(
        participants=("p-business", "p-creator"),
        messages=[Message.from_row({
            "id": "m1", "conversation_id": "conv1", "sender_id": "p-creator",
            "content": "Hi!", "created_at": "2024-01-01T12:00:00+00:00",
        })],
    )

    result = await chat_service.list_conversations("p-business", repo=repo, **_repos())

    assert "business_id" not in result[0]["other_participant"]


async def test_get_conversation_marks_read_and_returns_messages():
    repo = FakeChatRepo(messages=[Message.from_row({
        "id": "m1", "conversation_id": "conv1", "sender_id": "p-business",
        "content": "Hello", "created_at": "2024-01-01T12:00:00+00:00",
    })])

    result = await chat_service.get_conversation("conv1", "p-creator", repo=repo, **_repos())

    assert len(result["messages"]) == 1
    assert ("conv1", "p-creator") in repo.reads


async def test_get_conversation_marks_own_messages_seen_once_other_participant_read_past_them():
    """WhatsApp/Instagram-style single-vs-double-tick: a message I sent shows
    seen once the other participant's last_read_at has passed its timestamp,
    and not before — even for a later message I sent that they haven't
    scrolled to yet."""
    repo = FakeChatRepo(messages=[
        Message.from_row({
            "id": "m1", "conversation_id": "conv1", "sender_id": "p-creator",
            "content": "Hey!", "created_at": "2024-01-01T12:00:00+00:00",
        }),
        Message.from_row({
            "id": "m2", "conversation_id": "conv1", "sender_id": "p-creator",
            "content": "You there?", "created_at": "2024-01-01T13:00:00+00:00",
        }),
    ])
    # Business read up through 12:30 — sees m1 but not m2 yet.
    repo.reads[("conv1", "p-business")] = "2024-01-01T12:30:00+00:00"

    result = await chat_service.get_conversation("conv1", "p-creator", repo=repo, **_repos())

    by_id = {m["id"]: m for m in result["messages"]}
    assert by_id["m1"]["seen"] is True
    assert by_id["m2"]["seen"] is False


async def test_get_conversation_never_marks_received_messages_seen():
    """`seen` is a property of what I sent — it shouldn't ever apply to a
    message I received, regardless of my own read state."""
    repo = FakeChatRepo(messages=[Message.from_row({
        "id": "m1", "conversation_id": "conv1", "sender_id": "p-business",
        "content": "Hello", "created_at": "2024-01-01T12:00:00+00:00",
    })])
    repo.reads[("conv1", "p-business")] = "2024-01-02T00:00:00+00:00"

    result = await chat_service.get_conversation("conv1", "p-creator", repo=repo, **_repos())

    assert result["messages"][0]["seen"] is False


def test_conversation_response_schema_round_trips_messages():
    """Regression: ConversationResponse had no `messages` field at all, so
    FastAPI's response_model silently dropped whatever
    chat_service.get_conversation() put there — every real HTTP response
    came back with no message history, no matter what the service fetched."""
    from app.schemas.chat import ConversationResponse

    payload = {
        "id": "conv1",
        "participant_ids": ["p1", "p2"],
        "other_participant": {"id": "p2", "name": "Acme", "avatar_url": None},
        "collaboration_id": None,
        "last_message": "hi",
        "last_message_at": "2024-01-01T00:00:00+00:00",
        "unread_count": 0,
        "created_at": "2024-01-01T00:00:00+00:00",
        "messages": [{
            "id": "m1", "conversation_id": "conv1", "sender_id": "p1",
            "content": "hi", "created_at": "2024-01-01T00:00:00+00:00", "seen": True,
        }],
    }

    dumped = ConversationResponse(**payload).model_dump()

    assert len(dumped["messages"]) == 1
    assert dumped["messages"][0]["content"] == "hi"
    assert dumped["other_participant"]["business_id"] is None
    assert dumped["messages"][0]["seen"] is True


async def test_get_conversation_returns_other_last_read_at():
    repo = FakeChatRepo(messages=[Message.from_row({
        "id": "m1", "conversation_id": "conv1", "sender_id": "p-creator",
        "content": "Hey!", "created_at": "2024-01-01T12:00:00+00:00",
    })])
    repo.reads[("conv1", "p-business")] = "2024-01-01T12:30:00+00:00"

    result = await chat_service.get_conversation("conv1", "p-creator", repo=repo, **_repos())

    assert result["other_last_read_at"] == "2024-01-01T12:30:00+00:00"


async def test_get_conversation_after_returns_only_newer_messages():
    repo = FakeChatRepo(messages=[
        Message.from_row({
            "id": "m1", "conversation_id": "conv1", "sender_id": "p-business",
            "content": "Hello", "created_at": "2024-01-01T12:00:00+00:00",
        }),
        Message.from_row({
            "id": "m2", "conversation_id": "conv1", "sender_id": "p-creator",
            "content": "Hi", "created_at": "2024-01-01T13:00:00+00:00",
        }),
    ])

    result = await chat_service.get_conversation(
        "conv1", "p-creator", after_id="m1", repo=repo, **_repos(),
    )

    assert [m["id"] for m in result["messages"]] == ["m2"]


async def test_get_conversation_unknown_after_falls_back_to_bounded_latest():
    repo = FakeChatRepo(messages=[
        Message.from_row({
            "id": f"m{i}", "conversation_id": "conv1", "sender_id": "p-business",
            "content": f"msg{i}", "created_at": f"2024-01-01T{10 + i:02d}:00:00+00:00",
        })
        for i in range(3)
    ])

    result = await chat_service.get_conversation(
        "conv1", "p-creator", after_id="missing", repo=repo, **_repos(),
    )

    assert len(result["messages"]) == 3


async def test_send_message_updates_last_message_cache(monkeypatch):
    from app.core.chat_message_cache import chat_message_cache

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(chat_service.notification_service, "create_notification", _noop)

    repo = FakeChatRepo()
    await chat_service.send_message("conv1", "p-creator", "Cached!", repo=repo)

    cached = await chat_message_cache.get_last_message("conv1")
    assert cached is not None
    assert cached.content == "Cached!"


async def test_get_conversation_rejects_non_participant():
    repo = FakeChatRepo()
    with pytest.raises(HTTPException) as exc:
        await chat_service.get_conversation("conv1", "p-stranger", repo=repo, **_repos())
    assert exc.value.status_code == 403


async def test_get_conversation_404_when_missing():
    repo = FakeChatRepo()
    with pytest.raises(HTTPException) as exc:
        await chat_service.get_conversation("missing", "p-creator", repo=repo, **_repos())
    assert exc.value.status_code == 404


async def test_send_message_inserts_and_marks_sender_read(monkeypatch):
    notified = []

    async def _fake_create_notification(profile_id, type, title, body, related_id=None, **kwargs):
        notified.append(profile_id)

    monkeypatch.setattr(chat_service.notification_service, "create_notification", _fake_create_notification)

    repo = FakeChatRepo()
    result = await chat_service.send_message("conv1", "p-creator", "Hey!", repo=repo)

    assert result["content"] == "Hey!"
    assert result["sender_id"] == "p-creator"
    assert ("conv1", "p-creator") in repo.reads
    assert notified == ["p-business"]


async def test_send_message_rejects_non_participant():
    repo = FakeChatRepo()
    with pytest.raises(HTTPException) as exc:
        await chat_service.send_message("conv1", "p-stranger", "Hey!", repo=repo)
    assert exc.value.status_code == 403


async def test_get_or_create_conversation_finds_existing_by_collaboration():
    repo = FakeChatRepo(collaboration_id="collab1")

    resp, created = await chat_service.get_or_create_conversation(
        "p-creator", "p-business", "collab1", repo=repo, **_repos()
    )

    assert created is False
    assert resp["id"] == "conv1"
    assert repo.inserted_conversations == []


async def test_get_or_create_conversation_creates_new_when_none_exists():
    repo = FakeChatRepo(participants=())  # no existing conversation has these participants
    repo.participants = {}
    repo.conversations = {}

    resp, created = await chat_service.get_or_create_conversation(
        "p-creator", "p-business", None, repo=repo, **_repos()
    )

    assert created is True
    assert len(repo.inserted_conversations) == 1
    assert set(repo.participants[resp["id"]]) == {"p-creator", "p-business"}


async def test_get_or_create_conversation_rejects_self():
    repo = FakeChatRepo()
    with pytest.raises(HTTPException) as exc:
        await chat_service.get_or_create_conversation("p-creator", "p-creator", None, repo=repo, **_repos())
    assert exc.value.status_code == 400


async def test_get_or_create_conversation_404s_on_unknown_participant():
    repo = FakeChatRepo()
    with pytest.raises(HTTPException) as exc:
        await chat_service.get_or_create_conversation("p-creator", "p-ghost", None, repo=repo, **_repos())
    assert exc.value.status_code == 404
