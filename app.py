"""
SmartXFlow - Betting Odds Monitor
Flask Web Application with modern dark theme UI
Build: 2025-11-28

Mode-aware architecture:
- SERVER mode (Replit): Runs scraper, writes to SQLite, syncs to Supabase
- CLIENT mode (EXE): Only reads from Supabase, no scraping
"""

import os
import sys
import json
import threading
import time
import queue
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, Response

# ============================================
# SERVER-SIDE ALARM CACHE
# Reduces Supabase calls from ~2s to <50ms
# ============================================
_server_alarm_cache = None
_server_alarm_cache_time = 0
SERVER_ALARM_CACHE_TTL = 60  # 60 seconds cache - Supabase istek optimizasyonu

def get_cached_alarms(force_refresh=False):
    """Get alarms from server-side cache or refresh from Supabase"""
    global _server_alarm_cache, _server_alarm_cache_time
    
    now = time.time()
    
    if not force_refresh and _server_alarm_cache and (now - _server_alarm_cache_time) < SERVER_ALARM_CACHE_TTL:
        return _server_alarm_cache, True  # data, from_cache
    
    return None, False

def set_alarm_cache(data):
    """Update server-side alarm cache"""
    global _server_alarm_cache, _server_alarm_cache_time
    _server_alarm_cache = data
    _server_alarm_cache_time = time.time()
# ============================================

# ============================================
# SERVER-SIDE MATCHES CACHE
# Loads all matches instantly on cache hit
# ============================================
_server_matches_cache = {}  # {market: data}
_server_matches_cache_time = {}  # {market: timestamp}
SERVER_MATCHES_CACHE_TTL = 60  # 60 seconds cache - Supabase istek optimizasyonu

def get_cached_matches(market, force_refresh=False):
    """Get matches from server-side cache"""
    global _server_matches_cache, _server_matches_cache_time
    
    now = time.time()
    cache_time = _server_matches_cache_time.get(market, 0)
    
    if not force_refresh and market in _server_matches_cache and (now - cache_time) < SERVER_MATCHES_CACHE_TTL:
        return _server_matches_cache[market], True
    
    return None, False

def set_matches_cache(market, data):
    """Update server-side matches cache"""
    global _server_matches_cache, _server_matches_cache_time
    _server_matches_cache[market] = data
    _server_matches_cache_time[market] = time.time()
# ============================================

# ============================================
# SERVER-SIDE MATCH HISTORY CACHE
# Modal 2. acilista anlik yukleme icin
# ============================================
_server_history_cache = {}  # {match_key: data}
_server_history_cache_time = {}  # {match_key: timestamp}
SERVER_HISTORY_CACHE_TTL = 60  # 60 seconds cache

def get_cached_history(match_key, force_refresh=False):
    """Get match history from server-side cache"""
    global _server_history_cache, _server_history_cache_time
    
    now = time.time()
    cache_time = _server_history_cache_time.get(match_key, 0)
    
    if not force_refresh and match_key in _server_history_cache and (now - cache_time) < SERVER_HISTORY_CACHE_TTL:
        return _server_history_cache[match_key], True
    
    return None, False

def set_history_cache(match_key, data):
    """Update server-side match history cache"""
    global _server_history_cache, _server_history_cache_time
    _server_history_cache[match_key] = data
    _server_history_cache_time[match_key] = time.time()
# ============================================

def resource_path(relative_path):
    """Get absolute path to resource - works for dev and PyInstaller EXE"""
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

template_dir = resource_path("templates")
static_dir = resource_path("static")

from core.settings import init_mode, is_server_mode, is_client_mode, get_scrape_interval_seconds, is_scraper_disabled
from core.timezone import now_turkey, now_turkey_iso, now_turkey_formatted, format_turkey_time, format_time_only, TURKEY_TZ
from services.supabase_client import (
    get_database, get_supabase_client,
    get_sharp_alarms_from_supabase,
    get_bigmoney_alarms_from_supabase, get_volumeshock_alarms_from_supabase,
    get_dropping_alarms_from_supabase,
    get_volumeleader_alarms_from_supabase, get_mim_alarms_from_supabase,
    delete_alarms_from_supabase,
    write_sharp_alarms_to_supabase,
    write_volumeleader_alarms_to_supabase,
    write_bigmoney_alarms_to_supabase, write_dropping_alarms_to_supabase,
    write_volumeshock_alarms_to_supabase
)
import hashlib
import re

def normalize_field(value):
    """
    Normalize a field value for match_id_hash generation.
    Rules (per replit.md contract - core/hash_utils.py ile UYUMLU):
    - trim (strip leading/trailing whitespace)
    - Turkish character normalization BEFORE lowercase
    - lowercase
    - Remove special characters (only letters, numbers, spaces)
    - collapse multiple spaces to single space
    - Remove suffixes (FC, FK, SK, etc.)
    """
    if not value:
        return ""
    value = str(value).strip()
    
    # Turkish character normalization (core/hash_utils.py ile ayni)
    tr_map = {
        'ş': 's', 'Ş': 'S',
        'ğ': 'g', 'Ğ': 'G',
        'ü': 'u', 'Ü': 'U',
        'ı': 'i', 'İ': 'I',
        'ö': 'o', 'Ö': 'O',
        'ç': 'c', 'Ç': 'C'
    }
    for tr_char, en_char in tr_map.items():
        value = value.replace(tr_char, en_char)
    
    value = value.lower()
    
    # Remove special characters (only letters, numbers, spaces)
    value = re.sub(r'[^a-z0-9\s]', '', value)
    value = ' '.join(value.split())
    
    # Remove suffixes (FC, FK, SK, etc.)
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

def normalize_kickoff(kickoff):
    """
    Normalize kickoff time for match_id_hash generation.
    Rules (per replit.md contract):
    - Must be UTC timezone
    - Output format: YYYY-MM-DDTHH:MM (minute precision, no seconds)
    - Strips ALL timezone suffixes (Z, +00:00, +03:00, etc.)
    """
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

def generate_match_id(home, away, league, kickoff=''):
    """
    Generate unique 12-character match ID hash.
    
    IMMUTABLE CONTRACT (per replit.md):
    - Format: league|home|away (kickoff KULLANILMIYOR)
    - Hash: MD5, first 12 hex characters
    - All fields normalized via normalize_field()
    
    NOT: kickoff parametresi geriye uyumluluk icin tutuldu ama KULLANILMIYOR.
    This ensures: Scraper, Admin.exe, Backend all generate same hash for same match.
    """
    home_norm = normalize_field(home)
    away_norm = normalize_field(away)
    league_norm = normalize_field(league)
    
    canonical = f"{league_norm}|{home_norm}|{away_norm}"
    
    return hashlib.md5(canonical.encode('utf-8')).hexdigest()[:12]

def parse_created_at_for_sort(created_at_str):
    """Parse created_at string (DD.MM.YYYY HH:MM) to datetime for sorting.
    Returns a very old date if parsing fails (to put invalid entries at end)."""
    try:
        if not created_at_str:
            return datetime(1970, 1, 1)
        return datetime.strptime(created_at_str, '%d.%m.%Y %H:%M')
    except:
        return datetime(1970, 1, 1)

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.secret_key = os.environ.get('SESSION_SECRET', 'smartxflow-secret-key')

current_mode = init_mode()
db = get_database()

if is_server_mode():
    from scraper.core import run_scraper, get_cookie_string
else:
    def run_scraper(*args, **kwargs):
        return {'status': 'disabled', 'message': 'Scraping disabled in client mode'}
    def get_cookie_string():
        return None

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

scrape_status = {
    "running": False,
    "auto_running": False,
    "last_result": None,
    "last_scrape_time": None,
    "next_scrape_time": None,
    "interval_minutes": 10,
    "last_supabase_sync": None
}

auto_scrape_thread = None
stop_auto_event = threading.Event()
server_scheduler_thread = None
server_scheduler_stop = threading.Event()
cleanup_thread = None
alarm_scheduler_thread = None
last_cleanup_date = None
last_alarm_calc_time = None


def cleanup_old_matches():
    """
    Delete matches older than yesterday (keep today and yesterday only).
    D-2+ maçların history kayıtları silinir.
    Runs once per day on server startup or scheduler.
    """
    global last_cleanup_date
    
    today = now_turkey().date()
    if last_cleanup_date == today:
        return
    
    last_cleanup_date = today
    
    # D-2 = Dünden önceki gün (silinecek)
    cutoff = today - timedelta(days=2)
    cutoff_str = cutoff.strftime('%Y-%m-%d')
    
    print(f"[Cleanup] Starting cleanup for matches before {cutoff_str}...")
    
    try:
        supabase = get_supabase_client()
        if supabase and supabase.is_available:
            deleted = supabase.cleanup_old_matches(cutoff_str)
            total = sum(deleted.values())
            if total > 0:
                print(f"[Cleanup] Deleted {total} old records from {len(deleted)} tables")
            else:
                print(f"[Cleanup] No old records to delete")
        else:
            print(f"[Cleanup] Supabase not available, skipping cleanup")
    except Exception as e:
        print(f"[Cleanup] Error: {e}")
    
    print(f"[Cleanup] Old matches cleanup completed for {today}")


def start_cleanup_scheduler():
    """Start daily cleanup scheduler for old matches - runs at 05:00 Turkey time"""
    global cleanup_thread
    
    def cleanup_loop():
        # İlk başlatmada bir kez çalıştır
        cleanup_old_matches()
        
        while True:
            # Şu anki Türkiye saatini al
            now = now_turkey()
            
            # Yarın saat 05:00'i hesapla
            tomorrow_5am = now.replace(hour=5, minute=0, second=0, microsecond=0)
            if now.hour >= 5:
                # Saat 5'i geçtiyse, yarın 05:00
                tomorrow_5am = tomorrow_5am + timedelta(days=1)
            
            # Beklenecek süre (saniye)
            wait_seconds = (tomorrow_5am - now).total_seconds()
            
            # En az 60 saniye bekle (rapid loop önleme)
            wait_seconds = max(60, wait_seconds)
            
            print(f"[Cleanup Scheduler] Next cleanup at 05:00 Turkey time, waiting {wait_seconds/3600:.1f} hours")
            time.sleep(wait_seconds)
            
            # Cleanup çalıştır
            cleanup_old_matches()
    
    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()


def run_alarm_calculations():
    """Run all alarm calculations"""
    global sharp_alarms, big_money_alarms, volume_shock_alarms, last_alarm_calc_time
    
    try:
        print(f"[Alarm Scheduler] Starting alarm calculations at {now_turkey_iso()}")
        
        # LIVE RELOAD: Refresh configs from Supabase before calculations
        refresh_configs_from_supabase()
        
        # Sharp alarms
        try:
            new_sharp = calculate_sharp_scores(sharp_config)
            if new_sharp:
                sharp_alarms = new_sharp
                save_sharp_alarms_to_file(sharp_alarms)
                print(f"[Alarm Scheduler] Sharp: {len(sharp_alarms)} alarms")
        except Exception as e:
            print(f"[Alarm Scheduler] Sharp error: {e}")
        
        # Big Money alarms
        try:
            new_bigmoney = calculate_big_money_scores(big_money_config)
            if new_bigmoney:
                big_money_alarms = new_bigmoney
                save_big_money_alarms_to_file(big_money_alarms)
                print(f"[Alarm Scheduler] BigMoney: {len(big_money_alarms)} alarms")
        except Exception as e:
            print(f"[Alarm Scheduler] BigMoney error: {e}")
        
        # Volume Shock alarms
        try:
            new_volumeshock = calculate_volume_shock_scores(volume_shock_config)
            if new_volumeshock:
                volume_shock_alarms = new_volumeshock
                save_volume_shock_alarms_to_file(volume_shock_alarms)
                print(f"[Alarm Scheduler] VolumeShock: {len(volume_shock_alarms)} alarms")
        except Exception as e:
            print(f"[Alarm Scheduler] VolumeShock error: {e}")
        
        # Dropping alarms - uses global dropping_config (refreshed from Supabase)
        try:
            new_dropping = calculate_dropping_scores(dropping_config)
            if new_dropping:
                global dropping_alarms
                dropping_alarms = new_dropping
                save_dropping_alarms_to_file(dropping_alarms)
                print(f"[Alarm Scheduler] Dropping: {len(dropping_alarms)} alarms")
        except Exception as e:
            print(f"[Alarm Scheduler] Dropping error: {e}")
        
        # PublicMove (Public Move) alarms
        try:
            global publicmove_alarms
            new_publicmove = calculate_publicmove_scores(publicmove_config)
            if new_publicmove:
                publicmove_alarms = new_publicmove
                save_publicmove_alarms_to_file(publicmove_alarms)
            print(f"[Alarm Scheduler] PublicMove: {len(publicmove_alarms)} alarms")
        except Exception as e:
            print(f"[Alarm Scheduler] PublicMove error: {e}")
        
        # VolumeLeader alarms
        try:
            global volume_leader_alarms
            new_volumeleader = calculate_volume_leader_scores(volume_leader_config)
            if new_volumeleader:
                # Merge with existing alarms
                existing_keys = set()
                for alarm in volume_leader_alarms:
                    key = f"{alarm.get('home', '')}_{alarm.get('away', '')}_{alarm.get('market', '')}_{alarm.get('old_leader', '')}_{alarm.get('new_leader', '')}"
                    existing_keys.add(key)
                
                for alarm in new_volumeleader:
                    key = f"{alarm.get('home', '')}_{alarm.get('away', '')}_{alarm.get('market', '')}_{alarm.get('old_leader', '')}_{alarm.get('new_leader', '')}"
                    if key not in existing_keys:
                        volume_leader_alarms.append(alarm)
                        existing_keys.add(key)
                
                save_volume_leader_alarms_to_file(volume_leader_alarms)
            print(f"[Alarm Scheduler] VolumeLeader: {len(volume_leader_alarms)} alarms")
        except Exception as e:
            print(f"[Alarm Scheduler] VolumeLeader error: {e}")
        
        last_alarm_calc_time = now_turkey_iso()
        print(f"[Alarm Scheduler] Completed at {last_alarm_calc_time}")
        
    except Exception as e:
        print(f"[Alarm Scheduler] Error: {e}")


def start_alarm_scheduler():
    """Start periodic alarm calculation scheduler
    
    DISABLED: Alarm calculation is handled by Admin Panel via scraper_signal.
    Web App only reads alarms from Supabase.
    """
    print("[Alarm Scheduler] DISABLED - Alarms calculated by Admin Panel")
    print("[Alarm Scheduler] Signal flow: Scraper -> scraper_signal -> Admin Panel")
    return


def start_server_scheduler():
    """Start background scheduler for server mode - runs scraper periodically"""
    global server_scheduler_thread, server_scheduler_stop, scrape_status
    
    if not is_server_mode():
        return
    
    if is_scraper_disabled():
        print("[Server Mode] Scraper disabled via DISABLE_SCRAPER env variable")
        print("[Server Mode] Running as UI-only, data comes from Supabase (standalone scraper)")
        scrape_status['auto_running'] = False
        return
    
    server_scheduler_stop.clear()
    interval_seconds = get_scrape_interval_seconds()
    scrape_status['auto_running'] = True
    scrape_status['interval_minutes'] = interval_seconds // 60
    
    def scheduler_loop():
        global scrape_status
        print(f"[Server Scheduler] Started - interval: {interval_seconds // 60} minutes")
        
        while not server_scheduler_stop.is_set():
            if not scrape_status['running']:
                scrape_status['running'] = True
                try:
                    print(f"[Server Scheduler] Running scrape at {now_turkey_iso()}")
                    result = run_scraper()
                    scrape_status['last_result'] = result
                    scrape_status['last_scrape_time'] = now_turkey_iso()
                    scrape_status['last_supabase_sync'] = now_turkey_iso()
                    print(f"[Server Scheduler] Scrape completed")
                except Exception as e:
                    print(f"[Server Scheduler] Error: {e}")
                    scrape_status['last_result'] = {'status': 'error', 'error': str(e)}
                finally:
                    scrape_status['running'] = False
            
            next_time = now_turkey() + timedelta(seconds=interval_seconds)
            scrape_status['next_scrape_time'] = next_time.isoformat()
            
            for _ in range(interval_seconds):
                if server_scheduler_stop.is_set():
                    break
                time.sleep(1)
        
        print("[Server Scheduler] Stopped")
    
    server_scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
    server_scheduler_thread.start()


@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')


@app.route('/match/<home>/<away>')
def match_detail(home, away):
    """Match detail page with charts"""
    return render_template('match_detail.html', home=home, away=away)


matches_cache = {
    'data': {},  # market -> data
    'timestamp': {},  # market -> timestamp
    'ttl': 60,  # 1 dakika cache (sık güncellenen veri)
    'warming': set(),  # markets currently being warmed (to prevent duplicate fetches)
    'lock': threading.Lock()  # thread lock for cache access
}

def warm_matches_cache():
    """Pre-fill cache for common markets on server startup"""
    import time as time_module
    print("[Cache Warming] Starting background cache warm-up...")
    
    markets_to_warm = ['moneyway_1x2', 'dropping_1x2', 'moneyway_ou25', 'dropping_ou25', 'moneyway_btts', 'dropping_btts']
    
    for market in markets_to_warm:
        try:
            # Mark this market as being warmed
            with matches_cache['lock']:
                matches_cache['warming'].add(market)
            
            is_dropping = market.startswith('dropping')
            matches_with_latest = db.get_all_matches_with_latest(market, date_filter=None)
            
            enriched = []
            for m in matches_with_latest:
                latest = m.get('latest', {})
                odds = {}
                prev_odds = {}
                
                if latest:
                    if market in ['moneyway_1x2', 'dropping_1x2']:
                        odds = {
                            'Odds1': latest.get('Odds1', latest.get('1', '-')),
                            'OddsX': latest.get('OddsX', latest.get('X', '-')),
                            'Odds2': latest.get('Odds2', latest.get('2', '-')),
                            'Pct1': latest.get('Pct1', ''),
                            'Amt1': latest.get('Amt1', ''),
                            'PctX': latest.get('PctX', ''),
                            'AmtX': latest.get('AmtX', ''),
                            'Pct2': latest.get('Pct2', ''),
                            'Amt2': latest.get('Amt2', ''),
                            'Volume': latest.get('Volume', '')
                        }
                        if is_dropping:
                            prev_odds = {
                                'PrevOdds1': latest.get('Odds1_prev', ''),
                                'PrevOddsX': latest.get('OddsX_prev', ''),
                                'PrevOdds2': latest.get('Odds2_prev', ''),
                                'Trend1': latest.get('Trend1', ''),
                                'TrendX': latest.get('TrendX', ''),
                                'Trend2': latest.get('Trend2', ''),
                                'DropPct1': latest.get('DropPct1', ''),
                                'DropPctX': latest.get('DropPctX', ''),
                                'DropPct2': latest.get('DropPct2', '')
                            }
                    elif market in ['moneyway_ou25', 'dropping_ou25']:
                        odds = {
                            'Under': latest.get('Under', '-'),
                            'Over': latest.get('Over', '-'),
                            'PctUnder': latest.get('PctUnder', ''),
                            'AmtUnder': latest.get('AmtUnder', ''),
                            'PctOver': latest.get('PctOver', ''),
                            'AmtOver': latest.get('AmtOver', ''),
                            'Volume': latest.get('Volume', '')
                        }
                        if is_dropping:
                            prev_odds = {
                                'PrevUnder': latest.get('Under_prev', ''),
                                'PrevOver': latest.get('Over_prev', ''),
                                'TrendUnder': latest.get('TrendUnder', ''),
                                'TrendOver': latest.get('TrendOver', ''),
                                'DropPctUnder': latest.get('DropPctUnder', ''),
                                'DropPctOver': latest.get('DropPctOver', '')
                            }
                    elif market in ['moneyway_btts', 'dropping_btts']:
                        odds = {
                            'OddsYes': latest.get('OddsYes', latest.get('Yes', '-')),
                            'OddsNo': latest.get('OddsNo', latest.get('No', '-')),
                            'PctYes': latest.get('PctYes', ''),
                            'AmtYes': latest.get('AmtYes', ''),
                            'PctNo': latest.get('PctNo', ''),
                            'AmtNo': latest.get('AmtNo', ''),
                            'Volume': latest.get('Volume', '')
                        }
                        if is_dropping:
                            prev_odds = {
                                'PrevYes': latest.get('OddsYes_prev', ''),
                                'PrevNo': latest.get('OddsNo_prev', ''),
                                'TrendYes': latest.get('TrendYes', ''),
                                'TrendNo': latest.get('TrendNo', ''),
                                'DropPctYes': latest.get('DropPctYes', ''),
                                'DropPctNo': latest.get('DropPctNo', '')
                            }
                
                home = m.get('home_team', '')
                away = m.get('away_team', '')
                league = m.get('league', '')
                date = m.get('date', '')
                
                enriched.append({
                    'home_team': home,
                    'away_team': away,
                    'league': league,
                    'date': date,
                    'match_id': generate_match_id(home, away, league, date),
                    'odds': {**odds, **prev_odds},
                    'history_count': 1
                })
            
            matches_cache['data'][market] = enriched
            matches_cache['timestamp'][market] = time_module.time()
            print(f"[Cache Warming] {market}: {len(enriched)} matches cached")
        except Exception as e:
            print(f"[Cache Warming] Error warming {market}: {e}")
        finally:
            # Remove from warming set when done
            with matches_cache['lock']:
                matches_cache['warming'].discard(market)
    
    print("[Cache Warming] Complete!")

# Cache warming DISABLED - no longer needed with fixtures-first pagination
# Server now fetches only 20 fixtures + their odds (~100 rows vs 10,000 rows)
# cache_warming_thread = threading.Thread(target=warm_matches_cache, daemon=True)
# cache_warming_thread.start()

@app.route('/api/matches')
def get_matches():
    """Get matches from database with server-side caching
    
    Params:
    - bulk=1: Returns ALL matches at once (uses server cache, instant on hit)
    - refresh=true: Force cache refresh
    
    Result: Cache hit = 0ms, Cache miss = ~2s (fetches all pages)
    """
    import time as t
    start_time = t.time()
    
    market = request.args.get('market', 'moneyway_1x2')
    date_filter = request.args.get('date_filter', None)
    limit = request.args.get('limit', type=int, default=20)
    offset = request.args.get('offset', type=int, default=0)
    bulk_mode = request.args.get('bulk', '0') == '1'
    force_refresh = request.args.get('refresh', 'false').lower() == 'true'
    is_dropping = market.startswith('dropping')
    
    # BULK MODE: Return all matches from cache (instant on hit)
    # Works for both ALL mode (no date_filter) and TODAY/YESTERDAY filters
    if bulk_mode:
        cache_key = f"{market}_{date_filter or 'all'}"
        cached_data, from_cache = get_cached_matches(cache_key, force_refresh)
        
        if cached_data:
            elapsed = (t.time() - start_time) * 1000
            print(f"[Matches/Bulk] Cache HIT for {market} - {elapsed:.0f}ms, {len(cached_data)} matches")
            return jsonify({'matches': cached_data, 'total': len(cached_data), 'has_more': False})
        
        # Cache miss - fetch ALL matches in one go
        all_matches = []
        
        # For date_filter, use get_all_matches_with_latest (already returns all)
        if date_filter:
            matches_with_latest = db.get_all_matches_with_latest(market, date_filter=date_filter)
            page_matches_list = [matches_with_latest]
        else:
            # For ALL mode, paginate through all results
            page_matches_list = []
            current_offset = 0
            page_limit = 100
            max_pages = 50
            
            for page in range(max_pages):
                result = db.get_matches_paginated(market, limit=page_limit, offset=current_offset)
                page_matches = result.get('matches', [])
                if not page_matches:
                    break
                page_matches_list.append(page_matches)
                current_offset += len(page_matches)
                if not result.get('has_more', False):
                    break
        
        # Process all pages
        for page_matches in page_matches_list:
            if not page_matches:
                continue
            
            # Transform to expected format
            for m in page_matches:
                latest = m.get('latest', {})
                odds = {}
                prev_odds = {}
                
                if latest:
                    if market in ['moneyway_1x2', 'dropping_1x2']:
                        odds = {
                            'Odds1': latest.get('Odds1', latest.get('1', '-')),
                            'OddsX': latest.get('OddsX', latest.get('X', '-')),
                            'Odds2': latest.get('Odds2', latest.get('2', '-')),
                            'Pct1': latest.get('Pct1', ''),
                            'Amt1': latest.get('Amt1', ''),
                            'PctX': latest.get('PctX', ''),
                            'AmtX': latest.get('AmtX', ''),
                            'Pct2': latest.get('Pct2', ''),
                            'Amt2': latest.get('Amt2', ''),
                            'Volume': latest.get('Volume', '')
                        }
                        if is_dropping:
                            prev_odds = {
                                'PrevOdds1': latest.get('Odds1_prev', ''),
                                'PrevOddsX': latest.get('OddsX_prev', ''),
                                'PrevOdds2': latest.get('Odds2_prev', ''),
                                'Trend1': latest.get('Trend1', ''),
                                'TrendX': latest.get('TrendX', ''),
                                'Trend2': latest.get('Trend2', ''),
                                'DropPct1': latest.get('DropPct1', ''),
                                'DropPctX': latest.get('DropPctX', ''),
                                'DropPct2': latest.get('DropPct2', '')
                            }
                    elif market in ['moneyway_ou25', 'dropping_ou25']:
                        odds = {
                            'Under': latest.get('Under', '-'),
                            'Over': latest.get('Over', '-'),
                            'PctUnder': latest.get('PctUnder', ''),
                            'AmtUnder': latest.get('AmtUnder', ''),
                            'PctOver': latest.get('PctOver', ''),
                            'AmtOver': latest.get('AmtOver', ''),
                            'Volume': latest.get('Volume', '')
                        }
                        if is_dropping:
                            prev_odds = {
                                'PrevUnder': latest.get('Under_prev', ''),
                                'PrevOver': latest.get('Over_prev', ''),
                                'TrendUnder': latest.get('TrendUnder', ''),
                                'TrendOver': latest.get('TrendOver', ''),
                                'DropPctUnder': latest.get('DropPctUnder', ''),
                                'DropPctOver': latest.get('DropPctOver', '')
                            }
                    elif market in ['moneyway_btts', 'dropping_btts']:
                        odds = {
                            'OddsYes': latest.get('OddsYes', latest.get('Yes', '-')),
                            'OddsNo': latest.get('OddsNo', latest.get('No', '-')),
                            'PctYes': latest.get('PctYes', ''),
                            'AmtYes': latest.get('AmtYes', ''),
                            'PctNo': latest.get('PctNo', ''),
                            'AmtNo': latest.get('AmtNo', ''),
                            'Volume': latest.get('Volume', '')
                        }
                        if is_dropping:
                            prev_odds = {
                                'PrevYes': latest.get('OddsYes_prev', ''),
                                'PrevNo': latest.get('OddsNo_prev', ''),
                                'TrendYes': latest.get('TrendYes', ''),
                                'TrendNo': latest.get('TrendNo', ''),
                                'DropPctYes': latest.get('DropPctYes', ''),
                                'DropPctNo': latest.get('DropPctNo', '')
                            }
                
                home = m.get('home_team', '')
                away = m.get('away_team', '')
                league = m.get('league', '')
                date = m.get('date', '')
                
                all_matches.append({
                    'home_team': home,
                    'away_team': away,
                    'league': league,
                    'date': date,
                    'match_id': m.get('match_id_hash', generate_match_id(home, away, league, date)),
                    'odds': {**odds, **prev_odds},
                    'history_count': 1
                })
        
        # For DROPPING markets: Get true opening odds from first history record
        # The _prev fields in history only store previous snapshot, not true opening
        if is_dropping and all_matches:
            match_hashes = [m.get('match_id') for m in all_matches if m.get('match_id')]
            opening_odds = db.get_opening_odds_batch(market, match_hashes)
            
            if opening_odds:
                for match in all_matches:
                    match_id = match.get('match_id')
                    if match_id in opening_odds:
                        opening = opening_odds[match_id]
                        odds = match.get('odds', {})
                        
                        # Override PrevOdds with true opening odds
                        if '1x2' in market:
                            if opening.get('OpeningOdds1'):
                                odds['PrevOdds1'] = opening['OpeningOdds1']
                            if opening.get('OpeningOddsX'):
                                odds['PrevOddsX'] = opening['OpeningOddsX']
                            if opening.get('OpeningOdds2'):
                                odds['PrevOdds2'] = opening['OpeningOdds2']
                        elif 'ou25' in market:
                            if opening.get('OpeningOver'):
                                odds['PrevOver'] = opening['OpeningOver']
                            if opening.get('OpeningUnder'):
                                odds['PrevUnder'] = opening['OpeningUnder']
                        elif 'btts' in market:
                            if opening.get('OpeningYes'):
                                odds['PrevYes'] = opening['OpeningYes']
                            if opening.get('OpeningNo'):
                                odds['PrevNo'] = opening['OpeningNo']
        
        # Cache the result
        set_matches_cache(cache_key, all_matches)
        elapsed = (t.time() - start_time) * 1000
        print(f"[Matches/Bulk] Cache MISS for {market} - fetched {len(all_matches)} matches in {elapsed:.0f}ms")
        
        return jsonify({'matches': all_matches, 'total': len(all_matches), 'has_more': False})
    
    # PAGINATED MODE (legacy): Use for non-bulk requests
    # Use new paginated function for ALL/no date_filter (most common case)
    if date_filter is None:
        result = db.get_matches_paginated(market, limit=limit, offset=offset)
        
        # Transform to expected format
        enriched = []
        for m in result.get('matches', []):
            latest = m.get('latest', {})
            odds = {}
            prev_odds = {}
            
            if latest:
                if market in ['moneyway_1x2', 'dropping_1x2']:
                    odds = {
                        'Odds1': latest.get('Odds1', latest.get('1', '-')),
                        'OddsX': latest.get('OddsX', latest.get('X', '-')),
                        'Odds2': latest.get('Odds2', latest.get('2', '-')),
                        'Pct1': latest.get('Pct1', ''),
                        'Amt1': latest.get('Amt1', ''),
                        'PctX': latest.get('PctX', ''),
                        'AmtX': latest.get('AmtX', ''),
                        'Pct2': latest.get('Pct2', ''),
                        'Amt2': latest.get('Amt2', ''),
                        'Volume': latest.get('Volume', '')
                    }
                    if is_dropping:
                        prev_odds = {
                            'PrevOdds1': latest.get('Odds1_prev', ''),
                            'PrevOddsX': latest.get('OddsX_prev', ''),
                            'PrevOdds2': latest.get('Odds2_prev', ''),
                            'Trend1': latest.get('Trend1', ''),
                            'TrendX': latest.get('TrendX', ''),
                            'Trend2': latest.get('Trend2', '')
                        }
                elif market in ['moneyway_ou25', 'dropping_ou25']:
                    odds = {
                        'Under': latest.get('Under', '-'),
                        'Over': latest.get('Over', '-'),
                        'PctUnder': latest.get('PctUnder', ''),
                        'AmtUnder': latest.get('AmtUnder', ''),
                        'PctOver': latest.get('PctOver', ''),
                        'AmtOver': latest.get('AmtOver', ''),
                        'Volume': latest.get('Volume', '')
                    }
                    if is_dropping:
                        prev_odds = {
                            'PrevUnder': latest.get('Under_prev', ''),
                            'PrevOver': latest.get('Over_prev', ''),
                            'TrendUnder': latest.get('TrendUnder', ''),
                            'TrendOver': latest.get('TrendOver', '')
                        }
                elif market in ['moneyway_btts', 'dropping_btts']:
                    odds = {
                        'OddsYes': latest.get('OddsYes', latest.get('Yes', '-')),
                        'OddsNo': latest.get('OddsNo', latest.get('No', '-')),
                        'PctYes': latest.get('PctYes', ''),
                        'AmtYes': latest.get('AmtYes', ''),
                        'PctNo': latest.get('PctNo', ''),
                        'AmtNo': latest.get('AmtNo', ''),
                        'Volume': latest.get('Volume', '')
                    }
                    if is_dropping:
                        prev_odds = {
                            'PrevYes': latest.get('OddsYes_prev', ''),
                            'PrevNo': latest.get('OddsNo_prev', ''),
                            'TrendYes': latest.get('TrendYes', ''),
                            'TrendNo': latest.get('TrendNo', '')
                        }
            
            home = m.get('home_team', '')
            away = m.get('away_team', '')
            league = m.get('league', '')
            date = m.get('date', '')
            
            enriched.append({
                'home_team': home,
                'away_team': away,
                'league': league,
                'date': date,
                'match_id': m.get('match_id_hash', generate_match_id(home, away, league, date)),
                'odds': {**odds, **prev_odds},
                'history_count': 1
            })
        
        return jsonify({
            'matches': enriched,
            'total': result.get('total', len(enriched)),
            'has_more': result.get('has_more', False)
        })
    
    # Fallback to old method for date_filter (today/yesterday)
    now = time.time()
    cache_key = f"{market}_{date_filter}"
    
    if cache_key in matches_cache['data']:
        last_time = matches_cache['timestamp'].get(cache_key, 0)
        if (now - last_time) < matches_cache['ttl']:
            cached_data = matches_cache['data'][cache_key]
            sliced = cached_data[offset:offset + limit]
            return jsonify({'matches': sliced, 'total': len(cached_data), 'has_more': offset + limit < len(cached_data)})
    
    matches_with_latest = db.get_all_matches_with_latest(market, date_filter=date_filter)
    
    enriched = []
    for m in matches_with_latest:
        latest = m.get('latest', {})
        odds = {}
        prev_odds = {}
        
        if latest:
            if market in ['moneyway_1x2', 'dropping_1x2']:
                odds = {
                    'Odds1': latest.get('Odds1', latest.get('1', '-')),
                    'OddsX': latest.get('OddsX', latest.get('X', '-')),
                    'Odds2': latest.get('Odds2', latest.get('2', '-')),
                    'Pct1': latest.get('Pct1', ''),
                    'Amt1': latest.get('Amt1', ''),
                    'PctX': latest.get('PctX', ''),
                    'AmtX': latest.get('AmtX', ''),
                    'Pct2': latest.get('Pct2', ''),
                    'Amt2': latest.get('Amt2', ''),
                    'Volume': latest.get('Volume', '')
                }
                if is_dropping:
                    prev_odds = {
                        'PrevOdds1': latest.get('Odds1_prev', ''),
                        'PrevOddsX': latest.get('OddsX_prev', ''),
                        'PrevOdds2': latest.get('Odds2_prev', ''),
                        'Trend1': latest.get('Trend1', ''),
                        'TrendX': latest.get('TrendX', ''),
                        'Trend2': latest.get('Trend2', '')
                    }
            elif market in ['moneyway_ou25', 'dropping_ou25']:
                odds = {
                    'Under': latest.get('Under', '-'),
                    'Over': latest.get('Over', '-'),
                    'PctUnder': latest.get('PctUnder', ''),
                    'AmtUnder': latest.get('AmtUnder', ''),
                    'PctOver': latest.get('PctOver', ''),
                    'AmtOver': latest.get('AmtOver', ''),
                    'Volume': latest.get('Volume', '')
                }
                if is_dropping:
                    prev_odds = {
                        'PrevUnder': latest.get('Under_prev', ''),
                        'PrevOver': latest.get('Over_prev', ''),
                        'TrendUnder': latest.get('TrendUnder', ''),
                        'TrendOver': latest.get('TrendOver', '')
                    }
            elif market in ['moneyway_btts', 'dropping_btts']:
                odds = {
                    'OddsYes': latest.get('OddsYes', latest.get('Yes', '-')),
                    'OddsNo': latest.get('OddsNo', latest.get('No', '-')),
                    'PctYes': latest.get('PctYes', ''),
                    'AmtYes': latest.get('AmtYes', ''),
                    'PctNo': latest.get('PctNo', ''),
                    'AmtNo': latest.get('AmtNo', ''),
                    'Volume': latest.get('Volume', '')
                }
                if is_dropping:
                    prev_odds = {
                        'PrevYes': latest.get('OddsYes_prev', ''),
                        'PrevNo': latest.get('OddsNo_prev', ''),
                        'TrendYes': latest.get('TrendYes', ''),
                        'TrendNo': latest.get('TrendNo', '')
                    }
        
        home = m.get('home_team', '')
        away = m.get('away_team', '')
        league = m.get('league', '')
        date = m.get('date', '')
        
        enriched.append({
            'home_team': home,
            'away_team': away,
            'league': league,
            'date': date,
            'match_id': generate_match_id(home, away, league, date),
            'odds': {**odds, **prev_odds},
            'history_count': 1
        })
    
    matches_cache['data'][cache_key] = enriched
    matches_cache['timestamp'][cache_key] = now
    
    sliced = enriched[offset:offset + limit]
    return jsonify({'matches': sliced, 'total': len(enriched), 'has_more': offset + limit < len(enriched)})


