-- SmartXFlow Base Signals Part 5B: outbox observability (source-only).
-- Does NOT enable triggers, workers, writes, or run an index on live systems.
BEGIN;
CREATE OR REPLACE FUNCTION public.sxf_base_source_health()
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path=pg_catalog,public AS $$
DECLARE
    v_delivery jsonb;
    v_kinds jsonb;
BEGIN
    SELECT jsonb_build_object(
        'total',count(*),
        'pending_due',count(*) FILTER (WHERE state IN ('PENDING','RETRY')
                                              AND next_attempt_at<=now()),
        'retry',count(*) FILTER (WHERE state='RETRY'),
        'leased',count(*) FILTER (WHERE state='LEASED'),
        'expired_leases',count(*) FILTER (WHERE state='LEASED' AND lease_expires_at<now()),
        'done',count(*) FILTER (WHERE state='DONE'),
        'review_required',count(*) FILTER (WHERE state='RETRY'
            AND last_error_code='SOURCE_MUTATION_REVIEW'),
        'oldest_due_seconds',max(GREATEST(0,EXTRACT(EPOCH FROM now()-c.captured_at)))
            FILTER (WHERE d.state IN ('PENDING','RETRY') AND d.next_attempt_at<=now()),
        'last_source_capture_at',max(c.captured_at)
    ) INTO v_delivery
      FROM public.sxf_base_source_changes c
      JOIN public.sxf_base_source_deliveries d ON d.change_id=c.change_id;

    SELECT COALESCE(jsonb_object_agg(kind,cnt),'{}'::jsonb) INTO v_kinds
    FROM (
        SELECT event_kind AS kind,count(*) AS cnt
        FROM public.sxf_base_source_changes GROUP BY event_kind
    ) grouped;
    RETURN jsonb_build_object(
       'captured_at_semantics','TRIGGER_TIME_NOT_COMMIT_TIME',
       'source_commit_watermark',NULL,
       'source_delivery',v_delivery,
       'event_kinds',v_kinds
    );
END $$;
REVOKE ALL ON FUNCTION public.sxf_base_source_health()
    FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sxf_base_source_health()
    TO service_role;
COMMIT;
