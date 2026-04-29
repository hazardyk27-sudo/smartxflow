#!/usr/bin/env python3
"""
Task #159 — Eski Arbworld kayıtlarını temizle (one-off).

Arbworld JSON API'ye geçişten sonra (2026-04-29 ~18:20 UTC), eski HTML scraper'ın
kısa-adlı (örn "Atletico Ma" vs yeni "Atletico Madrid") stale Supabase kayıtları
6 ana market tablosunda farklı match_id_hash üreterek duplicate satırlara yol
açtı. Bu script eski kayıtları temizler.

Şema gerçeği (önemli):
  - Ana market tabloları (moneyway_*, dropping_*): id, league, date, home, away,
    odds*, pct*, amt*, volume — `scraped_at` YOK, `match_id_hash` YOK.
  - History tabloları (moneyway_*_history, dropping_*_history): yukarıdakilere
    ek olarak `scraped_at` (TR-tz string "+03:00") ve `match_id_hash` var.
  - Snapshot tabloları (moneyway_snapshots, dropping_odds_snapshots): match_id_hash,
    market, selection, odds, volume, share, scraped_at_utc (UTC string "+00:00").
  - fixtures: match_id_hash unique key + home_team/away_team/league/kickoff_utc.

PostgREST text kolonlar üzerinde lex (string) karşılaştırması yapar — cutoff
string'i kolonun tz formatına uymalı:
  - history.scraped_at → TR-tz cutoff (20:45 TR = 17:45 UTC)
  - snapshot.scraped_at_utc → UTC cutoff (17:45 UTC)

Strateji (KONSERVATİF — over-deletion'ı önler):
  1) Pre-cutoff history hash'lerini topla (sadece hash + home + away + league + date).
  2) Post-cutoff history hash'lerini topla (aynı şekilde).
  3) "Narrowed stale": pre_cutoff'ta var, post_cutoff'ta YOK olan hash'lerden
     SADECE replacement adayı bulunanlar. Replacement testi: (away_norm[:8],
     league_norm[:8], kickoff_yyyymmdd) tuple'ı post_cutoff'ta farklı bir hash
     ile mevcut. Bu, "isim değişti, hash değişti, ama aynı maç" durumunu yakalar.
     Bu testin amacı: cutoff öncesi sadece tek sefer yazılmış geçmiş/test maçlarını
     STALE OLARAK İŞARETLEMEMEK (over-deletion önlenir).
  4) Sırasıyla sil:
       a) snapshots (scraped_at_utc < CUTOFF_SNAPSHOT)
       b) history (scraped_at < CUTOFF_HISTORY)
       c) ana market tabloları (id batch — taranıp hash'i stale olanların id'si)
       d) fixtures (match_id_hash in stale_set)
  5) Her DELETE için PostgREST `Prefer: count=exact` ile gerçek silinen satır
     sayısı Content-Range header'dan okunur ve raporlanır.

Kullanım:
  python scripts/one_off/cleanup_stale_arbworld_records.py --dry-run
  python scripts/one_off/cleanup_stale_arbworld_records.py --execute
"""

import argparse
import os
import re
import sys
from typing import Dict, List, Set, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.hash_utils import make_match_id_hash, normalize_field  # noqa: E402
from services.supabase_client import SupabaseClient  # noqa: E402

CUTOFF_HISTORY_TR = "2026-04-29T20:45:00"   # 20:45 TR = 17:45 UTC (lex-doğru, history)
CUTOFF_SNAPSHOT_UTC = "2026-04-29T17:45:00"  # 17:45 UTC (lex-doğru, snapshot_utc)

MARKET_TABLES = [
    "moneyway_1x2", "moneyway_ou25", "moneyway_btts",
    "dropping_1x2", "dropping_ou25", "dropping_btts",
]
HISTORY_TABLES = [t + "_history" for t in MARKET_TABLES]
SNAPSHOT_TABLES = ["moneyway_snapshots", "dropping_odds_snapshots"]

PAGE_SIZE = 10000
DELETE_BATCH = 80
SAMPLE_LIMIT = 20


# ---------- HTTP helpers (SupabaseClient REST primitives) ----------

