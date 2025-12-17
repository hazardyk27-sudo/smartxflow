#!/usr/bin/env python3
"""
ALARM CALCULATOR - Mevcut snapshot tablolarından alarm üretir
Threshold'lar alarm_settings tablosundan okunur
"""

import os
import re
import hashlib
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

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

SETTINGS_CACHE: Dict[str, Any] = {}

def fetch_alarm_settings() -> Dict[str, Dict]:
    """alarm_settings tablosundan tum ayarlari cek"""
    global SETTINGS_CACHE
    if SETTINGS_CACHE:
        return SETTINGS_CACHE
    
    r = requests.get(
        f'{SUPABASE_URL}/rest/v1/alarm_settings?select=*',
        headers={'apikey': SUPABASE_KEY, 'Authorization': f'Bearer {SUPABASE_KEY}'},
        timeout=10
    )
    if r.status_code == 200:
        for row in r.json():
            alarm_type = row.get('alarm_type', '')
            SETTINGS_CACHE[alarm_type] = {
                'enabled': row.get('enabled', True),
                'config': row.get('config', {})
            }
    print(f"Yuklenen alarm ayarlari: {list(SETTINGS_CACHE.keys())}")
    return SETTINGS_CACHE

def get_setting(alarm_type: str, key: str, default: Any = None) -> Any:
    """Belirli bir alarm turunden ayar al"""
    settings = fetch_alarm_settings()
    if alarm_type in settings:
        return settings[alarm_type].get('config', {}).get(key, default)
    return default

def is_enabled(alarm_type: str) -> bool:
    """Alarm turu aktif mi?"""
    settings = fetch_alarm_settings()
    if alarm_type in settings:
        return settings[alarm_type].get('enabled', True) is not False
    return True

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
    if not money_str:
        return 0.0
    clean = re.sub(r'[^\d.]', '', money_str.replace(' ', ''))
    try:
        return float(clean) if clean else 0.0
    except:
        return 0.0

def parse_percent(pct_str: str) -> float:
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

def calculate_bigmoney_alarms() -> list:
    """BigMoney: Yuksek para girisi olan maclar"""
    if not is_enabled('bigmoney'):
        print("BigMoney DEVRE DISI")
        return []
    
    threshold = get_setting('bigmoney', 'big_money_limit', 15000)
    print(f"BigMoney threshold: £{threshold}")
    
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
            
            total_volume = parse_money(row.get('volume', ''))
            
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
                        'total_selection': total_volume,
                        'is_huge': is_huge
                    }
                    alarms.append(alarm)
    
    return alarms

def calculate_dropping_alarms() -> list:
    """Dropping: Oran dususu yuksek olan maclar"""
    if not is_enabled('dropping'):
        print("Dropping DEVRE DISI")
        return []
    
    min_drop_l1 = get_setting('dropping', 'min_drop_l1', 8)
    min_drop_l2 = get_setting('dropping', 'min_drop_l2', 13)
    min_drop_l3 = get_setting('dropping', 'min_drop_l3', 20)
    max_odds_1x2 = get_setting('dropping', 'max_odds_1x2', 3.5)
    min_volume_1x2 = get_setting('dropping', 'min_volume_1x2', 1)
    
    print(f"Dropping thresholds: L1={min_drop_l1}%, L2={min_drop_l2}%, L3={min_drop_l3}%")
    
    alarms = []
    
    for table, market in [('dropping_1x2', '1X2'), ('dropping_ou25', 'OU25'), ('dropping_btts', 'BTTS')]:
        data = fetch_data(table)
        
        for row in data:
            kickoff = parse_date(row.get('date', ''))
            if not kickoff:
                continue
            
            total_volume = parse_money(row.get('volume', ''))
            if total_volume < min_volume_1x2:
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
                if opening <= 0 or current <= 0:
                    continue
                if current > max_odds_1x2:
                    continue
                
                drop_pct = ((opening - current) / opening) * 100
                
                level = None
                if drop_pct >= min_drop_l3:
                    level = 'L3'
                elif drop_pct >= min_drop_l2:
                    level = 'L2'
                elif drop_pct >= min_drop_l1:
                    level = 'L1'
                
                if level:
                    alarm = {
                        'match_id_hash': match_id_hash,
                        'home': row.get('home', '')[:100],
                        'away': row.get('away', '')[:100],
                        'league': row.get('league', '')[:150],
                        'market': market,
                        'selection': sel,
                        'opening_odds': opening,
                        'current_odds': current,
                        'drop_pct': round(drop_pct, 2),
                        'level': level
                    }
                    alarms.append(alarm)
    
    return alarms

