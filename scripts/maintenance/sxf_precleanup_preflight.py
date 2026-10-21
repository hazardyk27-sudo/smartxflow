#!/usr/bin/env python3
"""Fail-closed, READ-ONLY retention preflight. This tool contains NO delete path.

Run with PostgreSQL client connection via PGHOST/PGUSER/PGDATABASE/PGPASSWORD
(or PG* service settings). The SQL is a bounded, read-only catalog/archive
probe and never reads account records or private archive payloads.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ISTANBUL = ZoneInfo("Europe/Istanbul")
SQL_PATH = Path(__file__).with_name("sxf_precleanup_evidence.sql")


def retention_cutoff(today: date) -> date:
    """Keep today and the previous SIX calendar days (seven inclusive)."""
    return today - timedelta(days=6)


def assess(evidence: dict, today: date) -> dict:
    """Read-only fail-closed evidence evaluation.

    Snapshot capture date and archived fixture date are NOT interchangeable.
    Archive runs are partitioned by fixture day, including snapshots captured
    days before kickoff. Only source fixture dates may be compared to runs.
    Independent full-row lineage, archival backup, and future-fixture safety
    remain separate hard gates; SQL never self-certifies any of them.
    """
    cutoff = retention_cutoff(today)
    failures = []
    if evidence.get("db_today") != today.isoformat():
        failures.append("DATABASE_CLOCK_MISMATCH")
    if evidence.get("cutoff") != cutoff.isoformat():
        failures.append("CUTOFF_MISMATCH")
    try:
        oldest = date.fromisoformat(evidence["earliest_source"])
    except (KeyError, ValueError, TypeError):
        oldest = None
        failures.append("EARLIEST_SOURCE_NOT_VERIFIED")
    if oldest is not None and oldest >= cutoff:
        failures.append("NO_OLD_SOURCE_ROWS_VERIFIED")

    if evidence.get("source_date_axis") != "observation_timestamp":
        failures.append("SOURCE_DATE_AXIS_UNVERIFIED")
    if evidence.get("archive_date_axis") != "kickoff_istanbul_day":
        failures.append("ARCHIVE_DATE_AXIS_UNVERIFIED")
    if evidence.get("source_archive_temporal_lineage_verified") is not True:
        failures.append("OBSERVATION_TO_FIXTURE_LINEAGE_UNVERIFIED")

    # These are fixture start dates, never the observed-at day of a raw row.
    raw_days = evidence.get("source_fixture_dates")
    days = []
    if not isinstance(raw_days, list) or not raw_days:
        failures.append("SOURCE_FIXTURE_DATE_SET_NOT_VERIFIED")
    else:
        try:
            days = sorted({date.fromisoformat(day) for day in raw_days})
        except (ValueError, TypeError):
            failures.append("SOURCE_FIXTURE_DATE_SET_INVALID")
            days = []
    archive = {a.get("date"): a for a in evidence.get("archives", []) if isinstance(a, dict)}
    for day in days:
        if day >= cutoff:
            failures.append(f"NOT_OLD_FIXTURE_DAY:{day.isoformat()}")
            continue
        row = archive.get(day.isoformat())
        if row is None:
            failures.append(f"ARCHIVE_FIXTURE_DAY_MISSING:{day.isoformat()}")
            continue
        if row.get("status") != "COMPLETE" or row.get("full") is not True:
            failures.append(f"ARCHIVE_NOT_COMPLETE:{day.isoformat()}")
        if row.get("cold") != "VERIFIED":
            failures.append(f"COLD_BACKUP_UNVERIFIED:{day.isoformat()}")
        if row.get("allow") is not True:
            failures.append(f"SOURCE_RETENTION_NOT_APPROVED:{day.isoformat()}")

    # Check one recent eligible fixture-day as a cheap, separately visible
    # smoke test. A pass is NOT full source/archive parity.
    probe = evidence.get("fixture_probe")
    probe_day = (cutoff - timedelta(days=1)).isoformat()
    probe_fields = ("source_total", "archive_total", "missing_in_archive",
                    "archive_not_in_source", "kickoff_mismatches",
                    "source_null_uid", "archive_null_uid")
    if not isinstance(probe, dict) or probe.get("date") != probe_day:
        failures.append("FIXTURE_PROBE_DAY_UNVERIFIED")
    elif any(not isinstance(probe.get(k), int) or isinstance(probe[k], bool)
             or probe[k] < 0 for k in probe_fields):
        failures.append("FIXTURE_PROBE_INVALID")
    elif (probe["source_total"] != probe["archive_total"]
          or any(probe[k] for k in probe_fields[2:])):
        failures.append(f"FIXTURE_UID_PARITY_MISMATCH:{probe_day}")

    for key in ("pending_holds", "pending_outbox"):
        value = evidence.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            failures.append(f"UNVERIFIED_{key.upper()}")
        elif value != 0:
            failures.append(f"NONZERO_{key.upper()}:{value}")
    if evidence.get("independent_backup_verified") is not True:
        failures.append("INDEPENDENT_BACKUP_NOT_VERIFIED")
    if evidence.get("source_archive_parity_verified") is not True:
        failures.append("SOURCE_ARCHIVE_PARITY_NOT_VERIFIED")
    if evidence.get("future_fixture_history_protected") is not True:
        failures.append("FUTURE_FIXTURE_HISTORY_NOT_PROTECTED")

    return {
        "local_today": today.isoformat(),
        "cutoff_local_start": cutoff.isoformat() + "T00:00:00+03:00",
        "cutoff_utc": datetime.combine(cutoff, datetime.min.time(), ISTANBUL).astimezone(
            ZoneInfo("UTC")
        ).isoformat(),
        "earliest_observed_source_date": evidence.get("earliest_source"),
        "fixture_probe": probe if isinstance(probe, dict) else None,
        "status": "BLOCKED" if failures else "GATES_PASSED_MANUAL_REVIEW_REQUIRED",
        "failures": sorted(set(failures)),
        "note": "No DELETE, DROP, TRUNCATE, REINDEX or VACUUM FULL is executed.",
    }


def load_from_psql(sql_path: Path) -> dict:
    command = [
        "psql", "-X", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1",
        "-f", str(sql_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=35, check=True)
    rows = [line.strip() for line in result.stdout.splitlines() if line.strip().startswith("{")]
    if len(rows) != 1:
        raise ValueError("Expected exactly one JSON evidence row from read-only SQL")
    return json.loads(rows[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-json", type=Path, help="Test an existing audit JSON (no DB access)")
    args = parser.parse_args()
    try:
        evidence = json.loads(args.evidence_json.read_text(encoding="utf-8")) if args.evidence_json else load_from_psql(SQL_PATH)
        report = assess(evidence, datetime.now(ISTANBUL).date())
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if not report["failures"] else 2
    except (OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "BLOCKED", "error_type": type(exc).__name__}), file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
