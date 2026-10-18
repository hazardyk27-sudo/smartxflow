-- SmartXFlow Base Signals Phase 4: PROPOSED ONLY; DO NOT APPLY WITHOUT APPROVAL.
-- Creates isolated DB-backed checkpoint jobs, immutable evaluations/events and atomic RPCs.
-- Must be executed as one migration transaction by a privileged deployment operator.
BEGIN;

CREATE TABLE IF NOT EXISTS public.sxf_base_checkpoint_jobs (
    job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_key text NOT NULL UNIQUE,
    ruleset_version text NOT NULL,
    fixture_uid uuid NOT NULL,
    kickoff_utc timestamptz NOT NULL,
    checkpoint_hours smallint NOT NULL,
    family text NOT NULL,
    checkpoint_at timestamptz NOT NULL,
    run_after timestamptz NOT NULL,
    state text NOT NULL DEFAULT 'PENDING' CHECK (state IN ('PENDING','LEASED','RETRY','COMPLETED')),
    next_attempt_at timestamptz NOT NULL,
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    lease_owner text,
    lease_token uuid,
    lease_expires_at timestamptz,
    last_error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    CONSTRAINT sxf_base_job_family_ck CHECK (
        (family='EARLY_CORE' AND checkpoint_hours IN (72,60,40,24)) OR
        (family='EARLY_T12' AND checkpoint_hours=12) OR
        (family='BASE' AND checkpoint_hours IN (8,6)) OR
        (family='EARLY_RETENTION' AND checkpoint_hours IN (6,5,4,3))
    ),
    CONSTRAINT sxf_base_job_checkpoint_ck CHECK (checkpoint_at = kickoff_utc - checkpoint_hours * INTERVAL '1 hour'),
    CONSTRAINT sxf_base_job_unique UNIQUE(ruleset_version,fixture_uid,kickoff_utc,family,checkpoint_hours)
);
CREATE INDEX IF NOT EXISTS sxf_base_jobs_pending_idx
    ON public.sxf_base_checkpoint_jobs(next_attempt_at,checkpoint_at,job_id)
    WHERE state IN ('PENDING','RETRY');
CREATE INDEX IF NOT EXISTS sxf_base_jobs_expired_idx
    ON public.sxf_base_checkpoint_jobs(lease_expires_at,checkpoint_at,job_id)
    WHERE state='LEASED';
CREATE INDEX IF NOT EXISTS sxf_base_jobs_fixture_idx
    ON public.sxf_base_checkpoint_jobs(fixture_uid,kickoff_utc);

CREATE TABLE IF NOT EXISTS public.sxf_base_checkpoint_evaluations (
    evaluation_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id uuid NOT NULL UNIQUE REFERENCES public.sxf_base_checkpoint_jobs(job_id) ON DELETE RESTRICT,
    job_key text NOT NULL UNIQUE,
    ruleset_version text NOT NULL,
    fixture_uid uuid NOT NULL,
    kickoff_utc timestamptz NOT NULL,
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload)='object'),
    recorded_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.sxf_base_signal_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_key text NOT NULL UNIQUE,
    job_id uuid NOT NULL REFERENCES public.sxf_base_checkpoint_jobs(job_id) ON DELETE RESTRICT,
    fixture_uid uuid NOT NULL,
    kickoff_utc timestamptz NOT NULL,
    ruleset_version text NOT NULL,
    family text NOT NULL,
    job_checkpoint_hours smallint NOT NULL,
    source_checkpoint_hours smallint,
    market text NOT NULL CHECK (market IN ('1X2','OU25','BTTS')),
    engine text,
    selection text,
    kind text NOT NULL CHECK (kind IN ('PRELIMINARY_SIGNAL','FINAL_SIGNAL','EARLY_SIGNAL','MARKET_DECISION','RETENTION_CHECK')),
    details jsonb NOT NULL CHECK (jsonb_typeof(details)='object'),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT sxf_base_event_selection_ck CHECK (
       selection IS NULL OR (market='1X2' AND selection IN ('1','X','2')) OR
       (market='OU25' AND selection IN ('O','U')) OR
       (market='BTTS' AND selection IN ('Y','N'))
    )
);
CREATE INDEX IF NOT EXISTS sxf_base_events_fixture_idx
    ON public.sxf_base_signal_events(fixture_uid,kickoff_utc,recorded_at);
CREATE INDEX IF NOT EXISTS sxf_base_events_job_idx ON public.sxf_base_signal_events(job_id);

CREATE OR REPLACE FUNCTION public.sxf_base_append_only_guard()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN
   RAISE EXCEPTION 'SXF Base audit records are append-only';
END $$;
CREATE TRIGGER sxf_base_checkpoint_eval_immutable
    BEFORE UPDATE OR DELETE ON public.sxf_base_checkpoint_evaluations
    FOR EACH ROW EXECUTE FUNCTION public.sxf_base_append_only_guard();
