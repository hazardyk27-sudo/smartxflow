from pathlib import Path


MIGRATION = Path("migrations/2026_10_13_moneyway_history_fixture_uid_lookup_indexes.sql")


def test_uid_history_lookup_indexes_cover_all_moneyway_markets():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    for table in (
        "moneyway_1x2_history",
        "moneyway_ou25_history",
        "moneyway_btts_history",
    ):
        assert f"on public.{table} (fixture_uid, scraped_at desc)" in sql
        assert "create index concurrently" in sql
