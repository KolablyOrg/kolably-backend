-- Migration: 30-day reactivation window for deactivated accounts
-- Description: adds profiles.deactivated_at so login can tell whether a
-- deactivated account is still within its 30-day reactivate-by-logging-in
-- window, and so a scheduled job can anonymize accounts past it. Backfills
-- existing deactivated rows to "now" (rather than leaving them NULL) so
-- they get a fresh, unambiguous 30-day window instead of the app treating
-- an unknown timestamp as a special case forever.

ALTER TABLE profiles
  ADD COLUMN IF NOT EXISTS deactivated_at TIMESTAMPTZ;

UPDATE profiles
  SET deactivated_at = now()
  WHERE is_active = false AND deactivated_at IS NULL;

COMMENT ON COLUMN profiles.deactivated_at IS
  'Set when is_active is flipped to false (DELETE /auth/me). Logging in
   within 30 days of this timestamp reactivates the account automatically;
   past that, the daily cleanup job anonymizes it. NULL means active.';
