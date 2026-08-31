"""
Isolated unit tests for email_service.py.
"""

import pytest

from app.core.enums import EmailDeliveryStatus, EmailFlow
from app.models.email_delivery import EmailDelivery
from app.services import email_service


class FakeEmailDeliveryRepo:
    def __init__(self):
        self.deliveries: dict[str, dict] = {}
        self.by_key: dict[str, dict] = {}

    async def get_by_idempotency_key(self, idempotency_key: str):
        row = self.by_key.get(idempotency_key)
        return EmailDelivery.from_row(row) if row else None

    async def get_by_resend_id(self, resend_id: str):
        for row in self.deliveries.values():
            if row.get("resend_id") == resend_id:
                return EmailDelivery.from_row(row)
        return None

    async def insert_delivery(self, data: dict):
        delivery_id = f"del_{len(self.deliveries) + 1}"
        row = dict(data)
        row["id"] = delivery_id
        row["created_at"] = "2026-08-30T00:00:00Z"
        row["updated_at"] = "2026-08-30T00:00:00Z"
        self.deliveries[delivery_id] = row
        self.by_key[data["idempotency_key"]] = row
        return EmailDelivery.from_row(row)

    async def update_delivery(self, delivery_id: str, data: dict):
        row = self.deliveries.get(delivery_id)
        if row:
            row.update(data)
            row["updated_at"] = "2026-08-30T00:00:01Z"
            return EmailDelivery.from_row(row)
        return None


class FakeResendClient:
    def __init__(self, should_fail: bool = False, fail_count: int = 0):
        self.should_fail = should_fail
        self.fail_count = fail_count
        self.calls = []

    async def send(self, payload: dict, idempotency_key: str | None = None):
        self.calls.append({"payload": payload, "idempotency_key": idempotency_key})
        if self.fail_count > 0:
            self.fail_count -= 1
            raise RuntimeError("Resend rate limit / temporary failure (429)")
        if self.should_fail:
            raise RuntimeError("Resend permanent failure (400)")
        return {"id": f"re_{len(self.calls)}"}


@pytest.mark.asyncio
async def test_send_email_success():
    repo = FakeEmailDeliveryRepo()
    client = FakeResendClient()

    delivery = await email_service.send_email(
        flow=EmailFlow.SIGNUP_CONFIRMATION,
        recipient_email="alex@example.com",
        subject="Verify Account",
        template_data={"name": "Alex", "otp_code": "123456", "action_url": "https://kolably.com"},
        idempotency_key="auth-signup:alex@example.com:123456",
        repo=repo,
        resend_client=client,
    )

    assert delivery is not None
    assert delivery.status == EmailDeliveryStatus.SENT
    assert delivery.resend_id == "re_1"
    assert len(client.calls) == 1
    assert client.calls[0]["idempotency_key"] == "auth-signup:alex@example.com:123456"


@pytest.mark.asyncio
async def test_send_email_idempotency_deduplication():
    repo = FakeEmailDeliveryRepo()
    client = FakeResendClient()

    # First send
    del1 = await email_service.send_email(
        flow=EmailFlow.PASSWORD_RESET,
        recipient_email="alex@example.com",
        subject="Reset Password",
        template_data={"name": "Alex", "otp_code": "654321", "reset_url": "https://kolably.com"},
        idempotency_key="auth-reset:alex@example.com:654321",
        repo=repo,
        resend_client=client,
    )
    assert del1.status == EmailDeliveryStatus.SENT
    assert len(client.calls) == 1

    # Second send with identical idempotency key
    del2 = await email_service.send_email(
        flow=EmailFlow.PASSWORD_RESET,
        recipient_email="alex@example.com",
        subject="Reset Password",
        template_data={"name": "Alex", "otp_code": "654321", "reset_url": "https://kolably.com"},
        idempotency_key="auth-reset:alex@example.com:654321",
        repo=repo,
        resend_client=client,
    )
    assert del2.status == EmailDeliveryStatus.SENT
    # No extra call made to Resend!
    assert len(client.calls) == 1


