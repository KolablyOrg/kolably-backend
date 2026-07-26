from fastapi import HTTPException, status

from app.repositories.chat_repo import ChatRepository


def _row_to_conversation_response(row: dict) -> dict:
    return {
        "id": row["id"],
        "participant_ids": row.get("participant_ids", []),
        "other_participant": {"id": "", "name": "", "avatar_url": None},
        "collaboration_id": row.get("collaboration_id"),
        "last_message": row.get("last_message"),
        "last_message_at": row.get("last_message_at"),
        "unread_count": row.get("unread_count", 0),
        "created_at": row["created_at"],
    }


async def list_conversations(
    profile_id: str,
    *,
    repo: ChatRepository | None = None,
) -> list[dict]:
    repo = repo or ChatRepository()
    rows = await repo.list_conversations(profile_id)
    return [_row_to_conversation_response(row) for row in rows]


async def get_conversation(
    conversation_id: str,
    profile_id: str,
    *,
    repo: ChatRepository | None = None,
) -> dict:
    repo = repo or ChatRepository()
    row = await repo.get_conversation(conversation_id)

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    if profile_id not in row.get("participant_ids", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation",
        )

    messages_raw = await repo.list_messages(conversation_id)
    messages = [
        {
            "id": msg["id"],
            "conversation_id": msg["conversation_id"],
            "sender_id": msg["sender_id"],
            "content": msg["content"],
            "created_at": msg["created_at"],
        }
        for msg in messages_raw
    ]

    await repo.upsert_read(conversation_id, profile_id)

    resp = _row_to_conversation_response(row)
    resp["messages"] = messages
    return resp


async def get_unread_count(
    profile_id: str,
    *,
    repo: ChatRepository | None = None,
) -> dict:
    repo = repo or ChatRepository()
    total = await repo.get_total_unread(profile_id)
    return {"unread_count": total}
