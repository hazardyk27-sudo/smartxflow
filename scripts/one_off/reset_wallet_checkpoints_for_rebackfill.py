"""
Re-backfill: tracked_wallet_activity ve tracked_wallet_redeems tablolarındaki
tüm satırları sil → Hetzner scraper bir sonraki çalışmasında checkpoint=None
görür ve tüm geçmişi yeniden çeker (upsert ile duplicate yok).

Sadece verisi az olan cüzdanları temizler (toplam activity < 1000 satır).
Zaten yeterli verisi olan cüzdanlara dokunmaz.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import argparse
import requests
from services.supabase_client import SupabaseClient

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true', help='Gerçekten sil (yoksa dry-run)')
    parser.add_argument('--all', action='store_true', help='Satır sayısından bağımsız tüm cüzdanları sıfırla')
    args = parser.parse_args()

    client = SupabaseClient()
    http = client._get_http_client()
    headers = client._headers()

    r = http.get(client._rest_url('tracked_wallets'),
                 params={'select': 'wallet,nickname,created_at', 'order': 'created_at.asc'},
                 headers=headers, timeout=15)
    wallets = r.json()
    print(f"{len(wallets)} cüzdan bulundu.\n")

    total_cleared = 0
    for w in wallets:
        wallet = w['wallet']
        nickname = w.get('nickname', wallet[:10])

        # Kaç satır var?
        rc = http.get(client._rest_url('tracked_wallet_activity'),
                      params={'select': 'wallet', 'wallet': f'eq.{wallet}'},
                      headers={**headers, 'Prefer': 'count=exact'}, timeout=10)
        cr = rc.headers.get('Content-Range', '*/0')
        count = int(cr.split('/')[-1]) if '/' in cr else 0

        if not args.all and count >= 1000:
            print(f"[SKIP] {nickname:<22} {count} satır — yeterli veri, atlanıyor")
            continue

        print(f"{'[DRY]' if not args.execute else '[SİL]'} {nickname:<22} {count} satır → sıfırlanacak")
        total_cleared += count

        if args.execute:
            for table in ('tracked_wallet_activity', 'tracked_wallet_redeems'):
                d = http.delete(client._rest_url(table),
                                params={'wallet': f'eq.{wallet}'},
                                headers=headers, timeout=30)
                if d.status_code not in (200, 204):
                    print(f"  [HATA] {table}: HTTP {d.status_code}")

    print(f"\nToplam {'sıfırlanan' if args.execute else 'sıfırlanacak'}: {total_cleared} satır")
    if not args.execute:
        print("Dry-run. Gerçekten silmek için: python3 scripts/one_off/reset_wallet_checkpoints_for_rebackfill.py --execute")

if __name__ == '__main__':
    main()