def calculate_volumeshock_alarms() -> list:
    """VolumeShock: Ortalamaya gore yuksek hacim"""
    if not is_enabled('volumeshock'):
        print("VolumeShock DEVRE DISI")
        return []
    
    min_volume_1x2 = get_setting('volumeshock', 'min_volume_1x2', 999)
    min_volume_ou25 = get_setting('volumeshock', 'min_volume_ou25', 499)
    min_volume_btts = get_setting('volumeshock', 'min_volume_btts', 499)
    shock_threshold = get_setting('volumeshock', 'hacim_soku_min_esik', 100)
    
    print(f"VolumeShock: min_1x2={min_volume_1x2}, shock_threshold={shock_threshold}")
    
    alarms = []
    
    market_config = [
        ('moneyway_1x2', '1X2', min_volume_1x2),
        ('moneyway_ou25', 'OU25', min_volume_ou25),
        ('moneyway_btts', 'BTTS', min_volume_btts)
    ]
    
    for table, market, min_vol in market_config:
        data = fetch_data(table)
        
        if not data:
            continue
        
        all_volumes = [parse_money(r.get('volume', '')) for r in data]
        avg_volume = sum(all_volumes) / len(all_volumes) if all_volumes else 1
        
        for row in data:
            kickoff = parse_date(row.get('date', ''))
            if not kickoff:
                continue
            
            total_volume = parse_money(row.get('volume', ''))
            if total_volume < min_vol:
                continue
            
            shock_value = (total_volume / avg_volume * 100) if avg_volume > 0 else 0
            
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
                    'incoming_money': total_volume,
                    'avg_previous': round(avg_volume, 2),
                    'volume_shock_value': round(shock_value, 2)
                }
                alarms.append(alarm)
    
    return alarms

def calculate_publicmove_alarms() -> list:
    """PublicMove: Tek tarafa yuksek yuzde"""
    if not is_enabled('publicmove'):
        print("PublicMove DEVRE DISI")
        return []
    
    min_volume_1x2 = get_setting('publicmove', 'min_volume_1x2', 2999)
    min_volume_ou25 = get_setting('publicmove', 'min_volume_ou25', 1499)
    min_volume_btts = get_setting('publicmove', 'min_volume_btts', 999)
    min_sharp_score = get_setting('publicmove', 'min_sharp_score', 60)
    
    print(f"PublicMove: min_1x2={min_volume_1x2}, min_score={min_sharp_score}")
    
    alarms = []
    
    market_config = [
        ('moneyway_1x2', '1X2', min_volume_1x2),
        ('moneyway_ou25', 'OU25', min_volume_ou25),
        ('moneyway_btts', 'BTTS', min_volume_btts)
    ]
    
    for table, market, min_vol in market_config:
        data = fetch_data(table)
        
        for row in data:
            kickoff = parse_date(row.get('date', ''))
            if not kickoff:
                continue
            
            total_volume = parse_money(row.get('volume', ''))
            if total_volume < min_vol:
                continue
            
            match_id_hash = make_match_id_hash(
                row.get('home', ''),
                row.get('away', ''),
                row.get('league', ''),
                kickoff
            )
            
            if market == '1X2':
                selections = [
                    ('1', parse_percent(row.get('pct1', '')), parse_money(row.get('amt1', ''))),
                    ('X', parse_percent(row.get('pctx', '')), parse_money(row.get('amtx', ''))),
                    ('2', parse_percent(row.get('pct2', '')), parse_money(row.get('amt2', '')))
                ]
            elif market == 'OU25':
                selections = [
                    ('O', parse_percent(row.get('pctover', '')), parse_money(row.get('amtover', ''))),
                    ('U', parse_percent(row.get('pctunder', '')), parse_money(row.get('amtunder', '')))
                ]
            else:
                selections = [
                    ('Y', parse_percent(row.get('pctyes', '')), parse_money(row.get('amtyes', ''))),
                    ('N', parse_percent(row.get('pctno', '')), parse_money(row.get('amtno', '')))
                ]
            
            for sel, pct, amt in selections:
                if pct >= min_sharp_score:
                    alarm = {
                        'match_id_hash': match_id_hash,
                        'home': row.get('home', '')[:100],
                        'away': row.get('away', '')[:100],
                        'league': row.get('league', '')[:150],
                        'market': market,
                        'selection': sel,
                        'public_pct': pct,
                        'volume': total_volume
                    }
                    alarms.append(alarm)
    
    return alarms

def calculate_mim_alarms() -> list:
    """MIM (Money In Market): Secenege gelen para / mac market hacmi >= threshold"""
    if not is_enabled('mim'):
        print("MIM DEVRE DISI")
        return []
    
    min_prev_volume = get_setting('mim', 'min_prev_volume', 3000)
    min_impact = get_setting('mim', 'min_impact_threshold', 0.1)
    
    print(f"MIM: min_prev_volume={min_prev_volume}, min_impact={min_impact}")
    
    alarms = []
    
    for table, market in [('moneyway_1x2', '1X2'), ('moneyway_ou25', 'OU25'), ('moneyway_btts', 'BTTS')]:
        data = fetch_data(table)
        
        if not data:
            continue
        
        for row in data:
            kickoff = parse_date(row.get('date', ''))
            if not kickoff:
                continue
            
            match_volume = parse_money(row.get('volume', ''))
            if match_volume < min_prev_volume:
                continue
            
            if market == '1X2':
                selections = [
                    ('1', parse_money(row.get('amt1', ''))),
                    ('X', parse_money(row.get('amtx', ''))),
                    ('2', parse_money(row.get('amt2', '')))
                ]
            elif market == 'OU25':
                selections = [
                    ('O', parse_money(row.get('amtover', ''))),
                    ('U', parse_money(row.get('amtunder', '')))
                ]
            else:
                selections = [
                    ('Y', parse_money(row.get('amtyes', ''))),
                    ('N', parse_money(row.get('amtno', '')))
                ]
            
            for sel, sel_amount in selections:
                if sel_amount < 1500:
                    continue
                
                impact = sel_amount / match_volume if match_volume > 0 else 0
                
                if impact >= min_impact:
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
                        'selection': sel,
                        'selection_amount': sel_amount,
                        'match_volume': match_volume,
                        'impact_pct': round(impact * 100, 2)
                    }
                    alarms.append(alarm)
    
    return alarms

