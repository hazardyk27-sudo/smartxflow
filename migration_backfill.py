"""
Migration: moneyway_snapshots → moneyway_*_history
Eski snapshot verilerini pivot edip history tablolarına taşır.
Duplicate önleme: Zaten history'de olan match_id_hash+scraped_at kombinasyonları atlanır.
"""

import os
import httpx
import json
import time
from datetime import datetime

SUPABASE_URL = os.getenv('SUPABASE_URL', '')
SUPABASE_KEY = os.getenv('SUPABASE_ANON_KEY', '') or os.getenv('SUPABASE_KEY', '')

def headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

def rest_url(table):
    return f"{SUPABASE_URL}/rest/v1/{table}"

def fetch_all_paginated(table, select="*", filters="", order="scraped_at_utc.asc", page_size=1000):
    all_rows = []
    offset = 0
    while True:
        url = f"{rest_url(table)}?select={select}&order={order}&limit={page_size}&offset={offset}"
        if filters:
            url += f"&{filters}"
        resp = httpx.get(url, headers=headers(), timeout=30)
        if resp.status_code != 200:
            print(f"  ERROR fetching {table}: {resp.status_code} - {resp.text[:200]}")
            break
        rows = resp.json()
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size
        print(f"  ... fetched {len(all_rows)} rows so far")
    return all_rows

def fetch_existing_history_keys(history_table):
    """History tablosundaki mevcut match_id_hash + scraped_at kombinasyonlarını çek"""
    print(f"\n[STEP] {history_table} mevcut kayıtları kontrol ediliyor...")
    keys = set()
    offset = 0
    page_size = 1000
    while True:
        url = f"{rest_url(history_table)}?select=match_id_hash,scraped_at&order=scraped_at.asc&limit={page_size}&offset={offset}"
        resp = httpx.get(url, headers=headers(), timeout=30)
        if resp.status_code != 200:
            print(f"  ERROR: {resp.status_code}")
            break
        rows = resp.json()
        if not rows:
            break
        for r in rows:
            keys.add((r.get('match_id_hash', ''), r.get('scraped_at', '')))
        if len(rows) < page_size:
            break
        offset += page_size
    print(f"  -> {len(keys)} mevcut kayıt bulundu")
    return keys

def fetch_fixtures():
    """fixtures tablosundan tüm maç bilgilerini çek"""
    print("\n[STEP] Fixtures tablosu çekiliyor...")
    fixtures = {}
    offset = 0
    page_size = 1000
    while True:
        url = f"{rest_url('fixtures')}?select=match_id_hash,home_team,away_team,league,fixture_date&limit={page_size}&offset={offset}"
        resp = httpx.get(url, headers=headers(), timeout=30)
        if resp.status_code != 200:
            print(f"  ERROR: {resp.status_code}")
            break
        rows = resp.json()
        if not rows:
            break
        for r in rows:
            fixtures[r['match_id_hash']] = {
                'home': r.get('home_team', ''),
                'away': r.get('away_team', ''),
                'league': r.get('league', ''),
                'date': r.get('fixture_date', '')
            }
        if len(rows) < page_size:
            break
        offset += page_size
    print(f"  -> {len(fixtures)} fixture bulundu")
    return fixtures

def pivot_snapshots_to_history(snapshots, fixtures, market):
    """
    moneyway_snapshots row-per-selection formatını pivot edip history formatına çevir.
    
    snapshots format: match_id_hash, market, selection, odds, volume, share, scraped_at_utc
    
    1X2 selections: 1, X, 2
    OU25 selections: O, U
    BTTS selections: Y, N
    """
    grouped = {}
    for s in snapshots:
        key = (s['match_id_hash'], s['scraped_at_utc'])
        if key not in grouped:
            grouped[key] = {}
        grouped[key][s['selection']] = s
    
    history_rows = []
    
    for (match_hash, scraped_at), selections in grouped.items():
        fix = fixtures.get(match_hash)
        if not fix:
            continue
        
        scraped_ts = scraped_at
        if scraped_ts and 'T' in scraped_ts:
            try:
                dt = datetime.fromisoformat(scraped_ts.replace('Z', '+00:00'))
                from datetime import timezone, timedelta
                tr_tz = timezone(timedelta(hours=3))
                tr_dt = dt.astimezone(tr_tz)
                scraped_ts = tr_dt.strftime('%Y-%m-%dT%H:%M:%S+03:00')
            except:
                pass
        
        if market == '1X2':
            s1 = selections.get('1', {})
            sx = selections.get('X', {})
            s2 = selections.get('2', {})
            
            if not s1 and not sx and not s2:
                continue
            
            row = {
                'match_id_hash': match_hash,
                'home': fix['home'],
                'away': fix['away'],
                'league': fix['league'],
                'date': fix['date'],
                'odds1': s1.get('odds', ''),
                'oddsx': sx.get('odds', ''),
                'odds2': s2.get('odds', ''),
                'amt1': s1.get('volume', ''),
                'amtx': sx.get('volume', ''),
                'amt2': s2.get('volume', ''),
                'pct1': s1.get('share', ''),
                'pctx': sx.get('share', ''),
                'pct2': s2.get('share', ''),
                'scraped_at': scraped_ts
            }
            history_rows.append(row)
        
        elif market == 'OU25':
            so = selections.get('O', {})
            su = selections.get('U', {})
            
            if not so and not su:
                continue
            
            row = {
                'match_id_hash': match_hash,
                'home': fix['home'],
                'away': fix['away'],
                'league': fix['league'],
                'date': fix['date'],
                'odds_over': so.get('odds', ''),
                'odds_under': su.get('odds', ''),
                'amt_over': so.get('volume', ''),
                'amt_under': su.get('volume', ''),
                'pct_over': so.get('share', ''),
                'pct_under': su.get('share', ''),
                'scraped_at': scraped_ts
            }
            history_rows.append(row)
        
        elif market == 'BTTS':
            sy = selections.get('Y', {})
            sn = selections.get('N', {})
            
            if not sy and not sn:
                continue
            
            row = {
                'match_id_hash': match_hash,
                'home': fix['home'],
                'away': fix['away'],
                'league': fix['league'],
                'date': fix['date'],
                'odds_yes': sy.get('odds', ''),
                'odds_no': sn.get('odds', ''),
                'amt_yes': sy.get('volume', ''),
                'amt_no': sn.get('volume', ''),
                'pct_yes': sy.get('share', ''),
                'pct_no': sn.get('share', ''),
                'scraped_at': scraped_ts
            }
            history_rows.append(row)
    
    return history_rows

