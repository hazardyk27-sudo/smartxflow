-- Security hardening: these tables remain publicly readable for current clients,
-- but public roles must not be able to mutate server-produced data.
-- RLS is intentionally not enabled in this phase so existing SELECT paths remain unchanged.

BEGIN;

REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
ON TABLE
    public.analyses,
    public.analysts,
    public.confirmed_money_signals,
    public.confirmed_money_v2_signals,
    public.early_money_lock_signals,
    public.fake_sharp_signals,
    public.underdog_signals,
    public.free_matches
FROM anon, authenticated;

COMMIT;
