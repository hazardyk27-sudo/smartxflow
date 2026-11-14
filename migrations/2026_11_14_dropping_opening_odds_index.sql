-- Run each CREATE INDEX statement separately; CONCURRENTLY cannot run inside a transaction.
-- The existing match_id_hash index supports the opening-odds RPC's bounded
-- lookups. These indexes accelerate the UI's
-- `fixture_uid = ... ORDER BY scraped_at DESC LIMIT 1` history lookups.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_drop_1x2_hist_uid_scraped
    ON public.dropping_1x2_history (fixture_uid, scraped_at DESC)
    WHERE fixture_uid IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_drop_ou25_hist_uid_scraped
    ON public.dropping_ou25_history (fixture_uid, scraped_at DESC)
    WHERE fixture_uid IS NOT NULL;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_drop_btts_hist_uid_scraped
    ON public.dropping_btts_history (fixture_uid, scraped_at DESC)
    WHERE fixture_uid IS NOT NULL;
