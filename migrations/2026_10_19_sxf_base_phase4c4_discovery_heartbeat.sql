-- SXF Base Signals Part 4C4B: fenced discovery lease renewal.
-- SOURCE ONLY. Do not apply to live Supabase without explicit approval.
BEGIN;
CREATE OR REPLACE FUNCTION public.sxf_base_renew_discovery(
    p_lease_token uuid,p_lease_seconds integer DEFAULT 900)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog,public AS $$
BEGIN
    IF p_lease_token IS NULL OR p_lease_seconds IS NULL
       OR p_lease_seconds NOT BETWEEN 60 AND 1800 THEN
        RAISE EXCEPTION 'invalid discovery lease renewal';
    END IF;
    UPDATE public.sxf_base_discovery_cursors c
       SET lease_expires_at=now()+make_interval(secs=>p_lease_seconds),
           updated_at=now()
     WHERE c.cursor_name='BASE_FIXTURES' AND c.lease_token=p_lease_token
       AND c.lease_expires_at>now();
    RETURN FOUND;
END $$;
REVOKE ALL ON FUNCTION public.sxf_base_renew_discovery(uuid,integer)
    FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sxf_base_renew_discovery(uuid,integer)
    TO service_role;
COMMIT;
