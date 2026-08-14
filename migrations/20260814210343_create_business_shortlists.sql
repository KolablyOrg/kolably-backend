-- Persisted creator shortlists for brand discovery and comparison.
CREATE TABLE IF NOT EXISTS business_shortlists (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id UUID NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
  tags TEXT[] NOT NULL DEFAULT '{}',
  note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (business_id, creator_id)
);

CREATE INDEX IF NOT EXISTS idx_business_shortlists_business_id
  ON business_shortlists(business_id);

CREATE INDEX IF NOT EXISTS idx_business_shortlists_creator_id
  ON business_shortlists(creator_id);
