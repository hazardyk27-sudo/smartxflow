-- SmartXFlow 2026-10-26: starvation-free eligible T-6 reconciliation claims.
-- No DELETE/TRUNCATE/DROP and no mutation of existing event/queue rows.
-- Keep the exact lease fencing, worker/ruleset validation and RETURN signature.
-- Old WAITING_DATA retries must not permanently outrank never-attempted
-- PENDING items merely because their reconciliation_id is smaller.
CREATE OR REPLACE FUNCTION public.sxf_base_claim_reconcile(
    p_worker text, p_limit integer DEFAULT 1, p_lease_seconds integer DEFAULT 900)
RETURNS TABLE(reconciliation_id bigint, origin_event_key text, fixture_uid uuid,
    kickoff_utc timestamptz, market text, lease_token uuid, attempt_count integer)
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
BEGIN
    IF p_worker IS NULL OR length(btrim(p_worker)) NOT BETWEEN 1 AND 100
       OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 10
       OR p_lease_seconds IS NULL OR p_lease_seconds NOT BETWEEN 60 AND 1800 THEN
        RAISE EXCEPTION 'invalid reconcile claim';
    END IF;
    RETURN QUERY WITH locked AS (
      SELECT r.reconciliation_id FROM public.sxf_base_reconcile_jobs r
      WHERE EXISTS (
        SELECT 1 FROM public.sxf_base_signal_events e
        WHERE e.event_key=r.origin_event_key
          AND e.ruleset_version='SXF_SIGNAL_MOTOR_V3_2026_10_24'
      )
        AND ((r.state IN ('PENDING','RETRY','WAITING_DATA')
              AND r.next_attempt_at<=now())
          OR (r.state='LEASED' AND r.lease_expires_at<now()))
      -- Fair due-time ordering: aged never-attempted PENDING items move ahead
      -- of recently scheduled WAITING_DATA retries. Expired leases retain
      -- their own expiry time as due-at, never an obsolete original due time.
      ORDER BY CASE WHEN r.state='LEASED' THEN r.lease_expires_at
                    ELSE r.next_attempt_at END ASC,
               r.reconciliation_id ASC
      LIMIT p_limit FOR UPDATE OF r SKIP LOCKED
    ), updated AS (
      UPDATE public.sxf_base_reconcile_jobs r
      SET state='LEASED', lease_owner=p_worker,lease_token=gen_random_uuid(),
          lease_expires_at=now()+make_interval(secs=>p_lease_seconds),
          attempt_count=r.attempt_count+1
      FROM locked l WHERE r.reconciliation_id=l.reconciliation_id
      RETURNING r.*
    ) SELECT u.reconciliation_id,u.origin_event_key,u.fixture_uid,u.kickoff_utc,
             u.market,u.lease_token,u.attempt_count FROM updated u
      ORDER BY u.reconciliation_id;
END $$;

REVOKE ALL ON FUNCTION public.sxf_base_claim_reconcile(text,integer,integer)
    FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sxf_base_claim_reconcile(text,integer,integer)
    TO service_role;