CREATE TRIGGER sxf_base_signal_events_immutable
    BEFORE UPDATE OR DELETE ON public.sxf_base_signal_events
    FOR EACH ROW EXECUTE FUNCTION public.sxf_base_append_only_guard();

CREATE OR REPLACE FUNCTION public.sxf_base_enqueue_jobs(p_jobs jsonb)
RETURNS integer LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,pg_temp AS $$
DECLARE
    item jsonb;
    v_uid uuid;
    v_kick timestamptz;
    v_hours smallint;
    v_family text;
    v_cp timestamptz;
    v_key text;
    v_ruleset text;
    v_added integer := 0;
    v_count integer;
    v_existing record;
BEGIN
    IF p_jobs IS NULL OR jsonb_typeof(p_jobs)<>'array' OR jsonb_array_length(p_jobs)>1000 THEN
        RAISE EXCEPTION 'invalid enqueue batch';
    END IF;
    FOR item IN SELECT value FROM jsonb_array_elements(p_jobs) LOOP
        v_uid := (item->>'fixture_uid')::uuid;
        v_kick := (item->>'kickoff_utc')::timestamptz;
        v_hours := (item->>'checkpoint_hours')::smallint;
        v_family := item->>'family';
        v_key := item->>'job_key';
        v_ruleset := item->>'ruleset_version';
        v_cp := v_kick - v_hours * INTERVAL '1 hour';
        IF v_uid IS NULL OR v_kick IS NULL OR v_hours IS NULL OR v_family IS NULL
            OR v_key IS NULL OR length(v_key)>320 OR v_ruleset <> 'SXF_BASE_V1_2026_10_18'
            OR NOT ((v_family='EARLY_CORE' AND v_hours IN(72,60,40,24))
                 OR (v_family='EARLY_T12' AND v_hours=12)
                 OR (v_family='BASE' AND v_hours IN(8,6))
                 OR (v_family='EARLY_RETENTION' AND v_hours IN(6,5,4,3))) THEN
            RAISE EXCEPTION 'invalid enqueue job';
        END IF;
        -- No phantom/ambiguous fixture identities, no legacy hash-only linking.
        SELECT count(*) INTO v_count FROM public.fixtures f
          WHERE f.fixture_uid=v_uid AND f.kickoff_utc=v_kick;
        IF v_count<>1 THEN
            RAISE EXCEPTION 'fixture identity missing or kickoff drift';
        END IF;
        SELECT job_key,fixture_uid,kickoff_utc,family,checkpoint_hours,ruleset_version
          INTO v_existing FROM public.sxf_base_checkpoint_jobs
          WHERE job_key=v_key OR (ruleset_version=v_ruleset AND fixture_uid=v_uid
                AND kickoff_utc=v_kick AND family=v_family AND checkpoint_hours=v_hours)
          LIMIT 1;
        IF FOUND THEN
            IF v_existing.job_key<>v_key OR v_existing.fixture_uid<>v_uid
                OR v_existing.kickoff_utc<>v_kick OR v_existing.family<>v_family
                OR v_existing.checkpoint_hours<>v_hours OR v_existing.ruleset_version<>v_ruleset THEN
                RAISE EXCEPTION 'enqueue key collision';
            END IF;
            CONTINUE;
        END IF;
        INSERT INTO public.sxf_base_checkpoint_jobs(
            job_key,ruleset_version,fixture_uid,kickoff_utc,checkpoint_hours,family,
            checkpoint_at,run_after,next_attempt_at)
        VALUES(v_key,v_ruleset,v_uid,v_kick,v_hours,v_family,v_cp,v_cp+INTERVAL '10 minutes',v_cp+INTERVAL '10 minutes')
        ON CONFLICT DO NOTHING;
        GET DIAGNOSTICS v_count = ROW_COUNT;
        IF v_count = 0 THEN
            -- Another enqueuer may have won the unique-index race after our check.
            SELECT job_key,fixture_uid,kickoff_utc,family,checkpoint_hours,ruleset_version
              INTO v_existing FROM public.sxf_base_checkpoint_jobs
              WHERE job_key=v_key OR (ruleset_version=v_ruleset AND fixture_uid=v_uid
                AND kickoff_utc=v_kick AND family=v_family AND checkpoint_hours=v_hours)
              LIMIT 1;
            IF NOT FOUND OR v_existing.job_key<>v_key OR v_existing.fixture_uid<>v_uid
                OR v_existing.kickoff_utc<>v_kick OR v_existing.family<>v_family
                OR v_existing.checkpoint_hours<>v_hours OR v_existing.ruleset_version<>v_ruleset THEN
                RAISE EXCEPTION 'concurrent enqueue collision';
            END IF;
        END IF;
        v_added := v_added + v_count;
    END LOOP;
    RETURN v_added;
