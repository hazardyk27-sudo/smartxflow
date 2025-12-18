#!/usr/bin/env python3
"""
History tablolarındaki mevcut kayıtlar için match_id_hash backfill
Supabase'de migration SQL çalıştırıldıktan sonra bu scripti çalıştırın.
"""

import os
import sys
import re
import hashlib
import requests
from datetime import datetime

# Supabase credentials
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')

if not SUPABASE_URL or not SERVICE_KEY:
    print("ERROR: SUPABASE_URL ve SUPABASE_SERVICE_ROLE_KEY environment variables gerekli!")
    sys.exit(1)

HEADERS = {
    'apikey': SERVICE_KEY,
    'Authorization': f'Bearer {SERVICE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=minimal'
}

# Hash fonksiyonları (core/hash_utils.py ile aynı)
def normalize_field(value: str) -> str:
    if not value:
        return ""
    value = value.strip()
    tr_map = {'ş': 's', 'Ş': 'S', 'ğ': 'g', 'Ğ': 'G', 'ü': 'u', 'Ü': 'U',
              'ı': 'i', 'İ': 'I', 'ö': 'o', 'Ö': 'O', 'ç': 'c', 'Ç': 'C'}
    for tr_char, en_char in tr_map.items():
        value = value.replace(tr_char, en_char)
    value = value.lower()
    value = re.sub(r'[^a-z0-9\s]', '', value)
    value = ' '.join(value.split())
    suffixes = ['fc', 'fk', 'sk', 'sc', 'afc', 'cf', 'ac', 'as']
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if value.endswith(' ' + suffix):
                value = value[:-len(suffix)-1].strip()
                changed = True
                break
    return value

def normalize_kickoff(kickoff: str) -> str:
    if not kickoff:
        return ""
    kickoff = str(kickoff).strip()
    kickoff = re.sub(r'[+-]\d{2}:\d{2}$', '', kickoff)
    kickoff = kickoff.replace('Z', '')
    if 'T' in kickoff and len(kickoff) >= 16:
        return kickoff[:16]
    if len(kickoff) >= 10 and kickoff[4] == '-':
        return kickoff[:16] if len(kickoff) >= 16 else kickoff[:10] + "T00:00"
    return kickoff

def make_match_id_hash(home: str, away: str, league: str, kickoff: str) -> str:
    home_norm = normalize_field(home)
    away_norm = normalize_field(away)
    league_norm = normalize_field(league)
    kickoff_norm = normalize_kickoff(kickoff)
    canonical = f"{league_norm}|{kickoff_norm}|{home_norm}|{away_norm}"
    return hashlib.md5(canonical.encode('utf-8')).hexdigest()[:12]

def backfill_table(table_name: str):
    """Tek bir history tablosu için backfill"""
    print(f"\n[{table_name}] Backfill başlıyor...")
    
    # NULL match_id_hash olan kayıtları çek
    offset = 0
    page_size = 500
    total_updated = 0
    
    while True:
        url = f"{SUPABASE_URL}/rest/v1/{table_name}?match_id_hash=is.null&select=id,home,away,league,date&limit={page_size}&offset={offset}"
        r = requests.get(url, headers=HEADERS, timeout=30)
        
        if r.status_code != 200:
            print(f"  ERROR: {r.status_code} - {r.text[:100]}")
            break
        
        rows = r.json()
        if not rows:
            break
        
        print(f"  {len(rows)} kayıt işleniyor (offset={offset})...")
        
        # Her kayıt için hash hesapla ve güncelle
        for row in rows:
            row_id = row.get('id')
            home = row.get('home', '')
            away = row.get('away', '')
            league = row.get('league', '')
            date_val = row.get('date', '')
            
            if not home or not away:
                continue
            
            # Hash hesapla
            match_hash = make_match_id_hash(home, away, league, date_val)
            
            # Güncelle
            update_url = f"{SUPABASE_URL}/rest/v1/{table_name}?id=eq.{row_id}"
            update_r = requests.patch(
                update_url,
                headers=HEADERS,
                json={'match_id_hash': match_hash},
                timeout=10
            )
            
            if update_r.status_code in [200, 204]:
                total_updated += 1
            else:
                print(f"    WARN: id={row_id} güncellenemedi: {update_r.status_code}")
        
        if len(rows) < page_size:
            break
        offset += page_size
    
    print(f"  [{table_name}] Toplam {total_updated} kayıt güncellendi")
    return total_updated

def main():
    print("=" * 60)
    print("HISTORY TABLOLARI match_id_hash BACKFILL")
    print("=" * 60)
    print(f"Supabase URL: {SUPABASE_URL[:40]}...")
    
    history_tables = [
        'moneyway_1x2_history',
        'moneyway_ou25_history', 
        'moneyway_btts_history',
        'dropping_1x2_history',
        'dropping_ou25_history',
        'dropping_btts_history'
    ]
    
    total = 0
    for table in history_tables:
        count = backfill_table(table)
        total += count
    
    print("\n" + "=" * 60)
    print(f"TOPLAM: {total} kayıt güncellendi")
    print("=" * 60)

if __name__ == '__main__':
    main()
