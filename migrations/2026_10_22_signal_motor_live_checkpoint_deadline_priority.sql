-- V2 live checkpoint priority: protect still-on-time T windows when
-- historical replay jobs exist. Istanbul match date remains primary.
-- Worker-safe migration: replaces only the order of a token-fenced claim
-- function; no queue DML, no service restart, no history rewrite.
-- No future checkpoint is claimable before run_after, unchanged.
BEGIN;
SET LOCAL lock_timeout='8s';
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
            (j.state IN ('PENDING','RETRY','WAITING_DATA') AND j.next_attempt_at<=now())
            OR (j.state='LEASED' AND j.lease_expires_at<now())
        )
        AND j.run_after<=now()
        AND j.ruleset_version='SXF_SIGNAL_MOTOR_V2_2026_10_22'
        -- Jobs are independent: an Early source gap cannot block Base or T12.
        AND (
            CASE WHEN p_lane='LIVE'
                THEN j.kickoff_utc>now()
                ELSE j.kickoff_utc<=now()
            END
        )
        -- Today first (Istanbul day), then tomorrow, then later match days.
        -- Do NOT prioritize ancient checkpoint debt over today's fixtures.
        ORDER BY
            -- Today first as explicitly requested, then protect checkpoint
            -- windows that can still yield an on-time signal before backlog.
            (j.kickoff_utc AT TIME ZONE 'Europe/Istanbul')::date ASC,
            CASE WHEN j.checkpoint_at + INTERVAL '20 minutes' >= now()
                      THEN 0 ELSE 1 END ASC,
            CASE WHEN j.checkpoint_at + INTERVAL '20 minutes' >= now()
                      THEN j.checkpoint_at ELSE NULL END ASC NULLS LAST,
            j.kickoff_utc ASC,
            j.checkpoint_at ASC,
            j.job_id ASC
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
END;
$function$;
REVOKE ALL ON FUNCTION public.sxf_base_claim_due_jobs_lane(text,text,integer,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sxf_base_claim_due_jobs_lane(text,text,integer,integer) TO service_role;
COMMIT;
