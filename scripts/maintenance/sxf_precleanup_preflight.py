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
    """Independent gates: the presence of an archive is never approval to delete."""
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
    if oldest is not None and oldest < cutoff:
        archive = {a.get("date"): a for a in evidence.get("archives", []) if isinstance(a, dict)}
        for offset in range((cutoff - oldest).days):
            day = (oldest + timedelta(days=offset)).isoformat()
            row = archive.get(day)
            if row is None:
                failures.append(f"ARCHIVE_DAY_MISSING:{day}")
                continue
            if row.get("status") != "COMPLETE" or row.get("full") is not True:
                failures.append(f"ARCHIVE_NOT_COMPLETE:{day}")
            if row.get("cold") != "VERIFIED":
                failures.append(f"COLD_BACKUP_UNVERIFIED:{day}")
            if row.get("allow") is not True:
                failures.append(f"SOURCE_RETENTION_NOT_APPROVED:{day}")
    elif oldest is not None:
        failures.append("NO_OLD_SOURCE_ROWS_VERIFIED")
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
    return {
        "local_today": today.isoformat(),
        "cutoff_local_start": cutoff.isoformat() + "T00:00:00+03:00",
        "cutoff_utc": datetime.combine(cutoff, datetime.min.time(), ISTANBUL).astimezone(
            ZoneInfo("UTC")
        ).isoformat(),
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
