import json
import httpx
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from services.supabase_client import SupabaseClient

db = SupabaseClient()
if not db.url or not db.key:
    print("Supabase credentials not found!")
    sys.exit(1)

HEADERS = {
    "apikey": db.key,
    "Authorization": f"Bearer {db.key}",
    "Content-Type": "application/json"
}

DATE_FROM = "2026-03-09T00:00:00"
DATE_TO = "2026-03-10T00:00:00"

TABLES = {
    "moneyway_1x2": {
        "table": "moneyway_1x2_history",
        "columns": "match_id_hash,league,home,away,date,odds1,oddsx,odds2,pct1,pctx,pct2,amt1,amtx,amt2,volume,scraped_at"
    },
    "moneyway_ou25": {
        "table": "moneyway_ou25_history",
        "columns": "match_id_hash,league,home,away,date,under,over,line,pctunder,pctover,amtunder,amtover,volume,scraped_at"
    },
    "moneyway_btts": {
        "table": "moneyway_btts_history",
        "columns": "match_id_hash,league,home,away,date,yes,no,pctyes,pctno,amtyes,amtno,volume,scraped_at"
    },
    "dropping_1x2": {
        "table": "dropping_1x2_history",
        "columns": "match_id_hash,league,home,away,date,odds1,oddsx,odds2,odds1_prev,oddsx_prev,odds2_prev,trend1,trendx,trend2,volume,scraped_at"
    },
    "dropping_ou25": {
        "table": "dropping_ou25_history",
        "columns": "match_id_hash,league,home,away,date,under,over,line,pctunder,pctover,amtunder,amtover,volume,under_prev,over_prev,scraped_at"
    },
    "dropping_btts": {
        "table": "dropping_btts_history",
        "columns": "match_id_hash,league,home,away,date,oddsyes,oddsyes_prev,oddsno,oddsno_prev,trendyes,trendno,pctyes,amtyes,pctno,amtno,volume,scraped_at"
    }
}

def fetch_all_rows(table_name, columns):
    all_rows = []
    offset = 0
    page_size = 1000
    while True:
        url = (
            f"{db.url}/rest/v1/{table_name}"
            f"?select={columns}"
            f"&scraped_at=gte.{DATE_FROM}"
            f"&scraped_at=lt.{DATE_TO}"
            f"&order=scraped_at.asc"
            f"&offset={offset}&limit={page_size}"
        )
        resp = httpx.get(url, headers=HEADERS, timeout=60)
        if resp.status_code != 200:
            print(f"  ERROR {resp.status_code}: {resp.text[:200]}")
            break
        data = resp.json()
        if not data:
            break
        all_rows.extend(data)
        print(f"  {table_name}: fetched {len(all_rows)} rows...")
        if len(data) < page_size:
            break
        offset += page_size
    return all_rows

matches = {}

for market_key, cfg in TABLES.items():
    print(f"\nFetching {market_key}...")
    rows = fetch_all_rows(cfg["table"], cfg["columns"])
    print(f"  Total: {len(rows)} rows")

    for row in rows:
        mhash = row.get("match_id_hash", "unknown")
        if mhash not in matches:
            matches[mhash] = {
                "match_id_hash": mhash,
                "league": row.get("league", ""),
                "home": row.get("home", ""),
                "away": row.get("away", ""),
                "date": row.get("date", ""),
                "moneyway_1x2": [],
                "moneyway_ou25": [],
                "moneyway_btts": [],
                "dropping_1x2": [],
                "dropping_ou25": [],
                "dropping_btts": []
            }
        else:
            if not matches[mhash]["league"] and row.get("league"):
                matches[mhash]["league"] = row["league"]
            if not matches[mhash]["home"] and row.get("home"):
                matches[mhash]["home"] = row["home"]
            if not matches[mhash]["away"] and row.get("away"):
                matches[mhash]["away"] = row["away"]

        snapshot = {k: v for k, v in row.items() if k not in ("match_id_hash", "league", "home", "away", "date")}
        matches[mhash][market_key].append(snapshot)

for mhash in matches:
    for market_key in TABLES:
        matches[mhash][market_key].sort(key=lambda x: x.get("scraped_at", ""))

output = {
    "export_date": "2026-03-09",
    "total_matches": len(matches),
    "total_snapshots": sum(
        len(m[mk]) for m in matches.values() for mk in TABLES
    ),
    "markets": list(TABLES.keys()),
    "matches": matches
}

out_file = "march9_all_data.json"
with open(out_file, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

file_size_mb = os.path.getsize(out_file) / (1024 * 1024)
print(f"\nDone! File: {out_file}")
print(f"Size: {file_size_mb:.1f} MB")
print(f"Matches: {output['total_matches']}")
print(f"Total snapshots: {output['total_snapshots']}")
