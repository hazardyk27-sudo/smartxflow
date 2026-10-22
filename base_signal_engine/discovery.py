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
                         catalog: Any = None, window_hours: int = 24,
                         max_fixtures: int | None = None) -> dict:
    """Scan one contiguous UTC window; crash/retry replays idempotent enqueue."""
    if not 1 <= window_hours <= 24:
        raise ValueError("discovery window must be <=24h")
    if max_fixtures is not None and (type(max_fixtures) is not int or
                                     not 1 <= max_fixtures <= 500):
        raise ValueError("unsafe fixture fanout limit")
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
        if max_fixtures is not None:
            # Heavy kickoff hours can exceed the 100-fixture bounded fanout.
            # Halve the ACTUAL source window and re-read *every* fixture in
            # that smaller interval. Never truncate the source fixture list:
            # that would advance the cursor past fixtures never enqueued.
            # The cursor advances only to the verified smaller end time,
            # then the next cycle resumes from that timestamp. Boundaries
            # overlap intentionally; job-key upsert is idempotent.
            while len(fixtures) > max_fixtures:
                if end - begin <= timedelta(seconds=2):
                    # A single dense timestamp cannot be split safely with
                    # a time-only cursor; fail closed rather than lose games.
                    raise RuntimeError("DISCOVERY_WINDOW_TOO_LARGE")
                end = begin + (end - begin) / 2
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


def bounded_cursor_discovery_once(reader: Any, store: Any, *,
                                  worker_id: str, now: datetime | None = None,
                                  catalog: Any = None,
                                  window_hours: int = 1,
                                  max_fixtures: int = 50,
                                  max_pending_due: int = 250,
                                  allow_high_backlog: bool = False) -> dict:
    """Backpressure-safe contiguous fixture discovery; no mass rolling fanout.

    Requires an explicitly initialized SQL cursor. Never performs bootstrap.
    Normal mode pauses on due-job debt. The approved autonomous recovery
    mode may continue bounded discovery despite that debt, to prevent
    historical WAITING_DATA rows from starving fresh checkpoints. Every scanned window advances only after an
    idempotent enqueue of ALL its fixtures; more than max_fixtures is
    a hard retry/error, not a partial cursor advance.
    """
    if (type(window_hours) is not int or not 1 <= window_hours <= 6 or
            type(max_fixtures) is not int or not 1 <= max_fixtures <= 100 or
            type(max_pending_due) is not int or not 1 <= max_pending_due <= 1000
            or type(allow_high_backlog) is not bool):
        raise ValueError("unsafe bounded discovery settings")
    health = store.health_snapshot()
    if not isinstance(health, dict):
        raise DurableStoreError("missing discovery preflight")
    checkpoint = health.get("checkpoint_queue")
    cursor = health.get("discovery_cursor")
    if not isinstance(checkpoint, dict) or not isinstance(cursor, dict):
        raise DurableStoreError("missing discovery health sections")
    pending = checkpoint.get("pending_due")
    if type(pending) is not int or pending < 0:
        raise DurableStoreError("invalid pending checkpoint metric")
    if cursor.get("initialized") is not True:
        # Distinguish explicit not-yet-bootstrapped from a normal empty window.
        return {"status": "UNINITIALIZED", "fixtures": 0, "enqueued": 0,
                "pending_due": pending, "advanced": False,
                "uncertain": False, "paused": False}
    if pending >= max_pending_due and not allow_high_backlog:
        return {"status": "PAUSED_BACKLOG", "fixtures": 0, "enqueued": 0,
                "pending_due": pending, "advanced": False,
                "uncertain": False, "paused": True, "backpressure": True}
    result = discover_window_once(
        reader, store, worker_id=worker_id, now=now, catalog=catalog,
        window_hours=window_hours, max_fixtures=max_fixtures)
    status = ("UNCERTAIN" if result["uncertain"] else
              "RETRY" if result["retry"] else
              "IDLE" if result["idle"] else
              "OK" if result["advanced"] else "ERROR")
    return {"status": status, "fixtures": result["fixtures"],
            "enqueued": result["enqueued"], "pending_due": pending,
            "advanced": result["advanced"], "uncertain": result["uncertain"],
            "paused": False, "backpressure": pending >= max_pending_due}


