"""
Email service using Resend and Jinja2 templates.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings
from app.core.enums import EmailDeliveryStatus, EmailFlow
from app.models.email_delivery import EmailDelivery
from app.repositories.email_delivery_repo import EmailDeliveryRepository

logger = logging.getLogger(__name__)

# Locate templates directory
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"

# Initialize Jinja2 environment with autoescaping for HTML
_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)


def _render_template(template_name: str, context: dict[str, Any]) -> str:
    """Render a template with context variables."""
    try:
        template = _jinja_env.get_template(template_name)
        return template.render(**context)
    except Exception as exc:
        logger.warning("Template %s not found or render failed: %s", template_name, exc)
        # Fallback basic rendering
        return f"<p>{context.get('message', '')}</p>"


def _render_plain_text(template_name: str, context: dict[str, Any]) -> str:
    """Render plain text fallback."""
    try:
        template = _jinja_env.get_template(template_name)
        return template.render(**context)
    except Exception:
        # Generic fallback
        return "\n".join(f"{k}: {v}" for k, v in context.items() if isinstance(v, (str, int, float)))


class ResendClientWrapper:
    """Wrapper around resend SDK for testing and dispatch."""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.RESEND_API_KEY
        if self.api_key:
            try:
                import resend

                resend.api_key = self.api_key
                self._resend = resend
            except ImportError:
                self._resend = None
        else:
            self._resend = None

    async def send(self, payload: dict[str, Any], idempotency_key: str | None = None) -> dict[str, Any]:
        if not self._resend:
            logger.info("Resend not configured or API key missing. Simulating send for %s", payload.get("to"))
            return {"id": f"sim_{idempotency_key or 'test'}"}

        # Run synchronous resend SDK send call in threadpool
        def _do_send():
            params = dict(payload)
            if idempotency_key:
                headers = dict(params.get("headers") or {})
                headers["Idempotency-Key"] = idempotency_key
                params["headers"] = headers
            return self._resend.Emails.send(params)

        return await asyncio.to_thread(_do_send)


async def send_email(
    flow: EmailFlow,
    recipient_email: str,
    subject: str,
    template_data: dict[str, Any],
    *,
    idempotency_key: str,
    recipient_profile_id: str | None = None,
    repo: EmailDeliveryRepository | None = None,
    resend_client: Any | None = None,
    max_retries: int = 3,
) -> EmailDelivery | None:
    """Send an email using Resend, ensuring idempotency and bounded retries.

    Never raises: failures are logged and recorded in email_deliveries table.
    """
    repo = repo or EmailDeliveryRepository()
    client = resend_client or ResendClientWrapper()

    if not recipient_email or "@" not in recipient_email:
        logger.warning("Invalid recipient email: %s for flow %s", recipient_email, flow.value)
        return None

    # Deduplication check
    try:
        existing = await repo.get_by_idempotency_key(idempotency_key)
        if existing and existing.status in (EmailDeliveryStatus.SENT, EmailDeliveryStatus.DELIVERED):
            logger.info("Email already sent for idempotency_key: %s", idempotency_key)
            return existing
    except Exception:
        logger.exception("Failed to query existing email delivery for idempotency_key: %s", idempotency_key)
        existing = None

    # Render HTML and plain text
    html_content = _render_template(f"{flow.value}.html", template_data)
    text_content = _render_plain_text(f"{flow.value}.txt", template_data)

    payload = {
        "from": settings.EMAIL_FROM,
        "to": [recipient_email],
        "subject": subject,
        "html": html_content,
        "text": text_content,
        "reply_to": settings.EMAIL_REPLY_TO,
    }

    delivery_id = existing.id if existing else None
    if not existing:
        try:
            delivery = await repo.insert_delivery(
                {
                    "idempotency_key": idempotency_key,
                    "flow_name": flow.value,
                    "recipient_email": recipient_email,
                    "recipient_profile_id": recipient_profile_id,
                    "subject": subject,
                    "status": EmailDeliveryStatus.PENDING.value,
                    "attempts": 1,
                }
            )
            if delivery:
                delivery_id = delivery.id
        except Exception:
            logger.exception("Failed to record initial email delivery for %s", recipient_email)

    attempts = 0
    last_error = None
    resend_id = None

    while attempts < max_retries:
        attempts += 1
        try:
            res = await client.send(payload, idempotency_key=idempotency_key)
            if isinstance(res, dict):
                resend_id = res.get("id")
            elif hasattr(res, "id"):
                resend_id = getattr(res, "id")
            elif hasattr(res, "get"):
                resend_id = res.get("id")
            else:
                resend_id = str(res)

            # Success
            if delivery_id:
                await repo.update_delivery(
                    delivery_id,
                    {
                        "status": EmailDeliveryStatus.SENT.value,
                        "resend_id": resend_id,
                        "attempts": attempts,
                        "error_message": None,
                    },
                )
            logger.info("Email sent successfully: flow=%s, to=%s, resend_id=%s", flow.value, recipient_email, resend_id)
            return EmailDelivery(
                id=delivery_id or "temp",
                idempotency_key=idempotency_key,
                flow_name=flow,
                recipient_email=recipient_email,
                subject=subject,
                status=EmailDeliveryStatus.SENT,
                recipient_profile_id=recipient_profile_id,
                resend_id=resend_id,
                attempts=attempts,
            )
        except Exception as exc:
            last_error = str(exc)
            logger.warning(
                "Attempt %d/%d failed to send email (flow=%s, to=%s): %s",
                attempts,
                max_retries,
                flow.value,
                recipient_email,
                exc,
            )
            if attempts < max_retries:
                # Exponential backoff: 0.5s, 1s, 2s
                await asyncio.sleep(0.5 * (2 ** (attempts - 1)))

    # Permanent failure after max_retries
    if delivery_id:
        try:
            await repo.update_delivery(
                delivery_id,
                {
                    "status": EmailDeliveryStatus.FAILED.value,
                    "attempts": attempts,
                    "error_message": last_error,
                },
            )
        except Exception:
            logger.exception("Failed to update failed delivery state for %s", delivery_id)

    return None


# ── Specialized Auth Helpers ────────────────────────────────────────────────


async def send_signup_confirmation_email(
    email: str,
    name: str,
    otp_code: str,
    action_url: str,
    *,
    profile_id: str | None = None,
    repo: EmailDeliveryRepository | None = None,
    resend_client: Any | None = None,
) -> None:
    idempotency_key = f"auth-signup:{email}:{otp_code}"
    await send_email(
        flow=EmailFlow.SIGNUP_CONFIRMATION,
        recipient_email=email,
        subject="Verify your Kolably Account",
        template_data={
            "name": name,
            "otp_code": otp_code,
            "action_url": action_url,
        },
        idempotency_key=idempotency_key,
        recipient_profile_id=profile_id,
        repo=repo,
        resend_client=resend_client,
    )


async def send_password_reset_email(
    email: str,
    name: str,
    otp_code: str,
    reset_url: str,
    *,
    profile_id: str | None = None,
    repo: EmailDeliveryRepository | None = None,
    resend_client: Any | None = None,
) -> None:
    idempotency_key = f"auth-reset:{email}:{otp_code}"
    await send_email(
        flow=EmailFlow.PASSWORD_RESET,
        recipient_email=email,
        subject="Reset your Kolably password",
        template_data={
            "name": name,
            "otp_code": otp_code,
            "reset_url": reset_url,
            "expires_in_minutes": 15,
        },
        idempotency_key=idempotency_key,
        recipient_profile_id=profile_id,
        repo=repo,
        resend_client=resend_client,
    )


async def send_team_invitation_email(
    email: str,
    inviter_name: str,
    business_name: str,
    role: str,
    accept_url: str,
    *,
    business_id: str,
    inviter_profile_id: str | None = None,
    repo: EmailDeliveryRepository | None = None,
    resend_client: Any | None = None,
) -> None:
    idempotency_key = f"team-invite:{business_id}:{email}"
    await send_email(
        flow=EmailFlow.TEAM_INVITATION,
        recipient_email=email,
        subject=f"{inviter_name} invited you to join {business_name} on Kolably",
        template_data={
            "inviter_name": inviter_name,
            "business_name": business_name,
            "role": role,
            "accept_url": accept_url,
        },
        idempotency_key=idempotency_key,
        recipient_profile_id=inviter_profile_id,
        repo=repo,
        resend_client=resend_client,
    )


# ── Specialized Transactional Helpers ──────────────────────────────────────


async def send_kyb_approved_email(
    email: str,
    business_name: str,
    dashboard_url: str,
    *,
    business_id: str,
    profile_id: str | None = None,
    repo: EmailDeliveryRepository | None = None,
    resend_client: Any | None = None,
) -> None:
    idempotency_key = f"kyb-approved:{business_id}:verified"
    await send_email(
        flow=EmailFlow.KYB_APPROVED,
        recipient_email=email,
        subject=f"Your business verification is approved! — {business_name}",
        template_data={
            "business_name": business_name,
            "dashboard_url": dashboard_url,
        },
        idempotency_key=idempotency_key,
        recipient_profile_id=profile_id,
        repo=repo,
        resend_client=resend_client,
    )


async def send_kyb_rejected_email(
    email: str,
    business_name: str,
    rejection_reason: str,
    resubmit_url: str,
    *,
    business_id: str,
    profile_id: str | None = None,
    repo: EmailDeliveryRepository | None = None,
    resend_client: Any | None = None,
) -> None:
    idempotency_key = f"kyb-rejected:{business_id}:{rejection_reason[:32]}"
    await send_email(
        flow=EmailFlow.KYB_REJECTED,
        recipient_email=email,
        subject=f"Action required: Business verification update for {business_name}",
        template_data={
            "business_name": business_name,
            "rejection_reason": rejection_reason,
            "resubmit_url": resubmit_url,
        },
        idempotency_key=idempotency_key,
        recipient_profile_id=profile_id,
        repo=repo,
        resend_client=resend_client,
    )


async def send_campaign_invite_email(
    email: str,
    creator_name: str,
    campaign_title: str,
    business_name: str,
    compensation_text: str,
    action_url: str,
    *,
    campaign_id: str,
    creator_profile_id: str | None = None,
    repo: EmailDeliveryRepository | None = None,
    resend_client: Any | None = None,
) -> None:
    idempotency_key = f"campaign-invite:{campaign_id}:{email}"
    await send_email(
        flow=EmailFlow.CAMPAIGN_INVITE,
        recipient_email=email,
        subject=f"Campaign Invitation: {campaign_title}",
        template_data={
            "creator_name": creator_name,
            "campaign_title": campaign_title,
            "business_name": business_name,
            "compensation_text": compensation_text,
            "action_url": action_url,
        },
        idempotency_key=idempotency_key,
        recipient_profile_id=creator_profile_id,
        repo=repo,
        resend_client=resend_client,
    )


async def send_revision_requested_email(
    email: str,
    creator_name: str,
    campaign_title: str,
    business_name: str,
    revision_notes: str,
    review_url: str,
    *,
    application_id: str,
    creator_profile_id: str | None = None,
    repo: EmailDeliveryRepository | None = None,
    resend_client: Any | None = None,
) -> None:
    idempotency_key = f"revision-requested:{application_id}:{revision_notes[:32]}"
    await send_email(
        flow=EmailFlow.REVISION_REQUESTED,
        recipient_email=email,
        subject=f"Revision requested on {campaign_title}",
        template_data={
            "creator_name": creator_name,
            "campaign_title": campaign_title,
            "business_name": business_name,
            "revision_notes": revision_notes,
            "review_url": review_url,
        },
        idempotency_key=idempotency_key,
        recipient_profile_id=creator_profile_id,
        repo=repo,
        resend_client=resend_client,
    )


async def send_invoice_email(
    email: str,
    recipient_name: str,
    sender_name: str,
    invoice_number: str,
    amount_formatted: str,
    status: str,
    view_url: str,
    *,
    invoice_id: str,
    recipient_profile_id: str | None = None,
    repo: EmailDeliveryRepository | None = None,
    resend_client: Any | None = None,
) -> None:
    idempotency_key = f"invoice:{invoice_id}:{status}"
    await send_email(
        flow=EmailFlow.INVOICE,
        recipient_email=email,
        subject=f"Invoice {invoice_number} from {sender_name}",
        template_data={
            "recipient_name": recipient_name,
            "sender_name": sender_name,
            "invoice_number": invoice_number,
            "amount_formatted": amount_formatted,
            "status": status,
            "view_url": view_url,
        },
        idempotency_key=idempotency_key,
        recipient_profile_id=recipient_profile_id,
        repo=repo,
        resend_client=resend_client,
    )


async def handle_resend_webhook(
    payload: dict[str, Any],
    *,
    repo: EmailDeliveryRepository | None = None,
) -> dict[str, Any]:
    """Process incoming Resend webhook delivery status events."""
    repo = repo or EmailDeliveryRepository()
    event_type = payload.get("type")
    data = payload.get("data", {})
    email_id = data.get("email_id") or data.get("id")

    if not email_id:
        return {"status": "ignored", "reason": "no_email_id"}

    record = await repo.get_by_resend_id(email_id)
    if not record:
        return {"status": "ignored", "reason": "record_not_found"}

    new_status = None
    if event_type == "email.delivered":
        new_status = EmailDeliveryStatus.DELIVERED
    elif event_type == "email.bounced":
        new_status = EmailDeliveryStatus.BOUNCED
    elif event_type == "email.complained":
        new_status = EmailDeliveryStatus.COMPLAINED

    if new_status:
        await repo.update_delivery(record.id, {"status": new_status.value})
        logger.info("Updated email delivery status to %s for resend_id=%s", new_status.value, email_id)
        return {"status": "updated", "delivery_status": new_status.value}

    return {"status": "received"}
