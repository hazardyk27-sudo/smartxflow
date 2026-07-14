#!/usr/bin/env python3
"""
Tüm tracked_wallet_activity ve tracked_wallet_redeems kayıtlarını siler.
Bu işlemden sonra scraper her cüzdan için since_ts=None ile çalışır
(checkpoint bulunamaz) → tam backfill tetiklenir.
"""
import os
import sys
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("HATA: SUPABASE_URL ve SUPABASE_ANON_KEY env değişkenleri gerekli")
    sys.exit(1)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


def delete_all(table: str) -> int:
    url = f"{SUPABASE_URL}/rest/v1/{table}?id=gte.0"
    # PostgREST: neq filter ensures all rows match
    url = f"{SUPABASE_URL}/rest/v1/{table}?wallet=neq.___none___"
    resp = requests.delete(url, headers={**HEADERS, "Prefer": "return=representation"}, timeout=30)
    if resp.status_code in (200, 204):
        try:
            deleted = len(resp.json()) if resp.text else 0
        except Exception:
            deleted = -1
        print(f"  [{table}] silindi (HTTP {resp.status_code}) — yaklaşık {deleted} satır")
        return deleted
    else:
        print(f"  [{table}] HATA HTTP {resp.status_code}: {resp.text[:300]}")
        return 0


print("=== Wallet Activity Backfill Reset ===")
print("tracked_wallet_activity siliniyor...")
delete_all("tracked_wallet_activity")
print("tracked_wallet_redeems siliniyor...")
delete_all("tracked_wallet_redeems")
print("Bitti. Bir sonraki scraper döngüsünde tüm cüzdanlar için tam backfill başlayacak.")
