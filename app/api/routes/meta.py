"""
Server-to-server callbacks Meta calls directly — not user-facing, no bearer auth.
"""

from fastapi import APIRouter, Form

from app.schemas.meta import DataDeletionResponse
from app.services import meta_webhook_service

router = APIRouter()


@router.post("/data-deletion", response_model=DataDeletionResponse)
async def data_deletion_callback(signed_request: str = Form(...)):
    """Meta's Data Deletion Request Callback.

    Register this endpoint's full URL (e.g. https://api.kolably.com/api/v1/meta/data-deletion)
    in the App Dashboard's Data Deletion Request URL field.
    """
    return await meta_webhook_service.handle_data_deletion(signed_request)


@router.post("/deauthorize")
async def deauthorize_callback(signed_request: str = Form(...)):
    """Meta's Deauthorize Callback — fires when a user revokes access.

    Register this endpoint's full URL (e.g. https://api.kolably.com/api/v1/meta/deauthorize)
    in the App Dashboard's Deauthorize Callback URL field.
    """
    return await meta_webhook_service.handle_deauthorize(signed_request)
