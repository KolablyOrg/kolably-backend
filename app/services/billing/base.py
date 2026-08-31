"""
The contract every payment gateway adapter must satisfy, plus the
normalised event shape everything downstream is written against.

The point of this file: Razorpay and Stripe disagree about almost
everything — event names, payload shape, id prefixes, how a signature is
computed, whether a period end is a unix timestamp or an ISO string. None
of that should leak into `subscription_service`, the entitlement rules, or
the campaign gate. An adapter's job is to turn a gateway's webhook into a
`SubscriptionEvent` and nothing more.

Written before the gateway decision on purpose. The decision (Razorpay vs
Stripe) is still open and blocked on a live account existing — but the
translation target doesn't depend on which one wins, so it can be built,
reviewed, and tested now.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable


class SubscriptionEventType(StrEnum):
    """Normalised event vocabulary.

    Deliberately small. Gateways emit dozens of event types; only these
    change entitlement, and mapping the rest to "ignore" in the adapter is
    both easier to review and safer than handling everything generically.
    """

    # Subscription became (or remains) paid and entitled.
    ACTIVATED = "activated"
    # Payment failed; gateway is retrying. Still entitled — see
    # plans.ENTITLED_STATUSES for why.
    PAYMENT_FAILED = "payment_failed"
    # Gateway gave up, or the user cancelled immediately. Entitlement ends.
    CANCELED = "canceled"
    # Cancelled but paid through to period end. Still entitled until then.
    SCHEDULED_FOR_CANCELLATION = "scheduled_for_cancellation"
    # Trial started.
    TRIAL_STARTED = "trial_started"


@dataclass(frozen=True)
class SubscriptionEvent:
    """One gateway webhook, translated.

    Frozen because an event is a record of something that already happened;
    nothing downstream should be rewriting it.
    """

    type: SubscriptionEventType

    # The gateway's own subscription id. This — not our business id — is
    # what webhooks are keyed by, which is why it has a unique index on
    # `businesses`. An adapter that can't supply this can't be handled.
    provider_subscription_id: str

    # Which gateway this came from. Stored on the business so a later
    # gateway change can't silently reinterpret ids from the old one.
    provider: str

    # The gateway's customer id, when the event carries one. Optional
    # because not every event type includes it.
    provider_customer_id: str | None = None

    # Which tier this subscription grants. The adapter maps the gateway's
    # plan/price id onto our own plan name — that mapping is gateway
    # config, not business logic, so it belongs in the adapter.
    plan: str | None = None

    # End of the paid period, as a timezone-aware datetime. Adapters MUST
    # normalise here (Stripe sends unix seconds, Razorpay sends unix
    # seconds too but on different fields) so nothing downstream has to
    # know the difference.
    current_period_end: datetime | None = None

    # The gateway's own event id, for idempotency. Gateways retry webhooks
    # — the same event WILL arrive more than once, and processing a
    # cancellation twice must not differ from processing it once.
    provider_event_id: str | None = None


@runtime_checkable
class BillingGateway(Protocol):
    """What a concrete adapter (razorpay.py / stripe.py) must implement.

    A Protocol rather than an ABC so an adapter doesn't have to import from
    here to satisfy it, and so tests can pass a plain fake without
    inheritance. `runtime_checkable` allows an isinstance assertion in a
    test, though note that only checks method presence, not signatures.
    """

    #: Value stored in `businesses.billing_provider`. Must be one of the
    #: values allowed by that column's CHECK constraint.
    provider_name: str

    def verify_webhook(self, *, payload: bytes, signature: str) -> bool:
        """Verify the request genuinely came from the gateway.

        Takes raw bytes, not a parsed dict: every gateway signs the exact
        body, and re-serialising a parsed payload changes the bytes and
        breaks verification. The route must therefore read the raw body.

        MUST use a constant-time comparison. A webhook endpoint that
        accepts unverified payloads is a way for anyone to grant themselves
        a paid plan.
        """
        ...

    def parse_event(self, payload: dict) -> SubscriptionEvent | None:
        """Translate a verified webhook into a `SubscriptionEvent`.

        Returns None for events that don't affect entitlement — which is
        most of them. Returning None must be the default for anything
        unrecognised, so a new gateway event type can never be
        accidentally interpreted as an entitlement change.
        """
        ...

    async def create_checkout(
        self, *, business_id: str, plan: str, customer_email: str
    ) -> str:
        """Start a subscription and return a URL to send the user to.

        Returns a URL rather than a client secret / order object so the
        same interface covers a hosted checkout page (Razorpay's and
        Stripe's default) without the caller knowing which.
        """
        ...

    async def cancel_subscription(self, *, provider_subscription_id: str) -> None:
        """Cancel at period end (not immediately).

        At-period-end is the deliberate default: the customer paid for the
        period, and cutting access the moment they click cancel would
        strand live campaigns. `cancel_at_period_end` on the business row
        exists to represent exactly this state.
        """
        ...
