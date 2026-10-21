-- Base WAITING_DATA: allow conservative 6h retries of an already-past immutable source window.
-- The existing token/lease fences and source history are unchanged.
-- No deletion, terminal mark, invented snapshot, or rule edit.
BEGIN;
CREATE OR REPLACE FUNCTION public.sxf_base_wait_for_data(p_job_id uuid, p_lease_token uuid, p_reason text DEFAULT 'INSUFFICIENT_DATA'::text, p_retry_seconds integer DEFAULT 180)
 RETURNS boolean
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
BEGIN
    IF p_reason NOT IN ('INSUFFICIENT_DATA','SOURCE_LAG','SOURCE_INCOMPLETE')
       OR p_retry_seconds NOT BETWEEN 60 AND 21600 THEN
        RAISE EXCEPTION 'invalid missing-data retry parameters';
    END IF;
    UPDATE public.sxf_base_checkpoint_jobs j
    SET state='WAITING_DATA',next_attempt_at=now()+make_interval(secs=>p_retry_seconds),
        waiting_since=COALESCE(j.waiting_since,now()),last_error_code=p_reason,
        lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL
    WHERE j.job_id=p_job_id AND j.lease_token=p_lease_token
      AND j.state='LEASED' AND j.lease_expires_at>now();
    RETURN FOUND;
END $function$;
REVOKE ALL ON FUNCTION public.sxf_base_wait_for_data(uuid,uuid,text,integer)
FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sxf_base_wait_for_data(uuid,uuid,text,integer)
TO service_role;
COMMIT;
