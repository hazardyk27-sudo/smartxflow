"""Part 4C3: opt-in bounded durable bootstrap and fixture discovery.

No CLI or automatic service activation. Start must be explicitly initialized
against a verified source retention window. A cursor advances ONLY after
paginated source discovery and idempotent DB enqueue both acknowledge success.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .reader import _parse_time
from .runtime import SupabaseFixtureCatalog
from .storage import DurableStoreError
from .lease_heartbeat import CooperativeLeaseHeartbeat


def discover_window_once(reader: Any, store: Any, *,
                         worker_id: str, now: datetime | None = None,
                         catalog: Any = None, window_hours: int = 24) -> dict:
    """Scan one contiguous UTC window; crash/retry replays idempotent enqueue."""
    if not 1 <= window_hours <= 24:
        raise ValueError("discovery window must be <=24h")
    at = _parse_time(now or datetime.now(timezone.utc))
    item = store.claim_discovery(worker_id)
    stats = {"claimed": bool(item), "enqueued": 0, "fixtures": 0,
             "advanced": False, "retry": False, "uncertain": False, "idle": False}
    if item is None:
        stats["idle"] = True
        return stats
    begin = item["completed_through"]
    end = min(begin + timedelta(hours=window_hours), at + timedelta(hours=74))
    if end <= begin:
        try:
            store.release_discovery(item)
            stats["idle"] = True
        except DurableStoreError:
            stats["uncertain"] = True
        return stats
    source = catalog or SupabaseFixtureCatalog(reader)
    heartbeat = None
    try:
        if hasattr(store, "renew_discovery"):
            heartbeat = CooperativeLeaseHeartbeat(
                lambda: store.renew_discovery(item, lease_seconds=900),
                lease_seconds=900)
            heartbeat.pulse(force=True)
        if heartbeat is not None and isinstance(source, SupabaseFixtureCatalog):
            fixtures = source.list_between(begin,end,progress_hook=heartbeat.pulse)
        else:
            fixtures = source.list_between(begin,end)
        if heartbeat is not None:
            heartbeat.pulse(force=True)
        # Enqueue uses the same 11 frozen tasks per fixture; no filtering.
        enqueued = store.enqueue(fixtures)
    except Exception as error:
        reason = type(error).__name__.upper()
        if reason not in ("SNAPSHOTREADERROR","CATALOGREADERROR","DURABLESTOREERROR",
                          "VALUEERROR","CONNECTIONERROR","TIMEOUTERROR","RUNTIMEERROR"):
            reason = "WORKER_ERROR"
        try:
            store.release_discovery(item,error_code=reason)
            stats["retry"] = True
        except DurableStoreError:
            stats["uncertain"] = True
        return stats
    stats["fixtures"],stats["enqueued"] = len(fixtures),enqueued
    try:
        if heartbeat is not None:
            heartbeat.pulse(force=True)
        store.advance_discovery(item,end=end,fixture_count=len(fixtures))
    except DurableStoreError:
        # The advance may have committed but HTTP response was lost.
        stats["uncertain"] = True
    else:
        stats["advanced"] = True
    return stats

def rolling_rescan_once(reader: Any, store: Any, *,
                        now: datetime | None = None, catalog: Any = None,
                        lookback_days: int = 14, drift_limit: int = 250) -> dict:
    """Repeat a bounded kickoff window; never claim it is an ingest watermark.

    A late-created fixture or reschedule inside this window is re-enqueued
    idempotently. SQL quarantine rejects stale jobs even if a reader races
    rescheduling. Failures propagate, rather than asserting successful coverage.
    """
    if type(lookback_days) is not int or not 1 <= lookback_days <= 30:
        raise ValueError("rolling lookback must be between 1 and 30 days")
    if type(drift_limit) is not int or not 1 <= drift_limit <= 1000:
        raise ValueError("drift batch must be between 1 and 1000")
    at = _parse_time(now or datetime.now(timezone.utc))
    source = catalog or SupabaseFixtureCatalog(reader)
    fixtures = source.list_between(at - timedelta(days=lookback_days),
                                   at + timedelta(hours=74))
    enqueued = store.enqueue(fixtures)
    superseded = store.quarantine_fixture_drift(limit=drift_limit)
    return {"fixtures_discovered": len(fixtures), "enqueued": enqueued,
            "superseded_jobs": superseded, "lookback_days": lookback_days,
            "complete_ingestion_history": False}
