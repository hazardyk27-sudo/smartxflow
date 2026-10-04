#!/usr/bin/env python3
"""Persist due prematch capture requests durably.

Hetzner systemd is the primary clock. Every due case is written to both the
local queue and a service-role-only Supabase outbox with the exact observed_at.
The outbox is independent of GitHub Actions scheduling and protects source
history from cleanup until the event is mirrored to Learning Archive.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Iterator

from learning_archive.outbox import CaptureOutboxError, enqueue_capture_events, load_dotenv_literal
from scripts.build_due_learning_revisit_batch import build_due_batch


ARCHIVE_BRANCH = "learning-archive"
DEFAULT_ROOT = Path(os.environ.get("SMARTXFLOW_ROOT", "/opt/smartxflow"))
DEFAULT_QUEUE = Path(
    os.environ.get(
        "SMARTXFLOW_PREMATCH_QUEUE",
        "/var/lib/smartxflow-prematch/request.json",
    )
)


class PrematchEnqueueError(RuntimeError):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def merge_request_payload(
    existing: dict[str, Any] | None,
    observed_at: str,
    due_case_ids: list[str],
) -> tuple[dict[str, Any], list[str]]:
    payload = dict(existing or {})
    requests = payload.get("requests", [])
    if not isinstance(requests, list):
        raise PrematchEnqueueError("request queue requests must be an array")

    queued_case_ids: set[str] = set()
    normalized_requests: list[dict[str, Any]] = []
    for index, item in enumerate(requests):
        if not isinstance(item, dict):
            raise PrematchEnqueueError(f"request queue item {index} must be an object")
        queued = item.get("case_ids")
        if not isinstance(queued, list):
            raise PrematchEnqueueError(f"request queue item {index}.case_ids must be an array")
        clean_ids = [str(value or "").strip() for value in queued]
        if any(not value for value in clean_ids):
            raise PrematchEnqueueError(f"request queue item {index}.case_ids contains an empty value")
        queued_case_ids.update(clean_ids)
        normalized_requests.append(dict(item))

    clean_due = sorted({str(value or "").strip() for value in due_case_ids if str(value or "").strip()})
    added = [case_id for case_id in clean_due if case_id not in queued_case_ids]
    if added:
        normalized_requests.append({"observed_at": observed_at, "case_ids": added})

    payload["request_id"] = "hetzner-prematch-queue"
    payload["requests"] = normalized_requests
    return payload, added


def _run(argv: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        argv,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "command failed").strip()
        raise PrematchEnqueueError(f"{' '.join(argv[:3])}: {detail}")
    return result


def _assert_production_checkout(app_root: Path) -> None:
    branch = _run(["git", "branch", "--show-current"], cwd=app_root).stdout.strip()
    if branch != "main":
        raise PrematchEnqueueError(f"production branch is {branch!r}, expected 'main'")
    if _run(["git", "diff", "--quiet"], cwd=app_root, check=False).returncode != 0:
        raise PrematchEnqueueError("production tracked worktree is dirty")
    if _run(["git", "diff", "--cached", "--quiet"], cwd=app_root, check=False).returncode != 0:
        raise PrematchEnqueueError("production index is dirty")


def export_archive_snapshot(app_root: Path, destination: Path) -> None:
    """Export learning-archive read-only without creating a git worktree."""
    destination.mkdir(parents=True, exist_ok=True)
    tar_path = destination.parent / "learning-archive.tar"
    _run(
        [
            "git",
            "archive",
            "--format=tar",
            f"--output={tar_path}",
            f"origin/{ARCHIVE_BRANCH}",
            "learning_archive_data",
        ],
        cwd=app_root,
    )
    try:
        _run(["tar", "-xf", str(tar_path), "-C", str(destination)], cwd=app_root)
    finally:
        tar_path.unlink(missing_ok=True)


@contextmanager
def _queue_lock(queue_file: Path) -> Iterator[None]:
    queue_file.parent.mkdir(parents=True, exist_ok=True)
    lock_path = queue_file.with_suffix(queue_file.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _read_queue(queue_file: Path) -> dict[str, Any]:
    if not queue_file.exists():
        return {"request_id": "hetzner-prematch-queue", "requests": []}
    try:
        value = json.loads(queue_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PrematchEnqueueError("local prematch queue JSON is invalid") from exc
    if not isinstance(value, dict):
        raise PrematchEnqueueError("local prematch queue must be a JSON object")
    return value


def _write_queue_atomic(queue_file: Path, payload: dict[str, Any]) -> None:
    queue_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = queue_file.with_name(queue_file.name + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, queue_file)


def enqueue_due(
    app_root: Path,
    queue_file: Path,
    observed_at: str,
    *,
    max_minutes_before_kickoff: int = 35,
) -> dict[str, Any]:
    _assert_production_checkout(app_root)
    _run(["git", "fetch", "origin", ARCHIVE_BRANCH], cwd=app_root)

    with tempfile.TemporaryDirectory(prefix="sxf-prematch-enqueue-") as tmp:
        archive_root = Path(tmp) / "archive"
        export_archive_snapshot(app_root, archive_root)
        due = build_due_batch(
            archive_root,
            observed_at,
            max_minutes_before_kickoff=max_minutes_before_kickoff,
        )

    captures = due.get("captures") if isinstance(due, dict) else None
    if not isinstance(captures, list):
        raise PrematchEnqueueError("due capture batch is invalid")
    due_case_ids = [
        str(item.get("case", {}).get("case_id") or "").strip()
        for item in captures
    ]
    due_case_ids = [case_id for case_id in due_case_ids if case_id]
    if not due_case_ids:
        return {
            "status": "NO_DUE",
            "observed_at": observed_at,
            "due": 0,
            "queued": 0,
            "outbox_events": 0,
        }

    # External durable receipt is mandatory. If this fails, the timer fails
    # closed and retries on the next run rather than pretending capture is safe.
    outbox_ids = enqueue_capture_events(captures, observed_at)

    with _queue_lock(queue_file):
        existing = _read_queue(queue_file)
        merged, added = merge_request_payload(existing, observed_at, due_case_ids)
        if added:
            _write_queue_atomic(queue_file, merged)
        return {
            "status": "QUEUED_DURABLE" if added else "ALREADY_QUEUED",
            "observed_at": observed_at,
            "due": len(due_case_ids),
            "queued": len(added),
            "outbox_events": len(outbox_ids),
            "case_ids": added,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Production SmartXFlow checkout")
    parser.add_argument("--queue-file", default=str(DEFAULT_QUEUE), help="Durable local request queue")
    parser.add_argument("--observed-at", help="Optional deterministic UTC/offset timestamp")
    parser.add_argument("--max-minutes-before-kickoff", type=int, default=35)
    parser.add_argument("--dotenv", help="Production dotenv loaded literally before durable outbox access")
    args = parser.parse_args()

    observed_at = args.observed_at or utc_now_iso()
    try:
        if args.dotenv:
            load_dotenv_literal(args.dotenv)
        result = enqueue_due(
            Path(args.root),
            Path(args.queue_file),
            observed_at,
            max_minutes_before_kickoff=args.max_minutes_before_kickoff,
        )
    except (OSError, ValueError, PrematchEnqueueError, CaptureOutboxError) as exc:
        print(f"PREMATCH_ENQUEUE_FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
