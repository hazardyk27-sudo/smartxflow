-- Part 3 additive fixture-level source gap hardening.
-- Migration 1 has ALREADY been applied. This migration is PREVIEW ONLY until
-- the Base worker and recovery timer are confirmed stopped and leases drained.
-- The user's requirement is to SKIP THE MATCH when an original T checkpoint
-- lacks valid source data; not to endlessly retry or run its sibling checkpoints.
-- All completed events, source rows and historical jobs remain unchanged.
BEGIN;
CREATE OR REPLACE FUNCTION public.sxf_base_skip_missing_source(
    p_job_id uuid, p_lease_token uuid, p_reason text DEFAULT 'SOURCE_INCOMPLETE'
) RETURNS boolean
LANGUAGE plpgsql
SET search_path TO 'public','pg_temp'
AS $function$
DECLARE
    v_fixture_uid uuid;
    v_kickoff_utc timestamptz;
BEGIN
    IF p_job_id IS NULL OR p_lease_token IS NULL
       OR p_reason IS DISTINCT FROM 'SOURCE_INCOMPLETE' THEN
        RAISE EXCEPTION 'invalid source skip parameters';
    END IF;

    -- Only a LIVE, due and correctly fenced source job can initiate a fixture
    -- skip. No retroactive cleanup after kickoff; no invented observations.
    SELECT j.fixture_uid,j.kickoff_utc INTO v_fixture_uid,v_kickoff_utc
      FROM public.sxf_base_checkpoint_jobs j
     WHERE j.job_id=p_job_id
       AND j.lease_token=p_lease_token
       AND j.state='LEASED'
       AND j.lease_expires_at>now()
       AND j.checkpoint_at<=now()
       AND j.run_after<=now()
       AND j.kickoff_utc>now()
     FOR UPDATE;
    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    -- Do not invalidate any other worker's live lease. If another sibling
    -- is currently leased, reject the transition and let normal fencing
    -- handle the concurrent attempt (never cancel an in-flight completion).
    IF EXISTS(
        SELECT 1 FROM public.sxf_base_checkpoint_jobs sibling
         WHERE sibling.fixture_uid=v_fixture_uid
           AND sibling.kickoff_utc=v_kickoff_utc
           AND sibling.job_id<>p_job_id
           AND sibling.state='LEASED'
           AND sibling.lease_expires_at>now()
    ) THEN
        RETURN FALSE;
    END IF;

    -- Atomic fixture-level terminalization. Not-yet-due sibling checkpoints
    -- are recorded as upstream fixture skips, NOT falsely as missing snapshots.
    -- Other completed signals and SUPERSEDED/SKIPPED_DATA rows are untouched.
    UPDATE public.sxf_base_checkpoint_jobs j
       SET state='SKIPPED_DATA',
           last_error_code=CASE WHEN j.job_id=p_job_id
                          THEN 'SOURCE_INCOMPLETE'
                          ELSE 'FIXTURE_SKIPPED_UPSTREAM_GAP' END,
           waiting_since=COALESCE(j.waiting_since,now()),
           lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL
     WHERE j.fixture_uid=v_fixture_uid
       AND j.kickoff_utc=v_kickoff_utc
       AND j.kickoff_utc>now()
       AND (j.job_id=p_job_id
            OR j.state IN ('PENDING','RETRY','WAITING_DATA')
            OR (j.state='LEASED' AND j.lease_expires_at<=now()));
    RETURN FOUND;
END;
$function$;
REVOKE ALL ON FUNCTION public.sxf_base_skip_missing_source(uuid,uuid,text)
    FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sxf_base_skip_missing_source(uuid,uuid,text)
    TO service_role;
COMMIT;