class Rest:
    def __init__(self, client: SupabaseClient):
        self.client = client
        self.http = client._get_http_client()
        self.base_headers = client._headers()

    def url(self, table: str) -> str:
        return self.client._rest_url(table)

    def get(self, table: str, params: Dict[str, str], extra_headers: Dict[str, str] | None = None):
        h = dict(self.base_headers)
        if extra_headers:
            h.update(extra_headers)
        return self.http.get(self.url(table), headers=h, params=params, timeout=60)

    def delete_with_count(self, table: str, params: Dict[str, str]) -> Tuple[int, int, str]:
        """DELETE + Prefer: count=exact. Returns (status, deleted_count, body)."""
        h = dict(self.base_headers)
        h["Prefer"] = "count=exact"
        r = self.http.delete(self.url(table), headers=h, params=params, timeout=60)
        cr = r.headers.get("content-range", "")
        deleted = 0
        m = re.match(r"\*?/?(\d+)$|^(\d+)-(\d+)/(\d+)$", cr)
        if m:
            if m.group(4):
                deleted = int(m.group(3)) - int(m.group(2)) + 1
            elif m.group(1):
                deleted = int(m.group(1))
        return r.status_code, deleted, (r.text or "")[:200]


# ---------- Data collection ----------

def collect_history_rows(rest: Rest, table: str, op: str, cutoff: str
                          ) -> List[Dict[str, str]]:
    """History rows {match_id_hash, home, away, league, date} for op in {lt, gte}."""
    rows: List[Dict[str, str]] = []
    offset = 0
    while True:
        params = {
            "select": "match_id_hash,home,away,league,date,scraped_at",
            "scraped_at": f"{op}.{cutoff}",
            "order": "match_id_hash.asc",
            "limit": str(PAGE_SIZE),
            "offset": str(offset),
        }
        r = rest.get(table, params)
        if r.status_code != 200:
            print(f"  [WARN] {table} {op} GET HTTP {r.status_code}: {r.text[:200]}")
            return rows
        page = r.json()
        if not page:
            break
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return rows


def parse_kickoff_yyyymmdd(date_str: str) -> str:
    """History `date` formats:
       - 'YYYY-MM-DDTHH:MM:SS+00:00' (newer JSON)
       - '29.Apr 19:00:00' (old HTML)
    Returns 'YYYY-MM-DD' or '' if unparseable. Year defaults to current year for old format.
    """
    if not date_str:
        return ""
    s = date_str.strip()
    # ISO
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # DD.Mon
    m = re.match(r"^(\d{1,2})\.([A-Za-z]{3})", s)
    if m:
        months = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                  "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
        mo = months.get(m.group(2).lower())
        if mo:
            from datetime import datetime as _dt
            yr = _dt.utcnow().year
            return f"{yr:04d}-{mo:02d}-{int(m.group(1)):02d}"
    return ""


def fingerprint(row: Dict[str, str]) -> Tuple[str, str, str]:
    """Replacement detection key: (away_norm[:8], league_norm[:8], kickoff_yyyymmdd)."""
    a = normalize_field(str(row.get("away") or ""))[:8]
    l = normalize_field(str(row.get("league") or ""))[:8]
    d = parse_kickoff_yyyymmdd(str(row.get("date") or ""))
    return (a, l, d)


