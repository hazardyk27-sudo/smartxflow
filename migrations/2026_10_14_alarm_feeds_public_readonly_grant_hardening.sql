-- Security hardening: alarm feed tables remain readable by existing clients,
-- while alarm generation/retention mutations are restricted to trusted server
-- credentials. Hetzner alarm runtime writes with service_role.

BEGIN;

REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
ON TABLE
    public.bigmoney_alarms,
    public.dropping_alarms,
    public.insider_alarms,
    public.publicmove_alarms,
    public.volumeshock_alarms
FROM anon, authenticated;

COMMIT;
