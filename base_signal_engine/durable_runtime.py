"""Phase 4B, NOT DEPLOYED: conservative durable checkpoint job execution.

No CLI or service auto-start, no production migration or legacy source writes.
An immutable source-coverage summary is attached to successful evaluations.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time
from typing import Any, Callable

from .reader import SupabaseMoneywayReader
from .runtime import SupabaseFixtureCatalog
from .scheduler import evaluate_job
from .storage import DurableStoreError, SupabaseCheckpointStore
from .source_quality import CapturingReader, source_coverage
from .lease_heartbeat import CooperativeLeaseHeartbeat


class CheckpointReadBudgetExceeded(RuntimeError):
    """Snapshot reading exceeded its bounded job budget; retry, do not complete."""


class LeaseRenewalUncertain(DurableStoreError):
    """A lease renewal ACK is missing: cannot safely mutate this job again."""


def retry_delay_seconds(attempt: int) -> int:
    """Bounded exponential backoff; all attempts remain in durable queue."""
    return min(3600, 30 * 2 ** min(max(0, attempt - 1), 7))


def execute_claims(reader: SupabaseMoneywayReader, store: SupabaseCheckpointStore,
                   *, worker_id: str, limit: int = 1, lease_seconds: int = 900,
                   lane: str = "ANY", max_read_seconds: int = 150,
                   clock: Callable[[], float] = time.monotonic,
                   progress_hook: Callable[[], None] | None = None) -> dict:
    """Never claim multiple unstarted leases while waiting for a slow DB read.

    A timeout during completion may mean the *transaction committed*; therefore
    mark it uncertain rather than claiming a retry or success. Fencing makes
    an eventual replay idempotent. Lease renewal before completion narrows the
    stale-lease window; long-running readers still need periodic heartbeats.
    """
    if limit != 1:
        raise ValueError("claim batch must be one until heartbeat support")
    if type(max_read_seconds) is not int or not 30 <= max_read_seconds <= 600:
        raise ValueError("unsafe checkpoint read budget")
    if lane not in ("ANY", "LIVE", "BACKLOG") or type(lane) is not str:
        raise ValueError("invalid checkpoint lane")
    if lane == "ANY":
        claimed = store.claim(worker_id, limit=1, lease_seconds=lease_seconds)
    else:
        claimed = store.claim(worker_id, limit=1, lease_seconds=lease_seconds,
                              lane=lane)
    stats = {"claimed": len(claimed), "completed": 0, "waiting_data": 0,
             "retry": 0, "lease_lost": 0, "commit_uncertain": 0}

    for item in claimed:
        deadline = clock() + max_read_seconds
        def pulse_read(*, force: bool = False) -> None:
            if clock() >= deadline:
                raise CheckpointReadBudgetExceeded()
            if heartbeat is not None:
                try:
                    heartbeat.pulse(force=force)
                except DurableStoreError as error:
                    raise LeaseRenewalUncertain() from error

        try:
            heartbeat = None
            if isinstance(reader, SupabaseMoneywayReader):
                heartbeat = CooperativeLeaseHeartbeat(
                    lambda: store.renew(item, lease_seconds=lease_seconds),
                    lease_seconds=lease_seconds)
            pulse_read(force=True)
            capture = CapturingReader(reader, progress_hook=pulse_read)
            result = evaluate_job(item.job, capture)
            pulse_read()
            coverage = source_coverage(item.job, capture.source, result)
            pulse_read()
            result["source_coverage"] = coverage
        except LeaseRenewalUncertain:
            # Renewal response may have been lost after PostgreSQL committed.
            # Never issue a fail/wait/complete write with ambiguous ownership.
            stats["lease_lost"] += 1
            continue
        except Exception as error:
            # Restrict reason to exception class, never source URL / credentials.
            code = type(error).__name__.upper()
            try:
                store.fail(item, code, delay_seconds=retry_delay_seconds(item.attempt_count))
                stats["retry"] += 1
                if progress_hook is not None:
                    progress_hook()
            except DurableStoreError:
                # May be expired/foreign lease OR transport outcome unknown.
                stats["lease_lost"] += 1
            continue

        if coverage["disposition"] == "WAITING_DATA":
            try:
                store.wait_for_data(
                    item, reason="SOURCE_INCOMPLETE",
                    delay_seconds=max(180, retry_delay_seconds(item.attempt_count)))
                stats["waiting_data"] += 1
                if progress_hook is not None:
                    progress_hook()
            except DurableStoreError:
                stats["lease_lost"] += 1
            continue

        try:
            store.renew(item, lease_seconds=lease_seconds)
        except DurableStoreError:
            # Do NOT commit evidence using a lease whose renewal cannot be proven.
            stats["lease_lost"] += 1
            continue
        try:
            store.complete(item, result)
        except DurableStoreError:
            # The DB could have atomically committed, but the HTTP response was
            # lost. Replaying a COMPLETED job cannot duplicate the immutable rows.
            stats["commit_uncertain"] += 1
        else:
            stats["completed"] += 1
            if progress_hook is not None:
                progress_hook()
    return stats


def cycle(reader: SupabaseMoneywayReader, store: SupabaseCheckpointStore, *,
          worker_id: str, now: datetime | None = None, catalog: Any = None,
          fixture_backfill_days: int = 7, claim_limit: int = 1) -> dict:
    """Discovery is separate from execution: queued jobs survive catalog outage.

    Initial bootstrap/backfill beyond the known fixture catalog is a separate
    operator decision and cannot be silently represented as fully covered.
    """
    if fixture_backfill_days < 1 or fixture_backfill_days > 30:
        raise ValueError("invalid discovery horizon")
    if claim_limit != 1:
        raise ValueError("multi-job claims are gated until lease heartbeats")
    at = now or datetime.now(timezone.utc)
    catalog = catalog or SupabaseFixtureCatalog(reader)
    status = {"fixtures": None, "enqueued": None, "catalog_error": False}
    try:
        fixtures = catalog.list_between(at-timedelta(days=fixture_backfill_days),
                                        at+timedelta(hours=74))
        status["fixtures"] = len(fixtures)
        status["enqueued"] = store.enqueue(fixtures)
    except Exception:
        # A discovery error must not block already queued work.
        status["catalog_error"] = True
    status.update(execute_claims(reader, store, worker_id=worker_id, limit=claim_limit))
    return status