def narrow_stale_hashes(pre_rows: List[Dict[str, str]],
                         post_rows: List[Dict[str, str]]
                         ) -> Tuple[Set[str], Set[str], Dict[str, Dict[str, str]]]:
    """Return (narrowed_stale, broad_stale, sample_by_hash).

    - broad_stale = pre_hashes - post_hashes (eski mantık; raporlama için)
    - narrowed_stale ⊆ broad_stale: replacement adayı olan hash'ler. Replacement
      testi: post_rows'da aynı fingerprint var ama hash farklı → confirmed
      isim-değişikliği duplicate. Bu, sadece-pre'de var olan ama post'ta hiç
      replacement adayı bulunmayan eski tek-seferlik kayıtları KORUR.
    - sample_by_hash: dry-run sample print için her hash için 1 örnek satır.
    """
    pre_hashes = set()
    post_hashes = set()
    sample: Dict[str, Dict[str, str]] = {}
    post_fp_to_hashes: Dict[Tuple[str, str, str], Set[str]] = {}

    for row in pre_rows:
        h = row.get("match_id_hash")
        if not h:
            continue
        pre_hashes.add(h)
        if h not in sample:
            sample[h] = row
    for row in post_rows:
        h = row.get("match_id_hash")
        if not h:
            continue
        post_hashes.add(h)
        fp = fingerprint(row)
        if fp[2]:  # only count fingerprints with valid date
            post_fp_to_hashes.setdefault(fp, set()).add(h)

    broad_stale = pre_hashes - post_hashes
    narrowed: Set[str] = set()
    for h in broad_stale:
        row = sample.get(h)
        if not row:
            continue
        fp = fingerprint(row)
        if not fp[2]:
            continue
        post_hash_set = post_fp_to_hashes.get(fp, set())
        # confirmed replacement: same fingerprint exists in post with different hash
        if post_hash_set - {h}:
            narrowed.add(h)
    return narrowed, broad_stale, sample


# ---------- Delete helpers ----------

