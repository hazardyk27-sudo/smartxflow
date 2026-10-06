#!/usr/bin/env python3
"""Read-only Fixture Identity V2 Part 6 provider-first writer preflight.

The script fetches one live Betwatch prematch payload plus existing fixture/provider
rows, then classifies every event in memory. It does not POST/PATCH/DELETE and does
not flush the staged shadow registry batch created by the Betwatch client.
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
from core.fixture_uid_writer_preflight import plan_provider_first_fixture_rows  # noqa: E402
from standalone_scraper import SupabaseWriter  # noqa: E402

PAGE_SIZE = 1000


def _require_env() -> tuple[str, str]:
    url = (os.environ.get("SUPABASE_URL") or "").strip()
    service_key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url:
        raise SystemExit("SUPABASE_URL missing")
    if not service_key:
        raise SystemExit("SUPABASE_SERVICE_ROLE_KEY missing; preflight refuses anon fallback")
    if not (os.environ.get("Betwach_api_key") or "").strip():
        raise SystemExit("Betwach_api_key missing")
    return url, service_key


def _read_all(writer: SupabaseWriter, table: str, select: str, extra: Dict[str, str] | None = None) -> List[dict]:
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


def main() -> int:
    url, service_key = _require_env()
    writer = SupabaseWriter(url, service_key)

    matches = fetch_prematch(timeout=40)
    if not matches:
        print("WRITER_PREFLIGHT_RESULT=FAIL_CLOSED reason=empty_payload")
        return 2

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
        "WRITER_PREFLIGHT "
        f"payload_rows={len(matches)} registry_rows={len(registry_rows)} "
        f"fixture_rows={len(fixture_rows)} safe_rows={result['safe_rows']} "
        f"blocking_rows={result['blocking_rows']} counts={counts_text}"
    )

    blockers = [d for d in result["decisions"] if d.status not in ("mapped_exact", "new_fixture", "link_existing_unowned")]
    for decision in blockers[:20]:
        print(
            "WRITER_PREFLIGHT_BLOCKER "
            f"status={decision.status} event={decision.source_event_id or '-'} "
            f"hash={decision.match_id_hash or '-'} uid={decision.fixture_uid or '-'} "
            f"fixture={decision.league}|{decision.home}|{decision.away}|{decision.kickoff}"
        )

    if result["blocking_rows"]:
        print("WRITER_PREFLIGHT_RESULT=FAIL_CLOSED")
        return 2

    print("WRITER_PREFLIGHT_RESULT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
