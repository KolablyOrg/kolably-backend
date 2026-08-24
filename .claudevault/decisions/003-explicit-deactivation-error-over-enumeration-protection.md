# 003 — Password reset explicitly errors on a deactivated account, trading away anti-enumeration protection for that one case

parent:: [[context]]
date:: 2026-08-24
status:: accepted

## Context
The #31 fix (deactivated accounts could still get a working password-reset
email) was originally built to stay **silent**: a deactivated account got
the exact same generic success response as an active account or a
nonexistent email, and the actual Supabase send was just skipped
underneath. This was deliberate anti-enumeration design — matching the
same non-leaking shape already used elsewhere in this file
(`resend_verification_email`, the "unknown email" case of this same
function) — so that no response alone could tell an attacker whether a
given email belongs to a deactivated account, an active account, or no
account at all.

In practice this meant: someone testing their own deactivated account got
sent to the OTP entry screen exactly as if a code had been sent — except no
code was ever actually generated, so the screen could never succeed, with
nothing telling them why. The user hit this directly, reported "still not
fixed" (reasonably, since nothing about the *experience* had changed), and
was explicit about the tradeoff they wanted:

> "the api should return error message or something and not let me go to
> OTP screen"

## Decision
`forgot_password` now raises an explicit `403` for a deactivated account —
"This Brand/Creator account has been deactivated", same role-aware wording
`login`/`google_auth` already use for the identical situation — instead of
silently no-oping behind a generic success response.

This is a conscious choice to prioritize a clear, actionable error over
narrow account-enumeration protection for *this specific case*. The
tradeoff is real and now accepted, not overlooked: an attacker who already
suspects an email might belong to a Kolably account can now distinguish
"exists and deactivated" (403) from "exists and active" or "doesn't exist"
(both 200) by calling this one endpoint. Judged an acceptable cost against
a real, repeated user-facing dead end — deactivated accounts are not
secret, security-sensitive data in the same way as (say) whether a
password is correct.

## Consequences
- `resend_verification_email` still uses the silent/non-leaking pattern —
  **not** changed by this decision, since it wasn't part of what the user
  raised. Worth a conscious decision (not a default assumption either way)
  if it comes up: does the same "explicit error beats a silent dead end"
  reasoning apply there too, or does that endpoint's specific dead-end risk
  differ enough to keep it silent? Don't change it without that
  conversation happening first.
- Any *new* deactivation-adjacent check added to an auth endpoint should
  default to this repo's now-established pattern: explicit, role-aware
  error over a silent generic response — unless there's a specific reason
  (like account enumeration risk) to prefer the opposite, in which case
  that reasoning should be written down the way this decision is, not left
  implicit.
- No frontend code changes were needed for this — both `kolably_ui`'s
  `ForgotPassword.tsx` (web) and `forgot-password.tsx` (mobile) already
  `await` the API call before navigating to the OTP screen and already have
  working interceptor-driven toast handling for any thrown error; the
  silent-vs-explicit choice was purely a backend response-shape decision.

## Related decisions
- Supersedes the silent-response half of the original #31 fix recorded in
  [[logs/2026-08-24]]'s "issue-tracker bug-fixing pass" section.

## Session
- [[logs/2026-08-24]]
