"""Pre-cleanup policy tests: no DB credentials, external dependencies, or writes."""
import importlib.util
from datetime import date
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "maintenance" / "sxf_precleanup_preflight.py"
spec = importlib.util.spec_from_file_location("sxf_precleanup_preflight", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

TODAY = date(2026, 10, 21)


def fixture():
    return {
        "db_today": "2026-10-21",
        "cutoff": "2026-10-15",
        "earliest_source": "2026-10-13",
        "archives": [
            {"date": "2026-10-13", "status": "COMPLETE", "full": True, "cold": "VERIFIED", "allow": True},
            {"date": "2026-10-14", "status": "COMPLETE", "full": True, "cold": "VERIFIED", "allow": True},
        ],
        "pending_holds": 0,
        "pending_outbox": 0,
        "independent_backup_verified": True,
        "source_archive_parity_verified": True,
    }


def test_cutoff_keep_seven_calendar_days():
    assert mod.retention_cutoff(TODAY) == date(2026, 10, 15)
    assert mod.retention_cutoff(date(2026, 10, 22)) == date(2026, 10, 16)


def test_all_evidence_still_requires_manual_review():
    report = mod.assess(fixture(), TODAY)
    assert report["status"] == "GATES_PASSED_MANUAL_REVIEW_REQUIRED"
    assert report["cutoff_utc"] == "2026-10-14T21:00:00+00:00"


def test_missing_day_fail_closed():
    evidence = fixture()
    evidence["archives"].pop()
    report = mod.assess(evidence, TODAY)
    assert "ARCHIVE_DAY_MISSING:2026-10-14" in report["failures"]


def test_no_cold_backup_or_retention_permission():
    evidence = fixture()
    evidence["archives"][0].update(cold="COLD_BACKUP_PENDING", allow=False)
    failed = mod.assess(evidence, TODAY)["failures"]
    assert "COLD_BACKUP_UNVERIFIED:2026-10-13" in failed
    assert "SOURCE_RETENTION_NOT_APPROVED:2026-10-13" in failed


def test_protect_hold_and_outbox():
    evidence = fixture()
    evidence.update(pending_holds=1, pending_outbox=2)
    failed = mod.assess(evidence, TODAY)["failures"]
    assert "NONZERO_PENDING_HOLDS:1" in failed
    assert "NONZERO_PENDING_OUTBOX:2" in failed


def test_missing_independent_verification_never_approves():
    evidence = fixture()
    evidence["independent_backup_verified"] = False
    evidence["source_archive_parity_verified"] = False
    failed = mod.assess(evidence, TODAY)["failures"]
    assert "INDEPENDENT_BACKUP_NOT_VERIFIED" in failed
    assert "SOURCE_ARCHIVE_PARITY_NOT_VERIFIED" in failed


def test_clock_and_unknown_earliest_fail_closed():
    evidence = fixture()
    evidence["db_today"] = "2026-10-20"
    evidence.pop("earliest_source")
    failed = mod.assess(evidence, TODAY)["failures"]
    assert "DATABASE_CLOCK_MISMATCH" in failed
    assert "EARLIEST_SOURCE_NOT_VERIFIED" in failed


def test_no_old_source_does_not_claim_cleanup_ready():
    evidence = fixture()
    evidence["earliest_source"] = "2026-10-15"
    assert "NO_OLD_SOURCE_ROWS_VERIFIED" in mod.assess(evidence, TODAY)["failures"]
