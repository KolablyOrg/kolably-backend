"""
Applies normalised subscription events to a business.

This is the whole of the "what happens when billing state changes" logic,
and it is deliberately gateway-agnostic: it takes a `SubscriptionEvent`
(see app/services/billing/base.py) and never sees a raw webhook. That means
it is fully built and testable today, before the Razorpay-vs-Stripe
decision is made — and when an adapter arrives, none of this changes.

Adding a gateway is: one adapter file + one webhook route that verifies the
signature, parses the event, and calls `apply_subscription_event`.
"""

import logging

from app.core import plans
from app.models.business import Business
from app.repositories.business_repo import BusinessRepository
from app.services.billing.base import SubscriptionEvent, SubscriptionEventType

logger = logging.getLogger(__name__)


# How each normalised event maps onto the stored subscription status.
# A table rather than an if-chain so the full mapping is visible at once —
# an event silently falling through to "no change" is the failure mode that
# matters here, and a dict makes a missing entry obvious.
_STATUS_BY_EVENT: dict[SubscriptionEventType, plans.SubscriptionStatus] = {
    SubscriptionEventType.ACTIVATED: plans.SubscriptionStatus.ACTIVE,
    SubscriptionEventType.TRIAL_STARTED: plans.SubscriptionStatus.TRIALING,
    SubscriptionEventType.PAYMENT_FAILED: plans.SubscriptionStatus.PAST_DUE,
    SubscriptionEventType.CANCELED: plans.SubscriptionStatus.CANCELED,
    # Still paid up: the status stays whatever it was, and only
    # cancel_at_period_end flips. Handled explicitly below rather than here,
    # because this is the one event that must NOT overwrite status.
}


async def apply_subscription_event(
    event: SubscriptionEvent,
    *,
    repo: BusinessRepository | None = None,
) -> Business | None:
    """Update the business this event belongs to. Returns None if no
    business matches (which is normal and not an error — see below).

    Idempotent by construction: every branch writes an absolute state, not
    a delta. Gateways retry webhooks, so the same cancellation WILL arrive
    twice, and the second one must be a no-op rather than compounding.
    """
    repo = repo or BusinessRepository()

    business = await repo.get_by_billing_subscription_id(event.provider_subscription_id)
    if not business:
        # Not an error worth raising: a webhook can legitimately arrive for
        # a subscription belonging to another environment (test vs live
        # keys pointed at the same endpoint), or before our own record was
        # written. Log and acknowledge — returning a 5xx would make the
        # gateway retry forever on something that will never resolve.
        logger.warning(
            "Subscription event %s for unknown subscription_id=%s (provider=%s) — ignoring",
            event.type.value,
            event.provider_subscription_id,
            event.provider,
        )
        return None

    update: dict = {
        "billing_provider": event.provider,
    }

    if event.provider_customer_id:
        update["billing_customer_id"] = event.provider_customer_id
    if event.current_period_end:
        update["current_period_end"] = event.current_period_end.isoformat()

    if event.type is SubscriptionEventType.SCHEDULED_FOR_CANCELLATION:
        # Deliberately does NOT touch subscription_status. The customer has
        # paid through the end of the period and stays entitled until then;
        # writing 'canceled' here would revoke access they've already paid
        # for. The actual revocation arrives later as a CANCELED event.
        update["cancel_at_period_end"] = True
    else:
        status = _STATUS_BY_EVENT.get(event.type)
        if status is None:
            # Unmapped event type. Adapters are supposed to return None for
            # anything that doesn't affect entitlement, so reaching here
            # means the vocabulary grew without this table being updated.
            logger.error(
                "No status mapping for subscription event type %r — business %s left unchanged",
                event.type,
                business.id,
            )
            return business

        update["subscription_status"] = status.value

        # A fresh activation clears any pending cancellation — this is how
        # "I cancelled then changed my mind" resolves.
        if event.type in (
            SubscriptionEventType.ACTIVATED,
            SubscriptionEventType.TRIAL_STARTED,
        ):
            update["cancel_at_period_end"] = False
            if event.plan:
                update["plan"] = event.plan

        # On cancellation, `plan` is deliberately left as-is rather than
        # reset to 'free'. Entitlement already resolves to free via
        # plans.resolve_plan (status is canceled), and keeping the last
        # paid tier on the row preserves "what were they on?" for support
        # and for a re-subscribe flow. Resetting it would destroy that with
        # no benefit.

    updated = await repo.update_business(business.id, update)
    if not updated:
        logger.error(
            "Failed to persist subscription event %s for business %s",
            event.type.value,
            business.id,
        )
    return updated


async def link_subscription_to_business(
    business_id: str,
    *,
    provider: str,
    provider_customer_id: str,
    provider_subscription_id: str,
    repo: BusinessRepository | None = None,
) -> Business | None:
    """Record the gateway ids on a business at checkout time.

    Separate from `apply_subscription_event` because it happens on our side
    of the flow (we know the business id) whereas webhooks arrive keyed by
    the gateway's id and have to look the business up. Calling this at
    checkout is what makes that later lookup possible — a subscription
    created without it will produce "unknown subscription_id" warnings for
    every subsequent webhook.

    Does NOT set plan or status: entitlement is granted by the webhook that
    confirms payment, never by the act of starting a checkout. Otherwise an
    abandoned checkout would hand out a free paid plan.
    """
    repo = repo or BusinessRepository()
    return await repo.update_business(
        business_id,
        {
            "billing_provider": provider,
            "billing_customer_id": provider_customer_id,
            "billing_subscription_id": provider_subscription_id,
        },
    )
