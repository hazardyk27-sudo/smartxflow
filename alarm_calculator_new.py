#!/usr/bin/env python3
"""
ALARM CALCULATOR - Mevcut snapshot tablolarından alarm üretir
Tablolar: moneyway_1x2, moneyway_ou25, moneyway_btts, dropping_1x2, dropping_ou25, dropping_btts
"""

import os
import re
import hashlib
import requests
from datetime import datetime, timedelta
from typing import Optional

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')

HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=minimal'
}

TR_MAP = {
    'ş': 's', 'Ş': 'S', 'ğ': 'g', 'Ğ': 'G',
    'ü': 'u', 'Ü': 'U', 'ı': 'i', 'İ': 'I',
    'ö': 'o', 'Ö': 'O', 'ç': 'c', 'Ç': 'C'
}

SUFFIXES = ['fc', 'fk', 'sk', 'sc', 'afc', 'cf', 'ac', 'as']

def normalize_field(value: str) -> str:
    if not value:
        return ""
    value = value.strip()
    for tr, en in TR_MAP.items():
        value = value.replace(tr, en)
    value = value.lower()
    value = re.sub(r'[^a-z0-9\s]', '', value)
    value = ' '.join(value.split())
    changed = True
    while changed:
        changed = False
        for suffix in SUFFIXES:
            if value.endswith(' ' + suffix):
                value = value[:-len(suffix)-1].strip()
                changed = True
                break
    return value

def parse_date(date_str: str) -> Optional[str]:
    """Parse '23.Dec 17:30:00' or '07.Dec20:00:00' to ISO format"""
    if not date_str:
        return None
    date_str = date_str.strip()
    date_str = re.sub(r'(\d{2}\.\w{3})(\d{2}:\d{2})', r'\1 \2', date_str)
    months = {'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06',
              'Jul': '07', 'Aug': '08', 'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'}
    match = re.match(r'(\d{2})\.(\w{3})\s*(\d{2}:\d{2})', date_str)
    if match:
        day, mon, time = match.groups()
        year = datetime.now().year
        if mon in months:
            return f"{year}-{months[mon]}-{day}T{time}"
    return None

def parse_money(money_str: str) -> float:
    """Parse '£ 206' or '£ 2 930' to float"""
    if not money_str:
        return 0.0
    clean = re.sub(r'[^\d.]', '', money_str.replace(' ', ''))
    try:
        return float(clean) if clean else 0.0
    except:
        return 0.0

def parse_percent(pct_str: str) -> float:
    """Parse '90.2%' to float"""
    if not pct_str:
        return 0.0
    clean = pct_str.replace('%', '').strip()
    try:
        return float(clean)
    except:
        return 0.0

def parse_odds(odds_str: str) -> float:
    if not odds_str:
        return 0.0
    try:
        return float(odds_str)
    except:
        return 0.0

def make_match_id_hash(home: str, away: str, league: str, kickoff: str) -> str:
    home_n = normalize_field(home)
    away_n = normalize_field(away)
    league_n = normalize_field(league)
    kickoff_n = kickoff[:16] if kickoff and len(kickoff) >= 16 else (kickoff or "")
    canonical = f"{league_n}|{kickoff_n}|{home_n}|{away_n}"
    return hashlib.md5(canonical.encode('utf-8')).hexdigest()[:12]

def fetch_data(table: str, limit: int = 500) -> list:
    r = requests.get(
        f'{SUPABASE_URL}/rest/v1/{table}?select=*&limit={limit}',
        headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'},
        timeout=30
    )
    return r.json() if r.status_code == 200 else []

def upsert_alarm(table: str, data: dict) -> bool:
    r = requests.post(
        f'{SUPABASE_URL}/rest/v1/{table}',
        headers={**HEADERS, 'Prefer': 'resolution=merge-duplicates'},
        json=data,
        timeout=10
    )
    return r.status_code in [200, 201]

def calculate_bigmoney_alarms(threshold: float = 500) -> list:
    """BigMoney: Yüksek para girişi olan maçlar"""
    alarms = []
    
    for table, market in [('moneyway_1x2', '1X2'), ('moneyway_ou25', 'OU25'), ('moneyway_btts', 'BTTS')]:
        data = fetch_data(table)
        
        for row in data:
            kickoff = parse_date(row.get('date', ''))
            if not kickoff:
                continue
            
            match_id_hash = make_match_id_hash(
                row.get('home', ''),
                row.get('away', ''),
                row.get('league', ''),
                kickoff
            )
            
            if market == '1X2':
                selections = [
                    ('1', parse_money(row.get('amt1', '')), parse_odds(row.get('odds1', ''))),
                    ('X', parse_money(row.get('amtx', '')), parse_odds(row.get('oddsx', ''))),
                    ('2', parse_money(row.get('amt2', '')), parse_odds(row.get('odds2', '')))
                ]
            elif market == 'OU25':
                selections = [
                    ('O', parse_money(row.get('amtover', '')), parse_odds(row.get('over', ''))),
                    ('U', parse_money(row.get('amtunder', '')), parse_odds(row.get('under', '')))
                ]
            else:
                selections = [
                    ('Y', parse_money(row.get('amtyes', '')), parse_odds(row.get('yes', ''))),
                    ('N', parse_money(row.get('amtno', '')), parse_odds(row.get('no', '')))
                ]
            
            total = parse_money(row.get('volume', ''))
            
            for sel, amt, odds in selections:
                if amt >= threshold:
                    is_huge = amt >= threshold * 2
                    alarm = {
                        'match_id_hash': match_id_hash,
                        'home': row.get('home', '')[:100],
                        'away': row.get('away', '')[:100],
                        'league': row.get('league', '')[:150],
                        'market': market,
                        'selection': sel,
                        'incoming_money': amt,
                        'total_selection': total,
                        'is_huge': is_huge
                    }
                    alarms.append(alarm)
    
    return alarms

