#!/usr/bin/env python3
"""Strict postmatch lifecycle: finalize cases, then durably publish postmatch diary.

The existing fast finalizer remains the canonical settlement/checksum engine. This
wrapper adds a durable local diary outbox so a diary/network failure cannot be
silently lost after a case reaches FINALIZED. A subsequent timer run retries only
pending diary case IDs from the canonical finalized archive packages.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

from learning_archive.outbox import load_dotenv_literal
from learning_archive.postmatch_diary import (
    PostmatchDiaryError,
    PostmatchDiaryWriter,
    load_finalized_diary_entry,
)
from scripts.enqueue_due_learning_revisit import export_archive_snapshot
from scripts.settle_due_learning_cases import (
    ARCHIVE_BRANCH,
    DEFAULT_OVERRIDE_DIR,
    DEFAULT_QUEUE,
    DEFAULT_ROOT,
    PostmatchSettlementError,
    _assert_production_checkout,
    _read_queue,
    _run,
    _write_queue,
    utc_now_iso,
)
from scripts.settle_due_learning_cases_fast import settle_due_cases_fast


def _pending_map(queue: dict[str, Any]) -> dict[str, dict[str, Any]]:
    value = queue.setdefault("postmatch_diaries", {})
    if not isinstance(value, dict):
        raise PostmatchSettlementError("postmatch queue postmatch_diaries must be an object")
    return value


def _enqueue_finalized(queue: dict[str, Any], result: dict[str, Any], observed_at: str) -> int:
    pending = _pending_map(queue)
    added = 0
    for item in result.get("cases") or []:
        if not isinstance(item, dict) or str(item.get("status") or "").upper() != "DONE":
            continue
        case_id = str(item.get("case_id") or "").strip()
        if not case_id:
            continue
        if case_id not in pending:
            pending[case_id] = {"case_id": case_id, "observed_at": observed_at}
            added += 1
    return added


def _drain_postmatch_diaries(
    app_root: Path,
    queue: dict[str, Any],
    *,
    now: str,
    writer: PostmatchDiaryWriter,
) -> dict[str, Any]:
    pending = _pending_map(queue)
    if not pending:
        return {"written": 0, "pending": 0, "references": {}, "errors": []}

    _run(["git", "fetch", "--quiet", "origin", ARCHIVE_BRANCH], cwd=app_root)
    errors: list[dict[str, str]] = []
    entries: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="sxf-postmatch-diary-snapshot-") as tmp:
        archive_root = Path(tmp) / "archive"
        export_archive_snapshot(app_root, archive_root)
        for case_id, request in sorted(pending.items()):
            try:
                observed_at = str((request or {}).get("observed_at") or now)
                entries.append(
                    load_finalized_diary_entry(
                        archive_root,
                        case_id,
                        observed_at=observed_at,
                    )
                )
            except Exception as exc:
                errors.append({"case_id": case_id, "error": str(exc)[:500]})

    write_result: dict[str, Any] = {"case_ids": [], "references": {}, "idempotent": True}
    if entries:
        try:
            write_result = writer.write_entries(entries, timezone_name="Europe/Istanbul")
        except Exception as exc:
            for entry in entries:
                errors.append({"case_id": str(entry.get("case_id") or ""), "error": f"diary write: {exc}"[:500]})
        else:
            for case_id in write_result.get("case_ids") or []:
                pending.pop(str(case_id), None)

    return {
        "written": len(write_result.get("case_ids") or []),
        "pending": len(pending),
        "references": write_result.get("references") or {},
        "idempotent": bool(write_result.get("idempotent", False)),
        "errors": errors,
    }


def settle_due_cases_with_diary(
    app_root: Path,
    queue_file: Path,
    *,
    now: str,
    minimum_minutes_after_kickoff: int = 75,
    override_file: str | None = None,
    override_dir: Path | None = DEFAULT_OVERRIDE_DIR,
    writer: PostmatchDiaryWriter | None = None,
) -> dict[str, Any]:
    _assert_production_checkout(app_root)
    base = settle_due_cases_fast(
        app_root,
        queue_file,
        now=now,
        minimum_minutes_after_kickoff=minimum_minutes_after_kickoff,
        override_file=override_file,
        override_dir=override_dir,
    )

    queue = _read_queue(queue_file)
    enqueued = _enqueue_finalized(queue, base, now)
    # Persist the outbox before attempting another network mutation. A crash or
    # GitHub outage after FINALIZED therefore remains retryable on the next timer.
    _write_queue(queue_file, queue)

    try:
        active_writer = writer or PostmatchDiaryWriter.from_env()
        diary = _drain_postmatch_diaries(
            app_root,
            queue,
            now=now,
            writer=active_writer,
        )
    except (OSError, ValueError, PostmatchDiaryError, RuntimeError) as exc:
        diary = {
            "written": 0,
            "pending": len(_pending_map(queue)),
            "references": {},
            "idempotent": False,
            "errors": [{"case_id": "*", "error": str(exc)[:500]}],
        }
    _write_queue(queue_file, queue)

    result = dict(base)
    result["postmatch_diary_enqueued"] = enqueued
    result["postmatch_diary_written"] = diary["written"]
    result["postmatch_diary_pending"] = diary["pending"]
    result["postmatch_diary_references"] = diary["references"]
    result["postmatch_diary_errors"] = diary["errors"]
    if diary["pending"] or diary["errors"]:
        result["status"] = "POSTMATCH_DIARY_PENDING" if not base.get("failed") else "POSTMATCH_PARTIAL"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--queue-file", default=str(DEFAULT_QUEUE))
    parser.add_argument("--now", help="Deterministic current timestamp; defaults to UTC now")
    parser.add_argument("--minimum-minutes-after-kickoff", type=int, default=75)
    parser.add_argument("--result-file", help="Optional verified result override JSON for historical backfill")
    parser.add_argument(
        "--result-dir",
        default=str(DEFAULT_OVERRIDE_DIR),
        help="Directory of auditable verified result override JSON files",
    )
    parser.add_argument("--dotenv", help="Production dotenv loaded literally")
    args = parser.parse_args()

    try:
        if args.dotenv:
            load_dotenv_literal(args.dotenv)
        result = settle_due_cases_with_diary(
            Path(args.root),
            Path(args.queue_file),
            now=args.now or utc_now_iso(),
            minimum_minutes_after_kickoff=args.minimum_minutes_after_kickoff,
            override_file=args.result_file,
            override_dir=Path(args.result_dir) if args.result_dir else None,
        )
    except Exception as exc:
        print(f"POSTMATCH_STRICT_FAIL: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "POSTMATCH_DONE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
