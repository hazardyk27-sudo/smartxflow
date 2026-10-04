-- SmartXFlow scraper heartbeat table only.
-- Apply in the SmartXFlow Supabase SQL Editor for project pswdvnmqjjnjodwzkmkp.
-- Safe to re-run.

CREATE TABLE IF NOT EXISTS public.scraper_heartbeat (
    source TEXT PRIMARY KEY,
    last_heartbeat TIMESTAMPTZ,
    status TEXT DEFAULT 'unknown',
    match_count INTEGER DEFAULT 0,
    error_message TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scraper_heartbeat_last_heartbeat
    ON public.scraper_heartbeat(last_heartbeat);
