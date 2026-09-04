# Brand subscriptions — how it works today, and what changes later

**Model as of 2026-08-29: manual subscriptions, no payment gateway.**

A payment gateway needs GST registration, which isn't in place. Rather than
block the feature on that, subscriptions are activated by hand:

1. Every brand starts on **free — 3 campaigns per calendar month**.
2. A brand pays **offline** (bank transfer / UPI, however you arrange it).
3. A superadmin calls `PATCH /businesses/{id}/plan` to set them to **pro**.
4. Pro = **unlimited campaigns**. That is the only thing it unlocks.

No free trial. No self-serve checkout. No gateway.

---

## Activating a subscription

```
PATCH /api/v1/businesses/{business_id}/plan     (superadmin only)

{ "plan": "pro",
  "expires_at": "2026-09-30T00:00:00Z",
  "note": "₹X by UPI on 29 Aug, ref 12345" }
```

**Set `expires_at`.** It's optional, but it's the safety net for a manual
process: without it the subscription runs until someone remembers to switch
it off, and an unpaid brand quietly keeps unlimited campaigns. With it,
entitlement lapses on its own — worst case is a paying brand needing
re-activation, rather than a non-paying one keeping access.

Deactivating:

```
{ "plan": "free" }
```

`note` goes to the application log (greppable, `"Business plan set
manually"`). There's no billing-audit table yet — not worth one for a
handful of manual activations.

**Brands cannot change their own plan.** `plan` is deliberately absent from
`BusinessUpdateRequest`, and the endpoint is superadmin-only. A brand able
to set its own plan is the whole feature bypassed in one request.

---

## How the quota works

- Counted from `campaigns.created_at` within the **current calendar
  month**. No usage table — the campaign rows are the counter.
- Calendar month, not rolling 30 days: a brand told "3 per month" who used
  theirs on the 28th expects a reset on the 1st, not on the 27th.
- **Every created campaign counts**, including drafts and ones since
  closed. The quota is on the act of creating.
- Over quota returns **402 Payment Required**, not 403 — the client should
  show an upgrade prompt, not an access error.
- **Known gap:** deleting a campaign frees its slot, so create → delete →
  create can exceed the allowance. Accepted for now — activation is manual
  and the customer base is small enough to notice. Revisit if self-serve
  billing ships.

---

## What a brand actually sees

**Before hitting the limit** — `GET /businesses/me/stats` now returns
`campaigns_used_this_month`, `campaigns_limit_this_month` (null = unlimited)
and `effective_plan`, so the UI can show "1 of 3 left this month". Being
blocked with no prior warning is what generates support tickets.

**On hitting it** — campaign creation returns 402 and both apps show a
dedicated upgrade prompt instead of the usual error toast:

- **Web** (`CampaignWizard`): a full panel — "You've used this month's
  campaigns" — with *Back to campaign* and *Contact us to upgrade*. Entered
  details are preserved; going back returns them to the wizard intact.
- **Mobile** (`business-campaign-create`): a native alert with the same two
  choices. Falls back to showing the support address as a toast if no mail
  client is configured.

Both read the message from the server's 402 body rather than restating the
number client-side, so the copy can't drift from `plans.py`.

The CTA is an email, not a checkout link — there is no self-serve payment
page, and linking to one that doesn't exist would be worse than an honest
mailto. Shared helpers: `src/lib/support.ts`, `mobile/utils/support.ts`.

⚠️ Those two files hardcode **different** support addresses
(`info@kolably.com` on web, `support@kolably.com` on mobile). That
inconsistency predates this work; it's now in one place per app, so it's a
one-line fix once someone decides which is correct.

---

## What clients should read

`GET /businesses/{id}` (and the business object on `/auth/me`) now returns:

| Field | Use |
|---|---|
| `effective_plan` | **Gate UI on this.** Resolved from plan + status + expiry. |
| `plan` | What they signed up for. Can disagree with reality. |
| `subscription_status` | Billing lifecycle state. |
| `current_period_end` | When access lapses. NULL = open-ended. |

`plan` and `effective_plan` legitimately differ: an expired or cancelled
`pro` row still reads `plan: "pro"` but `effective_plan: "free"`.

---

## Where it's implemented

| Piece | File |
|---|---|
| Tiers, quotas, entitlement rules | `app/core/plans.py` |
| Manual activation | `business_service.set_business_plan` |
| Quota enforcement | `campaign_service._assert_campaign_quota_available` |
| Monthly count | `campaign_repo.count_created_since` |
| Schema | `migrations/20260829160000_add_business_subscription.sql` |

Tests: `tests/test_plans.py`, plus the plan-gate tests in
`tests/test_campaign_service.py`.

---

## When a gateway is eventually added

The schema and the state machine are already gateway-shaped, so this stays
additive rather than a rewrite:

- `app/services/billing/base.py` — the adapter contract and a normalised
  `SubscriptionEvent`. Written, unused.
- `app/services/subscription_service.py` — applies those events to a
  business (activation, payment failure, cancel-at-period-end,
  reactivation, replayed webhooks). Written and tested, unused.
- `businesses.billing_provider` already distinguishes `'manual'` from a
  gateway, so manually-granted subscriptions can't be clobbered by a
  webhook.

Remaining then: one adapter file, a checkout route, a
signature-verified webhook route, and billing UI.

**Before any of that, the team still needs to settle:** GST registration,
the actual price, and — if annual billing is considered — that RBI's
e-mandate rules require the customer to re-authenticate every debit above
₹15,000, which would stop annual renewals being silent.
