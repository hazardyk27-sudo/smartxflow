-- SXF Base Signals Part 4C4D: bounded read-only market event projection RPC.
-- SOURCE ONLY. Do not apply to live Supabase without explicit user approval.
BEGIN;
CREATE OR REPLACE FUNCTION public.sxf_base_read_market_events(
    p_fixture_uid uuid, p_kickoff_utc timestamptz)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path=pg_catalog,public AS $$
DECLARE
    v_count integer;
    v_events jsonb;
BEGIN
    IF p_fixture_uid IS NULL OR p_kickoff_utc IS NULL THEN
        RAISE EXCEPTION 'missing physical fixture identity';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.fixtures f
        WHERE f.fixture_uid=p_fixture_uid AND f.kickoff_utc=p_kickoff_utc
    ) THEN
        RETURN jsonb_build_object('fixture_authoritative',false,'events','[]'::jsonb);
    END IF;

    SELECT count(*) INTO v_count
    FROM public.sxf_base_signal_events e
    JOIN public.sxf_base_checkpoint_jobs j ON j.job_id=e.job_id
    WHERE e.fixture_uid=p_fixture_uid AND e.kickoff_utc=p_kickoff_utc
      AND j.state='COMPLETED'
      AND e.family='BASE'
      AND e.kind IN ('PRELIMINARY_SIGNAL','FINAL_SIGNAL','MARKET_DECISION','CORRECTED');
    IF v_count>500 THEN
        RAISE EXCEPTION 'projection event count exceeds bounded limit';
    END IF;
    SELECT COALESCE(jsonb_agg(jsonb_build_object(
        'event_id',e.event_id,'event_key',e.event_key,'kind',e.kind,
        'market',e.market,'job_checkpoint_hours',e.job_checkpoint_hours,
        'source_checkpoint_hours',e.source_checkpoint_hours,
        'engine',e.engine,'selection',e.selection,
        'origin_event_key',e.details->>'origin_event_key',
        'decision',e.details->>'decision',
        'reconciled',r.reconciliation_id IS NOT NULL
    ) ORDER BY e.event_id),'[]'::jsonb)
    INTO v_events
    FROM public.sxf_base_signal_events e
    JOIN public.sxf_base_checkpoint_jobs j ON j.job_id=e.job_id
    LEFT JOIN public.sxf_base_reconcile_jobs r
      ON e.kind='CORRECTED' AND r.origin_event_key=e.details->>'origin_event_key'
        AND r.reconciliation_id::text=e.details->>'reconciliation_id'
        AND r.state='COMPLETED'
    WHERE e.fixture_uid=p_fixture_uid AND e.kickoff_utc=p_kickoff_utc
      AND j.state='COMPLETED'
      AND e.family='BASE'
      AND e.kind IN ('PRELIMINARY_SIGNAL','FINAL_SIGNAL','MARKET_DECISION','CORRECTED');
    RETURN jsonb_build_object('fixture_authoritative',true,'events',v_events);
END $$;
REVOKE ALL ON FUNCTION public.sxf_base_read_market_events(uuid,timestamptz)
    FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sxf_base_read_market_events(uuid,timestamptz)
    TO service_role;
COMMIT;
