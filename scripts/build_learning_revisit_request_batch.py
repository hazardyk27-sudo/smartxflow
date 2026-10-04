#!/usr/bin/env python3
"""Build a deterministic prematch revisit batch from an explicit request file."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from scripts.build_due_learning_revisit_batch import DueCaptureError, build_due_batch


class CaptureRequestError(RuntimeError):
    pass


def build_request_batch(archive_root: Path, request_file: Path) -> dict:
    try:
        payload = json.loads(request_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CaptureRequestError("capture request file contains invalid JSON") from exc
    if not isinstance(payload, dict):
        raise CaptureRequestError("capture request must be an object")
    requests = payload.get("requests")
    if not isinstance(requests, list) or not requests:
        raise CaptureRequestError("capture request requires a non-empty requests array")

    captures: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(requests):
        if not isinstance(item, dict):
            raise CaptureRequestError(f"requests[{index}] must be an object")
        observed_at = str(item.get("observed_at") or "").strip()
        raw_case_ids = item.get("case_ids")
        if not observed_at:
            raise CaptureRequestError(f"requests[{index}].observed_at is required")
        if not isinstance(raw_case_ids, list) or not raw_case_ids:
            raise CaptureRequestError(f"requests[{index}].case_ids must be a non-empty array")
        case_ids = [str(value or "").strip() for value in raw_case_ids]
        if any(not case_id for case_id in case_ids):
            raise CaptureRequestError(f"requests[{index}].case_ids contains an empty value")
        if len(set(case_ids)) != len(case_ids):
            raise CaptureRequestError(f"requests[{index}].case_ids contains duplicates")
        for case_id in case_ids:
            key = (observed_at, case_id)
            if key in seen:
                raise CaptureRequestError(f"duplicate capture request for {case_id} at {observed_at}")
            seen.add(key)

        part = build_due_batch(
            archive_root,
            observed_at,
            case_ids=set(case_ids),
        )
        captures.extend(part.get("captures") or [])

    return {
        "request_id": str(payload.get("request_id") or request_file.stem),
        "captures": captures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive_root", help="Checkout root of the learning-archive branch")
    parser.add_argument("request_file", help="Explicit JSON request file")
    parser.add_argument("--output", help="Write JSON batch to this path instead of stdout")
    args = parser.parse_args()

    try:
        batch = build_request_batch(Path(args.archive_root), Path(args.request_file))
    except (OSError, ValueError, DueCaptureError, CaptureRequestError) as exc:
        print(f"FAIL revisit request queue: {exc}", file=sys.stderr)
        return 1

    encoded = json.dumps(batch, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        Path(args.output).write_text(encoded, encoding="utf-8")
    else:
        sys.stdout.write(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