END $$;

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
       ORDER BY j.checkpoint_at,j.job_id LIMIT p_limit
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

CREATE OR REPLACE FUNCTION public.sxf_base_renew_lease(
    p_job_id uuid,p_lease_token uuid,p_lease_seconds integer DEFAULT 300)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,pg_temp AS $$
BEGIN
  IF p_lease_seconds NOT BETWEEN 60 AND 1800 THEN
     RAISE EXCEPTION 'invalid renewal ttl';
  END IF;
  UPDATE public.sxf_base_checkpoint_jobs j
  SET lease_expires_at=now()+make_interval(secs=>p_lease_seconds)
  WHERE j.job_id=p_job_id AND j.lease_token=p_lease_token
    AND j.state='LEASED' AND j.lease_expires_at>now();
  RETURN FOUND;
END $$;

CREATE OR REPLACE FUNCTION public.sxf_base_fail_job(
    p_job_id uuid,p_lease_token uuid,p_error_code text DEFAULT 'WORKER_ERROR',p_retry_seconds integer DEFAULT 60)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,pg_temp AS $$
BEGIN
    IF p_error_code IS NULL OR p_error_code !~ '^[A-Z_0-9]{1,64}$'
       OR p_retry_seconds NOT BETWEEN 10 AND 3600 THEN
        RAISE EXCEPTION 'invalid failure parameters';
    END IF;
    UPDATE public.sxf_base_checkpoint_jobs j
     SET state='RETRY',next_attempt_at=now()+make_interval(secs=>p_retry_seconds),
         last_error_code=p_error_code,lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL
    WHERE j.job_id=p_job_id AND j.lease_token=p_lease_token
      AND j.state='LEASED' AND j.lease_expires_at>now();
    RETURN FOUND;
END $$;

CREATE OR REPLACE FUNCTION public.sxf_base_complete_job(
    p_job_id uuid,p_lease_token uuid,p_payload jsonb)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,pg_temp AS $$
DECLARE
    j public.sxf_base_checkpoint_jobs%ROWTYPE;
    s jsonb;
    m text;
    v_engine text;
    v_market text;
    v_side text;
    v_cp integer;
    v_kind text;
