-- Add result column to tracked_wallet_activity so the scraper can store
-- won/lost/open per outcome token (CLOB-based), and the web app reads
-- directly from DB without live API calls on every profile open.
ALTER TABLE public.tracked_wallet_activity ADD COLUMN IF NOT EXISTS result TEXT;
