#!/usr/bin/env python3
"""
ALARM CALCULATOR - Mevcut snapshot tablolarından alarm üretir
Threshold'lar alarm_settings tablosundan okunur
"""

import os
import re
import hashlib
import requests
from urllib.parse import quote
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY')
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')

HEADERS_READ = {
    'apikey': SUPABASE_ANON_KEY,
    'Authorization': f'Bearer {SUPABASE_ANON_KEY}',
    'Content-Type': 'application/json'
}

HEADERS_WRITE = {
    'apikey': SUPABASE_SERVICE_KEY,
    'Authorization': f'Bearer {SUPABASE_SERVICE_KEY}',
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
        headers=HEADERS_READ,
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

def fetch_data(table: str, limit: int = 20000) -> list:
    """Veri çek - pagination ile tüm veriyi al"""
    all_data = []
    page_size = 1000  # Her seferde 1000 kayıt
    offset = 0
    
    while offset < limit:
        batch_limit = min(page_size, limit - offset)
        r = requests.get(
            f'{SUPABASE_URL}/rest/v1/{table}?select=*&order=id.desc&limit={batch_limit}&offset={offset}',
            headers=HEADERS_READ,
            timeout=30
        )
        if r.status_code != 200:
            break
        batch = r.json()
        if not batch:
            break
        all_data.extend(batch)
        offset += len(batch)
        if len(batch) < batch_limit:
            break
    
    return all_data

def fetch_all_data(table: str, page_size: int = 1000) -> list:
    """Tum veriyi pagination ile cek"""
    all_data = []
    offset = 0
    while True:
        r = requests.get(
            f'{SUPABASE_URL}/rest/v1/{table}?select=*&order=id.desc&limit={page_size}&offset={offset}',
            headers=HEADERS_READ,
            timeout=30
        )
        if r.status_code != 200:
            break
        batch = r.json()
        if not batch:
            break
        all_data.extend(batch)
        offset += page_size
        if len(batch) < page_size:
            break
    return all_data

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
                    alarm = {
                        'match_id_hash': match_id_hash,
                        'home': row.get('home', '')[:100],
                        'away': row.get('away', '')[:100],
                        'league': row.get('league', '')[:150],
                        'market': market,
                        'selection': sel,
                        'incoming_money': amt,            # DB kolon adı
                        'trigger_at': datetime.utcnow().isoformat()
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
                        'opening_odds': opening,            # DB kolon adı
                        'current_odds': current,            # DB kolon adı
                        'drop_pct': round(drop_pct, 2),     # DB kolon adı
                        'trigger_at': datetime.utcnow().isoformat()
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
                    'incoming_money': total_volume,              # DB kolon adı
                    'avg_previous': round(avg_volume, 2),        # DB kolon adı
                    'volume_shock_value': round(shock_value, 2), # DB kolon adı
                    'trigger_at': datetime.utcnow().isoformat()
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
                        'odds_direction': 'up' if pct > 50 else 'down',  # DB kolon adı
                        'share_direction': 'high',                       # DB kolon adı
                        'current_odds': 0.0,                             # DB kolon adı
                        'current_share': pct,                            # DB kolon adı (public yüzdesi)
                        'trigger_at': datetime.utcnow().isoformat()
                    }
                    alarms.append(alarm)
    
    return alarms

# MIM Cache - TTL 10 dakika (aligned with bucket size)
_mim_cache = {}
_mim_cache_ttl = 600  # 10 dakika (bucket size ile aynı)
_mim_cache_max_size = 1000  # Max cache entries
_mim_cache_last_cleanup = 0

def _cleanup_mim_cache():
    """Expired entries ve size limit cleanup"""
    global _mim_cache, _mim_cache_last_cleanup
    import time
    now = time.time()
    
    # Cleanup her 60 saniyede bir
    if now - _mim_cache_last_cleanup < 60:
        return
    _mim_cache_last_cleanup = now
    
    # Expired entries sil
    expired_keys = [k for k, (data, ts) in _mim_cache.items() if now - ts >= _mim_cache_ttl]
    for k in expired_keys:
        del _mim_cache[k]
    
    # Size limit aşıldıysa tam olarak max_size'a düşür
    if len(_mim_cache) > _mim_cache_max_size:
        sorted_items = sorted(_mim_cache.items(), key=lambda x: x[1][1])
        to_remove = len(_mim_cache) - _mim_cache_max_size
        for k, _ in sorted_items[:to_remove]:
            del _mim_cache[k]

def _get_mim_cache_key(hist_table: str, home: str, away: str) -> str:
    """MIM cache key üret - bucket size = TTL = 10 dakika"""
    import time
    bucket = int(time.time() // 600) * 600  # 10 dakikalık bucket
    return f"{hist_table}:{home}:{away}:{bucket}"

def _get_from_mim_cache(key: str):
    """Cache'den veri al"""
    import time
    _cleanup_mim_cache()  # Periodic cleanup
    if key in _mim_cache:
        data, timestamp = _mim_cache[key]
        if time.time() - timestamp < _mim_cache_ttl:
            return data
        del _mim_cache[key]
    return None

def _set_mim_cache(key: str, data):
    """Cache'e veri yaz"""
    import time
    _mim_cache[key] = (data, time.time())
    _cleanup_mim_cache()  # Size limit kontrolü


def calculate_mim_alarms() -> list:
    """
    MIM (Money In Market) = market_total / incoming
    incoming = amt_now - amt_prev (2 snapshot arası fark)
    
    MIM düşükse → güçlü hareket (alarm tetiklenir)
    Şartlar:
    - incoming >= mim_min_incoming (default 300)
    - market_total >= mim_min_market_total (default 1000)
    - mim_value <= mim_max_ratio (default 12)
    
    Sadece en yüksek incoming olan selection için hesapla
    
    OPTIMIZASYON: Cache + Concurrency limit (max 5 paralel istek)
    """
    if not is_enabled('mim'):
        print("MIM DEVRE DISI")
        return []
    
    mim_min_incoming = get_setting('mim', 'mim_min_incoming', 300)
    mim_min_market_total = get_setting('mim', 'mim_min_market_total', 1000)
    mim_max_ratio = get_setting('mim', 'mim_max_ratio', 0.10)  # 10% - yüksek MIM = güçlü hareket
    
    print(f"MIM: min_incoming={mim_min_incoming}, min_market_total={mim_min_market_total}, max_ratio={mim_max_ratio}")
    
    alarms = []
    cache_hits = 0
    cache_misses = 0
    
    # Benzersiz maç listesini ana tablodan çek
    for main_table, hist_table, market in [
        ('moneyway_1x2', 'moneyway_1x2_history', '1X2'), 
        ('moneyway_ou25', 'moneyway_ou25_history', 'OU25'), 
        ('moneyway_btts', 'moneyway_btts_history', 'BTTS')
    ]:
        # Ana tablodan aktif maçları çek
        matches = fetch_data(main_table, limit=500)
        print(f"  {market}: {len(matches)} aktif mac")
        
        if not matches:
            continue
        
        mim_count = 0
        for match in matches:
            home = match.get('home', '')
            away = match.get('away', '')
            
            if not home or not away:
                continue
            
            # Cache kontrolü
            cache_key = _get_mim_cache_key(hist_table, home, away)
            cached_snapshots = _get_from_mim_cache(cache_key)
            
            if cached_snapshots is not None:
                snapshots = cached_snapshots
                cache_hits += 1
            else:
                # Bu maç için son 20 history snapshot'ı çek (farklı değer bulmak için)
                try:
                    r = requests.get(
                        f'{SUPABASE_URL}/rest/v1/{hist_table}?select=*&home=eq.{quote(home)}&away=eq.{quote(away)}&order=scraped_at.desc&limit=20',
                        headers=HEADERS_READ,
                        timeout=10  # Timeout düşürüldü
                    )
                    if r.status_code == 200:
                        snapshots = r.json()
                        _set_mim_cache(cache_key, snapshots)
                        cache_misses += 1
                    else:
                        continue
                except requests.exceptions.Timeout:
                    continue
                except Exception:
                    continue
            
            if len(snapshots) < 2:
                continue
            
            curr_row = snapshots[0]  # En yeni
            
            # Farklı değere sahip önceki snapshot bul
            prev_row = None
            curr_vol = parse_money(curr_row.get('volume', ''))
            for snap in snapshots[1:]:
                snap_vol = parse_money(snap.get('volume', ''))
                if snap_vol != curr_vol:  # Farklı volume = farklı snapshot
                    prev_row = snap
                    break
            
            if not prev_row:
                continue
            
            kickoff = parse_date(curr_row.get('date', ''))
            
            if market == '1X2':
                selections = [('1', 'amt1'), ('X', 'amtx'), ('2', 'amt2')]
                market_total = (parse_money(curr_row.get('amt1', '')) + 
                               parse_money(curr_row.get('amtx', '')) + 
                               parse_money(curr_row.get('amt2', '')))
            elif market == 'OU25':
                selections = [('O', 'amtover'), ('U', 'amtunder')]
                market_total = (parse_money(curr_row.get('amtover', '')) + 
                               parse_money(curr_row.get('amtunder', '')))
            else:
                selections = [('Y', 'amtyes'), ('N', 'amtno')]
                market_total = (parse_money(curr_row.get('amtyes', '')) + 
                               parse_money(curr_row.get('amtno', '')))
            
            if market_total < mim_min_market_total:
                continue
            
            # Her selection için incoming hesapla
            incoming_list = []
            for sel, field in selections:
                amt_now = parse_money(curr_row.get(field, ''))
                amt_prev = parse_money(prev_row.get(field, ''))
                incoming = amt_now - amt_prev
                if incoming > 0:
                    incoming_list.append((sel, incoming, amt_now))
            
            if not incoming_list:
                continue
            
            # En yüksek incoming olan selection'ı bul
            incoming_list.sort(key=lambda x: x[1], reverse=True)
            best_sel, best_incoming, best_amt = incoming_list[0]
            
            if best_incoming < mim_min_incoming:
                continue
            
            # MIM hesapla: incoming / market_total
            # Örnek: £1,000 / £10,000 = 0.10 (10%)
            mim_value = best_incoming / market_total
            
            if mim_value >= mim_max_ratio:  # Yüksek MIM = güçlü hareket = alarm
                match_id_hash = make_match_id_hash(home, away, curr_row.get('league', ''), kickoff or '')
                alarm = {
                    'match_id_hash': match_id_hash,
                    'home': home[:100],
                    'away': away[:100],
                    'league': curr_row.get('league', '')[:150],
                    'market': market,
                    'selection': best_sel,
                    'prev_volume': market_total,       # DB kolon adı
                    'curr_volume': best_incoming,      # DB kolon adı
                    'impact_value': round(mim_value, 4),  # DB kolon adı (MIM değeri)
                    'trigger_at': datetime.utcnow().isoformat()
                }
                alarms.append(alarm)
                mim_count += 1
        
        print(f"  {market}: {mim_count} MIM alarm")
    
    print(f"  MIM Cache: {cache_hits} hit, {cache_misses} miss")
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
                'old_leader': '',                                    # DB kolon adı
                'new_leader': row.get('home', '')[:50],              # En yüksek hacimli maç
                'old_leader_share': 0.0,                             # DB kolon adı
                'new_leader_share': min(round(vol / 1000, 2), 999.99),  # K cinsinden (max 999.99)
                'trigger_at': datetime.utcnow().isoformat()
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
                headers={**HEADERS_WRITE, 'Prefer': 'resolution=merge-duplicates'},
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
        print(f"  {a['home']} vs {a['away']} | {a['market']}-{a['selection']} | {a['drop_pct']}%")
    
    volumeshock = calculate_volumeshock_alarms()
    print(f"\nVolumeShock alarms: {len(volumeshock)}")
    for a in volumeshock[:3]:
        print(f"  {a['home']} vs {a['away']} | {a['market']} | {a['volume_shock_value']}%")
    
    publicmove = calculate_publicmove_alarms()
    print(f"\nPublicMove alarms: {len(publicmove)}")
    for a in publicmove[:3]:
        print(f"  {a['home']} vs {a['away']} | {a['market']}-{a['selection']} | {a['current_share']}%")
    
    volumeleader = calculate_volumeleader_alarms()
    print(f"\nVolumeLeader alarms: {len(volumeleader)}")
    for a in volumeleader[:3]:
        print(f"  {a['home']} vs {a['away']} | {a['market']} | {a['old_leader']} -> {a['new_leader']}")
    
    mim = calculate_mim_alarms()
    print(f"\nMIM alarms: {len(mim)}")
    for a in mim[:3]:
        print(f"  {a['home']} vs {a['away']} | {a['market']}-{a['selection']} | MIM={a['impact_value']} (prev={a['prev_volume']} / curr={a['curr_volume']})")
    
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
