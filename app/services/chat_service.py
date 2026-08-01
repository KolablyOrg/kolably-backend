from fastapi import HTTPException, status

from app.models.chat import Conversation, Message
from app.repositories.chat_repo import ChatRepository


def _conversation_to_response(conv: Conversation) -> dict:
    """Convert a Conversation model to a response dict."""
    return {
        "id": conv.id,
        "participant_ids": conv.participant_ids,
        "other_participant": {"id": "", "name": "", "avatar_url": None},
        "collaboration_id": conv.collaboration_id,
        "last_message": conv.last_message,
        "last_message_at": conv.last_message_at,
        "unread_count": conv.unread_count,
        "created_at": conv.created_at,
    }


def _message_to_response(msg: Message) -> dict:
    """Convert a Message model to a response dict."""
    return {
        "id": msg.id,
        "conversation_id": msg.conversation_id,
        "sender_id": msg.sender_id,
        "content": msg.content,
        "created_at": msg.created_at,
    }


async def list_conversations(
    profile_id: str,
    *,
    repo: ChatRepository | None = None,
) -> list[dict]:
    repo = repo or ChatRepository()
    conversations = await repo.list_conversations(profile_id)
    return [_conversation_to_response(c) for c in conversations]


async def get_conversation(
    conversation_id: str,
    profile_id: str,
    *,
    repo: ChatRepository | None = None,
) -> dict:
    repo = repo or ChatRepository()
    conversation = await repo.get_conversation(conversation_id)

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # Access check — participant_ids comes from the joined query
    if profile_id not in conversation.participant_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation",
        )

    messages = await repo.list_messages(conversation_id)

    await repo.upsert_read(conversation_id, profile_id)

    resp = _conversation_to_response(conversation)
    resp["messages"] = [_message_to_response(m) for m in messages]
    return resp


async def get_unread_count(
    profile_id: str,
    *,
    repo: ChatRepository | None = None,
) -> dict:
    repo = repo or ChatRepository()
    total = await repo.get_total_unread(profile_id)
    return {"unread_count": total}
