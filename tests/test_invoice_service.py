"""
Unit tests for invoice_service — repositories injected as fakes, no Supabase.
"""

import pytest
from fastapi import HTTPException

from app.core.enums import UserRole
from app.models.business import Business
from app.models.collaboration import Collaboration
from app.models.creator import Creator
from app.models.invoice import Invoice
from app.schemas.invoice import InvoiceCreateRequest, InvoiceLineItem
from app.services import invoice_service

COLLAB_ROW = {
    "id": "collab1",
    "campaign_id": "camp1",
    "creator_id": "creator1",
    "business_id": "biz1",
    "status": "completed",
    "created_at": "2026-01-01T00:00:00+00:00",
}

CREATOR_ROW = {
    "id": "creator1",
    "profile_id": "creator-profile-1",
    "name": "Ananya Rao",
    "created_at": "2026-01-01T00:00:00+00:00",
    "payout_method_type": "bank",
    "bank_name": "HDFC Bank",
    "account_number_last4": "4412",
    "pan_number": "ABCDE1234F",
    "has_gst": False,
}

BUSINESS_ROW = {
    "id": "biz1",
    "profile_id": "biz-profile-1",
    "business_name": "BrewHouse Cafe",
    "owner_name": "Priya",
    "created_at": "2026-01-01T00:00:00+00:00",
    "gst_number": "07AAECB1234F1Z5",
}

INVOICE_ROW = {
    "id": "inv1",
    "collaboration_id": "collab1",
    "creator_id": "creator1",
    "business_id": "biz1",
    "status": "sent",
    "line_items": [{"title": "Instagram Reel", "amount": 6000}],
    "total_amount": 6000,
    "billed_by": {"name": "Ananya Rao"},
    "billed_to": {"name": "BrewHouse Cafe"},
    "created_at": "2026-01-01T00:00:00+00:00",
}


class FakeInvoiceRepo:
    def __init__(self, row=None, existing_for_collab=None):
        self._row = row
        self._existing_for_collab = existing_for_collab
        self.inserted: list[dict] = []
        self.status_updates: list[tuple] = []

    async def get_by_id(self, invoice_id):
        return Invoice.from_row(self._row) if self._row else None

    async def get_by_collaboration_id(self, collaboration_id):
        return Invoice.from_row(self._existing_for_collab) if self._existing_for_collab else None

    async def list_by_creator(self, creator_id, status=None, page=1, page_size=20):
        rows = [self._row] if self._row else []
        return [Invoice.from_row(r) for r in rows], len(rows)

    async def list_by_business(self, business_id, status=None, page=1, page_size=20):
        rows = [self._row] if self._row else []
        return [Invoice.from_row(r) for r in rows], len(rows)

    async def insert_invoice(self, data):
        self.inserted.append(data)
        row = {**INVOICE_ROW, **data}
        self._row = row
        return Invoice.from_row(row)

    async def update_status(self, invoice_id, data):
        self.status_updates.append((invoice_id, data))
        if self._row is None:
            return None
        self._row = {**self._row, **data}
        return Invoice.from_row(self._row)


class FakeCollabRepo:
    def __init__(self, row=dict(COLLAB_ROW)):
        self._row = row

    async def get_by_id(self, collaboration_id):
        return Collaboration.from_row(self._row) if self._row else None


class FakeCreatorRepo:
    def __init__(self, row=dict(CREATOR_ROW)):
        self._row = row

    async def get_by_profile_id(self, profile_id):
        if self._row and self._row.get("profile_id") == profile_id:
            return Creator.from_row(self._row)
        return None

    async def get_by_id(self, creator_id):
        return Creator.from_row(self._row) if self._row else None


class FakeBusinessRepo:
    def __init__(self, row=dict(BUSINESS_ROW)):
        self._row = row

    async def get_by_id(self, business_id):
        return Business.from_row(self._row) if self._row else None

    async def get_id_by_profile_id(self, profile_id):
        if self._row and self._row.get("profile_id") == profile_id:
            return self._row["id"]
        return None


class FakeBusinessMemberRepo:
    """No team memberships — a profile with no business row (e.g. a plain
    creator) has no fallback path either."""

    async def get_active_by_profile_id(self, profile_id):
        return None


LINE_ITEMS = [InvoiceLineItem(title="Instagram Reel", amount=6000)]


