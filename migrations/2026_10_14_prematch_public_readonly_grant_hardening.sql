-- Security hardening: SmartXFlow prematch storage is readable by existing
-- clients, but only trusted server credentials may mutate production data.
-- Hetzner authoritative prematch runtime writes with service_role.
-- SELECT grants and existing RLS policies are intentionally unchanged here.

BEGIN;

REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
ON TABLE
    public.fixtures,
    public.moneyway_1x2,
    public.moneyway_ou25,
    public.moneyway_btts,
    public.moneyway_1x2_history,
    public.moneyway_ou25_history,
    public.moneyway_btts_history,
    public.moneyway_1x2_hist,
    public.moneyway_ou25_hist,
    public.moneyway_btts_hist,
    public.moneyway_snapshots,
    public.dropping_1x2,
    public.dropping_ou25,
    public.dropping_btts,
    public.dropping_1x2_history,
    public.dropping_ou25_history,
    public.dropping_btts_history,
    public.dropping_1x2_hist,
    public.dropping_ou25_hist,
    public.dropping_btts_hist
FROM anon, authenticated;

COMMIT;
