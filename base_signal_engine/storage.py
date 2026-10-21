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


class ReadOnlyStoreError(DurableStoreError):
    """A read-only RPC failed; no mutation ACK can be uncertain.

    These requests are made through HTTP POST only because PostgREST RPC
    requires it. They are semantically read-only, so systemd can safely retry.
    """


@dataclass(frozen=True)
class ClaimedCheckpoint:
    job_id: str
    lease_token: str
    job: CheckpointJob
    attempt_count: int


class SupabaseCheckpointStore:
    """RPC-only atomic queue/client. Caller controls discovery and scanning."""

    _READ_ONLY_RPCS = frozenset({"sxf_base_health_snapshot", "sxf_base_read_market_events",
                                  "sxf_base_source_fixture_state", "sxf_base_source_health"})

    _ALLOWED = frozenset({
        "sxf_base_enqueue_jobs", "sxf_base_claim_due_jobs",
        "sxf_base_claim_due_jobs_lane",
        "sxf_base_renew_lease", "sxf_base_fail_job", "sxf_base_complete_job",
        "sxf_base_wait_for_data", "sxf_base_append_reconciliation",
        "sxf_base_backfill_reconcile", "sxf_base_claim_reconcile",
        "sxf_base_renew_reconcile", "sxf_base_retry_reconcile",
        "sxf_base_complete_reconcile",
        "sxf_base_init_discovery", "sxf_base_claim_discovery",
        "sxf_base_advance_discovery", "sxf_base_release_discovery",
        "sxf_base_quarantine_fixture_drift", "sxf_base_renew_discovery",
        "sxf_base_health_snapshot",
        "sxf_base_read_market_events",
        "sxf_base_claim_source_changes", "sxf_base_ack_source_change",
        "sxf_base_retry_source_change", "sxf_base_quarantine_obsolete_uid",
        "sxf_base_wake_late_t6",
        "sxf_base_source_fixture_state",
        "sxf_base_source_health",
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
                error_class = ReadOnlyStoreError if name in self._READ_ONLY_RPCS else DurableStoreError
                raise error_class(f"{name} failed: HTTP {response.status_code}")
            return response.json()
        except DurableStoreError:
            raise
        except Exception as error:
            # Do not include URLs, exception messages or response bodies: auth secrets
            # may appear in transport exceptions or provider debug payloads.
            error_class = ReadOnlyStoreError if name in self._READ_ONLY_RPCS else DurableStoreError
            raise error_class(f"{name} unavailable ({type(error).__name__})") from error

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

    def active_job_keys_between(self, start: datetime, end: datetime, *,
                                page_size: int = 500, max_pages: int = 60) -> set[str]:
        """Read a complete, bounded set of current job keys via GET.

        An incomplete page traversal must NEVER masquerade as complete
        coverage; on failure no new discovery writes are attempted.
        """
        if (start.tzinfo is None or end.tzinfo is None or start >= end or
                type(page_size) is not int or not 1 <= page_size <= 1000 or
                type(max_pages) is not int or not 1 <= max_pages <= 80):
            raise ValueError("invalid active job key coverage bounds")
        found: set[str] = set()
        for page in range(max_pages):
            try:
                resp = self._session.get(
                    self._base[:-4] + "sxf_base_checkpoint_jobs",
                    params=[
                        ("select", "job_key"),
                        ("ruleset_version", "eq." + RULESET_VERSION),
                        ("kickoff_utc", "gte." + start.isoformat()),
                        ("kickoff_utc", "lte." + end.isoformat()),
                        ("state", "neq.SUPERSEDED"),
                        ("order", "job_id.asc"),
                        ("limit", str(page_size)),
                        ("offset", str(page * page_size)),
                    ],
                    headers=self._headers, timeout=self._timeout)
                if resp.status_code not in (200, 206):
                    raise ReadOnlyStoreError(
                        f"active job coverage failed: HTTP {resp.status_code}")
                rows = resp.json()
            except ReadOnlyStoreError:
                raise
            except Exception as error:
                raise ReadOnlyStoreError(
                    f"active job coverage unavailable ({type(error).__name__})") from error
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ReadOnlyStoreError("active job coverage malformed")
            for row in rows:
                key = row.get("job_key")
                if not isinstance(key, str) or not key or key in found:
                    raise ReadOnlyStoreError("active job key missing or duplicate")
                found.add(key)
            if len(rows) < page_size:
                return found
        raise ReadOnlyStoreError("active job coverage pagination cap reached")

    def claim(self, worker_id: str, *, limit: int = 25,
              lease_seconds: int = 300, lane: str = "ANY") -> list[ClaimedCheckpoint]:
        if not worker_id or len(worker_id) > 100 or not 1 <= limit <= 100 or not 60 <= lease_seconds <= 1800:
            raise ValueError("invalid claim settings")
        if lane not in ("ANY", "LIVE", "BACKLOG") or type(lane) is not str:
            raise ValueError("invalid checkpoint lane")
        rpc = ("sxf_base_claim_due_jobs" if lane == "ANY" else
               "sxf_base_claim_due_jobs_lane")
        params = {"p_worker": worker_id, "p_limit": limit,
                  "p_lease_seconds": lease_seconds}
        if lane != "ANY":
            params["p_lane"] = lane
        rows = self._rpc(rpc, params)
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
        if not 60 <= delay_seconds <= 21600:
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

    def backfill_reconcile(self, limit: int = 100) -> int:
        if not 1 <= limit <= 500:
            raise ValueError("reconcile backfill limit outside bounds")
        count = self._rpc("sxf_base_backfill_reconcile", {"p_limit": limit})
        if type(count) is not int or not 0 <= count <= limit:
            raise DurableStoreError("invalid reconcile backfill response")
        return count

    def claim_reconcile(self, worker_id: str, *, lease_seconds: int = 900) -> list:
        if not worker_id or len(worker_id.strip()) > 100 or not 60 <= lease_seconds <= 1800:
            raise ValueError("invalid reconcile lease settings")
        rows = self._rpc("sxf_base_claim_reconcile", {
            "p_worker": worker_id, "p_limit": 1, "p_lease_seconds": lease_seconds})
        if not isinstance(rows, list) or len(rows) > 1:
            raise DurableStoreError("invalid reconcile claim response")
        claims = []
        for row in rows:
            try:
                uid = str(UUID(str(row["fixture_uid"])))
                market = str(row["market"])
                if market not in ("1X2", "OU25", "BTTS"):
                    raise ValueError("invalid market")
                origin = str(row["origin_event_key"])
                if not origin or len(origin) > 450:
                    raise ValueError("invalid origin")
                attempt = int(row["attempt_count"])
                rec_id = int(row["reconciliation_id"])
                if attempt < 1 or rec_id < 1:
                    raise ValueError("invalid reconcile identity")
                claims.append({
                    "reconciliation_id": rec_id, "origin_event_key": origin,
                    "fixture_uid": uid, "kickoff_utc": _parse_time(row["kickoff_utc"]),
                    "market": market, "lease_token": str(UUID(str(row["lease_token"]))),
                    "attempt_count": attempt,
                })
            except (KeyError, TypeError, ValueError) as exc:
                raise DurableStoreError("malformed reconcile claim") from exc
        return claims

    def renew_reconcile(self, item: Mapping[str, Any], *, lease_seconds: int = 900) -> None:
        if not 60 <= lease_seconds <= 1800:
            raise ValueError("invalid reconcile renewal TTL")
        if self._rpc("sxf_base_renew_reconcile", {
            "p_reconciliation_id": item["reconciliation_id"],
            "p_lease_token": item["lease_token"], "p_lease_seconds": lease_seconds}) is not True:
            raise DurableStoreError("reconcile renewal rejected")

    def retry_reconcile(self, item: Mapping[str, Any], *,
                        reason: str = "SOURCE_INCOMPLETE", delay_seconds: int = 900) -> None:
        if reason not in ("SOURCE_INCOMPLETE", "SNAPSHOTREADERROR",
                          "DURABLESTOREERROR", "VALUEERROR", "CONNECTIONERROR",
                          "TIMEOUTERROR", "RUNTIMEERROR", "WORKER_ERROR"):
            raise ValueError("invalid reconciliation failure category")
        if not 60 <= delay_seconds <= 3600:
            raise ValueError("invalid reconcile retry interval")
        if self._rpc("sxf_base_retry_reconcile", {
            "p_reconciliation_id": item["reconciliation_id"],
            "p_lease_token": item["lease_token"], "p_reason": reason,
            "p_delay_seconds": delay_seconds}) is not True:
            raise DurableStoreError("reconcile retry rejected")

    def complete_reconcile(self, item: Mapping[str, Any], plan: Any, *,
                           lease_seconds: int = 900) -> None:
        if (item["origin_event_key"] != plan.origin_event_key or
            item["fixture_uid"] != plan.fixture_uid or
            item["kickoff_utc"] != plan.kickoff_utc or
            item["market"] != plan.market):
            raise ValueError("reconciliation proof identity mismatch")
        if self._rpc("sxf_base_complete_reconcile", {
            "p_reconciliation_id": item["reconciliation_id"],
            "p_lease_token": item["lease_token"],
            "p_snapshot_ids": list(plan.source_snapshot_ids),
            "p_signals": list(plan.signals),
            "p_evidence": {"source_observed_at": plan.source_observed_at.isoformat(),
                           "v2_state": plan.v2_state},
        }) is not True:
            raise DurableStoreError("reconciliation completion not acknowledged")

    def init_discovery(self, start: datetime) -> bool:
        """Explicit bootstrap only; never infer initial history horizon."""
        value = self._rpc("sxf_base_init_discovery", {"p_start": start.isoformat()})
        if type(value) is not bool:
            raise DurableStoreError("discovery initialization unacknowledged")
        return value

    def claim_discovery(self, worker_id: str, *, lease_seconds: int = 900) -> dict | None:
        if not worker_id or len(worker_id.strip()) > 100 or not 60 <= lease_seconds <= 1800:
            raise ValueError("invalid discovery lease")
        rows = self._rpc("sxf_base_claim_discovery", {
            "p_worker": worker_id, "p_lease_seconds": lease_seconds})
        if not isinstance(rows, list) or len(rows)>1:
            raise DurableStoreError("invalid discovery claim batch")
        if not rows:
            return None
        r = rows[0]
        try:
            if r["cursor_name"] != "BASE_FIXTURES":
                raise ValueError("wrong cursor")
            start = _parse_time(r["completed_through"])
            bootstrap = _parse_time(r["bootstrap_start"])
            if start<bootstrap or int(r["lease_attempts"]) <1:
                raise ValueError("invalid highwater")
            return {"cursor_name": "BASE_FIXTURES","completed_through": start,
                    "bootstrap_start": bootstrap,
                    "lease_token": str(UUID(str(r["lease_token"]))),
                    "lease_attempts": int(r["lease_attempts"])}
        except (KeyError,ValueError,TypeError) as exc:
            raise DurableStoreError("malformed discovery claim") from exc

    def advance_discovery(self, item: Mapping[str, Any], *,
                          end: datetime, fixture_count: int) -> None:
        if item["cursor_name"]!="BASE_FIXTURES" or type(fixture_count) is not int or fixture_count<0:
            raise ValueError("invalid discovery advancement")
        value = self._rpc("sxf_base_advance_discovery", {
            "p_lease_token": item["lease_token"],
            "p_start": item["completed_through"].isoformat(),
            "p_end": end.isoformat(),
            "p_fixture_count": fixture_count})
        if value is not True:
            raise DurableStoreError("discovery watermark advancement rejected")

    def release_discovery(self, item: Mapping[str, Any], *,
                          error_code: str | None = None) -> None:
        if error_code is not None and (not error_code or
              any(x not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for x in error_code) or
              len(error_code)>64):
            raise ValueError("unsafe discovery error category")
        value = self._rpc("sxf_base_release_discovery", {
            "p_lease_token": item["lease_token"], "p_error_code": error_code})
        if value is not True:
            raise DurableStoreError("discovery release not acknowledged")

    def quarantine_fixture_drift(self, *, limit: int = 250) -> int:
        """Disable obsolete UID/kickoff jobs; immutable history stays visible."""
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("invalid drift quarantine batch size")
        result = self._rpc("sxf_base_quarantine_fixture_drift", {"p_limit": limit})
        if type(result) is not int or not 0 <= result <= limit:
            raise DurableStoreError("invalid drift quarantine acknowledgment")
        return result

    def renew_discovery(self, item: Mapping[str, Any], *,
                        lease_seconds: int = 900) -> None:
        """Extend only a currently owned discovery lease."""
        if type(lease_seconds) is not int or not 60 <= lease_seconds <= 1800:
            raise ValueError("invalid discovery renewal lease interval")
        if self._rpc("sxf_base_renew_discovery", {
            "p_lease_token": item["lease_token"], "p_lease_seconds": lease_seconds,
        }) is not True:
            raise DurableStoreError("discovery renewal rejected")

    def health_snapshot(self) -> dict:
        """Service-role health-only read; never changes checkpoint state."""
        value = self._rpc("sxf_base_health_snapshot", {})
        needed = {"generated_at","checkpoint_queue","reconciliation_queue",
                  "discovery_cursor","fixture_identity","snapshot_ingestion_watermark"}
        if not isinstance(value, dict) or not needed.issubset(value):
            raise DurableStoreError("unexpected health snapshot response")
        return value

    def read_market_events(self, fixture_uid: str, kickoff_utc: datetime) -> dict:
        """Read allowlisted market identity and correction metadata only."""
        uid = str(UUID(fixture_uid))
        result = self._rpc("sxf_base_read_market_events", {
            "p_fixture_uid": uid,
            "p_kickoff_utc": kickoff_utc.isoformat(),
        })
        if (not isinstance(result, dict) or
            type(result.get("fixture_authoritative")) is not bool or
            not isinstance(result.get("events"), list)):
            raise DurableStoreError("malformed current projection evidence")
        return result

    def claim_source_changes(self, worker_id: str, *, lease_seconds: int = 900) -> list[dict]:
        """One event at a time: never claim more leases than can be processed."""
        if not worker_id or len(worker_id.strip()) > 100 or not 60 <= lease_seconds <= 1800:
            raise ValueError("invalid source worker identity or lease")
        rows = self._rpc("sxf_base_claim_source_changes", {
            "p_worker": worker_id, "p_limit": 1, "p_lease_seconds": lease_seconds})
        if not isinstance(rows, list) or len(rows) > 1:
            raise DurableStoreError("invalid source outbox claim batch")
        results = []
        kinds = frozenset(("FIXTURE_INSERT","FIXTURE_CHANGE","FIXTURE_DELETE",
                           "SNAPSHOT_INSERT","SNAPSHOT_CHANGE","SNAPSHOT_DELETE"))
        for row in rows:
            try:
                event_kind = str(row["event_kind"])
                if event_kind not in kinds:
                    raise ValueError("invalid source event type")
                change_id = int(row["change_id"])
                attempt = int(row["attempt_count"])
                if change_id <= 0 or attempt < 1:
                    raise ValueError("invalid source delivery identity")
                previous = (str(UUID(str(row["previous_fixture_uid"])))
                            if row.get("previous_fixture_uid") else None)
                snapshot_id = (int(row["snapshot_id"])
                               if row.get("snapshot_id") is not None else None)
                if event_kind.startswith("SNAPSHOT_") and (
                        snapshot_id is None or snapshot_id <= 0):
                    raise ValueError("invalid source snapshot ID")
                if event_kind.startswith("FIXTURE_") and snapshot_id is not None:
                    raise ValueError("fixture event has snapshot ID")
                results.append({
                    "change_id": change_id, "event_kind": event_kind,
                    "fixture_uid": str(UUID(str(row["fixture_uid"]))),
                    "previous_fixture_uid": previous,
                    "kickoff_before": (_parse_time(row["kickoff_before"])
                                       if row.get("kickoff_before") else None),
                    "kickoff_after": (_parse_time(row["kickoff_after"])
                                      if row.get("kickoff_after") else None),
                    "snapshot_id": snapshot_id, "market": row.get("market"),
                    "source_observed_at": (_parse_time(row["source_observed_at"])
                        if row.get("source_observed_at") else None),
                    "captured_at": _parse_time(row["captured_at"]),
                    "attempt_count": attempt,
                    "lease_token": str(UUID(str(row["lease_token"]))),
                })
            except (ValueError, KeyError, TypeError) as error:
                raise DurableStoreError("malformed source outbox identity") from error
        return results

    def ack_source_change(self, item: Mapping[str, Any]) -> None:
        result = self._rpc("sxf_base_ack_source_change", {
            "p_change_id": item["change_id"], "p_lease_token": item["lease_token"]})
        if result is not True:
            raise DurableStoreError("source delivery acknowledgment rejected")

    def retry_source_change(self, item: Mapping[str, Any], *,
                            reason: str, delay_seconds: int = 300) -> None:
        if not reason or len(reason) > 64 or any(
            ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for ch in reason
        ):
            raise ValueError("unsafe source retry classification")
        if type(delay_seconds) is not int or not 10 <= delay_seconds <= 3600:
            raise ValueError("invalid source retry delay")
        result = self._rpc("sxf_base_retry_source_change", {
            "p_change_id": item["change_id"], "p_lease_token": item["lease_token"],
            "p_reason": reason, "p_delay_seconds": delay_seconds})
        if result is not True:
            raise DurableStoreError("source retry transition rejected")

    def quarantine_obsolete_uid(self, fixture_uid: str, *, limit: int = 250) -> int:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("invalid UID quarantine limit")
        count = self._rpc("sxf_base_quarantine_obsolete_uid", {
            "p_fixture_uid": str(UUID(fixture_uid)), "p_limit": limit})
        if type(count) is not int or not 0 <= count <= limit:
            raise DurableStoreError("invalid obsolete UID quarantine response")
        return count

    def wake_late_t6(self, fixture_uid: str, market: str,
                     observed_at: datetime) -> int:
        if market not in ("1X2","OU25","BTTS"):
            raise ValueError("invalid T6 wake market")
        value = self._rpc("sxf_base_wake_late_t6", {
            "p_fixture_uid": str(UUID(fixture_uid)),
            "p_market": market, "p_observed_at": observed_at.isoformat()})
        if type(value) is not int or value < 0:
            raise DurableStoreError("invalid wake response")
        return value

    def source_fixture_state(self, fixture_uid: str) -> datetime | None:
        """Read current source kickoff; None is authoritative deleted UID."""
        value = self._rpc("sxf_base_source_fixture_state", {
            "p_fixture_uid": str(UUID(fixture_uid))})
        if value is None:
            return None
        try:
            return _parse_time(value)
        except (ValueError, TypeError) as exc:
            raise DurableStoreError("invalid source fixture state") from exc

    def source_health(self) -> dict:
        """Aggregate append-only source changes without claiming commit times."""
        value = self._rpc("sxf_base_source_health", {})
        if (not isinstance(value, dict) or
            value.get("captured_at_semantics") != "TRIGGER_TIME_NOT_COMMIT_TIME" or
            value.get("source_commit_watermark", "INVALID") is not None or
            not isinstance(value.get("source_delivery"), dict) or
            not isinstance(value.get("event_kinds"), dict)):
            raise DurableStoreError("invalid source change health payload")
        return value
