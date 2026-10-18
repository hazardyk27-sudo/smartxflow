"""Phase 4, *not deployed*: durable queue orchestration using atomic Supabase RPCs.

Intentionally has no command-line auto-start. DB migration, index benchmark,
preview integration test, shadow authorization and explicit production approval
are prerequisites. Legacy signal tables / scraper remain untouched.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .reader import SupabaseMoneywayReader
from .runtime import SupabaseFixtureCatalog
from .scheduler import evaluate_job
from .storage import ClaimedCheckpoint, DurableStoreError, SupabaseCheckpointStore


def retry_delay_seconds(attempt: int) -> int:
    """Bounded exponential backoff; all attempts remain in durable queue."""
    return min(3600, 30 * 2 ** min(max(0, attempt - 1), 7))


def execute_claims(reader: SupabaseMoneywayReader, store: SupabaseCheckpointStore,
                   *, worker_id: str, limit: int = 1, lease_seconds: int = 900) -> dict:
    """Claim and finish jobs, independently; DB commits both audit+signals or nothing.

    One claim per cycle avoids unstarted jobs expiring while earlier jobs run.
    The 900s lease is provisional; long-running evaluations must renew before
    expiry. DB fencing prevents stale-token writes regardless of runtime failures.
    """
    claimed = store.claim(worker_id, limit=limit, lease_seconds=lease_seconds)
    stats = {"claimed": len(claimed), "completed": 0, "retry": 0, "lease_lost": 0}
    for item in claimed:
        try:
            result = evaluate_job(item.job, reader)
            # A stale worker cannot silently commit: SQL verifies ownership token.
            store.complete(item, result)
            stats["completed"] += 1
        except Exception as error:
            code = type(error).__name__.upper()
            try:
                store.fail(item, code, delay_seconds=retry_delay_seconds(item.attempt_count))
                stats["retry"] += 1
            except DurableStoreError:
                # A lost lease may be owned by another worker; do not mutate it.
                stats["lease_lost"] += 1
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