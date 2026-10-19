-- SmartXFlow Base Signals Phase 5A — source change ledger proposal.
-- GitHub preview ONLY. NEVER apply to live source tables without separate
-- explicit DBA/user approval and source-ingest load benchmarks.
BEGIN;

CREATE TABLE IF NOT EXISTS public.sxf_base_source_changes (
    change_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_kind text NOT NULL CHECK (event_kind IN
       ('FIXTURE_INSERT','FIXTURE_CHANGE','FIXTURE_DELETE',
        'SNAPSHOT_INSERT','SNAPSHOT_CHANGE','SNAPSHOT_DELETE')),
    fixture_uid uuid NOT NULL,
    previous_fixture_uid uuid,
    kickoff_before timestamptz,
    kickoff_after timestamptz,
    snapshot_id bigint,
    market text,
    source_observed_at timestamptz,
    captured_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT sxf_base_source_change_kind CHECK (
       (event_kind LIKE 'FIXTURE_%' AND snapshot_id IS NULL)
       OR (event_kind LIKE 'SNAPSHOT_%' AND snapshot_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS sxf_base_changes_fixture_idx
    ON public.sxf_base_source_changes(fixture_uid,change_id);
CREATE INDEX IF NOT EXISTS sxf_base_changes_kind_idx
    ON public.sxf_base_source_changes(event_kind,change_id);
CREATE TRIGGER sxf_base_source_changes_immutable
  BEFORE UPDATE OR DELETE ON public.sxf_base_source_changes
  FOR EACH ROW EXECUTE FUNCTION public.sxf_base_append_only_guard();

CREATE TABLE IF NOT EXISTS public.sxf_base_source_deliveries (
    change_id bigint PRIMARY KEY REFERENCES public.sxf_base_source_changes(change_id) ON DELETE RESTRICT,
    state text NOT NULL DEFAULT 'PENDING' CHECK (state IN ('PENDING','LEASED','RETRY','DONE')),
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count>=0),
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    lease_token uuid,
    lease_owner text,
    lease_expires_at timestamptz,
    last_error_code text,
    completed_at timestamptz
);
CREATE INDEX IF NOT EXISTS sxf_base_source_due_idx
    ON public.sxf_base_source_deliveries(next_attempt_at,change_id)
    WHERE state IN ('PENDING','RETRY');
CREATE INDEX IF NOT EXISTS sxf_base_source_lease_idx
    ON public.sxf_base_source_deliveries(lease_expires_at,change_id)
    WHERE state='LEASED';

ALTER TABLE public.sxf_base_source_changes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sxf_base_source_deliveries ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.sxf_base_source_changes,public.sxf_base_source_deliveries
    FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.sxf_base_source_changes TO service_role;
GRANT SELECT,UPDATE ON public.sxf_base_source_deliveries TO service_role;

-- These narrow SECURITY DEFINER triggers are the only proposed exception to
-- SECURITY INVOKER: production source writers cannot be granted outbox INSERT.
-- The function owner must be audited; NO EXECUTE granted to client roles.
-- Appended outbox event and delivery commit atomically with source write.
CREATE OR REPLACE FUNCTION public.sxf_base_capture_fixture_change()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
DECLARE v_id bigint;
BEGIN
    IF TG_TABLE_SCHEMA<>'public' OR TG_TABLE_NAME<>'fixtures' THEN
       RAISE EXCEPTION 'invalid source capture trigger table';
    END IF;
    IF TG_OP='UPDATE' AND OLD.fixture_uid IS NOT DISTINCT FROM NEW.fixture_uid
       AND OLD.kickoff_utc IS NOT DISTINCT FROM NEW.kickoff_utc THEN
       RETURN NEW;
    END IF;
    INSERT INTO public.sxf_base_source_changes(
      event_kind,fixture_uid,previous_fixture_uid,kickoff_before,kickoff_after)
    VALUES (
      CASE TG_OP WHEN 'INSERT' THEN 'FIXTURE_INSERT'
                 WHEN 'DELETE' THEN 'FIXTURE_DELETE'
                 ELSE 'FIXTURE_CHANGE' END,
      CASE WHEN TG_OP='DELETE' THEN OLD.fixture_uid ELSE NEW.fixture_uid END,
      CASE WHEN TG_OP='INSERT' THEN NULL ELSE OLD.fixture_uid END,
      CASE WHEN TG_OP='INSERT' THEN NULL ELSE OLD.kickoff_utc END,
      CASE WHEN TG_OP='DELETE' THEN NULL ELSE NEW.kickoff_utc END)
    RETURNING change_id INTO v_id;
    INSERT INTO public.sxf_base_source_deliveries(change_id) VALUES(v_id);
    RETURN COALESCE(NEW,OLD);
END $$;

CREATE OR REPLACE FUNCTION public.sxf_base_capture_snapshot_change()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog,public AS $$
DECLARE v_id bigint;
BEGIN
    IF TG_TABLE_SCHEMA<>'public' OR TG_TABLE_NAME<>'moneyway_snapshots' THEN
       RAISE EXCEPTION 'invalid snapshot source capture table';
    END IF;
    INSERT INTO public.sxf_base_source_changes(
      event_kind,fixture_uid,previous_fixture_uid,snapshot_id,market,source_observed_at)
    VALUES(
      CASE TG_OP WHEN 'INSERT' THEN 'SNAPSHOT_INSERT'
                 WHEN 'DELETE' THEN 'SNAPSHOT_DELETE'
                 ELSE 'SNAPSHOT_CHANGE' END,
      CASE WHEN TG_OP='DELETE' THEN OLD.fixture_uid ELSE NEW.fixture_uid END,
      CASE WHEN TG_OP='INSERT' THEN NULL ELSE OLD.fixture_uid END,
      CASE WHEN TG_OP='DELETE' THEN OLD.id ELSE NEW.id END,
      CASE WHEN TG_OP='DELETE' THEN OLD.market ELSE NEW.market END,
      CASE WHEN TG_OP='DELETE' THEN OLD.scraped_at_utc ELSE NEW.scraped_at_utc END)
    RETURNING change_id INTO v_id;
    INSERT INTO public.sxf_base_source_deliveries(change_id) VALUES(v_id);
    RETURN COALESCE(NEW,OLD);
END $$;

-- SECURITY DEFINER is not an API: do not grant function EXECUTE to anon/auth.
REVOKE ALL ON FUNCTION public.sxf_base_capture_fixture_change(),
   public.sxf_base_capture_snapshot_change() FROM PUBLIC,anon,authenticated;

CREATE TRIGGER sxf_base_fixture_source_capture
    AFTER INSERT OR UPDATE OR DELETE ON public.fixtures
    FOR EACH ROW EXECUTE FUNCTION public.sxf_base_capture_fixture_change();
CREATE TRIGGER sxf_base_snapshot_source_capture
    AFTER INSERT OR UPDATE OR DELETE ON public.moneyway_snapshots
    FOR EACH ROW EXECUTE FUNCTION public.sxf_base_capture_snapshot_change();

CREATE OR REPLACE FUNCTION public.sxf_base_claim_source_changes(
    p_worker text,p_limit integer DEFAULT 25,p_lease_seconds integer DEFAULT 300)
RETURNS TABLE(change_id bigint,event_kind text,fixture_uid uuid,
    previous_fixture_uid uuid,kickoff_before timestamptz,kickoff_after timestamptz,
    snapshot_id bigint,market text,source_observed_at timestamptz,
    captured_at timestamptz,lease_token uuid,attempt_count integer)
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
BEGIN
    IF p_worker IS NULL OR length(btrim(p_worker)) NOT BETWEEN 1 AND 100
       OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 100
       OR p_lease_seconds IS NULL OR p_lease_seconds NOT BETWEEN 60 AND 1800 THEN
       RAISE EXCEPTION 'invalid source claim request';
    END IF;
    RETURN QUERY WITH locked AS (
      SELECT d.change_id FROM public.sxf_base_source_deliveries d
      WHERE (d.state IN ('PENDING','RETRY') AND d.next_attempt_at<=now())
         OR (d.state='LEASED' AND d.lease_expires_at<now())
      ORDER BY d.change_id LIMIT p_limit FOR UPDATE SKIP LOCKED
    ), updated AS (
      UPDATE public.sxf_base_source_deliveries d
      SET state='LEASED',attempt_count=d.attempt_count+1,
          lease_owner=p_worker,lease_token=gen_random_uuid(),
          lease_expires_at=now()+make_interval(secs=>p_lease_seconds)
      FROM locked l WHERE l.change_id=d.change_id RETURNING d.*
    )
    SELECT c.change_id,c.event_kind,c.fixture_uid,c.previous_fixture_uid,
           c.kickoff_before,c.kickoff_after,c.snapshot_id,c.market,
           c.source_observed_at,c.captured_at,u.lease_token,u.attempt_count
    FROM updated u JOIN public.sxf_base_source_changes c ON c.change_id=u.change_id
    ORDER BY c.change_id;
END $$;

CREATE OR REPLACE FUNCTION public.sxf_base_ack_source_change(
    p_change_id bigint,p_lease_token uuid)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
BEGIN
    UPDATE public.sxf_base_source_deliveries d
       SET state='DONE',completed_at=now(),lease_token=NULL,
           lease_owner=NULL,lease_expires_at=NULL,last_error_code=NULL
    WHERE d.change_id=p_change_id AND d.state='LEASED'
      AND d.lease_token=p_lease_token AND d.lease_expires_at>now();
    RETURN FOUND;
END $$;
CREATE OR REPLACE FUNCTION public.sxf_base_retry_source_change(
    p_change_id bigint,p_lease_token uuid,p_reason text,p_delay_seconds integer DEFAULT 60)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
BEGIN
    IF p_reason IS NULL OR p_reason !~ '^[A-Z0-9_]{1,64}$'
       OR p_delay_seconds IS NULL OR p_delay_seconds NOT BETWEEN 10 AND 3600 THEN
       RAISE EXCEPTION 'invalid source retry';
    END IF;
    UPDATE public.sxf_base_source_deliveries d
      SET state='RETRY',next_attempt_at=now()+make_interval(secs=>p_delay_seconds),
          lease_token=NULL,lease_owner=NULL,lease_expires_at=NULL,
          last_error_code=p_reason
    WHERE d.change_id=p_change_id AND d.state='LEASED'
      AND d.lease_token=p_lease_token AND d.lease_expires_at>now();
    RETURN FOUND;
END $$;

REVOKE ALL ON FUNCTION public.sxf_base_claim_source_changes(text,integer,integer),
 public.sxf_base_ack_source_change(bigint,uuid),
 public.sxf_base_retry_source_change(bigint,uuid,text,integer)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sxf_base_claim_source_changes(text,integer,integer),
 public.sxf_base_ack_source_change(bigint,uuid),
 public.sxf_base_retry_source_change(bigint,uuid,text,integer)
 TO service_role;
COMMIT;
