-- SmartXFlow Base Signals Part 4A hardening. SOURCE ONLY / NOT APPLIED.
-- Must follow migrations/2026_10_18_sxf_base_durable_queue.sql in ONE
-- controlled, explicitly approved migration sequence. No production execution.
BEGIN;

-- Absent source evidence is not a terminal checkpoint. A worker must retry.
ALTER TABLE public.sxf_base_checkpoint_jobs
    DROP CONSTRAINT IF EXISTS sxf_base_checkpoint_jobs_state_check;
ALTER TABLE public.sxf_base_checkpoint_jobs
    ADD CONSTRAINT sxf_base_checkpoint_jobs_state_check
    CHECK (state IN ('PENDING','LEASED','RETRY','WAITING_DATA','COMPLETED'));
ALTER TABLE public.sxf_base_checkpoint_jobs
    ADD COLUMN IF NOT EXISTS waiting_since timestamptz;
CREATE INDEX IF NOT EXISTS sxf_base_jobs_waiting_idx
    ON public.sxf_base_checkpoint_jobs(next_attempt_at,checkpoint_at,job_id)
    WHERE state='WAITING_DATA';

-- Unlike the final one-row evaluation, attempts survive missing data, failures,
-- and reclaimed expired leases. Never rewrite or delete diagnostic truth.
CREATE TABLE IF NOT EXISTS public.sxf_base_checkpoint_attempts (
    attempt_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id uuid NOT NULL REFERENCES public.sxf_base_checkpoint_jobs(job_id) ON DELETE RESTRICT,
    attempt_number integer NOT NULL CHECK (attempt_number >= 1),
    lease_token uuid NOT NULL,
    outcome text NOT NULL CHECK (outcome IN ('RETRY','WAITING_DATA','COMPLETED','LEASE_EXPIRED')),
    reason text NOT NULL CHECK (reason ~ '^[A-Z0-9_]{1,64}$'),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT sxf_base_attempt_unique UNIQUE(job_id,attempt_number)
);
CREATE INDEX IF NOT EXISTS sxf_base_attempts_job_idx
    ON public.sxf_base_checkpoint_attempts(job_id,recorded_at);
CREATE TRIGGER sxf_base_checkpoint_attempts_immutable
    BEFORE UPDATE OR DELETE ON public.sxf_base_checkpoint_attempts
    FOR EACH ROW EXECUTE FUNCTION public.sxf_base_append_only_guard();

-- Audit is part of the SAME transaction as a lease transition.
-- Reclaim records the prior (expired) attempt, not the new worker's attempt.
CREATE OR REPLACE FUNCTION public.sxf_base_audit_attempt_transition()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE
    v_outcome text;
    v_reason text;
BEGIN
    IF OLD.state <> 'LEASED' THEN
        RETURN NEW;
    END IF;
    IF NEW.state = 'LEASED' AND OLD.lease_token IS DISTINCT FROM NEW.lease_token THEN
        v_outcome := 'LEASE_EXPIRED';
        v_reason := 'LEASE_EXPIRED';
    ELSIF NEW.state IN ('RETRY','WAITING_DATA','COMPLETED') THEN
        v_outcome := NEW.state;
        v_reason := COALESCE(NEW.last_error_code, 'OK');
    ELSE
        RETURN NEW;
    END IF;
    INSERT INTO public.sxf_base_checkpoint_attempts(
        job_id,attempt_number,lease_token,outcome,reason
    ) VALUES(OLD.job_id,OLD.attempt_count,OLD.lease_token,v_outcome,v_reason);
    RETURN NEW;
END $$;
CREATE TRIGGER sxf_base_checkpoint_attempt_transition
    AFTER UPDATE ON public.sxf_base_checkpoint_jobs
    FOR EACH ROW EXECUTE FUNCTION public.sxf_base_audit_attempt_transition();

-- Existing claim semantics preserved, with WAITING_DATA eligible after delay.
-- SKIP LOCKED + rotating lease_token fence two concurrent workers.
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
       WHERE (j.state IN('PENDING','RETRY','WAITING_DATA') AND j.next_attempt_at<=now())
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

-- Explicit non-terminal missing-source transition (not a false COMPLETED).
CREATE OR REPLACE FUNCTION public.sxf_base_wait_for_data(
    p_job_id uuid,p_lease_token uuid,p_reason text DEFAULT 'INSUFFICIENT_DATA',
    p_retry_seconds integer DEFAULT 180)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path=public,pg_temp AS $$
