"""
Unit tests for subscription_service — repository injected as a fake, no
gateway, no network.

These exist specifically so the billing state machine is proven correct
*before* a gateway is chosen. When an adapter is added, none of this should
need to change: the adapter's job ends at producing a SubscriptionEvent.
"""

from datetime import UTC, datetime

import pytest

from app.models.business import Business
from app.services import subscription_service
from app.services.billing.base import SubscriptionEvent, SubscriptionEventType

BUSINESS_ROW = {
    "id": "b1",
    "profile_id": "p-business",
    "business_name": "Acme Co",
    "city": "Mumbai",
    "category": "food",
    "created_at": "2024-01-01T00:00:00+00:00",
    "plan": "free",
    "subscription_status": "none",
    "billing_subscription_id": "sub_live_123",
}


class FakeBusinessRepo:
    def __init__(self, row=None):
        self._row = row if row is not None else dict(BUSINESS_ROW)
        self.updated_with = None

    async def get_by_billing_subscription_id(self, provider_subscription_id: str):
        if not self._row:
            return None
        if self._row.get("billing_subscription_id") != provider_subscription_id:
            return None
        return Business.from_row(self._row)

    async def update_business(self, business_id: str, data: dict):
        self.updated_with = data
        self._row = {**self._row, **data}
        return Business.from_row(self._row)


def _event(event_type: SubscriptionEventType, **overrides) -> SubscriptionEvent:
    return SubscriptionEvent(
        type=event_type,
        provider_subscription_id=overrides.pop("provider_subscription_id", "sub_live_123"),
        provider=overrides.pop("provider", "razorpay"),
        **overrides,
    )


async def test_activation_sets_plan_and_status():
    repo = FakeBusinessRepo()

    result = await subscription_service.apply_subscription_event(
        _event(
            SubscriptionEventType.ACTIVATED,
            plan="pro",
            provider_customer_id="cust_1",
            current_period_end=datetime(2026, 12, 1, tzinfo=UTC),
        ),
        repo=repo,
    )

    assert repo.updated_with["plan"] == "pro"
    assert repo.updated_with["subscription_status"] == "active"
    assert repo.updated_with["billing_customer_id"] == "cust_1"
    assert repo.updated_with["billing_provider"] == "razorpay"
    # Normalised to a string before write, per the isoformat-before-insert
    # convention every service in this codebase follows.
    assert isinstance(repo.updated_with["current_period_end"], str)
    assert result.subscription_status == "active"


async def test_payment_failure_does_not_revoke_access():
    """A failed card must leave the customer entitled while the gateway
    retries — see plans.ENTITLED_STATUSES. Writing 'canceled' here would
    strand live campaigns over an expired card."""
    repo = FakeBusinessRepo({**BUSINESS_ROW, "plan": "pro", "subscription_status": "active"})

    await subscription_service.apply_subscription_event(
        _event(SubscriptionEventType.PAYMENT_FAILED), repo=repo
    )

    assert repo.updated_with["subscription_status"] == "past_due"
    # plan untouched — entitlement is still derived as 'pro'
    assert "plan" not in repo.updated_with


async def test_scheduled_cancellation_keeps_status_and_only_flags_the_flip():
    """The trap this guards: writing status='canceled' on a
    cancel-at-period-end event would revoke access the customer has already
    paid for. Only the flag moves; the real revocation arrives later."""
    repo = FakeBusinessRepo({**BUSINESS_ROW, "plan": "pro", "subscription_status": "active"})

    await subscription_service.apply_subscription_event(
        _event(SubscriptionEventType.SCHEDULED_FOR_CANCELLATION), repo=repo
    )

    assert repo.updated_with["cancel_at_period_end"] is True
    assert "subscription_status" not in repo.updated_with


async def test_cancellation_keeps_last_paid_plan_on_the_row():
    """`plan` is deliberately not reset to 'free': entitlement already
    resolves to free from the status, and keeping the last paid tier
    preserves 'what were they on?' for support and re-subscribe."""
    repo = FakeBusinessRepo({**BUSINESS_ROW, "plan": "pro", "subscription_status": "active"})

    await subscription_service.apply_subscription_event(
        _event(SubscriptionEventType.CANCELED), repo=repo
    )

    assert repo.updated_with["subscription_status"] == "canceled"
    assert "plan" not in repo.updated_with


async def test_reactivation_clears_a_pending_cancellation():
    """"I cancelled, then changed my mind" — without this the row would
    stay flagged for cancellation while active."""
    repo = FakeBusinessRepo(
        {**BUSINESS_ROW, "plan": "pro", "subscription_status": "active", "cancel_at_period_end": True}
    )

    await subscription_service.apply_subscription_event(
        _event(SubscriptionEventType.ACTIVATED, plan="pro"), repo=repo
    )

    assert repo.updated_with["cancel_at_period_end"] is False


async def test_replaying_the_same_event_is_a_no_op():
    """Gateways retry webhooks; the same event WILL arrive more than once.
    Every branch writes absolute state rather than a delta, so a replay
    must land on the identical row."""
    repo = FakeBusinessRepo()
    event = _event(SubscriptionEventType.ACTIVATED, plan="pro")

    first = await subscription_service.apply_subscription_event(event, repo=repo)
    after_first = repo.updated_with
    second = await subscription_service.apply_subscription_event(event, repo=repo)

    assert after_first == repo.updated_with
    assert first.plan == second.plan
    assert first.subscription_status == second.subscription_status


async def test_unknown_subscription_id_is_ignored_not_raised():
    """A webhook for a subscription we don't know about (test-vs-live keys
    hitting the same endpoint, or an event arriving before our own record)
    must be acknowledged, not 5xx'd — otherwise the gateway retries forever
    on something that will never resolve."""
    repo = FakeBusinessRepo()

    result = await subscription_service.apply_subscription_event(
        _event(SubscriptionEventType.CANCELED, provider_subscription_id="sub_unknown"),
        repo=repo,
    )

    assert result is None
    assert repo.updated_with is None


async def test_link_subscription_does_not_grant_a_plan():
    """Checkout started is not payment received. Granting entitlement here
    would hand a free paid plan to anyone who abandons a checkout."""
    repo = FakeBusinessRepo()

    await subscription_service.link_subscription_to_business(
        "b1",
        provider="razorpay",
        provider_customer_id="cust_1",
        provider_subscription_id="sub_new",
        repo=repo,
    )

    assert repo.updated_with["billing_subscription_id"] == "sub_new"
    assert "plan" not in repo.updated_with
    assert "subscription_status" not in repo.updated_with


@pytest.mark.parametrize("event_type", list(SubscriptionEventType))
async def test_every_event_type_is_handled(event_type):
    """Guards the gap between the event vocabulary and the status mapping
    table: adding a SubscriptionEventType without mapping it would
    otherwise silently leave businesses unchanged, with only a log line."""
    repo = FakeBusinessRepo()

    await subscription_service.apply_subscription_event(_event(event_type), repo=repo)

    assert repo.updated_with is not None, f"{event_type} produced no write"
    assert (
        "subscription_status" in repo.updated_with
        or "cancel_at_period_end" in repo.updated_with
    ), f"{event_type} changed no entitlement-relevant field"
