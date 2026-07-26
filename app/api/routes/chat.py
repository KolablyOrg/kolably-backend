"""
Chat / messaging routes.
"""

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_user
from app.schemas.chat import ConversationResponse, UnreadCountResponse
from app.schemas.user import UserInToken
from app.services import chat_service

router = APIRouter()


@router.get("/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    user: UserInToken = Depends(get_current_user),
):
    """List all chat conversations for the current user."""
    return await chat_service.list_conversations(profile_id=user.id)


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    user: UserInToken = Depends(get_current_user),
):
    """Get unread count across all conversations."""
    return await chat_service.get_unread_count(profile_id=user.id)


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Get messages in a conversation."""
    return await chat_service.get_conversation(conversation_id, user.id)
