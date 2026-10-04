#!/usr/bin/env python3
"""Mirror durable prematch capture requests into Learning Archive CAPTURED events."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from learning_archive.outbox import (
    CaptureOutboxError,
    fetch_pending_capture_events,
    load_dotenv_literal,
    mark_capture_events_mirrored,
    outbox_requests,
)
from scripts.build_learning_revisit_request_batch import build_request_batch
from scripts.enqueue_due_learning_revisit import (
    ARCHIVE_BRANCH,
    DEFAULT_QUEUE,
    DEFAULT_ROOT,
    PrematchEnqueueError,
    _assert_production_checkout,
    _queue_lock,
    _read_queue,
    _run,
    _write_queue_atomic,
    export_archive_snapshot,
)


class PrematchDrainError(RuntimeError):
    pass


def _pending_requests(payload: dict[str, Any]) -> list[dict[str, Any]]:
    requests = payload.get("requests", [])
    if not isinstance(requests, list):
        raise PrematchDrainError("local prematch queue requests must be an array")
    return requests


def _merge_requests(*request_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, set[str]] = {}
    for requests in request_lists:
        for index, item in enumerate(requests):
            if not isinstance(item, dict):
                raise PrematchDrainError(f"prematch request {index} must be an object")
            observed_at = str(item.get("observed_at") or "").strip()
            case_ids = item.get("case_ids")
            if not observed_at or not isinstance(case_ids, list):
                raise PrematchDrainError("prematch request is missing observed_at/case_ids")
            for value in case_ids:
                case_id = str(value or "").strip()
                if not case_id:
                    raise PrematchDrainError("prematch request contains empty case_id")
                grouped.setdefault(observed_at, set()).add(case_id)
    return [
        {"observed_at": observed_at, "case_ids": sorted(case_ids)}
        for observed_at, case_ids in sorted(grouped.items())
    ]


def _clear_queue(queue_file: Path) -> None:
    _write_queue_atomic(
        queue_file,
        {"request_id": "hetzner-prematch-queue", "requests": []},
    )


def _archive_credentials_available() -> bool:
    token = os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip()
    ssh_key = os.environ.get("LEARNING_ARCHIVE_GIT_SSH_KEY", "").strip()
    return bool(token or ssh_key)


def drain_queue(
    app_root: Path,
    queue_file: Path,
    *,
    dotenv: Path | None = None,
) -> dict[str, Any]:
    _assert_production_checkout(app_root)
    if dotenv is not None:
        load_dotenv_literal(str(dotenv))

    # Supabase outbox is the external durable source of truth for pending mirror
    # work. The local queue is retained as a second independent copy.
    outbox_rows = fetch_pending_capture_events()
    outbox_event_ids = [str(row.get("event_id") or "").strip() for row in outbox_rows]
    outbox_event_ids = [value for value in outbox_event_ids if value]
    durable_requests = outbox_requests(outbox_rows)

    with _queue_lock(queue_file):
        queue = _read_queue(queue_file)
        local_requests = _pending_requests(queue)
        requests = _merge_requests(local_requests, durable_requests)
        if not requests:
            return {
                "status": "QUEUE_EMPTY",
                "queued_requests": 0,
                "outbox_pending": 0,
                "captures": 0,
            }

        _run(["git", "fetch", "origin", ARCHIVE_BRANCH], cwd=app_root)
        with tempfile.TemporaryDirectory(prefix="sxf-prematch-drain-") as tmp:
            temp_root = Path(tmp)
            archive_root = temp_root / "archive"
            export_archive_snapshot(app_root, archive_root)

            merged_request_file = temp_root / "request.json"
            merged_request_file.write_text(
                json.dumps(
                    {"request_id": "durable-prematch-merge", "requests": requests},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
            batch = build_request_batch(archive_root, merged_request_file)

            captures = batch.get("captures") if isinstance(batch, dict) else None
            if not isinstance(captures, list):
                raise PrematchDrainError("generated prematch batch has no captures array")
            if not captures:
                mark_capture_events_mirrored(outbox_event_ids)
                _clear_queue(queue_file)
                return {
                    "status": "QUEUE_ALREADY_FULFILLED",
                    "queued_requests": len(local_requests),
                    "outbox_pending": len(outbox_event_ids),
                    "captures": 0,
                }
            if not _archive_credentials_available():
                raise PrematchDrainError(
                    "canonical archive credentials are required to mirror durable queue "
                    "(GitHub token or LEARNING_ARCHIVE_GIT_SSH_KEY)"
                )

            batch_file = temp_root / "due-revisits.json"
            batch_file.write_text(
                json.dumps(batch, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            command = [
                sys.executable,
                str(app_root / "scripts" / "record_learning_revisit_batch.py"),
                str(batch_file),
            ]
            if dotenv is not None:
                command.extend(["--dotenv", str(dotenv)])
            result = subprocess.run(
                command,
                cwd=str(app_root),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=os.environ.copy(),
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "capture recorder failed").strip()
                raise PrematchDrainError(f"archive queue drain failed: {detail}")

            # Only clear durable/local pending state after every CAPTURED receipt
            # was written successfully. If this update fails, the next drain is
            # idempotent and verifies the archive before marking MIRRORED.
            mark_capture_events_mirrored(outbox_event_ids)
            _clear_queue(queue_file)
            output = (result.stdout or "").strip()
            return {
                "status": "QUEUE_DRAINED",
                "queued_requests": len(local_requests),
                "outbox_pending": len(outbox_event_ids),
                "captures": len(captures),
                "recorder": output,
            }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Production SmartXFlow checkout")
    parser.add_argument("--queue-file", default=str(DEFAULT_QUEUE), help="Durable local request queue")
    parser.add_argument("--dotenv", help="Production dotenv consumed by outbox and recorder")
    args = parser.parse_args()

    try:
        result = drain_queue(
            Path(args.root),
            Path(args.queue_file),
            dotenv=Path(args.dotenv) if args.dotenv else None,
        )
    except (
        OSError,
        ValueError,
        PrematchEnqueueError,
        PrematchDrainError,
        CaptureOutboxError,
        RuntimeError,
    ) as exc:
        print(f"PREMATCH_DRAIN_FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