def calculate_dropping_alarms(drop_threshold: float = 10) -> list:
    """Dropping: Oran düşüşü yüksek olan maçlar"""
    alarms = []
    
    for table, market in [('dropping_1x2', '1X2'), ('dropping_ou25', 'OU25'), ('dropping_btts', 'BTTS')]:
        data = fetch_data(table)
        
        for row in data:
            kickoff = parse_date(row.get('date', ''))
            if not kickoff:
                continue
            
            match_id_hash = make_match_id_hash(
                row.get('home', ''),
                row.get('away', ''),
                row.get('league', ''),
                kickoff
            )
            
            if market == '1X2':
                selections = [
                    ('1', parse_odds(row.get('odds1', '')), parse_odds(row.get('odds1_prev', ''))),
                    ('X', parse_odds(row.get('oddsx', '')), parse_odds(row.get('oddsx_prev', ''))),
                    ('2', parse_odds(row.get('odds2', '')), parse_odds(row.get('odds2_prev', '')))
                ]
            elif market == 'OU25':
                selections = [
                    ('O', parse_odds(row.get('over', '')), parse_odds(row.get('over_prev', ''))),
                    ('U', parse_odds(row.get('under', '')), parse_odds(row.get('under_prev', '')))
                ]
            else:
                selections = [
                    ('Y', parse_odds(row.get('oddsyes', '')), parse_odds(row.get('oddsyes_prev', ''))),
                    ('N', parse_odds(row.get('oddsno', '')), parse_odds(row.get('oddsno_prev', '')))
                ]
            
            for sel, current, opening in selections:
                if opening > 0 and current > 0:
                    drop_pct = ((opening - current) / opening) * 100
                    if drop_pct >= drop_threshold:
                        alarm = {
                            'match_id_hash': match_id_hash,
                            'home': row.get('home', '')[:100],
                            'away': row.get('away', '')[:100],
                            'league': row.get('league', '')[:150],
                            'market': market,
                            'selection': sel,
                            'opening_odds': opening,
                            'current_odds': current,
                            'drop_pct': round(drop_pct, 2)
                        }
                        alarms.append(alarm)
    
    return alarms

def calculate_volumeshock_alarms(shock_threshold: float = 3.0) -> list:
    """VolumeShock: Ortalamaya göre yüksek hacim"""
    alarms = []
    
    for table, market in [('moneyway_1x2', '1X2'), ('moneyway_ou25', 'OU25'), ('moneyway_btts', 'BTTS')]:
        data = fetch_data(table)
        
        if not data:
            continue
        
        if market == '1X2':
            all_amts = [parse_money(r.get('amt1', '')) + parse_money(r.get('amtx', '')) + parse_money(r.get('amt2', '')) for r in data]
        elif market == 'OU25':
            all_amts = [parse_money(r.get('amtover', '')) + parse_money(r.get('amtunder', '')) for r in data]
        else:
            all_amts = [parse_money(r.get('amtyes', '')) + parse_money(r.get('amtno', '')) for r in data]
        
        avg_volume = sum(all_amts) / len(all_amts) if all_amts else 1
        
        for row in data:
            kickoff = parse_date(row.get('date', ''))
            if not kickoff:
                continue
            
            if market == '1X2':
                total = parse_money(row.get('amt1', '')) + parse_money(row.get('amtx', '')) + parse_money(row.get('amt2', ''))
            elif market == 'OU25':
                total = parse_money(row.get('amtover', '')) + parse_money(row.get('amtunder', ''))
            else:
                total = parse_money(row.get('amtyes', '')) + parse_money(row.get('amtno', ''))
            
            shock_value = total / avg_volume if avg_volume > 0 else 0
            
            if shock_value >= shock_threshold:
                match_id_hash = make_match_id_hash(
                    row.get('home', ''),
                    row.get('away', ''),
                    row.get('league', ''),
                    kickoff
                )
                alarm = {
                    'match_id_hash': match_id_hash,
                    'home': row.get('home', '')[:100],
                    'away': row.get('away', '')[:100],
                    'league': row.get('league', '')[:150],
                    'market': market,
                    'selection': 'ALL',
                    'incoming_money': total,
                    'avg_previous': round(avg_volume, 2),
                    'volume_shock_value': round(shock_value, 2)
                }
                alarms.append(alarm)
    
    return alarms

