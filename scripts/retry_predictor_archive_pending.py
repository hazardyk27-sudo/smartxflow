#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

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


def _pending_stage_runs(db_path: str) -> list[tuple[str, str]]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT workflow_id, stage_run_id
            FROM predictor_archive_lifecycle
            WHERE archive_status != 'RECORDED'
               OR COALESCE(diary_status, '') != 'RECORDED'
            ORDER BY workflow_id, stage_run_id
            """
        ).fetchall()
    return [(str(row[0]), str(row[1])) for row in rows]


def retry_pending() -> dict[str, Any]:
    cfg = OrchestratorConfig.from_env(require_secrets=False, require_api_key=False)
    store = SQLiteOrchestratorStore(cfg.state_db_path)
    orch = StrictPredictorOrchestrator(config=cfg, store=store, llm=_NoLLM())

    pending = _pending_stage_runs(cfg.state_db_path)
    if not pending:
        return {"ok": True, "retried_stage_runs": 0, "remaining_pending": 0, "results": []}

    if orch.archive_publisher is None:
        return {
            "ok": False,
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
            results.append(
                {
                    "workflow_id": workflow_id,
                    "stage_run_id": stage_run_id,
                    "status": summary.get("status"),
                    "formal_cases": summary.get("formal_cases"),
                    "diary_status": summary.get("diary_status"),
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

    remaining = _pending_stage_runs(cfg.state_db_path)
    return {
        "ok": not remaining,
        "retried_stage_runs": len(pending),
        "remaining_pending": len(remaining),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Retry durable Predictor archive/diary lifecycle work")
    parser.add_argument("--dotenv", default=None)
    args = parser.parse_args()

    try:
        _load_dotenv(args.dotenv)
        result = retry_pending()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)[:500]}, ensure_ascii=False, sort_keys=True))
        return 1

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
