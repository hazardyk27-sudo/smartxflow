#!/usr/bin/env python3
"""Run a short, shadow-only Fixture Identity V2 stability probe.

This script intentionally does NOT run the normal prematch writer. It only:
1. fetches Betwatch prematch payloads,
2. resolves existing legacy fixture hashes to already-assigned fixture_uid values,
3. records provider -> fixture_uid observations through the guarded shadow RPC,
4. reports cross-sample stability.

It never writes current/history/snapshot/fixture rows and never changes legacy
match_id_hash behavior.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Set

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "desktop" / "scraper_standalone"))

from betwatch_client import fetch_prematch  # noqa: E402
from core.fixture_identity_shadow import (  # noqa: E402
    build_betwatch_identity_stage,
    flush_staged_betwatch_identity_shadow,
)
from standalone_scraper import SupabaseWriter  # noqa: E402

MIN_INTERVAL_SECONDS = 40


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _event_to_hashes(matches) -> Dict[str, Set[str]]:
    batch = build_betwatch_identity_stage(matches)
    result: Dict[str, Set[str]] = defaultdict(set)
    for match_hash, event_ids in batch.hash_to_event_ids.items():
        for event_id in event_ids:
            result[event_id].add(match_hash)
    return dict(result)


def _require_env() -> tuple[str, str]:
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    service_key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url:
        raise SystemExit("SUPABASE_URL missing")
    if not service_key:
        raise SystemExit(
            "SUPABASE_SERVICE_ROLE_KEY missing; shadow probe refuses anon-key fallback"
        )
    if not (os.environ.get("Betwach_api_key") or "").strip():
        raise SystemExit("Betwach_api_key missing")
    return url, service_key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--interval", type=int, default=45)
    args = parser.parse_args()

    if args.samples < 2:
        raise SystemExit("--samples must be >= 2")
    if args.interval < MIN_INTERVAL_SECONDS:
        raise SystemExit(f"--interval must be >= {MIN_INTERVAL_SECONDS} seconds")

    url, service_key = _require_env()
    writer = SupabaseWriter(url, service_key)

    cross_sample_hashes: Dict[str, Set[str]] = defaultdict(set)
    total_errors = 0
    total_conflicts = 0
    total_missing = 0
    total_hash_collisions = 0
    total_event_collisions = 0
    total_unresolved = 0
    total_inserted = 0
    total_matched = 0
    sample_event_sets = []

    for idx in range(args.samples):
        if idx:
            time.sleep(args.interval)

        observed_at = _utc_now()
        matches = fetch_prematch(timeout=40)
        event_map = _event_to_hashes(matches)
        sample_event_sets.append(set(event_map))
        for event_id, hashes in event_map.items():
            cross_sample_hashes[event_id].update(hashes)

        stats = flush_staged_betwatch_identity_shadow(
            writer,
            observed_at=observed_at,
            logger=print,
        )

        total_errors += 1 if stats.get("error") else 0
        total_conflicts += int(stats.get("conflict_count") or 0)
        total_missing += int(stats.get("missing_provider_ids") or 0)
        total_hash_collisions += int(stats.get("hash_collision_groups") or 0)
        total_event_collisions += int(stats.get("provider_event_collision_groups") or 0)
        total_unresolved += int(stats.get("unresolved_hashes") or 0)
        total_inserted += int(stats.get("inserted_count") or 0)
        total_matched += int(stats.get("matched_count") or 0)

        print(
            "PROBE_SAMPLE "
            f"index={idx + 1} rows={len(matches)} providers={len(event_map)} "
            f"submitted={stats.get('submitted_bindings', 0)} "
            f"inserted={stats.get('inserted_count', 0)} "
            f"matched={stats.get('matched_count', 0)} "
            f"conflicts={stats.get('conflict_count', 0)} "
            f"missing={stats.get('missing_provider_ids', 0)} "
            f"hash_collision={stats.get('hash_collision_groups', 0)} "
            f"event_collision={stats.get('provider_event_collision_groups', 0)} "
            f"unresolved={stats.get('unresolved_hashes', 0)} "
            f"error={stats.get('error') or 'none'}"
        )

    changed_hash_events = {
        event_id: hashes
        for event_id, hashes in cross_sample_hashes.items()
        if len(hashes) > 1
    }
    repeated_events = {
        event_id
        for event_id in cross_sample_hashes
        if sum(event_id in sample for sample in sample_event_sets) >= 2
    }
    all_events = set().union(*sample_event_sets) if sample_event_sets else set()

    print(
        "PROBE_FINAL "
        f"samples={args.samples} unique_provider_ids={len(all_events)} "
        f"repeated_provider_ids={len(repeated_events)} "
        f"provider_ids_with_hash_change={len(changed_hash_events)} "
        f"inserted_total={total_inserted} matched_total={total_matched} "
        f"conflicts_total={total_conflicts} missing_total={total_missing} "
        f"hash_collision_total={total_hash_collisions} "
        f"event_collision_total={total_event_collisions} "
        f"unresolved_total={total_unresolved} errors_total={total_errors}"
    )

    failed = any(
        (
            total_errors,
            total_conflicts,
            total_missing,
            total_hash_collisions,
            total_event_collisions,
            total_unresolved,
            len(changed_hash_events),
        )
    )
    if failed:
        print("PROBE_RESULT=FAIL_CLOSED")
        return 2

    print("PROBE_RESULT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
