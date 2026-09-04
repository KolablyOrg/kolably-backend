"""
Brand subscription plans: tiers, quotas, and entitlement checks.

## Current model (2026-08-29): manual subscriptions, no payment gateway

There is no payment integration and deliberately so — a payment gateway
needs GST registration, which isn't in place yet. Until then:

  * Every brand starts on FREE: **3 campaigns per calendar month**, and
    each campaign can include **at most 1 creator**.
  * Payment is taken offline. A superadmin then flips the business to PRO
    via `PATCH /businesses/{id}/plan`, which records
    `billing_provider='manual'`.
  * PRO unlocks **unlimited campaigns** and **unlimited creators per
    campaign**. Those are the only two things it unlocks right now — no
    other feature is gated, on purpose.

The numbers here are real, not placeholders. When a gateway is eventually
added, none of this changes: an adapter writes the same `plan` /
`subscription_status` columns the manual toggle writes today.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class BusinessPlan(StrEnum):
    FREE = "free"
    PRO = "pro"


class SubscriptionStatus(StrEnum):
    NONE = "none"
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


# Statuses that still entitle a business to its paid plan.
#
# TRIALING is retained even though there is no trial today — a status a
# gateway can send must still resolve sanely if one ever arrives, and
# removing it would make an unexpected value silently downgrade a paying
# customer. PAST_DUE is entitled because a failed payment should not
# revoke access mid-campaign while retries are still happening.
ENTITLED_STATUSES = frozenset({
    SubscriptionStatus.TRIALING,
    SubscriptionStatus.ACTIVE,
    SubscriptionStatus.PAST_DUE,
})


@dataclass(frozen=True)
class PlanLimits:
    """Per-plan quotas. `None` means unlimited, NOT zero — the distinction
    matters because 0 is a legitimate quota and a falsy check would treat
    unlimited and none-allowed identically."""

    # Campaigns a business may CREATE per calendar month. Counted from
    # campaigns.created_at, so no usage table is needed — the campaign rows
    # are the counter.
    max_campaigns_per_month: int | None

    # Creators a single campaign may accept (campaigns.max_creators).
    # Enforced wherever max_creators is written — see
    # campaign_service._assert_max_creators_allowed — not just at creation,
    # since a free brand could otherwise raise it later via a plain edit.
    max_creators_per_campaign: int | None


PLAN_LIMITS: dict[BusinessPlan, PlanLimits] = {
    BusinessPlan.FREE: PlanLimits(max_campaigns_per_month=3, max_creators_per_campaign=1),
    BusinessPlan.PRO: PlanLimits(max_campaigns_per_month=None, max_creators_per_campaign=None),
}


def month_start(now: datetime | None = None) -> datetime:
    """Start of the current calendar month, UTC.

    Calendar month, not a rolling 30-day window: "3 campaigns a month" is
    what brands are told, and a rolling window would mean a brand who used
    their 3 on the 28th is still blocked on the 5th of the next month —
    which reads as broken even though it's arithmetically defensible.
    """
    reference = now or datetime.now(UTC)
    return reference.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def resolve_plan(
    plan: str | None,
    subscription_status: str | None,
    current_period_end: datetime | None = None,
    *,
    now: datetime | None = None,
) -> BusinessPlan:
    """The plan a business is actually entitled to right now.

    Reads all three columns, not just `plan`:

    * `subscription_status` — a row left at plan='pro' after cancellation
      must fall back to free rather than granting access forever.
    * `current_period_end` — for MANUAL subscriptions this is the safety
      net. Access is granted by a human flipping a switch, and humans
      forget to flip it back; an expiry date means an unpaid brand lapses
      on its own instead of keeping PRO indefinitely. NULL means
      open-ended (pure manual on/off), which is a deliberate, valid choice
      — it just has to be turned off by hand.

    Unknown values fall back to FREE rather than raising: an unrecognised
    plan string should degrade to the least-privileged tier, never grant
    more or take an endpoint down.
    """
    try:
        parsed_plan = BusinessPlan(plan) if plan else BusinessPlan.FREE
    except ValueError:
        return BusinessPlan.FREE

    if parsed_plan is BusinessPlan.FREE:
        return BusinessPlan.FREE

    try:
        parsed_status = (
            SubscriptionStatus(subscription_status) if subscription_status else SubscriptionStatus.NONE
        )
    except ValueError:
        return BusinessPlan.FREE

    if parsed_status not in ENTITLED_STATUSES:
        return BusinessPlan.FREE

    if current_period_end is not None:
        reference = now or datetime.now(UTC)
        # Rows read back from Postgres are tz-aware; be defensive about a
        # naive value arriving from a fake or a hand-edited row rather than
        # raising a comparison TypeError inside an entitlement check.
        if current_period_end.tzinfo is None:
            current_period_end = current_period_end.replace(tzinfo=UTC)
        if current_period_end <= reference:
            return BusinessPlan.FREE

    return parsed_plan


def limits_for(
    plan: str | None,
    subscription_status: str | None,
    current_period_end: datetime | None = None,
    *,
    now: datetime | None = None,
) -> PlanLimits:
    return PLAN_LIMITS[resolve_plan(plan, subscription_status, current_period_end, now=now)]


def is_within_limit(current: int, limit: int | None) -> bool:
    """`limit is None` means unlimited. Kept as a named function so call
    sites can't accidentally write `if limit and current < limit`, which
    would treat unlimited (None) as "deny" and a zero quota as "allow" —
    both backwards."""
    return limit is None or current < limit
