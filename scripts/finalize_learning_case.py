#!/usr/bin/env python3
"""Finalize one Predictor BET/WATCH/PASS case into the private Learning Archive."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from learning_archive.exporter import ArchiveFinalizationError, LearningArchiveExporter
from learning_archive.source_history import SXFHistoryError, fetch_selected_match_history


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_file", help="Path to Predictor case JSON")
    args = parser.parse_args()

    try:
        case = json.loads(Path(args.case_file).read_text(encoding="utf-8"))
        match_hash = case["match"]["match_id_hash"]
        history = fetch_selected_match_history(match_hash)
        result = LearningArchiveExporter.from_env().finalize_case(case, history.snapshots)
    except (OSError, ValueError, KeyError, SXFHistoryError, ArchiveFinalizationError, RuntimeError) as exc:
        print(f"FAIL archive finalization: {exc}", file=sys.stderr)
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