# ── create_invoice ───────────────────────────────────────────────────────
async def test_create_invoice_happy_path_builds_snapshots_and_total():
    invoice_repo = FakeInvoiceRepo()
    result = await invoice_service.create_invoice(
        profile_id="creator-profile-1",
        role=UserRole.CREATOR,
        data=InvoiceCreateRequest(collaboration_id="collab1", line_items=LINE_ITEMS),
        repo=invoice_repo,
        collab_repo=FakeCollabRepo(),
        creator_repo=FakeCreatorRepo(),
        business_repo=FakeBusinessRepo(),
    )

    assert result.total_amount == 6000
    assert result.billed_by.name == "Ananya Rao"
    assert result.billed_by.bank_display == "HDFC Bank ••4412"
    assert result.billed_to.name == "BrewHouse Cafe"
    assert result.billed_to.gst == "07AAECB1234F1Z5"
    assert result.status == "sent"
    assert invoice_repo.inserted[0]["collaboration_id"] == "collab1"


async def test_create_invoice_falls_back_to_owner_name_when_business_name_unset():
    """A business can have a completed collaboration before finishing onboarding
    (business_name is only set in step 1) — billed_to.name must not be null."""
    unnamed_business = {**BUSINESS_ROW, "business_name": None, "owner_name": "Priya"}
    result = await invoice_service.create_invoice(
        profile_id="creator-profile-1",
        role=UserRole.CREATOR,
        data=InvoiceCreateRequest(collaboration_id="collab1", line_items=LINE_ITEMS),
        repo=FakeInvoiceRepo(),
        collab_repo=FakeCollabRepo(),
        creator_repo=FakeCreatorRepo(),
        business_repo=FakeBusinessRepo(row=unnamed_business),
    )
    assert result.billed_to.name == "Priya"


async def test_create_invoice_404_when_collaboration_missing():
    with pytest.raises(HTTPException) as exc_info:
        await invoice_service.create_invoice(
            profile_id="creator-profile-1",
            role=UserRole.CREATOR,
            data=InvoiceCreateRequest(collaboration_id="missing", line_items=LINE_ITEMS),
            repo=FakeInvoiceRepo(),
            collab_repo=FakeCollabRepo(row=None),
            creator_repo=FakeCreatorRepo(),
            business_repo=FakeBusinessRepo(),
        )
    assert exc_info.value.status_code == 404


async def test_create_invoice_403_for_non_owning_creator():
    with pytest.raises(HTTPException) as exc_info:
        await invoice_service.create_invoice(
            profile_id="someone-elses-profile",
            role=UserRole.CREATOR,
            data=InvoiceCreateRequest(collaboration_id="collab1", line_items=LINE_ITEMS),
            repo=FakeInvoiceRepo(),
            collab_repo=FakeCollabRepo(),
            creator_repo=FakeCreatorRepo(),
            business_repo=FakeBusinessRepo(),
        )
    assert exc_info.value.status_code == 403


async def test_create_invoice_400_when_collaboration_not_completed():
    active_collab = {**COLLAB_ROW, "status": "active"}
    with pytest.raises(HTTPException) as exc_info:
        await invoice_service.create_invoice(
            profile_id="creator-profile-1",
            role=UserRole.CREATOR,
            data=InvoiceCreateRequest(collaboration_id="collab1", line_items=LINE_ITEMS),
            repo=FakeInvoiceRepo(),
            collab_repo=FakeCollabRepo(row=active_collab),
            creator_repo=FakeCreatorRepo(),
            business_repo=FakeBusinessRepo(),
        )
    assert exc_info.value.status_code == 400


async def test_create_invoice_409_when_already_exists_for_collaboration():
    with pytest.raises(HTTPException) as exc_info:
        await invoice_service.create_invoice(
            profile_id="creator-profile-1",
            role=UserRole.CREATOR,
            data=InvoiceCreateRequest(collaboration_id="collab1", line_items=LINE_ITEMS),
            repo=FakeInvoiceRepo(existing_for_collab=dict(INVOICE_ROW)),
            collab_repo=FakeCollabRepo(),
            creator_repo=FakeCreatorRepo(),
            business_repo=FakeBusinessRepo(),
        )
    assert exc_info.value.status_code == 409


