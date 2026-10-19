-- SXF Base Signals Part 4C2: persistent late-T6 reconcile queue, SOURCE ONLY.
-- Depends on 2026_10_18 durable, 2026_10_19 4A and 4B2 SQL.
-- DO NOT APPLY TO LIVE SUPABASE WITHOUT USER APPROVAL.
BEGIN;

CREATE TABLE IF NOT EXISTS public.sxf_base_reconcile_jobs (
    reconciliation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    origin_event_id bigint NOT NULL UNIQUE REFERENCES public.sxf_base_signal_events(event_id) ON DELETE RESTRICT,
    origin_event_key text NOT NULL UNIQUE,
    fixture_uid uuid NOT NULL,
    kickoff_utc timestamptz NOT NULL,
    market text NOT NULL CHECK (market IN ('1X2','OU25','BTTS')),
    state text NOT NULL DEFAULT 'PENDING'
        CHECK (state IN ('PENDING','LEASED','RETRY','WAITING_DATA','COMPLETED')),
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count>=0),
    lease_owner text,
    lease_token uuid,
    lease_expires_at timestamptz,
    last_checked_at timestamptz,
    last_source_observed_at timestamptz,
    last_error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);
CREATE INDEX IF NOT EXISTS sxf_base_reconcile_due_idx
    ON public.sxf_base_reconcile_jobs(next_attempt_at,reconciliation_id)
    WHERE state IN ('PENDING','RETRY','WAITING_DATA');
CREATE INDEX IF NOT EXISTS sxf_base_reconcile_lease_idx
    ON public.sxf_base_reconcile_jobs(lease_expires_at,reconciliation_id)
    WHERE state='LEASED';
CREATE INDEX IF NOT EXISTS sxf_base_reconcile_fixture_idx
    ON public.sxf_base_reconcile_jobs(fixture_uid,kickoff_utc,market);

ALTER TABLE public.sxf_base_reconcile_jobs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.sxf_base_reconcile_jobs FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.sxf_base_reconcile_jobs TO service_role;
GRANT USAGE,SELECT ON SEQUENCE public.sxf_base_reconcile_jobs_reconciliation_id_seq TO service_role;

-- The queue is populated within the original atomic T6 job commit: if that
-- transaction rolls back, the reconciliation job never becomes visible.
CREATE OR REPLACE FUNCTION public.sxf_base_queue_late_t6()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
BEGIN
    IF NEW.kind='MARKET_DECISION' AND NEW.family='BASE'
       AND NEW.job_checkpoint_hours=6
       AND NEW.source_checkpoint_hours IS DISTINCT FROM 6 THEN
        INSERT INTO public.sxf_base_reconcile_jobs
          (origin_event_id,origin_event_key,fixture_uid,kickoff_utc,market)
        VALUES(NEW.event_id,NEW.event_key,NEW.fixture_uid,NEW.kickoff_utc,NEW.market)
        ON CONFLICT (origin_event_id) DO NOTHING;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER sxf_base_queue_late_t6_after_event
    AFTER INSERT ON public.sxf_base_signal_events
    FOR EACH ROW EXECUTE FUNCTION public.sxf_base_queue_late_t6();

-- A bounded bootstrap if migration is installed after some T6 jobs completed.
-- Repeated calls walk forward because already-enqueued events are excluded.
CREATE OR REPLACE FUNCTION public.sxf_base_backfill_reconcile(p_limit integer DEFAULT 100)
RETURNS integer LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE v_added integer;
BEGIN
    IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 500 THEN
        RAISE EXCEPTION 'invalid reconciliation bootstrap batch';
    END IF;
    WITH candidate AS (
      SELECT e.event_id,e.event_key,e.fixture_uid,e.kickoff_utc,e.market
      FROM public.sxf_base_signal_events e
      JOIN public.sxf_base_checkpoint_jobs j ON j.job_id=e.job_id
      WHERE e.kind='MARKET_DECISION' AND e.family='BASE'
        AND e.job_checkpoint_hours=6 AND e.source_checkpoint_hours IS DISTINCT FROM 6
        AND j.state='COMPLETED'
        AND NOT EXISTS(SELECT 1 FROM public.sxf_base_reconcile_jobs r
                       WHERE r.origin_event_id=e.event_id)
      ORDER BY e.event_id
      LIMIT p_limit
    ), inserted AS (
      INSERT INTO public.sxf_base_reconcile_jobs
        (origin_event_id,origin_event_key,fixture_uid,kickoff_utc,market)
      SELECT event_id,event_key,fixture_uid,kickoff_utc,market FROM candidate
      ON CONFLICT (origin_event_id) DO NOTHING
      RETURNING reconciliation_id
    ) SELECT count(*) INTO v_added FROM inserted;
    RETURN v_added;
