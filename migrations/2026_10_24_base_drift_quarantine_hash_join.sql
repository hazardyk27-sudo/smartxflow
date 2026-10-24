-- Stabilize drift quarantine read-only fastpath with bounded hash-join COUNT.
-- Preserve the existing fenced, append-only behavior and all historical rows.
-- The initial EXISTS is read-only; every actual mutation still uses the same
-- row locks, state predicate, lease fence, and unique drift-event key.
BEGIN;

CREATE OR REPLACE FUNCTION public.sxf_base_quarantine_fixture_drift(
    p_limit integer DEFAULT 250
)
RETURNS integer
LANGUAGE plpgsql
SET search_path TO 'pg_catalog', 'public'
SET statement_timeout TO '12s'
AS $function$
DECLARE
    v_changed integer;
    v_drift_candidates bigint;
BEGIN
    IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 1000 THEN
       RAISE EXCEPTION 'invalid fixture drift batch';
    END IF;

    -- Always visit the bounded active-job set with a hash join. EXISTS/LIMIT 1
    -- misestimates kickoff drift selectivity and instead scans thousands of
    -- random index probes until PostgREST's statement timeout terminates the
    -- safety RPC. A full COUNT has a stable hash-join plan (~19ms, 2026-10-24).
    -- No data is changed in this fastpath; the original fenced update follows.
    SELECT COUNT(*) INTO v_drift_candidates
      FROM public.sxf_base_checkpoint_jobs j
      JOIN public.fixtures f ON f.fixture_uid = j.fixture_uid
      WHERE j.kickoff_utc IS DISTINCT FROM f.kickoff_utc
        AND j.state <> 'SUPERSEDED'
        AND (j.state <> 'LEASED' OR j.lease_expires_at <= now());
    IF v_drift_candidates = 0 THEN
       RETURN 0;
    END IF;

    WITH locked AS (
      SELECT j.job_id, j.fixture_uid,
             j.kickoff_utc AS prior, f.kickoff_utc AS current
      FROM public.sxf_base_checkpoint_jobs j
      JOIN public.fixtures f ON f.fixture_uid = j.fixture_uid
      WHERE j.kickoff_utc IS DISTINCT FROM f.kickoff_utc
        AND j.state <> 'SUPERSEDED'
        AND (j.state <> 'LEASED' OR j.lease_expires_at <= now())
      ORDER BY j.fixture_uid, j.kickoff_utc, j.job_id
      LIMIT p_limit FOR UPDATE OF j SKIP LOCKED
    ), changed AS (
      UPDATE public.sxf_base_checkpoint_jobs j
      SET state = 'SUPERSEDED',
          lease_owner = NULL,
          lease_token = NULL,
          lease_expires_at = NULL,
          last_error_code = 'KICKOFF_DRIFT'
      FROM locked l WHERE j.job_id = l.job_id
      RETURNING l.fixture_uid, l.prior, l.current
    ), events AS (
      INSERT INTO public.sxf_base_fixture_drift_events(
          fixture_uid, previous_kickoff, current_kickoff, event_key)
      SELECT DISTINCT c.fixture_uid, c.prior, c.current,
             c.fixture_uid::text || ':' ||
             to_char(c.prior AT TIME ZONE 'UTC',
                     'YYYY-MM-DD"T"HH24:MI:SS.US') || ':' ||
             to_char(c.current AT TIME ZONE 'UTC',
                     'YYYY-MM-DD"T"HH24:MI:SS.US')
      FROM changed c
      ON CONFLICT (event_key) DO NOTHING
      RETURNING drift_id
    )
    SELECT count(*) INTO v_changed FROM changed;
    RETURN v_changed;
END
$function$;

COMMIT;
