"""
Unit tests for app.core.plans — pure logic, no repos, no network.

These deliberately assert *behaviour* (who is entitled to what) rather than
the specific placeholder quota numbers, so that setting real prices later
doesn't require rewriting the suite. The one place a number is asserted is
where the number itself encodes a rule (free is limited, pro is not).
"""

from datetime import UTC, datetime

from app.core.plans import (
    PLAN_LIMITS,
    BusinessPlan,
    SubscriptionStatus,
    is_within_limit,
    limits_for,
    month_start,
    resolve_plan,
)


def test_free_plan_resolves_to_free_regardless_of_status():
    for status in SubscriptionStatus:
        assert resolve_plan("free", status.value) is BusinessPlan.FREE


def test_paid_plan_requires_an_entitling_status():
    assert resolve_plan("pro", "active") is BusinessPlan.PRO
    assert resolve_plan("pro", "trialing") is BusinessPlan.PRO


def test_past_due_keeps_access():
    """A failed card must not instantly revoke a paying customer mid-campaign.

    Gateways retry for days; cutting access on the first failure would
    strand live collaborations over what is usually an expired card. Access
    ends when the gateway gives up and the status becomes canceled.
    """
    assert resolve_plan("pro", "past_due") is BusinessPlan.PRO


def test_canceled_paid_plan_falls_back_to_free():
    """The `plan` column is not self-cleaning — a cancellation webhook may
    update status and leave plan='pro' behind. Resolving from both columns
    is what stops that stale value granting unlimited access forever."""
    assert resolve_plan("pro", "canceled") is BusinessPlan.FREE
    assert resolve_plan("pro", "none") is BusinessPlan.FREE


def test_unknown_values_degrade_to_free_rather_than_raising():
    """An unrecognised plan/status (a gateway sending something new, a typo
    in a manual DB edit) must fail closed to the least-privileged tier —
    never grant more access, and never 500 an endpoint."""
    assert resolve_plan("enterprise_v2", "active") is BusinessPlan.FREE
    assert resolve_plan("pro", "some_new_gateway_status") is BusinessPlan.FREE
    assert resolve_plan(None, None) is BusinessPlan.FREE


def test_free_gets_three_campaigns_a_month_and_pro_is_unlimited():
    """The number is asserted here because it's the actual product promise
    made to brands ("3 campaigns per month free"), not an internal detail —
    changing it should require deliberately changing this test."""
    assert PLAN_LIMITS[BusinessPlan.FREE].max_campaigns_per_month == 3
    assert PLAN_LIMITS[BusinessPlan.PRO].max_campaigns_per_month is None


def test_free_gets_one_creator_per_campaign_and_pro_is_unlimited():
    """Same reasoning as the campaign-count test above — this is the actual
    product promise ("1 creator per campaign on the free plan"), asserted
    directly so changing it is a deliberate act, not a side effect."""
    assert PLAN_LIMITS[BusinessPlan.FREE].max_creators_per_campaign == 1
    assert PLAN_LIMITS[BusinessPlan.PRO].max_creators_per_campaign is None


def test_expired_manual_subscription_lapses_to_free():
    """The safety net for manual activation: subscriptions are switched on
    by a human, and humans forget to switch them off. An expiry in the past
    must revoke entitlement without anyone doing anything."""
    past = datetime(2026, 1, 1, tzinfo=UTC)
    now = datetime(2026, 8, 29, tzinfo=UTC)

    assert resolve_plan("pro", "active", past, now=now) is BusinessPlan.FREE


def test_unexpired_manual_subscription_still_entitles():
    future = datetime(2026, 12, 1, tzinfo=UTC)
    now = datetime(2026, 8, 29, tzinfo=UTC)

    assert resolve_plan("pro", "active", future, now=now) is BusinessPlan.PRO


def test_no_expiry_means_open_ended():
    """NULL expiry is a valid, deliberate choice — a manual subscription
    that runs until someone turns it off. It must not be read as
    'expired'."""
    assert resolve_plan("pro", "active", None) is BusinessPlan.PRO


def test_naive_expiry_does_not_crash_the_entitlement_check():
    """A hand-edited row or a test fake can produce a naive datetime.
    Comparing naive to aware raises TypeError — inside an entitlement check
    that would 500 campaign creation, so it's coerced instead."""
    naive_future = datetime(2026, 12, 1)  # noqa: DTZ001 — the point of the test
    now = datetime(2026, 8, 29, tzinfo=UTC)

    assert resolve_plan("pro", "active", naive_future, now=now) is BusinessPlan.PRO


def test_month_start_is_the_first_at_midnight():
    assert month_start(datetime(2026, 8, 29, 17, 45, tzinfo=UTC)) == datetime(
        2026, 8, 1, tzinfo=UTC
    )


def test_limits_for_matches_resolved_plan():
    assert limits_for("pro", "active") == PLAN_LIMITS[BusinessPlan.PRO]
    assert limits_for("pro", "canceled") == PLAN_LIMITS[BusinessPlan.FREE]


def test_is_within_limit_treats_none_as_unlimited_not_zero():
    """The trap this helper exists to prevent: `if limit and current < limit`
    reads None as falsy (deny — backwards) and 0 as falsy (allow —
    backwards). Both directions are asserted."""
    assert is_within_limit(9999, None) is True
    assert is_within_limit(0, 0) is False
    assert is_within_limit(0, 1) is True
    assert is_within_limit(1, 1) is False
