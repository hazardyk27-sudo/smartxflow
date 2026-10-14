-- Security hardening phase 2: licenses is now server-only.
-- Hetzner web PostgREST traffic uses service_role via web_runtime.py.
-- Browser/desktop clients validate licenses through the SmartXFlow API.

BEGIN;

REVOKE ALL PRIVILEGES
ON TABLE public.licenses
FROM anon, authenticated;

ALTER TABLE public.licenses ENABLE ROW LEVEL SECURITY;

-- No anon/authenticated policy is intentional.
-- service_role retains its existing grants and bypasses RLS.

COMMIT;
