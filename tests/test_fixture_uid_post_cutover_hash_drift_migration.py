from pathlib import Path


MIGRATION = Path("migrations/2026_10_13_fixture_identity_v2_post_cutover_hash_drift.sql")


def test_post_cutover_hash_drift_no_longer_aborts_mapped_uid_batch():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "create or replace function public.record_betwatch_fixture_batch_v2" in sql.lower()
    assert "mapped legacy hash drift for event" not in sql
    assert "mapped physical collision for event %" in sql
    assert "exact fixture already owned by Betwatch event %" in sql
    assert "orphan Betwatch registry mapping for event %" in sql


def test_post_cutover_mapped_rows_preserve_legacy_hash_and_uid_safety():
    sql = MIGRATION.read_text(encoding="utf-8")

    mapped_block = sql.split("if v_uid is not null then", 1)[1].split("select count(*)", 1)[0]

    assert "set home_team = v_row.home_team" in mapped_block
    assert "match_id_hash = v_row.match_id_hash" not in mapped_block
    assert "where f.fixture_uid <> v_uid" in mapped_block
    assert "where source = 'betwatch'" in mapped_block
    assert "and source_event_id = v_row.source_event_id" in mapped_block
