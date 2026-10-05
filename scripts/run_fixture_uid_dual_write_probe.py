#!/usr/bin/env python3
"""Read-only validation for Fixture Identity V2 Part 4 dual-write.

The probe fetches one Betwatch prematch payload and reads existing Supabase
fixture/provider mappings. It mutates only in-memory row dictionaries. It never
writes current, history, snapshot, fixture, signal, alarm, or archive rows.
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
from core.fixture_identity_v2 import extract_betwatch_identity  # noqa: E402
from core.fixture_uid_dual_write import (  # noqa: E402
    attach_fixture_uids_to_current_rows,
    attach_fixture_uids_to_snapshots,
)
from core.hash_utils import make_match_id_hash  # noqa: E402
from standalone_scraper import SupabaseWriter  # noqa: E402

PAGE_SIZE = 1000


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


def _provider_registry(writer: SupabaseWriter) -> Dict[str, str]:
    result: Dict[str, str] = {}
    offset = 0
    while True:
        response = requests.get(
            writer._rest_url("fixture_source_ids"),
            headers=writer._headers(),
            params={
                "select": "source_event_id,fixture_uid",
                "source": "eq.betwatch",
                "order": "source_event_id.asc",
                "limit": PAGE_SIZE,
                "offset": offset,
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
        if len(payload) < PAGE_SIZE:
            return result
        offset += PAGE_SIZE


def main() -> int:
    url, service_key = _require_env()
    writer = SupabaseWriter(url, service_key)
    matches = fetch_prematch(timeout=40)
    if not matches:
        print("UID_PROBE_RESULT=FAIL_CLOSED reason=empty_payload")
        return 2

    current_rows: List[dict] = []
    snapshot_rows: List[dict] = []
    hash_to_provider_ids: Dict[str, Set[str]] = defaultdict(set)
    provider_to_hash: Dict[str, str] = {}
    missing_provider_ids = 0

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

        identity = extract_betwatch_identity(match)
        if identity is None:
            missing_provider_ids += 1
            continue
        hash_to_provider_ids[match_hash].add(identity.event_id)
        provider_to_hash[identity.event_id] = match_hash

    hash_collision_groups = sum(1 for ids in hash_to_provider_ids.values() if len(ids) > 1)

    current_stats = attach_fixture_uids_to_current_rows(
        writer,
        "moneyway_1x2",
        current_rows,
        request_get=requests.get,
    )
    snapshot_stats = attach_fixture_uids_to_snapshots(
        writer,
        "moneyway_snapshots",
        snapshot_rows,
        request_get=requests.get,
    )

    hash_to_uid = {
        make_match_id_hash(row["home"], row["away"], row["league"], row["date"]):
        str(row.get("fixture_uid") or "").strip()
        for row in current_rows
        if row.get("fixture_uid")
    }

    registry = _provider_registry(writer)
    registry_overlap = 0
    registry_missing = 0
    registry_uid_conflicts = 0
    for event_id, match_hash in provider_to_hash.items():
        registry_uid = registry.get(event_id)
        if not registry_uid:
            registry_missing += 1
            continue
        registry_overlap += 1
        resolved_uid = hash_to_uid.get(match_hash)
        if not resolved_uid or resolved_uid != registry_uid:
            registry_uid_conflicts += 1

    current_snapshot_uid_mismatch = 0
    for snapshot in snapshot_rows:
        match_hash = str(snapshot.get("match_id_hash") or "")
        if str(snapshot.get("fixture_uid") or "") != hash_to_uid.get(match_hash, ""):
            current_snapshot_uid_mismatch += 1

    print(
        "UID_PROBE "
        f"payload_rows={len(matches)} current_rows={len(current_rows)} "
        f"provider_ids={len(provider_to_hash)} missing_provider_ids={missing_provider_ids} "
        f"hash_collision_groups={hash_collision_groups} "
        f"current_tagged={current_stats.get('tagged_rows', 0)} "
        f"current_unresolved={current_stats.get('unresolved_rows', 0)} "
        f"current_conflicts={current_stats.get('conflicting_existing_uid', 0)} "
        f"current_error={current_stats.get('error') or 'none'} "
        f"snapshot_tagged={snapshot_stats.get('tagged_rows', 0)} "
        f"snapshot_unresolved={snapshot_stats.get('unresolved_rows', 0)} "
        f"snapshot_conflicts={snapshot_stats.get('conflicting_existing_uid', 0)} "
        f"snapshot_error={snapshot_stats.get('error') or 'none'} "
        f"registry_overlap={registry_overlap} registry_missing={registry_missing} "
        f"registry_uid_conflicts={registry_uid_conflicts} "
        f"current_snapshot_uid_mismatch={current_snapshot_uid_mismatch}"
    )

    failed = any((
        missing_provider_ids,
        hash_collision_groups,
        int(current_stats.get("unresolved_rows") or 0),
        int(current_stats.get("conflicting_existing_uid") or 0),
        1 if current_stats.get("error") else 0,
        int(snapshot_stats.get("unresolved_rows") or 0),
        int(snapshot_stats.get("conflicting_existing_uid") or 0),
        1 if snapshot_stats.get("error") else 0,
        registry_uid_conflicts,
        current_snapshot_uid_mismatch,
    ))
    if current_stats.get("tagged_rows") != len(current_rows):
        failed = True
    if snapshot_stats.get("tagged_rows") != len(snapshot_rows):
        failed = True

    if failed:
        print("UID_PROBE_RESULT=FAIL_CLOSED")
        return 2

    print("UID_PROBE_RESULT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
