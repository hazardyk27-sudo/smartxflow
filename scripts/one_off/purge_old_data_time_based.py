"""
One-off: zaman bazli (time-based) eski veri temizligi.

Cleanup'in match_id_hash eslestirmesi yuzunden ORPHAN olan satirlar (ozellikle
live_snapshots, 380K+) hicbir zaman silinmiyordu. Bu betik, yeni zaman bazli
cleanup_old_matches() yolunu kullanarak D-8'den (today - 8 gun) eski TUM satirlari
(orphan dahil) tek seferde temizler ve birikmis backlog'u indirir.

Calistirma: python scripts/one_off/purge_old_data_time_based.py
Gerekli env: SUPABASE_URL, SUPABASE_ANON_KEY
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from services.supabase_client import SupabaseClient

TURKEY = timezone(timedelta(hours=3))

CHECK_TABLES = [
    ('live_snapshots', 'snapshot_at'),
    ('moneyway_snapshots', 'scraped_at_utc'),
    ('moneyway_1x2_history', 'scraped_at'),
    ('moneyway_ou25_history', 'scraped_at'),
    ('moneyway_btts_history', 'scraped_at'),
    ('dropping_1x2_history', 'scraped_at'),
    ('dropping_ou25_history', 'scraped_at'),
    ('dropping_btts_history', 'scraped_at'),
]


def report(client, cutoff, label):
    print(f"\n=== {label} (cutoff < {cutoff}) ===")
    for table, col in CHECK_TABLES:
        n = client._count_rows_before(table, col, cutoff)
        if n == -1:
            print(f"  {table:28s} -> tablo yok (skip)")
        else:
            print(f"  {table:28s} -> {n} eski satir")


def main():
    client = SupabaseClient()
    if not client.is_available:
        print("[FATAL] Supabase credentials yok. SUPABASE_URL / SUPABASE_ANON_KEY gerekli.")
        sys.exit(1)

    today = datetime.now(TURKEY).date()
    cutoff = (today - timedelta(days=8)).strftime('%Y-%m-%d')
    print(f"Bugun (Turkiye): {today} | Cutoff (today-8): {cutoff}")

    report(client, cutoff, "ONCESI - silinecek eski satir sayilari")

    print("\n>>> cleanup_old_matches() calistiriliyor (zaman bazli, orphan dahil)...")
    deleted = client.cleanup_old_matches(cutoff)
    print("\n>>> Silinen ozeti:")
    total = 0
    for k, v in deleted.items():
        total += v
        print(f"  {k:28s} -> {v} satir silindi")
    print(f"  TOPLAM: {total} satir")

    report(client, cutoff, "SONRASI - kalan eski satir sayilari (0 olmali)")


if __name__ == '__main__':
    main()
