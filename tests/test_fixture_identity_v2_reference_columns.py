from pathlib import Path

MIGRATION = Path("migrations/2026_10_06_fixture_identity_v2_reference_columns.sql")

EXPECTED_TABLES = {
    "moneyway_1x2", "moneyway_ou25", "moneyway_btts",
    "dropping_1x2", "dropping_ou25", "dropping_btts",
    "moneyway_1x2_history", "moneyway_ou25_history", "moneyway_btts_history",
    "dropping_1x2_history", "dropping_ou25_history", "dropping_btts_history",
    "moneyway_snapshots",
    "bigmoney_alarms", "dropping_alarms", "insider_alarms", "mim_alarms",
    "publicmove_alarms", "sharp_alarms", "volume_leader_alarms", "volumeshock_alarms",
    "underdog_signals", "confirmed_money_signals", "confirmed_money_v2_signals",
    "fake_sharp_signals", "early_money_lock_signals",
    "live_fixtures", "live_snapshots",
    "matchbook_fixtures", "matchbook_1x2_history", "matchbook_ou25_history", "matchbook_btts_history",
    "analyses", "free_matches", "telegram_sent_log", "license_favorites",
}


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_reference_column_migration_is_additive_only():
    sql = _sql()
    for table in EXPECTED_TABLES:
        assert f"alter table public.{table} add column if not exists fixture_uid uuid;" in sql

    forbidden = (
        " set not null",
        " default ",
        " references ",
        " foreign key",
        " create index",
        " update public.",
        " delete from",
        " drop column",
        " drop table",
        " alter column",
    )
    for token in forbidden:
        assert token not in sql


def test_archive_and_legacy_favorite_tables_are_not_mutated():
    sql = _sql()
    executable_lines = [
        line.strip()
        for line in sql.splitlines()
        if line.strip() and not line.lstrip().startswith("--")
    ]
    joined = "\n".join(executable_lines)
    assert "learning_archive_capture_outbox" not in joined
    assert "learning_archive_retention_holds" not in joined
    assert "match_favorites" not in joined


def test_every_executable_statement_only_adds_nullable_fixture_uid():
    executable_lines = [
        line.strip()
        for line in _sql().splitlines()
        if line.strip() and not line.lstrip().startswith("--")
    ]
    assert len(executable_lines) == len(EXPECTED_TABLES)
    assert all(
        line.startswith("alter table public.")
        and line.endswith(" add column if not exists fixture_uid uuid;")
        for line in executable_lines
    )
