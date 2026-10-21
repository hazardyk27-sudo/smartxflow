"""Independent, bounded 80-hour Base fixture-discovery service.

This deliberately does NOT evaluate signals or claim checkpoint/reconciliation
jobs. It reads the canonical fixtures table and all 11 existing job identities,
then idempotently schedules ONLY missing checkpoint families via the existing
database-fenced enqueue RPC. The main checkpoint worker may stall or restart
without preventing fixture discovery.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import sys
import time
from typing import Any

from .reader import SupabaseMoneywayReader
from .runtime import SupabaseFixtureCatalog
from .scheduler import CHECKPOINT_TASKS, RULESET_VERSION, CheckpointJob
from .storage import DurableStoreError, ReadOnlyStoreError, SupabaseCheckpointStore
from .systemd_watchdog import SystemdNotifier


class FixtureHorizonUnverified(RuntimeError):
    """The universe cannot be proven complete; never mark this sweep healthy."""


def scan_horizon_once(reader: Any, store: Any, *,
                      now: datetime | None = None,
                      catalog: Any = None,
                      forward_hours: int = 80,
                      lookback_hours: int = 2,
                      fixture_batch: int = 12,
                      max_fixtures: int = 1500,
                      progress_hook=None) -> dict:
    """Complete snapshot-before-enqueue sweep; never silently truncate fixtures.

    A read-only query gathers ALL existing non-superseded job keys first.
    A fixture is skipped only if ALL 11 frozen jobs exist for its current
    kickoff. Missing jobs are idempotently created in bounded chunks.
    """
    if (type(forward_hours) is not int or not 74 <= forward_hours <= 96 or
            type(lookback_hours) is not int or not 0 <= lookback_hours <= 24 or
            type(fixture_batch) is not int or not 1 <= fixture_batch <= 20 or
            type(max_fixtures) is not int or not 1 <= max_fixtures <= 2000 or
            (progress_hook is not None and not callable(progress_hook))):
        raise ValueError("unsafe fixture discovery bounds")
    at = (now or datetime.now(timezone.utc))
    if at.tzinfo is None:
        raise ValueError("fixture discovery requires timezone-aware clock")
    at = at.astimezone(timezone.utc)
    start, end = at - timedelta(hours=lookback_hours), at + timedelta(hours=forward_hours)

    health = store.health_snapshot()
    cursor = health.get("discovery_cursor") if isinstance(health, dict) else None
    if not isinstance(cursor, dict) or cursor.get("initialized") is not True:
        raise FixtureHorizonUnverified("durable discovery not initialized")

    source = catalog or SupabaseFixtureCatalog(reader, page_size=250, max_pages=20)
    fixtures = source.list_between(start, end)
    if len(fixtures) > max_fixtures:
        raise FixtureHorizonUnverified("fixture universe exceeds bounded scan cap")
    # Never compare against a partial response; all pages complete or raise.
    keys = store.active_job_keys_between(start, end)
    missing = []
    for fixture in fixtures:
        expected = {CheckpointJob(fixture, h, family).key for h, family in CHECKPOINT_TASKS}
        if len(expected) != len(CHECKPOINT_TASKS):
            raise FixtureHorizonUnverified("duplicate frozen checkpoint rules")
        if not expected.issubset(keys):
            missing.append(fixture)

    added = 0
    for i in range(0, len(missing), fixture_batch):
        group = missing[i:i + fixture_batch]
        # Enqueue is idempotent across its full frozen 11-job fanout. It is
        # not a signal event and does not alter any past result or snapshot.
        ack = store.enqueue(group, batch_size=200)
        if type(ack) is not int or not 0 <= ack <= len(group) * len(CHECKPOINT_TASKS):
            raise DurableStoreError("invalid fixture enqueue acknowledgement")
        added += ack
        if progress_hook is not None:
            progress_hook()

    # Rescheduled fixtures have changed physical kickoff identities.
    # Existing SQL fences and records every superseded job; no deletion.
    drift = store.quarantine_fixture_drift(limit=250)
    if progress_hook is not None:
        progress_hook()
    return {"mode": "BASE_FIXTURE_DISCOVERY",
            "status": "SCANNED",
            "checked_at": at.isoformat(),
            "range_start": start.isoformat(), "range_end": end.isoformat(),
            "fixtures": len(fixtures),
            "fully_scheduled_before": len(fixtures) - len(missing),
            "fixtures_needing_enqueue": len(missing),
            "new_jobs": added, "superseded_drift_jobs": drift,
            "drift_may_remain": drift == 250,
            "full_catalog_read": True,
            "full_job_key_read": True,
            "coverage_verified_for_snapshot": True,
            "continuous_future_coverage_verified": False}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Independent Hetzner fixture discovery")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=300)
    args = parser.parse_args(argv)
    if not 120 <= args.interval_seconds <= 600:
        parser.error("unsafe discovery interval")
    if os.environ.get("SXF_BASE_FIXTURE_DISCOVERY_APPROVED") != "yes":
        parser.error("separate fixture discovery release gate required")
    if os.environ.get("SXF_BASE_COMPOSITE_INDEX_VERIFIED") != "yes":
        parser.error("verified fixture/snapshot index gate required")
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        parser.error("server-only Supabase credentials required")

    reader = SupabaseMoneywayReader(url, key, page_size=300,
                                    max_pages_per_window=10, request_timeout_seconds=15)
    store = SupabaseCheckpointStore(url, key, request_timeout_seconds=20)
    notifier = SystemdNotifier()
    if notifier.enabled:
        notifier.ready()

    while True:
        try:
            result = scan_horizon_once(reader, store,
                progress_hook=notifier.progressed if notifier.enabled else None)
            print(json.dumps(result, sort_keys=True), flush=True)
            if notifier.enabled:
                notifier.progressed()
        except ReadOnlyStoreError as error:
            print(json.dumps({"mode": "BASE_FIXTURE_DISCOVERY", "status": "READ_RETRY",
                              "error_type": type(error).__name__}), file=sys.stderr, flush=True)
            return 2
        except DurableStoreError as error:
            # The enqueue/quarantine RPC could have committed before losing
            # its HTTP acknowledgement. Never announce success or blindly
            # replay under an assumed lease/commit outcome.
            print(json.dumps({"mode": "BASE_FIXTURE_DISCOVERY", "status": "UNCERTAIN",
                              "error_type": type(error).__name__}), file=sys.stderr, flush=True)
            return 3
        except FixtureHorizonUnverified as error:
            print(json.dumps({"mode": "BASE_FIXTURE_DISCOVERY", "status": "INVALID_UNIVERSE",
                              "error_type": type(error).__name__}), file=sys.stderr, flush=True)
            return 4
        except Exception as error:
            print(json.dumps({"mode": "BASE_FIXTURE_DISCOVERY", "status": "SCAN_RETRY",
                              "error_type": type(error).__name__}), file=sys.stderr, flush=True)
            return 2
        if args.once:
            return 0
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    sys.exit(main())
