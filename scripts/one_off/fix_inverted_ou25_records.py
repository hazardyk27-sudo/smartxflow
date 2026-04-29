#!/usr/bin/env python3
"""
Task #160 — Eski yanlış OU25 Üst/Alt değerlerini düzelt (one-off).

Arbworld JSON migrasyonunda (commit 2ddd758, 2026-04-29 18:22:28 UTC) OU25 (Over/
Under 2.5) market'i için Over↔Under eşlemesi ters yazıldı. Hata fix commit
d7eb60a (2026-04-29 19:18:52 UTC) ile düzeltildi. Bu pencerede yazılan satırlar
(2026-04-29 18:20–19:43 UTC ≈ 21:20–22:43 TR) hâlâ ters Üst/Alt verisi taşıyor.

Etkilenen tablolar:
  - moneyway_ou25_history : sütun değerleri swap'lanır
                            (over↔under, pctover↔pctunder, amtover↔amtunder)
  - dropping_ou25_history : aynı (volume tek alan, dokunulmaz)
  - moneyway_snapshots (market='OU25') : selection 'O'↔'U' relabel
                            (odds/share/volume değerleri zaten karşı tarafa ait,
                            sadece etiket terstir)

Şema gerçekleri (önemli):
  - History tabloları: id YOK; composite (match_id_hash, scraped_at) ile satır
    tekilleştirilir. scraped_at TR-tz string ('+03:00').
  - moneyway_snapshots: id SERIAL PRIMARY KEY var; scraped_at_utc UTC ('+00:00').
  - Bug penceresinde dropping_odds_snapshots'a YAZILMAZ (standalone scraper
    yalnız moneyway_snapshots üretir), o tablo etkilenmez.

Bug penceresi (konservatif):
  - History TR  : 2026-04-29T21:00:00+03:00  →  2026-04-29T23:00:00+03:00
  - Snapshot UTC: 2026-04-29T18:00:00+00:00  →  2026-04-29T20:00:00+00:00
  Migrasyondan önce (eski HTML scraper) ve fix sonrası (henüz scraper restart
  edilmediği için satır yok) bu pencereye düşmez.

İdempotans uyarısı:
  Swap simetrik bir işlem; bu script'i ikinci kez --execute ile çalıştırmak
  satırları orijinal (yanlış) hâline geri çevirir. Tek seferlik çalıştır.

Kullanım:
  python scripts/one_off/fix_inverted_ou25_records.py --dry-run
  python scripts/one_off/fix_inverted_ou25_records.py --execute
"""

import argparse
import os
import sys
from typing import Dict, List, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from services.supabase_client import SupabaseClient  # noqa: E402

BUG_START_TR  = "2026-04-29T21:00:00+03:00"
BUG_END_TR    = "2026-04-29T23:00:00+03:00"
BUG_START_UTC = "2026-04-29T18:00:00+00:00"
BUG_END_UTC   = "2026-04-29T20:00:00+00:00"

HISTORY_TABLES = ["moneyway_ou25_history", "dropping_ou25_history"]
SNAPSHOT_TABLE = "moneyway_snapshots"

PAGE_SIZE = 5000
PATCH_IDS_BATCH = 100
SAMPLE_LIMIT = 5

# Sütun çiftleri: history satırında swap'lanacak alanlar.
HISTORY_SWAP_FIELDS: List[Tuple[str, str]] = [
    ("over", "under"),
    ("pctover", "pctunder"),
    ("amtover", "amtunder"),
]


# ---------- HTTP helpers ----------

class Rest:
    def __init__(self, client: SupabaseClient):
        self.client = client
        self.http = client._get_http_client()
        self.base_headers = client._headers()

    def url(self, table: str) -> str:
        return self.client._rest_url(table)

    def get(self, table, params, extra_headers=None):
        h = dict(self.base_headers)
        if extra_headers:
            h.update(extra_headers)
        return self.http.get(self.url(table), headers=h, params=params, timeout=60)

    def patch(self, table, params, body):
        h = dict(self.base_headers)
        h["Prefer"] = "return=minimal"
        return self.http.patch(
            self.url(table), headers=h, params=params, json=body, timeout=60
        )


