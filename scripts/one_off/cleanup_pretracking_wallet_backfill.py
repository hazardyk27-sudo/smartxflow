#!/usr/bin/env python3
"""
Task #280 - Takip edilen cuzdanlarin TAKIP BASLANGICINDAN ONCEKI backfill
verisini temizle (one-off).

Bir cuzdan `tracked_wallets`'a eklendiginde ilk senkronizasyon Polymarket
Data API'sinden ~10.000 islemlik gecmis backfill cekiyordu (bkz.
_ACTIVITY_MAX_PAGES). Bu davranis Task #280 ile durduruldu (yeni cuzdanlarda
artik sadece takip anindan sonraki islemler cekiliyor), ancak HALIHAZIRDA
takip edilen cuzdanlarin veritabaninda zaten yazilmis backfill satirlari
duruyor - bu script o satirlari siler ki istatistikler (Isabet Orani, Islem
Sayisi, Acik Pozisyon vb.) sadece takip sonrasi gercek veriden hesaplansin.

Kapsam:
  - tracked_wallet_activity : wallet bazinda traded_at < tracked_wallets.created_at
  - tracked_wallet_redeems  : ayni kural
  - tracked_wallet_positions: TARIH KOLONU YOK (her donguede tam senkron/anlik
    goruntu), bu yuzden BURADA silinmez - profil/liste tarafinda runtime'da
    (aktivite ile eslesmeyen asset'ler) filtrelenir (services/polymarket_client.py
    _filter_positions_since_tracking).

Kullanim:
  python scripts/one_off/cleanup_pretracking_wallet_backfill.py --dry-run
  python scripts/one_off/cleanup_pretracking_wallet_backfill.py --execute
"""

import argparse
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from services.supabase_client import SupabaseClient  # noqa: E402

TABLES_WITH_TIMESTAMP = ["tracked_wallet_activity", "tracked_wallet_redeems"]


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Sadece rapor et, silme")
    group.add_argument("--execute", action="store_true", help="Gercekten sil")
    args = parser.parse_args()

    client = SupabaseClient()
    http = client._get_http_client()
    headers = client._headers()

    r = http.get(
        f"{client._rest_url('tracked_wallets')}?select=wallet,nickname,created_at&order=created_at.asc",
        headers=headers,
        timeout=30,
    )
    if r.status_code != 200:
        print(f"[HATA] tracked_wallets GET basarisiz: HTTP {r.status_code}: {r.text[:200]}")
        sys.exit(1)
    wallets = r.json()
    if not wallets:
        print("Takip edilen cuzdan yok, yapilacak bir sey yok.")
        return

    print(f"{len(wallets)} takip edilen cuzdan bulundu.\n")
    total_deleted = 0

    for w in wallets:
        wallet = w.get("wallet")
        nickname = w.get("nickname")
        created_at = w.get("created_at")
        if not wallet or not created_at:
            continue

        print(f"--- {nickname} ({wallet[:10]}...) - takip baslangici: {created_at}")
        for table in TABLES_WITH_TIMESTAMP:
            params = {
                "select": "id",
                "wallet": f"eq.{wallet}",
                "traded_at": f"lt.{created_at}",
                "limit": "1",
            }
            count_r = http.get(
                client._rest_url(table),
                params=params,
                headers={**headers, "Prefer": "count=exact"},
                timeout=30,
            )
            content_range = count_r.headers.get("Content-Range", "")
            stale_count = None
            if "/" in content_range:
                try:
                    stale_count = int(content_range.split("/")[-1])
                except ValueError:
                    stale_count = None

            if not stale_count:
                print(f"    {table}: 0 backfill satiri")
                continue

            print(f"    {table}: {stale_count} takip-oncesi (backfill) satir bulundu")
            total_deleted += stale_count

            if args.execute:
                del_r = http.delete(
                    client._rest_url(table),
                    params={"wallet": f"eq.{wallet}", "traded_at": f"lt.{created_at}"},
                    headers=headers,
                    timeout=60,
                )
                if del_r.status_code not in (200, 204):
                    print(f"      [HATA] DELETE basarisiz: HTTP {del_r.status_code}: {del_r.text[:200]}")
                else:
                    print(f"      -> silindi")

    print(f"\nToplam {'silinecek' if args.dry_run else 'silinen'} satir: {total_deleted}")
    if args.dry_run:
        print("Bu bir dry-run idi, hicbir satir silinmedi. Gercekten silmek icin --execute kullanin.")


if __name__ == "__main__":
    main()
