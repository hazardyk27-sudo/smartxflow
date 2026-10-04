#!/usr/bin/env python3
"""Record every formal Predictor case from one report in the in-repo Learning Archive.

The input may be either:
- one case object,
- a JSON array of case objects, or
- an object with a top-level ``cases`` array.

Writes are individually durable and idempotent. If one case fails, the script keeps the
successful receipts, reports every failure, and exits non-zero so the Predictor must not
claim the report is fully archived. Re-running the same batch is safe.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from learning_archive.exporter import ArchiveFinalizationError, LearningArchiveExporter
from learning_archive.source_history import SXFHistoryError, fetch_selected_match_history


def _load_cases(path: str) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        cases = payload
    elif isinstance(payload, dict) and isinstance(payload.get("cases"), list):
        cases = payload["cases"]
    elif isinstance(payload, dict):
        cases = [payload]
    else:
        raise ValueError("batch file must contain a case object, array, or {'cases': [...]} object")

    if not cases:
        raise ValueError("batch contains no cases")
    if not all(isinstance(case, dict) for case in cases):
        raise ValueError("every batch item must be a case object")
    return cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch_file", help="Path to Predictor case JSON/object/array")
    args = parser.parse_args()

    try:
        cases = _load_cases(args.batch_file)
        exporter = LearningArchiveExporter.from_env()
    except (OSError, ValueError, json.JSONDecodeError, ArchiveFinalizationError, RuntimeError) as exc:
        print(json.dumps({"status": "BATCH_FAILED", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    receipts: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for index, case in enumerate(cases):
        case_id = str(case.get("case_id") or f"index:{index}")
        try:
            match_hash = case["match"]["match_id_hash"]
            observed_at = case["provenance"]["archive_created_at"]
            history = fetch_selected_match_history(match_hash)
            result = exporter.record_case(
                case,
                history.snapshots,
                observed_at=observed_at,
                revisit=False,
            )
            if result.status != "RECORDED":
                raise ArchiveFinalizationError(f"unexpected archive status {result.status}")
            receipts.append({
                "case_id": case_id,
                "status": result.status,
                "archive_reference": result.archive_reference,
                "archive_commit": result.archive_commit,
                "checksum_summary": result.checksum_summary,
                "idempotent": result.idempotent,
                "source_tables": history.source_tables,
                "unavailable_optional_tables": history.unavailable_optional_tables,
            })
        except (OSError, ValueError, KeyError, SXFHistoryError, ArchiveFinalizationError, RuntimeError) as exc:
            failures.append({"case_id": case_id, "error": str(exc)})

    output = {
        "status": "BATCH_RECORDED" if not failures else "BATCH_PARTIAL_FAILED",
        "requested": len(cases),
        "recorded": len(receipts),
        "failed": len(failures),
        "receipts": receipts,
        "failures": failures,
    }
    stream = sys.stdout if not failures else sys.stderr
    print(json.dumps(output, ensure_ascii=False, sort_keys=True), file=stream)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
