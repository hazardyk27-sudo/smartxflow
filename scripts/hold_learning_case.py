#!/usr/bin/env python3
"""Create/refresh the source-history retention hold when Predictor formalizes a case."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from learning_archive.retention import RetentionHoldError, create_retention_hold
from learning_archive.validator import validate_case


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_file", help="Path to formal Predictor case JSON")
    args = parser.parse_args()

    try:
        case = json.loads(Path(args.case_file).read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"FAIL case input: {exc}", file=sys.stderr)
        return 2

    validation = validate_case(case)
    if not validation.ok:
        print("FAIL case validation: " + "; ".join(validation.errors), file=sys.stderr)
        return 1

    try:
        create_retention_hold(
            case_id=case["case_id"],
            match_id_hash=case["match"]["match_id_hash"],
            prediction_at=case["prediction"]["prediction_at"],
        )
    except RetentionHoldError as exc:
        print(f"FAIL retention hold: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({
        "status": "HELD",
        "case_id": case["case_id"],
        "match_id_hash": case["match"]["match_id_hash"],
        "prediction_at": case["prediction"]["prediction_at"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
