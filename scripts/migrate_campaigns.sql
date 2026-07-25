-- Migration: Update campaigns table for the new 4-step create/publish flow
-- Run this in the Supabase SQL Editor

-- Add new columns to campaigns table
ALTER TABLE campaigns
  ADD COLUMN IF NOT EXISTS cover_image_url TEXT,
  ADD COLUMN IF NOT EXISTS objective TEXT,
  ADD COLUMN IF NOT EXISTS compensation_type TEXT,
  ADD COLUMN IF NOT EXISTS cash_amount_min NUMERIC,
  ADD COLUMN IF NOT EXISTS cash_amount_max NUMERIC,
  ADD COLUMN IF NOT EXISTS free_product_description TEXT,
  ADD COLUMN IF NOT EXISTS min_engagement_rate NUMERIC,
  ADD COLUMN IF NOT EXISTS max_creators INT,
  ADD COLUMN IF NOT EXISTS additional_requirements TEXT;

-- Convert deliverables from TEXT to JSONB (safe only if table is empty or rows contain valid JSON)
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'campaigns' AND column_name = 'deliverables' AND data_type = 'text'
  ) THEN
    ALTER TABLE campaigns ALTER COLUMN deliverables TYPE JSONB USING deliverables::JSONB;
  END IF;
END $$;

-- Update status check constraint to include new statuses
ALTER TABLE campaigns
  DROP CONSTRAINT IF EXISTS campaigns_status_check;

ALTER TABLE campaigns
  ADD CONSTRAINT campaigns_status_check
  CHECK (status IN ('draft', 'active', 'closed', 'completed'));

-- Ensure existing default status makes sense (draft for new campaigns)
ALTER TABLE campaigns
  ALTER COLUMN status SET DEFAULT 'draft';

-- Add indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status);
CREATE INDEX IF NOT EXISTS idx_campaigns_business_id ON campaigns(business_id);
CREATE INDEX IF NOT EXISTS idx_campaigns_creator_category ON campaigns(creator_category);
CREATE INDEX IF NOT EXISTS idx_campaigns_location ON campaigns(location);
CREATE INDEX IF NOT EXISTS idx_campaigns_created_at ON campaigns(created_at DESC);