BEGIN
    IF p_reason NOT IN ('INSUFFICIENT_DATA','SOURCE_LAG','SOURCE_INCOMPLETE')
       OR p_retry_seconds NOT BETWEEN 60 AND 3600 THEN
        RAISE EXCEPTION 'invalid missing-data retry parameters';
    END IF;
    UPDATE public.sxf_base_checkpoint_jobs j
    SET state='WAITING_DATA',next_attempt_at=now()+make_interval(secs=>p_retry_seconds),
        waiting_since=COALESCE(j.waiting_since,now()),last_error_code=p_reason,
        lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL
    WHERE j.job_id=p_job_id AND j.lease_token=p_lease_token
      AND j.state='LEASED' AND j.lease_expires_at>now();
    RETURN FOUND;
END $$;

-- Fail closed: a BASE job with zero usable market checkpoints CANNOT become
-- COMPLETED. A valid no-hit evaluation still completes normally.
-- Early absence is not yet distinguishable from an authentic no-hit in the
-- Phase 3 payload; Part 4B must add explicit source-quality metadata.
CREATE OR REPLACE FUNCTION public.sxf_base_require_base_evidence()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE
    v_family text;
BEGIN
    SELECT family INTO v_family
      FROM public.sxf_base_checkpoint_jobs WHERE job_id=NEW.job_id;
    IF v_family='BASE' THEN
        IF jsonb_typeof(NEW.payload->'markets') IS DISTINCT FROM 'object' THEN
            RAISE EXCEPTION 'BASE evaluation missing market evidence';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM jsonb_each(NEW.payload->'markets') AS m(market,decision)
            WHERE m.decision->>'checkpoint' IN ('6','8')
        ) THEN
            RAISE EXCEPTION 'BASE source evidence missing: use WAITING_DATA';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER sxf_base_require_base_evidence_before_completion
    BEFORE INSERT ON public.sxf_base_checkpoint_evaluations
    FOR EACH ROW EXECUTE FUNCTION public.sxf_base_require_base_evidence();

-- Explicit event vocabulary for FUTURE reconciliations. An event MUST be
-- inserted, never UPDATE/DELETE an existing signal or market decision.
ALTER TABLE public.sxf_base_signal_events
    DROP CONSTRAINT IF EXISTS sxf_base_signal_events_kind_check;
ALTER TABLE public.sxf_base_signal_events
    ADD CONSTRAINT sxf_base_signal_events_kind_check
    CHECK (kind IN ('PRELIMINARY_SIGNAL','FINAL_SIGNAL','EARLY_SIGNAL',
                   'MARKET_DECISION','RETENTION_CHECK','CONFIRMED',
                   'INVALIDATED','CORRECTED','SETTLED'));

-- Enforce event source observation time at the DB boundary, in addition to
-- reader cutoff checks. Recorded-at may be later (replay); observed-at may not.
CREATE OR REPLACE FUNCTION public.sxf_base_event_no_lookahead()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE
    v_observed timestamptz;
BEGIN
    IF NEW.kind IN ('PRELIMINARY_SIGNAL','FINAL_SIGNAL','EARLY_SIGNAL') THEN
        v_observed := NULLIF(NEW.details->>'observed_at','')::timestamptz;
        IF v_observed IS NULL OR NEW.source_checkpoint_hours IS NULL OR
            v_observed > NEW.kickoff_utc - NEW.source_checkpoint_hours * INTERVAL '1 hour' THEN
            RAISE EXCEPTION 'signal evidence after frozen checkpoint';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER sxf_base_signal_no_lookahead
    BEFORE INSERT ON public.sxf_base_signal_events
    FOR EACH ROW EXECUTE FUNCTION public.sxf_base_event_no_lookahead();

ALTER TABLE public.sxf_base_checkpoint_attempts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.sxf_base_checkpoint_attempts FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON public.sxf_base_checkpoint_attempts TO service_role;
GRANT USAGE,SELECT ON SEQUENCE public.sxf_base_checkpoint_attempts_attempt_id_seq TO service_role;
REVOKE ALL ON FUNCTION public.sxf_base_wait_for_data(uuid,uuid,text,integer)
    FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sxf_base_wait_for_data(uuid,uuid,text,integer)
    TO service_role;
COMMIT;
