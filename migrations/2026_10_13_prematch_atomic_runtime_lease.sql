BEGIN;

CREATE TABLE IF NOT EXISTS public.scraper_runtime_lease (
    lease_name text PRIMARY KEY,
    holder text NOT NULL,
    lease_until timestamptz NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

REVOKE ALL ON TABLE public.scraper_runtime_lease FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION public.acquire_scraper_runtime_lease(
    p_lease_name text,
    p_holder text,
    p_ttl_seconds integer DEFAULT 420
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_now timestamptz := clock_timestamp();
    v_holder text;
    v_until timestamptz;
    v_acquired boolean := false;
BEGIN
    p_lease_name := btrim(coalesce(p_lease_name, ''));
    p_holder := btrim(coalesce(p_holder, ''));

    IF p_lease_name = '' THEN
        RAISE EXCEPTION 'lease_name_required';
    END IF;
    IF p_holder = '' THEN
        RAISE EXCEPTION 'holder_required';
    END IF;
    IF p_ttl_seconds < 120 OR p_ttl_seconds > 1800 THEN
        RAISE EXCEPTION 'ttl_out_of_range';
    END IF;

    INSERT INTO public.scraper_runtime_lease AS lease (
        lease_name,
        holder,
        lease_until,
        updated_at
    )
    VALUES (
        p_lease_name,
        p_holder,
        v_now + make_interval(secs => p_ttl_seconds),
        v_now
    )
    ON CONFLICT (lease_name) DO UPDATE
    SET
        holder = EXCLUDED.holder,
        lease_until = EXCLUDED.lease_until,
        updated_at = EXCLUDED.updated_at
    WHERE
        lease.lease_until <= v_now
        OR lease.holder = EXCLUDED.holder
    RETURNING lease.holder, lease.lease_until
    INTO v_holder, v_until;

    IF FOUND THEN
        v_acquired := true;
    ELSE
        SELECT lease.holder, lease.lease_until
        INTO v_holder, v_until
        FROM public.scraper_runtime_lease AS lease
        WHERE lease.lease_name = p_lease_name;
    END IF;

    RETURN jsonb_build_object(
        'acquired', v_acquired,
        'holder', v_holder,
        'lease_until', v_until,
        'error', NULL
    );
END;
$$;

REVOKE ALL ON FUNCTION public.acquire_scraper_runtime_lease(text, text, integer)
FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.acquire_scraper_runtime_lease(text, text, integer)
TO service_role;

COMMIT;