def insert_batch(table, rows, batch_size=200):
    """Batch insert with retry"""
    total = 0
    failed = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        try:
            resp = httpx.post(
                rest_url(table),
                headers=headers(),
                json=batch,
                timeout=30
            )
            if resp.status_code in (200, 201):
                total += len(batch)
            else:
                print(f"  Batch error ({resp.status_code}): {resp.text[:200]}")
                for single in batch:
                    try:
                        r = httpx.post(rest_url(table), headers=headers(), json=single, timeout=10)
                        if r.status_code in (200, 201):
                            total += 1
                        else:
                            failed += 1
                    except:
                        failed += 1
        except Exception as e:
            print(f"  Batch exception: {e}")
            failed += len(batch)
        
        if (i + batch_size) % 1000 == 0:
            print(f"  ... inserted {total} rows")
    
    return total, failed

def migrate_market(market_code, history_table):
    print(f"\n{'='*60}")
    print(f"MARKET: {market_code} → {history_table}")
    print(f"{'='*60}")
    
    existing_keys = fetch_existing_history_keys(history_table)
    
    print(f"\n[STEP] moneyway_snapshots'tan {market_code} verisi çekiliyor...")
    snapshots = fetch_all_paginated(
        'moneyway_snapshots',
        select='match_id_hash,market,selection,odds,volume,share,scraped_at_utc',
        filters=f'market=eq.{market_code}'
    )
    print(f"  -> {len(snapshots)} snapshot satırı bulundu")
    
    if not snapshots:
        print("  -> Veri yok, atlanıyor.")
        return 0, 0
    
    min_ts = min(s['scraped_at_utc'] for s in snapshots)
    max_ts = max(s['scraped_at_utc'] for s in snapshots)
    print(f"  -> Tarih aralığı: {min_ts} ~ {max_ts}")
    
    fixtures = fetch_fixtures()
    
    print(f"\n[STEP] Pivot ediliyor...")
    history_rows = pivot_snapshots_to_history(snapshots, fixtures, market_code)
    print(f"  -> {len(history_rows)} pivot satırı oluşturuldu")
    
    new_rows = []
    skipped = 0
    for row in history_rows:
        key = (row.get('match_id_hash', ''), row.get('scraped_at', ''))
        if key in existing_keys:
            skipped += 1
        else:
            new_rows.append(row)
    
    print(f"  -> {skipped} duplicate atlandı, {len(new_rows)} yeni satır eklenecek")
    
    if not new_rows:
        print("  -> Eklenecek yeni veri yok.")
        return 0, 0
    
    print(f"\n[STEP] {history_table}'a yazılıyor...")
    total, failed = insert_batch(history_table, new_rows)
    print(f"  -> SONUÇ: {total} başarılı, {failed} başarısız")
    
    return total, failed

def main():
    print("=" * 60)
    print("SmartXFlow Migration: moneyway_snapshots → *_history")
    print(f"Zaman: {datetime.now().isoformat()}")
    print("=" * 60)
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("HATA: SUPABASE_URL veya SUPABASE_ANON_KEY bulunamadı!")
        return
    
    print(f"\n[INFO] Supabase URL: {SUPABASE_URL[:30]}...")
    
    markets = [
        ('1X2', 'moneyway_1x2_history'),
        ('OU25', 'moneyway_ou25_history'),
        ('BTTS', 'moneyway_btts_history'),
    ]
    
    results = {}
    for market_code, history_table in markets:
        total, failed = migrate_market(market_code, history_table)
        results[market_code] = {'total': total, 'failed': failed}
    
    print(f"\n{'='*60}")
    print("ÖZET")
    print(f"{'='*60}")
    for market, res in results.items():
        print(f"  {market}: {res['total']} eklendi, {res['failed']} başarısız")
    print(f"\nMigration tamamlandı: {datetime.now().isoformat()}")

if __name__ == '__main__':
    main()
