-- Security hardening phase 3: payment requests contain customer/payment metadata
-- and are only accessed through SmartXFlow server API routes. Hetzner web
-- PostgREST uses service_role via web_runtime.py.

BEGIN;

REVOKE ALL PRIVILEGES
ON TABLE public.payment_requests
FROM anon, authenticated;

ALTER TABLE public.payment_requests ENABLE ROW LEVEL SECURITY;

-- No anon/authenticated policy is intentional.
-- service_role retains its existing grants and bypasses RLS.

COMMIT;
