#!/usr/bin/env python3
"""Enqueue due prematch Learning Archive captures from the production host.

This is the primary scheduler path. It does not write archive truth directly;
it snapshots the intended observed_at/case_ids into the dedicated request branch.
The GitHub capture workflow consumes that queue with normal repository credentials.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from scripts.build_due_learning_revisit_batch import build_due_batch


ARCHIVE_BRANCH = "learning-archive"
REQUEST_BRANCH = "learning-archive-capture-requests"
REQUEST_RELATIVE_PATH = Path("learning_archive_capture_requests/request.json")
DEFAULT_ROOT = Path(os.environ.get("SMARTXFLOW_ROOT", "/opt/smartxflow"))


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

    payload["request_id"] = "prematch-capture-queue"
    payload["requests"] = normalized_requests
    return payload, added


def _run(
    argv: list[str],
    *,
    cwd: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
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


def _remove_worktree(app_root: Path, worktree: Path) -> None:
    if not worktree.exists():
        return
    result = _run(["git", "worktree", "remove", str(worktree)], cwd=app_root, check=False)
    if result.returncode != 0:
        raise PrematchEnqueueError(
            f"failed to remove temporary worktree {worktree}: {(result.stderr or result.stdout).strip()}"
        )


def _assert_production_checkout(app_root: Path) -> None:
    branch = _run(["git", "branch", "--show-current"], cwd=app_root).stdout.strip()
    if branch != "main":
        raise PrematchEnqueueError(f"production branch is {branch!r}, expected 'main'")
    if _run(["git", "diff", "--quiet"], cwd=app_root, check=False).returncode != 0:
        raise PrematchEnqueueError("production tracked worktree is dirty")
    if _run(["git", "diff", "--cached", "--quiet"], cwd=app_root, check=False).returncode != 0:
        raise PrematchEnqueueError("production index is dirty")


def _read_request_payload(request_root: Path) -> dict[str, Any]:
    target = request_root / REQUEST_RELATIVE_PATH
    if not target.exists():
        return {"request_id": "prematch-capture-queue", "requests": []}
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PrematchEnqueueError("request queue JSON is invalid") from exc
    if not isinstance(value, dict):
        raise PrematchEnqueueError("request queue must be a JSON object")
    return value


def enqueue_due(
    app_root: Path,
    observed_at: str,
    *,
    max_minutes_before_kickoff: int = 35,
) -> dict[str, Any]:
    _assert_production_checkout(app_root)
    _run(["git", "fetch", "origin", "main", ARCHIVE_BRANCH, REQUEST_BRANCH], cwd=app_root)

    with tempfile.TemporaryDirectory(prefix="sxf-prematch-enqueue-") as tmp:
        temp_root = Path(tmp)
        archive_root = temp_root / "archive"
        _run(["git", "worktree", "add", "--detach", str(archive_root), f"origin/{ARCHIVE_BRANCH}"], cwd=app_root)
        try:
            due = build_due_batch(
                archive_root,
                observed_at,
                max_minutes_before_kickoff=max_minutes_before_kickoff,
            )
        finally:
            _remove_worktree(app_root, archive_root)

        due_case_ids = [
            str(item.get("case", {}).get("case_id") or "").strip()
            for item in (due.get("captures") or [])
        ]
        due_case_ids = [case_id for case_id in due_case_ids if case_id]
        if not due_case_ids:
            return {"status": "NO_DUE", "observed_at": observed_at, "due": 0, "queued": 0}

        last_error = ""
        for attempt in range(1, 4):
            _run(["git", "fetch", "origin", REQUEST_BRANCH], cwd=app_root)
            request_root = temp_root / f"request-{attempt}"
            _run(["git", "worktree", "add", "--detach", str(request_root), f"origin/{REQUEST_BRANCH}"], cwd=app_root)
            try:
                existing = _read_request_payload(request_root)
                merged, added = merge_request_payload(existing, observed_at, due_case_ids)
                if not added:
                    return {
                        "status": "ALREADY_QUEUED",
                        "observed_at": observed_at,
                        "due": len(due_case_ids),
                        "queued": 0,
                    }

                target = request_root / REQUEST_RELATIVE_PATH
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                _run(["git", "config", "user.name", "smartxflow-prematch-timer"], cwd=request_root)
                _run(["git", "config", "user.email", "smartxflow-prematch-timer@localhost"], cwd=request_root)
                _run(["git", "add", REQUEST_RELATIVE_PATH.as_posix()], cwd=request_root)
                _run(["git", "commit", "-m", f"Queue prematch capture {observed_at}"], cwd=request_root)
                pushed = _run(
                    ["git", "push", "origin", f"HEAD:refs/heads/{REQUEST_BRANCH}"],
                    cwd=request_root,
                    check=False,
                )
                if pushed.returncode == 0:
                    return {
                        "status": "QUEUED",
                        "observed_at": observed_at,
                        "due": len(due_case_ids),
                        "queued": len(added),
                        "case_ids": added,
                    }
                last_error = (pushed.stderr or pushed.stdout or "push failed").strip()
            finally:
                _remove_worktree(app_root, request_root)

        raise PrematchEnqueueError(f"request queue push failed after retries: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Production SmartXFlow checkout")
    parser.add_argument("--observed-at", help="Optional deterministic UTC/offset timestamp")
    parser.add_argument("--max-minutes-before-kickoff", type=int, default=35)
    args = parser.parse_args()

    observed_at = args.observed_at or utc_now_iso()
    try:
        result = enqueue_due(
            Path(args.root),
            observed_at,
            max_minutes_before_kickoff=args.max_minutes_before_kickoff,
        )
    except (OSError, ValueError, PrematchEnqueueError) as exc:
        print(f"PREMATCH_ENQUEUE_FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
