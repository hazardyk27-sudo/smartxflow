-- SmartXFlow scraper heartbeat repair
-- Idempotent: safe to run even if the original 2026-06-20 migration was applied.
-- IMPORTANT: DDL must be run manually in the SmartXFlow Supabase SQL Editor.

BEGIN;

CREATE TABLE IF NOT EXISTS public.scraper_heartbeat (
    source TEXT PRIMARY KEY,
    last_heartbeat TIMESTAMPTZ,
    status TEXT DEFAULT 'unknown',
    match_count INTEGER DEFAULT 0,
    error_message TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.scraper_heartbeat
    ADD COLUMN IF NOT EXISTS last_heartbeat TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS match_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS error_message TEXT,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_scraper_heartbeat_updated_at
    ON public.scraper_heartbeat(updated_at DESC);

-- Current scraper runtimes use SUPABASE_ANON_KEY. Keep access narrowly scoped
-- to the operations they actually perform; heartbeat rows contain no secrets.
GRANT SELECT, INSERT, UPDATE ON public.scraper_heartbeat TO anon;
GRANT SELECT, INSERT, UPDATE ON public.scraper_heartbeat TO authenticated;
GRANT ALL ON public.scraper_heartbeat TO service_role;

COMMENT ON TABLE public.scraper_heartbeat IS
    'SmartXFlow scraper/alarm/live liveness and master coordination heartbeat.';

COMMIT;
