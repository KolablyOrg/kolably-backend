"""Presence API schemas."""

from datetime import datetime

from pydantic import BaseModel


class HeartbeatResponse(BaseModel):
    last_seen_at: datetime
