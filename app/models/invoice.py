"""
Invoice domain model.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.enums import InvoiceStatus


@dataclass
class Invoice:
    """Invoice domain model — internal representation.

    A creator-issued, point-in-time financial record for a completed
    collaboration. `billed_by`/`billed_to` are snapshots taken at creation,
    not live-resolved from the creator/business rows — an invoice shouldn't
    retroactively change if a profile is edited later.
    """

    id: str
    collaboration_id: str
    creator_id: str
    business_id: str
    status: InvoiceStatus = InvoiceStatus.SENT
    line_items: list[dict[str, Any]] = field(default_factory=list)
    total_amount: float = 0.0
    billed_by: dict[str, Any] = field(default_factory=dict)
    billed_to: dict[str, Any] = field(default_factory=dict)
    paid_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Invoice":
        return cls(
            id=row["id"],
            collaboration_id=row["collaboration_id"],
            creator_id=row["creator_id"],
            business_id=row["business_id"],
            status=InvoiceStatus(row.get("status", "sent")),
            line_items=row.get("line_items") or [],
            total_amount=float(row.get("total_amount") or 0),
            billed_by=row.get("billed_by") or {},
            billed_to=row.get("billed_to") or {},
            paid_at=row.get("paid_at"),
            created_at=row["created_at"],
        )

    def to_row(self) -> dict[str, Any]:
        """Convert to dict for database insert/update."""
        return {
            "id": self.id,
            "collaboration_id": self.collaboration_id,
            "creator_id": self.creator_id,
            "business_id": self.business_id,
            "status": self.status.value,
            "line_items": self.line_items,
            "total_amount": self.total_amount,
            "billed_by": self.billed_by,
            "billed_to": self.billed_to,
            "paid_at": self.paid_at,
            "created_at": self.created_at,
        }
