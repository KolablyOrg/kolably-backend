-- Migration: 001 - Extensions and Utility Functions
-- Description: Enable pg_trgm for text search and create reusable updated_at trigger function
-- Applied: 2026-07-26

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;
