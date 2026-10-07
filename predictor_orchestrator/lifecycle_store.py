from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import sqlite3
import threading
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class PredictorLifecycleStore:
    """Sidecar lifecycle state stored in the same Predictor SQLite database.

    Stage acceptance remains owned by SQLiteOrchestratorStore. This table tracks
    post-accept archive/diary work separately so archive failure can never rewrite
    or erase the immutable accepted Stage 3 decision.
    """

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._lock, self._connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS predictor_archive_lifecycle (
                    workflow_id TEXT NOT NULL,
                    stage_run_id TEXT NOT NULL,
                    fixture_id TEXT NOT NULL,
                    case_id TEXT,
                    archive_status TEXT NOT NULL,
                    archive_reference TEXT,
                    archive_commit TEXT,
                    checksum_summary TEXT,
                    diary_status TEXT,
                    diary_reference TEXT,
                    error TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(workflow_id, stage_run_id, fixture_id)
                );
                CREATE INDEX IF NOT EXISTS idx_predictor_archive_lifecycle_workflow
                    ON predictor_archive_lifecycle(workflow_id, stage_run_id);
                """
            )

    def upsert(
        self,
        *,
        workflow_id: str,
        stage_run_id: str,
        fixture_id: str,
        case_id: str | None,
        archive_status: str,
        archive_reference: str | None = None,
        archive_commit: str | None = None,
        checksum_summary: str | None = None,
        diary_status: str | None = None,
        diary_reference: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock, self._connection() as conn:
            conn.execute(
                """
                INSERT INTO predictor_archive_lifecycle(
                    workflow_id,stage_run_id,fixture_id,case_id,archive_status,
                    archive_reference,archive_commit,checksum_summary,diary_status,
                    diary_reference,error,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(workflow_id,stage_run_id,fixture_id) DO UPDATE SET
                    case_id=excluded.case_id,
                    archive_status=excluded.archive_status,
                    archive_reference=excluded.archive_reference,
                    archive_commit=excluded.archive_commit,
                    checksum_summary=excluded.checksum_summary,
                    diary_status=excluded.diary_status,
                    diary_reference=excluded.diary_reference,
                    error=excluded.error,
                    updated_at=excluded.updated_at
                """,
                (
                    workflow_id,
                    stage_run_id,
                    fixture_id,
                    case_id,
                    archive_status,
                    archive_reference,
                    archive_commit,
                    checksum_summary,
                    diary_status,
                    diary_reference,
                    error,
                    _now(),
                ),
            )

    def list_for_stage(self, workflow_id: str, stage_run_id: str) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT workflow_id,stage_run_id,fixture_id,case_id,archive_status,
                       archive_reference,archive_commit,checksum_summary,diary_status,
                       diary_reference,error,updated_at
                FROM predictor_archive_lifecycle
                WHERE workflow_id=? AND stage_run_id=?
                ORDER BY fixture_id
                """,
                (workflow_id, stage_run_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def summary(self, workflow_id: str, stage_run_id: str) -> dict[str, Any]:
        rows = self.list_for_stage(workflow_id, stage_run_id)
        if not rows:
            return {
                "status": "NOT_APPLICABLE",
                "formal_cases": 0,
                "cases": [],
                "diary_status": "NOT_REQUIRED",
            }
        archive_complete = all(row["archive_status"] == "RECORDED" for row in rows)
        diary_values = {str(row.get("diary_status") or "") for row in rows}
        diary_status = "RECORDED" if diary_values == {"RECORDED"} else "DIARY_PENDING"
        return {
            "status": "RECORDED" if archive_complete and diary_status == "RECORDED" else "ARCHIVE_PENDING",
            "formal_cases": len(rows),
            "cases": rows,
            "diary_status": diary_status,
        }
