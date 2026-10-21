-- READ ONLY: detect future fixtures harmed by a time-only raw history purge.
-- This deliberately uses an indexed EXISTS/fixture_uid lookup and does not
-- enumerate private odds payloads. Does not authorize any cleanup.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '8s';
SET LOCAL lock_timeout = '1s';
WITH cut AS (
  SELECT ((now() AT TIME ZONE 'Europe/Istanbul')::date - 6)::text
         || 'T00:00:00+03:00' AS capture_cutoff
), future AS MATERIALIZED (
  SELECT fixture_uid FROM public.fixtures
  WHERE fixture_uid IS NOT NULL AND kickoff_utc > now()
), probe AS (
  SELECT f.fixture_uid,
   EXISTS (
     SELECT 1 FROM public.moneyway_1x2_history h,cut
     WHERE h.fixture_uid=f.fixture_uid
       AND h.scraped_at < cut.capture_cutoff
     LIMIT 1
   ) AS has_older_prematch_history
  FROM future f
)
SELECT COUNT(*) AS future_fixtures_checked,
       COUNT(*) FILTER (WHERE has_older_prematch_history) AS future_fixtures_at_risk_of_time_only_cleanup,
       FALSE AS time_only_delete_safe
FROM probe;
COMMIT;