@pytest.mark.asyncio
async def test_send_email_bounded_retry_and_recovery():
    repo = FakeEmailDeliveryRepo()
    # Fail twice, succeed on 3rd attempt
    client = FakeResendClient(fail_count=2)

    delivery = await email_service.send_email(
        flow=EmailFlow.TEAM_INVITATION,
        recipient_email="team@example.com",
        subject="Invite",
        template_data={
            "inviter_name": "Boss",
            "business_name": "Acme",
            "role": "Editor",
            "accept_url": "https://kolably.com",
        },
        idempotency_key="team-invite:biz1:team@example.com",
        repo=repo,
        resend_client=client,
        max_retries=3,
    )

    assert delivery is not None
    assert delivery.status == EmailDeliveryStatus.SENT
    assert delivery.attempts == 3
    assert len(client.calls) == 3


@pytest.mark.asyncio
async def test_send_email_never_raise_on_fatal_error():
    repo = FakeEmailDeliveryRepo()
    client = FakeResendClient(should_fail=True)

    delivery = await email_service.send_email(
        flow=EmailFlow.KYB_APPROVED,
        recipient_email="biz@example.com",
        subject="KYB Approved",
        template_data={"business_name": "Acme Corp", "dashboard_url": "https://kolably.com/dashboard"},
        idempotency_key="kyb-approved:biz_999:verified",
        repo=repo,
        resend_client=client,
        max_retries=2,
    )

    assert delivery is None
    record = await repo.get_by_idempotency_key("kyb-approved:biz_999:verified")
    assert record is not None
    assert record.status == EmailDeliveryStatus.FAILED
    assert "Resend permanent failure" in (record.error_message or "")


@pytest.mark.asyncio
async def test_auth_templates_rendering_and_helpers():
    repo = FakeEmailDeliveryRepo()
    client = FakeResendClient()

    # Signup Confirmation helper
    await email_service.send_signup_confirmation_email(
        email="newuser@example.com",
        name="Alex <script>alert(1)</script>",
        otp_code="987654",
        action_url="https://kolably.com/verify?token=abc",
        profile_id="prof_1",
        repo=repo,
        resend_client=client,
    )
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["payload"]["to"] == ["newuser@example.com"]
    assert "987654" in call["payload"]["html"]
    assert "987654" in call["payload"]["text"]
    # HTML escaping verified: <script> must be escaped
    assert "<script>" not in call["payload"]["html"]
    assert "&lt;script&gt;" in call["payload"]["html"]

    # Password Reset helper
    await email_service.send_password_reset_email(
        email="reset@example.com",
        name="Sam",
        otp_code="112233",
        reset_url="https://kolably.com/reset?token=xyz",
        profile_id="prof_2",
        repo=repo,
        resend_client=client,
    )
    assert len(client.calls) == 2
    assert "112233" in client.calls[1]["payload"]["html"]

    # Team Invitation helper
    await email_service.send_team_invitation_email(
        email="invitee@example.com",
        inviter_name="Sarah",
        business_name="Nike Studio",
        role="Editor",
        accept_url="https://kolably.com/accept-invite?token=invite123",
        business_id="biz_100",
        inviter_profile_id="prof_sarah",
        repo=repo,
        resend_client=client,
    )
    assert len(client.calls) == 3
    assert "Nike Studio" in client.calls[2]["payload"]["html"]
    assert "Editor" in client.calls[2]["payload"]["text"]


