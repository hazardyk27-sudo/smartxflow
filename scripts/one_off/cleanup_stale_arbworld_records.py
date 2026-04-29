#!/usr/bin/env python3
"""
Task #159 — Eski Arbworld kayıtlarını temizle

Arbworld JSON API'ye geçişten sonra (2026-04-29 ~18:20 UTC), eski HTML scraper'ın
kısa-adlı (örn "Atletico Ma" vs yeni "Atletico Madrid") stale Supabase kayıtları
duplicate satırlar oluşturuyor. Bu script eski kayıtları siler.

Şema gerçeği (önemli):
  - Ana market tabloları (moneyway_*, dropping_*): id, league, date, home, away,
    odds*, pct*, amt*, volume — `scraped_at` YOK, `match_id_hash` YOK.
  - History tabloları (moneyway_*_history, dropping_*_history): yukarıdakilere
    ek olarak `scraped_at` ve `match_id_hash` var.
  - Snapshot tabloları (moneyway_snapshots, dropping_odds_snapshots): match_id_hash,
    market, selection, odds, volume, share, scraped_at_utc.
  - fixtures: match_id_hash unique key + home_team/away_team/league/kickoff_utc/fixture_date.

Strateji:
  1) History tablolarından "stale_hashes" hesapla:
       - pre_cutoff: scraped_at < CUTOFF olan hash'ler (eski HTML scraper döneminde
         yazılmış)
       - post_cutoff: scraped_at >= CUTOFF olan hash'ler (yeni JSON scraper aktif)
       - stale_hashes = pre_cutoff - post_cutoff
       (Yeni JSON aynı maçı farklı isimle yazdığı için, eski hash artık yeni
       scraper turlarında görünmüyor.)
  2) Ana market tablolarını sayfalı tara, her satır için (home, away, league) →
     match_id_hash hesapla. Stale ise id'sini topla.
  3) Snapshot tablolarından stale_hashes'a ait kayıtları sil
     (defansif: scraped_at_utc < CUTOFF).
  4) History tablolarından stale_hashes'a ait kayıtları sil
     (defansif: scraped_at < CUTOFF).
  5) Ana market tablolarından id batch ile sil.
  6) Fixtures'tan stale_hashes'a ait kayıtları sil (tanım gereği post-cutoff
     hiç yazılmadığı için yetim).

Kullanım:
  python scripts/one_off/cleanup_stale_arbworld_records.py --dry-run
  python scripts/one_off/cleanup_stale_arbworld_records.py --execute
"""

import argparse
import os
import sys
from typing import Dict, List, Set

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.hash_utils import make_match_id_hash  # noqa: E402

# History tablolarında scraped_at TR-tz string olarak saklanıyor ("...+03:00").
# Snapshot tablolarında scraped_at_utc UTC string olarak saklanıyor ("...+00:00").
# PostgREST text kolonlar üzerinde lex (string) karşılaştırması yapar — ikisini de
# uygun lex-doğru formatta tutmamız gerek.
# Yeni JSON scraper 18:20 UTC = 21:20 TR civarı çalışmaya başladı.
# Eski HTML scraper son yazma 17:47 TR = 14:47 UTC.
CUTOFF_HISTORY_TR = "2026-04-29T20:45:00"  # 20:45 TR = 17:45 UTC (lex-doğru, history için)
CUTOFF_SNAPSHOT_UTC = "2026-04-29T17:45:00"  # 17:45 UTC (lex-doğru, snapshot_utc için)

MARKET_TABLES = [
    "moneyway_1x2",
    "moneyway_ou25",
    "moneyway_btts",
    "dropping_1x2",
    "dropping_ou25",
    "dropping_btts",
]

HISTORY_TABLES = [
    "moneyway_1x2_history",
    "moneyway_ou25_history",
    "moneyway_btts_history",
    "dropping_1x2_history",
    "dropping_ou25_history",
    "dropping_btts_history",
]

SNAPSHOT_TABLES = ["moneyway_snapshots", "dropping_odds_snapshots"]

PAGE_SIZE = 10000
DELETE_BATCH = 80  # PostgREST URL uzunluğu sınırı için güvenli


def _h(key: str) -> Dict[str, str]:
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def _rest(base: str, table: str) -> str:
    return f"{base.rstrip('/')}/rest/v1/{table}"


