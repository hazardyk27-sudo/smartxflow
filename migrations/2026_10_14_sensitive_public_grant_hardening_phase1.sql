-- Security hardening phase 1: remove unnecessary public mutation rights from
-- sensitive tables without breaking current server paths.
--
-- licenses is still read through the server's legacy anon-key Supabase client,
-- so SELECT remains temporarily available while all mutation privileges are
-- removed.  A later phase will move that read path to service_role and close
-- SELECT as well.
--
-- telegram_settings / telegram_sent_log are current server-only runtime state.
-- alarm_config is legacy/orphaned and has no active application dependency.

BEGIN;

-- License keys and membership metadata must never be mutable through the public
-- anon/authenticated roles. Keep SELECT only until the server read path is
-- migrated to service_role.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
ON TABLE public.licenses
FROM anon, authenticated;

-- Current runtime access is service_role only. Remove all public privileges and
-- enable RLS as defense in depth. service_role bypasses RLS; no public policy is
-- intentionally created.
REVOKE ALL PRIVILEGES
ON TABLE public.telegram_settings
FROM anon, authenticated;
ALTER TABLE public.telegram_settings ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES
ON TABLE public.telegram_sent_log
FROM anon, authenticated;
ALTER TABLE public.telegram_sent_log ENABLE ROW LEVEL SECURITY;

-- Legacy configuration table: no active code path depends on public access.
REVOKE ALL PRIVILEGES
ON TABLE public.alarm_config
FROM anon, authenticated;
ALTER TABLE public.alarm_config ENABLE ROW LEVEL SECURITY;

COMMIT;
