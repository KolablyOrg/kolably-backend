-- Migration: 002 - Alter Profiles Table
-- Description: Convert role from USER-DEFINED enum to TEXT+CHECK, add ON DELETE CASCADE, updated_at trigger
-- Applied: 2026-07-26

ALTER TABLE profiles ALTER COLUMN role TYPE TEXT USING role::TEXT;

DROP TYPE IF EXISTS user_role;

ALTER TABLE profiles
  DROP CONSTRAINT IF EXISTS profiles_role_check;
ALTER TABLE profiles
  ADD CONSTRAINT profiles_role_check
  CHECK (role IN ('creator', 'business', 'superadmin'));

ALTER TABLE profiles ALTER COLUMN role SET DEFAULT 'creator';

ALTER TABLE profiles ALTER COLUMN is_active SET NOT NULL;
ALTER TABLE profiles ALTER COLUMN is_active SET DEFAULT true;

ALTER TABLE profiles ALTER COLUMN created_at SET NOT NULL;

ALTER TABLE profiles ALTER COLUMN updated_at SET NOT NULL;

ALTER TABLE profiles DROP CONSTRAINT IF EXISTS profiles_auth_id_fkey;
ALTER TABLE profiles
  ADD CONSTRAINT profiles_auth_id_fkey
  FOREIGN KEY (auth_id) REFERENCES auth.users(id) ON DELETE CASCADE;

DROP TRIGGER IF EXISTS trg_profiles_updated_at ON profiles;
CREATE TRIGGER trg_profiles_updated_at
  BEFORE UPDATE ON profiles
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
