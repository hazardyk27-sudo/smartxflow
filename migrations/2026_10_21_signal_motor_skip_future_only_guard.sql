-- Part 3 additive safety hardening. Migration 1 already exists in production.
-- Only skip an incomplete checkpoint while its physical match has NOT kicked off.
-- Preserve the exact lease token, terminal job audit, historical signals and
-- source rows. Applied after a verified worker drain and before new worker resume.
BEGIN;
CREATE OR REPLACE FUNCTION public.sxf_base_skip_missing_source(
    p_job_id uuid, p_lease_token uuid, p_reason text DEFAULT 'SOURCE_INCOMPLETE'
) RETURNS boolean
LANGUAGE plpgsql
SET search_path TO 'public','pg_temp'
AS $function$
BEGIN
    IF p_job_id IS NULL OR p_lease_token IS NULL
       OR p_reason IS DISTINCT FROM 'SOURCE_INCOMPLETE' THEN
        RAISE EXCEPTION 'invalid source skip parameters';
    END IF;
    UPDATE public.sxf_base_checkpoint_jobs j
       SET state='SKIPPED_DATA',last_error_code=p_reason,
           waiting_since=COALESCE(j.waiting_since,now()),
           lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL
     WHERE j.job_id=p_job_id
       AND j.lease_token=p_lease_token
       AND j.state='LEASED'
       AND j.lease_expires_at>now()
       AND j.checkpoint_at<=now()
       AND j.run_after<=now()
       AND j.kickoff_utc>now();
    RETURN FOUND;
END;
$function$;
REVOKE ALL ON FUNCTION public.sxf_base_skip_missing_source(uuid,uuid,text)
    FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sxf_base_skip_missing_source(uuid,uuid,text)
    TO service_role;
COMMIT;
