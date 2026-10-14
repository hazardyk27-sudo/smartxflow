-- Security hardening phase 5: core stored Polymarket match/trade data.
-- Browser UI reads these through SmartXFlow /api/poly routes; Hetzner web and
-- the production Poly worker both use service_role.

BEGIN;

REVOKE ALL PRIVILEGES
ON TABLE public.polymarket_matches
FROM anon, authenticated;
ALTER TABLE public.polymarket_matches ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES
ON TABLE public.polymarket_trades
FROM anon, authenticated;
ALTER TABLE public.polymarket_trades ENABLE ROW LEVEL SECURITY;

-- No anon/authenticated policies are intentional.
-- service_role retains existing grants and bypasses RLS.

COMMIT;