@app.route('/api/match/history/bulk')
def get_match_history_bulk():
    """Get historical data for ALL markets of a single match in one request.
    This is faster than calling /api/match/history 6 times separately.
    Server-side cache: 2. acilista 0ms.
    """
    home = request.args.get('home', '')
    away = request.args.get('away', '')
    league = request.args.get('league', '')
    
    if not home or not away:
        return jsonify({'error': 'Missing home or away parameter', 'markets': {}})
    
    cache_key = f"{home.lower().strip()}|{away.lower().strip()}|{league.lower().strip()}"
    
    cached_data, from_cache = get_cached_history(cache_key)
    if from_cache:
        print(f"[History/Bulk] Cache HIT for {home} vs {away} - 0ms")
        return jsonify({'markets': cached_data})
    
    start_time = time.time()
    print(f"[History/Bulk] Cache MISS for {home} vs {away}, fetching...")
    
    all_markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts', 
                   'dropping_1x2', 'dropping_ou25', 'dropping_btts']
    
    result = {}
    for market in all_markets:
        history = db.get_match_history(home, away, market, league)
        
        chart_data = {'labels': [], 'datasets': []}
        
        if history:
            for h in history:
                timestamp = h.get('ScrapedAt', '')
                try:
                    dt = datetime.fromisoformat(timestamp)
                    chart_data['labels'].append(dt.strftime('%H:%M'))
                except:
                    chart_data['labels'].append(timestamp[:16] if timestamp else '')
            
            if market in ['moneyway_1x2', 'dropping_1x2']:
                for idx, (key, color) in enumerate([('Odds1', '#4ade80'), ('OddsX', '#fbbf24'), ('Odds2', '#60a5fa')]):
                    alt_key = ['1', 'X', '2'][idx]
                    values = []
                    for h in history:
                        val = h.get(key, h.get(alt_key, ''))
                        try:
                            v = float(str(val).split('\n')[0]) if val else None
                            values.append(v)
                        except:
                            values.append(None)
                    chart_data['datasets'].append({
                        'label': ['1', 'X', '2'][idx],
                        'data': values,
                        'borderColor': color,
                        'tension': 0.1,
                        'fill': False
                    })
            elif market in ['moneyway_ou25', 'dropping_ou25']:
                for key, color, label in [('Under', '#60a5fa', 'Under'), ('Over', '#4ade80', 'Over')]:
                    values = []
                    for h in history:
                        val = h.get(key, '')
                        try:
                            v = float(str(val).split('\n')[0]) if val else None
                            values.append(v)
                        except:
                            values.append(None)
                    chart_data['datasets'].append({
                        'label': label,
                        'data': values,
                        'borderColor': color,
                        'tension': 0.1,
                        'fill': False
                    })
            elif market in ['moneyway_btts', 'dropping_btts']:
                for key, color, label in [('Yes', '#4ade80', 'Yes'), ('No', '#f87171', 'No')]:
                    values = []
                    for h in history:
                        val = h.get(key, '')
                        try:
                            v = float(str(val).split('\n')[0]) if val else None
                            values.append(v)
                        except:
                            values.append(None)
                    chart_data['datasets'].append({
                        'label': label,
                        'data': values,
                        'borderColor': color,
                        'tension': 0.1,
                        'fill': False
                    })
        
        result[market] = {
            'history': history,
            'chart_data': chart_data
        }
    
    elapsed = int((time.time() - start_time) * 1000)
    print(f"[History/Bulk] Fetched {home} vs {away} in {elapsed}ms, caching...")
    
    set_history_cache(cache_key, result)
    
    return jsonify({'markets': result})


@app.route('/api/match/history')
def get_match_history():
    """Get historical data for a specific match"""
    home = request.args.get('home', '')
    away = request.args.get('away', '')
    market = request.args.get('market', 'moneyway_1x2')
    league = request.args.get('league', '')
    
    history = db.get_match_history(home, away, market, league)
    
    chart_data = {
        'labels': [],
        'datasets': []
    }
    
    if history:
        for h in history:
            timestamp = h.get('ScrapedAt', '')
            try:
                dt = datetime.fromisoformat(timestamp)
                chart_data['labels'].append(dt.strftime('%H:%M'))
            except:
                chart_data['labels'].append(timestamp[:16] if timestamp else '')
        
        if market in ['moneyway_1x2', 'dropping_1x2']:
            colors = ['#4ade80', '#fbbf24', '#60a5fa']
            for idx, (key, color) in enumerate([('Odds1', '#4ade80'), ('OddsX', '#fbbf24'), ('Odds2', '#60a5fa')]):
                alt_key = ['1', 'X', '2'][idx]
                values = []
                for h in history:
                    val = h.get(key, h.get(alt_key, ''))
                    try:
                        v = float(str(val).split('\n')[0]) if val else None
                        values.append(v)
                    except:
                        values.append(None)
                chart_data['datasets'].append({
                    'label': ['1', 'X', '2'][idx],
                    'data': values,
                    'borderColor': color,
                    'tension': 0.1,
                    'fill': False
                })
        elif market in ['moneyway_ou25', 'dropping_ou25']:
            for key, color, label in [('Under', '#60a5fa', 'Under'), ('Over', '#4ade80', 'Over')]:
                values = []
                for h in history:
                    val = h.get(key, '')
                    try:
                        v = float(str(val).split('\n')[0]) if val else None
                        values.append(v)
                    except:
                        values.append(None)
                chart_data['datasets'].append({
                    'label': label,
                    'data': values,
                    'borderColor': color,
                    'tension': 0.1,
                    'fill': False
                })
        elif market in ['moneyway_btts', 'dropping_btts']:
            for key, color, label in [('Yes', '#4ade80', 'Yes'), ('No', '#f87171', 'No')]:
                values = []
                for h in history:
                    val = h.get(key, '')
                    try:
                        v = float(str(val).split('\n')[0]) if val else None
                        values.append(v)
                    except:
                        values.append(None)
                chart_data['datasets'].append({
                    'label': label,
                    'data': values,
                    'borderColor': color,
                    'tension': 0.1,
                    'fill': False
                })
    
    return jsonify({
        'history': history,
        'chart_data': chart_data
    })


@app.route('/api/scrape', methods=['POST'])
def trigger_scrape():
    """Trigger manual scrape - SERVER MODE ONLY"""
    global scrape_status
    
    if is_client_mode():
        return jsonify({
            'status': 'disabled', 
            'message': 'Scraping disabled in client mode. Data is fetched from Supabase.'
        })
    
    if scrape_status['running']:
        return jsonify({'status': 'error', 'message': 'Scrape already running'})
    
    scrape_status['running'] = True
    
    def do_scrape():
        global scrape_status
        try:
            result = run_scraper()
            scrape_status['last_result'] = result
            scrape_status['last_scrape_time'] = now_turkey_iso()
            scrape_status['last_supabase_sync'] = now_turkey_iso()
        except Exception as e:
            scrape_status['last_result'] = {'status': 'error', 'error': str(e)}
        finally:
            scrape_status['running'] = False
    
    thread = threading.Thread(target=do_scrape)
    thread.daemon = True
    thread.start()
    
    return jsonify({'status': 'ok', 'message': 'Scrape started'})


@app.route('/api/scrape/auto', methods=['POST'])
def toggle_auto_scrape():
    """Toggle automatic scraping/polling
    
    SERVER MODE: Auto runs scraper periodically
    CLIENT MODE: Auto polls Supabase for fresh data (no scraping)
    """
    global scrape_status, auto_scrape_thread, stop_auto_event
    
    data = request.get_json() or {}
    action = data.get('action', 'toggle')
    interval = int(data.get('interval', 5))
    
    if action == 'start' and not scrape_status['auto_running']:
        scrape_status['auto_running'] = True
        scrape_status['interval_minutes'] = interval
        stop_auto_event.clear()
        
        if is_client_mode():
            def client_poll_loop():
                global scrape_status
                poll_interval = interval * 60
                print(f"[Client Auto] Started - polling Supabase every {interval} minutes")
                
                while not stop_auto_event.is_set():
                    scrape_status['last_supabase_sync'] = now_turkey_iso()
                    
                    next_time = now_turkey() + timedelta(minutes=interval)
                    scrape_status['next_scrape_time'] = next_time.isoformat()
                    
                    for _ in range(poll_interval):
                        if stop_auto_event.is_set():
                            break
                        time.sleep(1)
                
                scrape_status['auto_running'] = False
                scrape_status['next_scrape_time'] = None
                print("[Client Auto] Stopped")
            
            auto_scrape_thread = threading.Thread(target=client_poll_loop, daemon=True)
            auto_scrape_thread.start()
            
            return jsonify({
                'status': 'ok', 
                'auto_running': True, 
                'interval_minutes': interval,
                'mode': 'client_poll'
            })
        else:
            def server_auto_loop():
                global scrape_status
                while not stop_auto_event.is_set():
                    if not scrape_status['running']:
                        scrape_status['running'] = True
                        scrape_status['next_scrape_time'] = None
                        try:
                            result = run_scraper()
                            scrape_status['last_result'] = result
                            scrape_status['last_scrape_time'] = now_turkey_iso()
                            scrape_status['last_supabase_sync'] = now_turkey_iso()
                        except Exception as e:
                            scrape_status['last_result'] = {'status': 'error', 'error': str(e)}
                        finally:
                            scrape_status['running'] = False
                    
                    next_time = now_turkey() + timedelta(minutes=scrape_status['interval_minutes'])
                    scrape_status['next_scrape_time'] = next_time.isoformat()
                    
                    for _ in range(scrape_status['interval_minutes'] * 60):
                        if stop_auto_event.is_set():
                            break
                        time.sleep(1)
                
                scrape_status['auto_running'] = False
                scrape_status['next_scrape_time'] = None
            
            auto_scrape_thread = threading.Thread(target=server_auto_loop, daemon=True)
            auto_scrape_thread.start()
            
            return jsonify({
                'status': 'ok', 
                'auto_running': True, 
                'interval_minutes': interval,
                'mode': 'server_scrape'
            })
    
    elif action == 'stop':
        stop_auto_event.set()
        scrape_status['auto_running'] = False
        scrape_status['next_scrape_time'] = None
        return jsonify({'status': 'ok', 'auto_running': False})
    
    return jsonify({'status': 'ok', 'auto_running': scrape_status['auto_running']})


@app.route('/api/interval', methods=['POST'])
def update_interval():
    """Update auto-scrape interval"""
    global scrape_status
    data = request.get_json() or {}
    new_interval = int(data.get('interval', 5))
    
    if new_interval < 1:
        new_interval = 1
    if new_interval > 60:
        new_interval = 60
    
    scrape_status['interval_minutes'] = new_interval
    return jsonify({'status': 'ok', 'interval_minutes': new_interval})


def get_turkey_time_str(iso_time: str) -> str:
    """Convert ISO time to Turkey timezone HH:MM format"""
    if not iso_time:
        return "--:--"
    try:
        return format_time_only(iso_time)
    except:
        return "--:--"


@app.route('/api/status')
def get_status():
    """Get current scrape status with mode information"""
    mode = "server" if is_server_mode() else "client"
    
    last_time_tr = get_turkey_time_str(scrape_status['last_scrape_time'])
    
    last_data_update = db.get_last_data_update() if db.is_supabase_available else None
    last_data_update_tr = None
    if last_data_update:
        try:
            from core.timezone import format_turkey_time
            last_data_update_tr = format_turkey_time(last_data_update)
        except:
            last_data_update_tr = last_data_update
    
    return jsonify({
        'running': scrape_status['running'],
        'auto_running': scrape_status['auto_running'],
        'last_result': scrape_status['last_result'],
        'last_scrape_time': scrape_status['last_scrape_time'],
        'last_scrape_time_tr': last_time_tr,
        'last_supabase_sync': scrape_status['last_supabase_sync'],
        'next_scrape_time': scrape_status['next_scrape_time'],
        'interval_minutes': scrape_status['interval_minutes'],
        'cookie_set': bool(get_cookie_string()) if is_server_mode() else False,
        'supabase_connected': db.is_supabase_available,
        'mode': mode,
        'scraping_enabled': not is_server_mode(),
        'last_data_update': last_data_update,
        'last_data_update_tr': last_data_update_tr
    })


@app.route('/api/markets')
def get_markets():
    """Get available markets"""
    return jsonify([
        {'key': 'moneyway_1x2', 'label': 'Moneyway 1X2', 'icon': 'chart-line'},
        {'key': 'moneyway_ou25', 'label': 'Moneyway O/U 2.5', 'icon': 'chart-line'},
        {'key': 'moneyway_btts', 'label': 'Moneyway BTTS', 'icon': 'chart-line'},
        {'key': 'dropping_1x2', 'label': 'Dropping 1X2', 'icon': 'arrow-trend-down'},
        {'key': 'dropping_ou25', 'label': 'Dropping O/U 2.5', 'icon': 'arrow-trend-down'},
        {'key': 'dropping_btts', 'label': 'Dropping BTTS', 'icon': 'arrow-trend-down'}
    ])


