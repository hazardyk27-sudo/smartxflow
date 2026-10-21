-- READ ONLY: outputs ONE JSON evidence record for sxf_precleanup_preflight.py.
-- Never expand this into a DELETE or reuse its report as automatic authorization.
-- Isolates hot account/position tables from this historical market-data audit.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '8s';
SET LOCAL lock_timeout = '1s';
WITH clock AS (
  SELECT (now() AT TIME ZONE 'Europe/Istanbul')::date AS local_today
), oldest AS (
  SELECT MIN(day) AS earliest_day FROM (
    VALUES
      ((SELECT (scraped_at_utc AT TIME ZONE 'Europe/Istanbul')::date
        FROM public.moneyway_snapshots WHERE scraped_at_utc IS NOT NULL ORDER BY scraped_at_utc LIMIT 1)),
      ((SELECT (snapshot_at AT TIME ZONE 'Europe/Istanbul')::date
        FROM public.live_snapshots WHERE snapshot_at IS NOT NULL ORDER BY snapshot_at LIMIT 1)),
      ((SELECT left(scraped_at,10)::date
        FROM public.moneyway_1x2_history WHERE scraped_at IS NOT NULL ORDER BY scraped_at LIMIT 1)),
      ((SELECT left(scraped_at,10)::date
        FROM public.moneyway_ou25_history WHERE scraped_at IS NOT NULL ORDER BY scraped_at LIMIT 1)),
      ((SELECT left(scraped_at,10)::date
        FROM public.moneyway_btts_history WHERE scraped_at IS NOT NULL ORDER BY scraped_at LIMIT 1)),
      ((SELECT left(scraped_at,10)::date
        FROM public.dropping_1x2_history WHERE scraped_at IS NOT NULL ORDER BY scraped_at LIMIT 1)),
      ((SELECT left(scraped_at,10)::date
        FROM public.dropping_ou25_history WHERE scraped_at IS NOT NULL ORDER BY scraped_at LIMIT 1)),
      ((SELECT left(scraped_at,10)::date
        FROM public.dropping_btts_history WHERE scraped_at IS NOT NULL ORDER BY scraped_at LIMIT 1))
  ) AS earliest(day)
)
SELECT jsonb_build_object(
  'db_today', clock.local_today,
  'cutoff', clock.local_today - 6,
  'earliest_source', oldest.earliest_day,
  'archives', COALESCE((
    SELECT jsonb_agg(jsonb_build_object(
      'date', a.local_date,
      'status', a.status,
      'full', COALESCE(a.notes->>'full_archive_complete', 'false') = 'true',
      'cold', a.notes->>'cold_backup',
      'allow', COALESCE(a.notes->>'source_retention_cleanup_allowed', 'false') = 'true'
    ) ORDER BY a.local_date)
    FROM research_archive.archive_runs a
    WHERE a.local_date >= oldest.earliest_day AND a.local_date < clock.local_today - 6
  ), '[]'::jsonb),
  'pending_holds', (SELECT COUNT(*) FROM public.learning_archive_retention_holds WHERE status = 'PENDING'),
  'pending_outbox', (SELECT COUNT(*) FROM public.learning_archive_capture_outbox WHERE status = 'PENDING'),
  -- Evidence for these critical claims must be explicitly supplied by separate,
  -- independent backup and source/target parity procedures, NOT self-certified.
  'independent_backup_verified', false,
  'source_archive_parity_verified', false
)::text FROM clock CROSS JOIN oldest;
COMMIT;
