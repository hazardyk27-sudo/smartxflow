-- SmartXFlow Phase 4C3 durable fixture discovery cursor. SOURCE ONLY.
-- Never apply to live Supabase/production without explicit user approval.
BEGIN;

CREATE TABLE IF NOT EXISTS public.sxf_base_discovery_cursors (
    cursor_name text PRIMARY KEY CHECK (cursor_name='BASE_FIXTURES'),
    bootstrap_start timestamptz NOT NULL,
    completed_through timestamptz NOT NULL,
    last_scanned_at timestamptz,
    last_window_fixtures integer CHECK (last_window_fixtures>=0),
    lease_owner text,
    lease_token uuid,
    lease_expires_at timestamptz,
    lease_attempts integer NOT NULL DEFAULT 0 CHECK (lease_attempts>=0),
    last_error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT sxf_base_discovery_progress CHECK(completed_through>=bootstrap_start)
);
ALTER TABLE public.sxf_base_discovery_cursors ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.sxf_base_discovery_cursors FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.sxf_base_discovery_cursors TO service_role;

-- Initial start is explicitly chosen after source retention/preflight review.
-- Existing bootstraps CANNOT be silently moved or rewound.
CREATE OR REPLACE FUNCTION public.sxf_base_init_discovery(p_start timestamptz)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
DECLARE
    v_added integer;
    v_initial timestamptz;
BEGIN
    IF p_start IS NULL OR p_start< '2020-01-01'::timestamptz
       OR p_start > now()+INTERVAL '1 day' THEN
        RAISE EXCEPTION 'invalid explicit discovery bootstrap';
    END IF;
    INSERT INTO public.sxf_base_discovery_cursors(
        cursor_name,bootstrap_start,completed_through)
    VALUES('BASE_FIXTURES',p_start,p_start)
    ON CONFLICT (cursor_name) DO NOTHING;
    GET DIAGNOSTICS v_added=ROW_COUNT;
    IF v_added=1 THEN RETURN true; END IF;
    SELECT bootstrap_start INTO v_initial FROM public.sxf_base_discovery_cursors
    WHERE cursor_name='BASE_FIXTURES';
    IF v_initial IS DISTINCT FROM p_start THEN
        RAISE EXCEPTION 'discovery bootstrap conflicts with immutable initial cursor';
    END IF;
    RETURN false;
END $$;

CREATE OR REPLACE FUNCTION public.sxf_base_claim_discovery(
    p_worker text,p_lease_seconds integer DEFAULT 900)
RETURNS TABLE(cursor_name text,completed_through timestamptz,bootstrap_start timestamptz,
    lease_token uuid,lease_attempts integer)
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
BEGIN
    IF p_worker IS NULL OR length(btrim(p_worker)) NOT BETWEEN 1 AND 100
       OR p_lease_seconds IS NULL OR p_lease_seconds NOT BETWEEN 60 AND 1800 THEN
        RAISE EXCEPTION 'invalid discovery lease';
    END IF;
    RETURN QUERY WITH locked AS (
      SELECT c.cursor_name FROM public.sxf_base_discovery_cursors c
      WHERE c.cursor_name='BASE_FIXTURES'
        AND (c.lease_expires_at IS NULL OR c.lease_expires_at<now())
      FOR UPDATE SKIP LOCKED
    ), updated AS (
      UPDATE public.sxf_base_discovery_cursors c
      SET lease_owner=p_worker,lease_token=gen_random_uuid(),
          lease_expires_at=now()+make_interval(secs=>p_lease_seconds),
          lease_attempts=c.lease_attempts+1,updated_at=now()
      FROM locked l WHERE c.cursor_name=l.cursor_name RETURNING c.*
    ) SELECT u.cursor_name,u.completed_through,u.bootstrap_start,
             u.lease_token,u.lease_attempts FROM updated u;
END $$;

CREATE OR REPLACE FUNCTION public.sxf_base_advance_discovery(
    p_lease_token uuid,p_start timestamptz,p_end timestamptz,p_fixture_count integer)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
BEGIN
    IF p_start IS NULL OR p_end IS NULL OR p_end<=p_start
       OR p_end>p_start+INTERVAL '1 day'
       OR p_end>now()+INTERVAL '75 hours'
       OR p_fixture_count IS NULL OR p_fixture_count NOT BETWEEN 0 AND 100000 THEN
        RAISE EXCEPTION 'invalid discovery coverage window';
    END IF;
    UPDATE public.sxf_base_discovery_cursors c
      SET completed_through=p_end,last_scanned_at=now(),last_window_fixtures=p_fixture_count,
          last_error_code=NULL,lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,
          updated_at=now()
    WHERE c.cursor_name='BASE_FIXTURES' AND c.completed_through=p_start
      AND c.lease_token=p_lease_token AND c.lease_expires_at>now();
    RETURN FOUND;
END $$;

CREATE OR REPLACE FUNCTION public.sxf_base_release_discovery(
    p_lease_token uuid,p_error_code text DEFAULT NULL)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog,public AS $$
BEGIN
    IF p_error_code IS NOT NULL AND p_error_code !~ '^[A-Z0-9_]{1,64}$' THEN
       RAISE EXCEPTION 'invalid discovery error code';
    END IF;
    UPDATE public.sxf_base_discovery_cursors c
      SET last_error_code=p_error_code,lease_owner=NULL,lease_token=NULL,
          lease_expires_at=NULL,updated_at=now()
    WHERE c.cursor_name='BASE_FIXTURES'
      AND c.lease_token=p_lease_token AND c.lease_expires_at>now();
    RETURN FOUND;
END $$;

REVOKE ALL ON FUNCTION public.sxf_base_init_discovery(timestamptz),
    public.sxf_base_claim_discovery(text,integer),
    public.sxf_base_advance_discovery(uuid,timestamptz,timestamptz,integer),
    public.sxf_base_release_discovery(uuid,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sxf_base_init_discovery(timestamptz),
    public.sxf_base_claim_discovery(text,integer),
    public.sxf_base_advance_discovery(uuid,timestamptz,timestamptz,integer),
    public.sxf_base_release_discovery(uuid,text) TO service_role;
COMMIT;
