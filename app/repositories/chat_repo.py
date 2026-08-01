from app.models.chat import Conversation, Message
from app.repositories.base import BaseRepository


class ChatRepository(BaseRepository):
    async def list_conversations(self, profile_id: str) -> list[Conversation]:
        query = (
            (await self._table("conversations"))
            .select("*")
            .contains("participant_ids", [profile_id])
            .order("last_message_at", desc=True)
        )
        result = await self._execute(query)
        rows = result.data or []
        return [Conversation.from_row(row) for row in rows]

    async def get_conversation(self, conversation_id: str) -> Conversation | None:
        row = await self.select_one(
            "conversations",
            columns="*",
            filters={"id": conversation_id},
        )
        return Conversation.from_row(row) if row else None

    async def list_messages(self, conversation_id: str) -> list[Message]:
        query = (
            (await self._table("messages"))
            .select("*")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=False)
        )
        result = await self._execute(query)
        rows = result.data or []
        return [Message.from_row(row) for row in rows]

    async def upsert_read(self, conversation_id: str, profile_id: str) -> None:
        await self.upsert("conversation_reads", {
            "conversation_id": conversation_id,
            "profile_id": profile_id,
            "last_read_at": "now()",
        })

    async def get_total_unread(self, profile_id: str) -> int:
        query = (
            (await self._table("conversations"))
            .select("unread_count")
            .contains("participant_ids", [profile_id])
        )
        result = await self._execute(query)
        return sum(row.get("unread_count", 0) for row in result.data or [])
