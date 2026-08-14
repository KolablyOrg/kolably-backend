-- Migration: add TOTP two-factor authentication fields to profiles
-- Description: custom TOTP 2FA (pyotp) — see app/services/twofa_service.py.
--   Not Supabase's built-in MFA: this backend never checks the `aal` claim,
--   so gating token issuance in application code (rather than relying on
--   Supabase's session-bound MFA flow) avoids a real security gap.
-- Applied: 2026-08-14

ALTER TABLE profiles
  ADD COLUMN IF NOT EXISTS totp_secret_encrypted text,
  ADD COLUMN IF NOT EXISTS totp_enabled boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN profiles.totp_secret_encrypted IS
  'Fernet-encrypted (app.core.crypto) TOTP secret — same at-rest encryption pattern as creators.instagram_access_token. Never returned by any API response.';
COMMENT ON COLUMN profiles.totp_enabled IS
  'When true, login() withholds real tokens until POST /auth/2fa/verify succeeds.';
