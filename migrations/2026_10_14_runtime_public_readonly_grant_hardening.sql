-- Security hardening: runtime feed/status tables remain readable by current
-- clients, but only server credentials may mutate them.
-- Existing SELECT behavior and existing RLS policies are intentionally left
-- unchanged in this phase.

BEGIN;

REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
ON TABLE
    public.live_fixtures,
    public.live_snapshots,
    public.moneyway_snapshots,
    public.scraper_heartbeat
FROM anon, authenticated;

COMMIT;
