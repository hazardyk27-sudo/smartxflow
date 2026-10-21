-- Approved operator-only: prioritize current + Early immutable checkpoint jobs.
-- Validated against the installed sxf_base_claim_due_jobs_lane definition.
-- No fixture, snapshot, signal, history or checkpoint rows are rewritten.
BEGIN;
CREATE OR REPLACE FUNCTION public.sxf_base_claim_due_jobs_lane(p_worker text, p_lane text, p_limit integer DEFAULT 1, p_lease_seconds integer DEFAULT 900)
 RETURNS TABLE(job_id uuid, job_key text, ruleset_version text, fixture_uid uuid, kickoff_utc timestamp with time zone, checkpoint_hours smallint, family text, checkpoint_at timestamp with time zone, lease_token uuid, attempt_count integer)
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
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
                (
                  j.kickoff_utc > now()
                  AND j.checkpoint_at >= now() - interval '8 hours'
                  AND j.checkpoint_at <= now()
                  AND (
                      (j.family='BASE' AND j.checkpoint_hours IN (8,6))
                      OR (j.family='EARLY_CORE' AND j.checkpoint_hours IN (72,60,40,24))
                      OR (j.family='EARLY_T12' AND j.checkpoint_hours=12)
                      OR (j.family='EARLY_RETENTION' AND j.checkpoint_hours IN (6,5,4,3))
                  )
                )
            ELSE NOT (
                  j.kickoff_utc > now()
                  AND j.checkpoint_at >= now() - interval '8 hours'
                  AND j.checkpoint_at <= now()
                  AND (
                      (j.family='BASE' AND j.checkpoint_hours IN (8,6))
                      OR (j.family='EARLY_CORE' AND j.checkpoint_hours IN (72,60,40,24))
                      OR (j.family='EARLY_T12' AND j.checkpoint_hours=12)
                      OR (j.family='EARLY_RETENTION' AND j.checkpoint_hours IN (6,5,4,3))
                  )
                ) END
        )
        -- New never-attempted fixtures outrank stale incomplete retries.
        -- LIVE covers all eleven frozen checkpoints and prioritizes timely
        -- authoritative Base T-6 / T-8, then Early retention and Early Core.
        -- BACKLOG still receives a fixed worker quota every cycle.
        ORDER BY
            CASE WHEN j.state='PENDING' AND j.attempt_count=0 THEN 0
                 WHEN j.state IN ('PENDING','RETRY') THEN 1
                 ELSE 2 END,
            CASE WHEN p_lane='LIVE' AND j.family='BASE' AND j.checkpoint_hours=6 THEN 0
                 WHEN p_lane='LIVE' AND j.family='BASE' AND j.checkpoint_hours=8 THEN 1
                 WHEN p_lane='LIVE' AND j.family='EARLY_RETENTION' THEN 2
                 WHEN p_lane='LIVE' AND j.family='EARLY_CORE' THEN 3
                 WHEN p_lane='LIVE' AND j.family='EARLY_T12' THEN 4
                 ELSE 5 END,
            CASE WHEN p_lane='LIVE' THEN j.kickoff_utc END ASC,
            j.checkpoint_at ASC, j.job_id ASC
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
END $function$

REVOKE ALL ON FUNCTION public.sxf_base_claim_due_jobs_lane(text,text,integer,integer)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sxf_base_claim_due_jobs_lane(text,text,integer,integer)
  TO service_role;
COMMIT;
