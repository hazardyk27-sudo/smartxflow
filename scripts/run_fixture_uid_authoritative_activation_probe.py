#!/usr/bin/env python3
"""Controlled Fixture Identity V2 authoritative activation probe.

This is the narrow write probe used after the Part 9 production migration and
before enabling the full prematch scraper flag. It may mutate ONLY the physical
fixture identity surface through ``record_betwatch_fixture_batch_v2``:

- ``fixtures``
- ``fixture_source_ids``

It does NOT write current market tables, history tables, snapshots, signals,
alarms, learning archive data, or any other application state.

The probe first runs the provider-first in-memory preflight. Any ambiguity blocks
the RPC. Execution also requires an explicit one-shot guard environment value:

    SMARTXFLOW_FIXTURE_UID_ACTIVATION_PROBE=APPLY

The full scraper activation flag is intentionally not changed by this script.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "desktop" / "scraper_standalone"))

from betwatch_client import fetch_prematch  # noqa: E402
from core.fixture_uid_authoritative_writer import write_provider_authoritative_fixture_batch  # noqa: E402
from core.fixture_uid_writer_preflight import plan_provider_first_fixture_rows  # noqa: E402
from standalone_scraper import SupabaseWriter  # noqa: E402

PAGE_SIZE = 1000
_APPLY_GUARD = "SMARTXFLOW_FIXTURE_UID_ACTIVATION_PROBE"


def _require_env() -> tuple[str, str]:
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    service_key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    betwatch_key = (os.environ.get("Betwach_api_key") or "").strip()
    if not url:
        raise SystemExit("SUPABASE_URL missing")
    if not service_key:
        raise SystemExit("SUPABASE_SERVICE_ROLE_KEY missing; activation probe refuses anon fallback")
    if not betwatch_key:
        raise SystemExit("Betwach_api_key missing")
    if (os.environ.get(_APPLY_GUARD) or "").strip() != "APPLY":
        raise SystemExit(f"{_APPLY_GUARD}=APPLY required")
    return url, service_key


def _read_all(
    writer: SupabaseWriter,
    table: str,
    select: str,
    extra: Dict[str, str] | None = None,
) -> List[dict]:
    result: List[dict] = []
    offset = 0
    while True:
        params: Dict[str, str | int] = {
            "select": select,
            "limit": PAGE_SIZE,
            "offset": offset,
        }
        if extra:
            params.update(extra)
        response = requests.get(
            writer._rest_url(table),
            headers=writer._headers(),
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list):
            raise RuntimeError(f"{table} returned non-list payload")
        result.extend(rows)
        if len(rows) < PAGE_SIZE:
            return result
        offset += PAGE_SIZE


def _preflight(writer: SupabaseWriter, matches: list[dict]) -> dict:
    registry_rows = _read_all(
        writer,
        "fixture_source_ids",
        "source,source_event_id,fixture_uid",
        {"source": "eq.betwatch"},
    )
    fixture_rows = _read_all(
        writer,
        "fixtures",
        "fixture_uid,match_id_hash,league,home_team,away_team,kickoff_utc",
    )
    result = plan_provider_first_fixture_rows(matches, registry_rows, fixture_rows)
    counts = result["counts"]
    counts_text = ",".join(f"{key}:{counts[key]}" for key in sorted(counts)) or "none"
    print(
        "AUTHORITATIVE_ACTIVATION_PREFLIGHT "
        f"payload_rows={len(matches)} registry_rows={len(registry_rows)} "
        f"fixture_rows={len(fixture_rows)} safe_rows={result['safe_rows']} "
        f"blocking_rows={result['blocking_rows']} counts={counts_text}"
    )
    if result["blocking_rows"]:
        for decision in result["decisions"]:
            if decision.status in ("mapped_exact", "new_fixture", "link_existing_unowned"):
                continue
            print(
                "AUTHORITATIVE_ACTIVATION_BLOCKER "
                f"status={decision.status} event={decision.source_event_id or '-'} "
                f"hash={decision.match_id_hash or '-'} uid={decision.fixture_uid or '-'} "
                f"fixture={decision.league}|{decision.home}|{decision.away}|{decision.kickoff}"
            )
        raise RuntimeError("provider_first_preflight_blocked")
    return result


def _postflight_live_events(writer: SupabaseWriter, matches: list[dict]) -> tuple[int, int]:
    registry_rows = _read_all(
        writer,
        "fixture_source_ids",
        "source,source_event_id,fixture_uid",
        {"source": "eq.betwatch"},
    )
    registry = {
        str(row.get("source_event_id") or "").strip(): str(row.get("fixture_uid") or "").strip()
        for row in registry_rows
        if str(row.get("source_event_id") or "").strip()
    }
    event_ids = {
        str(match.get("match_id") or "").strip()
        for match in matches
        if str(match.get("match_id") or "").strip()
    }
    unresolved = sum(1 for event_id in event_ids if not registry.get(event_id))
    return len(event_ids), unresolved


def main() -> int:
    url, service_key = _require_env()
    writer = SupabaseWriter(url, service_key)

    matches = fetch_prematch(timeout=40)
    if not matches:
        print("AUTHORITATIVE_ACTIVATION_RESULT=FAIL_CLOSED reason=empty_payload")
        return 2

    try:
        _preflight(writer, matches)
    except Exception as exc:
        print(f"AUTHORITATIVE_ACTIVATION_RESULT=FAIL_CLOSED reason={str(exc)[:160]}")
        return 2

    stats = write_provider_authoritative_fixture_batch(writer, matches)
    if stats.get("error"):
        print(
            "AUTHORITATIVE_ACTIVATION_RESULT=FAIL_CLOSED "
            f"reason={stats['error']} received={stats.get('received_count', 0)}"
        )
        return 3

    event_count, unresolved = _postflight_live_events(writer, matches)
    print(
        "AUTHORITATIVE_ACTIVATION_WRITE "
        f"received={stats.get('received_count', 0)} "
        f"mapped={stats.get('mapped_updated_count', 0)} "
        f"linked={stats.get('linked_existing_count', 0)} "
        f"inserted={stats.get('inserted_new_count', 0)} "
        f"live_events={event_count} unresolved_live_events={unresolved}"
    )
    if unresolved:
        print("AUTHORITATIVE_ACTIVATION_RESULT=FAIL_CLOSED reason=postflight_unresolved_live_events")
        return 4

    print("AUTHORITATIVE_ACTIVATION_RESULT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
