-- PROPOSAL ONLY. Requires explicit user approval and DBA review.
-- Execute separately from transactional migrations. CREATE INDEX CONCURRENTLY cannot run inside BEGIN/COMMIT.
-- Benchmark disk / write amplification and EXPLAIN ANALYZE safely first.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sxf_base_mw_snapshot_uid_time
  ON public.moneyway_snapshots (fixture_uid, scraped_at_utc, id);