# ---------- History fix ----------

def fetch_history_rows(rest: Rest, table: str) -> List[Dict]:
    """Bug penceresindeki tüm OU25 history satırlarını çek."""
    select_cols = ",".join(["match_id_hash", "scraped_at", "home", "away", "league"]
                            + [f for pair in HISTORY_SWAP_FIELDS for f in pair])
    all_rows: List[Dict] = []
    offset = 0
    while True:
        params = [
            ("select", select_cols),
            ("scraped_at", f"gte.{BUG_START_TR}"),
            ("scraped_at", f"lt.{BUG_END_TR}"),
            ("order", "scraped_at.asc,match_id_hash.asc"),
            ("limit", str(PAGE_SIZE)),
            ("offset", str(offset)),
        ]
        r = rest.get(table, params)
        if r.status_code != 200:
            print(f"  [WARN] {table} GET HTTP {r.status_code}: {r.text[:200]}")
            return all_rows
        page = r.json()
        if not page:
            break
        all_rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return all_rows


def patch_history_row(rest: Rest, table: str, row: Dict) -> Tuple[int, str]:
    """Tek satırı (match_id_hash, scraped_at) ile bul ve over↔under swap'la."""
    body = {}
    for a, b in HISTORY_SWAP_FIELDS:
        body[a] = row.get(b)
        body[b] = row.get(a)
    params = [
        ("match_id_hash", f"eq.{row['match_id_hash']}"),
        ("scraped_at",    f"eq.{row['scraped_at']}"),
    ]
    r = rest.patch(table, params, body)
    return r.status_code, (r.text or "")[:200]


def fix_history_table(rest: Rest, table: str, dry_run: bool) -> None:
    print(f"[HISTORY] {table} taranıyor (window: {BUG_START_TR} → {BUG_END_TR})...")
    rows = fetch_history_rows(rest, table)
    print(f"  bulunan: {len(rows)} satır")
    if not rows:
        return

    print(f"  [SAMPLE] ilk {min(SAMPLE_LIMIT, len(rows))} satır (öncesi):")
    for r in rows[:SAMPLE_LIMIT]:
        print(
            f"    hash={r['match_id_hash']}  scraped_at={r['scraped_at']}  "
            f"home={r.get('home')!r} away={r.get('away')!r}  "
            f"over={r.get('over')!r} under={r.get('under')!r}  "
            f"pct=O:{r.get('pctover')!r}/U:{r.get('pctunder')!r}  "
            f"amt=O:{r.get('amtover')!r}/U:{r.get('amtunder')!r}"
        )

    if dry_run:
        print(f"  [DRY-RUN] {len(rows)} satır PATCH edilecek (her biri swap).")
        return

    ok = 0
    fail = 0
    for i, row in enumerate(rows, 1):
        status, body = patch_history_row(rest, table, row)
        if status in (200, 204):
            ok += 1
        else:
            fail += 1
            if fail <= 5:
                print(f"  [PATCH ERR] hash={row['match_id_hash']} "
                      f"scraped_at={row['scraped_at']} HTTP {status}: {body}")
        if i % 100 == 0:
            print(f"  ...{i}/{len(rows)} (ok={ok}, fail={fail})")
    print(f"  [{table}] PATCH tamam: ok={ok}  fail={fail}")


# ---------- Snapshot fix (selection relabel) ----------

def fetch_snapshot_ids_by_selection(rest: Rest, selection: str) -> List[int]:
    """OU25 snapshot satırlarının id'lerini selection'a göre topla."""
    ids: List[int] = []
    offset = 0
    while True:
        params = [
            ("select", "id"),
            ("market", "eq.OU25"),
            ("selection", f"eq.{selection}"),
            ("scraped_at_utc", f"gte.{BUG_START_UTC}"),
            ("scraped_at_utc", f"lt.{BUG_END_UTC}"),
            ("order", "id.asc"),
            ("limit", str(PAGE_SIZE)),
            ("offset", str(offset)),
        ]
        r = rest.get(SNAPSHOT_TABLE, params)
        if r.status_code != 200:
            print(f"  [WARN] {SNAPSHOT_TABLE} GET HTTP {r.status_code}: {r.text[:200]}")
            return ids
        page = r.json()
        if not page:
            break
        ids.extend(int(x["id"]) for x in page if x.get("id") is not None)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return ids


