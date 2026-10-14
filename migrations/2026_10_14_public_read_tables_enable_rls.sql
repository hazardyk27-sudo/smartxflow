-- Security hardening: all remaining public read-only tables get RLS enabled.
-- Existing client behavior is preserved: anon/authenticated may SELECT only.
-- Mutation grants were already revoked in earlier hardening migrations.
-- service_role continues to bypass RLS for trusted Hetzner runtimes.

BEGIN;

DO $$
DECLARE
    table_name text;
    tables text[] := ARRAY[
        'analyses',
        'analysts',
        'bigmoney_alarms',
        'confirmed_money_signals',
        'confirmed_money_v2_signals',
        'dropping_1x2_hist',
        'dropping_alarms',
        'dropping_btts_hist',
        'dropping_ou25_hist',
        'early_money_lock_signals',
        'fake_sharp_signals',
        'fixtures',
        'free_matches',
        'insider_alarms',
        'matchbook_1x2_history',
        'matchbook_btts_history',
        'matchbook_fixtures',
        'matchbook_league_map',
        'matchbook_ou25_history',
        'moneyway_1x2_hist',
        'moneyway_btts_hist',
        'moneyway_ou25_hist',
        'moneyway_snapshots',
        'publicmove_alarms',
        'scraper_heartbeat',
        'underdog_signals',
        'volumeshock_alarms'
    ];
BEGIN
    FOREACH table_name IN ARRAY tables LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', table_name || '_public_read', table_name);
        EXECUTE format(
            'CREATE POLICY %I ON public.%I FOR SELECT TO anon, authenticated USING (true)',
            table_name || '_public_read',
            table_name
        );
    END LOOP;
END
$$;

COMMIT;
