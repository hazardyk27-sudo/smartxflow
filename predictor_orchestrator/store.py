from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading
from typing import Any

from predictor_policy.runtime import PredictorRunState


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


@dataclass(frozen=True)
class WorkflowRecord:
    workflow_id: str
    status: str
    state: PredictorRunState
    scope: dict[str, Any]
    created_at: str
    updated_at: str


class SQLiteOrchestratorStore:
    """Durable single-service store. WAL + one writer lock makes stage commits atomic."""

    def __init__(self, path: str):
        self.path = path
        db_path = Path(path)
        if db_path.parent and str(db_path.parent) not in {"", "."}:
            db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS predictor_workflows (
                    workflow_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    scope_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS predictor_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    attempt_no INTEGER NOT NULL,
                    model TEXT NOT NULL,
                    raw_payload_json TEXT,
                    violations_json TEXT NOT NULL,
                    accepted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(workflow_id) REFERENCES predictor_workflows(workflow_id),
                    UNIQUE(workflow_id, stage, attempt_no)
                );
                CREATE TABLE IF NOT EXISTS predictor_stage_outputs (
                    workflow_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    stage_run_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    rendered_json TEXT NOT NULL,
                    model TEXT NOT NULL,
                    policy_version INTEGER NOT NULL,
                    accepted_at TEXT NOT NULL,
                    PRIMARY KEY(workflow_id, stage),
                    UNIQUE(stage_run_id),
                    FOREIGN KEY(workflow_id) REFERENCES predictor_workflows(workflow_id)
                );
                CREATE TABLE IF NOT EXISTS predictor_user_prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id TEXT NOT NULL,
                    market TEXT NOT NULL,
                    selection TEXT NOT NULL,
                    price REAL NOT NULL,
                    observed_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(workflow_id) REFERENCES predictor_workflows(workflow_id)
                );
                CREATE INDEX IF NOT EXISTS idx_predictor_prices_lookup
                    ON predictor_user_prices(workflow_id, market, selection, id DESC);
                """
            )

    @staticmethod
    def _next_attempt_no(conn: sqlite3.Connection, workflow_id: str, stage: str) -> int:
        row = conn.execute(
            "SELECT COALESCE(MAX(attempt_no), 0) AS max_attempt FROM predictor_attempts WHERE workflow_id=? AND stage=?",
            (workflow_id, stage),
        ).fetchone()
        return int(row["max_attempt"] or 0) + 1

    def create_workflow(self, workflow_id: str, scope: dict[str, Any]) -> WorkflowRecord:
        now = _utc_now()
        state = PredictorRunState()
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "INSERT INTO predictor_workflows(workflow_id,status,state_json,scope_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                    (workflow_id, "CREATED", _dumps(state.to_dict()), _dumps(scope), now, now),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return WorkflowRecord(workflow_id, "CREATED", state, scope, now, now)

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM predictor_workflows WHERE workflow_id=?",
                (workflow_id,),
            ).fetchone()
        if row is None:
            return None
        return WorkflowRecord(
            workflow_id=row["workflow_id"],
            status=row["status"],
            state=PredictorRunState.from_dict(_loads(row["state_json"], {})),
            scope=_loads(row["scope_json"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def save_attempt(
        self,
        *,
        workflow_id: str,
        stage: str,
        attempt_no: int,
        model: str,
        raw_payload: dict[str, Any] | None,
        violations: list[dict[str, str]],
        accepted: bool,
    ) -> int:
        """Append a failed audit attempt, or acknowledge an already-atomic accepted row."""
        del attempt_no
        if accepted:
            with self._lock, self._connect() as conn:
                row = conn.execute(
                    "SELECT attempt_no FROM predictor_attempts WHERE workflow_id=? AND stage=? AND accepted=1 ORDER BY attempt_no DESC LIMIT 1",
                    (workflow_id, stage),
                ).fetchone()
            if row is None:
                raise RuntimeError("accepted attempt must be persisted through accept_stage")
            return int(row["attempt_no"])
        return self.save_failed_attempt(
            workflow_id=workflow_id,
            stage=stage,
            model=model,
            raw_payload=raw_payload,
            violations=violations,
        )

    def save_failed_attempt(
        self,
        *,
        workflow_id: str,
        stage: str,
        model: str,
        raw_payload: dict[str, Any] | None,
        violations: list[dict[str, str]],
    ) -> int:
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                durable_attempt = self._next_attempt_no(conn, workflow_id, stage)
                conn.execute(
                    "INSERT INTO predictor_attempts(workflow_id,stage,attempt_no,model,raw_payload_json,violations_json,accepted,created_at) VALUES(?,?,?,?,?,?,0,?)",
                    (
                        workflow_id,
                        stage,
                        durable_attempt,
                        model,
                        _dumps(raw_payload) if raw_payload is not None else None,
                        _dumps(violations),
                        _utc_now(),
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return durable_attempt

    def accept_stage(
        self,
        *,
        workflow_id: str,
        stage: str,
        stage_run_id: str,
        payload: dict[str, Any],
        rendered: dict[str, Any],
        model: str,
        policy_version: int,
        new_state: PredictorRunState,
    ) -> int:
        """Atomically persist accepted payload, advanced state and accepted audit row."""
        now = _utc_now()
        status = f"{stage}_COMPLETE"
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                exists = conn.execute(
                    "SELECT 1 FROM predictor_stage_outputs WHERE workflow_id=? AND stage=?",
                    (workflow_id, stage),
                ).fetchone()
                if exists:
                    raise RuntimeError(f"{stage} already accepted for workflow {workflow_id}")
                durable_attempt = self._next_attempt_no(conn, workflow_id, stage)
                conn.execute(
                    "INSERT INTO predictor_stage_outputs(workflow_id,stage,stage_run_id,payload_json,rendered_json,model,policy_version,accepted_at) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        workflow_id,
                        stage,
                        stage_run_id,
                        _dumps(payload),
                        _dumps(rendered),
                        model,
                        policy_version,
                        now,
                    ),
                )
                conn.execute(
                    "INSERT INTO predictor_attempts(workflow_id,stage,attempt_no,model,raw_payload_json,violations_json,accepted,created_at) VALUES(?,?,?,?,?,?,1,?)",
                    (
                        workflow_id,
                        stage,
                        durable_attempt,
                        model,
                        _dumps(payload),
                        _dumps([]),
                        now,
                    ),
                )
                updated = conn.execute(
                    "UPDATE predictor_workflows SET status=?, state_json=?, updated_at=? WHERE workflow_id=?",
                    (status, _dumps(new_state.to_dict()), now, workflow_id),
                )
                if updated.rowcount != 1:
                    raise KeyError(workflow_id)
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return durable_attempt

    def get_stage_output(self, workflow_id: str, stage: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json, rendered_json, stage_run_id, model, policy_version, accepted_at FROM predictor_stage_outputs WHERE workflow_id=? AND stage=?",
                (workflow_id, stage),
            ).fetchone()
        if row is None:
            return None
        return {
            "stage_run_id": row["stage_run_id"],
            "payload": _loads(row["payload_json"], {}),
            "rendered": _loads(row["rendered_json"], {}),
            "model": row["model"],
            "policy_version": row["policy_version"],
            "accepted_at": row["accepted_at"],
        }

    def list_attempts(self, workflow_id: str, stage: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT attempt_no, model, violations_json, accepted, created_at FROM predictor_attempts WHERE workflow_id=? AND stage=? ORDER BY attempt_no",
                (workflow_id, stage),
            ).fetchall()
        return [
            {
                "attempt_no": row["attempt_no"],
                "model": row["model"],
                "violations": _loads(row["violations_json"], []),
                "accepted": bool(row["accepted"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def add_user_price(
        self,
        *,
        workflow_id: str,
        market: str,
        selection: str,
        price: float,
        observed_at: str,
        status: str,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO predictor_user_prices(workflow_id,market,selection,price,observed_at,status,created_at) VALUES(?,?,?,?,?,?,?)",
                (workflow_id, market, selection, price, observed_at, status, _utc_now()),
            )

    def find_user_price(self, workflow_id: str, market: str, selection: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT market,selection,price,observed_at,status FROM predictor_user_prices WHERE workflow_id=? AND market=? AND selection=? ORDER BY id DESC LIMIT 1",
                (workflow_id, market, selection),
            ).fetchone()
        if row is None:
            return None
        return {
            "origin": "USER_SUPPLIED",
            "source": "USER_SUPPLIED",
            "market": row["market"],
            "selection": row["selection"],
            "price": row["price"],
            "observed_at": row["observed_at"],
            "status": row["status"],
        }
