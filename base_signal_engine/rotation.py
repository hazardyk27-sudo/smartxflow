"""Deterministic sampling scheduler; not a persistent fixture-coverage watermark.

A clock-aligned cycle rescans one canonical UTC kickoff bucket at a time.
Idempotent DB enqueue handles restarts/replays; missing cycles are explicitly
NOT considered successful scans. No filesystem or database cursor is created.
"""
from datetime import datetime, timezone
from math import isfinite

# Priority Base T-8/T-6 windows first. Also scan the *entire* Early horizon:
# a fixture first seen up to 80h ahead is enqueued before T-72.
# This rotation is best-effort; the independent durable contiguous cursor
# provides replay and must not be paused by unrelated historical WAITING_DATA.
HOUR_OFFSETS = (6, 8, 7, 5, 4, 9, 3, 10, 2, 11, 1, 12, 0, -1) + tuple(range(13, 81))


def rotation_slot(at: datetime) -> dict:
    if not isinstance(at, datetime) or at.tzinfo is None:
        raise ValueError("rotation requires an aware UTC clock")
    utc = at.astimezone(timezone.utc)
    # Wall-clock minute slot is deterministic after service restarts; repeats
    # inside one minute are safe thanks to immutable job identity/enqueue RPC.
    tick = int(utc.timestamp() // 60)
    slot = tick % len(HOUR_OFFSETS)
    return {"hour_offset": HOUR_OFFSETS[slot], "slot": slot,
            "cycle_minute_utc": utc.replace(second=0, microsecond=0).isoformat(),
            "cycle_size": len(HOUR_OFFSETS), "coverage_verified": False}


def queue_diagnostics(health: dict, *, now: datetime) -> dict:
    """Fail-closed health evidence; never turn unobserved coverage into green."""
    if not isinstance(health, dict) or not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("missing queue health evidence")
    queue = health.get("checkpoint_queue")
    cursor = health.get("discovery_cursor")
    reconcile = health.get("reconciliation_queue")
    if not all(isinstance(v, dict) for v in (queue, cursor, reconcile)):
        raise ValueError("queue health sections missing")
    pending = queue.get("pending_due")
    old = queue.get("oldest_due_seconds")
    reconcile_due = reconcile.get("pending_due")
    if (type(pending) is not int or pending < 0 or
            type(reconcile_due) is not int or reconcile_due < 0):
        raise ValueError("invalid queue health counters")
    # Postgres EXTRACT(EPOCH) returns a decimal through JSON; the health RPC
    # legitimately reports fractional seconds, and no-due queues may be null.
    if old is None and pending == 0:
        old = 0
    if (type(old) not in (int, float) or not isfinite(old) or old < 0):
        raise ValueError("invalid oldest due age")
    stamp = cursor.get("last_scanned_at")
    age = None
    if stamp is not None:
        try:
            scanned = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
            if scanned.tzinfo is None:
                raise ValueError("naive timestamp")
            age = max(0, int((now.astimezone(timezone.utc) - scanned.astimezone(timezone.utc)).total_seconds()))
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid discovery scan timestamp") from exc
    alerts = []
    if cursor.get("initialized") is not True:
        alerts.append("DISCOVERY_UNINITIALIZED")
    elif age is None or age > 15 * 60:
        alerts.append("DISCOVERY_STALE")
    if pending >= 250:
        alerts.append("CHECKPOINT_BACKPRESSURE")
    if pending and old > 3600:
        alerts.append("CHECKPOINT_OVERDUE")
    if reconcile_due >= 25:
        alerts.append("RECONCILE_BACKLOG")
    return {"discovery_scan_age_seconds": age,
            "checkpoint_pending_due": pending,
            "checkpoint_oldest_due_seconds": old,
            "reconcile_pending_due": reconcile_due,
            "alerts": alerts, "discovery_coverage_verified": False,
            "source_capture_verified": False}
