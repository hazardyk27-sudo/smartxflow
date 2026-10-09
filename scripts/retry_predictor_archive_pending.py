#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from predictor_orchestrator.config import OrchestratorConfig
from predictor_orchestrator.strict_service import StrictPredictorOrchestrator
from predictor_orchestrator.store import SQLiteOrchestratorStore


class _NoLLM:
    def generate(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("LLM must not be called during archive lifecycle retry")


def _load_dotenv(path: str | None) -> None:
    if not path:
        return
    dotenv = Path(path)
    if not dotenv.is_file():
        raise RuntimeError(f"dotenv file is missing: {dotenv}")
    for raw in dotenv.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key.startswith("export "):
            key = key[7:].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def _table_exists(db_path: str, table: str) -> bool:
    with sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True) as conn:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone()
    return row is not None


def _workflow_ids(db_path: str) -> set[str]:
    if not _table_exists(db_path, "predictor_workflows"):
        return set()
    with sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True) as conn:
        rows = conn.execute("SELECT workflow_id FROM predictor_workflows").fetchall()
    return {str(row[0]) for row in rows}


def _pending_stage_runs(db_path: str, workflow_filter: set[str] | None = None) -> list[tuple[str, str]]:
    sql = """
        SELECT DISTINCT workflow_id, stage_run_id
        FROM predictor_archive_lifecycle
        WHERE (archive_status != 'RECORDED'
           OR COALESCE(diary_status, '') != 'RECORDED')
    """
    params: list[str] = []
    if workflow_filter:
        placeholders = ",".join("?" for _ in sorted(workflow_filter))
        sql += f" AND workflow_id IN ({placeholders})"
        params.extend(sorted(workflow_filter))
    sql += " ORDER BY workflow_id, stage_run_id"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [(str(row[0]), str(row[1])) for row in rows]


def _candidate_db_paths(explicit: Iterable[str], scan_roots: Iterable[str]) -> list[str]:
    found: list[Path] = []
    for raw in explicit:
        value = str(raw or "").strip()
        if value:
            path = Path(value).expanduser().resolve()
            if path.is_file():
                found.append(path)
    for raw in scan_roots:
        value = str(raw or "").strip()
        if not value:
            continue
        root = Path(value).expanduser().resolve()
        if not root.is_dir():
            continue
        for path in root.rglob("*.sqlite3"):
            if path.is_file():
                found.append(path.resolve())
    unique: list[str] = []
    seen: set[str] = set()
    for path in found:
        value = str(path)
        if value not in seen:
            unique.append(value)
            seen.add(value)
    return unique


def retry_pending(
    db_path: str | None = None,
    workflow_filter: set[str] | None = None,
) -> dict[str, Any]:
    if db_path:
        os.environ["PREDICTOR_STATE_DB"] = str(Path(db_path).resolve())
    cfg = OrchestratorConfig.from_env(require_secrets=False, require_api_key=False)
    resolved_db = str(Path(cfg.state_db_path).resolve())
    if not Path(resolved_db).is_file():
        return {
            "ok": True,
            "db_path": resolved_db,
            "status": "MISSING",
            "matched_workflows": [],
            "retried_stage_runs": 0,
            "remaining_pending": 0,
            "results": [],
        }
    if not _table_exists(resolved_db, "predictor_archive_lifecycle"):
        return {
            "ok": True,
            "db_path": resolved_db,
            "status": "NO_LIFECYCLE_TABLE",
            "matched_workflows": [],
            "retried_stage_runs": 0,
            "remaining_pending": 0,
            "results": [],
        }

    present_workflows = _workflow_ids(resolved_db)
    matched_workflows = sorted(present_workflows & workflow_filter) if workflow_filter else sorted(present_workflows)
    if workflow_filter and not matched_workflows:
        return {
            "ok": True,
            "db_path": resolved_db,
            "status": "TARGET_NOT_FOUND",
            "matched_workflows": [],
            "retried_stage_runs": 0,
            "remaining_pending": 0,
            "results": [],
        }

    store = SQLiteOrchestratorStore(resolved_db)
    orch = StrictPredictorOrchestrator(config=cfg, store=store, llm=_NoLLM())

    pending = _pending_stage_runs(resolved_db, workflow_filter)
    if not pending:
        return {
            "ok": True,
            "db_path": resolved_db,
            "status": "CLEAR",
            "matched_workflows": matched_workflows,
            "retried_stage_runs": 0,
            "remaining_pending": 0,
            "results": [],
        }

    if orch.archive_publisher is None:
        return {
            "ok": False,
            "db_path": resolved_db,
            "status": "PUBLISHER_UNAVAILABLE",
            "matched_workflows": matched_workflows,
            "error": "Learning Archive publisher is not configured",
            "retried_stage_runs": 0,
            "remaining_pending": len(pending),
            "results": [],
        }

    results: list[dict[str, Any]] = []
    for workflow_id, stage_run_id in pending:
        accepted = store.get_stage_output(workflow_id, "STAGE3")
        if accepted is None:
            results.append(
                {
                    "workflow_id": workflow_id,
                    "stage_run_id": stage_run_id,
                    "status": "ERROR",
                    "error": "accepted STAGE3 is missing",
                }
            )
            continue
        if str(accepted.get("stage_run_id") or "") != stage_run_id:
            results.append(
                {
                    "workflow_id": workflow_id,
                    "stage_run_id": stage_run_id,
                    "status": "ERROR",
                    "error": "accepted STAGE3 run id mismatch",
                }
            )
            continue

        try:
            summary = orch._archive_stage3(
                workflow_id=workflow_id,
                stage_run_id=stage_run_id,
                stage3_payload=accepted["payload"],
            )
            lifecycle_rows = orch.lifecycle_store.list_for_stage(workflow_id, stage_run_id)
            archive_commits = sorted(
                {
                    str(row.get("archive_commit") or "").strip()
                    for row in lifecycle_rows
                    if str(row.get("archive_commit") or "").strip()
                }
            )
            diary_references = sorted(
                {
                    str(row.get("diary_reference") or "").strip()
                    for row in lifecycle_rows
                    if str(row.get("diary_reference") or "").strip()
                }
            )
            results.append(
                {
                    "workflow_id": workflow_id,
                    "stage_run_id": stage_run_id,
                    "status": summary.get("status"),
                    "formal_cases": summary.get("formal_cases"),
                    "diary_status": summary.get("diary_status"),
                    "archive_commits": archive_commits,
                    "diary_references": diary_references,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "workflow_id": workflow_id,
                    "stage_run_id": stage_run_id,
                    "status": "ERROR",
                    "error": str(exc)[:500],
                }
            )

    remaining = _pending_stage_runs(resolved_db, workflow_filter)
    return {
        "ok": not remaining,
        "db_path": resolved_db,
        "status": "CLEAR" if not remaining else "PENDING",
        "matched_workflows": matched_workflows,
        "retried_stage_runs": len(pending),
        "remaining_pending": len(remaining),
        "results": results,
    }


