"""
Chat service — conversations and messaging.
"""

from fastapi import HTTPException, status

from app.core.supabase import get_supabase_admin_client


def _ensure_conversation_exists(admin_client, conversation_id: str) -> dict:
    """Fetch a conversation and verify it exists. Returns the row."""
    result = (
        admin_client.table("conversations")
        .select("*")
        .eq("id", conversation_id)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return result.data


def _row_to_conversation_response(row: dict) -> dict:
    """Convert a Supabase conversations row to a ConversationResponse dict."""
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


async def list_conversations(profile_id: str) -> list[dict]:
    """List all chat conversations for the current user."""
    admin_client = get_supabase_admin_client()

    result = (
        admin_client.table("conversations")
        .select("*")
        .contains("participant_ids", [profile_id])
        .order("last_message_at", desc=True)
        .execute()
    )

    items = []
    for row in result.data or []:
        items.append(_row_to_conversation_response(row))

    return items


async def get_conversation(conversation_id: str, profile_id: str) -> dict:
    """Get messages in a conversation."""
    admin_client = get_supabase_admin_client()
    row = _ensure_conversation_exists(admin_client, conversation_id)

    if profile_id not in row.get("participant_ids", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation",
        )

    msgs_result = (
        admin_client.table("messages")
        .select("*")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=False)
        .execute()
    )

    messages = []
    for msg in msgs_result.data or []:
        messages.append({
            "id": msg["id"],
            "conversation_id": msg["conversation_id"],
            "sender_id": msg["sender_id"],
            "content": msg["content"],
            "created_at": msg["created_at"],
        })

    admin_client.table("conversation_reads").upsert({
        "conversation_id": conversation_id,
        "profile_id": profile_id,
        "last_read_at": "now()",
    }).execute()

    resp = _row_to_conversation_response(row)
    resp["messages"] = messages
    return resp


async def get_unread_count(profile_id: str) -> dict:
    """Get total unread count across all conversations for the current user."""
    admin_client = get_supabase_admin_client()

    result = (
        admin_client.table("conversations")
        .select("unread_count")
        .contains("participant_ids", [profile_id])
        .execute()
    )

    total_unread = sum(row.get("unread_count", 0) for row in result.data or [])
    return {"unread_count": total_unread}
