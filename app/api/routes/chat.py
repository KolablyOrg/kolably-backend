"""
Chat / messaging routes.
"""

from fastapi import APIRouter, Depends, Response, status

from app.core.dependencies import get_current_user, require_instagram_connected
from app.schemas.chat import (
    ConversationCreateRequest,
    ConversationResponse,
    MessageCreateRequest,
    MessageResponse,
    UnreadCountResponse,
)
from app.schemas.user import UserInToken
from app.services import chat_service

router = APIRouter()


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    user: UserInToken = Depends(get_current_user),
):
    """List all chat conversations for the current user."""
    return await chat_service.list_conversations(profile_id=user.id)


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    data: ConversationCreateRequest,
    response: Response,
    user: UserInToken = Depends(get_current_user),
):
    """Get-or-create a conversation with another participant."""
    conversation, created = await chat_service.get_or_create_conversation(
        profile_id=user.id,
        other_profile_id=data.participant_id,
        collaboration_id=data.collaboration_id,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return conversation


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    user: UserInToken = Depends(get_current_user),
):
    """Get unread count across all conversations."""
    return await chat_service.get_unread_count(profile_id=user.id)


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    after: str | None = None,
    limit: int = 100,
    user: UserInToken = Depends(get_current_user),
):
    """Get messages in a conversation. Use ?after=<message_id> for delta sync."""
    return await chat_service.get_conversation(
        conversation_id,
        user.id,
        after_id=after,
        limit=min(max(limit, 1), 100),
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageResponse,
    dependencies=[Depends(require_instagram_connected)],
)
async def send_message(
    conversation_id: str,
    data: MessageCreateRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Send a message in a conversation."""
    return await chat_service.send_message(
        conversation_id=conversation_id,
        sender_id=user.id,
        content=data.content,
    )
