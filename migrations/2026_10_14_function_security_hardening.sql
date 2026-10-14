-- Security hardening for public helper functions.
-- Pin search_path to prevent object-shadowing attacks. The wallet summary RPC
-- is an internal server helper, so it runs as invoker and is executable only
-- by service_role.

BEGIN;

ALTER FUNCTION public.update_alarm_settings_timestamp()
    SET search_path = pg_catalog, public;

ALTER FUNCTION public.parse_arbworld_date(text)
    SET search_path = pg_catalog, public;

ALTER FUNCTION public.is_match_not_started(text)
    SET search_path = pg_catalog, public;

ALTER FUNCTION public.get_wallet_activity_summary(text)
    SECURITY INVOKER;

ALTER FUNCTION public.get_wallet_activity_summary(text)
    SET search_path = pg_catalog, public;

REVOKE EXECUTE ON FUNCTION public.get_wallet_activity_summary(text)
FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.get_wallet_activity_summary(text)
TO service_role;

COMMIT;
