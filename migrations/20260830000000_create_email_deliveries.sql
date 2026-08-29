-- Migration: Create email_deliveries table
-- Description: Tracks outbound email dispatches, idempotency keys, delivery states, and error metadata.

CREATE TABLE IF NOT EXISTS public.email_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key VARCHAR(256) NOT NULL,
    flow_name VARCHAR(64) NOT NULL,
    recipient_email VARCHAR(255) NOT NULL,
    recipient_profile_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    resend_id VARCHAR(128),
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 1,
    subject VARCHAR(255) NOT NULL,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc'::text, now())
);

-- Deduplication index
CREATE UNIQUE INDEX IF NOT EXISTS idx_email_deliveries_idempotency_key
    ON public.email_deliveries(idempotency_key);

-- Performance & lookup indexes
CREATE INDEX IF NOT EXISTS idx_email_deliveries_flow_status
    ON public.email_deliveries(flow_name, status);

CREATE INDEX IF NOT EXISTS idx_email_deliveries_recipient
    ON public.email_deliveries(recipient_email, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_email_deliveries_resend_id
    ON public.email_deliveries(resend_id) WHERE resend_id IS NOT NULL;

-- Enable Row Level Security
ALTER TABLE public.email_deliveries ENABLE ROW LEVEL SECURITY;

-- Service role access policy
CREATE POLICY "Service role full access on email_deliveries"
    ON public.email_deliveries
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
