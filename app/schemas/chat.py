"""
Chat / messaging Pydantic schemas.
"""

from datetime import datetime

from pydantic import BaseModel


class ParticipantSummary(BaseModel):
    id: str
    name: str
    avatar_url: str | None = None


class MessageCreateRequest(BaseModel):
    content: str


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    sender_id: str
    content: str
    created_at: datetime


class ConversationResponse(BaseModel):
    id: str
    participant_ids: list[str]
    other_participant: ParticipantSummary
    collaboration_id: str | None = None
    last_message: str | None = None
    last_message_at: datetime | None = None
    unread_count: int = 0
    created_at: datetime


class UnreadCountResponse(BaseModel):
    unread_count: int
