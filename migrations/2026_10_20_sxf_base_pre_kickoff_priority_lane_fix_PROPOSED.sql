-- PROPOSED-only fix for due pre-kickoff T6/T8 jobs stranded by the 3h cutoff.
-- Requires explicit release approval and isolated schema review. NOT auto-deployed.
-- Must follow Phase 4A WAITING_DATA table and checkpoint durability migrations.
BEGIN;
CREATE OR REPLACE FUNCTION public.sxf_base_claim_due_jobs_lane(
    p_worker text, p_lane text, p_limit integer DEFAULT 1,
    p_lease_seconds integer DEFAULT 900)
RETURNS TABLE(job_id uuid,job_key text,ruleset_version text,fixture_uid uuid,
    kickoff_utc timestamptz,checkpoint_hours smallint,family text,
    checkpoint_at timestamptz,lease_token uuid,attempt_count integer)
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,pg_temp AS $$
BEGIN
    IF p_worker IS NULL OR length(trim(p_worker))<1 OR length(p_worker)>100
       OR p_lane IS NULL OR p_lane NOT IN ('LIVE','BACKLOG')
       OR p_limit IS NULL OR p_limit <> 1
       OR p_lease_seconds IS NULL OR p_lease_seconds NOT BETWEEN 60 AND 1800 THEN
        RAISE EXCEPTION 'invalid lane claim parameters';
    END IF;
    RETURN QUERY WITH locked AS (
        SELECT j.job_id
        FROM public.sxf_base_checkpoint_jobs j
        WHERE (
            (j.state IN ('PENDING','RETRY','WAITING_DATA') AND j.next_attempt_at <= now())
            OR (j.state='LEASED' AND j.lease_expires_at < now())
        )
        AND (
            CASE WHEN p_lane='LIVE' THEN
                (j.family='BASE' AND j.checkpoint_hours IN (8,6)
                 AND j.kickoff_utc > now()
                 AND j.checkpoint_at >= now()-interval '8 hours'
                 AND j.checkpoint_at <= now())
            ELSE NOT (
                j.family='BASE' AND j.checkpoint_hours IN (8,6)
                AND j.kickoff_utc > now()
                 AND j.checkpoint_at >= now()-interval '8 hours'
                AND j.checkpoint_at <= now()
            ) END
        )
        -- LIVE prioritizes earliest upcoming kickoff and T-6 over T-8.
        -- Backlog continues to use oldest checkpoint first.
        ORDER BY CASE WHEN p_lane='LIVE' THEN j.kickoff_utc END ASC,
                 CASE WHEN p_lane='LIVE' AND j.checkpoint_hours=6 THEN 0
                      WHEN p_lane='LIVE' THEN 1 ELSE 0 END ASC,
                 j.checkpoint_at, j.job_id
        LIMIT p_limit
        FOR UPDATE SKIP LOCKED
    ), updated AS (
        UPDATE public.sxf_base_checkpoint_jobs j
        SET state='LEASED',lease_owner=p_worker,lease_token=gen_random_uuid(),
            lease_expires_at=now()+make_interval(secs=>p_lease_seconds),
            attempt_count=j.attempt_count+1
        FROM locked l WHERE j.job_id=l.job_id
        RETURNING j.*
    )
    SELECT u.job_id,u.job_key,u.ruleset_version,u.fixture_uid,u.kickoff_utc,
           u.checkpoint_hours,u.family,u.checkpoint_at,u.lease_token,u.attempt_count
    FROM updated u ORDER BY u.checkpoint_at,u.job_id;
END $$;
REVOKE ALL ON FUNCTION public.sxf_base_claim_due_jobs_lane(text,text,integer,integer)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sxf_base_claim_due_jobs_lane(text,text,integer,integer)
  TO service_role;
COMMIT;
