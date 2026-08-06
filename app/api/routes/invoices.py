"""
Invoice routes — creator-issued invoices for completed collaborations.
"""

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_current_user, require_role
from app.core.enums import UserRole
from app.schemas.common import PaginatedResponse
from app.schemas.invoice import InvoiceCreateRequest, InvoiceResponse
from app.schemas.user import UserInToken
from app.services import invoice_service

router = APIRouter()


@router.post(
    "/",
    response_model=InvoiceResponse,
    status_code=201,
    dependencies=[Depends(require_role(UserRole.CREATOR, UserRole.SUPERADMIN))],
)
async def create_invoice(
    data: InvoiceCreateRequest,
    user: UserInToken = Depends(get_current_user),
):
    """Generate an invoice for a completed collaboration (creator only)."""
    return await invoice_service.create_invoice(profile_id=user.id, role=user.role, data=data)


@router.get("/", response_model=PaginatedResponse[InvoiceResponse])
async def list_invoices(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: UserInToken = Depends(get_current_user),
):
    """List invoices for the current user — sent (creator) or received (business)."""
    return await invoice_service.list_invoices(
        profile_id=user.id, role=user.role, status_filter=status, page=page, page_size=page_size
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Get a single invoice — accessible to either party on the collaboration."""
    return await invoice_service.get_invoice(invoice_id, profile_id=user.id, role=user.role)


@router.patch(
    "/{invoice_id}/paid",
    response_model=InvoiceResponse,
    dependencies=[Depends(require_role(UserRole.CREATOR, UserRole.SUPERADMIN))],
)
async def mark_invoice_paid(
    invoice_id: str,
    user: UserInToken = Depends(get_current_user),
):
    """Mark an invoice paid — the issuing creator self-reports receipt (honour system; Kolably never moves funds)."""
    return await invoice_service.mark_invoice_paid(invoice_id, profile_id=user.id, role=user.role)
