from pathlib import Path
import re


MIGRATION = Path("migrations/2026_10_05_fixture_identity_v2_additive.sql")


def _sql_without_comments() -> str:
    text = MIGRATION.read_text(encoding="utf-8")
    return re.sub(r"--.*?$", "", text, flags=re.MULTILINE).lower()


def test_identity_v2_migration_is_additive_only():
    sql = _sql_without_comments()
    assert "add column if not exists fixture_uid uuid" in sql
    assert "alter column fixture_uid set default gen_random_uuid()" in sql
    assert "create unique index if not exists fixtures_fixture_uid_uidx" in sql
    assert "create table if not exists public.fixture_source_ids" in sql

    forbidden = [
        r"\bdrop\s+table\b",
        r"\bdrop\s+column\b",
        r"\bdrop\s+constraint\b",
        r"\btruncate\b",
        r"\bdelete\s+from\b",
        r"\balter\s+column\s+match_id_hash\b",
        r"\brename\s+column\s+match_id_hash\b",
        r"\balter\s+column\s+fixture_uid\s+set\s+not\s+null\b",
    ]
    for pattern in forbidden:
        assert re.search(pattern, sql) is None, pattern


def test_provider_registry_enforces_one_provider_event_mapping():
    sql = _sql_without_comments()
    assert "primary key (source, source_event_id)" in sql
    assert "foreign key (fixture_uid)" in sql
    assert "references public.fixtures (fixture_uid)" in sql
    assert "on delete restrict" in sql
    assert "source = lower(btrim(source))" in sql
    assert "btrim(source_event_id) <> ''" in sql


def test_legacy_hash_uniqueness_is_not_retired_in_additive_phase():
    sql = _sql_without_comments()
    assert "match_id_hash" not in sql


def test_existing_rows_receive_uid_without_touching_fixture_payload():
    sql = _sql_without_comments()
    assert re.search(
        r"update\s+public\.fixtures\s+set\s+fixture_uid\s*=\s*gen_random_uuid\(\)\s+where\s+fixture_uid\s+is\s+null",
        sql,
    )
