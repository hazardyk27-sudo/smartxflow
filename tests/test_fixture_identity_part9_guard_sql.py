from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PRE = ROOT / "scripts" / "fixture_identity_v2_part9_preflight.sql"
POST = ROOT / "scripts" / "fixture_identity_v2_part9_postflight.sql"
MIGRATION = ROOT / "migrations" / "2026_10_06_fixture_identity_v2_provider_writer.sql"


def _sql_without_line_comments(path: Path) -> str:
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        lines.append(line.split("--", 1)[0])
    return "\n".join(lines)


def _statements(path: Path):
    sql = _sql_without_line_comments(path)
    return [part.strip() for part in sql.split(";") if part.strip()]


def test_part9_guard_sql_is_read_only():
    for path in (PRE, POST):
        statements = _statements(path)
        assert statements, path
        for statement in statements:
            first = re.match(r"^([a-zA-Z]+)", statement)
            assert first, (path, statement[:80])
            assert first.group(1).lower() in {"select", "with"}, (path, statement[:120])


def test_part9_preflight_checks_required_integrity_and_pre_schema_state():
    sql = PRE.read_text(encoding="utf-8").lower()
    for token in (
        "fixture_uid_null_rows",
        "duplicate_fixture_uid_groups",
        "exact_physical_duplicate_groups",
        "betwatch_uid_multi_event_groups",
        "orphan_betwatch_registry_rows",
        "physical_mismatch_rows",
        "fixtures_match_id_hash_key",
        "record_betwatch_fixture_batch_v2",
    ):
        assert token in sql


def test_part9_postflight_checks_migrated_schema_permissions_and_integrity():
    sql = POST.read_text(encoding="utf-8").lower()
    for token in (
        "fixtures_fixture_uid_uidx",
        "fixture_source_ids_betwatch_fixture_uid_uidx",
        "fixtures_match_id_hash_idx",
        "record_betwatch_fixture_batch_v2",
        "service_role_execute",
        "anon_execute",
        "authenticated_execute",
        "routine_privileges",
        "grantee = 'public'",
        "duplicate_fixture_uid_groups",
        "physical_mismatch_rows",
    ):
        assert token in sql


def test_provider_writer_migration_contract_matches_part9_guards():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "drop constraint if exists fixtures_match_id_hash_key" in sql
    assert "create index if not exists fixtures_match_id_hash_idx" in sql
    assert "create unique index if not exists fixture_source_ids_betwatch_fixture_uid_uidx" in sql
    assert "alter column fixture_uid set not null" in sql
    assert "create or replace function public.record_betwatch_fixture_batch_v2" in sql
    assert "revoke all on function public.record_betwatch_fixture_batch_v2" in sql
    assert "grant execute on function public.record_betwatch_fixture_batch_v2" in sql
    assert "to service_role" in sql
