"""
Email delivery domain model.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.enums import EmailDeliveryStatus, EmailFlow


@dataclass
class EmailDelivery:
    """Email delivery domain model — tracks outbound message lifecycle."""

    id: str
    idempotency_key: str
    flow_name: EmailFlow
    recipient_email: str
    subject: str
    status: EmailDeliveryStatus = EmailDeliveryStatus.PENDING
    recipient_profile_id: str | None = None
    resend_id: str | None = None
    attempts: int = 1
    error_message: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "EmailDelivery":
        return cls(
            id=str(row["id"]),
            idempotency_key=row["idempotency_key"],
            flow_name=EmailFlow(row["flow_name"]),
            recipient_email=row["recipient_email"],
            subject=row["subject"],
            status=EmailDeliveryStatus(row["status"]),
            recipient_profile_id=str(row["recipient_profile_id"]) if row.get("recipient_profile_id") else None,
            resend_id=row.get("resend_id"),
            attempts=row.get("attempts", 1),
            error_message=row.get("error_message"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "idempotency_key": self.idempotency_key,
            "flow_name": self.flow_name.value if hasattr(self.flow_name, "value") else self.flow_name,
            "recipient_email": self.recipient_email,
            "recipient_profile_id": self.recipient_profile_id,
            "resend_id": self.resend_id,
            "status": self.status.value if hasattr(self.status, "value") else self.status,
            "attempts": self.attempts,
            "subject": self.subject,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at,
        }
