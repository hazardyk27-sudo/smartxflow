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
    try:
        fixtures = source.list_between(begin,end)
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
        store.advance_discovery(item,end=end,fixture_count=len(fixtures))
    except DurableStoreError:
        # The advance may have committed but HTTP response was lost.
        stats["uncertain"] = True
    else:
        stats["advanced"] = True
    return stats
