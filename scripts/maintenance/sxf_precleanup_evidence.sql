-- STRICTLY READ ONLY. The raw source observation date differs from
-- the archive's Turkey-local kickoff-day partition key. Never infer that an old captured
-- snapshot requires an archive_runs row for the observation date, nor equate
-- public.fixtures.fixture_date (UTC) with the Turkey-local kickoff date.
--
-- This returns a small metadata/probe JSON object; it intentionally supplies
-- FALSE for independent backup, full source parity, timestamp->fixture lineage
-- and future-fixture retention readiness. Nothing in this SQL authorizes DELETE.
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
  ) AS first_observation(day)
), fixture_dates AS MATERIALIZED (
  SELECT DISTINCT (f.kickoff_utc AT TIME ZONE 'Europe/Istanbul')::date AS d
  FROM public.fixtures f, clock
  WHERE f.kickoff_utc IS NOT NULL
    AND (f.kickoff_utc AT TIME ZONE 'Europe/Istanbul')::date < clock.local_today - 6
), probe_day AS (
  SELECT local_today - 7 AS d FROM clock
), source_probe AS MATERIALIZED (
  SELECT internal_id,fixture_uid,kickoff_utc
  FROM public.fixtures,probe_day
  WHERE (kickoff_utc AT TIME ZONE 'Europe/Istanbul')::date=probe_day.d
), archive_probe AS MATERIALIZED (
  SELECT source_internal_id,fixture_uid,kickoff_utc
  FROM research_archive.fixtures,probe_day
  WHERE local_date=probe_day.d
), probe AS (
  SELECT jsonb_build_object(
    'date', (SELECT d FROM probe_day),
    'source_total', (SELECT count(*) FROM source_probe),
    'archive_total', (SELECT count(*) FROM archive_probe),
    'source_null_uid', (SELECT count(*) FROM source_probe WHERE fixture_uid IS NULL),
    'archive_null_uid', (SELECT count(*) FROM archive_probe WHERE fixture_uid IS NULL),
    'missing_in_archive', (SELECT count(*) FROM source_probe s WHERE NOT EXISTS
       (SELECT 1 FROM archive_probe a WHERE a.fixture_uid=s.fixture_uid)),
    'archive_not_in_source', (SELECT count(*) FROM archive_probe a WHERE NOT EXISTS
       (SELECT 1 FROM source_probe s WHERE a.fixture_uid=s.fixture_uid)),
    'kickoff_mismatches', (SELECT count(*) FROM source_probe s
       JOIN archive_probe a USING(fixture_uid)
       WHERE s.kickoff_utc IS DISTINCT FROM a.kickoff_utc)
  ) AS obj
)
SELECT jsonb_build_object(
  'db_today', clock.local_today,
  'cutoff', clock.local_today - 6,
  'earliest_source', oldest.earliest_day,
  'source_date_axis', 'observation_timestamp',
  'archive_date_axis', 'kickoff_istanbul_day',
  'source_fixture_dates', COALESCE((
    SELECT jsonb_agg(d ORDER BY d) FROM fixture_dates
  ),'[]'::jsonb),
  'archives', COALESCE((
    SELECT jsonb_agg(jsonb_build_object(
      'date', a.local_date,
      'status', a.status,
      'full', COALESCE(a.notes->>'full_archive_complete','false')='true',
      'cold', a.notes->>'cold_backup',
      'allow', COALESCE(a.notes->>'source_retention_cleanup_allowed','false')='true'
    ) ORDER BY a.local_date)
    FROM research_archive.archive_runs a
    WHERE a.local_date IN (SELECT d FROM fixture_dates)
  ),'[]'::jsonb),
  'fixture_probe', probe.obj,
  'pending_holds', (SELECT COUNT(*) FROM public.learning_archive_retention_holds WHERE status='PENDING'),
  'pending_outbox', (SELECT COUNT(*) FROM public.learning_archive_capture_outbox WHERE status='PENDING'),
  -- These independent proof gates are NEVER self-certified from DB metadata.
  'source_archive_temporal_lineage_verified',false,
  'independent_backup_verified',false,
  'source_archive_parity_verified',false,
  'future_fixture_history_protected',false
)::text
FROM clock CROSS JOIN oldest CROSS JOIN probe;
COMMIT;