@pytest.mark.asyncio
async def test_transactional_templates_rendering_and_helpers():
    repo = FakeEmailDeliveryRepo()
    client = FakeResendClient()

    # 1. KYB Approved
    await email_service.send_kyb_approved_email(
        email="owner@brand.com",
        business_name="Adidas Originals",
        dashboard_url="https://kolably.com/dashboard",
        business_id="biz_adi",
        profile_id="prof_adi",
        repo=repo,
        resend_client=client,
    )
    assert len(client.calls) == 1
    call1 = client.calls[0]
    assert "Adidas Originals" in call1["payload"]["html"]
    assert "Verified Brand" in call1["payload"]["html"]
    assert "https://kolably.com/dashboard" in call1["payload"]["text"]

    # 2. KYB Rejected
    await email_service.send_kyb_rejected_email(
        email="owner2@brand.com",
        business_name="Bonkers Corner",
        rejection_reason="PAN card document was blurred and unreadable.",
        resubmit_url="https://kolably.com/settings/verification",
        business_id="biz_bonk",
        profile_id="prof_bonk",
        repo=repo,
        resend_client=client,
    )
    assert len(client.calls) == 2
    call2 = client.calls[1]
    assert "Bonkers Corner" in call2["payload"]["html"]
    assert "PAN card document was blurred and unreadable." in call2["payload"]["html"]
    assert "https://kolably.com/settings/verification" in call2["payload"]["text"]

    # 3. Campaign Invite
    await email_service.send_campaign_invite_email(
        email="creator@influencer.com",
        creator_name="Rohan",
        campaign_title="Summer Fitness 2026",
        business_name="Puma India",
        compensation_text="₹40,000 + Apparel Kit",
        action_url="https://kolably.com/campaigns/c1",
        campaign_id="camp_1",
        creator_profile_id="prof_rohan",
        repo=repo,
        resend_client=client,
    )
    assert len(client.calls) == 3
    call3 = client.calls[2]
    assert "Summer Fitness 2026" in call3["payload"]["html"]
    assert "₹40,000 + Apparel Kit" in call3["payload"]["html"]

    # 4. Revision Requested
    await email_service.send_revision_requested_email(
        email="creator@influencer.com",
        creator_name="Rohan",
        campaign_title="Summer Fitness 2026",
        business_name="Puma India",
        revision_notes="Please include product close-up shot in the first 3 seconds.",
        review_url="https://kolably.com/collaborations/collab_1",
        application_id="app_1",
        creator_profile_id="prof_rohan",
        repo=repo,
        resend_client=client,
    )
    assert len(client.calls) == 4
    call4 = client.calls[3]
    assert "product close-up shot in the first 3 seconds." in call4["payload"]["html"]

    # 5. Invoice
    await email_service.send_invoice_email(
        email="brand@business.com",
        recipient_name="Finance Team",
        sender_name="Rohan Creator",
        invoice_number="INV-2026-0042",
        amount_formatted="₹40,000",
        status="sent",
        view_url="https://kolably.com/invoices/inv_42",
        invoice_id="inv_42",
        recipient_profile_id="prof_fin",
        repo=repo,
        resend_client=client,
    )
    assert len(client.calls) == 5
    call5 = client.calls[4]
    assert "INV-2026-0042" in call5["payload"]["html"]
    assert "₹40,000" in call5["payload"]["html"]
    assert "https://kolably.com/invoices/inv_42" in call5["payload"]["text"]


@pytest.mark.asyncio
async def test_resend_webhook_status_updates():
    repo = FakeEmailDeliveryRepo()
    # Insert a delivery record with a known resend_id
    await repo.insert_delivery(
        {
            "idempotency_key": "test:delivery:1",
            "flow_name": EmailFlow.INVOICE.value,
            "recipient_email": "brand@example.com",
            "subject": "Invoice",
            "status": EmailDeliveryStatus.SENT.value,
            "resend_id": "re_delivered_123",
        }
    )

    # Test email.delivered webhook event
    res1 = await email_service.handle_resend_webhook(
        {"type": "email.delivered", "data": {"id": "re_delivered_123"}},
        repo=repo,
    )
    assert res1["status"] == "updated"
    assert res1["delivery_status"] == EmailDeliveryStatus.DELIVERED.value
    rec1 = await repo.get_by_resend_id("re_delivered_123")
    assert rec1.status == EmailDeliveryStatus.DELIVERED

    # Test email.bounced webhook event
    res2 = await email_service.handle_resend_webhook(
        {"type": "email.bounced", "data": {"email_id": "re_delivered_123"}},
        repo=repo,
    )
    assert res2["status"] == "updated"
    assert res2["delivery_status"] == EmailDeliveryStatus.BOUNCED.value
    rec2 = await repo.get_by_resend_id("re_delivered_123")
    assert rec2.status == EmailDeliveryStatus.BOUNCED


@pytest.mark.asyncio
async def test_invalid_recipient_graceful_handling():
    repo = FakeEmailDeliveryRepo()
    client = FakeResendClient()

    # Empty email
    res1 = await email_service.send_email(
        flow=EmailFlow.SIGNUP_CONFIRMATION,
        recipient_email="",
        subject="Test",
        template_data={},
        idempotency_key="test:invalid:1",
        repo=repo,
        resend_client=client,
    )
    assert res1 is None
    assert len(client.calls) == 0

    # Malformed email without @
    res2 = await email_service.send_email(
        flow=EmailFlow.SIGNUP_CONFIRMATION,
        recipient_email="notanemail",
        subject="Test",
        template_data={},
        idempotency_key="test:invalid:2",
        repo=repo,
        resend_client=client,
    )
    assert res2 is None
    assert len(client.calls) == 0
