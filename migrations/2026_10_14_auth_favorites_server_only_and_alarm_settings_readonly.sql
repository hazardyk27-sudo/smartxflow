-- Security hardening for auth/favorites internals and alarm configuration.
-- Browser/desktop license and favorites flows go through SmartXFlow backend APIs.
-- alarm_settings keeps public read compatibility for legacy/desktop readers,
-- but only trusted server credentials may mutate it.

BEGIN;

-- Sensitive auth/favorites state is server-only.
REVOKE ALL PRIVILEGES
ON TABLE
    public.license_devices,
    public.user_sessions,
    public.license_favorites,
    public.match_favorites
FROM anon, authenticated;

ALTER TABLE public.license_devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.license_favorites ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.match_favorites ENABLE ROW LEVEL SECURITY;

-- These old policies were named as service policies but applied to PUBLIC.
DROP POLICY IF EXISTS service_access ON public.license_devices;
DROP POLICY IF EXISTS service_access ON public.user_sessions;

-- No anon/authenticated policy on the four sensitive tables is intentional.
-- service_role keeps its grants and bypasses RLS.

-- Alarm configuration remains publicly readable for legacy clients only.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
ON TABLE public.alarm_settings
FROM anon, authenticated;

DROP POLICY IF EXISTS "Allow all for alarm_settings" ON public.alarm_settings;
DROP POLICY IF EXISTS alarm_settings_public_read ON public.alarm_settings;
CREATE POLICY alarm_settings_public_read
ON public.alarm_settings
FOR SELECT
TO anon, authenticated
USING (true);

COMMIT;
