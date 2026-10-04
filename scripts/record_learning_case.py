#!/usr/bin/env python3
"""Record one formal Predictor BET/WATCH/PASS case in the in-repo Learning Archive."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from learning_archive.exporter import ArchiveFinalizationError, LearningArchiveExporter
from learning_archive.revisit import RevisitCaptureError, prepare_revisit_snapshots
from learning_archive.source_history import SXFHistoryError, fetch_selected_match_history


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_file", help="Path to formal Predictor case JSON")
    parser.add_argument("--observed-at", help="UTC/offset timestamp for this archive capture")
    parser.add_argument("--revisit", action="store_true", help="Append a later prematch capture")
    args = parser.parse_args()

    try:
        case = json.loads(Path(args.case_file).read_text(encoding="utf-8"))
        match_hash = case["match"]["match_id_hash"]
        observed_at = args.observed_at or case["provenance"]["archive_created_at"]
        if args.revisit and not args.observed_at:
            raise ValueError("--revisit requires explicit --observed-at for deterministic capture identity")
        history = fetch_selected_match_history(match_hash)
        snapshots = history.snapshots
        if args.revisit:
            snapshots = prepare_revisit_snapshots(case, snapshots, observed_at)
        result = LearningArchiveExporter.from_env().record_case(
            case,
            snapshots,
            observed_at=observed_at,
            revisit=args.revisit,
        )
    except (
        OSError,
        ValueError,
        KeyError,
        SXFHistoryError,
        RevisitCaptureError,
        ArchiveFinalizationError,
        RuntimeError,
    ) as exc:
        print(f"FAIL archive record: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({
        "status": result.status,
        "archive_reference": result.archive_reference,
        "archive_commit": result.archive_commit,
        "checksum_summary": result.checksum_summary,
        "idempotent": result.idempotent,
        "source_tables": history.source_tables,
        "unavailable_optional_tables": history.unavailable_optional_tables,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
