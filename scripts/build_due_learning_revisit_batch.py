#!/usr/bin/env python3
"""Build a batch of formal Learning Archive cases due for one prematch revisit."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


class DueCaptureError(RuntimeError):
    pass


def _parse_utc(value: str, field: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise DueCaptureError(f"{field} is required")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise DueCaptureError(f"{field} must be ISO-8601") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise DueCaptureError(f"{field} must include timezone")
    return dt.astimezone(timezone.utc)


def _manifest_state(manifest_path: Path) -> tuple[set[str], set[str], set[str]]:
    recorded: set[str] = set()
    captured: set[str] = set()
    finalized: set[str] = set()
    if not manifest_path.exists():
        return recorded, captured, finalized
    for lineno, raw in enumerate(manifest_path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DueCaptureError(f"manifest line {lineno} is invalid JSON") from exc
        if not isinstance(entry, dict):
            raise DueCaptureError(f"manifest line {lineno} must be an object")
        case_id = str(entry.get("case_id") or "").strip()
        event = str(entry.get("event") or "").strip()
        if not case_id:
            continue
        if event == "RECORDED":
            recorded.add(case_id)
        elif event == "CAPTURED":
            captured.add(case_id)
        elif event == "FINALIZED":
            finalized.add(case_id)
    return recorded, captured, finalized


def build_due_batch(archive_root: Path, observed_at: str, max_minutes_before_kickoff: int = 35) -> dict:
    now = _parse_utc(observed_at, "observed_at")
    data_root = archive_root / "learning_archive_data"
    cases_root = data_root / "cases"
    recorded, captured, finalized = _manifest_state(data_root / "manifest.jsonl")

    captures = []
    if not cases_root.exists():
        return {"observed_at": observed_at, "captures": []}

    for case_path in sorted(cases_root.glob("**/case.json")):
        case_doc = json.loads(case_path.read_text(encoding="utf-8"))
        case_id = str(case_doc.get("case_id") or "").strip()
        if not case_id or case_id not in recorded or case_id in finalized or case_id in captured:
            continue

        prediction_at = _parse_utc(case_doc.get("prediction", {}).get("prediction_at"), f"{case_id}.prediction_at")
        kickoff_at = _parse_utc(case_doc.get("match", {}).get("kickoff_at"), f"{case_id}.kickoff_at")
        if now <= prediction_at or now >= kickoff_at:
            continue
        seconds_to_kickoff = (kickoff_at - now).total_seconds()
        if seconds_to_kickoff > max_minutes_before_kickoff * 60:
            continue

        evidence_path = case_path.with_name("evidence.json")
        if not evidence_path.exists():
            raise DueCaptureError(f"{case_id}: evidence.json missing")
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        if not isinstance(evidence, list):
            raise DueCaptureError(f"{case_id}: evidence.json must be an array")

        full_case = dict(case_doc)
        full_case["evidence"] = evidence
        full_case["settlement"] = {"status": "PENDING"}
        captures.append({"case": full_case, "observed_at": observed_at})

    return {"observed_at": observed_at, "captures": captures}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive_root", help="Checkout root of the learning-archive branch")
    parser.add_argument("--observed-at", required=True, help="UTC/offset timestamp for this scheduled scan")
    parser.add_argument("--max-minutes-before-kickoff", type=int, default=35)
    parser.add_argument("--output", help="Write JSON batch to this path instead of stdout")
    args = parser.parse_args()

    try:
        payload = build_due_batch(
            Path(args.archive_root),
            args.observed_at,
            max_minutes_before_kickoff=args.max_minutes_before_kickoff,
        )
    except (OSError, ValueError, DueCaptureError, json.JSONDecodeError) as exc:
        print(f"FAIL due revisit selector: {exc}", file=sys.stderr)
        return 1

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        Path(args.output).write_text(encoded, encoding="utf-8")
    else:
        sys.stdout.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
