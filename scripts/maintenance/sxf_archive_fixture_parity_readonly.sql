-- Fixture-level archival parity smoke test. STRICTLY READ ONLY.
-- Archive day is kickoff time in Europe/Istanbul, NOT public.fixture_date UTC
-- and NOT the timestamp of a prematch observation.
-- Look back 16 calendar days, exclude the current 7 retained days.
-- This tests ONLY fixture coverage, never proves raw snapshot/history parity.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '8s';
SET LOCAL lock_timeout = '1s';
WITH clock AS (
  SELECT (now() AT TIME ZONE 'Europe/Istanbul')::date AS today
), dates AS (
  SELECT g::date AS d FROM clock,
    generate_series(clock.today-16,clock.today-7,interval '1 day') AS g
), src AS MATERIALIZED (
  SELECT fixture_uid,kickoff_utc,
         (kickoff_utc AT TIME ZONE 'Europe/Istanbul')::date AS local_day
  FROM public.fixtures,clock
  WHERE kickoff_utc >= ((clock.today-16)::timestamp AT TIME ZONE 'Europe/Istanbul')
    AND kickoff_utc < ((clock.today-6)::timestamp AT TIME ZONE 'Europe/Istanbul')
), arc AS MATERIALIZED (
  SELECT fixture_uid,kickoff_utc,local_date
  FROM research_archive.fixtures,clock
  WHERE local_date BETWEEN clock.today-16 AND clock.today-7
)
SELECT d.d AS fixture_day,
       COUNT(s.fixture_uid) AS source_count,
       COUNT(a.fixture_uid) AS matched_archive,
       COUNT(s.fixture_uid) FILTER(WHERE a.fixture_uid IS NULL) AS missing_archive,
       COUNT(s.fixture_uid) FILTER(
         WHERE a.fixture_uid IS NOT NULL
           AND (a.local_date IS DISTINCT FROM s.local_day
                OR a.kickoff_utc IS DISTINCT FROM s.kickoff_utc)
       ) AS wrong_archive_day_or_kickoff,
       (SELECT COUNT(*) FROM arc z WHERE z.local_date=d.d) AS archive_count
FROM dates d
LEFT JOIN src s ON s.local_day=d.d
LEFT JOIN arc a ON a.fixture_uid=s.fixture_uid
GROUP BY d.d ORDER BY d.d;
COMMIT;
