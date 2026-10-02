#!/usr/bin/env python3
"""Read-only audit for fixture/history match identity consistency.

Never prints credentials. Defaults to fixtures only; use the canonical
core.hash_utils contract and report mismatches that would break exact-hash V2
settlement.
"""

import argparse
import os
from collections import Counter

import requests

from core.hash_utils import make_match_id_hash


def _headers(key):
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }


def _fetch_all(url, headers, table, page_size=1000):
    rows = []
    offset = 0
    while True:
        r = requests.get(
            f"{url.rstrip('/')}/rest/v1/{table}?select=*&limit={page_size}&offset={offset}",
            headers=headers,
            timeout=30,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit-samples", type=int, default=25)
    args = ap.parse_args()

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not key:
        raise SystemExit("SUPABASE_URL and a Supabase read key are required")

    fixtures = _fetch_all(url, _headers(key), "fixtures")
    mismatches = []
    expected_counts = Counter()

    for row in fixtures:
        actual = str(row.get("match_id_hash") or "").strip().lower()
        expected = make_match_id_hash(
            row.get("home_team", ""),
            row.get("away_team", ""),
            row.get("league", ""),
        )
        expected_counts[expected] += 1
        if actual != expected:
            mismatches.append((row, actual, expected))

    collisions = {h: n for h, n in expected_counts.items() if n > 1}

    print(f"fixtures={len(fixtures)}")
    print(f"hash_mismatch={len(mismatches)}")
    print(f"canonical_collisions={len(collisions)}")

    for row, actual, expected in mismatches[: args.limit_samples]:
        print(
            "MISMATCH"
            f" | {row.get('home_team','')}"
            f" | {row.get('away_team','')}"
            f" | {row.get('league','')}"
            f" | actual={actual}"
            f" | expected={expected}"
        )

    if collisions:
        for h, n in list(collisions.items())[: args.limit_samples]:
            print(f"COLLISION | {h} | rows={n}")


if __name__ == "__main__":
    main()
