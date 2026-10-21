-- Bounded sample only: tests earliest available snapshots for up to 8
-- physical fixtures on the last day eligible for 7-day retention.
-- Does NOT verify all raw history, unnamed/null fixture_uid rows, or cold backup.
-- All SQL read-only and no destructive action is implied.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='1s';
WITH audit_day AS (
 SELECT (now() AT TIME ZONE 'Europe/Istanbul')::date-7 AS d
), fixture_sample AS MATERIALIZED (
 SELECT f.fixture_uid
 FROM public.fixtures f,audit_day a
 WHERE f.fixture_uid IS NOT NULL
   AND f.kickoff_utc >= (a.d::timestamp AT TIME ZONE 'Europe/Istanbul')
   AND f.kickoff_utc < ((a.d+1)::timestamp AT TIME ZONE 'Europe/Istanbul')
 ORDER BY f.fixture_uid LIMIT 8
), row_sample AS MATERIALIZED (
 SELECT f.fixture_uid,s.id,s.scraped_at_utc
 FROM fixture_sample f
 CROSS JOIN LATERAL (
   SELECT id,scraped_at_utc FROM public.moneyway_snapshots
   WHERE fixture_uid=f.fixture_uid
   ORDER BY scraped_at_utc ASC LIMIT 3
 ) s
)
SELECT jsonb_build_object(
 'fixture_day',(SELECT d FROM audit_day),
 'sampled_fixtures',(SELECT count(*) FROM fixture_sample),
 'sampled_rows',count(*),
 'found_in_archive',count(*) FILTER (WHERE EXISTS (
   SELECT 1 FROM research_archive.moneyway_snapshots a,audit_day d
   WHERE a.local_date=d.d AND a.source_id=s.id
 )),
 'missing_in_archive',count(*) FILTER (WHERE NOT EXISTS (
   SELECT 1 FROM research_archive.moneyway_snapshots a,audit_day d
   WHERE a.local_date=d.d AND a.source_id=s.id
 )),
 'complete_row_parity_verified',false
)::text AS result FROM row_sample s;
COMMIT;
