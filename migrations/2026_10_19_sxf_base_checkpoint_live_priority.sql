-- SmartXFlow Base checkpoint queue: prioritize timely live checkpoint review.
-- Changes ONLY sxf_base_claim_due_jobs; no snapshot/legacy table changes.
-- Durable backlog still drains, oldest jobs follow recent due checkpoints.
BEGIN;
CREATE OR REPLACE FUNCTION public.sxf_base_claim_due_jobs(
    p_worker text,p_limit integer DEFAULT 25,p_lease_seconds integer DEFAULT 300)
RETURNS TABLE(job_id uuid,job_key text,ruleset_version text,fixture_uid uuid,
    kickoff_utc timestamptz,checkpoint_hours smallint,family text,
    checkpoint_at timestamptz,lease_token uuid,attempt_count integer)
LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,pg_temp AS $$
BEGIN
    IF p_worker IS NULL OR length(trim(p_worker))<1 OR length(p_worker)>100
       OR p_limit NOT BETWEEN 1 AND 100 OR p_lease_seconds NOT BETWEEN 60 AND 1800 THEN
        RAISE EXCEPTION 'invalid claim parameters';
    END IF;
    RETURN QUERY WITH locked AS (
      SELECT j.job_id FROM public.sxf_base_checkpoint_jobs j
       WHERE (j.state IN('PENDING','RETRY') AND j.next_attempt_at<=now())
          OR (j.state='LEASED' AND j.lease_expires_at<now())
       ORDER BY
         CASE WHEN j.checkpoint_at >= now()-INTERVAL '3 hours' THEN 0 ELSE 1 END,
         CASE WHEN j.family='BASE' AND j.checkpoint_hours IN (8,6) THEN 0 ELSE 1 END,
         j.checkpoint_at,j.job_id LIMIT p_limit
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
REVOKE ALL ON FUNCTION public.sxf_base_claim_due_jobs(text,integer,integer)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sxf_base_claim_due_jobs(text,integer,integer)
  TO service_role;
COMMIT;
