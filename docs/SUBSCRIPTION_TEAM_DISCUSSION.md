# Brand subscriptions — decided, and still open

Updated 2026-08-29 after the team discussion. Most of the original question
list is now answered; this records the decisions so they aren't relitigated,
and keeps the genuinely open ones visible.

---

## Decided — and built

| Decision | Detail |
|---|---|
| **No payment gateway for now** | Blocked on GST registration. Payment is taken offline. |
| **Manual activation** | Superadmin flips a brand to pro via `PATCH /businesses/{id}/plan`. |
| **Two tiers** | `free` and `pro`. |
| **Free allowance** | **3 campaigns per calendar month**, for everyone. |
| **Pro unlocks** | **Unlimited campaigns** — and nothing else, deliberately. |
| **No free trial** | Everyone gets the same 3/month. |

All of this is implemented and tested. See `docs/SUBSCRIPTION_GO_LIVE.md`
for how to operate it.

---

## Still open — decide before charging anyone

1. **What's the price, and for how long does one payment grant access?**
   The endpoint takes an `expires_at`; whoever activates a subscription
   needs to know what date to put in.
2. **GST registration** — the thing actually blocking a gateway. Any
   timeline?
3. **Who has superadmin access** to activate subscriptions, and where do we
   record what was paid? Right now the `note` field goes to the application
   log only; there's no billing table.
4. **What do we tell brands when they hit the limit?** The API returns a
   402 with "You've used all 3 campaigns included this month… upgrade for
   unlimited." Someone should own that copy, and the upgrade path is
   currently "contact us" — is that a form, an email, a WhatsApp number?
5. **Existing brands** — anyone to put on pro at launch? Anyone who'd be
   blocked immediately by the new limit, and do we warn them first?

---

## Open, but only when a gateway is on the table

6. **Razorpay vs Stripe.** Razorpay keys already sit unused in our config,
   we price in ₹, and it supports UPI Autopay — it's the obvious fit for an
   India-only launch, but nobody has formally decided.
7. **Monthly vs annual pricing.** ⚠️ Under RBI's e-mandate framework
   (notified 21 Apr 2026), recurring auto-debits above **₹15,000 per
   transaction** require the customer to re-authenticate *every time*. The
   ₹1,00,000 exemption covers insurance, mutual funds and credit-card
   bills — not SaaS. A monthly plan is almost certainly under the ceiling;
   an annual one may not be, which would stop renewals being silent. Worth
   knowing before annual pricing is announced.
8. **Who issues the GST invoice** — the gateway, or us? We already have an
   invoice generator for creator↔brand invoices, but a subscription invoice
   is a different document with different requirements. Confirm the
   treatment with the CA rather than inferring it.
9. **Failed payments** — retry policy and who chases. Currently a failed
   payment keeps access while retries happen and only ends at cancellation,
   so a live campaign isn't stranded by an expired card.
