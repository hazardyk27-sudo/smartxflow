"""Phase 4 Supabase durable Base checkpoint RPC client, opt-in / non-deployed.

All writes are isolated to the new sxf_base_* RPCs; no mutation of legacy SXF
signals, fixtures, source snapshots, Predictor, or archive. Functions run with
service_role only after a separately approved migration. Every write and lease
transition is atomic on the database side; retries never fabricate success.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence
from uuid import UUID

import requests

from .reader import _parse_time
from .scheduler import CHECKPOINT_TASKS, RULESET_VERSION, CheckpointJob, FixtureRef


class DurableStoreError(RuntimeError):
    """RPC failure; safe for operators to log the class, never credentials."""


@dataclass(frozen=True)
class ClaimedCheckpoint:
    job_id: str
    lease_token: str
    job: CheckpointJob
    attempt_count: int


class SupabaseCheckpointStore:
    """RPC-only atomic queue/client. Caller controls discovery and scanning."""

    _ALLOWED = frozenset({
        "sxf_base_enqueue_jobs", "sxf_base_claim_due_jobs",
        "sxf_base_renew_lease", "sxf_base_fail_job", "sxf_base_complete_job",
        "sxf_base_wait_for_data", "sxf_base_append_reconciliation",
    })

    def __init__(self, base_url: str, service_key: str, *, session: Any = None,
                 request_timeout_seconds: float = 20):
        if not base_url.startswith("https://") or not service_key:
            raise ValueError("HTTPS Supabase URL and server-only credentials required")
        if request_timeout_seconds <= 0:
            raise ValueError("invalid HTTP timeout")
        self._base = base_url.rstrip("/") + "/rest/v1/rpc/"
        self._headers = {"apikey": service_key, "Authorization": "Bearer " + service_key,
                         "Content-Type": "application/json"}
        self._session = session if session is not None else requests.Session()
        self._timeout = request_timeout_seconds

    def _rpc(self, name: str, args: Mapping[str, Any]) -> Any:
        if name not in self._ALLOWED:
            raise ValueError("unsupported checkpoint storage RPC")
        try:
            response = self._session.post(
                self._base + name, json=dict(args), headers=self._headers, timeout=self._timeout,
            )
            if response.status_code not in (200, 201):
                raise DurableStoreError(f"{name} failed: HTTP {response.status_code}")
            return response.json()
        except DurableStoreError:
            raise
        except Exception as error:
            # Do not include URLs, exception messages or response bodies: auth secrets
            # may appear in transport exceptions or provider debug payloads.
            raise DurableStoreError(f"{name} unavailable ({type(error).__name__})") from error

    def enqueue(self, fixtures: Sequence[FixtureRef], *, batch_size: int = 200) -> int:
        """Idempotent full-checkpoint enumeration. Never narrow to only due jobs.

        Resumption after an outage depends on fixture discovery/upsert running
        before the checkpoint and queue records not being removed by retention.
        """
        if not 1 <= batch_size <= 1000:
            raise ValueError("invalid enqueue batch size")
        payloads = []
        seen = set()
        for fixture in fixtures:
            for hours, family in CHECKPOINT_TASKS:
                job = CheckpointJob(fixture, hours, family)
                if job.key in seen:
                    continue
                seen.add(job.key)
                payloads.append({
                    "job_key": job.key,
                    "ruleset_version": RULESET_VERSION,
                    "fixture_uid": fixture.fixture_uid,
                    "kickoff_utc": fixture.kickoff_utc.isoformat(),
                    "checkpoint_hours": hours,
                    "family": family,
                })
        added = 0
        for i in range(0, len(payloads), batch_size):
            value = self._rpc("sxf_base_enqueue_jobs", {"p_jobs": payloads[i:i + batch_size]})
            if type(value) is not int or value < 0 or value > len(payloads[i:i + batch_size]):
                raise DurableStoreError("enqueue RPC returned invalid count")
            added += value
        return added

    def claim(self, worker_id: str, *, limit: int = 25,
              lease_seconds: int = 300) -> list[ClaimedCheckpoint]:
        if not worker_id or len(worker_id) > 100 or not 1 <= limit <= 100 or not 60 <= lease_seconds <= 1800:
            raise ValueError("invalid claim settings")
        rows = self._rpc("sxf_base_claim_due_jobs", {
            "p_worker": worker_id, "p_limit": limit, "p_lease_seconds": lease_seconds,
        })
        if not isinstance(rows, list) or len(rows) > limit:
            raise DurableStoreError("unexpected claim payload")
        claimed = []
        for r in rows:
            try:
                if not isinstance(r, dict) or r["ruleset_version"] != RULESET_VERSION:
                    raise ValueError("wrong ruleset")
                fixture = FixtureRef(str(UUID(str(r["fixture_uid"]))), _parse_time(r["kickoff_utc"]))
                job = CheckpointJob(fixture, int(r["checkpoint_hours"]), str(r["family"]))
                if (job.hours, job.family) not in CHECKPOINT_TASKS or job.key != r["job_key"]:
                    raise ValueError("checkpoint key / identity mismatch")
                if _parse_time(r["checkpoint_at"]) != job.timestamp:
                    raise ValueError("checkpoint time mismatch")
                claimed.append(ClaimedCheckpoint(
                    str(UUID(str(r["job_id"]))), str(UUID(str(r["lease_token"]))),
                    job, int(r["attempt_count"])))
            except (ValueError, KeyError, TypeError) as error:
                raise DurableStoreError("invalid or mismatched claimed checkpoint") from error
        return claimed

    def renew(self, item: ClaimedCheckpoint, *, lease_seconds: int = 300) -> None:
        if self._rpc("sxf_base_renew_lease", {
            "p_job_id": item.job_id, "p_lease_token": item.lease_token,
            "p_lease_seconds": lease_seconds,
        }) is not True:
            raise DurableStoreError("checkpoint lease renewal rejected")

    def complete(self, item: ClaimedCheckpoint, payload: dict) -> None:
        if payload.get("key") != item.job.key:
            raise ValueError("payload does not belong to claimed checkpoint")
        if self._rpc("sxf_base_complete_job", {
            "p_job_id": item.job_id,
            "p_lease_token": item.lease_token,
            "p_payload": payload,
        }) is not True:
            raise DurableStoreError("checkpoint completion not acknowledged")

    def fail(self, item: ClaimedCheckpoint, error_code: str, *, delay_seconds: int = 60) -> None:
        if not error_code or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_' for c in error_code):
            raise ValueError("safe uppercase error class only")
        if not 10 <= delay_seconds <= 3600:
            raise ValueError("retry delay outside bounds")
        if self._rpc("sxf_base_fail_job", {
            "p_job_id": item.job_id,
            "p_lease_token": item.lease_token,
            "p_error_code": error_code[:64],
            "p_retry_seconds": delay_seconds,
        }) is not True:
            raise DurableStoreError("checkpoint failure update not acknowledged")
    def wait_for_data(self, item: ClaimedCheckpoint, *,
                      reason: str = "INSUFFICIENT_DATA",
                      delay_seconds: int = 180) -> None:
        """Mark a missing-source attempt nonterminal with a fenced lease token."""
        if reason not in ("INSUFFICIENT_DATA", "SOURCE_LAG", "SOURCE_INCOMPLETE"):
            raise ValueError("unsupported missing-source reason")
        if not 60 <= delay_seconds <= 3600:
            raise ValueError("missing-source retry delay outside bounds")
        if self._rpc("sxf_base_wait_for_data", {
            "p_job_id": item.job_id, "p_lease_token": item.lease_token,
            "p_reason": reason, "p_retry_seconds": delay_seconds,
        }) is not True:
            raise DurableStoreError("missing-source transition not acknowledged")

    def append_reconciliation(
        self, *, origin_event_key: str, kind: str,
        source_snapshot_ids: Sequence[int], details: Mapping[str, Any],
        engine: str | None = None, selection: str | None = None,
    ) -> bool:
        """Append one validated late-T6 event; False means identical replay.

        The DB re-reads every supplied source snapshot ID by PK, checks UID,
        market, complete side set, timestamp window and frozen source checkpoint.
        This adapter never accepts hash-only identity or live-money guesses.
        """
        if not origin_event_key or len(origin_event_key) > 450:
            raise ValueError("invalid source event key")
        if kind not in ("CONFIRMED", "INVALIDATED", "CORRECTED"):
            raise ValueError("invalid reconciliation type")
        if not isinstance(details, Mapping):
            raise ValueError("reconciliation evidence must be a mapping")
        if (engine is None) != (selection is None):
            raise ValueError("engine and selection must be supplied together")
        if kind != "CORRECTED" and engine is not None:
            raise ValueError("confirmation/invalidation inherits source identity")
        if not isinstance(source_snapshot_ids, (list, tuple)) or not (
            2 <= len(source_snapshot_ids) <= 3 and
            all(type(x) is int and x > 0 for x in source_snapshot_ids) and
            len(set(source_snapshot_ids)) == len(source_snapshot_ids)
        ):
            raise ValueError("expected unique positive snapshot identifiers")
        result = self._rpc("sxf_base_append_reconciliation", {
            "p_origin_event_key": origin_event_key,
            "p_kind": kind,
            "p_source_snapshot_ids": list(source_snapshot_ids),
            "p_details": dict(details),
            "p_engine": engine, "p_selection": selection,
        })
        if type(result) is not bool:
            raise DurableStoreError("reconciliation not acknowledged")
        return result
