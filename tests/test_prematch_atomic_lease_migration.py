from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "2026_10_13_prematch_atomic_runtime_lease.sql"


def test_atomic_lease_migration_is_service_role_only_and_compare_and_swap():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS public.scraper_runtime_lease" in sql
    assert "lease_name text PRIMARY KEY" in sql
    assert "ON CONFLICT (lease_name) DO UPDATE" in sql
    assert "lease.lease_until <= v_now" in sql
    assert "lease.holder = EXCLUDED.holder" in sql
    assert "SECURITY DEFINER" in sql
    assert "SET search_path = public" in sql
    assert "REVOKE ALL ON FUNCTION public.acquire_scraper_runtime_lease" in sql
    assert "FROM PUBLIC, anon, authenticated" in sql
    assert "TO service_role" in sql
    assert "p_ttl_seconds < 120 OR p_ttl_seconds > 1800" in sql
