#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
import sys
from typing import Any

from predictor_orchestrator.config import OrchestratorConfig
from predictor_orchestrator.strict_service import StrictPredictorOrchestrator
from predictor_orchestrator.store import SQLiteOrchestratorStore


class _NoLLM:
    def generate(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("LLM must not be called during archive lifecycle retry")


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
    try:
        result = retry_pending()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)[:500]}, ensure_ascii=False, sort_keys=True))
        return 1

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
