"""
Collaboration domain models.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.enums import CollaborationStatus


@dataclass
class Collaboration:
    """Collaboration domain model — internal representation."""
    id: str
    campaign_id: str
    creator_id: str
    business_id: str
    application_id: str | None = None
    status: CollaborationStatus = CollaborationStatus.ACTIVE
    deliverables: list[dict[str, Any]] = field(default_factory=list)
    compensation_type: str | None = None
    cash_amount: float | None = None
    free_product_description: str | None = None
    deadline: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime | None = None
    # ── Brand-side collab management (added via migration 20260814) ──────
    revision_notes: list[dict[str, Any]] = field(default_factory=list)
    revision_overall_note: str | None = None
    revision_rounds: int = 0
    payment_confirmed_at: datetime | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Collaboration":
        import json
        deliverables = row.get("deliverables") or []
        if isinstance(deliverables, str):
            deliverables = json.loads(deliverables) if deliverables else []

        revision_notes = row.get("revision_notes") or []
        if isinstance(revision_notes, str):
            revision_notes = json.loads(revision_notes) if revision_notes else []

        return cls(
            id=row["id"],
            campaign_id=row["campaign_id"],
            creator_id=row["creator_id"],
            business_id=row["business_id"],
            application_id=row.get("application_id"),
            status=CollaborationStatus(row["status"]),
            deliverables=deliverables,
            compensation_type=row.get("compensation_type"),
            cash_amount=row.get("cash_amount"),
            free_product_description=row.get("free_product_description"),
            deadline=row.get("deadline"),
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
            created_at=row["created_at"],
            updated_at=row.get("updated_at"),
            revision_notes=revision_notes,
            revision_overall_note=row.get("revision_overall_note"),
            revision_rounds=int(row.get("revision_rounds") or 0),
            payment_confirmed_at=row.get("payment_confirmed_at"),
        )

    def to_row(self) -> dict[str, Any]:
        """Convert to dict for database insert/update."""
        return {
            "id": self.id,
            "campaign_id": self.campaign_id,
            "creator_id": self.creator_id,
            "business_id": self.business_id,
            "application_id": self.application_id,
            "status": self.status.value,
            "deliverables": self.deliverables,
            "compensation_type": self.compensation_type,
            "cash_amount": self.cash_amount,
            "free_product_description": self.free_product_description,
            "deadline": self.deadline,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "revision_notes": self.revision_notes,
            "revision_overall_note": self.revision_overall_note,
            "revision_rounds": self.revision_rounds,
            "payment_confirmed_at": self.payment_confirmed_at,
        }
