from pathlib import Path


MIGRATION = Path("migrations/2026_10_06_fixture_identity_v2_shadow_rpc.sql")


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_shadow_migration_is_additive_and_fail_closed():
    sql = _sql()
    assert "add column if not exists seen_count" in sql
    assert "record_fixture_identity_shadow_batch" in sql
    assert "on conflict (source, source_event_id) do update" in sql
    assert "where public.fixture_source_ids.fixture_uid = excluded.fixture_uid" in sql
    assert "seen_count = public.fixture_source_ids.seen_count + 1" in sql


def test_shadow_migration_does_not_retire_legacy_identity():
    sql = _sql()
    forbidden = (
        "drop table public.fixtures",
        "drop column match_id_hash",
        "drop constraint fixtures_match_id_hash_key",
        "delete from public.fixtures",
        "truncate",
    )
    for fragment in forbidden:
        assert fragment not in sql


def test_shadow_rpc_is_not_publicly_callable():
    sql = _sql()
    assert "revoke all on function public.record_fixture_identity_shadow_batch" in sql
    assert "from public, anon, authenticated" in sql
    assert "grant execute on function public.record_fixture_identity_shadow_batch" in sql
    assert "to service_role" in sql
