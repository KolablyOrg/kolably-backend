-- Migration: campaign brief fields for 4-step create wizard
-- Adds objective & audience brief fields, content due date, and engagement objective.

ALTER TABLE campaigns
  ADD COLUMN IF NOT EXISTS platforms JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS product_promoted TEXT,
  ADD COLUMN IF NOT EXISTS audience_age_range TEXT,
  ADD COLUMN IF NOT EXISTS audience_gender TEXT,
  ADD COLUMN IF NOT EXISTS audience_location TEXT,
  ADD COLUMN IF NOT EXISTS audience_interests TEXT,
  ADD COLUMN IF NOT EXISTS key_messaging TEXT,
  ADD COLUMN IF NOT EXISTS dos TEXT,
  ADD COLUMN IF NOT EXISTS donts TEXT,
  ADD COLUMN IF NOT EXISTS reference_image_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS content_due_at TIMESTAMPTZ;

-- Expand objective check to include 'engagement' (design chip).
ALTER TABLE campaigns DROP CONSTRAINT IF EXISTS campaigns_objective_check;
ALTER TABLE campaigns
  ADD CONSTRAINT campaigns_objective_check CHECK (
    objective IN (
      'brand_awareness',
      'product_launch',
      'foot_traffic',
      'user_generated_content',
      'sales_conversion',
      'event_promotion',
      'engagement',
      'other'
    )
  );

COMMENT ON COLUMN campaigns.platforms IS 'Selected platforms for the campaign brief, e.g. ["instagram","youtube"]';
COMMENT ON COLUMN campaigns.product_promoted IS 'Product / what is being promoted';
COMMENT ON COLUMN campaigns.content_due_at IS 'When creators should deliver content';
COMMENT ON COLUMN campaigns.reference_image_urls IS 'Moodboard / reference image URLs shown to creators';
