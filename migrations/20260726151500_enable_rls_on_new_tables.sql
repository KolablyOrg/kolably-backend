-- Migration: 016 - Enable RLS and Security Hardening
-- Description: Enable Row Level Security on all new tables, revoke public EXECUTE on functions
-- Applied: 2026-07-26

ALTER TABLE public.saved_campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portfolio_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.collaborations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.content_submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversation_participants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversation_reads ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;

REVOKE EXECUTE ON FUNCTION public.handle_new_auth_user() FROM anon, authenticated;

REVOKE EXECUTE ON FUNCTION public.set_updated_at() FROM anon, authenticated;
