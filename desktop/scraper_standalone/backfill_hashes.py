#!/usr/bin/env python3
"""
Backfill script: NULL match_id_hash değerlerini doldur
Bu script Supabase'deki dropping_*_history tablolarındaki NULL hash'leri düzeltir
"""

import hashlib
import os
import sys

try:
    import httpx
except ImportError:
    import requests as httpx

def normalize_field(value: str) -> str:
    """Hash için string normalizasyonu"""
    if not value:
        return ""
    value = value.strip()
    value = value.replace('ı', 'i').replace('İ', 'I')
    value = value.lower()
    value = ' '.join(value.split())
    return value

def make_hash(home: str, away: str, league: str) -> str:
    """12 karakterlik MD5 hash üret"""
    home_norm = normalize_field(home)
    away_norm = normalize_field(away)
    league_norm = normalize_field(league)
    canonical = f"{league_norm}|{home_norm}|{away_norm}"
    return hashlib.md5(canonical.encode('utf-8')).hexdigest()[:12]

def backfill_table(url: str, key: str, table: str):
    """Bir tablodaki NULL hash'leri backfill et"""
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    print(f"\n[{table}] Fetching rows with NULL match_id_hash...")
    
    # NULL hash'li satırları al
    fetch_url = f"{url}/rest/v1/{table}?match_id_hash=is.null&select=id,home,away,league"
    
    try:
        resp = httpx.get(fetch_url, headers=headers, timeout=60)
        if resp.status_code != 200:
            print(f"  ERROR: HTTP {resp.status_code} - {resp.text[:200]}")
            return 0
        
        rows = resp.json()
        print(f"  Found {len(rows)} rows with NULL hash")
        
        if not rows:
            return 0
        
        # Her satır için hash hesapla ve güncelle
        updated = 0
        for row in rows:
            row_id = row.get('id')
            home = row.get('home', '')
            away = row.get('away', '')
            league = row.get('league', '')
            
            if not row_id or not home or not away:
                continue
            
            new_hash = make_hash(home, away, league)
            
            # UPDATE
            update_url = f"{url}/rest/v1/{table}?id=eq.{row_id}"
            update_resp = httpx.patch(
                update_url, 
                headers=headers, 
                json={"match_id_hash": new_hash},
                timeout=30
            )
            
            if update_resp.status_code in [200, 204]:
                updated += 1
            else:
                print(f"  WARN: Failed to update id={row_id}: HTTP {update_resp.status_code}")
        
        print(f"  Updated {updated}/{len(rows)} rows")
        return updated
        
    except Exception as e:
        print(f"  ERROR: {e}")
        return 0

def main():
    url = os.environ.get('SUPABASE_URL')
    key = os.environ.get('SUPABASE_ANON_KEY') or os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
    
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_ANON_KEY environment variables required")
        print("Usage: python backfill_hashes.py")
        sys.exit(1)
    
    print("=" * 50)
    print("BACKFILL: Dropping History Hash Repair")
    print("=" * 50)
    print(f"URL: {url[:40]}...")
    
    tables = [
        "dropping_1x2_history",
        "dropping_ou25_history", 
        "dropping_btts_history",
        "moneyway_1x2_history",
        "moneyway_ou25_history",
        "moneyway_btts_history",
    ]
    
    total = 0
    for table in tables:
        count = backfill_table(url, key, table)
        total += count
    
    print("\n" + "=" * 50)
    print(f"BACKFILL COMPLETE: {total} total rows updated")
    print("=" * 50)

if __name__ == "__main__":
    main()
