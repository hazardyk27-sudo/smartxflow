-- Security hardening: tracked-wallet internal storage is server-only.
-- Production traffic for these tables is Hetzner service_role only.
-- Public clients consume derived data through SmartXFlow server endpoints.

BEGIN;

REVOKE ALL PRIVILEGES
ON TABLE
    public.tracked_wallets,
    public.tracked_wallet_activity,
    public.tracked_wallet_bets,
    public.tracked_wallet_positions,
    public.tracked_wallet_redeems
FROM anon, authenticated;

ALTER TABLE public.tracked_wallets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tracked_wallet_activity ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tracked_wallet_bets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tracked_wallet_positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tracked_wallet_redeems ENABLE ROW LEVEL SECURITY;

-- No anon/authenticated policies are intentional.
-- service_role retains its existing grants and bypasses RLS.

COMMIT;
