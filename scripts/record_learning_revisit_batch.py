#!/usr/bin/env python3
"""Append deterministic prematch CAPTURED events for formal Learning Archive cases."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from learning_archive.exporter import ArchiveFinalizationError, LearningArchiveExporter
from learning_archive.revisit import RevisitCaptureError, prepare_revisit_snapshots
from learning_archive.supabase_source import (
    LearningArchiveSourceError,
    read_learning_archive_match_history,
)


def _flatten_history(history_payload) -> list[dict]:
    rows: list[dict] = []
    for table_name, table_rows in history_payload.histories.items():
        for row in table_rows:
            copied = dict(row)
            copied["_archive_source_table"] = table_name
            rows.append(copied)
    rows.sort(key=lambda row: (
        str(row.get("scraped_at") or row.get("scraped_at_utc") or row.get("snapshot_at") or row.get("created_at") or ""),
        str(row.get("_archive_source_table") or ""),
    ))
    return rows


def _load_dotenv_literal(path: str) -> None:
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if key.startswith("export "):
                key = key[7:].strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            if key:
                os.environ[key] = value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch_file", help="JSON from build_due_learning_revisit_batch.py")
    parser.add_argument("--dotenv", help="Optional dotenv file loaded literally, without shell expansion")
    args = parser.parse_args()

    if args.dotenv:
        try:
            _load_dotenv_literal(args.dotenv)
        except OSError as exc:
            print(f"FAIL revisit batch dotenv: {exc}", file=sys.stderr)
            return 1

    try:
        payload = json.loads(Path(args.batch_file).read_text(encoding="utf-8"))
        captures = payload.get("captures") if isinstance(payload, dict) else None
        if not isinstance(captures, list):
            raise ValueError("batch captures must be an array")
        if not captures:
            print(json.dumps({"status": "NO_DUE_CAPTURES", "captured": 0}, sort_keys=True))
            return 0

        exporter = LearningArchiveExporter.from_env()
        receipts = []
        failures = []

        for index, item in enumerate(captures):
            case_id = f"index:{index}"
            try:
                if not isinstance(item, dict):
                    raise ValueError("capture item must be an object")
                case = item["case"]
                observed_at = item["observed_at"]
                case_id = str(case.get("case_id") or case_id)
                match_hash = str(case["match"]["match_id_hash"]).strip().lower()
                history = read_learning_archive_match_history(match_hash)
                snapshots = prepare_revisit_snapshots(case, _flatten_history(history), observed_at)
                result = exporter.record_case(
                    case,
                    snapshots,
                    observed_at=observed_at,
                    revisit=True,
                )
                if result.status != "CAPTURED":
                    raise ArchiveFinalizationError(f"unexpected archive status {result.status}")
                receipts.append({
                    "case_id": case_id,
                    "status": result.status,
                    "archive_reference": result.archive_reference,
                    "archive_commit": result.archive_commit,
                    "checksum_summary": result.checksum_summary,
                    "idempotent": result.idempotent,
                    "source_tables": list(history.source_tables),
                })
            except (
                KeyError,
                ValueError,
                RevisitCaptureError,
                LearningArchiveSourceError,
                ArchiveFinalizationError,
                RuntimeError,
            ) as exc:
                failures.append({"case_id": case_id, "error": str(exc)})

        output = {
            "status": "BATCH_CAPTURED" if not failures else "BATCH_PARTIAL_FAILED",
            "requested": len(captures),
            "captured": len(receipts),
            "failed": len(failures),
            "receipts": receipts,
            "failures": failures,
        }
        stream = sys.stdout if not failures else sys.stderr
        print(json.dumps(output, ensure_ascii=False, sort_keys=True), file=stream)
        return 0 if not failures else 1
    except (OSError, ValueError, json.JSONDecodeError, ArchiveFinalizationError) as exc:
        print(f"FAIL revisit batch: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