def patch_snapshot_ids(rest: Rest, ids: List[int], new_selection: str) -> Tuple[int, int]:
    """ids'i batch'leyip selection'ı new_selection olarak set et."""
    ok = 0
    fail = 0
    for i in range(0, len(ids), PATCH_IDS_BATCH):
        batch = ids[i:i + PATCH_IDS_BATCH]
        params = [("id", f"in.({','.join(str(x) for x in batch)})")]
        r = rest.patch(SNAPSHOT_TABLE, params, {"selection": new_selection})
        if r.status_code in (200, 204):
            ok += len(batch)
        else:
            fail += len(batch)
            print(f"  [PATCH ERR] batch[{i}:{i+len(batch)}] HTTP {r.status_code}: "
                  f"{(r.text or '')[:200]}")
    return ok, fail


def fix_snapshots(rest: Rest, dry_run: bool) -> None:
    print(f"[SNAPSHOT] {SNAPSHOT_TABLE} OU25 (window: {BUG_START_UTC} → {BUG_END_UTC})...")
    ids_o = fetch_snapshot_ids_by_selection(rest, "O")
    ids_u = fetch_snapshot_ids_by_selection(rest, "U")
    overlap = set(ids_o) & set(ids_u)
    print(f"  selection='O': {len(ids_o)} id  |  selection='U': {len(ids_u)} id  "
          f"|  overlap: {len(overlap)} (0 olmalı)")
    if overlap:
        print("  [FATAL] id örtüşmesi var, swap yapılamaz, çıkılıyor.")
        return

    if dry_run:
        print(f"  [DRY-RUN] {len(ids_o)} 'O' satırı 'U' olacak, "
              f"{len(ids_u)} 'U' satırı 'O' olacak.")
        return

    # Step 1: 'O' (Under verisi taşıyan) → 'U'
    ok1, fail1 = patch_snapshot_ids(rest, ids_o, "U")
    print(f"  [STEP 1] 'O' → 'U' : ok={ok1}  fail={fail1}")
    # Step 2: 'U' (Over verisi taşıyan) → 'O'
    ok2, fail2 = patch_snapshot_ids(rest, ids_u, "O")
    print(f"  [STEP 2] 'U' → 'O' : ok={ok2}  fail={fail2}")


# ---------- Main ----------

def main() -> int:
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    has_url = bool(os.environ.get("SUPABASE_URL"))
    has_key = bool(os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_KEY"))
    if not (has_url and has_key):
        print("[WARN] SUPABASE_URL veya SUPABASE_ANON_KEY/SUPABASE_KEY env eksik — "
              "SupabaseClient embedded fallback denenecek.")

    try:
        client = SupabaseClient()
    except Exception as e:
        print(f"[FATAL] SupabaseClient kurulamadı: {e}")
        return 2
    rest = Rest(client)

    mode = "DRY-RUN" if args.dry_run else "EXECUTE"
    print(f"=== Fix Inverted OU25 Records — {mode} ===")
    print(f"Supabase: {client.url}")
    print(f"Bug window TR : {BUG_START_TR} → {BUG_END_TR}")
    print(f"Bug window UTC: {BUG_START_UTC} → {BUG_END_UTC}")
    print()

    if not args.dry_run:
        print("!!! UYARI: Swap simetrik bir işlem. Bu script ikinci kez çalıştırılırsa")
        print("!!! satırları yine ters çevirir. Lütfen tek seferlik çalıştırın.")
        print()

    for table in HISTORY_TABLES:
        fix_history_table(rest, table, args.dry_run)
        print()

    fix_snapshots(rest, args.dry_run)
    print()

    print("=== TAMAMLANDI ===")
    if args.dry_run:
        print("DRY-RUN: hiçbir kayıt değiştirilmedi. Gerçek için --execute kullan.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
