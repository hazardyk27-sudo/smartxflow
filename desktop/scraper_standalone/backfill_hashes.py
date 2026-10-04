#!/usr/bin/env python3
"""Backfill NULL match_id_hash values with the canonical SmartXFlow helper."""

import os
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    import requests as httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from core.hash_utils import make_match_id_hash
except ImportError:
    # Packaged standalone builds expose the same compatibility helper.
    from standalone_scraper import make_match_id_hash


def make_hash(home: str, away: str, league: str) -> str:
    return make_match_id_hash(home, away, league)


def backfill_table(url: str, key: str, table: str):
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    print(f"\n[{table}] Fetching rows with NULL match_id_hash...")
    fetch_url = f"{url}/rest/v1/{table}?match_id_hash=is.null&select=id,home,away,league"
    try:
        resp = httpx.get(fetch_url, headers=headers, timeout=60)
        if resp.status_code != 200:
            print(f"  ERROR: HTTP {resp.status_code} - {resp.text[:200]}")
            return 0

        rows = resp.json()
        print(f"  Found {len(rows)} rows with NULL hash")
        updated = 0
        for row in rows:
            row_id = row.get("id")
            home = row.get("home", "")
            away = row.get("away", "")
            league = row.get("league", "")
            if not row_id or not home or not away:
                continue

            new_hash = make_hash(home, away, league)
            update_resp = httpx.patch(
                f"{url}/rest/v1/{table}?id=eq.{row_id}",
                headers=headers,
                json={"match_id_hash": new_hash},
                timeout=30,
            )
            if update_resp.status_code in (200, 204):
                updated += 1
            else:
                print(f"  WARN: Failed to update id={row_id}: HTTP {update_resp.status_code}")

        print(f"  Updated {updated}/{len(rows)} rows")
        return updated
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return 0


def main():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_ANON_KEY environment variables required")
        sys.exit(1)

    tables = [
        "dropping_1x2_history", "dropping_ou25_history", "dropping_btts_history",
        "moneyway_1x2_history", "moneyway_ou25_history", "moneyway_btts_history",
    ]
    total = sum(backfill_table(url, key, table) for table in tables)
    print(f"\nBACKFILL COMPLETE: {total} total rows updated")


if __name__ == "__main__":
    main()
