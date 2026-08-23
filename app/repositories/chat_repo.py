from app.models.chat import Conversation, Message
from app.repositories.base import BaseRepository


class ChatRepository(BaseRepository):
    """Talks to `conversations`, `conversation_participants`, `messages`, and
    `conversation_reads` — four separate tables, no denormalized columns for
    participants/last-message/unread-count on `conversations` itself, so
    those are computed by the service layer from these primitives."""

    async def list_conversation_ids_for_profile(self, profile_id: str) -> list[str]:
        rows = await self.select(
            "conversation_participants",
            columns="conversation_id",
            filters={"profile_id": profile_id},
        )
        return [row["conversation_id"] for row in rows]

    async def get_conversations_by_ids(self, conversation_ids: list[str]) -> list[Conversation]:
        if not conversation_ids:
            return []
        rows = await self.select("conversations", columns="*", filters={"id": conversation_ids})
        return [Conversation.from_row(row) for row in rows]

    async def get_conversation(self, conversation_id: str) -> Conversation | None:
        row = await self.select_one(
            "conversations",
            columns="*",
            filters={"id": conversation_id},
        )
        return Conversation.from_row(row) if row else None

    async def get_participant_ids(self, conversation_id: str) -> list[str]:
        rows = await self.select(
            "conversation_participants",
            columns="profile_id",
            filters={"conversation_id": conversation_id},
        )
        return [row["profile_id"] for row in rows]

    async def add_participants(self, conversation_id: str, profile_ids: list[str]) -> None:
        existing = await self.select(
            "conversation_participants",
            columns="profile_id",
            filters={"conversation_id": conversation_id},
        )
        existing_ids = {row["profile_id"] for row in existing}
        to_add = [
            {"conversation_id": conversation_id, "profile_id": pid}
            for pid in profile_ids
            if pid not in existing_ids
        ]
        if to_add:
            await self.insert("conversation_participants", to_add)

    async def find_conversation_by_collaboration(self, collaboration_id: str) -> Conversation | None:
        row = await self.select_one(
            "conversations",
            columns="*",
            filters={"collaboration_id": collaboration_id},
        )
        return Conversation.from_row(row) if row else None

    async def find_shared_conversation_without_collaboration(
        self, profile_id: str, other_profile_id: str
    ) -> Conversation | None:
        """Only meaningful for `collaboration_id IS NULL` conversations — those
        aren't covered by the DB's unique index, so we look them up in code."""
        mine = await self.select(
            "conversation_participants", columns="conversation_id", filters={"profile_id": profile_id}
        )
        theirs = await self.select(
            "conversation_participants", columns="conversation_id", filters={"profile_id": other_profile_id}
        )
        shared_ids = list({r["conversation_id"] for r in mine} & {r["conversation_id"] for r in theirs})
        if not shared_ids:
            return None

        rows = await self.select("conversations", columns="*", filters={"id": shared_ids})
        for row in rows:
            if row.get("collaboration_id") is None:
                return Conversation.from_row(row)
        return None

    async def insert_conversation(self, collaboration_id: str | None) -> Conversation | None:
        rows = await self.insert("conversations", {"collaboration_id": collaboration_id})
        return Conversation.from_row(rows[0]) if rows else None

    async def get_message(self, conversation_id: str, message_id: str) -> Message | None:
        row = await self.select_one(
            "messages",
            columns="*",
            filters={"id": message_id, "conversation_id": conversation_id},
        )
        return Message.from_row(row) if row else None

    async def list_messages(
        self,
        conversation_id: str,
        *,
        after_id: str | None = None,
        limit: int = 100,
    ) -> list[Message]:
        limit = max(1, min(limit, 100))

        if after_id:
            after_msg = await self.get_message(conversation_id, after_id)
            if after_msg is None:
                after_id = None
            else:
                query = (
                    (await self._table("messages"))
                    .select("*")
                    .eq("conversation_id", conversation_id)
                    .gte("created_at", after_msg.created_at)
                    .order("created_at", desc=False)
                )
                result = await self._execute(query)
                rows = result.data or []
                messages = []
                for row in rows:
                    msg = Message.from_row(row)
                    if self._is_strictly_after(msg, after_msg):
                        messages.append(msg)
                return messages[:limit]

        query = (
            (await self._table("messages"))
            .select("*")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=True)
            .limit(limit)
        )
        result = await self._execute(query)
        rows = result.data or []
        return [Message.from_row(row) for row in reversed(rows)]

    @staticmethod
    def _is_strictly_after(msg: Message, cursor: Message) -> bool:
        if msg.created_at > cursor.created_at:
            return True
        if msg.created_at == cursor.created_at and str(msg.id) != str(cursor.id):
            return str(msg.id) > str(cursor.id)
        return False

    async def list_messages_legacy(self, conversation_id: str) -> list[Message]:
        """Unbounded fetch — kept for tests/fakes; prefer list_messages with limit."""
        return await self.list_messages(conversation_id, limit=100)

    async def get_last_message(self, conversation_id: str) -> Message | None:
        query = (
            (await self._table("messages"))
            .select("*")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=True)
            .limit(1)
        )
        result = await self._execute(query)
        rows = result.data or []
        return Message.from_row(rows[0]) if rows else None

    async def insert_message(self, data: dict) -> Message | None:
        rows = await self.insert("messages", data)
        return Message.from_row(rows[0]) if rows else None

    async def upsert_read(self, conversation_id: str, profile_id: str) -> None:
        await self.upsert("conversation_reads", {
            "conversation_id": conversation_id,
            "profile_id": profile_id,
            "last_read_at": "now()",
        })

    async def get_last_read_at(self, conversation_id: str, profile_id: str) -> str | None:
        row = await self.select_one(
            "conversation_reads",
            columns="last_read_at",
            filters={"conversation_id": conversation_id, "profile_id": profile_id},
        )
        return row["last_read_at"] if row else None

    async def count_unread(self, conversation_id: str, profile_id: str) -> int:
        """Messages in this conversation from someone else, sent after this
        profile's last read timestamp (or all of them, if never read)."""
        last_read_at = await self.get_last_read_at(conversation_id, profile_id)

        query = (
            (await self._table("messages"))
            .select("id", count="exact")
            .eq("conversation_id", conversation_id)
            .neq("sender_id", profile_id)
        )
        if last_read_at:
            query = query.gt("created_at", last_read_at)

        result = await self._execute(query)
        return result.count or 0

    async def get_total_unread(self, profile_id: str) -> int:
        conversation_ids = await self.list_conversation_ids_for_profile(profile_id)
        total = 0
        for conversation_id in conversation_ids:
            total += await self.count_unread(conversation_id, profile_id)
        return total