END $$;

CREATE OR REPLACE FUNCTION public.sxf_base_claim_reconcile(
    p_worker text,p_limit integer DEFAULT 1,p_lease_seconds integer DEFAULT 900)
RETURNS TABLE(reconciliation_id bigint,origin_event_key text,fixture_uid uuid,
    kickoff_utc timestamptz,market text,lease_token uuid,attempt_count integer)
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
BEGIN
    IF p_worker IS NULL OR length(btrim(p_worker)) NOT BETWEEN 1 AND 100
       OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 10
       OR p_lease_seconds IS NULL OR p_lease_seconds NOT BETWEEN 60 AND 1800 THEN
        RAISE EXCEPTION 'invalid reconcile claim';
    END IF;
    RETURN QUERY WITH locked AS (
      SELECT r.reconciliation_id FROM public.sxf_base_reconcile_jobs r
      WHERE (r.state IN ('PENDING','RETRY','WAITING_DATA') AND r.next_attempt_at<=now())
         OR (r.state='LEASED' AND r.lease_expires_at<now())
      ORDER BY r.reconciliation_id LIMIT p_limit FOR UPDATE SKIP LOCKED
    ), updated AS (
      UPDATE public.sxf_base_reconcile_jobs r
      SET state='LEASED',lease_owner=p_worker,lease_token=gen_random_uuid(),
          lease_expires_at=now()+make_interval(secs=>p_lease_seconds),
          attempt_count=r.attempt_count+1
      FROM locked l WHERE r.reconciliation_id=l.reconciliation_id
      RETURNING r.*
    ) SELECT u.reconciliation_id,u.origin_event_key,u.fixture_uid,u.kickoff_utc,
             u.market,u.lease_token,u.attempt_count FROM updated u
      ORDER BY u.reconciliation_id;
END $$;

CREATE OR REPLACE FUNCTION public.sxf_base_renew_reconcile(
    p_reconciliation_id bigint,p_lease_token uuid,p_lease_seconds integer DEFAULT 900)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
BEGIN
    IF p_lease_seconds IS NULL OR p_lease_seconds NOT BETWEEN 60 AND 1800 THEN
        RAISE EXCEPTION 'invalid reconcile renewal';
    END IF;
    UPDATE public.sxf_base_reconcile_jobs r
      SET lease_expires_at=now()+make_interval(secs=>p_lease_seconds)
    WHERE r.reconciliation_id=p_reconciliation_id
      AND r.state='LEASED' AND r.lease_token=p_lease_token AND r.lease_expires_at>now();
    RETURN FOUND;
END $$;

CREATE OR REPLACE FUNCTION public.sxf_base_retry_reconcile(
    p_reconciliation_id bigint,p_lease_token uuid,
    p_reason text DEFAULT 'SOURCE_INCOMPLETE',p_delay_seconds integer DEFAULT 900)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
BEGIN
    IF p_reason IS NULL OR p_reason !~ '^[A-Z0-9_]{1,64}$'
       OR p_delay_seconds IS NULL OR p_delay_seconds NOT BETWEEN 60 AND 3600 THEN
        RAISE EXCEPTION 'invalid reconcile retry';
    END IF;
    UPDATE public.sxf_base_reconcile_jobs r
      SET state=CASE WHEN p_reason='SOURCE_INCOMPLETE' THEN 'WAITING_DATA' ELSE 'RETRY' END,
          next_attempt_at=now()+make_interval(secs=>p_delay_seconds),
          last_checked_at=now(),last_error_code=p_reason,
          lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL
    WHERE r.reconciliation_id=p_reconciliation_id AND r.lease_token=p_lease_token
      AND r.state='LEASED' AND r.lease_expires_at>now();
    RETURN FOUND;
END $$;

-- Entire correction batch and final queue completion are ONE transaction.
-- Preexisting 4B2 RPC revalidates source market/UID/scrape timestamp and
-- enforces deterministic append-only idempotency for each correction event.
CREATE OR REPLACE FUNCTION public.sxf_base_complete_reconcile(
    p_reconciliation_id bigint,p_lease_token uuid,p_snapshot_ids bigint[],
    p_signals jsonb,p_evidence jsonb DEFAULT '{}'::jsonb)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE
    r public.sxf_base_reconcile_jobs%ROWTYPE;
    s jsonb;
    v_kind text;
    v_engine text;
    v_side text;
    v_seen text[] := ARRAY[]::text[];
    v_observed timestamptz;
    v_odds numeric;
    v_amount numeric;
    v_share numeric;
    v_snapshot_observed timestamptz;
    v_details jsonb;
    v_counter integer := 0;
