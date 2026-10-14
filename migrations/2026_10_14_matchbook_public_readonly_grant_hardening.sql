-- Security hardening: Matchbook storage remains readable by existing clients,
-- but public/desktop credentials may not mutate production data.
-- Any future Matchbook collector must run as a trusted server process with
-- service_role credentials.

BEGIN;

REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
ON TABLE
    public.matchbook_fixtures,
    public.matchbook_1x2_history,
    public.matchbook_ou25_history,
    public.matchbook_btts_history,
    public.matchbook_league_map
FROM anon, authenticated;

COMMIT;
