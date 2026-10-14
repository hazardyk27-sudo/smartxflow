-- Server-only RLS hardening phase 1.
-- These tables are only accessed by the Hetzner backend using service_role.
-- No anon/authenticated policies are intentionally created.

ALTER TABLE public.telegram_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.telegram_sent_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alarm_config ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.telegram_settings FROM anon, authenticated;
REVOKE ALL ON TABLE public.telegram_sent_log FROM anon, authenticated;
REVOKE ALL ON TABLE public.alarm_config FROM anon, authenticated;

-- service_role keeps its existing table grants and bypasses RLS.
