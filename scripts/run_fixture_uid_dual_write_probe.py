#!/usr/bin/env python3
"""Read-only Fixture Identity V2 Part 5 runtime-parity probe.

This probe exercises the same provider-gated UID resolver used by prematch current
writes. It never writes current/history/snapshot/fixture/registry rows. Snapshot
UIDs are expected to remain fail-closed until snapshots carry provider-verifiable
physical identity.
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "desktop" / "scraper_standalone"))

from betwatch_client import fetch_prematch, normalize_kickoff  # noqa: E402
from core.fixture_identity_shadow import build_betwatch_identity_stage  # noqa: E402
from core.fixture_uid_dual_write import attach_fixture_uids_to_snapshots  # noqa: E402
from core.fixture_uid_provider_gate import attach_provider_verified_fixture_uids  # noqa: E402
from core.hash_utils import make_match_id_hash  # noqa: E402
from standalone_scraper import SupabaseWriter  # noqa: E402

PAGE_SIZE = 500


def _require_env() -> tuple[str, str]:
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    service_key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url:
        raise SystemExit("SUPABASE_URL missing")
    if not service_key:
        raise SystemExit("SUPABASE_SERVICE_ROLE_KEY missing; probe refuses anon fallback")
    if not (os.environ.get("Betwach_api_key") or "").strip():
        raise SystemExit("Betwach_api_key missing")
    return url, service_key


def _registry_for_events(writer: SupabaseWriter, event_ids: Set[str]) -> Dict[str, str]:
    wanted = sorted(event_ids)
    result: Dict[str, str] = {}
    for start in range(0, len(wanted), PAGE_SIZE):
        chunk = wanted[start:start + PAGE_SIZE]
        if not chunk:
            continue
        response = requests.get(
            writer._rest_url("fixture_source_ids"),
            headers=writer._headers(),
            params={
                "select": "source_event_id,fixture_uid",
                "source": "eq.betwatch",
                "source_event_id": f"in.({','.join(chunk)})",
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("provider registry returned non-list payload")
        for row in payload:
            event_id = str(row.get("source_event_id") or "").strip()
            fixture_uid = str(row.get("fixture_uid") or "").strip()
            if event_id and fixture_uid:
                result[event_id] = fixture_uid
    return result


def main() -> int:
    url, service_key = _require_env()
    writer = SupabaseWriter(url, service_key)

    matches = fetch_prematch(timeout=40)
    if not matches:
        print("UID_PROBE_RESULT=FAIL_CLOSED reason=empty_payload")
        return 2

    batch = build_betwatch_identity_stage(matches)
    safe_event_by_hash: Dict[str, str] = {}
    safe_physical_by_hash: Dict[str, tuple[str, str, str, str]] = {}
    event_to_hashes: Dict[str, Set[str]] = defaultdict(set)

    hash_collision_groups = 0
    physical_collision_groups = 0
    for match_hash, event_ids in batch.hash_to_event_ids.items():
        physical_keys = batch.hash_to_physical_keys.get(match_hash, set())
        for event_id in event_ids:
            event_to_hashes[event_id].add(match_hash)
        if len(event_ids) != 1:
            hash_collision_groups += 1
            continue
        if len(physical_keys) != 1:
            physical_collision_groups += 1
            continue
        safe_event_by_hash[match_hash] = next(iter(event_ids))
        safe_physical_by_hash[match_hash] = next(iter(physical_keys))

    provider_event_collision_groups = sum(
        1 for hashes in event_to_hashes.values() if len(hashes) > 1
    )

    writer._fixture_identity_event_by_hash = dict(safe_event_by_hash)
    writer._fixture_identity_physical_by_hash = dict(safe_physical_by_hash)

    current_rows: List[dict] = []
    snapshot_rows: List[dict] = []
    for match in matches:
        teams = match.get("teams") or {}
        home = str(teams.get("v1") or "").strip()
        away = str(teams.get("v2") or "").strip()
        league = str(match.get("league") or "").strip()
        if not home or not away:
            continue
        date = normalize_kickoff(str(match.get("kickoff") or "").strip())
        match_hash = make_match_id_hash(home, away, league, date)
        current_rows.append({
            "league": league,
            "home": home,
            "away": away,
            "date": date,
        })
        snapshot_rows.append({
            "match_id_hash": match_hash,
            "market": "PROBE",
            "selection": "PROBE",
        })

    registry = _registry_for_events(writer, set(safe_event_by_hash.values()))
    registry_missing = sum(
        1 for event_id in safe_event_by_hash.values() if event_id not in registry
    )

    current_stats = attach_provider_verified_fixture_uids(
        writer,
        current_rows,
        request_get=requests.get,
    )
    snapshot_stats = attach_fixture_uids_to_snapshots(
        writer,
        "moneyway_snapshots",
        snapshot_rows,
        request_get=requests.get,
    )

    current_tagged = int(current_stats.get("tagged_rows") or 0)
    current_unresolved = int(current_stats.get("unresolved_rows") or 0)
    current_mismatch = int(current_stats.get("identity_mismatch_rows") or 0)
    current_conflicts = int(current_stats.get("conflicting_existing_uid") or 0)

    snapshot_fail_closed = (
        int(snapshot_stats.get("tagged_rows") or 0) == 0
        and int(snapshot_stats.get("unresolved_rows") or 0) == len(snapshot_rows)
        and snapshot_stats.get("error") == "snapshot_provider_identity_required"
    )

    print(
        "UID_PROBE "
        f"payload_rows={len(matches)} current_rows={len(current_rows)} "
        f"eligible_rows={batch.eligible_rows} missing_provider_ids={batch.missing_provider_ids} "
        f"safe_hashes={len(safe_event_by_hash)} "
        f"hash_collision_groups={hash_collision_groups} "
        f"physical_collision_groups={physical_collision_groups} "
        f"provider_event_collision_groups={provider_event_collision_groups} "
        f"registry_overlap={len(registry)} registry_missing={registry_missing} "
        f"current_tagged={current_tagged} current_unresolved={current_unresolved} "
        f"current_mismatch={current_mismatch} current_conflicts={current_conflicts} "
        f"current_error={current_stats.get('error') or 'none'} "
        f"snapshot_tagged={snapshot_stats.get('tagged_rows', 0)} "
        f"snapshot_unresolved={snapshot_stats.get('unresolved_rows', 0)} "
        f"snapshot_error={snapshot_stats.get('error') or 'none'} "
        f"snapshot_fail_closed={1 if snapshot_fail_closed else 0}"
    )

    failed = any((
        int(batch.missing_provider_ids or 0),
        hash_collision_groups,
        physical_collision_groups,
        provider_event_collision_groups,
        registry_missing,
        current_unresolved,
        current_mismatch,
        current_conflicts,
        1 if current_stats.get("error") else 0,
        0 if current_tagged == len(current_rows) else 1,
        0 if snapshot_fail_closed else 1,
    ))

    if failed:
        print("UID_PROBE_RESULT=FAIL_CLOSED")
        return 2

    print("UID_PROBE_RESULT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
