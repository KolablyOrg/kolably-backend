-- Create table for tracking daily stats of creators
CREATE TABLE IF NOT EXISTS public.creator_stats_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id UUID NOT NULL REFERENCES public.creators(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    follower_count INT,
    engagement_rate NUMERIC(5, 2),
    views_count INT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    UNIQUE(creator_id, snapshot_date)
);

-- Add index for fast querying by creator and date
CREATE INDEX IF NOT EXISTS idx_creator_stats_history_creator_date ON public.creator_stats_history(creator_id, snapshot_date DESC);
