from pathlib import Path


MIGRATION = Path("migrations/2026_10_06_fixture_identity_v2_final_cutover.sql")


def test_final_cutover_fails_closed_on_identity_integrity_preconditions():
    text = MIGRATION.read_text()

    required = (
        "record_betwatch_fixture_batch_v2",
        "fixture_uid is null",
        "duplicate fixture_uid exists",
        "exact physical duplicate exists",
        "orphan Betwatch registry row exists",
        "Betwatch UID multi-owner exists",
        "fixtures_match_id_hash_key",
        "fixture_source_ids_betwatch_fixture_uid_uidx",
    )
    for token in required:
        assert token in text


def test_final_cutover_only_demotes_legacy_hash_uniqueness():
    text = MIGRATION.read_text().lower()

    assert "drop constraint fixtures_match_id_hash_key" in text
    assert "create index if not exists fixtures_match_id_hash_idx" in text
    assert "delete from" not in text
    assert "truncate" not in text
    assert "drop table" not in text
    assert "update public.fixtures" not in text
    assert "merge" not in text
