"""Hetzner-only read-only Base pre-shadow telemetry.

This is NOT the 24h release attestation. The source-change outbox and commit
watermark are not deployed. Every observation explicitly marks this missing
evidence and fails the full shadow gate even with healthy raw snapshots.
No database table insert/update/delete and no systemd activation here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import sys
import time

from .reader import SupabaseMoneywayReader, _parse_time
from .shadow_evidence import ShadowEvidenceJournal
from .storage import SupabaseCheckpointStore


def observe_once(reader, store, journal: ShadowEvidenceJournal, *,
                 now: datetime | None = None) -> dict:
    at = now or datetime.now(timezone.utc)
    if at.tzinfo is None:
        raise ValueError("timezone-aware observer timestamp required")
    at = at.astimezone(timezone.utc)
    health = store.health_snapshot()
    checkpoints = health.get("checkpoint_queue", {})
    reconciliation = health.get("reconciliation_queue", {})
    counts = {}
    for label, section, name in (
        ("checkpoint_pending_due", checkpoints, "pending_due"),
        ("checkpoint_waiting_data", checkpoints, "waiting_data"),
        ("checkpoint_expired_leases", checkpoints, "expired_leases"),
        ("reconcile_pending_due", reconciliation, "pending_due"),
        ("reconcile_waiting_data", reconciliation, "waiting_data"),
        ("reconcile_expired_leases", reconciliation, "expired_leases"),
    ):
        value = section.get(name) if isinstance(section, dict) else None
        if type(value) is not int or value < 0:
            raise ValueError("missing durable health counter")
        counts[label] = value
    latest = reader._get("moneyway_snapshots", [
        ("select", "scraped_at_utc,id"),
        ("order", "scraped_at_utc.desc,id.desc"),
        ("limit", "1"),
    ])
    if len(latest) != 1:
        raise ValueError("missing source snapshot freshness evidence")
    source_at = _parse_time(latest[0]["scraped_at_utc"])
    age = (at - source_at).total_seconds()
    if age < -120:
        raise ValueError("future source freshness timestamp")
    counts.update({"failed": 0, "waiting_data": 0,
                   "uncertain_commits": 0})
    seq = journal.append(recorded_at=at, counters=counts,
                         error_code="SOURCE_CAPTURE_UNVERIFIED")
    return {
        "mode": "HETZNER_READ_ONLY_PRE_SHADOW",
        "sequence": seq,
        "checkpoint_pending_due": counts["checkpoint_pending_due"],
        "checkpoint_expired_leases": counts["checkpoint_expired_leases"],
        "source_snapshot_latest_utc": source_at.isoformat(),
        "source_snapshot_age_seconds": int(max(age, 0)),
        "source_capture_verified": False,
        "source_commit_watermark": None,
        "real_24h_verified": False,
        "production_approved": False,
        "db_writes_performed": False,
        "release_gate": "BLOCKED_SOURCE_CAPTURE_UNVERIFIED",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Honest read-only Base pre-shadow")
    parser.add_argument("--journal", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-seconds", type=int, default=120)
    args = parser.parse_args(argv)
    if os.environ.get("SXF_BASE_READ_ONLY_OBSERVATION_APPROVED") != "yes":
        parser.error("explicit read-only monitoring opt-in required")
    if not 60 <= args.interval_seconds <= 600:
        parser.error("bounded sampling interval required")
    reader = SupabaseMoneywayReader(
        os.environ.get("SUPABASE_URL", ""),
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        page_size=100, max_pages_per_window=1,
        request_timeout_seconds=15)
    store = SupabaseCheckpointStore(
        os.environ.get("SUPABASE_URL", ""),
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
        request_timeout_seconds=15)
    journal = ShadowEvidenceJournal(
        args.journal, run_id=args.run_id, mode="OPERATOR_READ_ONLY")
    while True:
        try:
            observation = observe_once(reader, store, journal)
            print(json.dumps(observation, sort_keys=True), flush=True)
        except Exception as exc:
            print(json.dumps({"mode":"HETZNER_READ_ONLY_PRE_SHADOW",
                              "status":"FAILED",
                              "error_type":type(exc).__name__,
                              "real_24h_verified":False}),
                  file=sys.stderr,flush=True)
            return 2
        if args.once:
            return 0
        time.sleep(args.interval_seconds)


if __name__=="__main__":
    sys.exit(main())
