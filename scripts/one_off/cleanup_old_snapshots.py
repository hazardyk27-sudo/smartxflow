"""
Tek seferlik: moneyway_snapshots + dropping_odds_snapshots eski veri temizligi
29M satirdan ~2.5M'a indirme (D-8 oncesi silme)
ID-bazli batch delete — primary key indexi kullanir, timeout riski yok
"""
import os, requests, time
from datetime import datetime, timezone, timedelta

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Prefer": "return=minimal",
}

CUTOFF = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%d")
BATCH = 50_000


def get_boundary_id(table: str, date_col: str) -> int:
    """cutoff tarihinden sonraki en kucuk id'yi bul"""
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}?{date_col}=gte.{CUTOFF}&select=id&order=id.asc&limit=1",
        headers=HEADERS, timeout=30
    )
    rows = resp.json()
    if not rows:
        print(f"  [{table}] Cutoff'tan yeni satir yok — tablo zaten temiz olabilir")
        return 0
    return rows[0]["id"]


def batch_delete(table: str, max_id: int) -> int:
    """id < max_id olan satirlari BATCH ile sil, toplam silinen sayisini dondur"""
    total = 0
    current = 1
    while current < max_id:
        end = min(current + BATCH, max_id)
        resp = requests.delete(
            f"{SUPABASE_URL}/rest/v1/{table}?id=gte.{current}&id=lt.{end}",
            headers=HEADERS, timeout=60
        )
        if resp.status_code in [200, 204]:
            total += BATCH
            print(f"  [{table}] Batch {current}-{end} silindi ({total:,} toplam)", flush=True)
        else:
            print(f"  [{table}] HATA {resp.status_code}: {resp.text[:100]}", flush=True)
        current = end
        time.sleep(0.1)
    return total


def run(table: str, date_col: str):
    print(f"\n[{table}] Basliyor — cutoff: {CUTOFF}")
    boundary = get_boundary_id(table, date_col)
    if boundary == 0:
        return
    print(f"  [{table}] Boundary ID: {boundary:,} — bu ID'den once her sey silinecek")
    deleted = batch_delete(table, boundary)
    print(f"  [{table}] TAMAMLANDI — {deleted:,} satir silindi\n")


if __name__ == "__main__":
    print(f"=== ONE-OFF SNAPSHOT CLEANUP ===")
    print(f"Cutoff: {CUTOFF} (D-8)")
    run("moneyway_snapshots", "scraped_at_utc")
    run("dropping_odds_snapshots", "scraped_at_utc")
    print("=== BITTI ===")
