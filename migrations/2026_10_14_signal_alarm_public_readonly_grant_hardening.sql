-- Security hardening: these signal/alarm feeds remain readable by existing
-- clients, while mutations are restricted to trusted server credentials.
-- Current Hetzner runtimes mutate them with service_role.

BEGIN;

REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
ON TABLE
    public.sharp_alarms,
    public.mim_alarms,
    public.volume_leader_alarms,
    public.scraper_signal
FROM anon, authenticated;

COMMIT;