def retry_many(
    db_paths: list[str],
    workflow_filter: set[str] | None = None,
    *,
    require_workflow: bool = False,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    total_retried = 0
    total_remaining = 0
    all_ok = True
    matched: set[str] = set()
    for db_path in db_paths:
        try:
            result = retry_pending(db_path, workflow_filter)
        except Exception as exc:
            result = {
                "ok": False,
                "db_path": str(Path(db_path).resolve()),
                "status": "ERROR",
                "matched_workflows": [],
                "error": str(exc)[:500],
                "retried_stage_runs": 0,
                "remaining_pending": 1,
                "results": [],
            }
        results.append(result)
        matched.update(str(item) for item in result.get("matched_workflows") or [])
        total_retried += int(result.get("retried_stage_runs") or 0)
        total_remaining += int(result.get("remaining_pending") or 0)
        all_ok = all_ok and result.get("ok") is True
    missing_required = bool(require_workflow and workflow_filter and not (matched & workflow_filter))
    return {
        "ok": all_ok and total_remaining == 0 and not missing_required,
        "error": "required Predictor workflow was not found in scanned databases" if missing_required else None,
        "scanned_databases": len(results),
        "matched_workflows": sorted(matched),
        "retried_stage_runs": total_retried,
        "remaining_pending": total_remaining,
        "databases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Retry durable Predictor archive/diary lifecycle work")
    parser.add_argument("--dotenv", default=None)
    parser.add_argument("--db", action="append", default=[], help="Existing Predictor SQLite DB to inspect/retry")
    parser.add_argument("--scan-root", action="append", default=[], help="Directory tree to scan for SQLite DBs")
    parser.add_argument("--workflow-id", action="append", default=[], help="Only retry these exact Predictor workflow IDs")
    parser.add_argument("--require-workflow", action="store_true", help="Fail when none of the requested workflow IDs are found")
    args = parser.parse_args()

    try:
        _load_dotenv(args.dotenv)
        explicit = list(args.db)
        if not explicit and not args.scan_root:
            explicit = [
                os.environ.get("PREDICTOR_STATE_DB", "").strip()
                or str(Path("data") / "predictor_orchestrator.sqlite3")
            ]
        candidates = _candidate_db_paths(explicit, args.scan_root)
        workflow_filter = {str(item).strip() for item in args.workflow_id if str(item).strip()} or None
        if not candidates:
            result = {
                "ok": False,
                "error": "no existing Predictor SQLite database found",
                "scanned_databases": 0,
                "matched_workflows": [],
                "retried_stage_runs": 0,
                "remaining_pending": 0,
                "databases": [],
            }
        else:
            result = retry_many(
                candidates,
                workflow_filter,
                require_workflow=args.require_workflow,
            )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)[:500]}, ensure_ascii=False, sort_keys=True))
        return 1

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
