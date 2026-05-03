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
    "Authorization": "Bearer " + db.key,
    "Content-Type": "application/json"
}

DATE_FROM = "2026-03-10T00:00:00"
DATE_TO = "2026-03-11T00:00:00"

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
            db.url + "/rest/v1/" + table_name
            + "?select=" + columns
            + "&scraped_at=gte." + DATE_FROM
            + "&scraped_at=lt." + DATE_TO
            + "&order=scraped_at.asc"
            + "&offset=" + str(offset) + "&limit=" + str(page_size)
        )
        resp = httpx.get(url, headers=HEADERS, timeout=60)
        if resp.status_code != 200:
            print("  ERROR " + str(resp.status_code) + ": " + resp.text[:200])
            break
        data = resp.json()
        if not data:
            break
        all_rows.extend(data)
        if len(all_rows) % 5000 == 0 or len(data) < page_size:
            print("  " + table_name + ": " + str(len(all_rows)) + " rows...")
        if len(data) < page_size:
            break
        offset += page_size
    return all_rows

matches = {}
market_keys = list(TABLES.keys())

for market_key in market_keys:
    cfg = TABLES[market_key]
    print("Fetching " + market_key + "...")
    rows = fetch_all_rows(cfg["table"], cfg["columns"])
    print("  Total: " + str(len(rows)) + " rows")

    for row in rows:
        mhash = row.get("match_id_hash", "unknown")
        if mhash not in matches:
            matches[mhash] = {
                "league": row.get("league", ""),
                "home": row.get("home", ""),
                "away": row.get("away", ""),
                "date": row.get("date", ""),
            }
            for mk in market_keys:
                matches[mhash][mk] = []
        snapshot = {}
        for k, v in row.items():
            if k not in ("match_id_hash", "league", "home", "away", "date") and v is not None:
                snapshot[k] = v
        matches[mhash][market_key].append(snapshot)

for mhash in matches:
    for mk in market_keys:
        matches[mhash][mk].sort(key=lambda x: x.get("scraped_at", ""))

total_snapshots = 0
for m in matches.values():
    for mk in market_keys:
        total_snapshots += len(m[mk])

print("\nWriting text file...")
with open("march10_all_data.txt", "w", encoding="utf-8") as out:
    out.write("=== 10 MART 2026 - TUM MAC VERILERI ===\n")
    out.write("Toplam Mac: " + str(len(matches)) + "\n")
    out.write("Toplam Snapshot: " + str(total_snapshots) + "\n")
    out.write("Pazarlar: " + ", ".join(market_keys) + "\n")
    out.write("=" * 80 + "\n\n")

    for mhash, m in matches.items():
        out.write("=" * 80 + "\n")
        out.write("MAC: " + m["home"] + " vs " + m["away"] + "\n")
        out.write("LIG: " + m["league"] + "\n")
        out.write("TARIH: " + m["date"] + "\n")
        out.write("ID: " + mhash + "\n")
        out.write("-" * 80 + "\n")

        for mk in market_keys:
            snapshots = m[mk]
            if not snapshots:
                continue
            out.write("\n  [" + mk.upper() + "] (" + str(len(snapshots)) + " snapshot)\n")
            out.write("  " + "-" * 60 + "\n")
            for s in snapshots:
                ts = s.get("scraped_at", "")
                parts = []
                for k, v in s.items():
                    if k != "scraped_at":
                        parts.append(k + "=" + str(v))
                out.write("  " + ts + " | " + " | ".join(parts) + "\n")

        out.write("\n")

size_mb = os.path.getsize("march10_all_data.txt") / (1024 * 1024)
print("Done! march10_all_data.txt - " + "{:.1f}".format(size_mb) + " MB")
print("Matches: " + str(len(matches)))
print("Snapshots: " + str(total_snapshots))
