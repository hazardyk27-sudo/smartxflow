#!/usr/bin/env python3
"""Drain the durable Hetzner prematch queue into Learning Archive CAPTURED events."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from scripts.build_learning_revisit_request_batch import build_request_batch
from scripts.enqueue_due_learning_revisit import (
    ARCHIVE_BRANCH,
    DEFAULT_QUEUE,
    DEFAULT_ROOT,
    PrematchEnqueueError,
    _assert_production_checkout,
    _queue_lock,
    _read_queue,
    _remove_worktree,
    _run,
    _write_queue_atomic,
)


class PrematchDrainError(RuntimeError):
    pass


def _pending_requests(payload: dict[str, Any]) -> list[dict[str, Any]]:
    requests = payload.get("requests", [])
    if not isinstance(requests, list):
        raise PrematchDrainError("local prematch queue requests must be an array")
    return requests


def _clear_queue(queue_file: Path) -> None:
    _write_queue_atomic(
        queue_file,
        {"request_id": "hetzner-prematch-queue", "requests": []},
    )


def drain_queue(
    app_root: Path,
    queue_file: Path,
    *,
    dotenv: Path | None = None,
) -> dict[str, Any]:
    _assert_production_checkout(app_root)
    token = os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip()

    with _queue_lock(queue_file):
        queue = _read_queue(queue_file)
        requests = _pending_requests(queue)
        if not requests:
            return {"status": "QUEUE_EMPTY", "queued_requests": 0, "captures": 0}

        _run(["git", "fetch", "origin", ARCHIVE_BRANCH], cwd=app_root)
        with tempfile.TemporaryDirectory(prefix="sxf-prematch-drain-") as tmp:
            temp_root = Path(tmp)
            archive_root = temp_root / "archive"
            _run(
                ["git", "worktree", "add", "--detach", str(archive_root), f"origin/{ARCHIVE_BRANCH}"],
                cwd=app_root,
            )
            try:
                batch = build_request_batch(archive_root, queue_file)
            finally:
                _remove_worktree(app_root, archive_root)

            captures = batch.get("captures") if isinstance(batch, dict) else None
            if not isinstance(captures, list):
                raise PrematchDrainError("generated prematch batch has no captures array")
            if not captures:
                _clear_queue(queue_file)
                return {
                    "status": "QUEUE_ALREADY_FULFILLED",
                    "queued_requests": len(requests),
                    "captures": 0,
                }
            if not token:
                raise PrematchDrainError("GITHUB_TOKEN/GH_TOKEN is required to drain durable archive queue")

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

            _clear_queue(queue_file)
            output = (result.stdout or "").strip()
            return {
                "status": "QUEUE_DRAINED",
                "queued_requests": len(requests),
                "captures": len(captures),
                "recorder": output,
            }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Production SmartXFlow checkout")
    parser.add_argument("--queue-file", default=str(DEFAULT_QUEUE), help="Durable local request queue")
    parser.add_argument("--dotenv", help="Production dotenv consumed by the existing recorder")
    args = parser.parse_args()

    try:
        result = drain_queue(
            Path(args.root),
            Path(args.queue_file),
            dotenv=Path(args.dotenv) if args.dotenv else None,
        )
    except (OSError, ValueError, PrematchEnqueueError, PrematchDrainError, RuntimeError) as exc:
        print(f"PREMATCH_DRAIN_FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