def calculate_publicmove_alarms(pct_threshold: float = 80) -> list:
    """PublicMove: Tek tarafa yüksek yüzde"""
    alarms = []
    
    for table, market in [('moneyway_1x2', '1X2'), ('moneyway_ou25', 'OU25'), ('moneyway_btts', 'BTTS')]:
        data = fetch_data(table)
        
        for row in data:
            kickoff = parse_date(row.get('date', ''))
            if not kickoff:
                continue
            
            match_id_hash = make_match_id_hash(
                row.get('home', ''),
                row.get('away', ''),
                row.get('league', ''),
                kickoff
            )
            
            if market == '1X2':
                selections = [
                    ('1', parse_percent(row.get('pct1', ''))),
                    ('X', parse_percent(row.get('pctx', ''))),
                    ('2', parse_percent(row.get('pct2', '')))
                ]
            elif market == 'OU25':
                selections = [
                    ('O', parse_percent(row.get('pctover', ''))),
                    ('U', parse_percent(row.get('pctunder', '')))
                ]
            else:
                selections = [
                    ('Y', parse_percent(row.get('pctyes', ''))),
                    ('N', parse_percent(row.get('pctno', '')))
                ]
            
            for sel, pct in selections:
                if pct >= pct_threshold:
                    alarm = {
                        'match_id_hash': match_id_hash,
                        'home': row.get('home', '')[:100],
                        'away': row.get('away', '')[:100],
                        'league': row.get('league', '')[:150],
                        'market': market,
                        'selection': sel,
                        'public_pct': pct,
                        'volume': parse_money(row.get('volume', ''))
                    }
                    alarms.append(alarm)
    
    return alarms

def write_alarms_to_db(alarms: dict, dry_run: bool = False) -> dict:
    """Alarmları Supabase'e yaz"""
    results = {}
    
    table_map = {
        'bigmoney': 'bigmoney_alarms',
        'dropping': 'dropping_alarms',
        'volumeshock': 'volumeshock_alarms',
        'publicmove': 'publicmove_alarms'
    }
    
    for alarm_type, alarm_list in alarms.items():
        table = table_map.get(alarm_type)
        if not table or not alarm_list:
            continue
        
        success = 0
        failed = 0
        
        for alarm in alarm_list:
            if dry_run:
                success += 1
                continue
            
            r = requests.post(
                f'{SUPABASE_URL}/rest/v1/{table}',
                headers={**HEADERS, 'Prefer': 'resolution=merge-duplicates'},
                json=alarm,
                timeout=10
            )
            if r.status_code in [200, 201]:
                success += 1
            else:
                failed += 1
                if failed <= 3:
                    print(f"  HATA {table}: {r.status_code} - {r.text[:100]}")
        
        results[alarm_type] = {'success': success, 'failed': failed}
        print(f"{table}: {success} basarili, {failed} basarisiz")
    
    return results

def run_all_calculations(write_to_db: bool = False):
    print("=" * 60)
    print("ALARM CALCULATOR - Mevcut Verilerden Hesaplama")
    print("=" * 60)
    
    bigmoney = calculate_bigmoney_alarms(threshold=200)
    print(f"\nBigMoney alarms: {len(bigmoney)}")
    for a in bigmoney[:3]:
        print(f"  {a['home']} vs {a['away']} | {a['market']}-{a['selection']} | £{a['incoming_money']}")
    
    dropping = calculate_dropping_alarms(drop_threshold=5)
    print(f"\nDropping alarms: {len(dropping)}")
    for a in dropping[:3]:
        print(f"  {a['home']} vs {a['away']} | {a['market']}-{a['selection']} | {a['drop_pct']}%")
    
    volumeshock = calculate_volumeshock_alarms(shock_threshold=2.0)
    print(f"\nVolumeShock alarms: {len(volumeshock)}")
    for a in volumeshock[:3]:
        print(f"  {a['home']} vs {a['away']} | {a['market']} | x{a['volume_shock_value']}")
    
    publicmove = calculate_publicmove_alarms(pct_threshold=75)
    print(f"\nPublicMove alarms: {len(publicmove)}")
    for a in publicmove[:3]:
        print(f"  {a['home']} vs {a['away']} | {a['market']}-{a['selection']} | {a['public_pct']}%")
    
    print("\n" + "=" * 60)
    print("TOPLAM ALARM SAYILARI")
    print("=" * 60)
    print(f"BigMoney: {len(bigmoney)}")
    print(f"Dropping: {len(dropping)}")
    print(f"VolumeShock: {len(volumeshock)}")
    print(f"PublicMove: {len(publicmove)}")
    print(f"TOPLAM: {len(bigmoney) + len(dropping) + len(volumeshock) + len(publicmove)}")
    
    alarms = {
        'bigmoney': bigmoney,
        'dropping': dropping,
        'volumeshock': volumeshock,
        'publicmove': publicmove
    }
    
    if write_to_db:
        print("\n" + "=" * 60)
        print("SUPABASE'E YAZILIYOR...")
        print("=" * 60)
        write_alarms_to_db(alarms)
    
    return alarms

if __name__ == '__main__':
    import sys
    write = '--write' in sys.argv
    run_all_calculations(write_to_db=write)
