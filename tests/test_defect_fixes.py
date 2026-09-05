"""Unit tests verifying fixes for defects #48, #49, #50, #51, #52, #53, #54."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.models.application import ApplicationDirection, ApplicationStatus, CampaignApplication
from app.models.campaign import Campaign
from app.repositories.campaign_repo import _sanitize_search_term as sanitize_campaign_search
from app.repositories.creator_repo import _sanitize_search_term as sanitize_creator_search
from app.repositories.profile_repo import ProfileRepository
from app.schemas.auth import LoginRequest
from app.schemas.chat import ConversationCreateRequest, MessageCreateRequest
from app.schemas.invoice import InvoiceCreateRequest
from app.services import application_service


def test_search_sanitizer_sql_injection_defense():
    """DEF-002: Verifies single quotes, dashes, equals, and SQL injection syntax are neutralized."""
    raw = "test' OR 1=1--"
    assert sanitize_campaign_search(raw) == "test OR 1 1"
    assert sanitize_creator_search(raw) == "test OR 1 1"

    # Multiple quotes, semicolons, brackets, PostgREST operators
    complex_payload = "admin'; DROP TABLE users; -- (foo.bar)"
    assert sanitize_campaign_search(complex_payload) == "admin DROP TABLE users foo bar"
    assert sanitize_creator_search(complex_payload) == "admin DROP TABLE users foo bar"


@pytest.mark.asyncio
async def test_application_decision_authorization_evaluated_before_status():
    """DEF-005 & DEF-006: Unauthorized users must receive 403 Forbidden rather than 400."""
    app_repo = AsyncMock()
    campaign_repo = AsyncMock()
    creator_repo = AsyncMock()
    business_repo = AsyncMock()

    app_id = "app-123"
    camp_id = "camp-456"

    # Application already decided (accepted), but requested by a creator
    already_accepted_app = CampaignApplication(
        id=app_id,
        campaign_id=camp_id,
        creator_id="creator-1",
        direction=ApplicationDirection.CREATOR_APPLIED,
        status=ApplicationStatus.ACCEPTED,
        created_at=datetime.now(UTC),
    )
    campaign = Campaign(
        id=camp_id,
        business_id="business-1",
        title="Test Campaign",
        objective="conversions",
        description="Test description",
        status="active",
        platforms=["instagram"],
        deliverables=[],
        created_at=datetime.now(UTC),
    )

    app_repo.get_by_id = AsyncMock(return_value=already_accepted_app)
    campaign_repo.get_by_id = AsyncMock(return_value=campaign)

    # Creator attempts to call accept on creator-applied application
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await application_service.accept_application(
            application_id=app_id,
            profile_id="creator-profile-1",
            role="creator",
            app_repo=app_repo,
            campaign_repo=campaign_repo,
            creator_repo=creator_repo,
            business_repo=business_repo,
        )

    # Must raise 403 Forbidden, NOT 400 Bad Request
    assert exc_info.value.status_code == 403
    assert "Only the business can decide" in exc_info.value.detail


def test_invoice_create_flat_amount_contract():
    """DEF-015: Ensure InvoiceCreateRequest accepts flat amount and generates default line item."""
    req = InvoiceCreateRequest(collaboration_id="collab-1", amount=1500.50)
    assert len(req.line_items) == 1
    assert req.line_items[0].title == "Collaboration Fee"
    assert req.line_items[0].amount == 1500.50

    # Also still supports explicit line items
    req_explicit = InvoiceCreateRequest(
        collaboration_id="collab-1",
        line_items=[{"title": "Custom Deliverable", "amount": 2000.0}],
    )
    assert len(req_explicit.line_items) == 1
    assert req_explicit.line_items[0].title == "Custom Deliverable"
    assert req_explicit.line_items[0].amount == 2000.0

    # Fails if neither provided
    with pytest.raises(ValidationError):
        InvoiceCreateRequest(collaboration_id="collab-1")


def test_chat_recipient_id_alias_and_whitespace_validation():
    """DEF-016 & DEF-017: recipient_id alias support and whitespace-only message rejection."""
    # recipient_id alias
    conv_req = ConversationCreateRequest(recipient_id="user-xyz")
    assert conv_req.participant_id == "user-xyz"

    # participant_id direct
    conv_req2 = ConversationCreateRequest(participant_id="user-abc")
    assert conv_req2.participant_id == "user-abc"

    # Whitespace-only message must be rejected
    with pytest.raises(ValidationError):
        MessageCreateRequest(content="   \n\t  ")

    # Valid message trimmed
    msg = MessageCreateRequest(content="  hello world!  ")
    assert msg.content == "hello world!"


def test_login_and_waitlist_schema_normalization():
    """DEF-001 & DEF-019: Login and waitlist handle reserved/test domains gracefully."""
    # LoginRequest accepts test domain without 422
    login_req = LoginRequest(email="  nobody@kolably.test  ", password="SecretPassword123")
    assert login_req.email == "nobody@kolably.test"

    # Waitlist schema handles test domain
    from app.api.routes.waitlist import WaitlistJoinRequest

    waitlist_req = WaitlistJoinRequest(email="blackbox_test@kolably.test", role="creator")
    assert waitlist_req.email == "blackbox_test@kolably.test"

    # Waitlist schema rejects invalid email format
    with pytest.raises(ValidationError):
        WaitlistJoinRequest(email="not-an-email", role="creator")


@pytest.mark.asyncio
async def test_profile_last_seen_at_iso_serialization():
    """DEF-018: ProfileRepository.update_last_seen_at converts datetime to ISO string."""
    repo = ProfileRepository()
    mock_update = AsyncMock(return_value=[{"id": "prof-1", "last_seen_at": "2026-09-06T00:00:00+00:00"}])
    repo.update = mock_update  # type: ignore[method-assign]

    now = datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC)
    await repo.update_last_seen_at("prof-1", now)

    mock_update.assert_called_once_with("prof-1", {"last_seen_at": now.isoformat()})
