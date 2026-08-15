from datetime import UTC, datetime

from fastapi import HTTPException, status

from app.core.enums import CollaborationStatus, InvoiceStatus, NotificationType, UserRole
from app.models.business import Business
from app.models.creator import Creator
from app.models.invoice import Invoice
from app.repositories.business_member_repo import BusinessMemberRepository
from app.repositories.business_repo import BusinessRepository
from app.repositories.collaboration_repo import CollaborationRepository
from app.repositories.creator_repo import CreatorRepository
from app.repositories.invoice_repo import InvoiceRepository
from app.schemas.invoice import InvoiceCreateRequest, InvoiceResponse
from app.services import business_access, chat_service, notification_service


def _invoice_number(invoice: Invoice) -> str:
    created_at = invoice.created_at
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    return f"KLB-{created_at.year}-{invoice.id.replace('-', '')[:6].upper()}"


def _invoice_to_response(invoice: Invoice) -> InvoiceResponse:
    invoice_number = _invoice_number(invoice)
    return InvoiceResponse(
        id=invoice.id,
        invoice_number=invoice_number,
        collaboration_id=invoice.collaboration_id,
        creator_id=invoice.creator_id,
        business_id=invoice.business_id,
        status=invoice.status.value,
        line_items=invoice.line_items,
        total_amount=invoice.total_amount,
        billed_by=invoice.billed_by,
        billed_to=invoice.billed_to,
        created_at=invoice.created_at,
        paid_at=invoice.paid_at,
        paid_by=invoice.paid_by,
    )


def _bank_display(creator: Creator) -> str | None:
    if creator.payout_method_type == "bank" and creator.account_number_last4:
        return f"{creator.bank_name or 'Bank'} ••{creator.account_number_last4}"
    if creator.payout_method_type == "upi" and creator.upi_id:
        return creator.upi_id
    return None


def _billed_by_snapshot(creator: Creator) -> dict:
    return {
        "name": creator.name,
        "pan": creator.pan_number,
        "gst": creator.gst_number if creator.has_gst else None,
        "bank_display": _bank_display(creator),
    }


def _billed_to_snapshot(business: Business) -> dict:
    return {"name": business.business_name or business.owner_name or "Business", "gst": business.gst_number}


async def create_invoice(
    profile_id: str,
    role: UserRole,
    data: InvoiceCreateRequest,
    *,
    repo: InvoiceRepository | None = None,
    collab_repo: CollaborationRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> InvoiceResponse:
    repo = repo or InvoiceRepository()
    collab_repo = collab_repo or CollaborationRepository()
    creator_repo = creator_repo or CreatorRepository()
    business_repo = business_repo or BusinessRepository()

    collab = await collab_repo.get_by_id(data.collaboration_id)
    if not collab:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collaboration not found")

    creator = await creator_repo.get_by_profile_id(profile_id)
    if role != UserRole.SUPERADMIN:
        if not creator or collab.creator_id != creator.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="You do not own this collaboration"
            )
    if not creator:
        creator = await creator_repo.get_by_id(collab.creator_id)
    if not creator:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found")

    if collab.status != CollaborationStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Collaboration must be completed before generating an invoice",
        )

    existing = await repo.get_by_collaboration_id(collab.id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="An invoice already exists for this collaboration"
        )

    business = await business_repo.get_by_id(collab.business_id)
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")

    total_amount = sum(item.amount for item in data.line_items)
    payment_confirmed = collab.payment_confirmed_at is not None

    row = await repo.insert_invoice(
        {
            "collaboration_id": collab.id,
            "creator_id": collab.creator_id,
            "business_id": collab.business_id,
            "status": InvoiceStatus.PAID.value if payment_confirmed else InvoiceStatus.SENT.value,
            "line_items": [item.model_dump() for item in data.line_items],
            "total_amount": total_amount,
            "billed_by": _billed_by_snapshot(creator),
            "billed_to": _billed_to_snapshot(business),
            "paid_at": collab.payment_confirmed_at if payment_confirmed else None,
            "paid_by": collab.payment_confirmed_by if payment_confirmed else None,
        }
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create invoice")

    await notification_service.create_notification(
        profile_id=business.profile_id,
        type=NotificationType.INVOICE_RECEIVED,
        title="New invoice received",
        body=f"{creator.name} sent you an invoice for ₹{total_amount:,.0f}",
        related_id=row.id,
    )

    await chat_service.post_collaboration_event(
        data.collaboration_id,
        creator.profile_id,
        "invoice_raised",
        f"Raised an invoice for ₹{total_amount:,.0f}.",
        extra={"invoice_id": row.id, "total_amount": total_amount},
    )

    return _invoice_to_response(row)


async def list_invoices(
    profile_id: str,
    role: UserRole,
    status_filter: str | None = None,
    page: int = 1,
    page_size: int = 20,
    *,
    repo: InvoiceRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> dict:
    repo = repo or InvoiceRepository()

    if role == UserRole.CREATOR:
        creator_repo = creator_repo or CreatorRepository()
        creator = await creator_repo.get_by_profile_id(profile_id)
        if not creator:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator profile not found")
        invoices, total = await repo.list_by_creator(creator.id, status=status_filter, page=page, page_size=page_size)
    elif role == UserRole.BUSINESS:
        business_repo = business_repo or BusinessRepository()
        business_id = await business_access.get_business_id_for_profile(
            profile_id, business_repo=business_repo, member_repo=member_repo
        )
        if not business_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile not found")
        invoices, total = await repo.list_by_business(
            business_id, status=status_filter, page=page, page_size=page_size
        )
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")

    return {
        "items": [_invoice_to_response(i) for i in invoices],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


async def get_invoice(
    invoice_id: str,
    profile_id: str,
    role: UserRole,
    *,
    repo: InvoiceRepository | None = None,
    creator_repo: CreatorRepository | None = None,
    business_repo: BusinessRepository | None = None,
    member_repo: BusinessMemberRepository | None = None,
) -> InvoiceResponse:
    repo = repo or InvoiceRepository()
    invoice = await repo.get_by_id(invoice_id)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    if role != UserRole.SUPERADMIN:
        creator_repo = creator_repo or CreatorRepository()
        business_repo = business_repo or BusinessRepository()
        creator = await creator_repo.get_by_profile_id(profile_id)
        business_id = await business_access.get_business_id_for_profile(
            profile_id, business_repo=business_repo, member_repo=member_repo
        )
        owns_as_creator = bool(creator) and invoice.creator_id == creator.id
        owns_as_business = bool(business_id) and invoice.business_id == business_id
        if not (owns_as_creator or owns_as_business):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="You do not have access to this invoice"
            )

    return _invoice_to_response(invoice)


async def mark_invoice_paid(
    invoice_id: str,
    profile_id: str,
    role: UserRole,
    *,
    repo: InvoiceRepository | None = None,
    creator_repo: CreatorRepository | None = None,
) -> InvoiceResponse:
    repo = repo or InvoiceRepository()
    invoice = await repo.get_by_id(invoice_id)
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    if role != UserRole.SUPERADMIN:
        creator_repo = creator_repo or CreatorRepository()
        creator = await creator_repo.get_by_profile_id(profile_id)
        if not creator or invoice.creator_id != creator.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the creator who issued this invoice can mark it paid",
            )

    if invoice.status == InvoiceStatus.PAID:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invoice is already marked paid")

    updated = await repo.update_status(
        invoice_id,
        {"status": InvoiceStatus.PAID.value, "paid_at": datetime.now(UTC).isoformat(), "paid_by": profile_id},
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update invoice")

    return _invoice_to_response(updated)