def chunk(seq: List, size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def delete_by_hashes(rest: Rest, table: str, hashes: List[str],
                      extra: Dict[str, str] | None, dry_run: bool) -> int:
    if not hashes:
        return 0
    if dry_run:
        # Use GET with same filter to count
        total = 0
        for batch in chunk(hashes, DELETE_BATCH):
            params = {
                "select": "match_id_hash",
                "match_id_hash": f"in.({','.join(batch)})",
                "limit": str(PAGE_SIZE * 2),
            }
            if extra:
                params.update(extra)
            r = rest.get(table, params)
            if r.status_code == 200:
                try:
                    total += len(r.json())
                except Exception:
                    pass
        return total
    total = 0
    for batch in chunk(hashes, DELETE_BATCH):
        params = {"match_id_hash": f"in.({','.join(batch)})"}
        if extra:
            params.update(extra)
        status, n, body = rest.delete_with_count(table, params)
        if status not in (200, 204):
            print(f"  [WARN] {table} DELETE HTTP {status}: {body}")
            continue
        total += n
    return total


def delete_by_ids(rest: Rest, table: str, ids: List[int], dry_run: bool) -> int:
    if not ids:
        return 0
    if dry_run:
        return len(ids)
    total = 0
    for batch in chunk(ids, DELETE_BATCH):
        params = {"id": f"in.({','.join(str(x) for x in batch)})"}
        status, n, body = rest.delete_with_count(table, params)
        if status not in (200, 204):
            print(f"  [WARN] {table} id-DELETE HTTP {status}: {body}")
            continue
        total += n
    return total


def scan_market_for_stale_ids(rest: Rest, table: str, stale_hashes: Set[str]) -> List[int]:
    ids: List[int] = []
    offset = 0
    while True:
        params = {
            "select": "id,home,away,league",
            "order": "id.asc",
            "limit": str(PAGE_SIZE),
            "offset": str(offset),
        }
        r = rest.get(table, params)
        if r.status_code != 200:
            print(f"  [WARN] {table} scan HTTP {r.status_code}: {r.text[:200]}")
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


def print_sample(label: str, hashes: List[str], sample: Dict[str, Dict[str, str]],
                  limit: int = SAMPLE_LIMIT) -> None:
    print(f"  [SAMPLE] {label} (ilk {min(limit, len(hashes))} / {len(hashes)}):")
    for h in sorted(hashes)[:limit]:
        row = sample.get(h, {})
        print(
            f"    hash={h}  scraped_at={row.get('scraped_at','?')}  "
            f"home={(row.get('home') or '')!r}  away={(row.get('away') or '')!r}  "
            f"league={(row.get('league') or '')!r}  date={(row.get('date') or '')!r}"
        )


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
    print(f"=== Cleanup Stale Arbworld Records — {mode} ===")
    print(f"Cutoff (history TR): {CUTOFF_HISTORY_TR}  |  "
          f"Cutoff (snapshot UTC): {CUTOFF_SNAPSHOT_UTC}")
    print(f"Supabase: {os.environ['SUPABASE_URL']}")
    print()

    # 1) History pre/post rows topla
    print("[1/5] History tablolarından pre/post satırlar toplanıyor...")
    pre_rows: List[Dict[str, str]] = []
    post_rows: List[Dict[str, str]] = []
    for table in HISTORY_TABLES:
        pre = collect_history_rows(rest, table, "lt", CUTOFF_HISTORY_TR)
        post = collect_history_rows(rest, table, "gte", CUTOFF_HISTORY_TR)
        pre_rows.extend(pre)
        post_rows.extend(post)
        pre_h = {r.get("match_id_hash") for r in pre if r.get("match_id_hash")}
        post_h = {r.get("match_id_hash") for r in post if r.get("match_id_hash")}
        print(f"  {table}: pre_rows={len(pre)} (uniq_hash={len(pre_h)}), "
              f"post_rows={len(post)} (uniq_hash={len(post_h)})")

    narrowed_stale, broad_stale, sample_by_hash = narrow_stale_hashes(pre_rows, post_rows)
    print(f"  TOPLAM: broad_stale={len(broad_stale)} "
          f"(pre - post; eski mantık)  |  narrowed_stale={len(narrowed_stale)} "
          f"(replacement-confirmed; KULLANILACAK)")
    skipped = broad_stale - narrowed_stale
    if skipped:
        print(f"  [SAFE] {len(skipped)} hash 'broad ama replacement yok' → KORUNDU "
              f"(over-deletion önlendi)")
    print()

    if not narrowed_stale:
        print("[OK] Stale hash yok, hiçbir şey yapılmadı.")
        return 0

    # Sample print (always, both for safety review)
    print_sample("STALE silinecek", sorted(narrowed_stale), sample_by_hash)
    if skipped:
        print_sample("KORUNAN broad-only", sorted(skipped), sample_by_hash)
    print()

    sorted_stale = sorted(narrowed_stale)

    # 2) Ana market tablolarını tara → stale id'ler
    print("[2/5] Ana market tablolarında stale id'ler taranıyor...")
    market_stale_ids: Dict[str, List[int]] = {}
    total_market_ids = 0
    for table in MARKET_TABLES:
        ids = scan_market_for_stale_ids(rest, table, narrowed_stale)
        market_stale_ids[table] = ids
        total_market_ids += len(ids)
        print(f"  {table}: {len(ids)} stale id")
    print(f"  TOPLAM: {total_market_ids} satır")
    print()

    # 3) Snapshot tablolarından sil
    print("[3/5] Snapshot tabloları (scraped_at_utc < cutoff & stale hash)...")
    snap_extra = {"scraped_at_utc": f"lt.{CUTOFF_SNAPSHOT_UTC}"}
    for table in SNAPSHOT_TABLES:
        n = delete_by_hashes(rest, table, sorted_stale, snap_extra, args.dry_run)
        verb = "matched" if args.dry_run else "deleted"
        print(f"  {table}: {n} satır {verb}")
    print()

    # 4) History tablolarından sil
    print("[4/5] History tabloları (scraped_at < cutoff & stale hash)...")
    hist_extra = {"scraped_at": f"lt.{CUTOFF_HISTORY_TR}"}
    for table in HISTORY_TABLES:
        n = delete_by_hashes(rest, table, sorted_stale, hist_extra, args.dry_run)
        verb = "matched" if args.dry_run else "deleted"
        print(f"  {table}: {n} satır {verb}")
    print()

    # 5) Ana market id batch + fixtures
    print("[5/5] Ana market tablolarından id ile sil...")
    for table in MARKET_TABLES:
        ids = market_stale_ids[table]
        n = delete_by_ids(rest, table, ids, args.dry_run)
        verb = "matched" if args.dry_run else "deleted"
        print(f"  {table}: {n} satır {verb}")
    print()
    print("[5b] Fixtures (yetim stale hash)...")
    n_fix = delete_by_hashes(rest, "fixtures", sorted_stale, None, args.dry_run)
    verb = "matched" if args.dry_run else "deleted"
    print(f"  fixtures: {n_fix} satır {verb}")
    print()

    print("=== TAMAMLANDI ===")
    if args.dry_run:
        print("DRY-RUN: hiçbir kayıt silinmedi. Gerçek silme için --execute kullan.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
