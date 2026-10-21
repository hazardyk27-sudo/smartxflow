-- SmartXFlow / cold backup + missing historical fixture readiness.
-- ZERO WRITES. This audit does not enable a deletion or archive job.
-- Uses the Istanbul kickoff-day, NEVER raw observation date or UTC fixture_date.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='1s';
WITH clock AS (
 SELECT (now() AT TIME ZONE 'Europe/Istanbul')::date AS today
), old_days AS (
 SELECT (clock.today-16+i)::date AS day FROM clock,generate_series(0,9) i
), public_fixtures AS MATERIALIZED (
 SELECT s.fixture_uid,s.match_id_hash,
        (s.kickoff_utc AT TIME ZONE 'Europe/Istanbul')::date AS local_day
 FROM public.fixtures s,clock
 WHERE s.kickoff_utc >= ((clock.today-16)::timestamp AT TIME ZONE 'Europe/Istanbul')
   AND s.kickoff_utc < ((clock.today-6)::timestamp AT TIME ZONE 'Europe/Istanbul')
), archived_fixtures AS MATERIALIZED (
 SELECT a.fixture_uid,a.local_date FROM research_archive.fixtures a,clock
 WHERE a.local_date BETWEEN clock.today-16 AND clock.today-7
), file_inventory AS (
 SELECT count(*)::bigint object_count,
        count(*) FILTER(WHERE name LIKE '%/manifest.json')::bigint manifest_count,
        COALESCE(sum((metadata->>'size')::bigint),0)::bigint object_bytes
 FROM storage.objects WHERE bucket_id='sxf-research-archive'
), collisions AS (
 SELECT count(*)::bigint reused_hashes FROM (
    SELECT match_id_hash FROM public.fixtures
    WHERE match_id_hash IS NOT NULL
    GROUP BY match_id_hash HAVING count(DISTINCT fixture_uid)>1
 ) x
), per_day AS (
 SELECT d.day,
  (SELECT count(*) FROM public_fixtures s WHERE s.local_day=d.day) source_fixtures,
  (SELECT count(*) FROM archived_fixtures a WHERE a.local_date=d.day) archive_fixtures,
  (SELECT count(*) FROM public_fixtures s WHERE s.local_day=d.day
    AND NOT EXISTS(SELECT 1 FROM archived_fixtures a
        WHERE a.fixture_uid=s.fixture_uid AND a.local_date=d.day)) unarchived_source_fixtures
 FROM old_days d
)
SELECT jsonb_build_object(
  'today_istanbul', (SELECT today FROM clock),
  'fixture_days', (SELECT jsonb_agg(to_jsonb(p) ORDER BY p.day) FROM per_day p),
  'cold_bucket_exists', EXISTS(
    SELECT 1 FROM storage.buckets WHERE id='sxf-research-archive'),
  'cold_bucket_object_count',(SELECT object_count FROM file_inventory),
  'cold_bucket_manifest_count',(SELECT manifest_count FROM file_inventory),
  'cold_bucket_bytes',(SELECT object_bytes FROM file_inventory),
  'reused_hashes',(SELECT reused_hashes FROM collisions),
  'backup_restored_and_verified',false,
  'hash_fallback_physical_identity_verified',false,
  'archive_data_parity_verified',false,
  'time_only_cleanup_safe',false
)::text AS result;
COMMIT;