def collect_history_hashes(
    base: str, key: str, table: str, op: str
) -> Set[str]:
    """History tablosundaki hash'leri sayfalı çek.

    op: 'lt' (pre_cutoff) veya 'gte' (post_cutoff)
    """
    out: Set[str] = set()
    offset = 0
    while True:
        params = {
            "select": "match_id_hash",
            "scraped_at": f"{op}.{CUTOFF_HISTORY_TR}",
            "order": "match_id_hash.asc",
            "limit": str(PAGE_SIZE),
            "offset": str(offset),
        }
        r = requests.get(_rest(base, table), headers=_h(key), params=params, timeout=60)
        if r.status_code != 200:
            print(f"  [WARN] {table} {op} GET HTTP {r.status_code}: {r.text[:200]}")
            return out
        page = r.json()
        if not page:
            break
        for row in page:
            h = row.get("match_id_hash")
            if h:
                out.add(h)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return out


def scan_market_table_for_stale_ids(
    base: str, key: str, table: str, stale_hashes: Set[str]
) -> List[int]:
    """Ana market tablosunu tara, hash'i stale_hashes'ta olan satırların id'sini topla."""
    ids: List[int] = []
    offset = 0
    while True:
        params = {
            "select": "id,home,away,league",
            "order": "id.asc",
            "limit": str(PAGE_SIZE),
            "offset": str(offset),
        }
        r = requests.get(_rest(base, table), headers=_h(key), params=params, timeout=60)
        if r.status_code != 200:
            print(f"  [WARN] {table} scan GET HTTP {r.status_code}: {r.text[:200]}")
            return ids
        page = r.json()
        if not page:
            break
        for row in page:
            rid = row.get("id")
            if rid is None:
                continue
            h = make_match_id_hash(
                str(row.get("home") or ""),
                str(row.get("away") or ""),
                str(row.get("league") or ""),
            )
            if h in stale_hashes:
                ids.append(int(rid))
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return ids


def delete_by_ids(
    base: str, key: str, table: str, ids: List[int], dry_run: bool
) -> int:
    if not ids:
        return 0
    if dry_run:
        return len(ids)
    deleted = 0
    for i in range(0, len(ids), DELETE_BATCH):
        batch = ids[i : i + DELETE_BATCH]
        ids_str = ",".join(str(x) for x in batch)
        url = f"{_rest(base, table)}?id=in.({ids_str})"
        r = requests.delete(url, headers=_h(key), timeout=60)
        if r.status_code not in (200, 204):
            print(
                f"  [WARN] {table} id-batch DELETE HTTP {r.status_code}: {r.text[:200]}"
            )
            continue
        deleted += len(batch)
    return deleted


def count_by_hashes(
    base: str,
    key: str,
    table: str,
    hashes: List[str],
    extra_params: Dict[str, str] | None = None,
) -> int:
    """DRY-RUN için: hash listesine uyan satır sayısını döner."""
    if not hashes:
        return 0
    total = 0
    for i in range(0, len(hashes), DELETE_BATCH):
        batch = hashes[i : i + DELETE_BATCH]
        params = {
            "select": "match_id_hash",
            "match_id_hash": f"in.({','.join(batch)})",
            "limit": str(PAGE_SIZE * 10),
        }
        if extra_params:
            params.update(extra_params)
        r = requests.get(_rest(base, table), headers=_h(key), params=params, timeout=60)
        if r.status_code != 200:
            print(f"  [WARN] {table} count GET HTTP {r.status_code}: {r.text[:200]}")
            continue
        try:
            total += len(r.json())
        except Exception:
            pass
    return total