async def test_create_invoice_allowed_for_superadmin_regardless_of_ownership():
    # The admin's own profile_id has no matching creator row (get_by_profile_id
    # returns None), but get_by_id(collab.creator_id) still resolves the real
    # creator who owns the collaboration — exactly like the live repo would.
    result = await invoice_service.create_invoice(
        profile_id="some-admin-profile",
        role=UserRole.SUPERADMIN,
        data=InvoiceCreateRequest(collaboration_id="collab1", line_items=LINE_ITEMS),
        repo=FakeInvoiceRepo(),
        collab_repo=FakeCollabRepo(),
        creator_repo=FakeCreatorRepo(),
        business_repo=FakeBusinessRepo(),
    )
    assert result.creator_id == "creator1"


# ── list_invoices ────────────────────────────────────────────────────────
async def test_list_invoices_as_creator_uses_creator_id():
    result = await invoice_service.list_invoices(
        profile_id="creator-profile-1",
        role=UserRole.CREATOR,
        repo=FakeInvoiceRepo(row=dict(INVOICE_ROW)),
        creator_repo=FakeCreatorRepo(),
    )
    assert result["total"] == 1
    assert result["items"][0].creator_id == "creator1"


async def test_list_invoices_as_business_uses_business_id():
    result = await invoice_service.list_invoices(
        profile_id="biz-profile-1",
        role=UserRole.BUSINESS,
        repo=FakeInvoiceRepo(row=dict(INVOICE_ROW)),
        business_repo=FakeBusinessRepo(),
    )
    assert result["total"] == 1
    assert result["items"][0].business_id == "biz1"


# ── get_invoice ──────────────────────────────────────────────────────────
async def test_get_invoice_accessible_to_owning_creator():
    result = await invoice_service.get_invoice(
        "inv1",
        profile_id="creator-profile-1",
        role=UserRole.CREATOR,
        repo=FakeInvoiceRepo(row=dict(INVOICE_ROW)),
        creator_repo=FakeCreatorRepo(),
        business_repo=FakeBusinessRepo(row=None),
        member_repo=FakeBusinessMemberRepo(),
    )
    assert result.id == "inv1"


async def test_get_invoice_accessible_to_owning_business():
    result = await invoice_service.get_invoice(
        "inv1",
        profile_id="biz-profile-1",
        role=UserRole.BUSINESS,
        repo=FakeInvoiceRepo(row=dict(INVOICE_ROW)),
        creator_repo=FakeCreatorRepo(row=None),
        business_repo=FakeBusinessRepo(),
    )
    assert result.id == "inv1"


async def test_get_invoice_403_for_unrelated_party():
    with pytest.raises(HTTPException) as exc_info:
        await invoice_service.get_invoice(
            "inv1",
            profile_id="unrelated-profile",
            role=UserRole.BUSINESS,
            repo=FakeInvoiceRepo(row=dict(INVOICE_ROW)),
            creator_repo=FakeCreatorRepo(row=None),
            business_repo=FakeBusinessRepo(row=None),
            member_repo=FakeBusinessMemberRepo(),
        )
    assert exc_info.value.status_code == 403


# ── mark_invoice_paid ────────────────────────────────────────────────────
async def test_mark_invoice_paid_happy_path():
    result = await invoice_service.mark_invoice_paid(
        "inv1",
        profile_id="creator-profile-1",
        role=UserRole.CREATOR,
        repo=FakeInvoiceRepo(row=dict(INVOICE_ROW)),
        creator_repo=FakeCreatorRepo(),
    )
    assert result.status == "paid"
    assert result.paid_at is not None


async def test_mark_invoice_paid_403_for_non_owning_creator():
    with pytest.raises(HTTPException) as exc_info:
        await invoice_service.mark_invoice_paid(
            "inv1",
            profile_id="someone-elses-profile",
            role=UserRole.CREATOR,
            repo=FakeInvoiceRepo(row=dict(INVOICE_ROW)),
            creator_repo=FakeCreatorRepo(),
        )
    assert exc_info.value.status_code == 403


async def test_mark_invoice_paid_400_when_already_paid():
    already_paid = {**INVOICE_ROW, "status": "paid", "paid_at": "2026-01-02T00:00:00+00:00"}
    with pytest.raises(HTTPException) as exc_info:
        await invoice_service.mark_invoice_paid(
            "inv1",
            profile_id="creator-profile-1",
            role=UserRole.CREATOR,
            repo=FakeInvoiceRepo(row=already_paid),
            creator_repo=FakeCreatorRepo(),
        )
    assert exc_info.value.status_code == 400