BEGIN
    SELECT * INTO r FROM public.sxf_base_reconcile_jobs
      WHERE reconciliation_id=p_reconciliation_id FOR UPDATE;
    IF NOT FOUND OR r.state<>'LEASED' OR r.lease_token IS DISTINCT FROM p_lease_token
       OR r.lease_expires_at<=now() THEN
        RAISE EXCEPTION 'missing, expired or foreign reconciliation lease';
    END IF;
    IF p_signals IS NULL OR jsonb_typeof(p_signals)<>'array'
       OR jsonb_array_length(p_signals)>12 OR p_evidence IS NULL
       OR jsonb_typeof(p_evidence)<>'object' OR length(p_evidence::text)>4096 THEN
        RAISE EXCEPTION 'invalid correction batch';
    END IF;
    IF p_snapshot_ids IS NULL OR cardinality(p_snapshot_ids) NOT IN (2,3)
       OR array_position(p_snapshot_ids,NULL) IS NOT NULL THEN
        RAISE EXCEPTION 'invalid correction source list';
    END IF;
    SELECT min(scraped_at_utc) INTO v_snapshot_observed
    FROM public.moneyway_snapshots
    WHERE id=ANY(p_snapshot_ids) AND fixture_uid=r.fixture_uid AND market=r.market;
    IF v_snapshot_observed IS NULL THEN
        RAISE EXCEPTION 'correction source missing';
    END IF;
    -- Prevent worker-provided details from rewriting authoritative lineage.
    v_details:=p_evidence || jsonb_build_object('reconciliation_id',r.reconciliation_id,
        'claim_attempt',r.attempt_count,'reconciliation_type','LATE_T6');

    IF jsonb_array_length(p_signals)=0 THEN
        PERFORM public.sxf_base_append_reconciliation(
           r.origin_event_key,'CORRECTED',p_snapshot_ids,
           v_details||jsonb_build_object('decision','NO_HIT'),NULL,NULL);
    ELSE
        FOR s IN SELECT value FROM jsonb_array_elements(p_signals) LOOP
            v_engine:=s->>'engine';
            v_side:=s->>'side';
            IF jsonb_typeof(s)<>'object' OR v_engine IS NULL OR v_side IS NULL
               OR (s->>'checkpoint')::integer IS DISTINCT FROM 6
               OR s->>'observed_at' IS NULL
               OR (s->>'observed_at')::timestamptz IS DISTINCT FROM v_snapshot_observed
               OR v_engine||':'||v_side = ANY(v_seen) THEN
                RAISE EXCEPTION 'correction hit payload mismatch';
            END IF;
            v_seen:=array_append(v_seen,v_engine||':'||v_side);
            SELECT q.odds,q.volume,q.share INTO v_odds,v_amount,v_share
            FROM public.moneyway_snapshots q
            WHERE q.id=ANY(p_snapshot_ids) AND q.fixture_uid=r.fixture_uid
              AND q.market=r.market AND q.selection=v_side;
            IF NOT FOUND OR (s->>'odds')::numeric IS DISTINCT FROM v_odds
               OR (s->>'amount')::numeric IS DISTINCT FROM v_amount
               OR (s->>'share')::numeric IS DISTINCT FROM v_share THEN
                RAISE EXCEPTION 'correction market quote does not match source';
            END IF;
            PERFORM public.sxf_base_append_reconciliation(
               r.origin_event_key,'CORRECTED',p_snapshot_ids,
               v_details||jsonb_build_object('decision','HIT','signal',s),
               v_engine,v_side);
            v_counter:=v_counter+1;
        END LOOP;
    END IF;
    UPDATE public.sxf_base_reconcile_jobs
      SET state='COMPLETED',completed_at=now(),last_checked_at=now(),
          last_source_observed_at=v_snapshot_observed,
          lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,last_error_code=NULL
    WHERE reconciliation_id=r.reconciliation_id;
    RETURN true;
END $$;

REVOKE ALL ON FUNCTION public.sxf_base_backfill_reconcile(integer),
    public.sxf_base_claim_reconcile(text,integer,integer),
    public.sxf_base_renew_reconcile(bigint,uuid,integer),
    public.sxf_base_retry_reconcile(bigint,uuid,text,integer),
    public.sxf_base_complete_reconcile(bigint,uuid,bigint[],jsonb,jsonb)
    FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sxf_base_backfill_reconcile(integer),
    public.sxf_base_claim_reconcile(text,integer,integer),
    public.sxf_base_renew_reconcile(bigint,uuid,integer),
    public.sxf_base_retry_reconcile(bigint,uuid,text,integer),
    public.sxf_base_complete_reconcile(bigint,uuid,bigint[],jsonb,jsonb) TO service_role;
COMMIT;