def calculate_volumeleader_alarms() -> list:
    """VolumeLeader: En yuksek hacimli maclar"""
    if not is_enabled('volumeleader'):
        print("VolumeLeader DEVRE DISI")
        return []
    
    min_volume_1x2 = get_setting('volumeleader', 'min_volume_1x2', 2999)
    leader_threshold = get_setting('volumeleader', 'leader_threshold', 50)
    
    print(f"VolumeLeader: min_1x2={min_volume_1x2}, threshold={leader_threshold}")
    
    alarms = []
    
    for table, market in [('moneyway_1x2', '1X2'), ('moneyway_ou25', 'OU25'), ('moneyway_btts', 'BTTS')]:
        data = fetch_data(table)
        
        if not data:
            continue
        
        volumes = [(row, parse_money(row.get('volume', ''))) for row in data]
        volumes.sort(key=lambda x: x[1], reverse=True)
        
        top_count = max(1, int(len(volumes) * leader_threshold / 100))
        
        for row, vol in volumes[:top_count]:
            if vol < min_volume_1x2:
                continue
            
            kickoff = parse_date(row.get('date', ''))
            if not kickoff:
                continue
            
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
                'total_volume': vol
            }
            alarms.append(alarm)
    
    return alarms

def write_alarms_to_db(alarms: dict, dry_run: bool = False) -> dict:
    """Alarmlari Supabase'e yaz"""
    results = {}
    
    table_map = {
        'bigmoney': 'bigmoney_alarms',
        'dropping': 'dropping_alarms',
        'volumeshock': 'volumeshock_alarms',
        'publicmove': 'publicmove_alarms',
        'volumeleader': 'volumeleader_alarms',
        'mim': 'mim_alarms'
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
    print("ALARM CALCULATOR - alarm_settings'den Threshold Okuma")
    print("=" * 60)
    
    fetch_alarm_settings()
    
    bigmoney = calculate_bigmoney_alarms()
    print(f"\nBigMoney alarms: {len(bigmoney)}")
    for a in bigmoney[:3]:
        print(f"  {a['home']} vs {a['away']} | {a['market']}-{a['selection']} | £{a['incoming_money']}")
    
    dropping = calculate_dropping_alarms()
    print(f"\nDropping alarms: {len(dropping)}")
    for a in dropping[:3]:
        print(f"  {a['home']} vs {a['away']} | {a['market']}-{a['selection']} | {a['drop_pct']}% ({a.get('level', '?')})")
    
    volumeshock = calculate_volumeshock_alarms()
    print(f"\nVolumeShock alarms: {len(volumeshock)}")
    for a in volumeshock[:3]:
        print(f"  {a['home']} vs {a['away']} | {a['market']} | {a['volume_shock_value']}%")
    
    publicmove = calculate_publicmove_alarms()
    print(f"\nPublicMove alarms: {len(publicmove)}")
    for a in publicmove[:3]:
        print(f"  {a['home']} vs {a['away']} | {a['market']}-{a['selection']} | {a['public_pct']}%")
    
    volumeleader = calculate_volumeleader_alarms()
    print(f"\nVolumeLeader alarms: {len(volumeleader)}")
    for a in volumeleader[:3]:
        print(f"  {a['home']} vs {a['away']} | {a['market']} | £{a['total_volume']}")
    
    mim = calculate_mim_alarms()
    print(f"\nMIM alarms: {len(mim)}")
    for a in mim[:3]:
        print(f"  {a['home']} vs {a['away']} | {a['market']}-{a['selection']} | £{a['selection_amount']} / £{a['match_volume']} = {a['impact_pct']}%")
    
    print("\n" + "=" * 60)
    print("TOPLAM ALARM SAYILARI")
    print("=" * 60)
    total = len(bigmoney) + len(dropping) + len(volumeshock) + len(publicmove) + len(volumeleader) + len(mim)
    print(f"BigMoney: {len(bigmoney)}")
    print(f"Dropping: {len(dropping)}")
    print(f"VolumeShock: {len(volumeshock)}")
    print(f"PublicMove: {len(publicmove)}")
    print(f"VolumeLeader: {len(volumeleader)}")
    print(f"MIM: {len(mim)}")
    print(f"TOPLAM: {total}")
    
    alarms = {
        'bigmoney': bigmoney,
        'dropping': dropping,
        'volumeshock': volumeshock,
        'publicmove': publicmove,
        'volumeleader': volumeleader,
        'mim': mim
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
