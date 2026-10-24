"""Part 4C2: bounded, opt-in durable late-T6 reconciliation worker.

No CLI startup/deploy, no legacy signal writes. The existing Base rules
remain frozen; PostgreSQL finalizes a whole market's correction atomically.
"""
from __future__ import annotations

from .reconciliation import plan_late_t6
from .reader import SupabaseMoneywayReader
from .lease_heartbeat import CooperativeLeaseHeartbeat
from .storage import DurableStoreError



def missing_source_reconcile_delay(attempt_count: int) -> int:
    """Retain late-source recovery without starving never-attempted corrections.

    Newly missing observations get a 15-minute retry; repeated immutable gaps
    gradually move to an hourly bounded revisit instead of consuming every
    reconciliation lease. The DB keeps the original event and audit history.
    """
    if type(attempt_count) is not int or attempt_count < 1:
        raise ValueError("invalid reconciliation attempt count")
    return min(3600, 900 * (2 ** min(2, (attempt_count - 1) // 3)))



def reconcile_once(reader, store, *, worker_id: str, lease_seconds: int = 900) -> dict:
    """Process at most one durable reconciliation claim to avoid idle leases."""
    claimed = store.claim_reconcile(worker_id, lease_seconds=lease_seconds)
    stats = {"claimed": len(claimed), "completed": 0, "waiting_data": 0,
             "retried": 0, "lease_uncertain": 0, "commit_uncertain": 0}
    for item in claimed:
        try:
            heartbeat = None
            if isinstance(reader, SupabaseMoneywayReader):
                heartbeat = CooperativeLeaseHeartbeat(
                    lambda: store.renew_reconcile(item, lease_seconds=lease_seconds),
                    lease_seconds=lease_seconds)
                heartbeat.pulse(force=True)
            plan = plan_late_t6(
                reader, origin_event_key=item["origin_event_key"],
                fixture_uid=item["fixture_uid"], kickoff_utc=item["kickoff_utc"],
                market=item["market"],
                progress_hook=heartbeat.pulse if heartbeat else None)
        except Exception as error:
            reason = type(error).__name__.upper()
            if reason not in ("SNAPSHOTREADERROR","DURABLESTOREERROR","VALUEERROR",
                              "CONNECTIONERROR","TIMEOUTERROR","RUNTIMEERROR"):
                reason = "WORKER_ERROR"
            try:
                store.retry_reconcile(item, reason=reason, delay_seconds=900)
                stats["retried"] += 1
            except DurableStoreError:
                stats["lease_uncertain"] += 1
            continue
        if plan is None:
            try:
                store.retry_reconcile(
                    item, reason="SOURCE_INCOMPLETE",
                    delay_seconds=missing_source_reconcile_delay(item["attempt_count"]))
                stats["waiting_data"] += 1
            except DurableStoreError:
                stats["lease_uncertain"] += 1
            continue
        try:
            store.renew_reconcile(item, lease_seconds=lease_seconds)
        except DurableStoreError:
            stats["lease_uncertain"] += 1
            continue
        try:
            store.complete_reconcile(item, plan)
        except DurableStoreError:
            # Response timeout may be AFTER an atomic DB commit; never report
            # success or force an immediate duplicate retry from the worker.
            stats["commit_uncertain"] += 1
        else:
            stats["completed"] += 1
    return stats