def near_term_discovery_once(reader: Any, store: Any, *,
                             now: datetime | None = None,
                             catalog: Any = None,
                             hour_offset: int = 0,
                             max_fixtures: int = 50,
                             max_pending_due: int = 1200,
                             allow_high_backlog: bool = False) -> dict:
    """Operator-opt-in, one-hour near-term discovery independent of old cursor lag.

    Scans exactly ONE UTC kickoff hour. The caller must rotate offsets
    deliberately; a successful scan is NOT proof of complete source capture.
    This path never claims or advances the contiguous historical cursor,
    modifies a signal, or pretends a delayed checkpoint was timely.

    At most 50 physical fixtures are fully enumerated by the existing
    idempotent 11-job RPC. Capacity uses a worst-case upper bound (rather than
    assuming previous jobs already exist) and refuses work instead of slicing
    fixtures or silently overrunning a known backlog.
    """
    if (type(hour_offset) is not int or not -1 <= hour_offset <= 80 or
            type(max_fixtures) is not int or not 1 <= max_fixtures <= 100 or
            type(max_pending_due) is not int or not 250 <= max_pending_due <= 2500
            or type(allow_high_backlog) is not bool):
        raise ValueError("unsafe near-term discovery settings")
    at = _parse_time(now or datetime.now(timezone.utc))
    begin = at.replace(minute=0, second=0, microsecond=0) + timedelta(hours=hour_offset)
    end = begin + timedelta(hours=1)
    health = store.health_snapshot()
    queue = health.get("checkpoint_queue") if isinstance(health, dict) else None
    cursor = health.get("discovery_cursor") if isinstance(health, dict) else None
    if not isinstance(queue, dict) or not isinstance(cursor, dict):
        raise DurableStoreError("missing near-term discovery health")
    pending = queue.get("pending_due")
    if type(pending) is not int or pending < 0:
        raise DurableStoreError("invalid near-term due backlog")
    report = {"status": "EMPTY", "fixtures": 0, "enqueued": 0,
              "pending_due": pending, "paused": False, "uncertain": False,
              "cursor_advanced": False, "source_capture_verified": False,
              "window_start": begin.isoformat(), "window_end": end.isoformat()}
    if cursor.get("initialized") is not True:
        report["status"] = "UNINITIALIZED"
        return report
    report["backpressure"] = pending >= max_pending_due
    if pending >= max_pending_due and not allow_high_backlog:
        report["status"], report["paused"] = "PAUSED_BACKLOG", True
        return report

    source = catalog or SupabaseFixtureCatalog(reader)
    fixtures = source.list_between(begin, end)
    report["fixtures"] = len(fixtures)
    if len(fixtures) > max_fixtures:
        report["status"], report["paused"] = "WINDOW_TOO_LARGE", True
        return report
    # Full fanout is required by the frozen checkpoint model. Never insert
    # only preferred bets, silently skip historic jobs or synthesize a signal.
    report["backpressure"] = pending + len(fixtures) * 11 > max_pending_due
    if report["backpressure"] and not allow_high_backlog:
        report["status"], report["paused"] = "PAUSED_CAPACITY", True
        return report
    if not fixtures:
        return report
    # An uncertain HTTP ACK may mean a successful SQL commit: propagate it
    # for operator review, rather than blindly claiming repeated success.
    count = store.enqueue(fixtures)
    if type(count) is not int or not 0 <= count <= len(fixtures) * 11:
        raise DurableStoreError("invalid near-term enqueue result")
    report["enqueued"] = count
    report["status"] = "ENQUEUED" if count else "IDEMPOTENT"
    return report
