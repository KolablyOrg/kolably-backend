"""
Chat / messaging Pydantic schemas.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ParticipantSummary(BaseModel):
    id: str
    name: str
    avatar_url: str | None = None
    # Only set when the other participant is a business — lets the client
    # link straight to GET /businesses/{business_id} for a profile view.
    business_id: str | None = None
    # Only set when the other participant is a creator — lets the client
    # link straight to GET /creators/{creator_id} for a profile view.
    creator_id: str | None = None
    # Only meaningful for a business participant — drives the verified badge
    # in the chat thread header.
    is_verified: bool = False


class MessageCreateRequest(BaseModel):
    content: str = Field(..., min_length=1)


class ConversationCreateRequest(BaseModel):
    """Get-or-create: returns the existing conversation between the two
    participants for `collaboration_id` if one exists, else creates one."""
    participant_id: str
    collaboration_id: str | None = None


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    sender_id: str
    content: str
    created_at: datetime
    # Only meaningful for messages the requesting user sent — true once the
    # other participant's last_read_at has passed this message's timestamp.
    seen: bool = False
    # 'text' | 'event'. Clients render 'event' as a neutral, centred system
    # entry rather than a chat bubble attributed to a person — `sender_id`
    # on an event is the actor who triggered it, not someone who typed.
    kind: str = "text"
    # For kind='event': {"event_type": "...", ...event-specific fields}.
    metadata: dict[str, Any] | None = None


class CollaborationContext(BaseModel):
    """Summary of the collaboration a conversation is scoped to — powers the
    inbox's Active/Invite tag and the chat thread's context banner."""
    id: str
    status: str
    campaign_id: str
    campaign_title: str
    compensation_type: str | None = None
    cash_amount_min: float | None = None
    cash_amount_max: float | None = None
    deadline: datetime | None = None


class ConversationResponse(BaseModel):
    id: str
    participant_ids: list[str]
    other_participant: ParticipantSummary
    collaboration_id: str | None = None
    collaboration: CollaborationContext | None = None
    last_message: str | None = None
    last_message_at: datetime | None = None
    # Who sent `last_message` — lets the inbox list prefix it with "You: "
    # when it was the requesting user.
    last_message_sender_id: str | None = None
    unread_count: int = 0
    created_at: datetime
    # Only populated by GET /chat/conversations/{id} — the list endpoint
    # doesn't fetch messages, so this defaults to empty there.
    messages: list[MessageResponse] = []


class UnreadCountResponse(BaseModel):
    unread_count: int
