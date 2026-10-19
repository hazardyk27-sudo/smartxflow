-- SmartXFlow Base Signals Part 4B2. SOURCE ONLY; NOT DEPLOYED.
-- Depends on 2026_10_18 durable queue and 2026_10_19 Part 4A hardening.
-- An explicit, immutable T-6 reconciliation event. This is NOT an auto-run worker.
BEGIN;

CREATE OR REPLACE FUNCTION public.sxf_base_append_reconciliation(
    p_origin_event_key text,
    p_kind text,
    p_source_snapshot_ids bigint[],
    p_details jsonb DEFAULT '{}'::jsonb,
    p_engine text DEFAULT NULL,
    p_selection text DEFAULT NULL
)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog,public AS $$
DECLARE
    v_origin public.sxf_base_signal_events%ROWTYPE;
    v_previous public.sxf_base_signal_events%ROWTYPE;
    v_engine text;
    v_selection text;
    v_expected text[];
    v_sides text[];
    v_count integer;
    v_timestamps integer;
    v_observed timestamptz;
    v_share numeric;
    v_min_odds numeric;
    v_min_amount numeric;
    v_min_share numeric;
    v_max_share numeric;
    v_at timestamptz;
    v_details jsonb;
    v_key text;
    v_ids bigint[];
    v_added bigint;
