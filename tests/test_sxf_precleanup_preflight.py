"""Read-only fixture-day versus observation-timestamp safety contract tests."""
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
        # Observation predates ALL fixture days. It must never be treated as
        # a required archive partition date.
        "earliest_source": "2026-10-05",
        "source_date_axis": "observation_timestamp",
        "archive_date_axis": "fixture_day",
        "source_fixture_dates": ["2026-10-13", "2026-10-14"],
        "archives": [
            {"date": "2026-10-13", "status": "COMPLETE", "full": True, "cold": "VERIFIED", "allow": True},
            {"date": "2026-10-14", "status": "COMPLETE", "full": True, "cold": "VERIFIED", "allow": True},
        ],
        "fixture_probe": {
            "date": "2026-10-14",
            "source_total": 152, "archive_total": 152, "missing_in_archive": 0,
            "archive_not_in_source": 0, "kickoff_mismatches": 0,
            "source_null_uid": 0, "archive_null_uid": 0,
        },
        "pending_holds": 0,
        "pending_outbox": 0,
        "source_archive_temporal_lineage_verified": True,
        "independent_backup_verified": True,
        "source_archive_parity_verified": True,
        "future_fixture_history_protected": True,
    }


def test_cutoff_keep_seven_calendar_days():
    assert mod.retention_cutoff(TODAY) == date(2026, 10, 15)
    assert mod.retention_cutoff(date(2026, 10, 22)) == date(2026, 10, 16)


def test_complete_evidence_still_requires_manual_review():
    report = mod.assess(fixture(), TODAY)
    assert report["status"] == "GATES_PASSED_MANUAL_REVIEW_REQUIRED"
    assert report["cutoff_utc"] == "2026-10-14T21:00:00+00:00"
    assert report["earliest_observed_source_date"] == "2026-10-05"


def test_observation_day_is_not_assumed_to_be_fixture_archive_day():
    evidence = fixture()
    assert "2026-10-05" not in evidence["source_fixture_dates"]
    assert mod.assess(evidence, TODAY)["failures"] == []


def test_missing_fixture_day_blocks():
    evidence = fixture()
    evidence["archives"].pop()
    report = mod.assess(evidence, TODAY)
    assert "ARCHIVE_FIXTURE_DAY_MISSING:2026-10-14" in report["failures"]


def test_cold_backup_and_approval_are_independent():
    evidence = fixture()
    evidence["archives"][0].update(cold="COLD_BACKUP_PENDING", allow=False)
    failed = mod.assess(evidence, TODAY)["failures"]
    assert "COLD_BACKUP_UNVERIFIED:2026-10-13" in failed
    assert "SOURCE_RETENTION_NOT_APPROVED:2026-10-13" in failed


def test_fixture_probe_matches_live_mismatch():
    evidence = fixture()
    evidence["fixture_probe"].update(source_total=164, archive_total=152,
                                     missing_in_archive=18, archive_not_in_source=6)
    failed = mod.assess(evidence, TODAY)["failures"]
    assert "FIXTURE_UID_PARITY_MISMATCH:2026-10-14" in failed


def test_invalid_or_wrong_day_probe_fails_closed():
    evidence = fixture()
    evidence["fixture_probe"]["date"] = "2026-10-13"
    assert "FIXTURE_PROBE_DAY_UNVERIFIED" in mod.assess(evidence, TODAY)["failures"]
    evidence["fixture_probe"]["date"] = "2026-10-14"
    evidence["fixture_probe"]["source_total"] = None
    assert "FIXTURE_PROBE_INVALID" in mod.assess(evidence, TODAY)["failures"]


def test_source_fixture_dates_must_be_explicit_and_correct():
    evidence = fixture()
    evidence["source_fixture_dates"] = []
    assert "SOURCE_FIXTURE_DATE_SET_NOT_VERIFIED" in mod.assess(evidence, TODAY)["failures"]
    evidence["source_fixture_dates"] = ["not a date"]
    assert "SOURCE_FIXTURE_DATE_SET_INVALID" in mod.assess(evidence, TODAY)["failures"]


def test_temporal_axis_and_future_fixture_protection_cannot_be_inferred():
    evidence = fixture()
    evidence["source_archive_temporal_lineage_verified"] = False
    evidence["future_fixture_history_protected"] = False
    evidence["archive_date_axis"] = "observation_timestamp"
    failed = mod.assess(evidence, TODAY)["failures"]
    assert "OBSERVATION_TO_FIXTURE_LINEAGE_UNVERIFIED" in failed
    assert "FUTURE_FIXTURE_HISTORY_NOT_PROTECTED" in failed
    assert "ARCHIVE_DATE_AXIS_UNVERIFIED" in failed


def test_pending_holds_and_outbox_protected():
    evidence = fixture()
    evidence.update(pending_holds=1, pending_outbox=2)
    failed = mod.assess(evidence, TODAY)["failures"]
    assert "NONZERO_PENDING_HOLDS:1" in failed
    assert "NONZERO_PENDING_OUTBOX:2" in failed


def test_missing_independent_backup_or_source_parity_blocks():
    evidence = fixture()
    evidence["independent_backup_verified"] = False
    evidence["source_archive_parity_verified"] = False
    failed = mod.assess(evidence, TODAY)["failures"]
    assert "INDEPENDENT_BACKUP_NOT_VERIFIED" in failed
    assert "SOURCE_ARCHIVE_PARITY_NOT_VERIFIED" in failed


def test_clock_and_earliest_source_are_fail_closed():
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
