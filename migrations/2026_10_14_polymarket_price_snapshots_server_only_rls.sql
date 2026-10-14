-- Security hardening: Polymarket price snapshots are server-only.
-- Current Hetzner Poly runtime uses service_role for this table.

BEGIN;

REVOKE ALL PRIVILEGES
ON TABLE public.polymarket_price_snapshots
FROM anon, authenticated;

ALTER TABLE public.polymarket_price_snapshots ENABLE ROW LEVEL SECURITY;

-- No anon/authenticated policy is intentional.
-- service_role retains its existing grants and bypasses RLS.

COMMIT;
