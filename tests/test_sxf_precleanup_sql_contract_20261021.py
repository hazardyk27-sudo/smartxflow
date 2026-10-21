"""Static safety contracts for audit-only SQL. No production database access."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1] / "scripts" / "maintenance"
AUDIT_FILES = (
    "sxf_precleanup_evidence.sql",
    "sxf_archive_fixture_parity_readonly.sql",
    "sxf_duplicate_index_audit_readonly.sql",
    "sxf_future_fixture_history_risk_readonly.sql",
    "sxf_archive_backfill_readiness_readonly.sql",
    "sxf_archive_snapshot_sample_readonly.sql",
)
DDL_OR_DML = re.compile(
    r"^\s*(?:DELETE|UPDATE|INSERT|ALTER|CREATE|DROP|TRUNCATE|REINDEX|"
    r"VACUUM|GRANT|REVOKE|CALL|DO|MERGE)\b", re.I | re.M
)


def test_all_maintenance_sql_is_explicitly_read_only():
    for file in AUDIT_FILES:
        src = (ROOT / file).read_text(encoding="utf-8")
        assert re.search(r"BEGIN\s+TRANSACTION\s+READ\s+ONLY", src, re.I), file
        assert re.search(r"SET\s+LOCAL\s+statement_timeout", src, re.I), file
        assert re.search(r"SET\s+LOCAL\s+lock_timeout", src, re.I), file
        assert re.search(r"\bCOMMIT;", src, re.I), file
        assert not DDL_OR_DML.search(src), file


def test_archive_day_uses_turkey_kickoff_not_raw_capture_or_utc_fixture_date():
    probe = (ROOT / "sxf_precleanup_evidence.sql").read_text(encoding="utf-8")
    audit = (ROOT / "sxf_archive_fixture_parity_readonly.sql").read_text(encoding="utf-8")
    assert "kickoff_utc AT TIME ZONE 'Europe/Istanbul'" in probe
    assert "kickoff_utc AT TIME ZONE 'Europe/Istanbul'" in audit
    assert "source_archive_temporal_lineage_verified',false" in probe
    assert "future_fixture_history_protected',false" in probe
    assert "independent_backup_verified',false" in probe
    assert "source_archive_parity_verified',false" in probe
    assert "fixture_date=probe_day.d" not in probe
    assert "fixture_date AS d" not in probe


def test_readonly_index_audit_never_authorizes_pruning():
    audit = (ROOT / "sxf_duplicate_index_audit_readonly.sql").read_text(encoding="utf-8")
    assert "FALSE AS production_drop_authorized" in audit
    for index in (
        "idx_mw_snap_scraped", "idx_mw_snap_scraped_utc",
        "idx_live_snapshots_hash", "idx_live_snap_hash",
    ):
        assert index in audit
    assert "constraint_refs" in audit
    assert "external_refs" in audit
    assert "structurally_equivalent" in audit


def test_future_fixture_timestamp_only_purge_prohibited():
    src = (ROOT / "sxf_future_fixture_history_risk_readonly.sql").read_text(encoding="utf-8")
    assert "fixture_uid=f.fixture_uid" in src
    assert "kickoff_utc > now()" in src
    assert "has_older_prematch_history" in src
    assert "FALSE AS time_only_delete_safe" in src


def test_archive_backfill_blocks_without_independent_cold_backup():
    src = (ROOT / "sxf_archive_backfill_readiness_readonly.sql").read_text(encoding="utf-8")
    assert "storage.objects" in src
    assert "sxf-research-archive" in src
    assert "source_fixtures" in src
    assert "unarchived_source_fixtures" in src
    assert "fixture_uid=s.fixture_uid" in src
    assert "'backup_restored_and_verified',false" in src
    assert "'archive_data_parity_verified',false" in src
    assert "'time_only_cleanup_safe',false" in src


def test_archive_snapshot_sample_stays_bounded_and_does_not_certify_parity():
    src = (ROOT / "sxf_archive_snapshot_sample_readonly.sql").read_text(encoding="utf-8")
    assert "ORDER BY f.fixture_uid LIMIT 8" in src
    assert "ORDER BY scraped_at_utc ASC LIMIT 3" in src
    assert "a.local_date=d.d AND a.source_id=s.id" in src
    assert "'complete_row_parity_verified',false" in src
