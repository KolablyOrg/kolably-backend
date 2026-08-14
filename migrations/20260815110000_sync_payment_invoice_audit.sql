-- Migration: synchronize direct payment confirmation with invoices
-- Description: records the profile that confirmed payment and the profile that
-- marked an invoice paid, allowing late-created invoices to reflect payment.

ALTER TABLE collaborations
  ADD COLUMN IF NOT EXISTS payment_confirmed_by UUID
    REFERENCES profiles(id) ON DELETE SET NULL;

ALTER TABLE invoices
  ADD COLUMN IF NOT EXISTS paid_by UUID
    REFERENCES profiles(id) ON DELETE SET NULL;

COMMENT ON COLUMN collaborations.payment_confirmed_by IS
  'Profile that confirmed the business paid the creator directly.';

COMMENT ON COLUMN invoices.paid_by IS
  'Profile that recorded the invoice as paid; business payment confirmation or creator receipt acknowledgement.';
