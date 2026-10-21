"""Static safety contracts for audit-only SQL. No production database access."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1] / "scripts" / "maintenance"
AUDIT_FILES = (
    "sxf_precleanup_evidence.sql",
    "sxf_archive_fixture_parity_readonly.sql",
    "sxf_duplicate_index_audit_readonly.sql",
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
