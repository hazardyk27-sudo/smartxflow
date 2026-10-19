-- SmartXFlow Base Signals Part 4C4A: kickoff drift quarantine / repeat scan.
-- SOURCE ONLY on GitHub preview. NEVER apply to live Supabase without approval.
BEGIN;

-- Identity invalidation is not completion; preserve old immutable evaluations.
ALTER TABLE public.sxf_base_checkpoint_jobs
    DROP CONSTRAINT IF EXISTS sxf_base_checkpoint_jobs_state_check;
ALTER TABLE public.sxf_base_checkpoint_jobs
    ADD CONSTRAINT sxf_base_checkpoint_jobs_state_check
    CHECK (state IN ('PENDING','LEASED','RETRY','WAITING_DATA','COMPLETED','SUPERSEDED'));

CREATE TABLE IF NOT EXISTS public.sxf_base_fixture_drift_events (
    drift_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fixture_uid uuid NOT NULL,
    previous_kickoff timestamptz NOT NULL,
    current_kickoff timestamptz NOT NULL,
    observed_at timestamptz NOT NULL DEFAULT now(),
    event_key text NOT NULL UNIQUE,
    CONSTRAINT sxf_base_drift_times_distinct CHECK(previous_kickoff<>current_kickoff)
);
CREATE INDEX IF NOT EXISTS sxf_base_drift_fixture_idx
    ON public.sxf_base_fixture_drift_events(fixture_uid,observed_at);
CREATE TRIGGER sxf_base_fixture_drift_events_immutable
    BEFORE UPDATE OR DELETE ON public.sxf_base_fixture_drift_events
    FOR EACH ROW EXECUTE FUNCTION public.sxf_base_append_only_guard();
ALTER TABLE public.sxf_base_fixture_drift_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.sxf_base_fixture_drift_events FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON public.sxf_base_fixture_drift_events TO service_role;
GRANT USAGE,SELECT ON SEQUENCE public.sxf_base_fixture_drift_events_drift_id_seq TO service_role;

-- Protect even when a drift scan has NOT run. All historical source writes must
-- still match the physical fixture UID and exact kickoff when inserted.
CREATE OR REPLACE FUNCTION public.sxf_base_insert_identity_guard()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE
    v_current timestamptz;
BEGIN
    SELECT f.kickoff_utc INTO v_current FROM public.fixtures f
     WHERE f.fixture_uid=NEW.fixture_uid;
    IF NOT FOUND OR v_current IS DISTINCT FROM NEW.kickoff_utc THEN
        RAISE EXCEPTION 'checkpoint fixture UID or kickoff is no longer authoritative';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER sxf_base_evaluation_identity_guard
    BEFORE INSERT ON public.sxf_base_checkpoint_evaluations
    FOR EACH ROW EXECUTE FUNCTION public.sxf_base_insert_identity_guard();
CREATE TRIGGER sxf_base_event_identity_guard
    BEFORE INSERT ON public.sxf_base_signal_events
    FOR EACH ROW EXECUTE FUNCTION public.sxf_base_insert_identity_guard();

-- A paginated, bounded reconciliation; stale completed evaluations remain
-- immutable. Old jobs are excluded from further claims, and drift is recorded.
CREATE OR REPLACE FUNCTION public.sxf_base_quarantine_fixture_drift(
    p_limit integer DEFAULT 250)
RETURNS integer LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE
    v_changed integer;
BEGIN
    IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 1000 THEN
       RAISE EXCEPTION 'invalid fixture drift batch';
    END IF;
    WITH locked AS (
      SELECT j.job_id, j.fixture_uid, j.kickoff_utc AS prior, f.kickoff_utc AS current
      FROM public.sxf_base_checkpoint_jobs j
      JOIN public.fixtures f ON f.fixture_uid=j.fixture_uid
      WHERE j.kickoff_utc IS DISTINCT FROM f.kickoff_utc
        AND j.state<>'SUPERSEDED'
      ORDER BY j.fixture_uid,j.kickoff_utc,j.job_id
      LIMIT p_limit FOR UPDATE OF j SKIP LOCKED
    ), changed AS (
      UPDATE public.sxf_base_checkpoint_jobs j
      SET state='SUPERSEDED',lease_owner=NULL,lease_token=NULL,
          lease_expires_at=NULL,last_error_code='KICKOFF_DRIFT'
      FROM locked l WHERE j.job_id=l.job_id
      RETURNING l.fixture_uid,l.prior,l.current
    ), events AS (
      INSERT INTO public.sxf_base_fixture_drift_events(
          fixture_uid,previous_kickoff,current_kickoff,event_key)
      SELECT DISTINCT c.fixture_uid,c.prior,c.current,
             c.fixture_uid::text||':'||to_char(c.prior AT TIME ZONE 'UTC',
                 'YYYY-MM-DD"T"HH24:MI:SS.US')||':'||
             to_char(c.current AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US')
      FROM changed c
      ON CONFLICT (event_key) DO NOTHING
      RETURNING drift_id
    )
    SELECT count(*) INTO v_changed FROM changed;
    RETURN v_changed;
END $$;

REVOKE ALL ON FUNCTION public.sxf_base_quarantine_fixture_drift(integer)
    FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sxf_base_quarantine_fixture_drift(integer)
    TO service_role;
COMMIT;
