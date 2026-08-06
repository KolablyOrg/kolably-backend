-- Migration: create invoices table
-- Description: A creator generates an invoice for a completed collaboration
--   (manual line items — no exact agreed amount exists anywhere upstream to
--   auto-fill from). billed_by/billed_to are point-in-time snapshots of the
--   creator's/business's tax & payout info, not live-resolved, since an
--   invoice is a financial record that shouldn't retroactively change if a
--   profile is edited later.

CREATE TABLE invoices (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  collaboration_id UUID NOT NULL UNIQUE REFERENCES collaborations(id) ON DELETE CASCADE,
  creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
  business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'sent' CHECK (status IN ('sent', 'paid')),
  line_items JSONB NOT NULL DEFAULT '[]'::jsonb,
  total_amount NUMERIC NOT NULL DEFAULT 0,
  billed_by JSONB NOT NULL DEFAULT '{}'::jsonb,
  billed_to JSONB NOT NULL DEFAULT '{}'::jsonb,
  paid_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_invoices_creator_id ON invoices(creator_id);
CREATE INDEX idx_invoices_business_id ON invoices(business_id);

COMMENT ON COLUMN invoices.billed_by IS 'Snapshot at creation: {name, pan, gst, bank_display}';
COMMENT ON COLUMN invoices.billed_to IS 'Snapshot at creation: {name, gst}';

-- Extend the notifications type enum (mirrors how kyb_status/business_type
-- were added in 20260804120000_business_signup_and_kyb.sql)
ALTER TABLE notifications DROP CONSTRAINT notifications_type_check;
ALTER TABLE notifications ADD CONSTRAINT notifications_type_check CHECK (
  type IN ('application_received','application_accepted','application_rejected',
           'revision_requested','application_resubmitted','campaign_invite_received',
           'new_message','collaboration_completed','invoice_received')
);
