"""
Pydantic schemas for email requests and delivery responses.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core.enums import EmailDeliveryStatus, EmailFlow


class SendEmailPayload(BaseModel):
    flow: EmailFlow
    to: EmailStr
    subject: str
    idempotency_key: str = Field(..., max_length=256)
    template_data: dict[str, Any] = Field(default_factory=dict)
    recipient_profile_id: str | None = None


class EmailDeliveryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    idempotency_key: str
    flow_name: EmailFlow
    recipient_email: str
    subject: str
    status: EmailDeliveryStatus
    resend_id: str | None = None
    attempts: int = 1
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