def delete_by_hashes(
    base: str,
    key: str,
    table: str,
    hashes: List[str],
    extra_params: Dict[str, str] | None = None,
) -> int:
    if not hashes:
        return 0
    deleted = 0
    for i in range(0, len(hashes), DELETE_BATCH):
        batch = hashes[i : i + DELETE_BATCH]
        params = {"match_id_hash": f"in.({','.join(batch)})"}
        if extra_params:
            params.update(extra_params)
        r = requests.delete(_rest(base, table), headers=_h(key), params=params, timeout=60)
        if r.status_code not in (200, 204):
            print(
                f"  [WARN] {table} hash-batch DELETE HTTP {r.status_code}: {r.text[:200]}"
            )
            continue
        deleted += len(batch)
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    base = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_ANON_KEY")
    if not base or not key:
        print("[FATAL] SUPABASE_URL veya SUPABASE_ANON_KEY env yok!")
        return 2

    mode = "DRY-RUN" if args.dry_run else "EXECUTE"
    print(f"=== Cleanup Stale Arbworld Records — {mode} ===")
    print(f"Cutoff (history TR): {CUTOFF_HISTORY_TR}  |  Cutoff (snapshot UTC): {CUTOFF_SNAPSHOT_UTC}")
    print(f"Supabase: {base}")
    print()

    # 1) Stale hash'leri history tablolarından hesapla
    print("[1/5] History'den stale_hashes hesaplanıyor...")
    pre_cutoff: Set[str] = set()
    post_cutoff: Set[str] = set()
    for table in HISTORY_TABLES:
        pre = collect_history_hashes(base, key, table, "lt")
        post = collect_history_hashes(base, key, table, "gte")
        pre_cutoff |= pre
        post_cutoff |= post
        print(f"  {table}: pre={len(pre)}, post={len(post)}")
    stale_hashes = pre_cutoff - post_cutoff
    print(f"  TOPLAM: pre={len(pre_cutoff)}, post={len(post_cutoff)}, "
          f"stale={len(stale_hashes)}")
    print()

    if not stale_hashes:
        print("[OK] Stale hash yok, hiçbir şey yapılmadı.")
        return 0

    sorted_stale = sorted(stale_hashes)

    # 2) Ana market tablolarını tara, stale id'leri topla
    print("[2/5] Ana market tablolarında stale id'ler taranıyor...")
    market_stale_ids: Dict[str, List[int]] = {}
    for table in MARKET_TABLES:
        ids = scan_market_table_for_stale_ids(base, key, table, stale_hashes)
        market_stale_ids[table] = ids
        print(f"  {table}: {len(ids)} stale id")
    total_market_ids = sum(len(v) for v in market_stale_ids.values())
    print(f"  TOPLAM: {total_market_ids} satır")
    print()

    # 3) Snapshot tablolarından sil
    print("[3/5] Snapshot tabloları (scraped_at_utc < cutoff & stale hash)...")
    snap_extra = {"scraped_at_utc": f"lt.{CUTOFF_SNAPSHOT_UTC}"}
    for table in SNAPSHOT_TABLES:
        if args.dry_run:
            n = count_by_hashes(base, key, table, sorted_stale, snap_extra)
            print(f"  {table}: {n} satır silinecek")
        else:
            n = delete_by_hashes(base, key, table, sorted_stale, snap_extra)
            print(f"  {table}: ~{n} satır silindi (batch sayısı * batch size)")
    print()

    # 4) History tablolarından sil
    print("[4/5] History tabloları (scraped_at < cutoff & stale hash)...")
    hist_extra = {"scraped_at": f"lt.{CUTOFF_HISTORY_TR}"}
    for table in HISTORY_TABLES:
        if args.dry_run:
            n = count_by_hashes(base, key, table, sorted_stale, hist_extra)
            print(f"  {table}: {n} satır silinecek")
        else:
            n = delete_by_hashes(base, key, table, sorted_stale, hist_extra)
            print(f"  {table}: ~{n} satır silindi")
    print()

    # 5) Ana market tablolarından id ile sil + fixtures
    print("[5/5] Ana market tabloları (id batch)...")
    for table in MARKET_TABLES:
        ids = market_stale_ids[table]
        n = delete_by_ids(base, key, table, ids, args.dry_run)
        verb = "silinecek" if args.dry_run else "silindi"
        print(f"  {table}: {n} satır {verb}")

    print()
    print("[5b] Fixtures (yetim stale hash)...")
    if args.dry_run:
        n_fix = count_by_hashes(base, key, "fixtures", sorted_stale)
        print(f"  fixtures: {n_fix} satır silinecek")
    else:
        n_fix = delete_by_hashes(base, key, "fixtures", sorted_stale)
        print(f"  fixtures: ~{n_fix} satır silindi")

    print()
    print("=== TAMAMLANDI ===")
    if args.dry_run:
        print("DRY-RUN: hiçbir kayıt silinmedi. Gerçek silme için --execute kullan.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