BEGIN
    IF p_origin_event_key IS NULL OR length(p_origin_event_key) NOT BETWEEN 1 AND 450
       OR p_kind IS NULL OR p_kind NOT IN ('CONFIRMED','INVALIDATED','CORRECTED')
       OR p_details IS NULL OR jsonb_typeof(p_details)<>'object'
       OR length(p_details::text)>8192
       OR p_source_snapshot_ids IS NULL OR cardinality(p_source_snapshot_ids) NOT IN (2,3)
       OR array_position(p_source_snapshot_ids, NULL) IS NOT NULL THEN
        RAISE EXCEPTION 'invalid reconciliation request';
    END IF;

    SELECT e.* INTO v_origin
      FROM public.sxf_base_signal_events e
      JOIN public.sxf_base_checkpoint_jobs j ON j.job_id=e.job_id
      WHERE e.event_key=p_origin_event_key AND j.state='COMPLETED';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'reconciliation origin not completed or missing';
    END IF;
    IF v_origin.family<>'BASE' THEN
        RAISE EXCEPTION 'only Base market reconciliation is supported';
    END IF;

    IF p_kind='CORRECTED' THEN
        IF v_origin.kind<>'MARKET_DECISION' OR v_origin.job_checkpoint_hours<>6
           OR (p_engine IS NULL) <> (p_selection IS NULL) THEN
            RAISE EXCEPTION 'correction requires T-6 market decision and matched engine/selection';
        END IF;
        v_engine:=p_engine;
        v_selection:=p_selection;
    ELSE
        IF v_origin.kind<>'PRELIMINARY_SIGNAL' OR v_origin.job_checkpoint_hours<>8
           OR p_engine IS NOT NULL OR p_selection IS NOT NULL THEN
            RAISE EXCEPTION 'confirmation/invalidation requires preliminary signal';
        END IF;
        v_engine:=v_origin.engine;
        v_selection:=v_origin.selection;
    END IF;

    v_expected := CASE v_origin.market
        WHEN '1X2' THEN ARRAY['1','2','X']::text[]
        WHEN 'OU25' THEN ARRAY['O','U']::text[]
        WHEN 'BTTS' THEN ARRAY['N','Y']::text[]
        ELSE NULL END;
    IF v_expected IS NULL OR cardinality(p_source_snapshot_ids) <> cardinality(v_expected) THEN
        RAISE EXCEPTION 'wrong reconciliation market cardinality';
    END IF;

    IF v_engine IS NOT NULL AND NOT (
        (v_origin.market='1X2' AND v_selection IN ('1','2')
          AND v_engine IN ('1X2_CONCENTRATION_V1','1X2_CONCENTRATION_V2',
                           'HEAVY_1X2_CONCENTRATION','SURPRISE_TEAM'))
        OR (v_origin.market='OU25' AND v_selection='O'
          AND v_engine IN ('STABLE_OVER_2_5','PREMIUM_OVER_2_5','PREMIUM_OVER_MIN1_70'))
        OR (v_origin.market='BTTS' AND v_selection='Y' AND v_engine='BTTS_YES')
    ) THEN
        RAISE EXCEPTION 'engine/selection mismatch in reconciliation';
    END IF;

    SELECT count(*),count(DISTINCT s.scraped_at_utc),
           array_agg(s.selection ORDER BY s.selection),min(s.scraped_at_utc),
           sum(s.share),min(s.odds),min(s.volume),min(s.share),max(s.share)
      INTO v_count,v_timestamps,v_sides,v_observed,v_share,
           v_min_odds,v_min_amount,v_min_share,v_max_share
      FROM public.moneyway_snapshots s
      WHERE s.id=ANY(p_source_snapshot_ids)
        AND s.fixture_uid=v_origin.fixture_uid
        AND s.market=v_origin.market;
    v_at := v_origin.kickoff_utc - INTERVAL '6 hours';
    IF v_count<>cardinality(v_expected) OR v_timestamps<>1 OR v_sides<>v_expected
       OR v_observed NOT BETWEEN v_at - INTERVAL '30 minutes' AND v_at
       OR v_share NOT BETWEEN 99.5 AND 100.5
       OR v_min_odds IS NULL OR v_min_odds<1 OR v_min_amount<0
       OR v_min_share<0 OR v_max_share>100 THEN
        RAISE EXCEPTION 'incomplete, cross-fixture, or post-checkpoint source evidence';
    END IF;

    -- Caller may attach machine-derived metrics, but never override validated
    -- identity, timestamp, source-row provenance or origin lineage.
    SELECT array_agg(x ORDER BY x) INTO v_ids
      FROM unnest(p_source_snapshot_ids) AS input_ids(x);
    v_details:=p_details || jsonb_build_object(
        'origin_event_key',v_origin.event_key,
        'origin_event_id',v_origin.event_id,
        'source_snapshot_ids',v_ids,
        'source_observed_at',v_observed,
        'source_checkpoint_hours',6,
        'source_market',v_origin.market);
    v_key:=v_origin.event_key||':RECON:'||p_kind||':'||
        md5(v_details::text||':'||coalesce(v_engine,'')||':'||coalesce(v_selection,''));

    INSERT INTO public.sxf_base_signal_events (
        event_key,job_id,fixture_uid,kickoff_utc,ruleset_version,family,
        job_checkpoint_hours,source_checkpoint_hours,market,engine,selection,kind,details)
    VALUES (
        v_key,v_origin.job_id,v_origin.fixture_uid,v_origin.kickoff_utc,
        v_origin.ruleset_version,v_origin.family,v_origin.job_checkpoint_hours,
        6,v_origin.market,v_engine,v_selection,p_kind,v_details)
    ON CONFLICT (event_key) DO NOTHING
    RETURNING event_id INTO v_added;
    IF v_added IS NOT NULL THEN
        RETURN true;
    END IF;
    SELECT * INTO v_previous FROM public.sxf_base_signal_events WHERE event_key=v_key;
    IF NOT FOUND OR v_previous.job_id IS DISTINCT FROM v_origin.job_id
       OR v_previous.kind IS DISTINCT FROM p_kind
       OR v_previous.details IS DISTINCT FROM v_details
       OR v_previous.engine IS DISTINCT FROM v_engine
       OR v_previous.selection IS DISTINCT FROM v_selection
       OR v_previous.source_checkpoint_hours IS DISTINCT FROM 6 THEN
        RAISE EXCEPTION 'reconciliation idempotency conflict';
    END IF;
    RETURN false;
END $$;

REVOKE ALL ON FUNCTION public.sxf_base_append_reconciliation(
    text,text,bigint[],jsonb,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sxf_base_append_reconciliation(
    text,text,bigint[],jsonb,text,text) TO service_role;
COMMIT;
