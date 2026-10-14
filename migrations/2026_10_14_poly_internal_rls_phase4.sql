-- Security hardening phase 4: internal Polymarket classification state.
-- Production Poly runs on Hetzner with service_role; these tables are not a
-- browser/desktop API surface.

BEGIN;

REVOKE ALL PRIVILEGES
ON TABLE public.polymarket_sport_registry
FROM anon, authenticated;
ALTER TABLE public.polymarket_sport_registry ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES
ON TABLE public.tracked_wallet_sport_quarantine
FROM anon, authenticated;
ALTER TABLE public.tracked_wallet_sport_quarantine ENABLE ROW LEVEL SECURITY;

-- No anon/authenticated policies are intentional.
-- service_role retains existing grants and bypasses RLS.

COMMIT;