BEGIN
    SELECT * INTO j FROM public.sxf_base_checkpoint_jobs
      WHERE job_id=p_job_id FOR UPDATE;
    IF NOT FOUND OR j.state<>'LEASED' OR j.lease_token IS DISTINCT FROM p_lease_token
         OR j.lease_expires_at<=now() THEN
        RAISE EXCEPTION 'missing, stale or expired checkpoint lease';
    END IF;
    IF jsonb_typeof(p_payload) IS DISTINCT FROM 'object'
        OR (p_payload->>'key') IS DISTINCT FROM j.job_key
        OR (p_payload->>'fixture_uid') IS DISTINCT FROM j.fixture_uid::text
        OR (p_payload->>'kickoff_utc')::timestamptz IS DISTINCT FROM j.kickoff_utc
        OR (p_payload->>'family') IS DISTINCT FROM j.family
        OR (p_payload->>'checkpoint')::int IS DISTINCT FROM j.checkpoint_hours
        OR (p_payload->>'ruleset') IS DISTINCT FROM j.ruleset_version
        OR jsonb_typeof(p_payload->'signals') IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'checkpoint payload identity mismatch';
    END IF;
    INSERT INTO public.sxf_base_checkpoint_evaluations(
      job_id,job_key,ruleset_version,fixture_uid,kickoff_utc,payload)
    VALUES(j.job_id,j.job_key,j.ruleset_version,j.fixture_uid,j.kickoff_utc,p_payload);
    FOR s IN SELECT value FROM jsonb_array_elements(p_payload->'signals') LOOP
        v_engine:=s->>'engine';v_side:=s->>'side';v_cp:=(s->>'checkpoint')::integer;
        IF v_engine IN('1X2_CONCENTRATION_V1','1X2_CONCENTRATION_V2','HEAVY_1X2_CONCENTRATION',
           'SURPRISE_TEAM','EARLY_MONEY_CORE','EARLY_MONEY_T12') THEN v_market:='1X2';
        ELSIF v_engine IN('STABLE_OVER_2_5','PREMIUM_OVER_2_5','PREMIUM_OVER_MIN1_70') THEN v_market:='OU25';
        ELSIF v_engine='BTTS_YES' THEN v_market:='BTTS';
        ELSE RAISE EXCEPTION 'unknown engine in checkpoint payload'; END IF;
        IF v_cp IS NULL OR v_side NOT IN('1','X','2','O','U','Y','N')
           OR (j.family='BASE' AND (j.checkpoint_hours NOT IN(8,6)
                OR (j.checkpoint_hours=8 AND v_cp<>8)
                OR (j.checkpoint_hours=6 AND v_cp NOT IN(6,8))))
           OR (j.family IN('EARLY_CORE','EARLY_T12') AND v_cp<>j.checkpoint_hours)
           OR j.family='EARLY_RETENTION'
           OR (j.family<>'BASE' AND v_engine NOT IN('EARLY_MONEY_CORE','EARLY_MONEY_T12'))
           OR (j.family='BASE' AND v_engine IN('EARLY_MONEY_CORE','EARLY_MONEY_T12')) THEN
            RAISE EXCEPTION 'invalid checkpoint signal';
        END IF;
        v_kind:=CASE WHEN j.family<>'BASE' THEN 'EARLY_SIGNAL'
                     WHEN j.checkpoint_hours=8 THEN 'PRELIMINARY_SIGNAL'
                     ELSE 'FINAL_SIGNAL' END;
        INSERT INTO public.sxf_base_signal_events (
          event_key,job_id,fixture_uid,kickoff_utc,ruleset_version,family,
          job_checkpoint_hours,source_checkpoint_hours,market,engine,selection,kind,details)
        VALUES (j.job_key||':SIGNAL:'||v_engine||':'||v_side||':T-'||v_cp,
          j.job_id,j.fixture_uid,j.kickoff_utc,j.ruleset_version,j.family,
          j.checkpoint_hours,v_cp,v_market,v_engine,v_side,v_kind,s);
    END LOOP;
    IF j.family='BASE' AND j.checkpoint_hours=6 THEN
       IF jsonb_typeof(p_payload->'markets')<>'object' THEN
          RAISE EXCEPTION 'base market outcomes missing';
       END IF;
       FOREACH m IN ARRAY ARRAY['1X2','OU25','BTTS'] LOOP
          IF p_payload->'markets'->m IS NULL THEN
             RAISE EXCEPTION 'base market outcome missing';
          END IF;
          INSERT INTO public.sxf_base_signal_events (
           event_key,job_id,fixture_uid,kickoff_utc,ruleset_version,family,
           job_checkpoint_hours,source_checkpoint_hours,market,engine,selection,kind,details)
          VALUES (j.job_key||':DECISION:'||m,j.job_id,j.fixture_uid,j.kickoff_utc,
            j.ruleset_version,j.family,6,(p_payload->'markets'->m->>'checkpoint')::smallint,
            m,NULL,NULL,'MARKET_DECISION',p_payload->'markets'->m);
       END LOOP;
    ELSIF j.family='EARLY_RETENTION' THEN
       INSERT INTO public.sxf_base_signal_events(
          event_key,job_id,fixture_uid,kickoff_utc,ruleset_version,family,
          job_checkpoint_hours,source_checkpoint_hours,market,engine,selection,kind,details)
       VALUES(j.job_key||':RETENTION',j.job_id,j.fixture_uid,j.kickoff_utc,
          j.ruleset_version,j.family,j.checkpoint_hours,j.checkpoint_hours,
          '1X2',NULL,NULL,'RETENTION_CHECK',p_payload->'retention');
    END IF;
    UPDATE public.sxf_base_checkpoint_jobs
       SET state='COMPLETED',completed_at=now(),lease_owner=NULL,
           lease_token=NULL,lease_expires_at=NULL,last_error_code=NULL
     WHERE job_id=j.job_id;
    RETURN true;
END $$;

ALTER TABLE public.sxf_base_checkpoint_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sxf_base_checkpoint_evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sxf_base_signal_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.sxf_base_checkpoint_jobs,public.sxf_base_checkpoint_evaluations,public.sxf_base_signal_events
    FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.sxf_base_checkpoint_jobs TO service_role;
GRANT SELECT,INSERT ON public.sxf_base_checkpoint_evaluations,public.sxf_base_signal_events TO service_role;
GRANT USAGE,SELECT ON SEQUENCE public.sxf_base_checkpoint_evaluations_evaluation_id_seq,
    public.sxf_base_signal_events_event_id_seq TO service_role;
REVOKE ALL ON FUNCTION public.sxf_base_enqueue_jobs(jsonb),
    public.sxf_base_claim_due_jobs(text,integer,integer),
    public.sxf_base_renew_lease(uuid,uuid,integer),
    public.sxf_base_fail_job(uuid,uuid,text,integer),
    public.sxf_base_complete_job(uuid,uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sxf_base_enqueue_jobs(jsonb),
    public.sxf_base_claim_due_jobs(text,integer,integer),
    public.sxf_base_renew_lease(uuid,uuid,integer),
    public.sxf_base_fail_job(uuid,uuid,text,integer),
    public.sxf_base_complete_job(uuid,uuid,jsonb) TO service_role;
COMMIT;