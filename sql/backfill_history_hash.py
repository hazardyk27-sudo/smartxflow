#!/usr/bin/env python3
"""Backfill NULL history match_id_hash values using the canonical helper.

This script writes data when executed; it is not run automatically. It exists so
future/manual backfills cannot reintroduce a kickoff-inclusive or locally
normalized hash family.
"""

import os
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.hash_utils import make_match_id_hash

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SERVICE_KEY:
    print("ERROR: SUPABASE_URL ve SUPABASE_SERVICE_ROLE_KEY environment variables gerekli!")
    sys.exit(1)

HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}


def backfill_table(table_name: str) -> int:
    print(f"\n[{table_name}] Backfill başlıyor...")
    page_size = 500
    total_updated = 0

    # Always refetch the first NULL page. Advancing offset while rows leave the
    # NULL result set skips records.
    while True:
        url = (
            f"{SUPABASE_URL}/rest/v1/{table_name}"
            f"?match_id_hash=is.null&select=id,home,away,league,date&limit={page_size}"
        )
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code != 200:
            print(f"  ERROR: {response.status_code} - {response.text[:100]}")
            break

        rows = response.json()
        if not rows:
            break

        updated_this_page = 0
        for row in rows:
            row_id = row.get("id")
            home = row.get("home", "")
            away = row.get("away", "")
            league = row.get("league", "")
            if row_id is None or not home or not away:
                continue

            match_hash = make_match_id_hash(home, away, league, row.get("date", ""))
            update_url = f"{SUPABASE_URL}/rest/v1/{table_name}?id=eq.{row_id}"
            update = requests.patch(
                update_url,
                headers=HEADERS,
                json={"match_id_hash": match_hash},
                timeout=10,
            )
            if update.status_code in (200, 204):
                total_updated += 1
                updated_this_page += 1
            else:
                print(f"    WARN: id={row_id} güncellenemedi: {update.status_code}")

        if updated_this_page == 0:
            print("  WARN: Sayfada hiçbir kayıt güncellenemedi; sonsuz döngüyü önlemek için duruyor.")
            break

    print(f"  [{table_name}] Toplam {total_updated} kayıt güncellendi")
    return total_updated


def main() -> None:
    tables = [
        "moneyway_1x2_history", "moneyway_ou25_history", "moneyway_btts_history",
        "dropping_1x2_history", "dropping_ou25_history", "dropping_btts_history",
    ]
    total = sum(backfill_table(table) for table in tables)
    print(f"\nTOPLAM: {total} kayıt güncellendi")


if __name__ == "__main__":
    main()
