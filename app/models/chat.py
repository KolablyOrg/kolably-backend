"""
Chat domain models.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Conversation:
    """Conversation domain model — internal representation.

    `conversations` itself only has `id`/`collaboration_id`/`created_at` —
    participants, last message, and unread count live in separate tables
    (`conversation_participants`, `messages`, `conversation_reads`) and are
    filled in by the service layer after construction, not read from a row.
    """
    id: str
    collaboration_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    participant_ids: list[str] = field(default_factory=list)
    last_message: str | None = None
    last_message_at: datetime | None = None
    unread_count: int = 0

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Conversation":
        return cls(
            id=row["id"],
            collaboration_id=row.get("collaboration_id"),
            created_at=row["created_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "collaboration_id": self.collaboration_id,
            "created_at": self.created_at,
        }


@dataclass
class Message:
    """Message domain model — internal representation."""
    id: str
    conversation_id: str
    sender_id: str
    content: str
    created_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Message":
        return cls(
            id=row["id"],
            conversation_id=row["conversation_id"],
            sender_id=row["sender_id"],
            content=row["content"],
            created_at=row["created_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "sender_id": self.sender_id,
            "content": self.content,
            "created_at": self.created_at,
        }