@app.route('/api/export/png', methods=['POST'])
def export_png():
    """Save PNG file for EXE/pywebview environment"""
    import base64
    import re
    import platform
    
    try:
        data = request.get_json()
        image_data = data.get('image', '')
        filename = data.get('filename', 'SmartXFlow_export.png')
        
        print(f"[PNG Export] Received request, filename: {filename}")
        
        if not image_data:
            print("[PNG Export] Error: No image data")
            return jsonify({'success': False, 'error': 'No image data'})
        
        header_match = re.match(r'data:image/\w+;base64,', image_data)
        if header_match:
            image_data = image_data[header_match.end():]
        
        image_bytes = base64.b64decode(image_data)
        print(f"[PNG Export] Image size: {len(image_bytes)} bytes")
        
        downloads_path = None
        possible_paths = []
        
        if platform.system() == 'Windows':
            possible_paths = [
                os.path.join(os.environ.get('USERPROFILE', ''), 'Downloads'),
                os.path.join(os.environ.get('USERPROFILE', ''), 'Desktop'),
                os.environ.get('USERPROFILE', ''),
                os.path.join(os.environ.get('HOMEDRIVE', 'C:'), os.environ.get('HOMEPATH', ''), 'Downloads'),
            ]
        else:
            possible_paths = [
                os.path.expanduser('~/Downloads'),
                os.path.expanduser('~/Desktop'),
                os.path.expanduser('~'),
                '/tmp'
            ]
        
        for path in possible_paths:
            if path and os.path.exists(path) and os.access(path, os.W_OK):
                downloads_path = path
                break
        
        if not downloads_path:
            downloads_path = os.getcwd()
        
        print(f"[PNG Export] Save directory: {downloads_path}")
        
        safe_filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filepath = os.path.join(downloads_path, safe_filename)
        
        counter = 1
        base_name = safe_filename.rsplit('.', 1)[0]
        ext = '.png'
        while os.path.exists(filepath):
            filepath = os.path.join(downloads_path, f"{base_name}_{counter}{ext}")
            counter += 1
        
        with open(filepath, 'wb') as f:
            f.write(image_bytes)
        
        print(f"[PNG Export] Saved to: {filepath}")
        return jsonify({'success': True, 'path': filepath})
    
    except Exception as e:
        print(f"[PNG Export] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})



odds_trend_cache = {
    'data': {},  # market -> data
    'timestamp': {},  # market -> timestamp
    'ttl': 600  # 10 dakika cache (optimized)
}

@app.route('/api/odds-trend/<market>')
def get_odds_trend(market):
    """Get odds trend data for DROP markets only (with cache).
    Returns sparkline data, percent change, and trend direction.
    """
    import time
    
    if not market.startswith('dropping'):
        return jsonify({'error': 'Only DROP markets supported', 'data': {}})
    
    try:
        now = time.time()
        
        # Cache kontrolü
        if market in odds_trend_cache['data']:
            last_time = odds_trend_cache['timestamp'].get(market, 0)
            if (now - last_time) < odds_trend_cache['ttl']:
                print(f"[Odds Trend] Using cached data for {market}")
                return jsonify({
                    'market': market,
                    'data': odds_trend_cache['data'][market],
                    'count': len(odds_trend_cache['data'][market]),
                    'cached': True
                })
        
        sb_client = get_supabase_client()
        if sb_client:
            trend_data = sb_client.get_6h_odds_history(market)
        else:
            trend_data = {}
        
        # Cache'e kaydet
        odds_trend_cache['data'][market] = trend_data
        odds_trend_cache['timestamp'][market] = now
        
        return jsonify({
            'market': market,
            'data': trend_data,
            'count': len(trend_data)
        })
    except Exception as e:
        print(f"[Odds Trend API] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'data': {}})


@app.route('/api/match/details')
def get_match_details():
    """Get match details by team names"""
    home = request.args.get('home', '')
    away = request.args.get('away', '')
    
    if not home or not away:
        return jsonify({'success': False, 'error': 'Missing home or away parameter'})
    
    try:
        match_data = None
        home_lower = home.lower().strip()
        away_lower = away.lower().strip()
        
        # Use get_matches_paginated which includes latest odds data
        result = db.get_matches_paginated('moneyway_1x2', limit=500, offset=0)
        matches_list = result.get('matches', [])
        
        for m in matches_list:
            m_home = (m.get('home_team') or '').lower().strip()
            m_away = (m.get('away_team') or '').lower().strip()
            # Partial match - isimler içeriyorsa kabul et
            if (home_lower in m_home or m_home in home_lower) and \
               (away_lower in m_away or m_away in away_lower):
                # Transform latest to odds format like /api/matches does
                latest = m.get('latest', {})
                if latest:
                    m['odds'] = {
                        'Odds1': latest.get('Odds1', latest.get('1', '-')),
                        'OddsX': latest.get('OddsX', latest.get('X', '-')),
                        'Odds2': latest.get('Odds2', latest.get('2', '-')),
                        'Pct1': latest.get('Pct1', ''),
                        'Amt1': latest.get('Amt1', ''),
                        'PctX': latest.get('PctX', ''),
                        'AmtX': latest.get('AmtX', ''),
                        'Pct2': latest.get('Pct2', ''),
                        'Amt2': latest.get('Amt2', ''),
                        'Volume': latest.get('Volume', '')
                    }
                match_data = m
                break
        
        if match_data:
            odds_data = match_data.get('odds') or {}
            
            # Generate match_id from team names and league
            m_home = match_data.get('home_team', home)
            m_away = match_data.get('away_team', away)
            m_league = match_data.get('league', '')
            m_date = match_data.get('date', '')
            match_id = generate_match_id(m_home, m_away, m_league, m_date)
            
            return jsonify({
                'success': True,
                'match': {
                    'home_team': m_home,
                    'away_team': m_away,
                    'league': m_league,
                    'date': m_date,
                    'match_id': match_id,
                    'odds': odds_data,
                    'details': odds_data
                }
            })
        else:
            return jsonify({
                'success': True,
                'match': {
                    'home_team': home,
                    'away_team': away,
                    'league': '',
                    'date': '',
                    'odds': {},
                    'details': {}
                }
            })
    except Exception as e:
        print(f"[Match Details API] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


def refresh_configs_from_supabase():
    """Refresh all alarm configs from Supabase alarm_settings table - LIVE RELOAD"""
    global sharp_config, publicmove_config, big_money_config, volume_shock_config, volume_leader_config, dropping_config
    
    supabase = get_supabase_client()
    if not supabase or not supabase.is_available:
        print("[Config Refresh] Supabase not available, using JSON fallback")
        return False
    
    try:
        settings = supabase.get_alarm_settings()
        if not settings:
            print("[Config Refresh] No settings from DB, using JSON fallback")
            return False
        
        changes = []
        
        for setting in settings:
            alarm_type = setting.get('alarm_type', '')
            enabled = setting.get('enabled', True)
            config = setting.get('config', {})
            
            if alarm_type == 'sharp' and config:
                old = sharp_config.copy()
                sharp_config.update(config)
                sharp_config['enabled'] = enabled
                if old != sharp_config:
                    changes.append('sharp')
                    
            elif alarm_type == 'publicmove' and config:
                old = publicmove_config.copy()
                publicmove_config.update(config)
                publicmove_config['enabled'] = enabled
                if old != publicmove_config:
                    changes.append('publicmove')
                    
            elif alarm_type == 'bigmoney' and config:
                old = big_money_config.copy()
                big_money_config.update(config)
                big_money_config['enabled'] = enabled
                if old != big_money_config:
                    changes.append('bigmoney')
                    
            elif alarm_type == 'volumeshock' and config:
                old = volume_shock_config.copy()
                volume_shock_config.update(config)
                volume_shock_config['enabled'] = enabled
                if old != volume_shock_config:
                    changes.append('volumeshock')
                    
            elif alarm_type == 'volumeleader' and config:
                old = volume_leader_config.copy()
                volume_leader_config.update(config)
                volume_leader_config['enabled'] = enabled
                if old != volume_leader_config:
                    changes.append('volumeleader')
                    
            elif alarm_type == 'dropping' and config:
                old = dropping_config.copy()
                dropping_config.update(config)
                dropping_config['enabled'] = enabled
                if old != dropping_config:
                    changes.append('dropping')
        
        if changes:
            print(f"[Config Refresh] Updated configs from Supabase: {', '.join(changes)}")
        else:
            print(f"[Config Refresh] Configs loaded from Supabase (no changes)")
        return True
        
    except Exception as e:
        print(f"[Config Refresh] Error: {e}")
        return False


SHARP_CONFIG_FILE = 'sharp_config.json'

def load_sharp_config_from_file():
    """Load Sharp config from JSON file - NO DEFAULTS (tüm değerler Supabase'den gelmeli)"""
    config = {}
    try:
        if os.path.exists(SHARP_CONFIG_FILE):
            with open(SHARP_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                print(f"[Sharp] Config loaded from {SHARP_CONFIG_FILE}: min_sharp_score={config.get('min_sharp_score')}")
    except Exception as e:
        print(f"[Sharp] Config load error: {e}")
    return config

def save_sharp_config_to_file(config):
    """Save Sharp config to both Supabase and JSON file"""
    success = False
    
    # 1. Supabase'e yaz (primary)
    try:
        supabase = get_supabase_client()
        if supabase and supabase.is_available:
            # Eğer config boşsa Supabase'e yazma - filtered_config kullan
            filtered_config = {k: v for k, v in config.items() if v is not None and k != 'enabled'}
            if not filtered_config:
                print("[Sharp] Config boş - Supabase'e yazılmadı")
            elif supabase.update_alarm_setting('sharp', config.get('enabled') if 'enabled' in config else None, filtered_config):
                print(f"[Sharp] Config saved to Supabase")
                success = True
    except Exception as e:
        print(f"[Sharp] Supabase save error: {e}")
    
    # 2. JSON'a yaz (fallback)
    try:
        with open(SHARP_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"[Sharp] Config saved to JSON")
        success = True
    except Exception as e:
        print(f"[Sharp] JSON save error: {e}")
    
    return success

sharp_config = load_sharp_config_from_file()

SHARP_ALARMS_FILE = 'sharp_alarms.json'

def load_sharp_alarms_from_file():
    """Load Sharp alarms from JSON file"""
    try:
        if os.path.exists(SHARP_ALARMS_FILE):
            with open(SHARP_ALARMS_FILE, 'r') as f:
                alarms = json.load(f)
                print(f"[Sharp] Loaded {len(alarms)} alarms from {SHARP_ALARMS_FILE}")
                return alarms
    except Exception as e:
        print(f"[Sharp] Alarms load error: {e}")
    return []

def save_sharp_alarms_to_file(alarms):
    """Save Sharp alarms to both JSON file and Supabase"""
    success = False
    
    # 1. Supabase'e yaz (primary)
    try:
        if write_sharp_alarms_to_supabase(alarms):
            success = True
    except Exception as e:
        print(f"[Sharp] Supabase write error: {e}")
    
    # 2. JSON'a yaz (fallback)
    try:
        with open(SHARP_ALARMS_FILE, 'w') as f:
            json.dump(alarms, f, indent=2, ensure_ascii=False)
        print(f"[Sharp] Saved {len(alarms)} alarms to {SHARP_ALARMS_FILE}")
        success = True
    except Exception as e:
        print(f"[Sharp] JSON save error: {e}")
    
    return success

sharp_alarms = load_sharp_alarms_from_file()
sharp_calculating = False
sharp_calc_progress = ""

# ==================== HALK TUZAĞI ALARM SYSTEM ====================
# (Sharp alarm'ın birebir kopyası, farklı isim)
PUBLICMOVE_CONFIG_FILE = 'publicmove_config.json'
PUBLICMOVE_ALARMS_FILE = 'publicmove_alarms.json'

def load_publicmove_config_from_file():
    """Load Public Move config from JSON file - NO DEFAULTS (tüm değerler Supabase'den gelmeli)"""
    config = {}
    try:
        if os.path.exists(PUBLICMOVE_CONFIG_FILE):
            with open(PUBLICMOVE_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                print(f"[PublicMove] Config loaded from {PUBLICMOVE_CONFIG_FILE}: min_sharp_score={config.get('min_sharp_score')}")
    except Exception as e:
        print(f"[PublicMove] Config load error: {e}")
    return config

def save_publicmove_config_to_file(config):
    """Save Public Move config to both Supabase and JSON file"""
    success = False
    
    # 1. Supabase'e yaz (primary)
    try:
        supabase = get_supabase_client()
        if supabase and supabase.is_available:
            # Eğer config boşsa Supabase'e yazma - filtered_config kullan
            filtered_config = {k: v for k, v in config.items() if v is not None and k != 'enabled'}
            if not filtered_config:
                print("[PublicMove] Config boş - Supabase'e yazılmadı")
            elif supabase.update_alarm_setting('publicmove', config.get('enabled') if 'enabled' in config else None, filtered_config):
                print(f"[PublicMove] Config saved to Supabase")
                success = True
    except Exception as e:
        print(f"[PublicMove] Supabase save error: {e}")
    
    # 2. JSON'a yaz (fallback)
    try:
        with open(PUBLICMOVE_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"[PublicMove] Config saved to JSON")
        success = True
    except Exception as e:
        print(f"[PublicMove] JSON save error: {e}")
    
    return success

publicmove_config = load_publicmove_config_from_file()

def load_publicmove_alarms_from_file():
    """Load Public Move alarms from JSON file"""
    try:
        if os.path.exists(PUBLICMOVE_ALARMS_FILE):
            with open(PUBLICMOVE_ALARMS_FILE, 'r') as f:
                alarms = json.load(f)
                print(f"[PublicMove] Loaded {len(alarms)} alarms from {PUBLICMOVE_ALARMS_FILE}")
                return alarms
    except Exception as e:
        print(f"[PublicMove] Alarms load error: {e}")
    return []

def save_publicmove_alarms_to_file(alarms):
    """Save PublicMove alarms to JSON file (Supabase write disabled - alarm type removed)"""
    success = False
    
    # JSON'a yaz (fallback only - Supabase write disabled)
    try:
        with open(PUBLICMOVE_ALARMS_FILE, 'w') as f:
            json.dump(alarms, f, indent=2, ensure_ascii=False)
        print(f"[PublicMove] Saved {len(alarms)} alarms to {PUBLICMOVE_ALARMS_FILE}")
        success = True
    except Exception as e:
        print(f"[PublicMove] JSON save error: {e}")
    
    return success

publicmove_alarms = load_publicmove_alarms_from_file()
publicmove_calculating = False
publicmove_calc_progress = ""


# ============================================================================
# BIG MONEY ALARM SYSTEM
# ============================================================================

BIG_MONEY_CONFIG_FILE = 'big_money_config.json'
BIG_MONEY_ALARMS_FILE = 'big_money_alarms.json'

big_money_calculating = False
big_money_calc_progress = ""

def load_big_money_config():
    """Load Big Money config from JSON file - NO DEFAULTS (tüm değerler Supabase'den gelmeli)"""
    config = {}
    try:
        if os.path.exists(BIG_MONEY_CONFIG_FILE):
            with open(BIG_MONEY_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                print(f"[BigMoney] Config loaded: limit={config.get('big_money_limit')}")
    except Exception as e:
        print(f"[BigMoney] Config load error: {e}")
    return config

def save_big_money_config(config):
    """Save Big Money config to both Supabase and JSON file"""
    success = False
    
    # 1. Supabase'e yaz (primary)
    try:
        supabase = get_supabase_client()
        if supabase and supabase.is_available:
            # Eğer config boşsa Supabase'e yazma - filtered_config kullan
            filtered_config = {k: v for k, v in config.items() if v is not None and k != 'enabled'}
            if not filtered_config:
                print("[BigMoney] Config boş - Supabase'e yazılmadı")
            elif supabase.update_alarm_setting('bigmoney', config.get('enabled') if 'enabled' in config else None, filtered_config):
                print(f"[BigMoney] Config saved to Supabase")
                success = True
    except Exception as e:
        print(f"[BigMoney] Supabase save error: {e}")
    
    # 2. JSON'a yaz (fallback)
    try:
        with open(BIG_MONEY_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"[BigMoney] Config saved to JSON: limit={config.get('big_money_limit')}")
        success = True
    except Exception as e:
        print(f"[BigMoney] JSON save error: {e}")
    
    return success

def load_big_money_alarms_from_file():
    """Load Big Money alarms from JSON file"""
    try:
        if os.path.exists(BIG_MONEY_ALARMS_FILE):
            with open(BIG_MONEY_ALARMS_FILE, 'r') as f:
                alarms = json.load(f)
                print(f"[BigMoney] Loaded {len(alarms)} alarms from {BIG_MONEY_ALARMS_FILE}")
                return alarms
    except Exception as e:
        print(f"[BigMoney] Alarms load error: {e}")
    return []

def save_big_money_alarms_to_file(alarms):
    """Save Big Money alarms to both Supabase and JSON file"""
    # 1. Supabase'e yaz (primary)
    if write_bigmoney_alarms_to_supabase(alarms):
        print(f"[BigMoney] Alarms written to Supabase")
    
    # 2. JSON'a yaz (fallback)
    try:
        with open(BIG_MONEY_ALARMS_FILE, 'w') as f:
            json.dump(alarms, f, indent=2, ensure_ascii=False)
        print(f"[BigMoney] Saved {len(alarms)} alarms to {BIG_MONEY_ALARMS_FILE}")
        return True
    except Exception as e:
        print(f"[BigMoney] Alarms save error: {e}")
        return False

big_money_config = load_big_money_config()
big_money_alarms = load_big_money_alarms_from_file()


@app.route('/api/bigmoney/config', methods=['GET'])
def get_big_money_config():
    """Get Big Money config with default fallback"""
    merged_config = DEFAULT_ALARM_SETTINGS.get('bigmoney', {}).get('config', {}).copy()
    
    try:
        supabase = get_supabase_client()
        if supabase and supabase.is_available:
            db_setting = supabase.get_alarm_setting('bigmoney')
            if db_setting:
                db_config = db_setting.get('config')
                if db_config and isinstance(db_config, dict):
                    for key, value in db_config.items():
                        if value is not None:
                            merged_config[key] = value
    except Exception as e:
        print(f"[BigMoney Config] Supabase error: {e}")
    
    if isinstance(big_money_config, dict):
        for key, value in big_money_config.items():
            if value is not None:
                merged_config[key] = value
    
    return jsonify(merged_config)


@app.route('/api/bigmoney/config', methods=['POST'])
def save_big_money_config_endpoint():
    """Save Big Money config"""
    global big_money_config
    try:
        data = request.get_json()
        if data:
            big_money_config.update(data)
            save_big_money_config(big_money_config)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/bigmoney/alarms', methods=['GET'])
def get_big_money_alarms():
    """Get all Big Money alarms - reads from Supabase first, fallback to local JSON only on error"""
    supabase_alarms = get_bigmoney_alarms_from_supabase()
    if supabase_alarms is not None:  # Boş liste dahil Supabase verisini kullan
        return jsonify(supabase_alarms)
    return jsonify(big_money_alarms)  # Sadece Supabase hatası durumunda JSON fallback


@app.route('/api/bigmoney/delete', methods=['POST'])
def delete_big_money_alarms():
    """Delete all Big Money alarms from both Supabase and local JSON"""
    global big_money_alarms
    try:
        big_money_alarms = []
        save_big_money_alarms_to_file(big_money_alarms)
        delete_alarms_from_supabase('bigmoney_alarms')
        print("[BigMoney] All alarms deleted")
        return jsonify({'success': True})
    except Exception as e:
        print(f"[BigMoney] Delete error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/bigmoney/status', methods=['GET'])
def get_big_money_status():
    """Get Big Money calculation status"""
    return jsonify({
        'calculating': big_money_calculating,
        'progress': big_money_calc_progress,
        'alarm_count': len(big_money_alarms)
    })

@app.route('/api/bigmoney/reset', methods=['POST'])
def reset_big_money_calculation():
    """Reset Big Money calculation flag (force unlock)"""
    global big_money_calculating, big_money_calc_progress
    big_money_calculating = False
    big_money_calc_progress = "Kullanici tarafindan sifirlandi"
    print("[BigMoney] Calculation flag reset by user")
    return jsonify({'success': True, 'message': 'Calculation reset'})


@app.route('/api/bigmoney/calculate', methods=['POST'])
def calculate_big_money_alarms_endpoint():
    """Calculate Big Money alarms based on config"""
    global big_money_alarms, big_money_calculating
    try:
        big_money_calculating = True
        big_money_alarms = calculate_big_money_scores(big_money_config)
        save_big_money_alarms_to_file(big_money_alarms)
        big_money_calculating = False
        return jsonify({'success': True, 'count': len(big_money_alarms)})
    except Exception as e:
        big_money_calculating = False
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


def calculate_big_money_scores(config):
    """
    Calculate Big Money and Huge Money alarms.
    
    BIG MONEY: Single snapshot with incoming money >= limit (default 15000)
    HUGE MONEY: 2 consecutive snapshots BOTH with incoming money >= limit
    """
    global big_money_calc_progress
    alarms = []
    supabase = get_supabase_client()
    if not supabase or not supabase.is_available:
        print("[BigMoney] Supabase not available")
        return alarms
    
    # NO DEFAULTS - tüm değerler Supabase'den gelmeli
    limit = config.get('big_money_limit')
    if limit is None:
        print("[BigMoney] CONFIG EKSIK - Supabase'den config yüklenemedi! Eksik: big_money_limit")
        return alarms
    print(f"[BigMoney] Config: limit={limit}")
    
    markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts']
    market_names = {'moneyway_1x2': '1X2', 'moneyway_ou25': 'O/U 2.5', 'moneyway_btts': 'BTTS'}
    
    # Prematch kuralı: D-2+ maçlar hariç
    today = now_turkey().date()
    yesterday = today - timedelta(days=1)
    
    for idx, market in enumerate(markets):
        try:
            if '1x2' in market:
                selections = ['1', 'X', '2']
                amount_keys = ['amt1', 'amtx', 'amt2']
            elif 'ou25' in market:
                selections = ['Over', 'Under']
                amount_keys = ['amtover', 'amtunder']
            else:
                selections = ['Yes', 'No']
                amount_keys = ['amtyes', 'amtno']
            
            history_table = f"{market}_history"
            matches = supabase.get_all_matches_with_latest(market)
            if not matches:
                continue
            
            big_money_calc_progress = f"{market_names.get(market, market)} isleniyor... ({idx+1}/3)"
            
            # D-2+ filtresi
            filtered_matches = []
            for match in matches:
                match_date_str = match.get('date', '')
                if match_date_str:
                    try:
                        date_part = match_date_str.split()[0]
                        if '.' in date_part:
                            parts = date_part.split('.')
                            if len(parts) == 2:
                                day = int(parts[0])
                                month_abbr = parts[1][:3]
                                month_map = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                                            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
                                month = month_map.get(month_abbr, today.month)
                                match_date = datetime(today.year, month, day).date()
                            elif len(parts) == 3:
                                match_date = datetime.strptime(date_part, '%d.%m.%Y').date()
                            else:
                                match_date = today
                        elif '-' in date_part:
                            match_date = datetime.strptime(date_part.split('T')[0], '%Y-%m-%d').date()
                        else:
                            match_date = today
                        
                        if match_date < yesterday:
                            continue
                        filtered_matches.append(match)
                    except:
                        filtered_matches.append(match)
                else:
                    filtered_matches.append(match)
            
            print(f"[BigMoney] Processing {len(filtered_matches)}/{len(matches)} matches for {market}")
            
            for match in filtered_matches:
                home = match.get('home_team', match.get('home', match.get('Home', '')))
                away = match.get('away_team', match.get('away', match.get('Away', '')))
                
                if not home or not away:
                    continue
                
                history = supabase.get_match_history_for_sharp(home, away, history_table)
                if not history or len(history) < 2:
                    continue
                
                match_date_str = match.get('date', '')
                
                for sel_idx, selection in enumerate(selections):
                    amount_key = amount_keys[sel_idx]
                    
                    # Her snapshot için gelen parayı hesapla
                    big_money_snapshots = []
                    
                    for i in range(1, len(history)):
                        current_amount = parse_volume(history[i].get(amount_key, '0'))
                        prev_amount = parse_volume(history[i-1].get(amount_key, '0'))
                        incoming_money = current_amount - prev_amount
                        
                        if incoming_money >= limit:
                            big_money_snapshots.append({
                                'index': i,
                                'incoming': incoming_money,
                                'scraped_at': history[i].get('scraped_at', '')
                            })
                    
                    if not big_money_snapshots:
                        continue
                    
                    # Huge Money kontrolü: 2 ardışık snapshot
                    is_huge = False
                    huge_total = 0
                    for j in range(len(big_money_snapshots) - 1):
                        if big_money_snapshots[j+1]['index'] - big_money_snapshots[j]['index'] == 1:
                            is_huge = True
                            huge_total = big_money_snapshots[j]['incoming'] + big_money_snapshots[j+1]['incoming']
                            break
                    
                    # En büyük gelen parayı bulan snapshot'ı bul
                    max_snapshot = max(big_money_snapshots, key=lambda s: s['incoming'])
                    max_incoming = max_snapshot['incoming']
                    
                    # O seçeneğin toplam stake'i (en son snapshot'taki değer)
                    selection_total = parse_volume(history[-1].get(amount_key, '0'))
                    
                    # Event time: en büyük para girişinin olduğu snapshot zamanı
                    event_time = max_snapshot.get('scraped_at', '')
                    created_at = now_turkey().strftime('%d.%m.%Y %H:%M')
                    
                    alarm = {
                        'home': home,
                        'away': away,
                        'market': market_names.get(market, market),
                        'selection': selection,
                        'incoming_money': max_incoming,
                        'selection_total': selection_total,
                        'is_huge': is_huge,
                        'huge_total': huge_total if is_huge else 0,
                        'alarm_type': 'HUGE MONEY' if is_huge else 'BIG MONEY',
                        'big_money_limit': limit,
                        'snapshot_count': len(big_money_snapshots),
                        'match_date': match_date_str,
                        'event_time': event_time,
                        'created_at': created_at
                    }
                    alarms.append(alarm)
                    
                    alarm_type = "HUGE MONEY" if is_huge else "BIG MONEY"
                    print(f"[BigMoney] {alarm_type}: {home} vs {away} [{selection}] £{max_incoming:,.0f}")
        
        except Exception as e:
            print(f"[BigMoney] Error processing {market}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Tetiklenme zamanına göre sırala (en yeni en üstte)
    alarms.sort(key=lambda x: parse_created_at_for_sort(x.get('created_at', '')), reverse=True)
    
    print(f"[BigMoney] Total alarms found: {len(alarms)}")
    return alarms


# ============================================================================
# DROPPING ALERT ALARM SYSTEM
# ============================================================================

DROPPING_CONFIG_FILE = 'dropping_config.json'
DROPPING_ALARMS_FILE = 'dropping_alarms.json'

dropping_calculating = False
dropping_calc_progress = ""

def load_dropping_config():
    """Load Dropping Alert config from JSON file - NO DEFAULTS (tüm değerler Supabase'den gelmeli)"""
    config = {}
    try:
        if os.path.exists(DROPPING_CONFIG_FILE):
            with open(DROPPING_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                print(f"[Dropping] Config loaded: L1={config.get('min_drop_l1')}-{config.get('max_drop_l1')}%, L2={config.get('min_drop_l2')}-{config.get('max_drop_l2')}%, L3={config.get('min_drop_l3')}%+")
    except Exception as e:
        print(f"[Dropping] Config load error: {e}")
    return config

def save_dropping_config(config):
    """Save Dropping Alert config to both Supabase and JSON file"""
    success = False
    
    # 1. Supabase'e yaz (primary)
    try:
        supabase = get_supabase_client()
        if supabase and supabase.is_available:
            # Eğer config boşsa Supabase'e yazma - filtered_config kullan
            filtered_config = {k: v for k, v in config.items() if v is not None and k != 'enabled'}
            if not filtered_config:
                print("[Dropping] Config boş - Supabase'e yazılmadı")
            elif supabase.update_alarm_setting('dropping', config.get('enabled') if 'enabled' in config else None, filtered_config):
                print(f"[Dropping] Config saved to Supabase")
                success = True
    except Exception as e:
        print(f"[Dropping] Supabase save error: {e}")
    
    # 2. JSON'a yaz (fallback)
    try:
        with open(DROPPING_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"[Dropping] Config saved to JSON")
        success = True
    except Exception as e:
        print(f"[Dropping] JSON save error: {e}")
    
    return success

def load_dropping_alarms_from_file():
    """Load Dropping Alert alarms from JSON file"""
    try:
        if os.path.exists(DROPPING_ALARMS_FILE):
            with open(DROPPING_ALARMS_FILE, 'r') as f:
                alarms = json.load(f)
                print(f"[Dropping] Loaded {len(alarms)} alarms from {DROPPING_ALARMS_FILE}")
                return alarms
    except Exception as e:
        print(f"[Dropping] Alarms load error: {e}")
    return []

def save_dropping_alarms_to_file(alarms):
    """Save Dropping Alert alarms to both Supabase and JSON file"""
    # 1. Supabase'e yaz (primary)
    if write_dropping_alarms_to_supabase(alarms):
        print(f"[Dropping] Alarms written to Supabase")
    
    # 2. JSON'a yaz (fallback)
    try:
        with open(DROPPING_ALARMS_FILE, 'w') as f:
            json.dump(alarms, f, indent=2, ensure_ascii=False)
        print(f"[Dropping] Saved {len(alarms)} alarms to {DROPPING_ALARMS_FILE}")
        return True
    except Exception as e:
        print(f"[Dropping] Alarms save error: {e}")
        return False

dropping_config = load_dropping_config()
dropping_alarms = load_dropping_alarms_from_file()


@app.route('/api/dropping/config', methods=['GET'])
def get_dropping_config():
    """Get Dropping Alert config with default fallback"""
    merged_config = DEFAULT_ALARM_SETTINGS.get('dropping', {}).get('config', {}).copy()
    
    try:
        supabase = get_supabase_client()
        if supabase and supabase.is_available:
            db_setting = supabase.get_alarm_setting('dropping')
            if db_setting:
                db_config = db_setting.get('config')
                if db_config and isinstance(db_config, dict):
                    for key, value in db_config.items():
                        if value is not None:
                            merged_config[key] = value
    except Exception as e:
        print(f"[Dropping Config] Supabase error: {e}")
    
    if isinstance(dropping_config, dict):
        for key, value in dropping_config.items():
            if value is not None:
                merged_config[key] = value
    
    return jsonify(merged_config)


@app.route('/api/dropping/config', methods=['POST'])
def save_dropping_config_endpoint():
    """Save Dropping Alert config"""
    global dropping_config
    try:
        data = request.get_json()
        if data:
            dropping_config.update(data)
            save_dropping_config(dropping_config)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/dropping/alarms', methods=['GET'])
def get_dropping_alarms():
    """Get all Dropping Alert alarms - reads from Supabase first, fallback to local JSON only on error"""
    supabase_alarms = get_dropping_alarms_from_supabase()
    if supabase_alarms is not None:  # Boş liste dahil Supabase verisini kullan
        return jsonify(supabase_alarms)
    return jsonify(dropping_alarms)  # Sadece Supabase hatası durumunda JSON fallback


@app.route('/api/dropping/delete', methods=['POST'])
def delete_dropping_alarms():
    """Delete all Dropping Alert alarms from both Supabase and local JSON"""
    global dropping_alarms
    try:
        dropping_alarms = []
        save_dropping_alarms_to_file(dropping_alarms)
        delete_alarms_from_supabase('dropping_alarms')
        print("[Dropping] All alarms deleted")
        return jsonify({'success': True})
    except Exception as e:
        print(f"[Dropping] Delete error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/dropping/status', methods=['GET'])
def get_dropping_status():
    """Get Dropping Alert calculation status"""
    return jsonify({
        'calculating': dropping_calculating,
        'progress': dropping_calc_progress,
        'alarm_count': len(dropping_alarms)
    })

@app.route('/api/dropping/reset', methods=['POST'])
def reset_dropping_calculation():
    """Reset Dropping calculation flag (force unlock)"""
    global dropping_calculating, dropping_calc_progress
    dropping_calculating = False
    dropping_calc_progress = "Kullanici tarafindan sifirlandi"
    print("[Dropping] Calculation flag reset by user")
    return jsonify({'success': True, 'message': 'Calculation reset'})


@app.route('/api/dropping/calculate', methods=['POST'])
def calculate_dropping_alarms_endpoint():
    """Calculate Dropping Alert alarms based on config"""
    global dropping_alarms, dropping_calculating
    try:
        dropping_calculating = True
        dropping_alarms = calculate_dropping_scores(dropping_config)
        save_dropping_alarms_to_file(dropping_alarms)
        dropping_calculating = False
        return jsonify({'success': True, 'count': len(dropping_alarms)})
    except Exception as e:
        dropping_calculating = False
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


def find_drop_trigger_time(full_history, odds_key, threshold_pct):
    """
    Find when the drop was first detected by scanning history snapshots.
    Returns the scraped_at of the first snapshot where drop >= threshold.
    
    Args:
        full_history: List of history rows ordered by scraped_at (ascending)
        odds_key: The odds column name (e.g., 'odds1', 'under', 'oddsyes')
        threshold_pct: Minimum drop percentage to consider (e.g., 7%)
    
    Returns:
        scraped_at string when drop first detected, or None
    """
    if not full_history or len(full_history) < 2:
        return None
    
    # Get opening odds from first snapshot
    first_row = full_history[0]
    opening_odds_str = first_row.get(odds_key, '')
    
    # Parse opening odds
    try:
        if opening_odds_str in (None, '', '-'):
            return None
        opening_odds = float(str(opening_odds_str).replace(',', '.').split('\n')[0])
        if opening_odds <= 0:
            return None
    except:
        return None
    
    # Scan through history to find first drop >= threshold
    for row in full_history[1:]:  # Skip first row (it's the opening)
        current_odds_str = row.get(odds_key, '')
        
        try:
            if current_odds_str in (None, '', '-'):
                continue
            current_odds = float(str(current_odds_str).replace(',', '.').split('\n')[0])
            if current_odds <= 0:
                continue
        except:
            continue
        
        # Calculate drop percentage
        if current_odds < opening_odds:
            drop_pct = ((opening_odds - current_odds) / opening_odds) * 100
            if drop_pct >= threshold_pct:
                # Found the first snapshot where drop crossed threshold
                return row.get('scraped_at', '')
    
    return None


def calculate_dropping_scores(config):
    """
    Calculate Dropping Alert alarms based on opening odds vs current odds drop percentage.
    Uses get_6h_odds_history which efficiently compares first snapshot vs last snapshot.
    
    IMPORTANT: Only creates alarms for matches that exist in BOTH Moneyway AND Dropping markets:
    - 1X2 selections: Match must be in moneyway_1x2 AND dropping_1x2
    - O/U 2.5 selections: Match must be in moneyway_ou25 AND dropping_ou25
    - BTTS selections: Match must be in moneyway_btts AND dropping_btts
    
    L1: min_drop_l1% - max_drop_l1% drop (e.g., 7-10%)
    L2: min_drop_l2% - max_drop_l2% drop (e.g., 10-15%)
    L3: min_drop_l3%+ drop (e.g., 15%+)
    
    TIMESTAMP PRESERVATION:
    - created_at: Set to the time when drop was FIRST detected (from history scraped_at)
    - event_time: Updated on each recalculation to show latest refresh time
    """
    global dropping_calc_progress
    alarms = []
    supabase = get_supabase_client()
    if not supabase or not supabase.is_available:
        print("[Dropping] Supabase not available")
        return alarms
    
    # Load existing alarms to preserve created_at timestamps
    existing_alarms = load_dropping_alarms_from_file()
    existing_map = {}
    for ea in existing_alarms:
        # Key: match_id + market + selection
        key = f"{ea.get('match_id', '')}|{ea.get('market', '')}|{ea.get('selection', '')}"
        existing_map[key] = ea
    print(f"[Dropping] Loaded {len(existing_map)} existing alarms for timestamp preservation")
    
    # NO DEFAULTS - tüm değerler Supabase'den gelmeli (None kontrolü)
    min_drop_l1 = config.get('min_drop_l1')
    max_drop_l1 = config.get('max_drop_l1')
    min_drop_l2 = config.get('min_drop_l2')
    max_drop_l2 = config.get('max_drop_l2')
    min_drop_l3 = config.get('min_drop_l3')
    l2_enabled = config.get('l2_enabled')
    l3_enabled = config.get('l3_enabled')
    
    # Config eksikse hesaplama yapma
    missing = []
    if min_drop_l1 is None: missing.append('min_drop_l1')
    if missing:
        print(f"[Dropping] CONFIG EKSIK - Supabase'den config yüklenemedi! Eksik: {missing}")
        return alarms
    
    max_odds_1x2 = config.get('max_odds_1x2')
    max_odds_ou25 = config.get('max_odds_ou25')
    max_odds_btts = config.get('max_odds_btts')
    max_odds_map = {
        'dropping_1x2': max_odds_1x2,
        'dropping_ou25': max_odds_ou25,
        'dropping_btts': max_odds_btts
    }
    
    print(f"[Dropping] Config: L1={min_drop_l1}-{max_drop_l1}%, L2={min_drop_l2}-{max_drop_l2}%, L3={min_drop_l3}%+")
    print(f"[Dropping] Max Odds: 1X2={max_odds_1x2}, OU={max_odds_ou25}, BTTS={max_odds_btts}")
    
    markets = ['dropping_1x2', 'dropping_ou25', 'dropping_btts']
    market_names = {'dropping_1x2': '1X2', 'dropping_ou25': 'O/U 2.5', 'dropping_btts': 'BTTS'}
    moneyway_markets = {'dropping_1x2': 'moneyway_1x2', 'dropping_ou25': 'moneyway_ou25', 'dropping_btts': 'moneyway_btts'}
    selection_map = {
        'dropping_1x2': {'odds1': '1', 'oddsx': 'X', 'odds2': '2'},
        'dropping_ou25': {'under': 'Under', 'over': 'Over'},
        'dropping_btts': {'oddsyes': 'Yes', 'oddsno': 'No'}
    }
    
    created_at = now_turkey().strftime('%d.%m.%Y %H:%M')
    
    for idx, market in enumerate(markets):
        try:
            dropping_calc_progress = f"{market_names.get(market, market)} isleniyor... ({idx+1}/3)"
            
            # Get corresponding Moneyway market data to check if match exists there + get match dates
            moneyway_market = moneyway_markets.get(market)
            moneyway_matches = set()
            moneyway_dates = {}
            if moneyway_market:
                moneyway_data = supabase.get_all_matches_with_latest(moneyway_market)
                if moneyway_data:
                    for m in moneyway_data:
                        home = (m.get('home') or m.get('home_team') or m.get('Home') or '').lower().strip()
                        away = (m.get('away') or m.get('away_team') or m.get('Away') or '').lower().strip()
                        league = (m.get('league') or '').lower().strip()
                        match_date_raw = m.get('date') or ''
                        if home and away:
                            key = f"{home}|{away}|{league}"
                            moneyway_matches.add(key)
                            moneyway_dates[key] = match_date_raw
                    print(f"[Dropping] Loaded {len(moneyway_matches)} matches from {moneyway_market} for cross-check")
            
            trend_data = supabase.get_6h_odds_history(market)
            if not trend_data:
                print(f"[Dropping] No trend data for {market}")
                continue
            
            print(f"[Dropping] Processing {len(trend_data)} matches for {market}")
            sel_map = selection_map.get(market, {})
            skipped_count = 0
            
            for match_key, match_data in trend_data.items():
                home = match_data.get('home') or ''
                away = match_data.get('away') or ''
                league = match_data.get('league') or ''
                values = match_data.get('values', {})
                
                # Check if match exists in corresponding Moneyway market
                home_lower = home.lower().strip() if home else ''
                away_lower = away.lower().strip() if away else ''
                league_lower = league.lower().strip() if league else ''
                match_check_key = f"{home_lower}|{away_lower}|{league_lower}"
                
                # Get match_date from moneyway data
                match_date = moneyway_dates.get(match_check_key, '')
                
                if moneyway_matches and match_check_key not in moneyway_matches:
                    # Try partial match for team name variations
                    found = False
                    found_key = None
                    for mw_key in moneyway_matches:
                        parts = mw_key.split('|')
                        mw_home = parts[0] if len(parts) > 0 else ''
                        mw_away = parts[1] if len(parts) > 1 else ''
                        mw_league = parts[2] if len(parts) > 2 else ''
                        if (home_lower in mw_home or mw_home in home_lower) and \
                           (away_lower in mw_away or mw_away in away_lower) and \
                           (league_lower in mw_league or mw_league in league_lower or not league_lower or not mw_league):
                            found = True
                            found_key = mw_key
                            break
                    if not found:
                        skipped_count += 1
                        continue
                    # Get date from partial match
                    if found_key:
                        match_date = moneyway_dates.get(found_key, '')
                
                if not home or not away:
                    continue
                
                for odds_key, sel_data in values.items():
                    selection = sel_map.get(odds_key, odds_key)
                    
                    opening_odds = sel_data.get('old')
                    current_odds = sel_data.get('new')
                    pct_change = sel_data.get('pct_change', 0)
                    trend = sel_data.get('trend', 'stable')
                    
                    if opening_odds is None or current_odds is None:
                        continue
                    
                    if opening_odds <= 0 or current_odds <= 0:
                        continue
                    
                    if trend != 'down':
                        continue
                    
                    max_odds_limit = max_odds_map.get(market, 5.0)
                    if opening_odds > max_odds_limit:
                        continue
                    
                    drop_pct = abs(pct_change)
                    
                    level = None
                    if drop_pct >= min_drop_l3 and l3_enabled:
                        level = 'L3'
                    elif min_drop_l2 <= drop_pct < max_drop_l2 and l2_enabled:
                        level = 'L2'
                    elif min_drop_l1 <= drop_pct < max_drop_l1:
                        level = 'L1'
                    
                    if not level:
                        continue
                    
                    if not match_date or match_date == '2025' or len(match_date) < 5:
                        continue
                    
                    match_id = generate_match_id(home, away, league, match_date)
                    market_name = market_names.get(market, market)
                    
                    # Check if alarm already exists to preserve created_at
                    alarm_key = f"{match_id}|{market_name}|{selection}"
                    existing_alarm = existing_map.get(alarm_key)
                    
                    # Find when the drop was first detected by scanning history
                    full_history = match_data.get('full_history', [])
                    trigger_scraped_at = find_drop_trigger_time(full_history, odds_key, min_drop_l1)
                    
                    # Convert ISO format to Turkey time format (DD.MM.YYYY HH:MM)
                    actual_event_time = created_at  # fallback
                    if trigger_scraped_at:
                        try:
                            from datetime import datetime
                            import pytz
                            # Parse ISO format: 2025-12-04T17:13:01
                            if 'T' in trigger_scraped_at:
                                dt = datetime.fromisoformat(trigger_scraped_at.replace('Z', '+00:00'))
                                turkey_tz = pytz.timezone('Europe/Istanbul')
                                if dt.tzinfo is None:
                                    dt = pytz.UTC.localize(dt)
                                dt_turkey = dt.astimezone(turkey_tz)
                                actual_event_time = dt_turkey.strftime('%d.%m.%Y %H:%M')
                        except Exception as e:
                            print(f"[Dropping] Date parse error: {e}")
                    
                    # Use existing created_at if alarm exists, otherwise use actual event time
                    alarm_created_at = existing_alarm.get('created_at', actual_event_time) if existing_alarm else actual_event_time
                    
                    alarm = {
                        'home': home,
                        'away': away,
                        'home_team': home,
                        'away_team': away,
                        'match_id': match_id,
                        'league': league,
                        'market': market_name,
                        'selection': selection,
                        'level': level,
                        'opening_odds': round(opening_odds, 2),
                        'current_odds': round(current_odds, 2),
                        'drop_pct': round(drop_pct, 2),
                        'volume': 0,
                        'match_date': match_date,
                        'fixture_date': match_date,
                        'event_time': created_at,
                        'created_at': alarm_created_at
                    }
                    alarms.append(alarm)
                    print(f"[Dropping] {level}: {home} vs {away} [{selection}] {opening_odds:.2f}->{current_odds:.2f} ({drop_pct:.1f}%) date={match_date}")
            
            if skipped_count > 0:
                print(f"[Dropping] Skipped {skipped_count} matches not found in {moneyway_market}")
        
        except Exception as e:
            print(f"[Dropping] Error processing {market}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Tetiklenme zamanına göre sırala (en yeni en üstte)
    alarms.sort(key=lambda x: parse_created_at_for_sort(x.get('created_at', '')), reverse=True)
    
    print(f"[Dropping] Total alarms found: {len(alarms)}")
    return alarms


# ============================================================================
# VOLUME SHOCK (HACİM ŞOKU) ALARM SYSTEM
# ============================================================================

VOLUME_SHOCK_CONFIG_FILE = 'volume_shock_config.json'
VOLUME_SHOCK_ALARMS_FILE = 'volume_shock_alarms.json'

volume_shock_calculating = False
volume_shock_calc_progress = ""
volume_shock_alarms = []

def load_volume_shock_config():
    """Load Volume Shock config from JSON file - NO DEFAULTS (tüm değerler Supabase'den gelmeli)"""
    config = {}
    try:
        if os.path.exists(VOLUME_SHOCK_CONFIG_FILE):
            with open(VOLUME_SHOCK_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                print(f"[VolumeShock] Config loaded: min_saat={config.get('hacim_soku_min_saat')}, min_esik={config.get('hacim_soku_min_esik')}")
    except Exception as e:
        print(f"[VolumeShock] Config load error: {e}")
    return config

def save_volume_shock_config(config):
    """Save Volume Shock config to both Supabase and JSON file"""
    success = False
    
    # 1. Supabase'e yaz (primary)
    try:
        supabase = get_supabase_client()
        if supabase and supabase.is_available:
            # Eğer config boşsa Supabase'e yazma - filtered_config kullan
            filtered_config = {k: v for k, v in config.items() if v is not None and k != 'enabled'}
            if not filtered_config:
                print("[VolumeShock] Config boş - Supabase'e yazılmadı")
            elif supabase.update_alarm_setting('volumeshock', config.get('enabled') if 'enabled' in config else None, filtered_config):
                print(f"[VolumeShock] Config saved to Supabase")
                success = True
    except Exception as e:
        print(f"[VolumeShock] Supabase save error: {e}")
    
    # 2. JSON'a yaz (fallback)
    try:
        with open(VOLUME_SHOCK_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"[VolumeShock] Config saved to JSON: min_saat={config.get('hacim_soku_min_saat')}, min_esik={config.get('hacim_soku_min_esik')}")
        success = True
    except Exception as e:
        print(f"[VolumeShock] JSON save error: {e}")
    
    return success

def load_volume_shock_alarms_from_file():
    """Load Volume Shock alarms from JSON file"""
    try:
        if os.path.exists(VOLUME_SHOCK_ALARMS_FILE):
            with open(VOLUME_SHOCK_ALARMS_FILE, 'r') as f:
                alarms = json.load(f)
                print(f"[VolumeShock] Loaded {len(alarms)} alarms from {VOLUME_SHOCK_ALARMS_FILE}")
                return alarms
    except Exception as e:
        print(f"[VolumeShock] Alarms load error: {e}")
    return []

def save_volume_shock_alarms_to_file(alarms):
    """Save Volume Shock alarms to both Supabase and JSON file"""
    # 1. Supabase'e yaz (primary)
    if write_volumeshock_alarms_to_supabase(alarms):
        print(f"[VolumeShock] Alarms written to Supabase")
    
    # 2. JSON'a yaz (fallback)
    try:
        with open(VOLUME_SHOCK_ALARMS_FILE, 'w') as f:
            json.dump(alarms, f, indent=2, ensure_ascii=False)
        print(f"[VolumeShock] Saved {len(alarms)} alarms to {VOLUME_SHOCK_ALARMS_FILE}")
        return True
    except Exception as e:
        print(f"[VolumeShock] Alarms save error: {e}")
        return False

volume_shock_config = load_volume_shock_config()
volume_shock_alarms = load_volume_shock_alarms_from_file()

@app.route('/api/volumeshock/config', methods=['GET'])
def get_volume_shock_config():
    """Get Volume Shock config with default fallback"""
    merged_config = DEFAULT_ALARM_SETTINGS.get('volumeshock', {}).get('config', {}).copy()
    
    try:
        supabase = get_supabase_client()
        if supabase and supabase.is_available:
            db_setting = supabase.get_alarm_setting('volumeshock')
            if db_setting:
                db_config = db_setting.get('config')
                if db_config and isinstance(db_config, dict):
                    for key, value in db_config.items():
                        if value is not None:
                            merged_config[key] = value
    except Exception as e:
        print(f"[VolumeShock Config] Supabase error: {e}")
    
    if isinstance(volume_shock_config, dict):
        for key, value in volume_shock_config.items():
            if value is not None:
                merged_config[key] = value
    
    return jsonify(merged_config)

@app.route('/api/volumeshock/config', methods=['POST'])
def save_volume_shock_config_api():
    """Save Volume Shock config"""
    global volume_shock_config
    try:
        data = request.get_json()
        if data:
            volume_shock_config.update(data)
            save_volume_shock_config(volume_shock_config)
            print(f"[VolumeShock] Config updated: min_saat={volume_shock_config.get('hacim_soku_min_saat')}, min_esik={volume_shock_config.get('hacim_soku_min_esik')}")
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/volumeshock/alarms', methods=['GET'])
def get_volume_shock_alarms():
    """Get all Volume Shock alarms - reads from Supabase first, fallback to local JSON only on error"""
    supabase_alarms = get_volumeshock_alarms_from_supabase()
    if supabase_alarms is not None:  # Boş liste dahil Supabase verisini kullan
        return jsonify(supabase_alarms)
    return jsonify(volume_shock_alarms)  # Sadece Supabase hatası durumunda JSON fallback

@app.route('/api/volumeshock/delete', methods=['POST'])
def delete_volume_shock_alarms():
    """Delete all Volume Shock alarms from both Supabase and local JSON"""
    global volume_shock_alarms
    volume_shock_alarms = []
    save_volume_shock_alarms_to_file(volume_shock_alarms)
    delete_alarms_from_supabase('volumeshock_alarms')
    return jsonify({'success': True})

@app.route('/api/volumeshock/status', methods=['GET'])
def get_volume_shock_status():
    """Get Volume Shock calculation status"""
    return jsonify({
        'calculating': volume_shock_calculating,
        'progress': volume_shock_calc_progress,
        'alarm_count': len(volume_shock_alarms)
    })

@app.route('/api/volumeshock/reset', methods=['POST'])
def reset_volume_shock_calculation():
    """Reset Volume Shock calculation flag (force unlock)"""
    global volume_shock_calculating, volume_shock_calc_progress
    volume_shock_calculating = False
    volume_shock_calc_progress = "Reset by user"
    print("[VolumeShock] Calculation flag reset by user")
    return jsonify({'success': True, 'message': 'Calculation reset'})

@app.route('/api/volumeshock/calculate', methods=['POST'])
def calculate_volume_shock_alarms():
    """Calculate Volume Shock alarms based on current config"""
    global volume_shock_calculating, volume_shock_calc_progress, volume_shock_alarms
    
    if volume_shock_calculating:
        return jsonify({'success': False, 'error': 'Calculation already in progress'})
    
    def run_calculation():
        global volume_shock_calculating, volume_shock_calc_progress, volume_shock_alarms
        volume_shock_calculating = True
        volume_shock_calc_progress = "Starting..."
        
        try:
            alarms = calculate_volume_shock_scores(volume_shock_config)
            volume_shock_alarms = alarms
            save_volume_shock_alarms_to_file(alarms)
            volume_shock_calc_progress = f"Completed: {len(alarms)} alarms"
        except Exception as e:
            volume_shock_calc_progress = f"Error: {str(e)}"
            print(f"[VolumeShock] Calculation error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            volume_shock_calculating = False
    
    import threading
    thread = threading.Thread(target=run_calculation)
    thread.start()
    
    return jsonify({'success': True, 'message': 'Calculation started'})

def parse_match_datetime(date_str):
    """Parse match date/time string to datetime object (Turkey timezone)"""
    try:
        if not date_str:
            return None
        
        today = now_turkey().date()
        
        # Format: "03.Dec 17:00:00" or "03.Dec17:00:00"
        date_str = date_str.replace('  ', ' ').strip()
        
        # Try various formats
        formats = [
            '%d.%b %H:%M:%S',  # 03.Dec 17:00:00
            '%d.%b%H:%M:%S',   # 03.Dec17:00:00
            '%d.%m.%Y %H:%M',  # 03.12.2025 17:00
            '%d.%m.%Y %H:%M:%S'  # 03.12.2025 17:00:00
        ]
        
        for fmt in formats:
            try:
                if '%Y' in fmt:
                    dt = datetime.strptime(date_str, fmt)
                else:
                    dt = datetime.strptime(date_str, fmt)
                    dt = dt.replace(year=today.year)
                return TURKEY_TZ.localize(dt)
            except ValueError:
                continue
        
        return None
    except Exception as e:
        print(f"[VolumeShock] Date parse error: {e} for '{date_str}'")
        return None

def calculate_volume_shock_scores(config):
    """Calculate Volume Shock alarms - only for movements well before match"""
    global volume_shock_calc_progress
    
    # NO DEFAULTS - tüm değerler Supabase'den gelmeli (None kontrolü)
    min_saat = config.get('hacim_soku_min_saat') if config.get('hacim_soku_min_saat') is not None else config.get('min_hours_to_kickoff')
    min_esik = config.get('hacim_soku_min_esik') if config.get('hacim_soku_min_esik') is not None else config.get('volume_shock_multiplier')
    enabled = config.get('enabled')
    
    # Minimum volume eşikleri - None kontrolü
    min_volume_1x2 = config.get('min_volume_1x2')
    min_volume_ou25 = config.get('min_volume_ou25')
    min_volume_btts = config.get('min_volume_btts')
    min_son_snapshot_para = config.get('min_son_snapshot_para')
    
    # Config eksikse hesaplama yapma
    missing = []
    if min_saat is None: missing.append('hacim_soku_min_saat')
    if min_esik is None: missing.append('hacim_soku_min_esik')
    
    if missing:
        print(f"[VolumeShock] CONFIG EKSIK - Supabase'den config yüklenemedi! Eksik: {missing}")
        return []
    
    if enabled is False:
        print("[VolumeShock] Disabled, skipping calculation")
        return []
    
    print(f"[VolumeShock] Config: min_saat={min_saat}, min_esik={min_esik}, min_vol_1x2={min_volume_1x2}, min_vol_ou25={min_volume_ou25}, min_vol_btts={min_volume_btts}, min_snapshot={min_son_snapshot_para}")
    
    supabase = get_supabase_client()
    if not supabase or not supabase.is_available:
        print("[VolumeShock] Supabase not available")
        return []
    
    alarms = []
    
    markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts']
    market_names = {
        'moneyway_1x2': 'Moneyway 1X2',
        'moneyway_ou25': 'Moneyway O/U 2.5',
        'moneyway_btts': 'Moneyway BTTS'
    }
    
    today = now_turkey().date()
    yesterday = today - timedelta(days=1)
    now = now_turkey()
    
    for market in markets:
        volume_shock_calc_progress = f"Processing {market}..."
        
        try:
            if '1x2' in market:
                selections = ['1', 'X', '2']
                amount_keys = ['amt1', 'amtx', 'amt2']
                min_volume = min_volume_1x2 if min_volume_1x2 is not None else 0
            elif 'ou25' in market:
                selections = ['Over', 'Under']
                amount_keys = ['amtover', 'amtunder']
                min_volume = min_volume_ou25 if min_volume_ou25 is not None else 0
            else:
                selections = ['Yes', 'No']
                amount_keys = ['amtyes', 'amtno']
                min_volume = min_volume_btts if min_volume_btts is not None else 0
            
            history_table = f"{market}_history"
            matches = supabase.get_all_matches_with_latest(market)
            if not matches:
                continue
            
            # D-2+ filtresi - sadece bugün ve yarın
            filtered_matches = []
            for match in matches:
                match_date_str = match.get('date', '')
                if match_date_str:
                    try:
                        date_part = match_date_str.split()[0]
                        if '.' in date_part:
                            parts = date_part.split('.')
                            if len(parts) == 2:
                                day = int(parts[0])
                                month_abbr = parts[1][:3]
                                month_map = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                                            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
                                month = month_map.get(month_abbr, today.month)
                                match_date = datetime(today.year, month, day).date()
                            elif len(parts) == 3:
                                match_date = datetime.strptime(date_part, '%d.%m.%Y').date()
                            else:
                                match_date = today
                        else:
                            match_date = today
                        
                        if match_date < yesterday:
                            continue
                        filtered_matches.append(match)
                    except:
                        filtered_matches.append(match)
                else:
                    filtered_matches.append(match)
            
            print(f"[VolumeShock] Processing {len(filtered_matches)}/{len(matches)} matches for {market}")
            
            for match in filtered_matches:
                home = match.get('home_team', match.get('home', match.get('Home', '')))
                away = match.get('away_team', match.get('away', match.get('Away', '')))
                match_date_str = match.get('date', '')
                
                if not home or not away:
                    continue
                
                # Demo maçları filtrele
                if 'Citizen AA' in home or 'Lucky Mile' in away:
                    continue
                
                # Market toplam hacim kontrolü - latest objesinden al
                latest = match.get('latest', {})
                total_volume = parse_volume(latest.get('Volume', match.get('volume', '0')))
                if total_volume < min_volume:
                    print(f"[VolumeShock] Skipping {home} vs {away}: volume {total_volume} < min {min_volume}")
                    continue
                
                # Parse match kickoff time
                match_kickoff = parse_match_datetime(match_date_str)
                if not match_kickoff:
                    continue
                
                history = supabase.get_match_history_for_sharp(home, away, history_table)
                if not history or len(history) < 2:
                    continue
                
                for sel_idx, selection in enumerate(selections):
                    amount_key = amount_keys[sel_idx]
                    
                    # Her snapshot için hacim şoku hesapla
                    for i in range(1, len(history)):
                        current_amount = parse_volume(history[i].get(amount_key, '0'))
                        prev_amount = parse_volume(history[i-1].get(amount_key, '0'))
                        
                        # Snapshot zamanı
                        snapshot_time_str = history[i].get('scraped_at', '')
                        if not snapshot_time_str:
                            continue
                        
                        try:
                            snapshot_time = datetime.fromisoformat(snapshot_time_str.replace('Z', '+00:00'))
                            if snapshot_time.tzinfo is None:
                                snapshot_time = TURKEY_TZ.localize(snapshot_time)
                            else:
                                snapshot_time = snapshot_time.astimezone(TURKEY_TZ)
                        except:
                            continue
                        
                        # Maça kaç saat kaldı?
                        time_diff = match_kickoff - snapshot_time
                        hours_to_kickoff = time_diff.total_seconds() / 3600.0
                        
                        # Hacim şoku hesapla
                        if prev_amount > 0 and current_amount > prev_amount:
                            amount_change = current_amount - prev_amount
                            
                            # Gelen para minimum kontrolü
                            if amount_change < min_son_snapshot_para:
                                continue
                            
                            # Son 20 snapshot'ın ortalamasını al
                            prev_amounts = []
                            for j in range(max(0, i-5), i):
                                amt = parse_volume(history[j].get(amount_key, '0'))
                                if amt > 0:
                                    prev_amounts.append(amt)
                            
                            if prev_amounts:
                                avg_prev = sum(prev_amounts) / len(prev_amounts)
                                if avg_prev > 0:
                                    volume_shock = amount_change / avg_prev
                                    
                                    # KOŞUL: Maçtan yeterince önce VE yeterli şok
                                    if hours_to_kickoff >= min_saat and volume_shock >= min_esik:
                                        created_at = now_turkey().strftime('%d.%m.%Y %H:%M')
                                        
                                        alarm = {
                                            'type': 'volume_shock',
                                            'home': home,
                                            'away': away,
                                            'market': market_names.get(market, market),
                                            'selection': selection,
                                            'volume_shock_value': round(volume_shock, 2),
                                            'hours_to_kickoff': round(hours_to_kickoff, 1),
                                            'incoming_money': amount_change,
                                            'avg_previous': round(avg_prev, 2),
                                            'hacim_soku_min_saat': min_saat,
                                            'hacim_soku_min_esik': min_esik,
                                            'match_date': match_date_str,
                                            'event_time': snapshot_time_str,
                                            'created_at': created_at
                                        }
                                        
                                        # Aynı maç/selection için en büyük şoku tut
                                        existing = None
                                        for idx, a in enumerate(alarms):
                                            if a['home'] == home and a['away'] == away and a['selection'] == selection and a['market'] == alarm['market']:
                                                existing = idx
                                                break
                                        
                                        if existing is not None:
                                            if volume_shock > alarms[existing]['volume_shock_value']:
                                                alarms[existing] = alarm
                                        else:
                                            alarms.append(alarm)
                                        
                                        print(f"[VolumeShock] ALARM: {home} vs {away} [{selection}] Shock: {volume_shock:.1f}x, {hours_to_kickoff:.1f}h before match")
        
        except Exception as e:
            print(f"[VolumeShock] Error processing {market}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Tetiklenme zamanına göre sırala (en yeni en üstte)
    alarms.sort(key=lambda x: parse_created_at_for_sort(x.get('created_at', '')), reverse=True)
    
    print(f"[VolumeShock] Total alarms found: {len(alarms)}")
    return alarms


@app.route('/api/sharp/status', methods=['GET'])
def get_sharp_status():
    """Get Sharp calculation status"""
    return jsonify({
        'calculating': sharp_calculating,
        'progress': sharp_calc_progress,
        'alarm_count': len(sharp_alarms)
    })

@app.route('/api/sharp/reset', methods=['POST'])
def reset_sharp_calculation():
    """Reset Sharp calculation flag (force unlock)"""
    global sharp_calculating, sharp_calc_progress
    sharp_calculating = False
    sharp_calc_progress = "Kullanici tarafindan sifirlandi"
    print("[Sharp] Calculation flag reset by user")
    return jsonify({'success': True, 'message': 'Calculation reset'})


@app.route('/api/sharp/config', methods=['GET'])
def get_sharp_config():
    """Get Sharp config with default fallback"""
    merged_config = DEFAULT_ALARM_SETTINGS.get('sharp', {}).get('config', {}).copy()
    
    try:
        supabase = get_supabase_client()
        if supabase and supabase.is_available:
            db_setting = supabase.get_alarm_setting('sharp')
            if db_setting:
                db_config = db_setting.get('config')
                if db_config and isinstance(db_config, dict):
                    for key, value in db_config.items():
                        if value is not None:
                            merged_config[key] = value
    except Exception as e:
        print(f"[Sharp Config] Supabase error: {e}")
    
    if isinstance(sharp_config, dict):
        for key, value in sharp_config.items():
            if value is not None:
                merged_config[key] = value
    
    return jsonify(merged_config)


@app.route('/api/sharp/config', methods=['POST'])
def save_sharp_config():
    """Save Sharp config"""
    global sharp_config
    try:
        data = request.get_json()
        if data:
            sharp_config.update(data)
            save_sharp_config_to_file(sharp_config)
            print(f"[Sharp] Config updated: min_sharp_score={sharp_config.get('min_sharp_score')}, volume_mult={sharp_config.get('volume_multiplier')}, odds_mult={sharp_config.get('odds_multiplier')}, share_mult={sharp_config.get('share_multiplier')}")
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/sharp/alarms', methods=['GET'])
def get_sharp_alarms():
    """Get all Sharp alarms - reads from Supabase first, fallback to local JSON only on error"""
    supabase_alarms = get_sharp_alarms_from_supabase()
    if supabase_alarms is not None:  # Boş liste dahil Supabase verisini kullan
        return jsonify(supabase_alarms)
    return jsonify(sharp_alarms)  # Sadece Supabase hatası durumunda JSON fallback


@app.route('/api/sharp/alarms', methods=['DELETE'])
def delete_sharp_alarms():
    """Delete all Sharp alarms from both Supabase and local JSON"""
    global sharp_alarms
    sharp_alarms = []
    save_sharp_alarms_to_file(sharp_alarms)
    delete_alarms_from_supabase('sharp_alarms')
    return jsonify({'success': True})


@app.route('/api/cleanup', methods=['POST'])
def run_cleanup():
    """Manual cleanup of D-2+ match data"""
    global last_cleanup_date
    
    # Reset last cleanup date to force cleanup
    last_cleanup_date = None
    
    try:
        cleanup_old_matches()
        return jsonify({'success': True, 'message': 'Cleanup completed'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/sharp/calculate', methods=['POST'])
def calculate_sharp_alarms():
    """Calculate Sharp alarms based on current config"""
    global sharp_alarms, sharp_calculating, sharp_calc_progress
    
    if sharp_calculating:
        return jsonify({'success': False, 'error': 'Hesaplama zaten devam ediyor', 'calculating': True})
    
    try:
        sharp_calculating = True
        sharp_calc_progress = "Hesaplama baslatiliyor..."
        sharp_alarms = calculate_sharp_scores(sharp_config)
        save_sharp_alarms_to_file(sharp_alarms)
        sharp_calc_progress = f"Tamamlandi! {len(sharp_alarms)} alarm bulundu."
        sharp_calculating = False
        return jsonify({'success': True, 'count': len(sharp_alarms)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        sharp_calculating = False
        sharp_calc_progress = f"Hata: {str(e)}"
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== HALK TUZAĞI API ENDPOINTS ====================

@app.route('/api/publicmove/status', methods=['GET'])
def get_publicmove_status():
    """Get Public Move calculation status"""
    return jsonify({
        'calculating': publicmove_calculating,
        'progress': publicmove_calc_progress,
        'alarm_count': len(publicmove_alarms)
    })

@app.route('/api/publicmove/reset', methods=['POST'])
def reset_publicmove_calculation():
    """Reset Public Move calculation flag (force unlock)"""
    global publicmove_calculating, publicmove_calc_progress
    publicmove_calculating = False
    publicmove_calc_progress = "Kullanici tarafindan sifirlandi"
    print("[PublicMove] Calculation flag reset by user")
    return jsonify({'success': True, 'message': 'Calculation reset'})


@app.route('/api/publicmove/config', methods=['GET'])
def get_publicmove_config():
    """Get Public Move config with default fallback"""
    merged_config = DEFAULT_ALARM_SETTINGS.get('publicmove', {}).get('config', {}).copy()
    
    try:
        supabase = get_supabase_client()
        if supabase and supabase.is_available:
            db_setting = supabase.get_alarm_setting('publicmove')
            if db_setting:
                db_config = db_setting.get('config')
                if db_config and isinstance(db_config, dict):
                    for key, value in db_config.items():
                        if value is not None:
                            merged_config[key] = value
    except Exception as e:
        print(f"[PublicMove Config] Supabase error: {e}")
    
    if isinstance(publicmove_config, dict):
        for key, value in publicmove_config.items():
            if value is not None:
                merged_config[key] = value
    
    return jsonify(merged_config)


@app.route('/api/publicmove/config', methods=['POST'])
def save_publicmove_config():
    """Save Public Move config"""
    global publicmove_config
    try:
        data = request.get_json()
        if data:
            publicmove_config.update(data)
            save_publicmove_config_to_file(publicmove_config)
            print(f"[PublicMove] Config updated: min_sharp_score={publicmove_config.get('min_sharp_score')}, volume_mult={publicmove_config.get('volume_multiplier')}, odds_mult={publicmove_config.get('odds_multiplier')}, share_mult={publicmove_config.get('share_multiplier')}")
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/publicmove/alarms', methods=['GET'])
def get_publicmove_alarms():
    """Get all Public Move alarms - reads from Supabase first, fallback to local JSON only on error"""
    supabase_alarms = get_publicmove_alarms_from_supabase()
    if supabase_alarms is not None:  # Boş liste dahil Supabase verisini kullan
        return jsonify(supabase_alarms)
    return jsonify(publicmove_alarms)  # Sadece Supabase hatası durumunda JSON fallback


@app.route('/api/publicmove/alarms', methods=['DELETE'])
def delete_publicmove_alarms():
    """Delete all Public Move alarms from both Supabase and local JSON"""
    global publicmove_alarms
    publicmove_alarms = []
    save_publicmove_alarms_to_file(publicmove_alarms)
    delete_alarms_from_supabase('publicmove_alarms')
    return jsonify({'success': True})


@app.route('/api/publicmove/calculate', methods=['POST'])
def calculate_publicmove_alarms():
    """Calculate Public Move alarms based on current config (same logic as Sharp)"""
    global publicmove_alarms, publicmove_calculating, publicmove_calc_progress
    
    if publicmove_calculating:
        return jsonify({'success': False, 'error': 'Hesaplama zaten devam ediyor', 'calculating': True})
    
    try:
        publicmove_calculating = True
        publicmove_calc_progress = "Hesaplama baslatiliyor..."
        publicmove_alarms = calculate_publicmove_scores(publicmove_config)
        save_publicmove_alarms_to_file(publicmove_alarms)
        publicmove_calc_progress = f"Tamamlandi! {len(publicmove_alarms)} alarm bulundu."
        publicmove_calculating = False
        return jsonify({'success': True, 'count': len(publicmove_alarms)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        publicmove_calculating = False
        publicmove_calc_progress = f"Hata: {str(e)}"
        return jsonify({'success': False, 'error': str(e)}), 500


def calculate_publicmove_scores(config):
    """Calculate Public Move scores for all matches based on config (same as Sharp)"""
    global publicmove_calc_progress
    alarms = []
    all_candidates = []
    
    # Kritik config kontrolü - min_sharp_score yoksa hesaplama yapma
    min_sharp_score = config.get('min_sharp_score')
    if min_sharp_score is None:
        print("[PublicMove] CONFIG EKSIK - Supabase'den config yüklenemedi! Eksik: min_sharp_score")
        return alarms
    
    supabase = get_supabase_client()
    if not supabase or not supabase.is_available:
        print("[PublicMove] Supabase not available")
        return alarms
    
    markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts']
    market_names = {'moneyway_1x2': '1X2', 'moneyway_ou25': 'O/U 2.5', 'moneyway_btts': 'BTTS'}
    
    for idx, market in enumerate(markets):
        try:
            # NO DEFAULTS - tüm değerler Supabase'den gelmeli
            if '1x2' in market:
                min_volume = config.get('min_volume_1x2') if config.get('min_volume_1x2') is not None else 0
                selections = ['1', 'X', '2']
            elif 'ou25' in market:
                min_volume = config.get('min_volume_ou25') if config.get('min_volume_ou25') is not None else 0
                selections = ['Over', 'Under']
            else:
                min_volume = config.get('min_volume_btts') if config.get('min_volume_btts') is not None else 0
                selections = ['Yes', 'No']
            
            history_table = f"{market}_history"
            matches = supabase.get_all_matches_with_latest(market)
            
            if not matches:
                print(f"[PublicMove] No matches for {market}")
                continue
            
            publicmove_calc_progress = f"{market_names.get(market, market)} isleniyor... ({idx+1}/3)"
            print(f"[PublicMove] Processing {len(matches)} matches for {market}, min_volume: {min_volume}")
            processed = 0
            skipped_old = 0
            
            today = now_turkey().date()
            yesterday = today - timedelta(days=1)
            
            for match in matches:
                home = match.get('home_team', match.get('home', match.get('Home', '')))
                away = match.get('away_team', match.get('away', match.get('Away', '')))
                
                if not home or not away:
                    continue
                
                match_date_str = match.get('date', '')
                if match_date_str:
                    try:
                        date_part = match_date_str.split()[0]
                        
                        if '.' in date_part:
                            parts = date_part.split('.')
                            if len(parts) == 2:
                                day = int(parts[0])
                                month_abbr = parts[1][:3]
                                month_map = {
                                    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                                    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                                }
                                month = month_map.get(month_abbr, today.month)
                                year = today.year
                                match_date = datetime(year, month, day).date()
                            elif len(parts) == 3:
                                match_date = datetime.strptime(date_part, '%d.%m.%Y').date()
                            else:
                                match_date = today
                        elif '-' in date_part:
                            match_date = datetime.strptime(date_part.split('T')[0], '%Y-%m-%d').date()
                        else:
                            match_date = today
                        
                        if match_date < yesterday:
                            skipped_old += 1
                            continue
                        
                        try:
                            time_parts = match_date_str.split()
                            if len(time_parts) >= 2:
                                time_str = time_parts[1]
                                hour_min = time_str.split(':')
                                match_hour = int(hour_min[0])
                                match_minute = int(hour_min[1]) if len(hour_min) > 1 else 0
                                
                                match_datetime_utc = datetime(match_date.year, match_date.month, match_date.day, match_hour, match_minute)
                                match_datetime_tr = match_datetime_utc + timedelta(hours=3)
                                now = now_turkey()
                                
                                time_to_match = match_datetime_tr - now.replace(tzinfo=None)
                                hours_to_match = time_to_match.total_seconds() / 3600
                                
                                # Public Move kuralı: Sadece maça 2 saatten AZ kaldığında hesapla
                                # Maça 2+ saat varsa hesaplama (Sharp'ın tersi)
                                if hours_to_match >= 2:
                                    print(f"[PublicMove] Skipped {home} vs {away}: {hours_to_match:.1f} hours to kickoff (>= 2h, only last 2h counts)")
                                    continue
                                    
                                # Maç başladıysa (negatif saat) atla
                                if hours_to_match <= 0:
                                    continue
                        except Exception as time_e:
                            pass
                    except Exception as e:
                        print(f"[PublicMove] Date parse error for {home} vs {away}: {match_date_str} - {e}")
                
                latest = match.get('latest', {})
                volume_str = latest.get('Volume', match.get('volume', match.get('Volume', '0')))
                volume = parse_volume(volume_str)
                
                if volume < min_volume:
                    continue
                
                history = supabase.get_match_history_for_sharp(home, away, history_table)
                
                if len(history) < 2:
                    continue
                
                processed += 1
                
                for sel_idx, selection in enumerate(selections):
                    alarm = calculate_selection_publicmove(
                        home, away, market, selection, sel_idx,
                        history, volume, config, match_date_str
                    )
                    if alarm:
                        all_candidates.append(alarm)
                        if alarm.get('triggered'):
                            alarms.append(alarm)
            
            print(f"[PublicMove] Processed {processed} matches with sufficient volume for {market}, skipped {skipped_old} old (D-2+) matches")
        except Exception as e:
            print(f"[PublicMove] Error processing {market}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"[PublicMove] Total candidates: {len(all_candidates)}, Triggered alarms: {len(alarms)}")
    
    # Tetiklenme zamanına göre sırala (en yeni en üstte)
    alarms.sort(key=lambda x: parse_created_at_for_sort(x.get('created_at', '')), reverse=True)
    return alarms


def calculate_selection_publicmove(home, away, market, selection, sel_idx, history, volume, config, match_date_str=''):
    """Calculate Public Move score for a single selection - only last 2 hours of history"""
    if len(history) < 2:
        return None
    
    # PUBLIC MOVE: Sadece son 2 saatteki hareketlere bak
    now = now_turkey()
    two_hours_ago = now - timedelta(hours=2)
    
    filtered_history = []
    for snap in history:
        scraped_at = snap.get('scraped_at', '')
        if scraped_at:
            try:
                # Parse scraped_at timestamp
                if 'T' in scraped_at:
                    snap_time_str = scraped_at.split('+')[0].split('.')[0]
                    snap_time = datetime.strptime(snap_time_str, '%Y-%m-%dT%H:%M:%S')
                else:
                    snap_time = datetime.strptime(scraped_at[:19], '%Y-%m-%d %H:%M:%S')
                
                # Sadece son 2 saatteki snapshot'ları al
                if snap_time >= two_hours_ago.replace(tzinfo=None):
                    filtered_history.append(snap)
            except:
                # Parse hatası olursa dahil et
                filtered_history.append(snap)
        else:
            filtered_history.append(snap)
    
    # Filtrelenmiş history ile devam et
    history = filtered_history
    
    if len(history) < 2:
        return None
    
    if '1x2' in market:
        amount_keys = ['amt1', 'amtx', 'amt2']
        odds_keys = ['odds1', 'oddsx', 'odds2']
        share_keys = ['pct1', 'pctx', 'pct2']
    elif 'ou25' in market:
        amount_keys = ['amtover', 'amtunder']
        odds_keys = ['over', 'under']
        share_keys = ['pctover', 'pctunder']
    else:
        amount_keys = ['amtyes', 'amtno']
        odds_keys = ['oddsyes', 'oddsno']
        share_keys = ['pctyes', 'pctno']
    
    if sel_idx >= len(amount_keys):
        return None
    
    amount_key = amount_keys[sel_idx]
    odds_key = odds_keys[sel_idx]
    share_key = share_keys[sel_idx]
    
    if len(history) < 2:
        return None
    
    # Kritik config değerlerini al - eksikse None döner ve return None ile çık
    min_sharp_score = config.get('min_sharp_score')
    if min_sharp_score is None:
        return None
    
    # İkincil değerler - None ise güvenli varsayılan kullan (aritmetik hata önleme)
    min_amount_change = config.get('min_amount_change') if config.get('min_amount_change') is not None else 0
    volume_multiplier = config.get('volume_multiplier') if config.get('volume_multiplier') is not None else 1
    max_volume_cap = config.get('max_volume_cap') if config.get('max_volume_cap') is not None else 100
    max_odds_cap = config.get('max_odds_cap') if config.get('max_odds_cap') is not None else 100
    max_share_cap = config.get('max_share_cap') if config.get('max_share_cap') is not None else 100
    min_share_threshold = config.get('min_share') if config.get('min_share') is not None else 0
    
    # Odds ranges - varsayılan aralıklar (Supabase'de yoksa)
    odds_ranges = [
        (config.get('odds_range_1_min') or 1.01, config.get('odds_range_1_max') or 1.50, config.get('odds_range_1_mult') or 1, config.get('odds_range_1_min_drop') or 0),
        (config.get('odds_range_2_min') or 1.50, config.get('odds_range_2_max') or 2.10, config.get('odds_range_2_mult') or 1, config.get('odds_range_2_min_drop') or 0),
        (config.get('odds_range_3_min') or 2.10, config.get('odds_range_3_max') or 3.50, config.get('odds_range_3_mult') or 1, config.get('odds_range_3_min_drop') or 0),
        (config.get('odds_range_4_min') or 3.50, config.get('odds_range_4_max') or 10.00, config.get('odds_range_4_mult') or 1, config.get('odds_range_4_min_drop') or 0),
    ]
    default_odds_multiplier = config.get('odds_multiplier') if config.get('odds_multiplier') is not None else 1
    default_min_drop = config.get('min_drop') if config.get('min_drop') is not None else 0
    
    # Share ranges - varsayılan aralıklar (Supabase'de yoksa)
    share_ranges = [
        (config.get('share_range_1_min') or 0, config.get('share_range_1_max') or 50, config.get('share_range_1_mult') or 1),
        (config.get('share_range_2_min') or 50, config.get('share_range_2_max') or 75, config.get('share_range_2_mult') or 1),
        (config.get('share_range_3_min') or 75, config.get('share_range_3_max') or 90, config.get('share_range_3_mult') or 1),
        (config.get('share_range_4_min') or 90, config.get('share_range_4_max') or 100, config.get('share_range_4_mult') or 1),
    ]
    default_share_multiplier = 1
    
    best_candidate = None
    best_score = 0
    
    for i in range(1, len(history)):
        prev_snap = history[i-1]
        curr_snap = history[i]
        
        prev_amount = parse_volume(prev_snap.get(amount_key, '0'))
        curr_amount = parse_volume(curr_snap.get(amount_key, '0'))
        amount_change = curr_amount - prev_amount
        
        if amount_change < min_amount_change:
            continue
        
        prev_odds = parse_float(prev_snap.get(odds_key, '0'))
        curr_odds = parse_float(curr_snap.get(odds_key, '0'))
        
        # Oran düşüşü hesapla (Sharp ile aynı mantık)
        if prev_odds > 0 and curr_odds < prev_odds:
            drop_pct = ((prev_odds - curr_odds) / prev_odds) * 100
        else:
            drop_pct = 0
        
        prev_share = parse_float(prev_snap.get(share_key, '0').replace('%', ''))
        curr_share = parse_float(curr_snap.get(share_key, '0').replace('%', ''))
        share_diff = curr_share - prev_share
        if share_diff < 0:
            share_diff = 0
        
        if curr_share < min_share_threshold:
            continue
        
        shock_value = min((amount_change / 1000) * volume_multiplier, max_volume_cap)
        
        odds_mult = None
        min_drop_threshold = default_min_drop
        odds_in_range = False
        for r_min, r_max, r_mult, r_min_drop in odds_ranges:
            if r_min <= prev_odds < r_max:
                odds_mult = r_mult
                min_drop_threshold = r_min_drop
                odds_in_range = True
                break
        
        # Oran hiçbir aralığa girmiyorsa bu snapshot'ı atla
        if not odds_in_range:
            continue
        
        # Oran düşüşü yoksa veya minimum eşik altındaysa atla
        if drop_pct < min_drop_threshold:
            continue
        
        # odds_value = düşüş yüzdesi × çarpan (Sharp ile aynı)
        odds_value = min(drop_pct * odds_mult, max_odds_cap)
        
        share_mult = default_share_multiplier
        for r_min, r_max, r_mult in share_ranges:
            if r_min <= prev_share < r_max:
                share_mult = r_mult
                break
        share_value = min(share_diff * share_mult, max_share_cap)
        
        sharp_score = shock_value + odds_value + share_value
        
        if sharp_score > best_score:
            best_score = sharp_score
            best_candidate = {
                'home': home,
                'away': away,
                'market': market,
                'selection': selection,
                'match_date': match_date_str,
                'sharp_score': round(sharp_score, 2),
                'shock_value': round(shock_value, 2),
                'odds_value': round(odds_value, 2),
                'share_value': round(share_value, 2),
                'amount_change': amount_change,
                'current_odds': curr_odds,
                'current_share': curr_share,
                'volume': volume,
                'triggered': min_sharp_score is not None and sharp_score >= min_sharp_score,
                'event_time': now_turkey_iso(),
                'calc_details': {
                    'prev_odds': round(prev_odds, 2),
                    'drop_pct': round(drop_pct, 2),
                    'odds_mult': odds_mult,
                    'min_drop_threshold': min_drop_threshold,
                    'prev_share': round(prev_share, 2),
                    'share_diff': round(share_diff, 2),
                    'share_mult': share_mult,
                    'volume_multiplier': volume_multiplier,
                    'max_volume_cap': max_volume_cap,
                    'max_odds_cap': max_odds_cap,
                    'max_share_cap': max_share_cap,
                    'min_sharp_score': min_sharp_score
                }
            }
    
    return best_candidate


def calculate_sharp_scores(config):
    """Calculate Sharp scores for all matches based on config"""
    global sharp_calc_progress
    alarms = []
    all_candidates = []
    
    # Kritik config kontrolü - min_sharp_score yoksa hesaplama yapma
    min_sharp_score = config.get('min_sharp_score')
    if min_sharp_score is None:
        print("[Sharp] CONFIG EKSIK - Supabase'den config yüklenemedi! Eksik: min_sharp_score")
        return alarms
    
    supabase = get_supabase_client()
    if not supabase or not supabase.is_available:
        print("[Sharp] Supabase not available")
        return alarms
    
    markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts']
    market_names = {'moneyway_1x2': '1X2', 'moneyway_ou25': 'O/U 2.5', 'moneyway_btts': 'BTTS'}
    
    for idx, market in enumerate(markets):
        try:
            # NO DEFAULTS - tüm değerler Supabase'den gelmeli
            if '1x2' in market:
                min_volume = config.get('min_volume_1x2') if config.get('min_volume_1x2') is not None else 0
                selections = ['1', 'X', '2']
            elif 'ou25' in market:
                min_volume = config.get('min_volume_ou25') if config.get('min_volume_ou25') is not None else 0
                selections = ['Over', 'Under']
            else:
                min_volume = config.get('min_volume_btts') if config.get('min_volume_btts') is not None else 0
                selections = ['Yes', 'No']
            
            history_table = f"{market}_history"
            matches = supabase.get_all_matches_with_latest(market)
            
            if not matches:
                print(f"[Sharp] No matches for {market}")
                continue
            
            sharp_calc_progress = f"{market_names.get(market, market)} isleniyor... ({idx+1}/3)"
            print(f"[Sharp] Processing {len(matches)} matches for {market}, min_volume: {min_volume}")
            processed = 0
            skipped_old = 0
            
            # Prematch kuralı: D-2+ maçlar hariç tutulur
            today = now_turkey().date()
            yesterday = today - timedelta(days=1)
            
            for match in matches:
                home = match.get('home_team', match.get('home', match.get('Home', '')))
                away = match.get('away_team', match.get('away', match.get('Away', '')))
                
                if not home or not away:
                    continue
                
                # Maç tarihini kontrol et (D-2+ filtresi)
                match_date_str = match.get('date', '')
                if match_date_str:
                    try:
                        # Format: "29.Nov 15:00:00" veya "DD.MM.YYYY" veya "YYYY-MM-DD"
                        date_part = match_date_str.split()[0]  # "29.Nov" veya "29.11.2025"
                        
                        if '.' in date_part:
                            parts = date_part.split('.')
                            if len(parts) == 2:
                                # Format: "29.Nov" - gün ve ay kısaltması
                                day = int(parts[0])
                                month_abbr = parts[1][:3]  # İlk 3 karakter
                                month_map = {
                                    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                                    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
                                }
                                month = month_map.get(month_abbr, today.month)
                                # Yıl: Eğer ay gelecekte ise geçen yıl, değilse bu yıl
                                year = today.year
                                match_date = datetime(year, month, day).date()
                            elif len(parts) == 3:
                                # Format: "29.11.2025"
                                match_date = datetime.strptime(date_part, '%d.%m.%Y').date()
                            else:
                                match_date = today
                        elif '-' in date_part:
                            # Format: "2025-11-29"
                            match_date = datetime.strptime(date_part.split('T')[0], '%Y-%m-%d').date()
                        else:
                            match_date = today  # Parse edilemezse bugün kabul et
                        
                        # D-2 veya daha eski maçları atla
                        if match_date < yesterday:
                            skipped_old += 1
                            continue
                        
                        # YENI KURAL: Maçın başlamasına 2 saatten az kaldıysa Sharp sayılmaz
                        try:
                            # Saat bilgisini parse et ("02.Dec 18:30:00" formatı)
                            time_parts = match_date_str.split()
                            if len(time_parts) >= 2:
                                time_str = time_parts[1]  # "18:30:00"
                                hour_min = time_str.split(':')
                                match_hour = int(hour_min[0])
                                match_minute = int(hour_min[1]) if len(hour_min) > 1 else 0
                                
                                # Maç datetime'ını oluştur - Arbworld tarihleri ZATEN Türkiye saatinde
                                match_datetime_tr = datetime(match_date.year, match_date.month, match_date.day, match_hour, match_minute)
                                now = now_turkey()
                                
                                # Maça kalan süreyi hesapla
                                time_to_match = match_datetime_tr - now.replace(tzinfo=None)
                                hours_to_match = time_to_match.total_seconds() / 3600
                                
                                # Maç geçmişte veya 2 saatten az kaldıysa Sharp sayılmaz
                                if hours_to_match < 2:
                                    if hours_to_match <= 0:
                                        print(f"[Sharp] Skipped {home} vs {away}: match already started ({hours_to_match:.1f}h ago)")
                                    else:
                                        print(f"[Sharp] Skipped {home} vs {away}: {hours_to_match:.1f} hours to kickoff (< 2h rule)")
                                    continue
                        except Exception as time_e:
                            pass  # Saat parse hatası varsa devam et
                    except Exception as e:
                        print(f"[Sharp] Date parse error for {home} vs {away}: {match_date_str} - {e}")
                        # Parse hatası varsa devam et
                
                history = supabase.get_match_history_for_sharp(home, away, history_table)
                
                if len(history) < 2:
                    continue
                
                processed += 1
                
                for sel_idx, selection in enumerate(selections):
                    alarm = calculate_selection_sharp(
                        home, away, market, selection, sel_idx,
                        history, min_volume, config, match_date_str
                    )
                    if alarm:
                        all_candidates.append(alarm)
                        if alarm.get('triggered'):
                            alarms.append(alarm)
            
            print(f"[Sharp] Processed {processed} matches with sufficient volume for {market}, skipped {skipped_old} old (D-2+) matches")
        except Exception as e:
            print(f"[Sharp] Error processing {market}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"[Sharp] Total candidates: {len(all_candidates)}, Triggered alarms: {len(alarms)}")
    
    if len(alarms) == 0 and len(all_candidates) > 0:
        top_candidates = sorted(all_candidates, key=lambda x: x.get('sharp_score', 0), reverse=True)[:5]
        print("[Sharp] Top 5 candidates (not triggered):")
        for c in top_candidates:
            print(f"  {c.get('home')} vs {c.get('away')} [{c.get('selection')}]: score={c.get('sharp_score', 0):.2f}, triggered={c.get('triggered')}")
            print(f"    shock={c.get('shock_value', 0):.2f}, odds={c.get('odds_value', 0):.2f}, share={c.get('share_value', 0):.2f}")
    
    # Tetiklenme zamanına göre sırala (en yeni en üstte)
    alarms.sort(key=lambda x: parse_created_at_for_sort(x.get('created_at', '')), reverse=True)
    return alarms


def calculate_selection_sharp(home, away, market, selection, sel_idx, history, min_volume, config, match_date_str=''):
    """Calculate Sharp score for a single selection"""
    if len(history) < 2:
        return None
    
    if '1x2' in market:
        amount_keys = ['amt1', 'amtx', 'amt2']
        odds_keys = ['odds1', 'oddsx', 'odds2']
        share_keys = ['pct1', 'pctx', 'pct2']
    elif 'ou25' in market:
        amount_keys = ['amtover', 'amtunder']
        odds_keys = ['over', 'under']
        share_keys = ['pctover', 'pctunder']
    else:
        amount_keys = ['amtyes', 'amtno']
        odds_keys = ['oddsyes', 'oddsno']
        share_keys = ['pctyes', 'pctno']
    
    if sel_idx >= len(amount_keys):
        return None
    
    amount_key = amount_keys[sel_idx]
    odds_key = odds_keys[sel_idx]
    share_key = share_keys[sel_idx]
    
    if len(history) < 2:
        return None
    
    # Kritik config değerlerini al - eksikse None döner ve return None ile çık
    min_sharp_score = config.get('min_sharp_score')
    if min_sharp_score is None:
        return None
    
    # İkincil değerler - None ise güvenli varsayılan kullan (aritmetik hata önleme)
    min_amount_change = config.get('min_amount_change') if config.get('min_amount_change') is not None else 0
    volume_multiplier = config.get('volume_multiplier') if config.get('volume_multiplier') is not None else 1
    max_volume_cap = config.get('max_volume_cap') if config.get('max_volume_cap') is not None else 100
    max_odds_cap = config.get('max_odds_cap') if config.get('max_odds_cap') is not None else 100
    max_share_cap = config.get('max_share_cap') if config.get('max_share_cap') is not None else 100
    min_share_threshold = config.get('min_share') if config.get('min_share') is not None else 0
    
    # Odds ranges - varsayılan aralıklar (Supabase'de yoksa)
    odds_ranges = [
        (config.get('odds_range_1_min') or 1.01, config.get('odds_range_1_max') or 1.50, config.get('odds_range_1_mult') or 1, config.get('odds_range_1_min_drop') or 0),
        (config.get('odds_range_2_min') or 1.50, config.get('odds_range_2_max') or 2.10, config.get('odds_range_2_mult') or 1, config.get('odds_range_2_min_drop') or 0),
        (config.get('odds_range_3_min') or 2.10, config.get('odds_range_3_max') or 3.50, config.get('odds_range_3_mult') or 1, config.get('odds_range_3_min_drop') or 0),
        (config.get('odds_range_4_min') or 3.50, config.get('odds_range_4_max') or 10.00, config.get('odds_range_4_mult') or 1, config.get('odds_range_4_min_drop') or 0),
    ]
    default_odds_multiplier = config.get('odds_multiplier') if config.get('odds_multiplier') is not None else 1
    default_min_drop = 0
    
    # Share ranges - varsayılan aralıklar (Supabase'de yoksa)
    share_ranges = [
        (config.get('share_range_1_min') or 0, config.get('share_range_1_max') or 50, config.get('share_range_1_mult') or 1),
        (config.get('share_range_2_min') or 50, config.get('share_range_2_max') or 75, config.get('share_range_2_mult') or 1),
        (config.get('share_range_3_min') or 75, config.get('share_range_3_max') or 90, config.get('share_range_3_mult') or 1),
        (config.get('share_range_4_min') or 90, config.get('share_range_4_max') or 100, config.get('share_range_4_mult') or 1),
    ]
    default_share_multiplier = 1
    
    best_candidate = None
    best_score = 0
    
    for i in range(1, len(history)):
        prev_snap = history[i-1]
        curr_snap = history[i]
        
        # OLAY ANINDAKI toplam volume kontrolü (curr_snap'taki tüm seçimlerin toplamı)
        curr_total_volume = sum(parse_volume(curr_snap.get(k, '0')) for k in amount_keys)
        if curr_total_volume < min_volume:
            continue  # Bu snapshot'taki volume yetersiz, atla
        
        prev_amt = parse_volume(prev_snap.get(amount_key, '0'))
        curr_amt = parse_volume(curr_snap.get(amount_key, '0'))
        amount_change = curr_amt - prev_amt
        
        if amount_change < min_amount_change:
            continue
        
        prev_odds = parse_float(prev_snap.get(odds_key, '0'))
        curr_odds = parse_float(curr_snap.get(odds_key, '0'))
        
        if prev_odds > 0 and curr_odds < prev_odds:
            drop_pct = ((prev_odds - curr_odds) / prev_odds) * 100
        else:
            drop_pct = 0
        
        prev_share = parse_float(str(prev_snap.get(share_key, '0')).replace('%', ''))
        curr_share = parse_float(str(curr_snap.get(share_key, '0')).replace('%', ''))
        share_diff = curr_share - prev_share
        if share_diff < 0:
            share_diff = 0
        
        if i >= 2:
            prev_amounts = [parse_volume(history[j].get(amount_key, '0')) for j in range(max(0, i-5), i-1)]
            avg_prev = sum(prev_amounts) / len(prev_amounts) if prev_amounts else prev_amt
        else:
            avg_prev = prev_amt
        
        shock_raw = amount_change / avg_prev if avg_prev > 0 else 0
        shock_value = shock_raw * volume_multiplier
        
        odds_multiplier = None
        min_drop_threshold = default_min_drop
        odds_in_range = False
        for range_min, range_max, range_mult, range_min_drop in odds_ranges:
            if range_min <= prev_odds < range_max:
                odds_multiplier = range_mult
                min_drop_threshold = range_min_drop
                odds_in_range = True
                break
        
        # Oran hiçbir aralığa girmiyorsa bu snapshot'ı atla
        if not odds_in_range:
            continue
        
        odds_value = drop_pct * odds_multiplier
        
        share_multiplier = default_share_multiplier
        for range_min, range_max, range_mult in share_ranges:
            if range_min <= prev_share < range_max:
                share_multiplier = range_mult
                break
        
        share_value = share_diff * share_multiplier
        
        volume_contrib = min(shock_value, max_volume_cap)
        odds_contrib = min(odds_value, max_odds_cap)
        share_contrib = min(share_value, max_share_cap)
        sharp_score = volume_contrib + odds_contrib + share_contrib
        
        triggered = (
            curr_share >= min_share_threshold and
            shock_value > 0 and
            odds_value > 0 and
            drop_pct >= min_drop_threshold and
            share_value > 0 and
            min_sharp_score is not None and sharp_score >= min_sharp_score
        )
        
        if triggered and sharp_score > best_score:
            best_score = sharp_score
            best_candidate = {
                'snap_index': i,
                'prev_snap': prev_snap,
                'curr_snap': curr_snap,
                'event_volume': curr_total_volume,
                'amount_change': amount_change,
                'avg_prev': avg_prev,
                'shock_raw': shock_raw,
                'shock_value': shock_value,
                'volume_contrib': volume_contrib,
                'prev_odds': prev_odds,
                'curr_odds': curr_odds,
                'drop_pct': drop_pct,
                'min_drop_threshold': min_drop_threshold,
                'odds_multiplier': odds_multiplier,
                'odds_value': odds_value,
                'odds_contrib': odds_contrib,
                'prev_share': prev_share,
                'curr_share': curr_share,
                'share_diff': share_diff,
                'share_multiplier': share_multiplier,
                'share_value': share_value,
                'share_contrib': share_contrib,
                'sharp_score': sharp_score
            }
    
    if not best_candidate:
        return None
    
    # KRITIK: Final kontrol - gelen para limiti
    if best_candidate['amount_change'] < min_amount_change:
        print(f"[Sharp] REJECTED {home} vs {away} [{selection}]: amount_change={best_candidate['amount_change']:.0f} < min={min_amount_change}")
        return None
    
    event_time = best_candidate['curr_snap'].get('scraped_at', '')
    
    return {
        'home': home,
        'away': away,
        'market': market,
        'selection': selection,
        'match_date': match_date_str,
        'event_time': event_time,
        'created_at': now_turkey_formatted(),
        'amount_change': best_candidate['amount_change'],
        'avg_last_amounts': best_candidate['avg_prev'],
        'shock_raw': best_candidate['shock_raw'],
        'volume_multiplier': volume_multiplier,
        'shock_value': best_candidate['shock_value'],
        'max_volume_cap': max_volume_cap,
        'volume_contrib': best_candidate['volume_contrib'],
        'previous_odds': best_candidate['prev_odds'],
        'current_odds': best_candidate['curr_odds'],
        'drop_pct': best_candidate['drop_pct'],
        'odds_multiplier': best_candidate['odds_multiplier'],
        'odds_value': best_candidate['odds_value'],
        'max_odds_cap': max_odds_cap,
        'odds_contrib': best_candidate['odds_contrib'],
        'previous_share': best_candidate['prev_share'],
        'current_share': best_candidate['curr_share'],
        'share_diff': best_candidate['share_diff'],
        'share_multiplier': best_candidate['share_multiplier'],
        'share_value': best_candidate['share_value'],
        'max_share_cap': max_share_cap,
        'share_contrib': best_candidate['share_contrib'],
        'sharp_score': best_candidate['sharp_score'],
        'min_sharp_score': min_sharp_score,
        'triggered': True
    }


def parse_volume(val):
    """Parse volume string to float"""
    if not val:
        return 0
    try:
        cleaned = str(val).replace('£', '').replace(',', '').replace(' ', '').strip()
        return float(cleaned) if cleaned else 0
    except:
        return 0


def parse_float(val):
    """Parse float from string (handles %, £, commas, etc.)"""
    if not val:
        return 0
    try:
        cleaned = str(val).replace(',', '.').replace('%', '').replace('£', '').strip()
        return float(cleaned) if cleaned else 0
    except:
        return 0


# ==================== VOLUME LEADER CHANGED ALARM SYSTEM ====================
VOLUME_LEADER_CONFIG_FILE = 'volume_leader_config.json'
VOLUME_LEADER_ALARMS_FILE = 'volume_leader_alarms.json'

volume_leader_calculating = False
volume_leader_calc_progress = ""
volume_leader_alarms = []

def load_volume_leader_config():
    """Load Volume Leader config from JSON file - NO DEFAULTS (tüm değerler Supabase'den gelmeli)"""
    config = {}
    try:
        if os.path.exists(VOLUME_LEADER_CONFIG_FILE):
            with open(VOLUME_LEADER_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                print(f"[VolumeLeader] Config loaded: min_1x2={config.get('min_volume_1x2')}, threshold={config.get('leader_threshold')}%")
    except Exception as e:
        print(f"[VolumeLeader] Config load error: {e}")
    return config

def save_volume_leader_config(config):
    """Save Volume Leader config to both Supabase and JSON file"""
    success = False
    
    # 1. Supabase'e yaz (primary)
    try:
        supabase = get_supabase_client()
        if supabase and supabase.is_available:
            # Eğer config boşsa Supabase'e yazma - filtered_config kullan
            filtered_config = {k: v for k, v in config.items() if v is not None and k != 'enabled'}
            if not filtered_config:
                print("[VolumeLeader] Config boş - Supabase'e yazılmadı")
            elif supabase.update_alarm_setting('volumeleader', config.get('enabled') if 'enabled' in config else None, filtered_config):
                print(f"[VolumeLeader] Config saved to Supabase")
                success = True
    except Exception as e:
        print(f"[VolumeLeader] Supabase save error: {e}")
    
    # 2. JSON'a yaz (fallback)
    try:
        with open(VOLUME_LEADER_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"[VolumeLeader] Config saved to JSON: min_1x2={config.get('min_volume_1x2')}, threshold={config.get('leader_threshold')}%")
        success = True
    except Exception as e:
        print(f"[VolumeLeader] JSON save error: {e}")
    
    return success

def load_volume_leader_alarms_from_file():
    """Load Volume Leader alarms from JSON file"""
    try:
        if os.path.exists(VOLUME_LEADER_ALARMS_FILE):
            with open(VOLUME_LEADER_ALARMS_FILE, 'r') as f:
                alarms = json.load(f)
                print(f"[VolumeLeader] Loaded {len(alarms)} alarms from {VOLUME_LEADER_ALARMS_FILE}")
                return alarms
    except Exception as e:
        print(f"[VolumeLeader] Alarms load error: {e}")
    return []

def save_volume_leader_alarms_to_file(alarms):
    """Save Volume Leader alarms to both JSON file and Supabase"""
    success = False
    
    # 1. Supabase'e yaz (primary)
    try:
        if write_volumeleader_alarms_to_supabase(alarms):
            success = True
    except Exception as e:
        print(f"[VolumeLeader] Supabase write error: {e}")
    
    # 2. JSON'a yaz (fallback)
    try:
        with open(VOLUME_LEADER_ALARMS_FILE, 'w') as f:
            json.dump(alarms, f, indent=2, ensure_ascii=False)
        print(f"[VolumeLeader] Saved {len(alarms)} alarms to {VOLUME_LEADER_ALARMS_FILE}")
        success = True
    except Exception as e:
        print(f"[VolumeLeader] JSON save error: {e}")
    
    return success

volume_leader_config = load_volume_leader_config()
volume_leader_alarms = load_volume_leader_alarms_from_file()


@app.route('/api/volumeleader/config', methods=['GET'])
def get_volume_leader_config():
    """Get Volume Leader config with default fallback"""
    merged_config = DEFAULT_ALARM_SETTINGS.get('volumeleader', {}).get('config', {}).copy()
    
    try:
        supabase = get_supabase_client()
        if supabase and supabase.is_available:
            db_setting = supabase.get_alarm_setting('volumeleader')
            if db_setting:
                db_config = db_setting.get('config')
                if db_config and isinstance(db_config, dict):
                    for key, value in db_config.items():
                        if value is not None:
                            merged_config[key] = value
    except Exception as e:
        print(f"[VolumeLeader Config] Supabase error: {e}")
    
    if isinstance(volume_leader_config, dict):
        for key, value in volume_leader_config.items():
            if value is not None:
                merged_config[key] = value
    
    return jsonify(merged_config)


@app.route('/api/volumeleader/config', methods=['POST'])
def save_volume_leader_config_api():
    """Save Volume Leader config"""
    global volume_leader_config
    try:
        data = request.get_json()
        if data:
            volume_leader_config.update(data)
            save_volume_leader_config(volume_leader_config)
            return jsonify({'success': True, 'config': volume_leader_config})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    return jsonify({'success': False, 'error': 'No data'}), 400


@app.route('/api/volumeleader/alarms', methods=['GET'])
def get_volume_leader_alarms():
    """Get Volume Leader alarms - reads from Supabase first, fallback to local JSON only on error"""
    supabase_alarms = get_volumeleader_alarms_from_supabase()
    if supabase_alarms is not None:  # Boş liste dahil Supabase verisini kullan
        return jsonify(supabase_alarms)
    return jsonify(volume_leader_alarms)  # Sadece Supabase hatası durumunda JSON fallback


@app.route('/api/volumeleader/alarms', methods=['DELETE'])
def delete_volume_leader_alarms():
    """Delete all Volume Leader alarms from both Supabase and local JSON"""
    global volume_leader_alarms
    volume_leader_alarms = []
    save_volume_leader_alarms_to_file(volume_leader_alarms)
    delete_alarms_from_supabase('volume_leader_alarms')
    return jsonify({'success': True})


@app.route('/api/volumeleader/status', methods=['GET'])
def get_volume_leader_status():
    """Get Volume Leader calculation status"""
    return jsonify({
        'calculating': volume_leader_calculating,
        'progress': volume_leader_calc_progress
    })


@app.route('/api/alarms/mim', methods=['GET'])
def get_mim_alarms():
    """Get MIM (Market Impact Money) alarms - reads from Supabase"""
    supabase_alarms = get_mim_alarms_from_supabase()
    if supabase_alarms is not None:
        return jsonify(supabase_alarms)
    return jsonify([])


@app.route('/api/mim/config', methods=['GET'])
def get_mim_config():
    """Get MIM config with default fallback"""
    default_config = {
        'min_impact_threshold': 0.10,
        'min_volume': 1000,
        'enabled': True
    }
    
    try:
        supabase = get_supabase_client()
        if supabase and supabase.is_available:
            db_setting = supabase.get_alarm_setting('mim')
            if db_setting:
                db_config = db_setting.get('config')
                if db_config and isinstance(db_config, dict):
                    for key, value in db_config.items():
                        if value is not None:
                            default_config[key] = value
    except Exception as e:
        print(f"[MIM] Config fetch error: {e}")
    
    return jsonify(default_config)


@app.route('/api/mim/config', methods=['POST'])
def save_mim_config():
    """Save MIM config to Supabase"""
    try:
        data = request.get_json()
        if data:
            supabase = get_supabase_client()
            if supabase and supabase.is_available:
                enabled = data.get('enabled', True)
                supabase.update_alarm_setting('mim', enabled, data)
            return jsonify({'success': True, 'config': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    return jsonify({'success': False, 'error': 'No data'}), 400


@app.route('/api/mim/alarms', methods=['DELETE'])
def delete_mim_alarms():
    """Delete all MIM alarms from Supabase"""
    try:
        delete_alarms_from_supabase('mim_alarms')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# TELEGRAM API ENDPOINTS
# ============================================

@app.route('/api/telegram/settings', methods=['GET'])
def get_telegram_settings():
    """Get Telegram settings from Supabase"""
    try:
        supabase = get_supabase_client()
        if supabase and supabase.is_available:
            import httpx
            url = f"{supabase._rest_url('telegram_settings')}?select=*"
            resp = httpx.get(url, headers=supabase._headers(), timeout=10)
            if resp.status_code == 200:
                rows = resp.json()
                settings = {row['setting_key']: row['setting_value'] for row in rows}
                return jsonify({'success': True, 'settings': settings})
        return jsonify({'success': True, 'settings': {}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/telegram/settings', methods=['POST'])
def save_telegram_settings():
    """Save Telegram settings to Supabase"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data'}), 400
        
        supabase = get_supabase_client()
        if supabase and supabase.is_available:
            import httpx
            from datetime import datetime
            headers = supabase._headers()
            headers['Prefer'] = 'resolution=merge-duplicates,return=representation'
            
            for key, value in data.items():
                row_data = [{
                    'setting_key': key,
                    'setting_value': str(value),
                    'updated_at': datetime.now().isoformat()
                }]
                url = f"{supabase._rest_url('telegram_settings')}?on_conflict=setting_key"
                resp = httpx.post(url, headers=headers, json=row_data, timeout=10)
                if resp.status_code not in [200, 201]:
                    return jsonify({'success': False, 'error': f'HTTP {resp.status_code}: {resp.text[:100]}'}), 500
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Supabase not available'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/telegram/test', methods=['POST'])
def test_telegram():
    """Send a test message to Telegram"""
    try:
        import os
        import requests as req
        
        token = os.environ.get('TELEGRAM_BOT_TOKEN') or os.environ.get('TELEGRAM_TOKEN')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        
        if not token or not chat_id:
            return jsonify({'success': False, 'error': 'TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID ayarlanmamis'})
        
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": "SmartXFlow Telegram test mesaji basarili!",
            "disable_web_page_preview": True
        }
        
        response = req.post(url, json=payload, timeout=30)
        if response.status_code == 200:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': f'Telegram API hatasi: {response.status_code}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/telegram/stats', methods=['GET'])
def get_telegram_stats():
    """Get Telegram statistics"""
    try:
        supabase = get_supabase_client()
        result = {
            'success': True,
            'total': 0,
            'today': 0,
            'enabled': False,
            'recent_logs': []
        }
        
        if supabase and supabase.is_available:
            settings_resp = supabase.client.table('telegram_settings').select('*').eq('setting_key', 'telegram_enabled').execute()
            if settings_resp.data and len(settings_resp.data) > 0:
                result['enabled'] = settings_resp.data[0]['setting_value'] == 'true'
            
            total_resp = supabase.client.table('telegram_sent_log').select('id', count='exact').execute()
            result['total'] = total_resp.count if hasattr(total_resp, 'count') else 0
            
            from datetime import datetime, timezone
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            today_resp = supabase.client.table('telegram_sent_log').select('id', count='exact').gte('last_sent_at', today_start).execute()
            result['today'] = today_resp.count if hasattr(today_resp, 'count') else 0
            
            recent_resp = supabase.client.table('telegram_sent_log').select('*').order('last_sent_at', desc=True).limit(20).execute()
            if recent_resp.data:
                result['recent_logs'] = recent_resp.data
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/alarms/all', methods=['GET'])
def get_all_alarms_batch():
    """
    Batch endpoint - Returns all 7 alarm types in a single request.
    Uses server-side cache to reduce response time from ~2s to <50ms.
    
    Query params:
    - types: comma-separated list of alarm types to include (default: all)
      Example: ?types=sharp,bigmoney,mim
    - refresh: set to 'true' to force cache refresh
    """
    import time as t
    start_time = t.time()
    
    requested_types = request.args.get('types', 'all')
    force_refresh = request.args.get('refresh', 'false').lower() == 'true'
    
    # Check server-side cache first (only for 'all' requests)
    if requested_types == 'all':
        cached_data, from_cache = get_cached_alarms(force_refresh)
        if cached_data:
            elapsed = (t.time() - start_time) * 1000
            print(f"[Alarms/All] Cache HIT - {elapsed:.0f}ms")
            return jsonify(cached_data)
    
    result = {}
    
    # Define all alarm types and their fetch functions
    alarm_fetchers = {
        'sharp': (get_sharp_alarms_from_supabase, sharp_alarms if 'sharp_alarms' in dir() else []),
        'bigmoney': (get_bigmoney_alarms_from_supabase, big_money_alarms if 'big_money_alarms' in dir() else []),
        'volumeshock': (get_volumeshock_alarms_from_supabase, volume_shock_alarms if 'volume_shock_alarms' in dir() else []),
        'dropping': (get_dropping_alarms_from_supabase, dropping_alarms if 'dropping_alarms' in dir() else []),
        'volumeleader': (get_volumeleader_alarms_from_supabase, volume_leader_alarms if 'volume_leader_alarms' in dir() else []),
        'mim': (get_mim_alarms_from_supabase, [])
    }
    
    # Determine which types to fetch
    if requested_types == 'all':
        types_to_fetch = list(alarm_fetchers.keys())
    else:
        types_to_fetch = [t.strip() for t in requested_types.split(',') if t.strip() in alarm_fetchers]
    
    # Fetch each alarm type
    for alarm_type in types_to_fetch:
        fetch_func, fallback = alarm_fetchers[alarm_type]
        try:
            supabase_data = fetch_func()
            if supabase_data is not None:
                result[alarm_type] = supabase_data
            else:
                result[alarm_type] = fallback
        except Exception as e:
            print(f"[Alarms/All] Error fetching {alarm_type}: {e}")
            result[alarm_type] = fallback
    
    # Enrich alarms with kickoff time from fixtures table
    try:
        all_hashes = set()
        for alarm_type, alarms in result.items():
            if isinstance(alarms, list):
                for alarm in alarms:
                    h = alarm.get('match_id_hash')
                    if h:
                        all_hashes.add(h)
        
        if all_hashes:
            supabase = get_supabase_client()
            if supabase and supabase.is_available:
                import httpx
                hash_list = list(all_hashes)[:200]
                kickoff_map = {}
                try:
                    hash_filter = ','.join([f'"{h}"' for h in hash_list])
                    url = f"{supabase._rest_url('fixtures')}?select=match_id_hash,kickoff_utc&match_id_hash=in.({hash_filter})"
                    resp = httpx.get(url, headers=supabase._headers(), timeout=15)
                    if resp.status_code == 200:
                        data = resp.json()
                        for row in data:
                            kickoff_map[row['match_id_hash']] = row.get('kickoff_utc')
                except Exception as e:
                    print(f"[Alarms/All] Kickoff fetch error: {e}")
                
                if kickoff_map:
                    for alarm_type, alarms in result.items():
                        if isinstance(alarms, list):
                            for alarm in alarms:
                                h = alarm.get('match_id_hash')
                                if h and h in kickoff_map:
                                    alarm['kickoff_utc'] = kickoff_map[h]
    except Exception as e:
        print(f"[Alarms/All] Kickoff enrichment error: {e}")
    
    # Update server-side cache (only for 'all' requests)
    if requested_types == 'all':
        set_alarm_cache(result)
        elapsed = (t.time() - start_time) * 1000
        print(f"[Alarms/All] Cache MISS - fetched fresh in {elapsed:.0f}ms")
    
    return jsonify(result)


@app.route('/api/match/<match_id>/snapshot', methods=['GET'])
def get_match_snapshot(match_id):
    """
    Full Match Snapshot endpoint - Returns all data for a specific match.
    
    PHASE 2: Uses Supabase RPC get_full_match_snapshot for efficient data retrieval.
    
    IMMUTABLE RESPONSE CONTRACT (per replit.md):
    - metadata: match identification info (match_id, internal_id, home, away, league, kickoff_utc, fixture_date, source)
    - alarms: All 7 alarm types filtered for this match
    - moneyway: Moneyway snapshot data from Phase 2 tables
    - dropping_odds: Dropping odds snapshot data from Phase 2 tables
    - updated_at_utc: ISO 8601 timestamp
    
    URL: /api/match/<match_id_hash>/snapshot
    
    The match_id is a 12-character MD5 hash generated from:
    Format: league|kickoff|home|away (all normalized)
    Use generate_match_id(home, away, league, kickoff) to create it.
    
    Query params:
    - include: comma-separated list of sections to include (default: all)
      Example: ?include=alarms,metadata
    """
    include_sections = request.args.get('include', 'all')
    
    if include_sections == 'all':
        sections_to_include = ['metadata', 'alarms', 'moneyway', 'dropping_odds']
    else:
        sections_to_include = [s.strip() for s in include_sections.split(',')]
    
    result = {}
    rpc_data = None
    
    try:
        supabase = get_supabase_client()
        if supabase:
            rpc_response = supabase.rpc('get_full_match_snapshot', {'p_match_id_hash': match_id}).execute()
            if rpc_response.data:
                raw_data = rpc_response.data
                if isinstance(raw_data, list) and len(raw_data) > 0:
                    rpc_data = raw_data[0] if isinstance(raw_data[0], dict) else raw_data
                elif isinstance(raw_data, dict):
                    rpc_data = raw_data
                else:
                    rpc_data = raw_data
                print(f"[MatchSnapshot] RPC returned data for {match_id}")
    except Exception as e:
        print(f"[MatchSnapshot] RPC error for {match_id}: {e}")
    
    match_found = False
    match_metadata = None
    
    if rpc_data and isinstance(rpc_data, dict):
        rpc_metadata = rpc_data.get('metadata', {})
        if rpc_metadata and isinstance(rpc_metadata, dict) and rpc_metadata.get('source') != 'not_found':
            match_found = True
            match_metadata = rpc_metadata
    
    if not match_found and ('metadata' in sections_to_include or 'alarms' in sections_to_include):
        for market_key in ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts', 
                          'dropping_1x2', 'dropping_ou25', 'dropping_btts']:
            if market_key in matches_cache.get('data', {}):
                for match in matches_cache['data'][market_key]:
                    home = match.get('home_team', match.get('home', ''))
                    away = match.get('away_team', match.get('away', ''))
                    league = match.get('league', '')
                    kickoff = match.get('kickoff', match.get('kickoff_utc', ''))
                    
                    computed_id = generate_match_id(home, away, league, kickoff)
                    if computed_id == match_id:
                        match_found = True
                        match_metadata = {
                            'match_id': match_id,
                            'internal_id': None,
                            'home': home,
                            'away': away,
                            'league': league,
                            'kickoff_utc': kickoff,
                            'fixture_date': match.get('date', match.get('fixture_date', match.get('match_date', ''))),
                            'source': 'cache'
                        }
                        break
                if match_found:
                    break
    
    alarms_result = {}
    first_alarm_metadata = None
    
    if 'alarms' in sections_to_include:
        alarm_fetchers = {
            'sharp': (get_sharp_alarms_from_supabase, sharp_alarms),
            'bigmoney': (get_bigmoney_alarms_from_supabase, big_money_alarms),
            'volumeshock': (get_volumeshock_alarms_from_supabase, volume_shock_alarms),
            'dropping': (get_dropping_alarms_from_supabase, dropping_alarms),
            'volumeleader': (get_volumeleader_alarms_from_supabase, volume_leader_alarms),
            'mim': (get_mim_alarms_from_supabase, [])
        }
        
        for alarm_type, (fetch_func, fallback) in alarm_fetchers.items():
            try:
                all_alarms = fetch_func()
                if all_alarms is None:
                    all_alarms = fallback
                
                filtered = []
                for alarm in all_alarms:
                    alarm_match_id = alarm.get('match_id', '')
                    
                    if alarm_match_id and len(alarm_match_id) == 12:
                        if alarm_match_id == match_id:
                            filtered.append(alarm)
                            if not first_alarm_metadata:
                                first_alarm_metadata = {
                                    'match_id': match_id,
                                    'internal_id': None,
                                    'home': alarm.get('home', alarm.get('home_team', '')),
                                    'away': alarm.get('away', alarm.get('away_team', '')),
                                    'league': alarm.get('league', ''),
                                    'kickoff_utc': alarm.get('kickoff', alarm.get('kickoff_utc', '')),
                                    'fixture_date': alarm.get('fixture_date', alarm.get('match_date', alarm.get('date', ''))),
                                    'source': 'alarm_data'
                                }
                    else:
                        alarm_home = alarm.get('home', alarm.get('home_team', ''))
                        alarm_away = alarm.get('away', alarm.get('away_team', ''))
                        alarm_league = alarm.get('league', '')
                        alarm_kickoff = alarm.get('kickoff', alarm.get('kickoff_utc', ''))
                        
                        computed_alarm_id = generate_match_id(alarm_home, alarm_away, alarm_league, alarm_kickoff)
                        
                        if computed_alarm_id == match_id:
                            filtered.append(alarm)
                            if not first_alarm_metadata:
                                first_alarm_metadata = {
                                    'match_id': match_id,
                                    'internal_id': None,
                                    'home': alarm_home,
                                    'away': alarm_away,
                                    'league': alarm_league,
                                    'kickoff_utc': alarm_kickoff,
                                    'fixture_date': alarm.get('fixture_date', alarm.get('match_date', alarm.get('date', ''))),
                                    'source': 'alarm_data'
                                }
                
                alarms_result[alarm_type] = filtered
            except Exception as e:
                print(f"[MatchSnapshot] Error fetching {alarm_type}: {e}")
                alarms_result[alarm_type] = []
        
        result['alarms'] = alarms_result
    
    if 'metadata' in sections_to_include:
        if match_metadata:
            result['metadata'] = match_metadata
        elif first_alarm_metadata:
            result['metadata'] = first_alarm_metadata
        else:
            result['metadata'] = {
                'match_id': match_id,
                'internal_id': None,
                'home': None,
                'away': None,
                'league': None,
                'kickoff_utc': None,
                'fixture_date': None,
                'source': 'not_found'
            }
    
    if 'moneyway' in sections_to_include:
        if rpc_data and isinstance(rpc_data, dict):
            result['moneyway'] = rpc_data.get('moneyway', [])
        else:
            result['moneyway'] = []
    
    if 'dropping_odds' in sections_to_include:
        if rpc_data and isinstance(rpc_data, dict):
            result['dropping_odds'] = rpc_data.get('dropping_odds', [])
        else:
            result['dropping_odds'] = []
    
    result['updated_at_utc'] = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    
    return jsonify(result)


@app.route('/api/volumeleader/reset', methods=['POST'])
def reset_volume_leader_calculation():
    """Reset Volume Leader calculation flag (force unlock)"""
    global volume_leader_calculating, volume_leader_calc_progress
    volume_leader_calculating = False
    volume_leader_calc_progress = "Kullanici tarafindan sifirlandi"
    print("[VolumeLeader] Calculation flag reset by user")
    return jsonify({'success': True, 'message': 'Calculation reset'})


@app.route('/api/volumeleader/calculate', methods=['POST'])
def calculate_volume_leader_alarms():
    """Calculate Volume Leader alarms"""
    global volume_leader_alarms, volume_leader_calculating, volume_leader_calc_progress
    
    if volume_leader_calculating:
        return jsonify({'success': False, 'error': 'Hesaplama zaten devam ediyor', 'calculating': True})
    
    try:
        volume_leader_calculating = True
        volume_leader_calc_progress = "Hesaplama başlatılıyor..."
        
        new_alarms = calculate_volume_leader_scores(volume_leader_config)
        
        # Merge with existing alarms (avoid duplicates)
        existing_keys = set()
        for alarm in volume_leader_alarms:
            key = f"{alarm.get('home', '')}_{alarm.get('away', '')}_{alarm.get('market', '')}_{alarm.get('old_leader', '')}_{alarm.get('new_leader', '')}_{alarm.get('event_time', '')}"
            existing_keys.add(key)
        
        for alarm in new_alarms:
            key = f"{alarm.get('home', '')}_{alarm.get('away', '')}_{alarm.get('market', '')}_{alarm.get('old_leader', '')}_{alarm.get('new_leader', '')}_{alarm.get('event_time', '')}"
            if key not in existing_keys:
                volume_leader_alarms.append(alarm)
                existing_keys.add(key)
        
        save_volume_leader_alarms_to_file(volume_leader_alarms)
        volume_leader_calc_progress = f"Tamamlandı! {len(new_alarms)} yeni alarm bulundu."
        volume_leader_calculating = False
        return jsonify({'success': True, 'count': len(new_alarms), 'total': len(volume_leader_alarms)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        volume_leader_calculating = False
        volume_leader_calc_progress = f"Hata: {str(e)}"
        return jsonify({'success': False, 'error': str(e)}), 500


def calculate_volume_leader_scores(config):
    """
    Calculate Volume Leader Changed alarms.
    
    ALARM CONDITIONS:
    1. A selection had >= leader_threshold% (default 50%) share
    2. Another selection now has >= leader_threshold% share
    3. Total market volume meets minimum threshold
    
    This indicates the "volume leader" has changed - a significant shift in betting sentiment.
    """
    global volume_leader_calc_progress
    alarms = []
    supabase = get_supabase_client()
    if not supabase or not supabase.is_available:
        print("[VolumeLeader] Supabase not available")
        return alarms
    
    # NO DEFAULTS - tüm değerler Supabase'den gelmeli
    leader_threshold = config.get('leader_threshold')
    if leader_threshold is None:
        print("[VolumeLeader] CONFIG EKSIK - Supabase'den config yüklenemedi! Eksik: leader_threshold")
        return alarms
    print(f"[VolumeLeader] Config: threshold={leader_threshold}%")
    
    markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts']
    market_names = {'moneyway_1x2': '1X2', 'moneyway_ou25': 'O/U 2.5', 'moneyway_btts': 'BTTS'}
    
    # Prematch rule: D-2+ matches excluded
    today = now_turkey().date()
    yesterday = today - timedelta(days=1)
    
    for idx, market in enumerate(markets):
        try:
            # NO DEFAULTS - tüm değerler Supabase'den gelmeli
            if '1x2' in market:
                min_volume = config.get('min_volume_1x2') if config.get('min_volume_1x2') is not None else 0
                selections = ['1', 'X', '2']
                share_keys = ['pct1', 'pctx', 'pct2']
                amount_keys = ['amt1', 'amtx', 'amt2']
            elif 'ou25' in market:
                min_volume = config.get('min_volume_ou25') if config.get('min_volume_ou25') is not None else 0
                selections = ['Over', 'Under']
                share_keys = ['pctover', 'pctunder']
                amount_keys = ['amtover', 'amtunder']
            else:
                min_volume = config.get('min_volume_btts') if config.get('min_volume_btts') is not None else 0
                selections = ['Yes', 'No']
                share_keys = ['pctyes', 'pctno']
                amount_keys = ['amtyes', 'amtno']
            
            history_table = f"{market}_history"
            matches = supabase.get_all_matches_with_latest(market)
            if not matches:
                continue
            
            volume_leader_calc_progress = f"{market_names.get(market, market)} işleniyor... ({idx+1}/3)"
            
            # D-2+ filter
            filtered_matches = []
            for match in matches:
                match_date_str = match.get('date', '')
                if match_date_str:
                    try:
                        date_part = match_date_str.split()[0]
                        if '.' in date_part:
                            parts = date_part.split('.')
                            if len(parts) == 2:
                                day = int(parts[0])
                                month_abbr = parts[1][:3]
                                month_map = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
                                            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12}
                                month = month_map.get(month_abbr, today.month)
                                match_date = datetime(today.year, month, day).date()
                            elif len(parts) == 3:
                                match_date = datetime.strptime(date_part, '%d.%m.%Y').date()
                            else:
                                match_date = today
                        elif '-' in date_part:
                            match_date = datetime.strptime(date_part.split('T')[0], '%Y-%m-%d').date()
                        else:
                            match_date = today
                        
                        # D-2+ filter: Only today and tomorrow
                        if match_date >= yesterday:
                            filtered_matches.append(match)
                    except:
                        filtered_matches.append(match)
                else:
                    filtered_matches.append(match)
            
            print(f"[VolumeLeader] {market}: {len(filtered_matches)} matches after D-2+ filter")
            
            for match in filtered_matches:
                home = match.get('home_team', match.get('home', match.get('Home', '')))
                away = match.get('away_team', match.get('away', match.get('Away', '')))
                match_id = match.get('id', match.get('match_id', ''))
                match_date_str = match.get('date', '')
                
                if not home or not away:
                    continue
                
                # Get history for this match using REST API
                try:
                    from urllib.parse import quote
                    home_enc = quote(home, safe='')
                    away_enc = quote(away, safe='')
                    history_url = f"{supabase.url}/rest/v1/{history_table}?home=eq.{home_enc}&away=eq.{away_enc}&order=scraped_at.desc&limit=50"
                    import httpx
                    resp = httpx.get(history_url, headers=supabase._headers(), timeout=15)
                    
                    if resp.status_code != 200 or not resp.json():
                        continue
                    
                    snapshots = resp.json()
                    if len(snapshots) < 2:
                        continue
                    
                    # DEBUG: Show first few matches with shares
                    if len(alarms) == 0 and len(filtered_matches) > 0 and filtered_matches.index(match) < 3:
                        latest = snapshots[0]
                        debug_volume = sum(parse_volume(latest.get(k, 0)) for k in amount_keys)
                        print(f"[VolumeLeader] DEBUG: {home} vs {away} - {len(snapshots)} snapshots, latest_vol={debug_volume}")
                        for sel, share_key in zip(selections, share_keys):
                            share_val = parse_float(latest.get(share_key, 0))
                            print(f"[VolumeLeader] DEBUG:   {sel}: {share_key}={share_val}%")
                    
                    # Find leader changes in history
                    for i in range(len(snapshots) - 1):
                        current = snapshots[i]
                        previous = snapshots[i + 1]
                        
                        # Calculate volume at trigger time (from current snapshot, not latest)
                        trigger_volume = 0
                        for amt_key in amount_keys:
                            trigger_volume += parse_volume(current.get(amt_key, 0))
                        
                        # Check minimum volume at trigger time
                        if trigger_volume < min_volume:
                            continue
                        
                        # Get shares for each selection
                        current_shares = {}
                        previous_shares = {}
                        
                        for sel, share_key in zip(selections, share_keys):
                            current_shares[sel] = parse_float(current.get(share_key, 0))
                            previous_shares[sel] = parse_float(previous.get(share_key, 0))
                        
                        # Find previous leader (>= threshold%)
                        prev_leader = None
                        prev_leader_share = 0
                        for sel, share in previous_shares.items():
                            if share >= leader_threshold and share > prev_leader_share:
                                prev_leader = sel
                                prev_leader_share = share
                        
                        # Find current leader (>= threshold%)
                        curr_leader = None
                        curr_leader_share = 0
                        for sel, share in current_shares.items():
                            if share >= leader_threshold and share > curr_leader_share:
                                curr_leader = sel
                                curr_leader_share = share
                        
                        # Check if leader changed
                        if prev_leader and curr_leader and prev_leader != curr_leader:
                            # Leader changed! Create alarm
                            event_time = current.get('scraped_at', '')
                            if event_time:
                                try:
                                    if 'T' in event_time:
                                        event_dt = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
                                    else:
                                        event_dt = datetime.strptime(event_time, '%Y-%m-%d %H:%M:%S')
                                    event_time_formatted = event_dt.strftime('%H:%M')
                                except:
                                    event_time_formatted = event_time[:5] if len(event_time) >= 5 else event_time
                            else:
                                event_time_formatted = now_turkey().strftime('%H:%M')
                            
                            alarm = {
                                'type': 'volumeleader',
                                'home': home,
                                'away': away,
                                'match_id': match_id,
                                'market': market_names.get(market, market),
                                'old_leader': prev_leader,
                                'old_leader_share': prev_leader_share,
                                'new_leader': curr_leader,
                                'new_leader_share': curr_leader_share,
                                'total_volume': trigger_volume,
                                'match_date': match_date_str,
                                'event_time': event_time_formatted,
                                'created_at': now_turkey_formatted(),
                                'selection': curr_leader,  # For grouping compatibility
                                'triggered': True
                            }
                            
                            # Check if this exact alarm already exists
                            alarm_key = f"{home}_{away}_{market}_{prev_leader}_{curr_leader}_{event_time_formatted}"
                            existing = False
                            for existing_alarm in alarms:
                                existing_key = f"{existing_alarm.get('home', '')}_{existing_alarm.get('away', '')}_{existing_alarm.get('market', '')}_{existing_alarm.get('old_leader', '')}_{existing_alarm.get('new_leader', '')}_{existing_alarm.get('event_time', '')}"
                                if existing_key == alarm_key:
                                    existing = True
                                    break
                            
                            if not existing:
                                alarms.append(alarm)
                                print(f"[VolumeLeader] ALARM: {home} vs {away} - {market_names.get(market, market)} - {prev_leader} ({prev_leader_share:.1f}%) -> {curr_leader} ({curr_leader_share:.1f}%)")
                            
                            # Only report first leader change per match/market
                            break
                
                except Exception as e:
                    print(f"[VolumeLeader] Error processing {home} vs {away}: {e}")
                    continue
        
        except Exception as e:
            print(f"[VolumeLeader] Error processing {market}: {e}")
            continue
    
    print(f"[VolumeLeader] Found {len(alarms)} total alarms")
    return alarms


DEFAULT_ALARM_SETTINGS = {
    'sharp': {
        'enabled': True,
        'config': {
            'min_share': 1,
            'max_odds_cap': 125,
            'max_share_cap': 1,
            'max_volume_cap': 124,
            'min_volume_1x2': 2999,
            'min_sharp_score': 100,
            'min_volume_btts': 999,
            'min_volume_ou25': 1499,
            'odds_range_1_max': 1.6,
            'odds_range_1_min': 1.01,
            'odds_range_2_max': 2.1,
            'odds_range_2_min': 1.59,
            'odds_range_3_max': 3.5,
            'odds_range_3_min': 2.09,
            'odds_range_4_max': 7,
            'odds_range_4_min': 3.49,
            'min_amount_change': 1999,
            'odds_range_1_mult': 20,
            'odds_range_2_mult': 12,
            'odds_range_3_mult': 8,
            'odds_range_4_mult': 3,
            'share_range_1_max': 30,
            'share_range_1_min': 1,
            'share_range_2_max': 60,
            'share_range_2_min': 30,
            'share_range_3_max': 80,
            'share_range_3_min': 60,
            'share_range_4_max': 100,
            'share_range_4_min': 80,
            'volume_multiplier': 15,
            'share_range_1_mult': 1,
            'share_range_2_mult': 1,
            'share_range_3_mult': 1,
            'share_range_4_mult': 1,
            'odds_range_1_min_drop': 1.5,
            'odds_range_2_min_drop': 3,
            'odds_range_3_min_drop': 7,
            'odds_range_4_min_drop': 15
        }
    },
    'bigmoney': {
        'enabled': True,
        'config': {
            'big_money_limit': 1499
        }
    },
    'volumeshock': {
        'enabled': True,
        'config': {
            'min_volume_1x2': 1999,
            'min_volume_btts': 599,
            'min_volume_ou25': 999,
            'hacim_soku_min_esik': 7,
            'hacim_soku_min_saat': 2,
            'min_son_snapshot_para': 499
        }
    },
    'dropping': {
        'enabled': True,
        'config': {
            'l2_enabled': True,
            'l3_enabled': True,
            'max_drop_l1': 13,
            'max_drop_l2': 20,
            'min_drop_l1': 8,
            'min_drop_l2': 13,
            'min_drop_l3': 20,
            'max_odds_1x2': 3.5,
            'max_odds_btts': 2.35,
            'max_odds_ou25': 2.35,
            'min_volume_1x2': 1,
            'min_volume_btts': 1,
            'min_volume_ou25': 1,
            'persistence_enabled': True,
            'persistence_minutes': 30
        }
    },
    'publicmove': {
        'enabled': True,
        'config': {
            'min_share': 1,
            'max_odds_cap': 80,
            'max_share_cap': 50,
            'max_volume_cap': 70,
            'min_volume_1x2': 2999,
            'min_sharp_score': 60,
            'min_volume_btts': 999,
            'min_volume_ou25': 1499,
            'odds_range_1_max': 1.6,
            'odds_range_1_min': 1.01,
            'odds_range_2_max': 2.1,
            'odds_range_2_min': 1.59,
            'odds_range_3_max': 3.5,
            'odds_range_3_min': 2.09,
            'odds_range_4_max': 7,
            'odds_range_4_min': 3.49,
            'min_amount_change': 1999,
            'odds_range_1_mult': 10,
            'odds_range_2_mult': 6,
            'odds_range_3_mult': 3,
            'odds_range_4_mult': 1.5,
            'share_range_1_max': 30,
            'share_range_1_min': 1,
            'share_range_2_max': 60,
            'share_range_2_min': 30,
            'share_range_3_max': 80,
            'share_range_3_min': 60,
            'share_range_4_max': 100,
            'share_range_4_min': 80,
            'volume_multiplier': 10,
            'share_range_1_mult': 1,
            'share_range_2_mult': 3,
            'share_range_3_mult': 6,
            'share_range_4_mult': 10
        }
    },
    'volumeleader': {
        'enabled': True,
        'config': {
            'min_volume_1x2': 2999,
            'min_volume_btts': 999,
            'min_volume_ou25': 1499,
            'leader_threshold': 50
        }
    }
}

@app.route('/api/alarm-settings')
def get_alarm_settings():
    """Get all alarm settings from database with default fallback"""
    try:
        supabase = get_supabase_client()
        db_settings_dict = {}
        
        if supabase and supabase.is_available:
            db_settings_list = supabase.get_alarm_settings()
            if db_settings_list:
                for row in db_settings_list:
                    alarm_type = row.get('alarm_type', '')
                    if alarm_type:
                        db_settings_dict[alarm_type] = {
                            'enabled': row.get('enabled', True),
                            'config': row.get('config', {})
                        }
        
        merged_settings = {}
        for alarm_type, default_setting in DEFAULT_ALARM_SETTINGS.items():
            if alarm_type in db_settings_dict:
                merged_config = default_setting['config'].copy()
                db_config = db_settings_dict[alarm_type].get('config')
                if db_config and isinstance(db_config, dict):
                    for key, value in db_config.items():
                        if value is not None:
                            merged_config[key] = value
                db_enabled = db_settings_dict[alarm_type].get('enabled')
                merged_settings[alarm_type] = {
                    'enabled': db_enabled if db_enabled is not None else default_setting['enabled'],
                    'config': merged_config
                }
            else:
                merged_settings[alarm_type] = {
                    'enabled': default_setting['enabled'],
                    'config': default_setting['config'].copy()
                }
        
        return jsonify({'status': 'ok', 'settings': merged_settings})
    except Exception as e:
        print(f"[Alarm Settings] Error loading settings, using defaults: {e}")
        return jsonify({'status': 'ok', 'settings': DEFAULT_ALARM_SETTINGS})


@app.route('/api/alarm-settings/<alarm_type>', methods=['GET', 'PUT', 'DELETE'])
def manage_alarm_setting(alarm_type):
    """Get, update or delete a specific alarm setting"""
    try:
        supabase = get_supabase_client()
        
        if request.method == 'GET':
            default_setting = DEFAULT_ALARM_SETTINGS.get(alarm_type)
            merged_config = default_setting['config'].copy() if default_setting else {}
            merged_enabled = default_setting['enabled'] if default_setting else True
            
            if supabase and supabase.is_available:
                db_setting = supabase.get_alarm_setting(alarm_type)
                if db_setting:
                    db_config = db_setting.get('config')
                    if db_config and isinstance(db_config, dict):
                        for key, value in db_config.items():
                            if value is not None:
                                merged_config[key] = value
                    db_enabled = db_setting.get('enabled')
                    if db_enabled is not None:
                        merged_enabled = db_enabled
            
            return jsonify({
                'status': 'ok', 
                'setting': {
                    'alarm_type': alarm_type,
                    'enabled': merged_enabled,
                    'config': merged_config
                }
            })
        
        if not supabase or not supabase.is_available:
            return jsonify({'status': 'error', 'message': 'Supabase not available'})
        
        elif request.method == 'PUT':
            data = request.get_json() or {}
            enabled = data.get('enabled', True)
            config = data.get('config', {})
            
            result = supabase.update_alarm_setting(alarm_type, enabled, config)
            if result:
                print(f"[Admin] Updated alarm setting: {alarm_type} -> enabled={enabled}, config={config}")
                return jsonify({'status': 'ok', 'message': f'{alarm_type} ayarları güncellendi'})
            return jsonify({'status': 'error', 'message': 'Update failed'})
        
        elif request.method == 'DELETE':
            result = supabase.delete_alarm_setting(alarm_type)
            if result:
                print(f"[Admin] Deleted alarm setting: {alarm_type}")
                return jsonify({'status': 'ok', 'message': f'{alarm_type} ayarları silindi'})
            return jsonify({'status': 'error', 'message': 'Delete failed'})
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/scraper/logs')
def get_scraper_logs():
    """Get recent scraper logs for admin panel"""
    try:
        logs = []
        log_file = 'scraper_log.txt'
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                logs = lines[-100:]  # Last 100 lines
        return jsonify({'status': 'ok', 'logs': logs})
    except Exception as e:
        return jsonify({'status': 'error', 'logs': [], 'message': str(e)})


# ============================================
# SCRAPER CONSOLE - Live Log Streaming
# ============================================

@app.route('/scraper/status')
def scraper_console_status():
    """Scraper durumu - canlı konsol için"""
    try:
        # EXE modunda scraper_admin'den state al
        if os.environ.get('SMARTX_DESKTOP') == '1':
            try:
                import scraper_admin
                state = getattr(scraper_admin, 'SCRAPER_STATE', {})
                return jsonify({
                    'status': 'ok',
                    'running': state.get('running', False),
                    'interval_minutes': state.get('interval_minutes', 10),
                    'last_scrape': state.get('last_scrape'),
                    'next_scrape': state.get('next_scrape'),
                    'last_rows': state.get('last_rows', 0),
                    'last_alarm_count': state.get('last_alarm_count', 0),
                    'status_text': state.get('status', 'Bekliyor...')
                })
            except:
                pass
        
        # Server modunda scrape_status kullan
        is_running = scrape_status.get('running', False)
        is_auto = scrape_status.get('auto_running', False)
        is_disabled = is_scraper_disabled()
        
        if is_disabled:
            status_text = 'Devre Dışı (Standalone)'
        elif is_running:
            status_text = 'Veri çekiliyor...'
        elif is_auto:
            status_text = 'Çalışıyor'
        else:
            status_text = 'Durduruldu'
        
        return jsonify({
            'status': 'ok',
            'running': is_auto or is_running,
            'is_scraping': is_running,
            'is_disabled': is_disabled,
            'interval_minutes': scrape_status.get('interval_minutes', 10),
            'last_scrape': scrape_status.get('last_scrape_time'),
            'next_scrape': scrape_status.get('next_scrape_time'),
            'last_rows': 0,
            'last_alarm_count': 0,
            'status_text': status_text
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e), 'running': False})


@app.route('/scraper/control', methods=['POST'])
def scraper_control():
    """Scraper başlat/durdur kontrolü - Desktop ve Server modları"""
    global scrape_status, server_scheduler_thread, server_scheduler_stop
    
    try:
        data = request.get_json() or {}
        action = data.get('action', '')
        
        # EXE (Desktop) modunda scraper_admin fonksiyonlarını kullan
        if os.environ.get('SMARTX_DESKTOP') == '1':
            try:
                import scraper_admin
                
                if action == 'start':
                    config = scraper_admin.get_scraper_config()
                    result = scraper_admin.start_scraper_desktop(config)
                    if result:
                        return jsonify({'status': 'ok', 'message': 'Scraper başlatıldı', 'running': True})
                    else:
                        return jsonify({'status': 'ok', 'message': 'Scraper zaten çalışıyor', 'running': True})
                
                elif action == 'stop':
                    result = scraper_admin.stop_scraper_desktop()
                    if result:
                        return jsonify({'status': 'ok', 'message': 'Scraper durduruldu', 'running': False})
                    else:
                        return jsonify({'status': 'ok', 'message': 'Scraper zaten durdurulmuş', 'running': False})
                
                else:
                    return jsonify({'status': 'error', 'message': 'Geçersiz action'})
                    
            except Exception as e:
                return jsonify({'status': 'error', 'message': f'Desktop kontrol hatası: {str(e)}'})
        
        # Scraper devre dışıysa (Standalone mode)
        if is_scraper_disabled():
            return jsonify({'status': 'error', 'message': 'Scraper devre dışı (Standalone mode)'})
        
        # Server modunda
        if action == 'start':
            if scrape_status.get('auto_running'):
                return jsonify({'status': 'ok', 'message': 'Zaten çalışıyor'})
            
            # Server scheduler'ı başlat
            server_scheduler_stop.clear()
            scrape_status['auto_running'] = True
            scrape_status['interval_minutes'] = get_scrape_interval_seconds() // 60
            
            def scheduler_loop():
                global scrape_status
                interval_seconds = get_scrape_interval_seconds()
                print(f"[Server Scheduler] Restarted - interval: {interval_seconds // 60} minutes")
                
                while not server_scheduler_stop.is_set():
                    if not scrape_status['running']:
                        scrape_status['running'] = True
                        try:
                            print(f"[Server Scheduler] Running scrape at {now_turkey_iso()}")
                            result = run_scraper()
                            scrape_status['last_result'] = result
                            scrape_status['last_scrape_time'] = now_turkey_iso()
                            scrape_status['last_supabase_sync'] = now_turkey_iso()
                            print(f"[Server Scheduler] Scrape completed")
                        except Exception as e:
                            print(f"[Server Scheduler] Error: {e}")
                            scrape_status['last_result'] = {'status': 'error', 'error': str(e)}
                        finally:
                            scrape_status['running'] = False
                    
                    next_time = now_turkey() + timedelta(seconds=interval_seconds)
                    scrape_status['next_scrape_time'] = next_time.isoformat()
                    
                    for _ in range(interval_seconds):
                        if server_scheduler_stop.is_set():
                            break
                        time.sleep(1)
                
                scrape_status['auto_running'] = False
                scrape_status['next_scrape_time'] = None
                print("[Server Scheduler] Stopped")
            
            server_scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
            server_scheduler_thread.start()
            
            return jsonify({'status': 'ok', 'message': 'Scraper başlatıldı', 'running': True})
        
        elif action == 'stop':
            if not scrape_status.get('auto_running'):
                return jsonify({'status': 'ok', 'message': 'Zaten durdurulmuş'})
            
            server_scheduler_stop.set()
            scrape_status['auto_running'] = False
            scrape_status['next_scrape_time'] = None
            
            return jsonify({'status': 'ok', 'message': 'Scraper durduruldu', 'running': False})
        
        else:
            return jsonify({'status': 'error', 'message': 'Geçersiz action'})
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/scraper/interval', methods=['POST'])
def scraper_interval():
    """Scraper interval değiştir"""
    try:
        data = request.get_json() or {}
        new_interval = data.get('interval', 10)
        
        if not isinstance(new_interval, int) or new_interval < 1 or new_interval > 60:
            return jsonify({'status': 'error', 'message': 'Interval 1-60 dakika arasında olmalı'})
        
        # EXE (Desktop) modunda config dosyasını güncelle
        if os.environ.get('SMARTX_DESKTOP') == '1':
            try:
                import scraper_admin
                config = scraper_admin.get_scraper_config()
                config['SCRAPE_INTERVAL_MINUTES'] = new_interval
                scraper_admin.save_config(config)
                scraper_admin.SCRAPER_STATE['interval_minutes'] = new_interval
                scraper_admin.log_scraper(f"Interval değiştirildi: {new_interval} dakika")
                return jsonify({'status': 'ok', 'message': f'Interval {new_interval} dakika olarak ayarlandı', 'interval': new_interval})
            except Exception as e:
                return jsonify({'status': 'error', 'message': f'Config güncellenemedi: {str(e)}'})
        
        # Server modunda global değişkeni güncelle
        global scrape_status
        scrape_status['interval_minutes'] = new_interval
        
        return jsonify({'status': 'ok', 'message': f'Interval {new_interval} dakika olarak ayarlandı', 'interval': new_interval})
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/scraper/logs')
def scraper_console_logs():
    """Son scraper logları"""
    try:
        logs = []
        
        # EXE modunda buffer'dan al
        if os.environ.get('SMARTX_DESKTOP') == '1':
            try:
                import scraper_admin
                buffer = getattr(scraper_admin, 'SCRAPER_LOG_BUFFER', [])
                logs = list(buffer)
            except:
                pass
        
        return jsonify({'status': 'ok', 'logs': logs})
    except Exception as e:
        return jsonify({'status': 'error', 'logs': [], 'message': str(e)})


@app.route('/scraper/stream')
def scraper_console_stream():
    """SSE stream - canlı log akışı (thread-safe)"""
    import queue
    
    def generate():
        q = queue.Queue()
        
        # EXE modunda client listesine thread-safe ekle
        if os.environ.get('SMARTX_DESKTOP') == '1':
            try:
                import scraper_admin
                lock = getattr(scraper_admin, 'SCRAPER_SSE_LOCK', None)
                clients = getattr(scraper_admin, 'SCRAPER_SSE_CLIENTS', [])
                if lock:
                    with lock:
                        clients.append(q)
                else:
                    clients.append(q)
            except:
                pass
        
        try:
            yield f"data: Scraper Console bağlandı\n\n"
            
            while True:
                try:
                    msg = q.get(timeout=15)
                    yield f"data: {msg}\n\n"
                except queue.Empty:
                    yield f": keepalive\n\n"
        finally:
            # Thread-safe cleanup
            if os.environ.get('SMARTX_DESKTOP') == '1':
                try:
                    import scraper_admin
                    lock = getattr(scraper_admin, 'SCRAPER_SSE_LOCK', None)
                    clients = getattr(scraper_admin, 'SCRAPER_SSE_CLIENTS', [])
                    if lock:
                        with lock:
                            if q in clients:
                                clients.remove(q)
                    elif q in clients:
                        clients.remove(q)
                except:
                    pass
    
    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/scraper/console')
def scraper_console_page():
    """Ayrı pencere için scraper konsol sayfası"""
    html = '''<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SmartXFlow Scraper Console</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Consolas', 'Courier New', monospace;
            background: #0d1117;
            color: #c9d1d9;
            padding: 15px;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 15px;
            background: #161b22;
            border-radius: 8px;
            margin-bottom: 15px;
            border: 1px solid #30363d;
        }
        .header h1 {
            font-size: 16px;
            color: #58a6ff;
        }
        .status-badges {
            display: flex;
            gap: 15px;
            font-size: 13px;
        }
        .badge {
            padding: 4px 10px;
            border-radius: 12px;
            background: #21262d;
        }
        .badge.running { background: #238636; }
        .badge.stopped { background: #da3633; }
        .console {
            flex: 1;
            background: #010409;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 15px;
            overflow-y: auto;
            font-size: 13px;
            line-height: 1.6;
        }
        .log-line {
            white-space: pre-wrap;
            word-break: break-all;
        }
        .log-line.error { color: #f85149; }
        .log-line.success { color: #3fb950; }
        .log-line.info { color: #58a6ff; }
        .log-line.separator { color: #484f58; }
        .toolbar {
            display: flex;
            gap: 10px;
            margin-top: 15px;
        }
        button {
            padding: 8px 16px;
            background: #21262d;
            border: 1px solid #30363d;
            color: #c9d1d9;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
        }
        button:hover { background: #30363d; }
    </style>
</head>
<body>
    <div class="header">
        <h1>SmartXFlow Scraper Console</h1>
        <div class="status-badges">
            <span class="badge" id="statusBadge">Bağlanıyor...</span>
            <span class="badge">Interval: <span id="intervalValue">10</span> dk</span>
            <span class="badge">Son: <span id="lastRows">-</span> satır</span>
        </div>
    </div>
    
    <div class="console" id="console"></div>
    
    <div class="toolbar">
        <button onclick="clearConsole()">Temizle</button>
        <button onclick="location.reload()">Yenile</button>
    </div>
    
    <script>
        const consoleEl = document.getElementById('console');
        const statusBadge = document.getElementById('statusBadge');
        
        function addLog(text) {
            const line = document.createElement('div');
            line.className = 'log-line';
            
            if (text.includes('HATA') || text.includes('ERROR')) {
                line.classList.add('error');
            } else if (text.includes('tamamlandı') || text.includes('başarılı')) {
                line.classList.add('success');
            } else if (text.includes('---') || text.includes('===')) {
                line.classList.add('separator');
            } else if (text.includes('başlıyor') || text.includes('çekiliyor')) {
                line.classList.add('info');
            }
            
            line.textContent = text;
            consoleEl.appendChild(line);
            consoleEl.scrollTop = consoleEl.scrollHeight;
        }
        
        function clearConsole() {
            consoleEl.innerHTML = '';
            addLog('[Console temizlendi]');
        }
        
        // Mevcut logları yükle
        fetch('/scraper/logs')
            .then(r => r.json())
            .then(data => {
                if (data.logs) {
                    data.logs.forEach(log => addLog(log));
                }
            });
        
        // Status güncelle
        function updateStatus() {
            fetch('/scraper/status')
                .then(r => r.json())
                .then(data => {
                    if (data.running) {
                        statusBadge.textContent = 'Çalışıyor';
                        statusBadge.className = 'badge running';
                    } else {
                        statusBadge.textContent = 'Durduruldu';
                        statusBadge.className = 'badge stopped';
                    }
                    document.getElementById('intervalValue').textContent = data.interval_minutes || 10;
                    document.getElementById('lastRows').textContent = data.last_rows || '-';
                });
        }
        updateStatus();
        setInterval(updateStatus, 5000);
        
        // SSE bağlantısı
        const evtSource = new EventSource('/scraper/stream');
        evtSource.onmessage = (e) => {
            addLog(e.data);
        };
        evtSource.onerror = () => {
            statusBadge.textContent = 'Bağlantı kesildi';
            statusBadge.className = 'badge stopped';
        };
    </script>
</body>
</html>'''
    return html


@app.route('/admin')
def admin_panel():
    """Admin Panel"""
    return render_template('admin.html')


# ============================================
# ALARM ENGINE CONSOLE - Live Log Streaming
# ============================================

@app.route('/alarm-engine/status')
def alarm_engine_status():
    """Alarm Engine durumu - canlı konsol için"""
    try:
        if os.environ.get('SMARTX_DESKTOP') == '1':
            try:
                import scraper_admin
                state = getattr(scraper_admin, 'ALARM_ENGINE_STATE', {})
                return jsonify({
                    'status': 'ok',
                    'running': state.get('running', False),
                    'last_calculation': state.get('last_calculation'),
                    'next_calculation': state.get('next_calculation'),
                    'last_duration_seconds': state.get('last_duration_seconds', 0),
                    'last_alarm_count': state.get('last_alarm_count', 0),
                    'alarm_summary': state.get('alarm_summary', {}),
                    'configs_loaded': state.get('configs_loaded', False),
                    'status_text': state.get('status', 'Durduruldu')
                })
            except:
                pass
        
        return jsonify({
            'status': 'ok',
            'running': False,
            'last_calculation': None,
            'next_calculation': None,
            'last_duration_seconds': 0,
            'last_alarm_count': 0,
            'alarm_summary': {},
            'configs_loaded': False,
            'status_text': 'Server Modu - EXE Gerekli'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e), 'running': False})


@app.route('/alarm-engine/control', methods=['POST'])
def alarm_engine_control():
    """Alarm Engine başlat/durdur kontrolü - Desktop modu"""
    try:
        data = request.get_json() or {}
        action = data.get('action', '')
        
        if os.environ.get('SMARTX_DESKTOP') == '1':
            try:
                import scraper_admin
                
                if action == 'start':
                    config = scraper_admin.get_scraper_config()
                    result = scraper_admin.start_alarm_engine_desktop(config)
                    if result:
                        return jsonify({'status': 'ok', 'message': 'Alarm Engine başlatıldı', 'running': True})
                    else:
                        return jsonify({'status': 'ok', 'message': 'Alarm Engine zaten çalışıyor', 'running': True})
                
                elif action == 'stop':
                    result = scraper_admin.stop_alarm_engine_desktop()
                    if result:
                        return jsonify({'status': 'ok', 'message': 'Alarm Engine durduruldu', 'running': False})
                    else:
                        return jsonify({'status': 'ok', 'message': 'Alarm Engine zaten durdurulmuş', 'running': False})
                
                else:
                    return jsonify({'status': 'error', 'message': 'Geçersiz action'})
                    
            except Exception as e:
                return jsonify({'status': 'error', 'message': f'Desktop kontrol hatası: {str(e)}'})
        
        return jsonify({'status': 'error', 'message': 'Alarm Engine sadece Desktop modunda çalışır (EXE)'})
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/alarm-engine/logs')
def alarm_engine_logs():
    """Alarm Engine log geçmişi"""
    try:
        if os.environ.get('SMARTX_DESKTOP') == '1':
            try:
                import scraper_admin
                buffer = getattr(scraper_admin, 'ALARM_ENGINE_LOG_BUFFER', [])
                lock = getattr(scraper_admin, 'ALARM_ENGINE_LOG_LOCK', None)
                if lock:
                    with lock:
                        logs = list(buffer)
                else:
                    logs = list(buffer)
                return jsonify({'status': 'ok', 'logs': logs})
            except:
                pass
        return jsonify({'status': 'ok', 'logs': []})
    except Exception as e:
        return jsonify({'status': 'error', 'logs': [], 'message': str(e)})


@app.route('/alarm-engine/stream')
def alarm_engine_stream():
    """Alarm Engine SSE stream - canlı log"""
    def generate():
        q = queue.Queue()
        
        if os.environ.get('SMARTX_DESKTOP') == '1':
            try:
                import scraper_admin
                lock = getattr(scraper_admin, 'ALARM_ENGINE_SSE_LOCK', None)
                clients = getattr(scraper_admin, 'ALARM_ENGINE_SSE_CLIENTS', [])
                if lock:
                    with lock:
                        clients.append(q)
                else:
                    clients.append(q)
            except:
                pass
        
        try:
            while True:
                try:
                    msg = q.get(timeout=15)
                    yield f"data: {msg}\n\n"
                except queue.Empty:
                    yield f": keepalive\n\n"
        finally:
            if os.environ.get('SMARTX_DESKTOP') == '1':
                try:
                    import scraper_admin
                    lock = getattr(scraper_admin, 'ALARM_ENGINE_SSE_LOCK', None)
                    clients = getattr(scraper_admin, 'ALARM_ENGINE_SSE_CLIENTS', [])
                    if lock:
                        with lock:
                            if q in clients:
                                clients.remove(q)
                    elif q in clients:
                        clients.remove(q)
                except:
                    pass
    
    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/alarm-engine/console')
def alarm_engine_console_page():
    """Ayrı pencere için Alarm Engine konsol sayfası"""
    html = '''<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SmartXFlow Alarm Engine Console</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Consolas', 'Courier New', monospace;
            background: #0d1117;
            color: #c9d1d9;
            padding: 15px;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 15px;
            background: #161b22;
            border-radius: 8px;
            margin-bottom: 15px;
            border: 1px solid #30363d;
        }
        .header h1 {
            font-size: 16px;
            color: #f0883e;
        }
        .status-badges {
            display: flex;
            gap: 10px;
            font-size: 12px;
            flex-wrap: wrap;
        }
        .badge {
            padding: 4px 10px;
            border-radius: 12px;
            background: #21262d;
        }
        .badge.running { background: #238636; }
        .badge.stopped { background: #da3633; }
        .badge.calculating { background: #f0883e; animation: pulse 1s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }
        .stats-row {
            display: flex;
            gap: 15px;
            padding: 10px 15px;
            background: #161b22;
            border-radius: 8px;
            margin-bottom: 15px;
            border: 1px solid #30363d;
            flex-wrap: wrap;
        }
        .stat-item {
            display: flex;
            flex-direction: column;
            gap: 2px;
        }
        .stat-label { font-size: 10px; color: #8b949e; }
        .stat-value { font-size: 14px; font-weight: bold; }
        .stat-value.alarm { color: #f0883e; }
        .console {
            flex: 1;
            background: #010409;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 15px;
            overflow-y: auto;
            font-size: 13px;
            line-height: 1.6;
        }
        .log-line {
            white-space: pre-wrap;
            word-break: break-all;
        }
        .log-line.error { color: #f85149; }
        .log-line.success { color: #3fb950; }
        .log-line.info { color: #58a6ff; }
        .log-line.separator { color: #484f58; }
        .log-line.alarm { color: #f0883e; font-weight: bold; }
        .toolbar {
            display: flex;
            gap: 10px;
            margin-top: 15px;
        }
        button {
            padding: 8px 16px;
            background: #21262d;
            border: 1px solid #30363d;
            color: #c9d1d9;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
        }
        button:hover { background: #30363d; }
    </style>
</head>
<body>
    <div class="header">
        <h1>SmartXFlow Alarm Engine Console</h1>
        <div class="status-badges">
            <span class="badge" id="statusBadge">Bağlanıyor...</span>
            <span class="badge">Config: <span id="configStatus">-</span></span>
        </div>
    </div>
    
    <div class="stats-row">
        <div class="stat-item">
            <span class="stat-label">Son Hesaplama</span>
            <span class="stat-value" id="lastCalc">-</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Süre</span>
            <span class="stat-value" id="duration">-</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Toplam Alarm</span>
            <span class="stat-value alarm" id="alarmCount">-</span>
        </div>
        <div class="stat-item">
            <span class="stat-label">Özet</span>
            <span class="stat-value" id="summary">-</span>
        </div>
    </div>
    
    <div class="console" id="console"></div>
    
    <div class="toolbar">
        <button onclick="clearConsole()">Temizle</button>
        <button onclick="location.reload()">Yenile</button>
    </div>
    
    <script>
        const consoleEl = document.getElementById('console');
        const statusBadge = document.getElementById('statusBadge');
        
        function addLog(text) {
            const line = document.createElement('div');
            line.className = 'log-line';
            
            if (text.includes('HATA') || text.includes('ERROR') || text.includes('!!!')) {
                line.classList.add('error');
            } else if (text.includes('TAMAMLANDI') || text.includes('tamamlandı')) {
                line.classList.add('success');
            } else if (text.includes('---') || text.includes('===')) {
                line.classList.add('separator');
            } else if (text.includes('alarm') && text.match(/\\d+/)) {
                line.classList.add('alarm');
            } else if (text.includes('hesaplanıyor') || text.includes('başlıyor')) {
                line.classList.add('info');
            }
            
            line.textContent = text;
            consoleEl.appendChild(line);
            consoleEl.scrollTop = consoleEl.scrollHeight;
        }
        
        function clearConsole() {
            consoleEl.innerHTML = '';
            addLog('[Console temizlendi]');
        }
        
        // Mevcut logları yükle
        fetch('/alarm-engine/logs')
            .then(r => r.json())
            .then(data => {
                if (data.logs) {
                    data.logs.forEach(log => addLog(log));
                }
            });
        
        // Status güncelle
        function updateStatus() {
            fetch('/alarm-engine/status')
                .then(r => r.json())
                .then(data => {
                    if (data.running) {
                        statusBadge.textContent = 'Hesaplanıyor...';
                        statusBadge.className = 'badge calculating';
                    } else {
                        statusBadge.textContent = 'Hazır';
                        statusBadge.className = 'badge running';
                    }
                    
                    document.getElementById('configStatus').textContent = data.configs_loaded ? 'Yüklendi' : 'Yüklenmedi';
                    document.getElementById('alarmCount').textContent = data.last_alarm_count || 0;
                    document.getElementById('duration').textContent = data.last_duration_seconds ? data.last_duration_seconds + 's' : '-';
                    
                    if (data.last_calculation) {
                        const d = new Date(data.last_calculation);
                        document.getElementById('lastCalc').textContent = d.toLocaleTimeString('tr-TR');
                    }
                    
                    if (data.alarm_summary && Object.keys(data.alarm_summary).length > 0) {
                        const parts = Object.entries(data.alarm_summary)
                            .filter(([k,v]) => v > 0)
                            .map(([k,v]) => k[0] + ':' + v);
                        document.getElementById('summary').textContent = parts.join(' ') || '-';
                    }
                });
        }
        updateStatus();
        setInterval(updateStatus, 3000);
        
        // SSE bağlantısı
        const evtSource = new EventSource('/alarm-engine/stream');
        evtSource.onmessage = (e) => {
            addLog(e.data);
        };
        evtSource.onerror = () => {
            statusBadge.textContent = 'Bağlantı kesildi';
            statusBadge.className = 'badge stopped';
        };
    </script>
</body>
</html>'''
    return html


# ============================================
# LICENSE MANAGEMENT API
# ============================================

import secrets
import string
import logging as license_logging
import httpx

def generate_license_key():
    """Generate unique license key: SXF-XXXX-XXXX-XXXX"""
    chars = string.ascii_uppercase + string.digits
    block1 = ''.join(secrets.choice(chars) for _ in range(4))
    block2 = ''.join(secrets.choice(chars) for _ in range(4))
    block3 = ''.join(secrets.choice(chars) for _ in range(4))
    return f"SXF-{block1}-{block2}-{block3}"

def get_license_db():
    """Get Supabase REST API client for license operations"""
    sc = get_supabase_client()
    if not sc or not sc.is_available:
        return None
    return {
        'url': sc.url,
        'headers': {
            "apikey": sc.key,
            "Authorization": f"Bearer {sc.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
    }

def license_select(table, columns='*', filters=None, order_by=None, desc=False):
    """SELECT from license tables"""
    cfg = get_license_db()
    if not cfg:
        return None
    
    url = f"{cfg['url']}/rest/v1/{table}?select={columns}"
    if filters:
        for k, v in filters.items():
            url += f"&{k}=eq.{v}"
    if order_by:
        url += f"&order={order_by}.{'desc' if desc else 'asc'}"
    
    try:
        resp = httpx.get(url, headers=cfg['headers'], timeout=10)
        if resp.status_code == 200:
            return resp.json()
        license_logging.error(f"license_select error: {resp.status_code} - {resp.text}")
        return []
    except Exception as e:
        license_logging.error(f"license_select exception: {e}")
        return []

def license_insert(table, data):
    """INSERT into license tables"""
    cfg = get_license_db()
    if not cfg:
        return None
    
    url = f"{cfg['url']}/rest/v1/{table}"
    try:
        resp = httpx.post(url, headers=cfg['headers'], json=data, timeout=10)
        if resp.status_code in [200, 201]:
            return resp.json()
        license_logging.error(f"license_insert error: {resp.status_code} - {resp.text}")
        return None
    except Exception as e:
        license_logging.error(f"license_insert exception: {e}")
        return None

def license_update(table, data, filters):
    """UPDATE license tables"""
    cfg = get_license_db()
    if not cfg:
        return None
    
    url = f"{cfg['url']}/rest/v1/{table}"
    filter_parts = [f"{k}=eq.{v}" for k, v in filters.items()]
    if filter_parts:
        url += "?" + "&".join(filter_parts)
    
    try:
        resp = httpx.patch(url, headers=cfg['headers'], json=data, timeout=10)
        if resp.status_code in [200, 204]:
            return True
        license_logging.error(f"license_update error: {resp.status_code} - {resp.text}")
        return False
    except Exception as e:
        license_logging.error(f"license_update exception: {e}")
        return False

def license_delete(table, filters):
    """DELETE from license tables"""
    cfg = get_license_db()
    if not cfg:
        return None
    
    url = f"{cfg['url']}/rest/v1/{table}"
    filter_parts = [f"{k}=eq.{v}" for k, v in filters.items()]
    if filter_parts:
        url += "?" + "&".join(filter_parts)
    
    try:
        resp = httpx.delete(url, headers=cfg['headers'], timeout=10)
        if resp.status_code in [200, 204]:
            return True
        license_logging.error(f"license_delete error: {resp.status_code} - {resp.text}")
        return False
    except Exception as e:
        license_logging.error(f"license_delete exception: {e}")
        return False


@app.route('/api/licenses/create', methods=['POST'])
def create_license():
    """Create a new license key"""
    try:
        if not get_license_db():
            return jsonify({'success': False, 'error': 'Supabase baglantisi yok'})
        
        data = request.get_json() or {}
        email = data.get('email', '').strip()
        duration_days = int(data.get('duration_days', 30))
        note = data.get('note', '').strip()
        max_devices = int(data.get('max_devices', 2))
        telegram_membership = data.get('telegram_membership', False)
        telegram_username = data.get('telegram_username', '').strip() if data.get('telegram_username') else None
        
        if not email:
            return jsonify({'success': False, 'error': 'Email gerekli'})
        
        # Generate unique key
        for _ in range(10):
            key = generate_license_key()
            existing = license_select('licenses', 'key', {'key': key})
            if not existing:
                break
        else:
            return jsonify({'success': False, 'error': 'Key olusturulamadi'})
        
        # Calculate expiry
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        if duration_days == 0:
            expires_at = now + timedelta(days=36500)
        else:
            expires_at = now + timedelta(days=duration_days)
        
        # Insert license
        result = license_insert('licenses', {
            'key': key,
            'email': email,
            'duration_days': duration_days,
            'expires_at': expires_at.isoformat(),
            'status': 'active',
            'max_devices': max_devices,
            'note': note or None,
            'telegram_membership': telegram_membership,
            'telegram_username': telegram_username
        })
        
        if result:
            return jsonify({'success': True, 'key': key})
        else:
            return jsonify({'success': False, 'error': 'Veritabani hatasi'})
            
    except Exception as e:
        license_logging.error(f"Create license error: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/licenses/list')
def list_licenses():
    """List all licenses with device counts"""
    try:
        if not get_license_db():
            return jsonify({'success': False, 'error': 'Supabase baglantisi yok'})
        
        # Get all licenses
        licenses = license_select('licenses', '*', None, 'created_at', True) or []
        
        # Get device counts
        devices = license_select('license_devices', 'license_key') or []
        device_counts = {}
        for d in devices:
            key = d.get('license_key')
            device_counts[key] = device_counts.get(key, 0) + 1
        
        # Add device count to each license
        for lic in licenses:
            lic['device_count'] = device_counts.get(lic.get('key'), 0)
        
        return jsonify({'success': True, 'licenses': licenses})
        
    except Exception as e:
        license_logging.error(f"List licenses error: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/licenses/stats')
def license_stats():
    """Get license statistics"""
    try:
        if not get_license_db():
            return jsonify({'success': False, 'error': 'Supabase baglantisi yok'})
        
        from datetime import datetime
        now = datetime.utcnow()
        
        # Get all licenses
        licenses = license_select('licenses', 'status,expires_at') or []
        
        total = 0
        active = 0
        expired = 0
        
        for lic in licenses:
            total += 1
            status = lic.get('status', 'active')
            expires_at = lic.get('expires_at')
            
            if status == 'revoked':
                continue
            
            if expires_at:
                try:
                    exp_date = datetime.fromisoformat(expires_at.replace('Z', '+00:00').replace('+00:00', ''))
                    if exp_date < now:
                        expired += 1
                    else:
                        active += 1
                except:
                    active += 1
            else:
                active += 1
        
        # Get device count
        devices = license_select('license_devices', 'id') or []
        device_count = len(devices)
        
        return jsonify({
            'success': True,
            'total': total,
            'active': active,
            'expired': expired,
            'devices': device_count
        })
        
    except Exception as e:
        license_logging.error(f"License stats error: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/licenses/extend', methods=['POST'])
def extend_license():
    """Extend license expiry date"""
    try:
        if not get_license_db():
            return jsonify({'success': False, 'error': 'Supabase baglantisi yok'})
        
        data = request.get_json() or {}
        key = data.get('key', '').strip()
        days = int(data.get('days', 30))
        
        if not key:
            return jsonify({'success': False, 'error': 'Key gerekli'})
        
        # Get current license
        lic = license_select('licenses', 'expires_at', {'key': key})
        if not lic:
            return jsonify({'success': False, 'error': 'Lisans bulunamadi'})
        
        # Calculate new expiry
        from datetime import datetime, timedelta
        current_expires = lic[0].get('expires_at')
        
        try:
            exp_date = datetime.fromisoformat(current_expires.replace('Z', '+00:00').replace('+00:00', ''))
        except:
            exp_date = datetime.utcnow()
        
        # If already expired, extend from now
        now = datetime.utcnow()
        if exp_date < now:
            exp_date = now
        
        new_expires = exp_date + timedelta(days=days)
        
        # Update license
        result = license_update('licenses', {
            'expires_at': new_expires.isoformat(),
            'status': 'active'
        }, {'key': key})
        
        if result:
            return jsonify({'success': True, 'new_expires': new_expires.isoformat()})
        else:
            return jsonify({'success': False, 'error': 'Guncelleme basarisiz'})
            
    except Exception as e:
        license_logging.error(f"Extend license error: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/licenses/reset-devices', methods=['POST'])
def reset_license_devices():
    """Reset all devices for a license"""
    try:
        if not get_license_db():
            return jsonify({'success': False, 'error': 'Supabase baglantisi yok'})
        
        data = request.get_json() or {}
        key = data.get('key', '').strip()
        
        if not key:
            return jsonify({'success': False, 'error': 'Key gerekli'})
        
        # Delete all devices for this key
        license_delete('license_devices', {'license_key': key})
        
        return jsonify({'success': True})
        
    except Exception as e:
        license_logging.error(f"Reset devices error: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/licenses/delete', methods=['POST'])
def delete_license():
    """Delete a license"""
    try:
        if not get_license_db():
            return jsonify({'success': False, 'error': 'Supabase baglantisi yok'})
        
        data = request.get_json() or {}
        key = data.get('key', '').strip()
        
        if not key:
            return jsonify({'success': False, 'error': 'Key gerekli'})
        
        # Delete license (devices will be deleted via CASCADE)
        license_delete('licenses', {'key': key})
        
        return jsonify({'success': True})
        
    except Exception as e:
        license_logging.error(f"Delete license error: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/licenses/validate', methods=['POST'])
def validate_license():
    """Validate license for desktop app activation"""
    try:
        if not get_license_db():
            return jsonify({'valid': False, 'error': 'Supabase baglantisi yok'})
        
        data = request.get_json() or {}
        key = data.get('key', '').strip()
        device_id = data.get('device_id', '').strip()
        device_name = data.get('device_name', '')
        
        if not key or not device_id:
            return jsonify({'valid': False, 'error': 'Key ve device_id gerekli'})
        
        # Get license
        lic = license_select('licenses', '*', {'key': key})
        if not lic:
            return jsonify({'valid': False, 'error': 'Gecersiz lisans anahtari'})
        
        license_data = lic[0]
        
        # Check status
        if license_data.get('status') == 'revoked':
            return jsonify({'valid': False, 'error': 'Bu lisans iptal edilmis'})
        
        # Check expiry
        from datetime import datetime
        now = datetime.utcnow()
        expires_at = license_data.get('expires_at')
        
        if expires_at:
            try:
                exp_date = datetime.fromisoformat(expires_at.replace('Z', '+00:00').replace('+00:00', ''))
                if exp_date < now:
                    return jsonify({'valid': False, 'error': 'Lisans suresi dolmus', 'expired': True})
                days_left = (exp_date - now).days
            except:
                days_left = 0
        else:
            days_left = 9999
        
        # Check device
        devices = license_select('license_devices', 'device_id', {'license_key': key}) or []
        device_ids = [d.get('device_id') for d in devices]
        max_devices = license_data.get('max_devices', 2)
        
        if device_id in device_ids:
            # Device already registered - update last_seen
            license_update('license_devices', {
                'last_seen': datetime.utcnow().isoformat()
            }, {'license_key': key, 'device_id': device_id})
            
            return jsonify({
                'valid': True,
                'days_left': days_left,
                'expires_at': expires_at,
                'email': license_data.get('email')
            })
        
        # Check if max devices reached
        if len(device_ids) >= max_devices:
            return jsonify({
                'valid': False,
                'error': f'Bu lisans {max_devices} cihazda aktif, limit asildi',
                'device_limit': True
            })
        
        # Register new device
        license_insert('license_devices', {
            'license_key': key,
            'device_id': device_id,
            'device_name': device_name or None
        })
        
        return jsonify({
            'valid': True,
            'days_left': days_left,
            'expires_at': expires_at,
            'email': license_data.get('email'),
            'new_device': True
        })
        
    except Exception as e:
        license_logging.error(f"Validate license error: {e}")
        return jsonify({'valid': False, 'error': str(e)})


# ============================================
# ANALYTICS & HEARTBEAT SYSTEM
# ============================================

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    """Desktop app heartbeat - tracks online users"""
    try:
        if not get_license_db():
            return jsonify({'success': False, 'error': 'DB not available'})
        
        data = request.get_json() or {}
        license_key = data.get('license_key', '').strip()
        device_id = data.get('device_id', '').strip()
        
        if not license_key or not device_id:
            return jsonify({'success': False, 'error': 'Missing params'})
        
        lic = license_select('licenses', 'key', {'key': license_key})
        if not lic:
            return jsonify({'success': False, 'error': 'Invalid license'})
        
        device = license_select('license_devices', 'device_id', {'license_key': license_key, 'device_id': device_id})
        if not device:
            return jsonify({'success': False, 'error': 'Device not registered'})
        
        from datetime import datetime
        now = datetime.utcnow()
        
        cfg = get_license_db()
        url = f"{cfg['url']}/rest/v1/user_sessions?license_key=eq.{license_key}&device_id=eq.{device_id}"
        
        try:
            resp = httpx.get(url, headers=cfg['headers'], timeout=10)
            existing = resp.json() if resp.status_code == 200 else []
        except:
            existing = []
        
        session_data = {
            'license_key': license_key,
            'device_id': device_id,
            'last_seen': now.isoformat(),
            'ip_address': request.remote_addr or 'unknown'
        }
        
        if existing:
            license_update('user_sessions', {'last_seen': now.isoformat(), 'ip_address': request.remote_addr or 'unknown'}, 
                          {'license_key': license_key, 'device_id': device_id})
        else:
            license_insert('user_sessions', session_data)
        
        return jsonify({'success': True, 'server_time': now.isoformat()})
        
    except Exception as e:
        license_logging.error(f"Heartbeat error: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/analytics/dashboard')
def analytics_dashboard():
    """Admin dashboard analytics"""
    try:
        if not get_license_db():
            return jsonify({'success': False, 'error': 'DB not available'})
        
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        today = now.date()
        week_ago = now - timedelta(days=7)
        five_min_ago = now - timedelta(minutes=5)
        
        licenses = license_select('licenses', 'status,expires_at,duration_days,created_at') or []
        sessions = license_select('user_sessions', 'license_key,device_id,last_seen') or []
        devices = license_select('license_devices', 'license_key') or []
        
        total_licenses = len(licenses)
        active_licenses = 0
        expired_licenses = 0
        lifetime_count = 0
        one_day_count = 0
        three_day_count = 0
        monthly_count = 0
        new_today = 0
        new_this_week = 0
        expiring_soon = 0
        
        for lic in licenses:
            status = lic.get('status', 'active')
            expires_at = lic.get('expires_at')
            duration = lic.get('duration_days', 30)
            created_at = lic.get('created_at', '')
            
            if duration == 0:
                lifetime_count += 1
            elif duration == 1:
                one_day_count += 1
            elif duration == 3:
                three_day_count += 1
            else:
                monthly_count += 1
            
            if status == 'revoked':
                continue
            
            try:
                exp_date = datetime.fromisoformat(expires_at.replace('Z', '+00:00').replace('+00:00', ''))
                if exp_date < now:
                    expired_licenses += 1
                else:
                    active_licenses += 1
                    days_until_expire = (exp_date - now).days
                    if days_until_expire <= 3:
                        expiring_soon += 1
            except:
                active_licenses += 1
            
            try:
                created = datetime.fromisoformat(created_at.replace('Z', '+00:00').replace('+00:00', ''))
                if created.date() == today:
                    new_today += 1
                if created >= week_ago:
                    new_this_week += 1
            except:
                pass
        
        online_users = 0
        for sess in sessions:
            try:
                last_seen = datetime.fromisoformat(sess.get('last_seen', '').replace('Z', '+00:00').replace('+00:00', ''))
                if last_seen >= five_min_ago:
                    online_users += 1
            except:
                pass
        
        total_devices = len(devices)
        
        estimated_monthly_revenue = (one_day_count * 5) + (three_day_count * 10) + (monthly_count * 25) + (lifetime_count * 100)
        
        return jsonify({
            'success': True,
            'data': {
                'total_licenses': total_licenses,
                'active_licenses': active_licenses,
                'expired_licenses': expired_licenses,
                'online_users': online_users,
                'total_devices': total_devices,
                'subscription_types': {
                    'one_day': one_day_count,
                    'three_day': three_day_count,
                    'monthly': monthly_count,
                    'lifetime': lifetime_count
                },
                'new_today': new_today,
                'new_this_week': new_this_week,
                'expiring_soon': expiring_soon,
                'estimated_revenue': estimated_monthly_revenue,
                'server_time': now.isoformat()
            }
        })
        
    except Exception as e:
        license_logging.error(f"Analytics dashboard error: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/analytics/online-users')
def analytics_online_users():
    """Get online users list"""
    try:
        if not get_license_db():
            return jsonify({'success': False, 'error': 'DB not available'})
        
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        five_min_ago = now - timedelta(minutes=5)
        
        sessions = license_select('user_sessions', '*') or []
        licenses = license_select('licenses', 'key,email') or []
        
        email_map = {lic.get('key'): lic.get('email') for lic in licenses}
        
        online_users = []
        for sess in sessions:
            try:
                last_seen = datetime.fromisoformat(sess.get('last_seen', '').replace('Z', '+00:00').replace('+00:00', ''))
                if last_seen >= five_min_ago:
                    online_users.append({
                        'license_key': sess.get('license_key', '')[:8] + '...',
                        'email': email_map.get(sess.get('license_key'), 'N/A'),
                        'device_id': sess.get('device_id', '')[:8] + '...',
                        'ip_address': sess.get('ip_address', 'N/A'),
                        'last_seen': sess.get('last_seen')
                    })
            except:
                pass
        
        return jsonify({
            'success': True,
            'count': len(online_users),
            'users': online_users
        })
        
    except Exception as e:
        license_logging.error(f"Online users error: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/lisans')
def license_preview():
    """Preview activation screen for testing"""
    device_id = "test123abc456"
    return f'''<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <title>SmartXFlow Aktivasyon</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #080b10 0%, #0d1117 50%, #0b0f14 100%);
            color: #c9d1d9;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .container {{
            background: linear-gradient(180deg, #0f141a 0%, #0b0f14 100%);
            border: 1px solid rgba(255,255,255,0.04);
            border-radius: 20px;
            padding: 48px 40px;
            width: 440px;
            text-align: center;
            box-shadow: 
                0 0 0 1px rgba(255,255,255,0.04),
                0 20px 60px rgba(0,0,0,0.6),
                0 0 80px rgba(30,144,255,0.08);
        }}
        .logo {{
            width: 64px;
            height: auto;
            max-height: 64px;
            margin-bottom: 14px;
            object-fit: contain;
        }}
        .brand-badge {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: linear-gradient(135deg, rgba(30,144,255,0.18) 0%, rgba(30,144,255,0.06) 100%);
            border: 1px solid rgba(30,144,255,0.35);
            padding: 8px 16px;
            border-radius: 30px;
            margin-bottom: 16px;
            box-shadow: 0 0 20px rgba(30,144,255,0.12), 0 0 40px rgba(30,144,255,0.06);
        }}
        .brand-badge-icon {{
            width: 20px;
            height: 20px;
            background: linear-gradient(135deg, #1e90ff 0%, #00bfff 100%);
            border-radius: 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 10px;
            font-weight: 700;
            color: white;
        }}
        .brand-badge-text {{
            font-size: 11px;
            font-weight: 600;
            color: #1e90ff;
            letter-spacing: 1px;
            text-transform: uppercase;
        }}
        h1 {{ 
            color: #e6edf3; 
            font-size: 28px; 
            font-weight: 700;
            margin-bottom: 6px;
            letter-spacing: -0.5px;
        }}
        .subtitle {{ 
            font-size: 13px; 
            font-weight: 500;
            letter-spacing: 2px;
            text-transform: uppercase;
            margin-bottom: 32px;
        }}
        .subtitle .green {{ color: #22c55e; }}
        .subtitle .red {{ color: #ef4444; }}
        .subtitle .muted {{ color: #8b949e; }}
        .form-group {{ margin-bottom: 24px; text-align: left; }}
        label {{
            display: block; 
            color: #8b949e; 
            font-size: 11px;
            margin-bottom: 10px; 
            text-transform: uppercase; 
            letter-spacing: 1px;
            font-weight: 500;
        }}
        input {{
            width: 100%; 
            padding: 16px 18px; 
            background: #0d1117;
            border: 1px solid #21262d; 
            border-radius: 10px; 
            color: #e6edf3;
            font-size: 18px; 
            font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace; 
            letter-spacing: 2px;
            text-transform: uppercase;
            transition: all 0.2s ease;
            box-shadow: inset 0 0 0 1px rgba(255,255,255,0.04), 0 0 20px rgba(30,144,255,0.08);
        }}
        input:focus {{ 
            outline: none; 
            border-color: #1e90ff; 
            box-shadow: inset 0 0 0 1px rgba(255,255,255,0.04), 0 0 0 2px rgba(30,144,255,0.4), 0 0 20px rgba(30,144,255,0.25);
        }}
        input::placeholder {{ 
            color: #30363d; 
            text-transform: uppercase; 
            letter-spacing: 2px;
            font-size: 16px;
        }}
        .btn {{
            width: 100%; 
            padding: 16px;
            background: linear-gradient(135deg, #1db954 0%, #22c55e 100%);
            border: none; 
            border-radius: 10px; 
            color: white;
            font-size: 15px; 
            font-weight: 600; 
            cursor: pointer; 
            transition: all 0.25s ease;
            letter-spacing: 0.5px;
            position: relative;
            overflow: hidden;
        }}
        .btn:hover {{ 
            transform: translateY(-3px); 
            box-shadow: 0 12px 28px rgba(29, 185, 84, 0.45);
            background: linear-gradient(135deg, #22c55e 0%, #34d058 100%);
        }}
        .btn:active {{
            transform: translateY(0);
        }}
        .btn:disabled {{ 
            opacity: 0.6; 
            cursor: not-allowed; 
            transform: none;
            box-shadow: none;
        }}
        .btn-hint {{
            margin-top: 12px;
            font-size: 11px;
            color: #484f58;
            text-align: center;
        }}
        .btn-loading {{
            display: none;
            position: absolute;
            left: 50%;
            top: 50%;
            transform: translate(-50%, -50%);
        }}
        .btn-loading .spinner {{
            width: 20px;
            height: 20px;
            border: 2px solid rgba(255,255,255,0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }}
        @keyframes spin {{
            to {{ transform: rotate(360deg); }}
        }}
        .error {{
            background: rgba(248, 81, 73, 0.1); 
            border: 1px solid rgba(248, 81, 73, 0.3);
            color: #f85149; 
            padding: 14px 16px; 
            border-radius: 10px;
            margin-bottom: 20px; 
            font-size: 13px; 
            display: none;
            text-align: left;
        }}
        .success {{
            background: rgba(35, 134, 54, 0.15); 
            border: 1px solid rgba(35, 134, 54, 0.3);
            color: #3fb950; 
            padding: 14px 16px; 
            border-radius: 10px;
            margin-bottom: 20px; 
            font-size: 13px; 
            display: none;
            text-align: center;
        }}
        .success-icon {{
            font-size: 24px;
            margin-bottom: 8px;
            animation: successPop 0.4s ease;
        }}
        @keyframes successPop {{
            0% {{ transform: scale(0); opacity: 0; }}
            50% {{ transform: scale(1.2); }}
            100% {{ transform: scale(1); opacity: 1; }}
        }}
        .shopier-btn {{
            margin-top: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 10px;
            padding: 14px 24px;
            background: linear-gradient(135deg, #c45500 0%, #d4650a 100%);
            border: none;
            border-radius: 10px;
            color: white;
            font-size: 14px;
            font-weight: 600;
            text-decoration: none;
            cursor: pointer;
            transition: all 0.2s ease;
            box-shadow: 0 2px 8px rgba(196,85,0,0.2);
        }}
        .shopier-btn:hover {{
            transform: translateY(-2px);
            background: linear-gradient(135deg, #d4650a 0%, #e8750f 100%);
            box-shadow: 0 6px 20px rgba(196,85,0,0.4);
        }}
        .shopier-hint {{
            margin-top: 8px;
            font-size: 10px;
            color: #6e7681;
            text-align: center;
        }}
        .shopier-icon {{
            font-size: 18px;
        }}
        .social-section {{
            margin-top: 20px;
            padding: 16px;
            background: rgba(13,17,23,0.5);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 10px;
            text-align: center;
        }}
        .social-title {{
            color: #8b949e;
            font-size: 12px;
            font-weight: 500;
            margin-bottom: 12px;
        }}
        .social-icons {{
            display: flex;
            justify-content: center;
            gap: 16px;
        }}
        .social-icon {{
            width: 40px;
            height: 40px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s ease;
            cursor: pointer;
        }}
        .social-icon svg {{
            width: 20px;
            height: 20px;
        }}
        .social-icon.instagram {{
            background: rgba(225,48,108,0.15);
            border: 1px solid rgba(225,48,108,0.3);
        }}
        .social-icon.instagram svg {{
            fill: #E1306C;
        }}
        .social-icon.telegram {{
            background: rgba(0,136,204,0.15);
            border: 1px solid rgba(0,136,204,0.3);
        }}
        .social-icon.telegram svg {{
            fill: #0088cc;
        }}
        .social-icon-email {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 14px;
            background: rgba(234,67,53,0.15);
            border: 1px solid rgba(234,67,53,0.3);
            border-radius: 10px;
            text-decoration: none;
            color: #ea4335;
            font-size: 11px;
            transition: all 0.2s ease;
            cursor: pointer;
        }}
        .social-icon-email svg {{
            width: 18px;
            height: 18px;
            flex-shrink: 0;
            fill: #ea4335;
        }}
        .social-icon-email:hover {{
            transform: scale(1.05);
            background: rgba(234,67,53,0.25);
        }}
        .social-icon:hover {{
            transform: scale(1.1);
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        }}
        .device-info {{ 
            margin-top: 20px; 
            padding: 12px 16px; 
            background: rgba(13,17,23,0.6); 
            border: 1px solid #21262d;
            border-radius: 8px; 
            font-size: 11px; 
            color: #484f58;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
        }}
        .device-info-icon {{
            opacity: 0.6;
        }}
        .progress-bar {{
            display: none;
            height: 3px;
            background: #21262d;
            border-radius: 2px;
            margin-bottom: 20px;
            overflow: hidden;
        }}
        .progress-bar-fill {{
            height: 100%;
            background: linear-gradient(90deg, #1e90ff, #00bfff);
            width: 0%;
            transition: width 0.3s ease;
            animation: progressPulse 1.5s ease infinite;
        }}
        @keyframes progressPulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.7; }}
        }}
        .fade-out {{
            animation: fadeOut 0.5s ease forwards;
        }}
        @keyframes fadeOut {{
            to {{ opacity: 0; transform: scale(0.98); }}
        }}
    </style>
</head>
<body>
    <div class="container" id="mainContainer">
        <img src="/static/images/smartxflow_logo.png" alt="SmartXFlow" class="logo">
        <h1>SmartXFlow Monitor</h1>
        <p class="subtitle"><span class="green">Akıllı Para</span> <span class="muted">&</span> <span class="red">Oran Takibi</span></p>
        
        <div id="progressBar" class="progress-bar">
            <div class="progress-bar-fill" id="progressFill"></div>
        </div>
        
        <div id="errorMsg" class="error"></div>
        <div id="successMsg" class="success"></div>
        
        <div class="form-group">
            <label>Lisans Anahtari</label>
            <input type="text" id="licenseKey" placeholder="SXF-XXXX-XXXX-XXXX" maxlength="18" autocomplete="off" spellcheck="false">
        </div>
        
        <button class="btn" id="activateBtn" onclick="activate()">
            <span class="btn-text">Lisansi Aktif Et</span>
            <div class="btn-loading"><div class="spinner"></div></div>
        </button>
        <div class="btn-hint">Lisans dogrulamasi birkac saniye surebilir</div>
        
        <a href="https://shopier.com" target="_blank" class="shopier-btn">
            <span class="shopier-icon">🛒</span>
            <span>Lisans Satin Al</span>
        </a>
        <div class="shopier-hint">Guvenli odeme • Aninda lisans teslimi</div>
        
        <div class="social-section">
            <div class="social-title">Bize Ulasin</div>
            <div class="social-icons">
                <a href="https://www.instagram.com/smartxflow/" target="_blank" class="social-icon instagram" title="Instagram">
                    <svg viewBox="0 0 24 24" fill="white"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z"/></svg>
                </a>
                <a href="https://t.me/smartxflow" target="_blank" class="social-icon telegram" title="Telegram">
                    <svg viewBox="0 0 24 24" fill="white"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>
                </a>
                <a href="#" onclick="copyEmail()" class="social-icon-email" title="Kopyalamak icin tikla">
                    <svg viewBox="0 0 24 24" fill="white"><path d="M20 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 4l-8 5-8-5V6l8 5 8-5v2z"/></svg>
                    <span id="emailText">smartxflow29@gmail.com</span>
                </a>
            </div>
        </div>
        
        <div class="device-info">
            <span class="device-info-icon">🔒</span>
            <span>Cihaz otomatik tanimlandi</span>
        </div>
    </div>
    <script>
        const keyInput = document.getElementById('licenseKey');
        const btn = document.getElementById('activateBtn');
        const btnText = btn.querySelector('.btn-text');
        const btnLoading = btn.querySelector('.btn-loading');
        const progressBar = document.getElementById('progressBar');
        const progressFill = document.getElementById('progressFill');
        
        keyInput.addEventListener('input', function(e) {{
            let value = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '');
            if (value.length > 3 && !value.startsWith('SXF')) value = 'SXF' + value.substring(0, 12);
            let formatted = '';
            if (value.length > 0) {{
                formatted = value.substring(0, 3);
                if (value.length > 3) formatted += '-' + value.substring(3, 7);
                if (value.length > 7) formatted += '-' + value.substring(7, 11);
                if (value.length > 11) formatted += '-' + value.substring(11, 15);
            }}
            e.target.value = formatted;
        }});
        
        function showLoading() {{
            btn.disabled = true;
            btnText.style.opacity = '0';
            btnLoading.style.display = 'block';
            progressBar.style.display = 'block';
            let progress = 0;
            const interval = setInterval(() => {{
                progress += Math.random() * 15;
                if (progress > 90) progress = 90;
                progressFill.style.width = progress + '%';
            }}, 200);
            return interval;
        }}
        
        function hideLoading(interval) {{
            clearInterval(interval);
            progressFill.style.width = '100%';
            setTimeout(() => {{
                btn.disabled = false;
                btnText.style.opacity = '1';
                btnLoading.style.display = 'none';
                progressBar.style.display = 'none';
                progressFill.style.width = '0%';
            }}, 300);
        }}
        
        function copyEmail() {{
            const email = 'smartxflow29@gmail.com';
            const emailSpan = document.getElementById('emailText');
            navigator.clipboard.writeText(email).then(() => {{
                emailSpan.textContent = 'Kopyalandi!';
                setTimeout(() => {{ emailSpan.textContent = email; }}, 1500);
            }});
        }}
        
        async function activate() {{
            const key = keyInput.value.trim();
            const errorEl = document.getElementById('errorMsg');
            const successEl = document.getElementById('successMsg');
            
            errorEl.style.display = 'none';
            successEl.style.display = 'none';
            
            if (!key || key.length < 18) {{
                errorEl.textContent = 'Lutfen gecerli bir lisans anahtari girin.';
                errorEl.style.display = 'block';
                keyInput.focus();
                return;
            }}
            
            const loadingInterval = showLoading();
            
            try {{
                const response = await fetch('/api/licenses/validate', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{key: key, device_id: '{device_id}', device_name: 'Web Test'}})
                }});
                const result = await response.json();
                
                hideLoading(loadingInterval);
                
                if (result.valid) {{
                    successEl.innerHTML = '<div class="success-icon">✓</div>Lisans aktif! Kalan gun: ' + result.days_left;
                    successEl.style.display = 'block';
                    
                    setTimeout(() => {{
                        document.getElementById('mainContainer').classList.add('fade-out');
                    }}, 2000);
                }} else {{
                    errorEl.textContent = result.error || 'Lisans dogrulanamadi.';
                    errorEl.style.display = 'block';
                }}
            }} catch (e) {{
                hideLoading(loadingInterval);
                errorEl.textContent = 'Baglanti hatasi. Lutfen tekrar deneyin.';
                errorEl.style.display = 'block';
            }}
        }}
        
        keyInput.addEventListener('keypress', function(e) {{ if (e.key === 'Enter') activate(); }});
        
        keyInput.focus();
    </script>
</body>
</html>'''


def main():
    """Main entry point with error handling for EXE"""
    try:
        mode_name = "CLIENT" if is_client_mode() else "SERVER"
        
        print("=" * 50)
        print("SmartXFlow Monitor")
        print("=" * 50)
        print(f"Mode: {mode_name}")
        print(f"Supabase: {'Connected' if db.is_supabase_available else 'Not Connected'}")
        print(f"Templates path: {template_dir}")
        print(f"Static path: {static_dir}")
        print(f"Templates exist: {os.path.exists(template_dir)}")
        print(f"Static exist: {os.path.exists(static_dir)}")
        print("=" * 50)
        
        if not db.is_supabase_available:
            print("WARNING: Supabase not configured!")
            print("Please set SUPABASE_URL and SUPABASE_KEY")
        
        if is_server_mode():
            start_server_scheduler()
            start_cleanup_scheduler()
            start_alarm_scheduler()
            host = '0.0.0.0'
        else:
            host = '127.0.0.1'
        
        port = 5000
        is_desktop = os.environ.get('SMARTX_DESKTOP') == '1'
        try:
            print(f"Starting Flask on http://{host}:{port}...")
            if is_client_mode() and not is_desktop:
                import webbrowser
                webbrowser.open(f'http://127.0.0.1:{port}')
            app.run(host=host, port=port, debug=False)
        except OSError as e:
            if "10048" in str(e) or "Address already in use" in str(e):
                port = 5050
                print(f"Port 5000 in use, trying http://{host}:{port}...")
                if is_client_mode() and not is_desktop:
                    import webbrowser
                    webbrowser.open(f'http://127.0.0.1:{port}')
                app.run(host=host, port=port, debug=False)
            else:
                raise
    except Exception as e:
        import traceback
        print("=" * 50)
        print("FATAL ERROR during startup:")
        print(str(e))
        print("=" * 50)
        traceback.print_exc()
        print("=" * 50)
        input("Press ENTER to close...")
        sys.exit(1)


if __name__ == '__main__':
    main()
