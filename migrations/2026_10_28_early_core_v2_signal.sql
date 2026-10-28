-- Add the separate EARLY CORE V2 engine to the active Early Core job output.
-- Existing EARLY_MONEY_CORE events and job identities remain unchanged.
BEGIN;
SET LOCAL lock_timeout='8s';
SET LOCAL statement_timeout='90s';

CREATE OR REPLACE FUNCTION public.sxf_base_complete_job(p_job_id uuid, p_lease_token uuid, p_payload jsonb)
 RETURNS boolean
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
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
           'SURPRISE_TEAM','EARLY_MONEY_CORE','EARLY_MONEY_CORE_V2','EARLY_MONEY_T12') THEN v_market:='1X2';
        ELSIF v_engine IN('STABLE_OVER_2_5','PREMIUM_OVER_2_5','PREMIUM_OVER_MIN1_70') THEN v_market:='OU25';
        ELSIF v_engine='BTTS_YES' THEN v_market:='BTTS';
        ELSE RAISE EXCEPTION 'unknown engine in checkpoint payload'; END IF;
        IF v_cp IS NULL OR v_side NOT IN('1','X','2','O','U','Y','N')
           OR (j.family='BASE' AND (j.checkpoint_hours NOT IN(8,6)
                OR (j.checkpoint_hours=8 AND v_cp<>8)
                OR (j.checkpoint_hours=6 AND v_cp NOT IN(6,8))))
           OR (j.family IN('EARLY_CORE','EARLY_T12') AND v_cp<>j.checkpoint_hours)
           OR j.family='EARLY_RETENTION'
           OR (j.family<>'BASE' AND v_engine NOT IN('EARLY_MONEY_CORE','EARLY_MONEY_CORE_V2','EARLY_MONEY_T12'))
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
END $function$
;

COMMIT;
