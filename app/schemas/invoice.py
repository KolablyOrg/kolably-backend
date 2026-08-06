"""
Invoice-related Pydantic schemas.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class InvoiceLineItem(BaseModel):
    title: str
    amount: float = Field(ge=0)


class InvoiceCreateRequest(BaseModel):
    collaboration_id: str
    line_items: list[InvoiceLineItem] = Field(..., min_length=1)


class InvoicePartySnapshot(BaseModel):
    name: str
    pan: str | None = None
    gst: str | None = None
    bank_display: str | None = None


class InvoiceResponse(BaseModel):
    id: str
    invoice_number: str
    collaboration_id: str
    creator_id: str
    business_id: str
    status: Literal["sent", "paid"]
    line_items: list[InvoiceLineItem]
    total_amount: float
    billed_by: InvoicePartySnapshot
    billed_to: InvoicePartySnapshot
    created_at: datetime
    paid_at: datetime | None = None
