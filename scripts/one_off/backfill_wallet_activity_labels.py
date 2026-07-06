#!/usr/bin/env python3
"""
Task #266 — tracked_wallet_activity geriye dönük etiket düzeltmesi (one-off).

`market_type`/`selection`/`side` alanları scrape anında hesaplanıp donuk
şekilde `tracked_wallet_activity` tablosuna yazılıyor. `_parse_activity_market`
fonksiyonundaki suffix (O/U 3.5, Spread gibi standart olmayan piyasalar)
sınıflandırma hatası düzeltildikten sonra bile DB'deki eski satırlar otomatik
güncellenmiyor - bu script mevcut tüm satırları güncel mantıkla yeniden
işleyip yanlış etiketlenmiş olanları düzeltir.

Sadece şu üç alan değişebilir: market_type, selection, side. Diğer tüm
alanlar (wallet, transaction_hash, asset, amount_usdc, price, traded_at, ...)
dokunulmadan kalır.

Kullanım:
  python scripts/one_off/backfill_wallet_activity_labels.py --dry-run
  python scripts/one_off/backfill_wallet_activity_labels.py --execute
"""

import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import requests  # noqa: E402
from services.polymarket_client import _parse_activity_market  # noqa: E402

PAGE_SIZE = 1000


def _supabase_base_url() -> str:
    return (os.environ.get("SUPABASE_URL", "") or "").rstrip("/")


def _headers() -> dict:
    key = os.environ.get("SUPABASE_ANON_KEY", "") or os.environ.get("SUPABASE_KEY", "")
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def fetch_all_rows(base: str, headers: dict):
    rows = []
    offset = 0
    while True:
        r = requests.get(
            f"{base}/rest/v1/tracked_wallet_activity",
            headers=headers,
            params={
                "select": "id,title,slug,outcome_raw,market_type,selection,side",
                "order": "id.asc",
                "limit": PAGE_SIZE,
                "offset": offset,
            },
            timeout=30,
        )
        r.raise_for_status()
        page = r.json()
        if not page:
            break
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return rows


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    base = _supabase_base_url()
    if not base:
        print("SUPABASE_URL bulunamadi.")
        sys.exit(1)
    headers = _headers()

    print("tracked_wallet_activity satirlari cekiliyor...")
    rows = fetch_all_rows(base, headers)
    print(f"{len(rows)} satir bulundu.")

    to_update = []
    for row in rows:
        # `side` is stored with "" as a non-null sentinel (see the UNIQUE
        # constraint note in the migration / scraper) - normalize it back to
        # None before re-deriving, matching what the live scraper sees.
        market_type, _home, _away, selection, side = _parse_activity_market({
            "title": row.get("title"),
            "slug": row.get("slug"),
            "outcome": row.get("outcome_raw"),
        })
        side_db = side if side is not None else ""
        old = (row.get("market_type"), row.get("selection"), row.get("side") or "")
        new = (market_type, selection, side_db)
        if old != new:
            to_update.append((row["id"], old, new))

    print(f"{len(to_update)} satir farkli sonuc uretiyor (guncellenecek).")
    for rid, old, new in to_update[:20]:
        print(f"  id={rid}: {old} -> {new}")
    if len(to_update) > 20:
        print(f"  ... ve {len(to_update) - 20} satir daha")

    if args.dry_run:
        print("Dry-run modu, hicbir sey yazilmadi.")
        return

    print("Guncelleniyor...")
    ok = 0
    fail = 0
    for rid, _old, (market_type, selection, side_db) in to_update:
        r = requests.patch(
            f"{base}/rest/v1/tracked_wallet_activity",
            headers=headers,
            params={"id": f"eq.{rid}"},
            json={"market_type": market_type, "selection": selection, "side": side_db},
            timeout=15,
        )
        if r.status_code in (200, 204):
            ok += 1
        else:
            fail += 1
            print(f"  HATA id={rid}: HTTP {r.status_code} {r.text[:200]}")
    print(f"Bitti. {ok} basarili, {fail} hatali.")


if __name__ == "__main__":
    main()
