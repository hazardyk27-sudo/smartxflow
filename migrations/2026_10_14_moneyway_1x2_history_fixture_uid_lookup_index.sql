-- Speed up UID-first latest-history reads used by Fixture Identity V2 UI readers.
-- Query shape:
--   WHERE fixture_uid = $1 ORDER BY scraped_at DESC LIMIT 1
--
-- Before this index PostgreSQL scanned the scraped_at index and filtered ~1.8M
-- rows for some fixture UIDs, causing PostgREST statement timeouts.
CREATE INDEX IF NOT EXISTS moneyway_1x2_history_fixture_uid_scraped_at_idx
ON public.moneyway_1x2_history (fixture_uid, scraped_at DESC);
