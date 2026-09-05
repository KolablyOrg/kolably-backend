"""
Invoice-related Pydantic schemas.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class InvoiceLineItem(BaseModel):
    title: str
    amount: float = Field(ge=0)


class InvoiceCreateRequest(BaseModel):
    collaboration_id: str
    amount: float | None = None
    line_items: list[InvoiceLineItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def populate_line_items(self) -> "InvoiceCreateRequest":
        if not self.line_items:
            if self.amount is not None:
                self.line_items = [InvoiceLineItem(title="Collaboration Fee", amount=self.amount)]
            else:
                raise ValueError("Either line_items or amount must be provided")
        return self


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
    paid_by: str | None = None
