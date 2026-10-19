"""Phase 5C1 opt-in adapter: connect existing read-only shadow scan to evidence.

This module starts no loop and contains no deploy/systemd code. Requires a
separately approved source read session and local checkpoint JSONL journal.
Missing health or source queries are recorded as failed cycles, not zero debt.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .runtime import scan_once
from .shadow_evidence import ShadowEvidenceJournal


def _count(obj: dict, key: str) -> int:
    if not isinstance(obj,dict):
        raise ValueError("health section unavailable")
    value=obj.get(key)
    if type(value) is not int or value<0:
        raise ValueError("health metric missing/invalid")
    return value


def _class_code(error: BaseException) -> str:
    code=type(error).__name__.upper()
    return code if 1<=len(code)<=64 and all(
        ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for ch in code) else "WORKER_ERROR"


def _counters(scan: dict, durable: dict, source: dict) -> dict:
    checkpoints=durable.get("checkpoint_queue")
    reconcile=durable.get("reconciliation_queue")
    delivery=source.get("source_delivery")
    if (source.get("captured_at_semantics")!="TRIGGER_TIME_NOT_COMMIT_TIME" or
            "source_commit_watermark" not in source or
            source["source_commit_watermark"] is not None):
        raise ValueError("unverified source commit watermark")
    return {
        "fixtures_discovered":_count(scan,"fixtures_discovered"),
        "due":_count(scan,"due"),
        "committed":_count(scan,"committed"),
        "already_done":_count(scan,"already_done"),
        "failed":_count(scan,"failed"),
        "waiting_data":_count(scan,"waiting_data"),
        "checkpoint_pending_due":_count(checkpoints,"pending_due"),
        "checkpoint_waiting_data":_count(checkpoints,"waiting_data"),
        "checkpoint_expired_leases":_count(checkpoints,"expired_leases"),
        "reconcile_pending_due":_count(reconcile,"pending_due"),
        "reconcile_waiting_data":_count(reconcile,"waiting_data"),
        "reconcile_expired_leases":_count(reconcile,"expired_leases"),
        "source_pending_due":_count(delivery,"pending_due"),
        "source_review_required":_count(delivery,"review_required"),
        "source_expired_leases":_count(delivery,"expired_leases"),
        "uncertain_commits":0,  # local shadow has no remote completion RPC
    }


def record_shadow_once(reader: Any, checkpoint_journal: Any, health_store: Any,
                       evidence: ShadowEvidenceJournal, *,
                       now: datetime | None = None, catalog: Any = None,
                       backfill_days: int = 3,max_jobs: int = 25) -> dict:
    """One explicitly invoked read-only scan; no background scheduling.

    Local journal stores checkpoint audit, *not* production DB signals.
    A failure of any scan or health read is a separate failed evidence row;
    never conceal a health outage by inventing zero-valued metrics.
    """
    at=now or datetime.now(timezone.utc)
    try:
        scan=scan_once(reader,checkpoint_journal,now=at,max_jobs=max_jobs,
                       backfill_days=backfill_days,catalog=catalog)
        durable=health_store.health_snapshot()
        source=health_store.source_health()
        counters=_counters(scan,durable,source)
        error_code="SHADOW_JOB_FAILURE" if counters["failed"] else None
    except Exception as exc:
        counters={"failed":1}
        error_code=_class_code(exc)
    seq=evidence.append(recorded_at=at,counters=counters,error_code=error_code)
    return {"sequence":seq,"error_code":error_code,
            "success":error_code is None,
            "evidence_mode":evidence.mode,"real_24h_verified":False}
