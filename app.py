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
from functools import wraps
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, jsonify, request, Response, send_from_directory, session, redirect, make_response

# Conditional import for compression (not needed in desktop mode)
if os.environ.get('SMARTX_DESKTOP') != '1':
    try:
        from flask_compress import Compress
    except ImportError:
        Compress = None
else:
    Compress = None

# ============================================
# LAZY WARMUP - Each section loads on first visit
# ============================================
_app_warmup_done = threading.Event()
_app_warmup_started = False
_app_warmup_lock = threading.Lock()
_admin_warmup_done = threading.Event()
_admin_warmup_started = False
_admin_warmup_lock = threading.Lock()

# ============================================
# SERVER-SIDE CACHE LOCK (thread safety)
# ============================================
_cache_lock = threading.Lock()

# ============================================
# SERVER-SIDE ALARM CACHE
# Reduces Supabase calls from ~2s to <50ms
# ============================================
_server_alarm_cache = None
_server_alarm_cache_time = 0
SERVER_ALARM_CACHE_TTL = 120

_cm_signals_cache = None
_cm_signals_cache_time = 0
CM_SIGNALS_CACHE_TTL = 60
CM_ODDS_DROP_PCT = 0.04  # %4 düşüş eşiği — sinyal_engine.py ile aynı

_cm_v2_signals_cache = None
_cm_v2_signals_cache_time = 0
CM_V2_SIGNALS_CACHE_TTL = 60
_cm_v2_admin_signals_cache = None
_cm_v2_admin_signals_cache_time = 0

_fs_signals_cache = None
_fs_signals_cache_time = 0
FS_SIGNALS_CACHE_TTL = 60

_eml_signals_cache = None
_eml_signals_cache_time = 0
EML_SIGNALS_CACHE_TTL = 60

_APPROVED_SIGNALS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'approved_signals.json')
_approved_signals_lock = threading.Lock()

def _load_approved_signals():
    try:
        if os.path.exists(_APPROVED_SIGNALS_PATH):
            with open(_APPROVED_SIGNALS_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"[ApprovedSignals] Load error: {e}")
    return {}

def _save_approved_signals(data):
    try:
        os.makedirs(os.path.dirname(_APPROVED_SIGNALS_PATH), exist_ok=True)
        with open(_APPROVED_SIGNALS_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[ApprovedSignals] Save error: {e}")
        return False

def get_cached_alarms(force_refresh=False):
    """Get alarms from server-side cache or refresh from Supabase. Waits for app warmup if in progress."""
    global _server_alarm_cache, _server_alarm_cache_time
    
    if _app_warmup_started and not _app_warmup_done.is_set():
        _app_warmup_done.wait(timeout=5)
    
    now = time.time()
    
    with _cache_lock:
        if not force_refresh and _server_alarm_cache and (now - _server_alarm_cache_time) < SERVER_ALARM_CACHE_TTL:
            return _server_alarm_cache, True
    
    return None, False

def set_alarm_cache(data):
    """Update server-side alarm cache"""
    global _server_alarm_cache, _server_alarm_cache_time
    with _cache_lock:
        _server_alarm_cache = data
        _server_alarm_cache_time = time.time()
# ============================================

# ============================================
# SERVER-SIDE MATCHES CACHE
# Loads all matches instantly on cache hit
# ============================================
_server_matches_cache = {}
_server_matches_cache_time = {}
SERVER_MATCHES_CACHE_TTL = 120
MAX_MATCHES_CACHE_SIZE = 20

def get_cached_matches(market, force_refresh=False):
    """Get matches from server-side cache. Waits for app warmup if in progress."""
    if _app_warmup_started and not _app_warmup_done.is_set():
        _app_warmup_done.wait(timeout=5)
    
    now = time.time()
    
    with _cache_lock:
        cache_time = _server_matches_cache_time.get(market, 0)
        if not force_refresh and market in _server_matches_cache and (now - cache_time) < SERVER_MATCHES_CACHE_TTL:
            return _server_matches_cache[market], True
    
    return None, False

def set_matches_cache(market, data):
    """Update server-side matches cache"""
    with _cache_lock:
        if len(_server_matches_cache) >= MAX_MATCHES_CACHE_SIZE and market not in _server_matches_cache:
            oldest_key = min(_server_matches_cache_time, key=_server_matches_cache_time.get)
            _server_matches_cache.pop(oldest_key, None)
            _server_matches_cache_time.pop(oldest_key, None)
        _server_matches_cache[market] = data
        _server_matches_cache_time[market] = time.time()
# ============================================

# ============================================
# SERVER-SIDE MATCH HISTORY CACHE
# Modal 2. acilista anlik yukleme icin
# ============================================
_server_history_cache = {}
_server_history_cache_time = {}
SERVER_HISTORY_CACHE_TTL = 60
MAX_HISTORY_CACHE_SIZE = 500

def get_cached_history(match_key, force_refresh=False):
    """Get match history from server-side cache"""
    now = time.time()
    
    with _cache_lock:
        cache_time = _server_history_cache_time.get(match_key, 0)
        if not force_refresh and match_key in _server_history_cache and (now - cache_time) < SERVER_HISTORY_CACHE_TTL:
            return _server_history_cache[match_key], True
    
    return None, False

def set_history_cache(match_key, data):
    """Update server-side match history cache"""
    with _cache_lock:
        if len(_server_history_cache) >= MAX_HISTORY_CACHE_SIZE:
            oldest_key = min(_server_history_cache_time, key=_server_history_cache_time.get)
            _server_history_cache.pop(oldest_key, None)
            _server_history_cache_time.pop(oldest_key, None)
        _server_history_cache[match_key] = data
        _server_history_cache_time[match_key] = time.time()

def _purge_expired_caches():
    """Remove expired entries from all server-side caches to prevent memory leaks"""
    import gc as _gc
    now = time.time()
    purged = 0
    with _cache_lock:
        expired_history = [k for k, t in list(_server_history_cache_time.items()) if (now - t) > SERVER_HISTORY_CACHE_TTL * 2]
        for k in expired_history:
            _server_history_cache.pop(k, None)
            _server_history_cache_time.pop(k, None)
            purged += 1
        expired_matches = [k for k, t in list(_server_matches_cache_time.items()) if (now - t) > SERVER_MATCHES_CACHE_TTL * 2]
        for k in expired_matches:
            _server_matches_cache.pop(k, None)
            _server_matches_cache_time.pop(k, None)
            purged += 1
    _purge_license_cache()
    _gc.collect()
    if purged > 0:
        print(f"[Cache] Purged {purged} expired entries (history={len(_server_history_cache)}, matches={len(_server_matches_cache)})")
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

from core.settings import init_mode, is_server_mode, is_client_mode
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
    write_bigmoney_alarms_to_supabase,
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
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

# Gzip/Brotli compression - only for web mode (not desktop)
if Compress is not None:
    app.config['COMPRESS_MIMETYPES'] = ['text/html', 'text/css', 'text/javascript', 'application/json', 'application/javascript']
    app.config['COMPRESS_LEVEL'] = 6  # Compression level (1-9, 6 is balanced)
    app.config['COMPRESS_MIN_SIZE'] = 500  # Only compress responses > 500 bytes
    Compress(app)

current_mode = init_mode()
db = get_database()
db.ensure_analyses_table()

_validated_licenses = {}
_LICENSE_CACHE_TTL = 300
_LICENSE_MAX_ENTRIES = 100

def _purge_license_cache():
    """Remove expired or stale entries from license cache"""
    now = time.time()
    expired = [k for k, v in list(_validated_licenses.items()) if (now - v.get('cached_at', 0)) > _LICENSE_CACHE_TTL * 3]
    for k in expired:
        _validated_licenses.pop(k, None)
    if len(_validated_licenses) > _LICENSE_MAX_ENTRIES:
        sorted_keys = sorted(_validated_licenses.keys(), key=lambda k: _validated_licenses[k].get('cached_at', 0))
        for k in sorted_keys[:len(_validated_licenses) - _LICENSE_MAX_ENTRIES]:
            _validated_licenses.pop(k, None)
    if expired:
        print(f"[License Cache] Purged {len(expired)} expired licenses, {len(_validated_licenses)} remaining")

def _parse_expires_naive(expires_at_str):
    if not expires_at_str:
        return None
    import re
    cleaned = re.sub(r'[+-]\d{2}(:\d{2})?$', '', expires_at_str.replace('Z', ''))
    return datetime.fromisoformat(cleaned)

def _refresh_license_from_supabase(key):
    try:
        lic_data = license_select('licenses', 'expires_at,status', {'key': key})
        print(f"[LicenseRefresh] key={key[:8]}..., response={lic_data}")
        if lic_data and len(lic_data) > 0:
            lic = lic_data[0] if isinstance(lic_data, list) else lic_data
            status = lic.get('status', '')
            if status == 'revoked':
                print(f"[LicenseRefresh] REVOKED: {key[:8]}...")
                _validated_licenses.pop(key, None)
                return 'LICENSE_REVOKED'
            expires_at = lic.get('expires_at')
            if expires_at:
                exp_dt = _parse_expires_naive(expires_at)
                now = datetime.utcnow()
                print(f"[LicenseRefresh] key={key[:8]}... expires={exp_dt} now={now} expired={exp_dt < now if exp_dt else 'parse_fail'}")
                if exp_dt and exp_dt < now:
                    _validated_licenses.pop(key, None)
                    return 'LICENSE_EXPIRED'
                if exp_dt:
                    _validated_licenses[key] = {
                        'expires': exp_dt,
                        'plan': _validated_licenses.get(key, {}).get('plan', 'core'),
                        'cached_at': time.time()
                    }
                    return None
        return 'LICENSE_REQUIRED'
    except Exception as e:
        print(f"[LicenseRefresh] Error for {key[:8]}...: {e}")
        _validated_licenses.pop(key, None)
        return 'LICENSE_EXPIRED'

def _license_block(error, message, status=403):
    if not request.path.startswith('/api/') and 'text/html' in request.headers.get('Accept', ''):
        return redirect(f'/app?next={request.path}')
    return jsonify({'error': error, 'message': message}), status

def license_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if os.environ.get('SMARTX_DESKTOP') == '1':
            return f(*args, **kwargs)
        
        header_key = request.headers.get('X-License-Key', '').strip()
        
        if session.get('license_plan') == 'test':
            return f(*args, **kwargs)
        
        lic_valid = session.get('license_valid')
        if lic_valid:
            session_key = session.get('license_key', '') or header_key
            print(f"[LicenseCheck] SESSION path: key={session_key[:8] if session_key else 'NONE'}... last_check={session.get('license_last_check', 0)}")
            if not session_key:
                print(f"[LicenseCheck] SESSION: no key found, clearing session")
                session.pop('license_valid', None)
                session.pop('license_expires', None)
                return _license_block('LICENSE_REQUIRED', 'Gecerli lisans gerekli')
            last_check = session.get('license_last_check', 0)
            age = time.time() - last_check
            if age > _LICENSE_CACHE_TTL:
                print(f"[LicenseCheck] SESSION: TTL expired (age={age:.0f}s), refreshing from Supabase...")
                err = _refresh_license_from_supabase(session_key)
                if err:
                    print(f"[LicenseCheck] SESSION: refresh returned {err}, blocking user")
                    session.pop('license_valid', None)
                    session.pop('license_expires', None)
                    session.pop('license_key', None)
                    session.pop('license_last_check', None)
                    return _license_block(err, 'Lisans suresi dolmus' if err == 'LICENSE_EXPIRED' else 'Lisans iptal edilmis' if err == 'LICENSE_REVOKED' else 'Gecerli lisans gerekli')
                print(f"[LicenseCheck] SESSION: refresh OK, license still valid")
                session['license_last_check'] = time.time()
                session['license_key'] = session_key
            return f(*args, **kwargs)
        
        if header_key:
            cached = _validated_licenses.get(header_key)
            print(f"[LicenseCheck] HEADER path: key={header_key[:8]}... cached={'YES' if cached else 'NO'}")
            if not cached:
                print(f"[LicenseCheck] HEADER: not cached, validating from Supabase...")
                err = _refresh_license_from_supabase(header_key)
                if err:
                    print(f"[LicenseCheck] HEADER: validation returned {err}, blocking")
                    return jsonify({'error': err, 'message': 'Lisans suresi dolmus' if err == 'LICENSE_EXPIRED' else 'Lisans iptal edilmis' if err == 'LICENSE_REVOKED' else 'Gecerli lisans gerekli'}), 403
                cached = _validated_licenses.get(header_key)
            else:
                cached_at = cached.get('cached_at', 0)
                age = time.time() - cached_at
                if age > _LICENSE_CACHE_TTL:
                    print(f"[LicenseCheck] HEADER: TTL expired (age={age:.0f}s), refreshing...")
                    err = _refresh_license_from_supabase(header_key)
                    if err:
                        print(f"[LicenseCheck] HEADER: refresh returned {err}, blocking")
                        return jsonify({'error': err, 'message': 'Lisans suresi dolmus' if err == 'LICENSE_EXPIRED' else 'Lisans iptal edilmis' if err == 'LICENSE_REVOKED' else 'Gecerli lisans gerekli'}), 403
                    cached = _validated_licenses.get(header_key)
            if cached:
                exp_time = cached.get('expires')
                if exp_time and exp_time < datetime.utcnow():
                    _validated_licenses.pop(header_key, None)
                    return jsonify({'error': 'LICENSE_EXPIRED', 'message': 'Lisans suresi dolmus'}), 403
                return f(*args, **kwargs)
        
        print(f"[LicenseCheck] NO valid session, NO cached header key -> LICENSE_REQUIRED")
        return _license_block('LICENSE_REQUIRED', 'Gecerli lisans gerekli')
    return decorated

@app.after_request
def add_header(response):
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=86400'
        response.headers.pop('Pragma', None)
        response.headers.pop('Expires', None)
    else:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['Surrogate-Control'] = 'no-store'
    response.headers['Vary'] = 'Accept-Encoding'
    if request.path.startswith('/static/') and request.path.endswith(('.js', '.css')):
        import gzip as _gzip
        import io as _io
        accept_enc = request.headers.get('Accept-Encoding', '')
        already_encoded = response.headers.get('Content-Encoding')
        if 'gzip' in accept_enc and response.status_code == 200 and not already_encoded:
            try:
                if response.direct_passthrough:
                    response.direct_passthrough = False
                raw = response.get_data()
                if len(raw) > 500:
                    buf = _io.BytesIO()
                    with _gzip.GzipFile(fileobj=buf, mode='wb', compresslevel=6) as gz:
                        gz.write(raw)
                    compressed = buf.getvalue()
                    response.set_data(compressed)
                    response.headers['Content-Encoding'] = 'gzip'
                    response.headers['Content-Length'] = len(compressed)
                    response.headers.pop('ETag', None)
                    response.headers.pop('Last-Modified', None)
            except Exception:
                pass
    return response

cleanup_thread = None
alarm_scheduler_thread = None
last_cleanup_date = None
last_alarm_calc_time = None

def cleanup_old_matches():
    """
    D-2+ maçları Supabase'den siler.
    Runs once per day on server startup or scheduler.
    """
    global last_cleanup_date
    
    today = now_turkey().date()
    if last_cleanup_date == today:
        return
    
    last_cleanup_date = today
    
    # D-8 = 8 günden eski veriler silinir (7 günlük geçmiş tutulur)
    cutoff = today - timedelta(days=8)
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


_cleanup_started_pids = set()

def start_cleanup_scheduler():
    """Start daily cleanup scheduler for old matches - runs at 05:00 Turkey time"""
    global cleanup_thread
    
    pid = os.getpid()
    if pid in _cleanup_started_pids:
        print(f"[Cleanup Scheduler] Already running in PID {pid}, skipping", flush=True)
        return
    _cleanup_started_pids.add(pid)
    print(f"[Cleanup Scheduler] Starting in PID {pid}", flush=True)
    
    def cleanup_loop():
        while True:
            try:
                cleanup_old_matches()
                
                CACHE_PURGE_INTERVAL = 300
                now = now_turkey()
                target_5am = now.replace(hour=5, minute=0, second=0, microsecond=0)
                if now.hour >= 5:
                    target_5am = target_5am + timedelta(days=1)
                
                print(f"[Cleanup Scheduler] Next cleanup at 05:00 Turkey time, waiting {(target_5am - now).total_seconds()/3600:.1f} hours")
                
                while now_turkey() < target_5am:
                    time.sleep(CACHE_PURGE_INTERVAL)
                    try:
                        _purge_expired_caches()
                    except Exception as e:
                        print(f"[Cache] Purge error: {e}")
                
                cleanup_old_matches()
            except Exception as e:
                import traceback
                print(f"[Cleanup Scheduler] CRITICAL ERROR (restarting loop): {e}")
                traceback.print_exc()
                time.sleep(60)
    
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
    """Legacy stub - scraping handled by Scraper Engine workflow"""
    print("[Server Mode] Scraper Engine workflow handles data collection")
    print("[Server Mode] Web app runs as UI-only")


@app.route('/robots.txt')
def robots_txt():
    content = """User-agent: *
Allow: /
Allow: /nedir
Allow: /pricing
Allow: /analysis
Allow: /rehber
Allow: /rehber/oran-analizi
Allow: /rehber/para-hareketi
Allow: /rehber/canli-oran-takibi
Disallow: /app
Disallow: /api/
Disallow: /admin
Disallow: /scraper/
Disallow: /alarm-engine/
Disallow: /lisans
Disallow: /status

Sitemap: https://www.smartxflow.com/sitemap.xml
"""
    return app.response_class(content, mimetype='text/plain')

@app.route('/sitemap.xml')
def sitemap_xml():
    from datetime import datetime
    now = datetime.utcnow().strftime('%Y-%m-%d')
    pages = [
        {'loc': '/', 'changefreq': 'weekly', 'priority': '1.0'},
        {'loc': '/nedir', 'changefreq': 'monthly', 'priority': '0.8'},
        {'loc': '/pricing', 'changefreq': 'weekly', 'priority': '0.9'},
        {'loc': '/analysis', 'changefreq': 'daily', 'priority': '0.7'},
        {'loc': '/rehber', 'changefreq': 'monthly', 'priority': '0.8'},
        {'loc': '/rehber/oran-analizi', 'changefreq': 'monthly', 'priority': '0.7'},
        {'loc': '/rehber/para-hareketi', 'changefreq': 'monthly', 'priority': '0.7'},
        {'loc': '/rehber/canli-oran-takibi', 'changefreq': 'monthly', 'priority': '0.7'},
    ]
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for p in pages:
        xml += '  <url>\n'
        xml += f'    <loc>https://www.smartxflow.com{p["loc"]}</loc>\n'
        xml += f'    <lastmod>{now}</lastmod>\n'
        xml += f'    <changefreq>{p["changefreq"]}</changefreq>\n'
        xml += f'    <priority>{p["priority"]}</priority>\n'
        xml += '  </url>\n'
    xml += '</urlset>'
    return app.response_class(xml, mimetype='application/xml')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico', mimetype='image/x-icon')

@app.route('/')
def landing_page():
    """Landing page - SmartXFlow tanıtımı"""
    response = make_response(render_template('landing.html'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/rehber')
def rehber_page():
    """Rehber hub page"""
    return render_template('rehber.html')

@app.route('/rehber/oran-analizi')
def rehber_oran_analizi():
    return render_template('rehber_oran_analizi.html')

@app.route('/rehber/para-hareketi')
def rehber_para_hareketi():
    return render_template('rehber_para_hareketi.html')

@app.route('/rehber/canli-oran-takibi')
def rehber_canli_oran_takibi():
    return render_template('rehber_canli_oran_takibi.html')

@app.route('/oran-analizi')
@app.route('/oran-degisimi')
def redirect_oran_analizi():
    return redirect('/rehber/oran-analizi', code=301)

@app.route('/oran-ve-para-nasil-okunur')
def redirect_para_hareketi():
    return redirect('/rehber/para-hareketi', code=301)

@app.route('/canli-oran-takibi')
@app.route('/orani-dusen-maclar')
def redirect_canli_oran():
    return redirect('/rehber/canli-oran-takibi', code=301)

@app.route('/nedir')
def nedir_page():
    """Nedir page - SmartXFlow nedir"""
    return render_template('nedir.html')

@app.route('/pricing')
def pricing_page():
    """Pricing page - Paket ve fiyatlar"""
    return render_template('pricing.html')

@app.route('/analysis')
def analysis_page():
    """Analysis page - Analiz paylaşımları"""
    plan = session.get('license_plan', 'core')
    return render_template('analysis.html', pro_required=(plan not in ('pro', 'premium') or plan == 'test'))

@app.route('/terms')
def terms_page():
    content = """
    <p>SmartXFlow platformunu kullanan tüm kullanıcılar aşağıdaki şartları kabul etmiş sayılır.</p>
    <p>SmartXFlow, piyasa verilerini analiz eden ve kullanıcıya veri odaklı sinyaller sunan bir analiz platformudur. Platformda sunulan veriler, analizler ve içerikler yatırım veya bahis tavsiyesi niteliği taşımaz.</p>
    <p>Kullanıcılar:</p>
    <ul>
        <li>Platformu yasal amaçlarla kullanmayı</li>
        <li>Hesap bilgilerini korumayı</li>
        <li>Platform verilerini izinsiz kopyalamamayı kabul eder</li>
    </ul>
    <p>SmartXFlow, hizmette yapılacak güncellemeler, değişiklikler ve teknik kesintiler nedeniyle oluşabilecek durumlardan sorumlu tutulamaz.</p>
    """
    return render_template('legal.html', title='Kullanım Şartları', content=content)

@app.route('/privacy')
def privacy_page():
    content = """
    <p>SmartXFlow kullanıcı gizliliğine önem verir.</p>
    <p>Platform aşağıdaki verileri toplayabilir:</p>
    <ul>
        <li>E-posta adresi</li>
        <li>Lisans anahtarı</li>
        <li>Kullanım istatistikleri</li>
    </ul>
    <p>Bu veriler yalnızca:</p>
    <ul>
        <li>Hesap doğrulama</li>
        <li>Lisans kontrolü</li>
        <li>Sistem güvenliği</li>
        <li>Hizmet geliştirme</li>
    </ul>
    <p>amaçlarıyla kullanılır ve üçüncü kişilerle paylaşılmaz.</p>
    """
    return render_template('legal.html', title='Gizlilik Politikası', content=content)

@app.route('/cookies')
def cookies_page():
    content = """
    <p>SmartXFlow, kullanıcı deneyimini iyileştirmek ve sistem performansını analiz etmek amacıyla çerezler kullanabilir.</p>
    <p>Çerezler:</p>
    <ul>
        <li>Oturum yönetimi</li>
        <li>Güvenlik</li>
        <li>Analitik ölçüm</li>
    </ul>
    <p>amaçlarıyla kullanılmaktadır. Kullanıcılar tarayıcı ayarlarından çerezleri devre dışı bırakabilir.</p>
    """
    resp = make_response(render_template('legal.html', title='Çerez Politikası', content=content))
    resp.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return resp

@app.route('/disclaimer')
def disclaimer_page():
    content = """
    <p>SmartXFlow, piyasa verilerini analiz eden bir veri platformudur. Platformda yer alan analizler, sinyaller ve içerikler yatırım veya bahis tavsiyesi niteliği taşımaz.</p>
    <p>Kullanıcılar platform verilerini kendi sorumlulukları dahilinde değerlendirir. SmartXFlow, kullanıcıların aldığı finansal veya piyasa kararlarından sorumlu değildir.</p>
    """
    return render_template('legal.html', title='Sorumluluk Reddi', content=content)

@app.route('/status')
def status_page():
    """Status page - Scraper durumu"""
    return render_template('status.html')

@app.route('/api/scraper-status')
def api_scraper_status():
    """Scraper durumu - son 24 saatteki sinyaller ve heartbeat"""
    import requests as req
    result = {"signals": [], "heartbeat": None, "active_match_count": 0}
    try:
        if not db.is_supabase_available:
            return jsonify(result)

        supa = db.supabase
        headers = {
            "apikey": supa.key,
            "Authorization": f"Bearer {supa.key}"
        }

        cutoff = (datetime.utcnow() - timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%S')
        sig_url = f"{supa.url}/rest/v1/scraper_signal?order=created_at.desc&limit=160&created_at=gte.{cutoff}"
        try:
            r = req.get(sig_url, headers=headers, timeout=10)
            if r.status_code == 200:
                result["signals"] = r.json()
        except Exception as e:
            print(f"[ScraperStatus] Signal error: {e}")

        today_str = datetime.utcnow().strftime('%Y-%m-%d')
        try:
            fix_url = f"{supa.url}/rest/v1/fixtures?select=match_id_hash&fixture_date=gte.{today_str}&limit=1"
            fix_headers = {**headers, "Prefer": "count=exact"}
            r = req.get(fix_url, headers=fix_headers, timeout=8)
            if r.status_code in [200, 206]:
                cr = r.headers.get('Content-Range', '')
                if '/' in cr:
                    result["active_match_count"] = int(cr.split('/')[1]) if cr.split('/')[1] != '*' else 0
        except Exception:
            pass

    except Exception as e:
        print(f"[ScraperStatus] Error: {e}")
    return jsonify(result)

@app.route('/api/alarm-engine-status')
def api_alarm_engine_status():
    """Alarm Engine v2.0 durumu - heartbeat, alarm istatistikleri ve son işlenen sinyaller"""
    import requests as req
    result = {
        "heartbeat": None,
        "processed_signals": [],
        "stats": {},
        "alarm_counts": {},
        "engine_version": "v2.0",
        "calculator": "scraper_standalone/alarm_calculator.py (AlarmCalculator)"
    }
    try:
        if not db.is_supabase_available:
            return jsonify(result)

        supa = db.supabase
        headers = {
            "apikey": supa.key,
            "Authorization": f"Bearer {supa.key}"
        }

        hb_url = f"{supa.url}/rest/v1/scraper_heartbeat?source=eq.alarm_engine&limit=1"
        try:
            r = req.get(hb_url, headers=headers, timeout=10)
            if r.status_code in [200, 206]:
                rows = r.json()
                if rows:
                    result["heartbeat"] = rows[0]
            else:
                sig_url_hb = f"{supa.url}/rest/v1/scraper_signal?processed=eq.true&order=processed_at.desc&limit=1"
                try:
                    r2 = req.get(sig_url_hb, headers=headers, timeout=10)
                    if r2.status_code == 200:
                        sigs = r2.json()
                        if sigs:
                            result["heartbeat"] = {
                                "source": "alarm_engine",
                                "last_heartbeat": sigs[0].get("processed_at", sigs[0].get("created_at")),
                                "status": "idle",
                                "match_count": sigs[0].get("match_count", 0)
                            }
                except Exception:
                    pass
        except Exception as e:
            print(f"[AlarmEngineStatus] Heartbeat error: {e}")

        alarm_tables = {
            "sharp": "sharp_alarms",
            "bigmoney": "bigmoney_alarms",
            "volumeshock": "volumeshock_alarms",
            "dropping": "dropping_alarms",
            "volumeleader": "volume_leader_alarms",
            "mim": "mim_alarms"
        }
        total_alarms = 0
        today_str = datetime.utcnow().strftime('%Y-%m-%d')
        for alarm_type, table_name in alarm_tables.items():
            try:
                count_url = f"{supa.url}/rest/v1/{table_name}?select=id&limit=1&match_date=gte.{today_str}"
                count_headers = {**headers, "Prefer": "count=exact"}
                r = req.get(count_url, headers=count_headers, timeout=8)
                if r.status_code in [200, 206]:
                    content_range = r.headers.get('Content-Range', '')
                    if '/' in content_range:
                        count = int(content_range.split('/')[1]) if content_range.split('/')[1] != '*' else 0
                    else:
                        count = len(r.json())
                    result["alarm_counts"][alarm_type] = count
                    total_alarms += count
                else:
                    result["alarm_counts"][alarm_type] = 0
            except Exception:
                result["alarm_counts"][alarm_type] = 0
        result["stats"]["total_active_alarms"] = total_alarms

        try:
            fix_url = f"{supa.url}/rest/v1/fixtures?select=match_id_hash&fixture_date=gte.{today_str}&limit=1"
            fix_headers = {**headers, "Prefer": "count=exact"}
            r = req.get(fix_url, headers=fix_headers, timeout=8)
            if r.status_code in [200, 206]:
                cr = r.headers.get('Content-Range', '')
                if '/' in cr:
                    result["stats"]["active_match_count"] = int(cr.split('/')[1]) if cr.split('/')[1] != '*' else 0
                else:
                    result["stats"]["active_match_count"] = len(r.json())
        except Exception:
            pass

        cutoff = (datetime.utcnow() - timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%S')
        sig_url = f"{supa.url}/rest/v1/scraper_signal?processed=eq.true&order=processed_at.desc&limit=50&created_at=gte.{cutoff}"
        try:
            r = req.get(sig_url, headers=headers, timeout=10)
            if r.status_code == 200:
                result["processed_signals"] = r.json()
        except Exception as e:
            print(f"[AlarmEngineStatus] Signal error: {e}")

        pending_url = f"{supa.url}/rest/v1/scraper_signal?processed=eq.false&select=id&limit=100"
        try:
            r = req.get(pending_url, headers=headers, timeout=10)
            if r.status_code == 200:
                result["stats"]["pending_count"] = len(r.json())
        except Exception:
            pass

    except Exception as e:
        print(f"[AlarmEngineStatus] Error: {e}")
    return jsonify(result)

@app.route('/app')
def index():
    """Main dashboard page - triggers lazy warmup on first visit"""
    trigger_app_warmup()
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

def _warmup_alarms():
    """Fill alarm cache"""
    alarm_fetchers = {
        'sharp': get_sharp_alarms_from_supabase,
        'bigmoney': get_bigmoney_alarms_from_supabase,
        'volumeshock': get_volumeshock_alarms_from_supabase,
        'dropping': get_dropping_alarms_from_supabase,
        'volumeleader': get_volumeleader_alarms_from_supabase,
        'mim': get_mim_alarms_from_supabase,
    }
    result = {}
    for atype, fetch_func in alarm_fetchers.items():
        try:
            data = fetch_func()
            result[atype] = data if data is not None else []
        except:
            result[atype] = []
    if result:
        set_alarm_cache(result)
    return len(result)

def _build_enriched_matches(matches_data):
    """Transform raw match list to frontend format"""
    enriched = []
    for m in matches_data:
        latest = m.get('latest', {})
        odds = {}
        if latest:
            odds = {
                'Odds1': latest.get('Odds1', latest.get('1', '-')),
                'OddsX': latest.get('OddsX', latest.get('X', '-')),
                'Odds2': latest.get('Odds2', latest.get('2', '-')),
                'Pct1': latest.get('Pct1', ''), 'Amt1': latest.get('Amt1', ''),
                'PctX': latest.get('PctX', ''), 'AmtX': latest.get('AmtX', ''),
                'Pct2': latest.get('Pct2', ''), 'Amt2': latest.get('Amt2', ''),
                'Volume': latest.get('Volume', '')
            }
        home = m.get('home_team', '')
        away = m.get('away_team', '')
        league = m.get('league', '')
        date = m.get('date', '')
        enriched.append({
            'home_team': home, 'away_team': away, 'league': league, 'date': date,
            'match_id': m.get('match_id_hash') or generate_match_id(home, away, league, date),
            'odds': odds, 'history_count': 1
        })
    return enriched

def _warmup_matches():
    """Fill matches cache for both all and today_future keys"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def fetch_all():
        data = db.get_all_matches_with_latest('moneyway_1x2', date_filter=None)
        return 'moneyway_1x2_all', data

    def fetch_today():
        result = db.get_matches_paginated('moneyway_1x2', limit=600, offset=0, today_only=True)
        return 'moneyway_1x2_today_future', result.get('matches', [])

    total = 0
    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = {ex.submit(fetch_all): 'all', ex.submit(fetch_today): 'today_future'}
        for future in as_completed(futures):
            try:
                cache_key, raw = future.result()
                if raw:
                    enriched = _build_enriched_matches(raw)
                    set_matches_cache(cache_key, enriched)
                    total += len(enriched)
            except Exception as e:
                print(f"[Warmup] matches fetch error: {e}")
    return total

def _warmup_licenses():
    """Fill license cache"""
    try:
        if not get_license_db():
            return 0
    except NameError:
        return 0
    licenses = license_select('licenses', '*', None, 'created_at', True) or []
    devices = license_select('license_devices', 'license_key') or []
    device_counts = {}
    for d in devices:
        key = d.get('license_key')
        device_counts[key] = device_counts.get(key, 0) + 1
    for lic in licenses:
        lic['device_count'] = device_counts.get(lic.get('key'), 0)
    _license_cache['data'] = {'success': True, 'licenses': licenses}
    import time as _t
    _license_cache['ts'] = _t.time()
    return len(licenses)

def _lazy_app_warmup():
    """Lazy warmup for /app - fills alarm + matches cache on first visit"""
    import time as _t
    from concurrent.futures import ThreadPoolExecutor, as_completed
    start = _t.time()
    print("[App Warmup] Starting parallel cache pre-fill...")
    
    tasks = {
        'Alarms': _warmup_alarms,
        'Matches': _warmup_matches,
    }
    
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {executor.submit(fn): name for name, fn in tasks.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    count = future.result()
                    print(f"[App Warmup] {name} cache filled ({_t.time()-start:.1f}s)")
                except Exception as e:
                    print(f"[App Warmup] {name} error: {e}")
    finally:
        _app_warmup_done.set()
    
    print(f"[App Warmup] Complete in {_t.time()-start:.1f}s")
    threading.Thread(target=_periodic_matches_warmup, daemon=True).start()

def _try_acquire_warmup_lock(pid):
    """Try to acquire the warmup master lock. Returns True if acquired."""
    lock_file = '/tmp/smartxflow_warmup.lock'
    try:
        fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(pid).encode())
        os.close(fd)
        return True
    except FileExistsError:
        try:
            with open(lock_file, 'r') as _lf:
                owner_pid = int(_lf.read().strip())
            try:
                os.kill(owner_pid, 0)
                return False
            except ProcessLookupError:
                os.remove(lock_file)
                return _try_acquire_warmup_lock(pid)
        except Exception:
            return False
    except Exception:
        return False

def _periodic_matches_warmup():
    """Keep matches cache always warm — refresh every 100s (TTL=120s).
    Only the master worker (file-lock winner) runs this; slave skips."""
    import time as _t
    my_pid = os.getpid()
    is_master = _try_acquire_warmup_lock(my_pid)
    if not is_master:
        print(f"[Cache Warmup] Worker {my_pid}: slave - periodic refresh skipped (master owns lock)")
        return
    print(f"[Cache Warmup] Worker {my_pid}: master - periodic refresh started (every 100s)")
    while True:
        _t.sleep(100)
        try:
            _warmup_matches()
            print("[Cache Warmup] Matches refreshed")
        except Exception as e:
            print(f"[Cache Warmup] Error: {e}")

def trigger_app_warmup():
    """Trigger app warmup on first /app visit (thread-safe, runs only once)"""
    global _app_warmup_started
    with _app_warmup_lock:
        if _app_warmup_started:
            return
        _app_warmup_started = True
    threading.Thread(target=_lazy_app_warmup, daemon=True).start()

def _lazy_admin_warmup():
    """Lazy warmup for /admin - fills license cache on first visit"""
    import time as _t
    start = _t.time()
    print("[Admin Warmup] Starting license cache pre-fill...")
    try:
        _warmup_licenses()
        print(f"[Admin Warmup] Licenses cache filled ({_t.time()-start:.1f}s)")
    except Exception as e:
        print(f"[Admin Warmup] Error: {e}")
    finally:
        _admin_warmup_done.set()
    print(f"[Admin Warmup] Complete in {_t.time()-start:.1f}s")

def trigger_admin_warmup():
    """Trigger admin warmup on first /admin visit (thread-safe, runs only once)"""
    global _admin_warmup_started
    with _admin_warmup_lock:
        if _admin_warmup_started:
            return
        _admin_warmup_started = True
    threading.Thread(target=_lazy_admin_warmup, daemon=True).start()

@app.route('/api/matches')
@license_required
def get_matches():
    """Get matches from database with server-side caching
    
    Triggers lazy app warmup if not started yet.
    
    Params:
    - bulk=1: Returns ALL matches at once (uses server cache, instant on hit)
    - refresh=true: Force cache refresh
    
    Result: Cache hit = 0ms, Cache miss = ~2s (fetches all pages)
    """
    trigger_app_warmup()
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
            ft_scores = _get_finished_scores_map()
            _enrich_ft_scores_with_match_hashes(ft_scores, cached_data)
            resp_data = {'matches': cached_data, 'total': len(cached_data), 'has_more': False}
            if ft_scores:
                resp_data['finished_scores'] = ft_scores
            return jsonify(resp_data)
        
        # Cache miss - fetch ALL matches in one go
        all_matches = []
        
        # For date_filter, use get_all_matches_with_latest (already returns all)
        if date_filter and date_filter not in ('today_future',):
            matches_with_latest = db.get_all_matches_with_latest(market, date_filter=date_filter)
            page_matches_list = [matches_with_latest]
        else:
            # For ALL / today_future mode, paginate through all results
            page_matches_list = []
            current_offset = 0
            page_limit = 100
            max_pages = 50
            
            for page in range(max_pages):
                result = db.get_matches_paginated(market, limit=page_limit, offset=current_offset, today_only=(date_filter == 'today_future'))
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
        
        # For DROPPING markets: Get odds from 24h ago for "Son 24 saat" comparison
        if is_dropping and all_matches:
            match_hashes = [m.get('match_id') for m in all_matches if m.get('match_id')]
            odds_24h = db.get_24h_odds_batch(market, match_hashes)
            
            if odds_24h:
                for match in all_matches:
                    match_id = match.get('match_id')
                    if match_id in odds_24h:
                        h24 = odds_24h[match_id]
                        odds = match.get('odds', {})
                        
                        if '1x2' in market:
                            if h24.get('OpeningOdds1'):
                                odds['PrevOdds1'] = h24['OpeningOdds1']
                            if h24.get('OpeningOddsX'):
                                odds['PrevOddsX'] = h24['OpeningOddsX']
                            if h24.get('OpeningOdds2'):
                                odds['PrevOdds2'] = h24['OpeningOdds2']
                        elif 'ou25' in market:
                            if h24.get('OpeningOver'):
                                odds['PrevOver'] = h24['OpeningOver']
                            if h24.get('OpeningUnder'):
                                odds['PrevUnder'] = h24['OpeningUnder']
                        elif 'btts' in market:
                            if h24.get('OpeningYes'):
                                odds['PrevYes'] = h24['OpeningYes']
                            if h24.get('OpeningNo'):
                                odds['PrevNo'] = h24['OpeningNo']
        
        # Cache the result
        set_matches_cache(cache_key, all_matches)
        elapsed = (t.time() - start_time) * 1000
        print(f"[Matches/Bulk] Cache MISS for {market} - fetched {len(all_matches)} matches in {elapsed:.0f}ms")
        
        ft_scores = _get_finished_scores_map()
        _enrich_ft_scores_with_match_hashes(ft_scores, all_matches)
        resp_data = {'matches': all_matches, 'total': len(all_matches), 'has_more': False}
        if ft_scores:
            resp_data['finished_scores'] = ft_scores
        return jsonify(resp_data)
    
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
        
        ft_scores = _get_finished_scores_map()
        _enrich_ft_scores_with_match_hashes(ft_scores, enriched)
        resp_data = {
            'matches': enriched,
            'total': result.get('total', len(enriched)),
            'has_more': result.get('has_more', False)
        }
        if ft_scores:
            resp_data['finished_scores'] = ft_scores
        return jsonify(resp_data)
    
    # Fallback to old method for date_filter (today/yesterday)
    now = time.time()
    cache_key = f"{market}_{date_filter}"
    
    if cache_key in matches_cache['data']:
        last_time = matches_cache['timestamp'].get(cache_key, 0)
        if (now - last_time) < matches_cache['ttl']:
            cached_data = matches_cache['data'][cache_key]
            sliced = cached_data[offset:offset + limit]
            ft_scores = _get_finished_scores_map()
            _enrich_ft_scores_with_match_hashes(ft_scores, cached_data)
            resp_data = {'matches': sliced, 'total': len(cached_data), 'has_more': offset + limit < len(cached_data)}
            if ft_scores:
                resp_data['finished_scores'] = ft_scores
            return jsonify(resp_data)
    
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
    ft_scores = _get_finished_scores_map()
    _enrich_ft_scores_with_match_hashes(ft_scores, enriched)
    resp_data = {'matches': sliced, 'total': len(enriched), 'has_more': offset + limit < len(enriched)}
    if ft_scores:
        resp_data['finished_scores'] = ft_scores
    return jsonify(resp_data)


@app.route('/api/match/history/bulk')
@license_required
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
    
    resolved_home = home
    resolved_away = away
    resolved_league = league
    
    cache_key = f"{home.lower().strip()}|{away.lower().strip()}|{league.lower().strip()}"
    
    cached_data, from_cache = get_cached_history(cache_key)
    if from_cache:
        print(f"[History/Bulk] Cache HIT for {home} vs {away} - 0ms")
        return jsonify({'markets': cached_data})
    
    start_time = time.time()
    print(f"[History/Bulk] Cache MISS for {home} vs {away}, fetching parallel...")
    
    test_history = db.get_match_history(home, away, 'moneyway_1x2', league)
    if not test_history:
        try:
            import urllib.parse
            home_like = urllib.parse.quote(home[:8] if len(home) > 8 else home, safe='')
            away_like = urllib.parse.quote(away[:8] if len(away) > 8 else away, safe='')
            fix_url = f"{db.supabase._rest_url('fixtures')}?select=home_team,away_team,league&home_team=ilike.*{home_like}*&away_team=ilike.*{away_like}*&limit=1"
            fix_resp = db.supabase._get_http_client().get(fix_url, headers=db.supabase._headers(), timeout=10)
            if fix_resp.status_code == 200:
                fix_rows = fix_resp.json()
                if fix_rows:
                    resolved_home = fix_rows[0].get('home_team', home)
                    resolved_away = fix_rows[0].get('away_team', away)
                    if not league and fix_rows[0].get('league'):
                        resolved_league = fix_rows[0]['league']
                    print(f"[History/Bulk] Fuzzy resolved: {home} vs {away} -> {resolved_home} vs {resolved_away} (league: {resolved_league})")
                    cache_key = f"{resolved_home.lower().strip()}|{resolved_away.lower().strip()}|{resolved_league.lower().strip()}"
                    cached_data2, from_cache2 = get_cached_history(cache_key)
                    if from_cache2:
                        print(f"[History/Bulk] Cache HIT after fuzzy for {resolved_home} vs {resolved_away} - 0ms")
                        return jsonify({'markets': cached_data2})
                else:
                    print(f"[History/Bulk] No fuzzy match found in fixtures for {home} vs {away}")
        except Exception as e:
            print(f"[History/Bulk] Fuzzy lookup error: {e}")
    
    all_markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts', 
                   'dropping_1x2', 'dropping_ou25', 'dropping_btts']
    
    def _build_market_data(market):
        history = db.get_match_history(resolved_home, resolved_away, market, resolved_league)
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
        return market, {'history': history, 'chart_data': chart_data}
    
    from concurrent.futures import ThreadPoolExecutor
    result = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(_build_market_data, m): m for m in all_markets}
        for future in futures:
            market_name, market_data = future.result()
            result[market_name] = market_data
    
    elapsed = int((time.time() - start_time) * 1000)
    
    total_history = sum(len(v.get('history') or []) for v in result.values())
    if total_history > 0:
        print(f"[History/Bulk] Fetched {home} vs {away} in {elapsed}ms (parallel), {total_history} rows, caching...")
        set_history_cache(cache_key, result)
    else:
        print(f"[History/Bulk] Fetched {home} vs {away} in {elapsed}ms but 0 rows - NOT caching (possible error)")
    
    return jsonify({'markets': result})


@app.route('/api/favorite/toggle', methods=['POST'])
@license_required
def toggle_favorite():
    data = request.get_json() or {}
    match_key = data.get('match_key', '').strip()
    license_key = session.get('license_key', '').strip()
    if not license_key:
        device_id = (data.get('device_id', '') or request.headers.get('X-Device-Id', '')).strip()[:16]
        license_key = f"device:{device_id}" if device_id else ''
    if not match_key or not license_key:
        return jsonify({'error': 'match_key and license_key required'}), 400
    result = db.toggle_favorite(license_key, match_key)
    return jsonify(result)

@app.route('/api/favorites')
@license_required
def get_favorites():
    license_key = session.get('license_key', '').strip()
    if not license_key:
        device_id = (request.args.get('device_id', '') or request.headers.get('X-Device-Id', '')).strip()[:16]
        license_key = f"device:{device_id}" if device_id else ''
    if not license_key:
        return jsonify({'favorites': []})
    favorites = db.get_user_favorites(license_key)
    return jsonify({'favorites': favorites})

@app.route('/api/favorites-matches')
@license_required
def get_favorites_matches():
    """Returns full match data for all favorited matches (any date)."""
    license_key = session.get('license_key', '').strip()
    if not license_key:
        device_id = (request.args.get('device_id', '') or request.headers.get('X-Device-Id', '')).strip()[:16]
        license_key = f"device:{device_id}" if device_id else ''
    if not license_key:
        return jsonify({'matches': []})

    market = request.args.get('market', 'moneyway_1x2')
    favorites = db.get_user_favorites(license_key)
    if not favorites:
        return jsonify({'matches': []})

    fav_set = set(favorites)

    def _mk(m):
        return (m.get('home_team', '') or '') + '|' + (m.get('away_team', '') or '') + '|' + (m.get('league', '') or '')

    fav_matches = []
    found_keys = set()

    # Try server-side cache first (all matches, no date limit)
    for cache_key in (f'{market}_all', f'{market}_today_future'):
        cached, _ = get_matches_cache(cache_key)
        if cached:
            for m in cached:
                k = _mk(m)
                if k in fav_set and k not in found_keys:
                    fav_matches.append(m)
                    found_keys.add(k)

    # For favorites still not found, try yesterday's data
    still_missing = fav_set - found_keys
    if still_missing:
        try:
            yest_raw = db.get_all_matches_with_latest(market, date_filter='yesterday')
            if yest_raw:
                yest_enriched = _build_enriched_matches(yest_raw) if isinstance(yest_raw, list) else _build_enriched_matches(yest_raw.get('matches', []))
                for m in yest_enriched:
                    k = _mk(m)
                    if k in still_missing and k not in found_keys:
                        fav_matches.append(m)
                        found_keys.add(k)
        except Exception as e:
            print(f"[FavMatches] Yesterday fetch error: {e}")

    return jsonify({'matches': fav_matches})

@app.route('/api/favorite/counts', methods=['POST'])
@license_required
def get_favorite_counts():
    data = request.get_json() or {}
    match_keys = data.get('match_keys', [])
    if not match_keys:
        return jsonify({'counts': {}})
    counts = db.get_favorite_counts(match_keys)
    return jsonify({'counts': counts})

@app.route('/api/favorite/all-counts')
@license_required
def get_all_favorite_counts():
    counts = db.get_all_favorite_counts()
    print(f"[FavCounts] GET /api/favorite/all-counts: {len(counts)} matches with favorites")
    return jsonify({'counts': counts})

@app.route('/api/match/history')
@license_required
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
    """Legacy endpoint - scraping handled by Scraper Engine workflow"""
    return jsonify({
        'status': 'disabled',
        'message': 'Scraping handled by Scraper Engine workflow'
    })


@app.route('/api/scrape/auto', methods=['POST'])
def toggle_auto_scrape():
    """Legacy endpoint - scraping handled by Scraper Engine workflow"""
    return jsonify({
        'status': 'disabled',
        'message': 'Scraping handled by Scraper Engine workflow'
    })


@app.route('/api/interval', methods=['POST'])
def update_interval():
    """Legacy endpoint - scraping handled by Scraper Engine workflow"""
    return jsonify({
        'status': 'disabled',
        'message': 'Scraping handled by Scraper Engine workflow'
    })


@app.route('/api/live/matches')
@license_required
def get_live_matches():
    """Canlı maç listesi - live_fixtures + son snapshot verisi"""
    try:
        supabase = get_supabase_client()
        if not supabase or not supabase.is_available:
            return jsonify({'matches': [], 'error': 'Supabase bağlantısı yok'}), 200

        headers = supabase._headers()

        fix_url = f"{supabase._rest_url('live_fixtures')}?status=eq.live&order=updated_at.desc&limit=200"
        fix_resp = supabase._get_http_client().get(fix_url, headers=headers, timeout=15)
        if fix_resp.status_code != 200:
            return jsonify({'matches': [], 'error': f'Fixtures HTTP {fix_resp.status_code}'}), 200
        raw_fixtures = fix_resp.json() or []

        from datetime import datetime as _dt2, timezone as _tz2
        _now_api = _dt2.now(_tz2.utc)
        auto_ft_hashes = []
        fixtures = []
        for f in raw_fixtures:
            ko_str = f.get('kickoff_utc', '')
            if ko_str:
                try:
                    ko_t = _dt2.fromisoformat(ko_str)
                    dm = (_now_api - ko_t).total_seconds() / 60
                    if dm >= 120:
                        auto_ft_hashes.append(f['match_id_hash'])
                        f['status'] = 'ft'
                        if not f.get('minute') or f['minute'] not in ('FT', 'MS', 'AET', 'PEN'):
                            f['minute'] = 'FT'
                except Exception:
                    pass
            fixtures.append(f)
        if auto_ft_hashes:
            try:
                for aft_h in auto_ft_hashes:
                    patch_url = f"{supabase._rest_url('live_fixtures')}?match_id_hash=eq.{aft_h}"
                    supabase._get_http_client().patch(patch_url, headers={**headers, 'Content-Type': 'application/json', 'Prefer': 'return=minimal'}, json={'status': 'ft', 'minute': 'FT'}, timeout=5)
                print(f"[Live API] Auto-FT: {len(auto_ft_hashes)} maç DB'de güncellendi")
            except Exception as e:
                print(f"[Live API] Auto-FT DB güncelleme hatası: {e}")

        ft_url = f"{supabase._rest_url('live_fixtures')}?status=eq.ft&order=updated_at.desc&limit=100"
        ft_resp = supabase._get_http_client().get(ft_url, headers=headers, timeout=10)
        ft_fixtures = ft_resp.json() if ft_resp.status_code == 200 else []
        fixtures = fixtures + ft_fixtures

        if not fixtures:
            return jsonify({'matches': [], 'total': 0}), 200

        hashes = [f['match_id_hash'] for f in fixtures]

        snap_url = (
            f"{supabase._rest_url('live_snapshots')}"
            f"?match_id_hash=in.({','.join(hashes)})"
            f"&order=snapshot_at.desc&limit=2000"
        )
        snap_resp = supabase._get_http_client().get(snap_url, headers=headers, timeout=15)
        snaps = snap_resp.json() if snap_resp.status_code == 200 else []

        latest_1x2 = {}
        ou_by_match = {}
        for s in snaps:
            h = s['match_id_hash']
            market = s.get('market', '')
            sel = s.get('selection', '')
            if market == '1X2':
                key = f"{h}_1X2_{sel}"
                if key not in latest_1x2:
                    latest_1x2[key] = s
            elif market == 'OU':
                if h not in ou_by_match:
                    ou_by_match[h] = []
                ou_by_match[h].append(s)

        matches = []
        from datetime import datetime as _dt, timezone as _tz
        now_utc = _dt.now(_tz.utc)
        for f in fixtures:
            h = f['match_id_hash']
            minute_val = (f.get('minute') or '').strip()
            score = f.get('score', '')
            f_status = (f.get('status') or '').strip().lower()

            is_finished = f_status == 'ft' or minute_val in ('FT', 'MS', 'AET', 'PEN')

            if is_finished:
                if not score:
                    continue
            elif not minute_val and not score:
                ko_str = f.get('kickoff_utc', '')
                if ko_str:
                    try:
                        ko_time = _dt.fromisoformat(ko_str)
                        if ko_time > now_utc:
                            continue
                        diff_min = (now_utc - ko_time).total_seconds() / 60
                        if diff_min > 130:
                            continue
                    except Exception:
                        pass
                else:
                    continue
            elif minute_val and not score:
                ko_str = f.get('kickoff_utc', '')
                if ko_str:
                    try:
                        ko_time = _dt.fromisoformat(ko_str)
                        diff_min = (now_utc - ko_time).total_seconds() / 60
                        if diff_min > 150:
                            continue
                    except Exception:
                        pass
            match_data = {
                'match_id_hash': h,
                'home_team': f.get('home_team', ''),
                'away_team': f.get('away_team', ''),
                'league': f.get('league', ''),
                'score': score,
                'minute': f.get('minute', ''),
                'kickoff_utc': f.get('kickoff_utc', ''),
                'status': f.get('status', 'live'),
                'updated_at': f.get('updated_at', ''),
                'odds': {},
                'ou_lines': {},
            }

            for sel in ['1', 'X', '2']:
                key = f"{h}_1X2_{sel}"
                s = latest_1x2.get(key)
                if s:
                    match_data['odds'][sel] = {
                        'odds': s.get('odds'),
                        'share': s.get('share'),
                        'volume': s.get('volume'),
                    }

            if h in ou_by_match:
                by_line = {}
                for s in ou_by_match[h]:
                    line = s.get('ou_line', '')
                    sel = s.get('selection', '')
                    if line not in by_line:
                        by_line[line] = {}
                    if sel not in by_line[line] or s.get('snapshot_at', '') > by_line[line][sel].get('snapshot_at', ''):
                        by_line[line][sel] = s
                for line, sels in by_line.items():
                    line_data = {}
                    for sel in ['U', 'O']:
                        sd = sels.get(sel)
                        if sd:
                            line_data[sel] = {
                                'odds': sd.get('odds'),
                                'share': sd.get('share'),
                                'volume': sd.get('volume'),
                            }
                    if line_data:
                        match_data['ou_lines'][line] = line_data

            matches.append(match_data)

        return jsonify({'matches': matches, 'total': len(matches)}), 200

    except Exception as e:
        print(f"[API] /api/live/matches hata: {e}")
        return jsonify({'matches': [], 'error': str(e)}), 200


_ft_scores_cache = {'data': None, 'ts': 0}

def _fuzzy_team_match(name1, name2):
    if name1 == name2:
        return True
    if len(name1) < 3 or len(name2) < 3:
        return False
    shorter, longer = (name1, name2) if len(name1) <= len(name2) else (name2, name1)
    if longer.startswith(shorter):
        return True
    w1 = shorter.split()
    w2 = longer.split()
    if w1 and w2 and len(w1[0]) >= 4 and len(w2[0]) >= 4:
        sw, lw = (w1[0], w2[0]) if len(w1[0]) <= len(w2[0]) else (w2[0], w1[0])
        if lw.startswith(sw):
            return True
    return False

def _enrich_ft_scores_with_match_hashes(ft_scores, matches):
    if not ft_scores or not matches:
        return ft_scores
    ft_entries = []
    seen = set()
    for key, entry in ft_scores.items():
        if '|' not in key or not isinstance(entry, dict):
            continue
        eid = id(entry)
        if eid in seen:
            continue
        seen.add(eid)
        h_norm = normalize_field(entry.get('home', ''))
        a_norm = normalize_field(entry.get('away', ''))
        if h_norm and a_norm:
            ft_entries.append((h_norm, a_norm, entry))
    if not ft_entries:
        return ft_scores
    added = 0
    for m in matches:
        mid = m.get('match_id', '')
        if not mid or mid in ft_scores:
            continue
        h_norm = normalize_field(m.get('home_team', ''))
        a_norm = normalize_field(m.get('away_team', ''))
        if not h_norm or not a_norm:
            continue
        for ft_h, ft_a, entry in ft_entries:
            if _fuzzy_team_match(h_norm, ft_h) and _fuzzy_team_match(a_norm, ft_a):
                ft_scores[mid] = entry
                added += 1
                break
    if added:
        print(f"[FT-Scores] Cross-ref: {added} Arbworld hash eklendi")
    return ft_scores

def _get_finished_scores_map():
    import time as _t
    now = _t.time()
    if _ft_scores_cache['data'] is not None and now - _ft_scores_cache['ts'] < 60:
        return _ft_scores_cache['data'].get('scores', {})
    try:
        supabase = get_supabase_client()
        if not supabase or not supabase.is_available:
            return {}
        headers = supabase._headers()
        cutoff_7d = (now_turkey() - timedelta(days=7)).strftime('%Y-%m-%dT00:00:00+03:00').replace('+', '%2B')
        scores = {}
        batch_size = 1000
        offset = 0
        while True:
            url = (f"{supabase._rest_url('live_fixtures')}?status=eq.ft"
                   f"&updated_at=gte.{cutoff_7d}"
                   f"&select=home_team,away_team,score,match_id_hash"
                   f"&order=updated_at.desc&limit={batch_size}&offset={offset}")
            resp = supabase._get_http_client().get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                break
            rows = resp.json()
            if not rows:
                break
            for f in rows:
                sc = (f.get('score') or '').strip()
                if sc:
                    h = f.get('match_id_hash', '')
                    key_name = (f.get('home_team', '') + '|' + f.get('away_team', '')).lower()
                    entry = {'score': sc, 'home': f.get('home_team', ''), 'away': f.get('away_team', '')}
                    scores[key_name] = entry
                    if h:
                        scores[h] = entry
            if len(rows) < batch_size:
                break
            offset += batch_size
        print(f"[FT-Scores] {len(scores)//2} maç skoru yüklendi (7 günlük)")
        result = {'scores': scores}
        _ft_scores_cache['data'] = result
        _ft_scores_cache['ts'] = now
        return scores
    except Exception as e:
        print(f"[FT-Scores] hata: {e}")
        return {}

def _normalize_to_iso_date(date_str):
    """'13.Apr 18:30:00' veya '2026-04-13T14:00' gibi her formatı 'YYYY-MM-DD' ISO'ya çevirir.
    Cleanup sorgusu match_date < 'YYYY-MM-DD' şeklinde karşılaştırır;
    ham betwatch formatı ('13.Apr...') metin sıralamasında her zaman yanlış eşleşir."""
    import re as _re
    from datetime import date as _d
    try:
        s = str(date_str).strip()
        if not s:
            return ''
        if len(s) >= 10 and s[4] == '-' and s[7] == '-':
            return s[:10]
        m = _re.search(r'(\d{2})\.(\w{3})', s)
        if m:
            months = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5,
                      'Jun': 6, 'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10,
                      'Nov': 11, 'Dec': 12}
            day = int(m.group(1))
            mon = months.get(m.group(2).capitalize(), 0)
            if mon:
                return _d(_d.today().year, mon, day).isoformat()
    except Exception:
        pass
    return str(date_str)[:10] if date_str else ''


def _normalize_to_iso_datetime_tr(date_str):
    """'13.Apr 18:30:00' veya '2026-04-13T14:00' → 'YYYY-MM-DDTHH:MM:00+03:00' (Türkiye saati).
    Betwatch saatleri zaten Türkiye saatindedir. Saat yoksa sadece YYYY-MM-DD döner."""
    import re as _re
    from datetime import date as _d
    try:
        s = str(date_str).strip()
        if not s:
            return ''
        if '+03:00' in s:
            return s
        if len(s) >= 10 and s[4] == '-' and s[7] == '-':
            t = _re.search(r'T(\d{2}):(\d{2})', s)
            if t:
                return f"{s[:10]}T{t.group(1)}:{t.group(2)}:00+03:00"
            return s[:10]
        m = _re.search(r'(\d{2})\.(\w{3})', s)
        if m:
            months = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5,
                      'Jun': 6, 'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10,
                      'Nov': 11, 'Dec': 12}
            day = int(m.group(1))
            mon = months.get(m.group(2).capitalize(), 0)
            if mon:
                iso_date = _d(_d.today().year, mon, day).isoformat()
                t = _re.search(r'(\d{2}):(\d{2})(?::\d{2})?', s)
                if t:
                    return f"{iso_date}T{t.group(1)}:{t.group(2)}:00+03:00"
                return iso_date
    except Exception:
        pass
    return str(date_str)[:10] if date_str else ''


def _save_underdog_signals(signals):
    """Upsert new signals to underdog_signals table; ignore duplicates."""
    try:
        supabase = get_supabase_client()
        if not supabase or not supabase.is_available:
            return
        records = []
        for s in signals:
            match_key = f"{s['home_team']}|{s['away_team']}|{s.get('date','')}"
            records.append({
                'match_key': match_key,
                'home_team': s.get('home_team', ''),
                'away_team': s.get('away_team', ''),
                'league': s.get('league', ''),
                'match_date': _normalize_to_iso_datetime_tr(s.get('date', '')),
                'selection_code': s.get('selection_code', ''),
                'odds': str(s.get('odds', '')),
                'pct': str(s.get('pct', '')),
                'amt': str(s.get('amt', '')),
                'volume': str(s.get('volume', '')),
            })
        if not records:
            return
        headers = supabase._headers()
        # VERIFIED: underdog_signals table has UNIQUE(match_key, selection_code)
        # composite constraint (confirmed by DB error: "Key (match_key, selection_code)
        # ... already exists."). on_conflict target must match this exactly.
        headers['Prefer'] = 'resolution=ignore-duplicates,return=minimal'
        url = f"{supabase._rest_url('underdog_signals')}?on_conflict=match_key,selection_code"
        resp = supabase._get_http_client().post(url, headers=headers, json=records, timeout=10)
        if resp.status_code not in (200, 201):
            print(f"[UnderdogSignals] Save non-2xx: {resp.status_code} {resp.text[:200]}")
        else:
            print(f"[UnderdogSignals] Saved {len(records)} signals: {resp.status_code}")
    except Exception as e:
        print(f"[UnderdogSignals] save error: {e}")


def _update_underdog_signal_scores():
    """Fill in FT scores for signals that don't have one yet."""
    try:
        supabase = get_supabase_client()
        if not supabase or not supabase.is_available:
            return
        headers = supabase._headers()
        # Match both NULL and empty-string scores (table default may vary)
        url = f"{supabase._rest_url('underdog_signals')}?or=(score.is.null,score.eq.)&select=match_key,selection_code,home_team,away_team&limit=300"
        resp = supabase._get_http_client().get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            print(f"[UnderdogSignals] Fetch pending non-2xx: {resp.status_code}")
            return
        pending = resp.json()
        if not pending:
            return
        ft_scores = _get_finished_scores_map()
        if not ft_scores:
            return
        # Build normalised FT entries list once
        ft_entries = []
        seen_ids = set()
        for ft_key, ft_entry in ft_scores.items():
            if '|' not in ft_key or not isinstance(ft_entry, dict):
                continue
            eid = id(ft_entry)
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
            ft_h = normalize_field(ft_entry.get('home', ''))
            ft_a = normalize_field(ft_entry.get('away', ''))
            if ft_h and ft_a:
                ft_entries.append((ft_h, ft_a, ft_entry))
        updated = 0
        for sig in pending:
            sig_h = normalize_field(sig.get('home_team', ''))
            sig_a = normalize_field(sig.get('away_team', ''))
            # Direct key lookup first
            direct_key = (sig.get('home_team', '') + '|' + sig.get('away_team', '')).lower()
            entry = ft_scores.get(direct_key)
            if not entry:
                for ft_h, ft_a, ft_entry in ft_entries:
                    if _fuzzy_team_match(sig_h, ft_h) and _fuzzy_team_match(sig_a, ft_a):
                        entry = ft_entry
                        break
            if entry and entry.get('score'):
                from urllib.parse import quote as _url_quote
                ph = supabase._headers()
                mk = _url_quote(sig.get('match_key', ''), safe='')
                sc = _url_quote(sig.get('selection_code', ''), safe='')
                pu = f"{supabase._rest_url('underdog_signals')}?match_key=eq.{mk}&selection_code=eq.{sc}"
                pr = supabase._get_http_client().patch(pu, headers=ph, json={'score': entry['score']}, timeout=5)
                if pr.status_code in (200, 204):
                    updated += 1
                else:
                    print(f"[UnderdogSignals] Score patch non-2xx: {pr.status_code} mk={sig.get('match_key','')}")
        if updated:
            print(f"[UnderdogSignals] Updated scores for {updated} signals")
    except Exception as e:
        print(f"[UnderdogSignals] score update error: {e}")


_backfill_done = set()

def _backfill_match_date_times(rows, table_name):
    """Backfill date-only match_date values with time parsed from match_key.
    Idempotent: skips rows that already have time info (+03:00).
    Runs once per table per process (marked done only after success).
    Also updates in-memory rows so the current response reflects corrected values."""
    if table_name in _backfill_done:
        return
    import re as _re
    from datetime import date as _d
    months = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5,
              'Jun': 6, 'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10,
              'Nov': 11, 'Dec': 12}
    to_fix = []
    for i, row in enumerate(rows):
        md = str(row.get('match_date', '') or '')
        if '+03:00' in md:
            continue
        mk = str(row.get('match_key', '') or '')
        parts = mk.split('|')
        if len(parts) < 3:
            continue
        date_part = parts[-1].strip()
        dm = _re.search(r'(\d{2})\.(\w{3})', date_part)
        tm = _re.search(r'(\d{2}):(\d{2})', date_part)
        if dm and tm:
            mon = months.get(dm.group(2).capitalize(), 0)
            if mon:
                iso_date = _d(_d.today().year, mon, int(dm.group(1))).isoformat()
                new_md = f"{iso_date}T{tm.group(1)}:{tm.group(2)}:00+03:00"
                to_fix.append((row.get('id'), new_md, i))
                rows[i]['match_date'] = new_md
    if not to_fix:
        _backfill_done.add(table_name)
        return
    try:
        supabase = get_supabase_client()
        if not supabase or not supabase.is_available:
            return
        http = supabase._get_http_client()
        hdrs = supabase._headers()
        hdrs['Content-Type'] = 'application/json'
        hdrs['Prefer'] = 'return=minimal'
        fixed = 0
        for rid, new_md, _ in to_fix:
            try:
                pr = http.patch(
                    f"{supabase._rest_url(table_name)}?id=eq.{rid}",
                    headers=hdrs, json={'match_date': new_md}, timeout=5
                )
                if pr.status_code in (200, 204):
                    fixed += 1
            except Exception:
                pass
        if fixed == len(to_fix):
            _backfill_done.add(table_name)
        if fixed:
            print(f"[Backfill] {table_name}: fixed {fixed}/{len(to_fix)} match_date values with +03:00")
    except Exception as e:
        print(f"[Backfill] {table_name} error: {e}")


def _fetch_all_underdog_signals():
    """Fetch signals from underdog_signals table (all records, up to 5000)."""
    try:
        supabase = get_supabase_client()
        if not supabase or not supabase.is_available:
            return []
        headers = supabase._headers()
        url = f"{supabase._rest_url('underdog_signals')}?select=*&selection_code=neq.X&order=match_date.desc,home_team.asc&limit=5000"
        resp = supabase._get_http_client().get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            rows = resp.json()
            _backfill_match_date_times(rows, 'underdog_signals')
            result = []
            for r in rows:
                result.append({
                    'match_key': r.get('match_key', ''),
                    'home_team': r.get('home_team', ''),
                    'away_team': r.get('away_team', ''),
                    'league': r.get('league', ''),
                    'date': r.get('match_date', ''),
                    'match_date': r.get('match_date', ''),
                    'selection_code': r.get('selection_code', ''),
                    'selection_label': r.get('selection_label', ''),
                    'odds': r.get('odds', ''),
                    'pct': r.get('pct', ''),
                    'amt': r.get('amt', ''),
                    'volume': r.get('volume', ''),
                    'current_odds': r.get('current_odds') or '',
                    'current_pct': r.get('current_pct') or '',
                    'current_amt': r.get('current_amt') or '',
                    'current_volume': r.get('current_volume') or '',
                    'last_updated_at': r.get('last_updated_at') or '',
                    'created_at': r.get('created_at') or '',
                    'score': r.get('score') or '',
                    'result': r.get('result') or '',
                })
            return result
        return []
    except Exception as e:
        print(f"[UnderdogSignals] fetch error: {e}")
        return []


def _ensure_underdog_result_column():
    """No-op: result column migration replaced by JSON file approach."""
    pass


_ud_results_path = os.path.join('data', 'underdog_results.json')


def _load_ud_results():
    """Load underdog signal results from JSON file."""
    try:
        if os.path.exists(_ud_results_path):
            with open(_ud_results_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_ud_result(match_key, selection_code, result):
    """Save (or clear) an underdog signal result to JSON file."""
    results = _load_ud_results()
    key = f"{match_key}|{selection_code}"
    if result:
        results[key] = result
    else:
        results.pop(key, None)
    os.makedirs('data', exist_ok=True)
    with open(_ud_results_path, 'w', encoding='utf-8') as f:
        json.dump(results, f)


@app.route('/api/finished-scores')
@license_required
def get_finished_scores():
    scores = _get_finished_scores_map()
    return jsonify({'scores': scores}), 200


@app.route('/api/live/match/history-by-teams')
@license_required
def get_live_match_history_by_teams():
    """Takım isimlerine göre live snapshot geçmişi (prematch modal için)"""
    home = request.args.get('home', '').strip()
    away = request.args.get('away', '').strip()
    if not home or not away:
        return jsonify({'snapshots': [], 'error': 'home ve away parametreleri gerekli'}), 200

    try:
        supabase = get_supabase_client()
        if not supabase or not supabase.is_available:
            return jsonify({'snapshots': [], 'has_live': False}), 200

        headers = supabase._headers()

        import urllib.parse
        home_short = home[:100].rstrip('.')
        away_short = away[:100].rstrip('.')
        if len(home_short) < 3 or len(away_short) < 3:
            return jsonify({'snapshots': [], 'has_live': False}), 200
        for ch in ['%', '_', '*']:
            home_short = home_short.replace(ch, '')
            away_short = away_short.replace(ch, '')
        if len(home_short) < 3 or len(away_short) < 3:
            return jsonify({'snapshots': [], 'has_live': False}), 200
        home_enc = urllib.parse.quote(home_short)
        away_enc = urllib.parse.quote(away_short)
        fix_url = (
            f"{supabase._rest_url('live_fixtures')}"
            f"?home_team=ilike.{home_enc}*&away_team=ilike.{away_enc}*"
            f"&order=updated_at.desc&limit=1"
        )
        fix_resp = supabase._get_http_client().get(fix_url, headers=headers, timeout=10)
        if fix_resp.status_code != 200 or not fix_resp.json():
            fix_url2 = (
                f"{supabase._rest_url('live_fixtures')}"
                f"?home_team=eq.{urllib.parse.quote(home[:100])}&away_team=eq.{urllib.parse.quote(away[:100])}"
                f"&order=updated_at.desc&limit=1"
            )
            fix_resp = supabase._get_http_client().get(fix_url2, headers=headers, timeout=10)
            if fix_resp.status_code != 200 or not fix_resp.json():
                return jsonify({'snapshots': [], 'has_live': False}), 200

        fixture = fix_resp.json()[0]
        match_hash = fixture.get('match_id_hash', '')
        if not match_hash:
            return jsonify({'snapshots': [], 'has_live': False}), 200

        return _get_live_history_by_hash(supabase, headers, match_hash, fixture)

    except Exception as e:
        print(f"[API] /api/live/match/history-by-teams hata: {e}")
        return jsonify({'snapshots': [], 'has_live': False, 'error': str(e)}), 200


def _get_live_history_by_hash(supabase, headers, match_hash, fixture=None):
    """Ortak live history verisi döndüren yardımcı fonksiyon."""
    if not fixture:
        fix_url = f"{supabase._rest_url('live_fixtures')}?match_id_hash=eq.{match_hash}&limit=1"
        fix_resp = supabase._get_http_client().get(fix_url, headers=headers, timeout=10)
        if fix_resp.status_code == 200 and fix_resp.json():
            fixture = fix_resp.json()[0]

    snap_url = (
        f"{supabase._rest_url('live_snapshots')}"
        f"?match_id_hash=eq.{match_hash}"
        f"&order=snapshot_at.asc&limit=5000"
    )
    snap_resp = supabase._get_http_client().get(snap_url, headers=headers, timeout=15)
    if snap_resp.status_code != 200:
        return jsonify({'snapshots': [], 'has_live': False, 'error': f'HTTP {snap_resp.status_code}'}), 200

    all_snaps = snap_resp.json()
    if not all_snaps:
        return jsonify({'snapshots': [], 'has_live': False}), 200

    kickoff_utc = fixture.get('kickoff_utc', '') if fixture else ''
    kickoff_dt = None
    if kickoff_utc:
        try:
            ko = kickoff_utc.replace('Z', '+00:00')
            kickoff_dt = datetime.fromisoformat(ko)
        except Exception:
            kickoff_dt = None

    periods = {}
    for s in all_snaps:
        ts = s.get('snapshot_at', '')
        market = s.get('market', '')
        sel = s.get('selection', '')
        key = ts

        snap_minute = s.get('minute', '')
        snap_score = s.get('score', '')
        if not snap_minute:
            continue

        if key not in periods:
            periods[key] = {
                'snapshot_at': ts,
                'minute': snap_minute,
                'score': snap_score,
                '1x2': {},
                'ou': {},
                'ou_lines': {},
                'ou_line': None,
            }

        if market == '1X2':
            periods[key]['1x2'][sel] = {
                'odds': s.get('odds'),
                'share': s.get('share'),
                'volume': s.get('volume'),
            }
        elif market == 'OU':
            line = s.get('ou_line', '')
            if line not in periods[key]['ou_lines']:
                periods[key]['ou_lines'][line] = {}
            periods[key]['ou_lines'][line][sel] = {
                'odds': s.get('odds'),
                'share': s.get('share'),
                'volume': s.get('volume'),
            }

    for p in periods.values():
        p.pop('ou_line', None)
        p.pop('ou', None)

    result = sorted(periods.values(), key=lambda x: x['snapshot_at'])

    return jsonify({'snapshots': result, 'total': len(result), 'kickoff_utc': kickoff_utc, 'has_live': True}), 200


@app.route('/api/live/match/history')
@license_required
def get_live_match_history():
    """Tek maçın 3dk periyot snapshot geçmişi"""
    match_hash = request.args.get('hash', '')
    if not match_hash:
        return jsonify({'error': 'hash parametresi gerekli'}), 400

    try:
        supabase = get_supabase_client()
        if not supabase or not supabase.is_available:
            return jsonify({'snapshots': [], 'error': 'Supabase bağlantısı yok'}), 200

        headers = supabase._headers()
        return _get_live_history_by_hash(supabase, headers, match_hash)

    except Exception as e:
        print(f"[API] /api/live/match/history hata: {e}")
        return jsonify({'snapshots': [], 'error': str(e)}), 200


@app.route('/health')
def health_check():
    return jsonify({'status': 'ok', 'ts': time.time()}), 200


@app.route('/api/status')
def get_status():
    """Get current status - scraping handled by Scraper Engine workflow"""
    mode = "server" if is_server_mode() else "client"
    
    last_data_update = db.get_last_data_update() if db.is_supabase_available else None
    last_data_update_tr = None
    if last_data_update:
        try:
            from core.timezone import format_turkey_time
            last_data_update_tr = format_turkey_time(last_data_update)
        except:
            last_data_update_tr = last_data_update
    
    return jsonify({
        'running': False,
        'auto_running': False,
        'last_result': None,
        'last_scrape_time': None,
        'last_scrape_time_tr': '--:--',
        'last_supabase_sync': None,
        'next_scrape_time': None,
        'interval_minutes': 9,
        'cookie_set': False,
        'supabase_connected': db.is_supabase_available,
        'mode': mode,
        'scraping_enabled': False,
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
    """Save PNG file for export"""
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
@license_required
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
@license_required
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
                    
                    huge_indices = set()
                    for j in range(len(big_money_snapshots) - 1):
                        if big_money_snapshots[j+1]['index'] - big_money_snapshots[j]['index'] == 1:
                            huge_indices.add(big_money_snapshots[j]['index'])
                            huge_indices.add(big_money_snapshots[j+1]['index'])
                    
                    alarm_history = []
                    for snap in big_money_snapshots:
                        alarm_history.append({
                            'incoming_money': snap['incoming'],
                            'trigger_at': snap.get('scraped_at', ''),
                            'selection_total': parse_volume(history[snap['index']].get(amount_key, '0')) if snap['index'] < len(history) else 0,
                            'is_huge': snap['index'] in huge_indices
                        })
                    
                    latest_snap = big_money_snapshots[-1]
                    latest_trigger = latest_snap.get('scraped_at', event_time)
                    
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
                        'trigger_at': latest_trigger,
                        'created_at': created_at,
                        'alarm_history': alarm_history
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

dropping_config = load_dropping_config()
dropping_alarms = []


FREE_MATCHES_CONFIG_FILE = 'free_matches_config.json'

def load_free_matches_config():
    # 1. Supabase free_matches tablosundan oku (birincil kaynak)
    try:
        _db = get_supabase_client()
        if _db and _db.is_available:
            import httpx as _httpx
            _h = {'apikey': _db.key, 'Authorization': f'Bearer {_db.key}'}
            fm_url = f"{_db.url}/rest/v1/free_matches?active=eq.true&select=match_id_hash,home_team,away_team,league,fixture_date&order=selected_at.asc"
            r = _httpx.get(fm_url, headers=_h, timeout=8)
            if r.status_code == 200:
                rows = r.json()
                hashes = [row['match_id_hash'] for row in rows]
                teams = [{'home': row.get('home_team', ''), 'away': row.get('away_team', ''), 'league': row.get('league', ''), 'date': str(row.get('fixture_date', '') or '')} for row in rows]
                # free_count için alarm_settings'den oku
                fc = 3
                try:
                    fc_url = f"{_db.url}/rest/v1/alarm_settings?alarm_type=eq.free_matches_config&select=config"
                    fc_r = _httpx.get(fc_url, headers=_h, timeout=5)
                    if fc_r.status_code == 200 and fc_r.json():
                        cfg = fc_r.json()[0].get('config') or {}
                        fc = int(cfg.get('free_count', 3))
                except Exception:
                    pass
                print(f"[FreeMatches] Loaded from free_matches table: {len(hashes)} maç seçili")
                return {'hashes': hashes, 'teams': teams, 'free_count': fc}
            elif r.status_code not in [404]:
                print(f"[FreeMatches] free_matches table error: HTTP {r.status_code}")
            # 404 = tablo yok, alarm_settings fallback'e geç
    except Exception as e:
        print(f"[FreeMatches] free_matches load error: {e}")
    # 2. alarm_settings fallback (eski yöntem / tablo yokken)
    try:
        _db = get_supabase_client()
        if _db and _db.is_available:
            import httpx as _httpx
            url = f"{_db.url}/rest/v1/alarm_settings?alarm_type=eq.free_matches_config&select=config"
            headers = {'apikey': _db.key, 'Authorization': f'Bearer {_db.key}'}
            r = _httpx.get(url, headers=headers, timeout=8)
            if r.status_code == 200:
                rows = r.json()
                if rows and rows[0].get('config'):
                    data = rows[0]['config']
                    print(f"[FreeMatches] Config loaded from alarm_settings: {len(data.get('hashes', []))} maç seçili")
                    return data
    except Exception as e:
        print(f"[FreeMatches] alarm_settings load error: {e}")
    # 3. Local dosya fallback
    try:
        if os.path.exists(FREE_MATCHES_CONFIG_FILE):
            with open(FREE_MATCHES_CONFIG_FILE, 'r') as f:
                data = json.load(f)
                print(f"[FreeMatches] Config loaded from file (fallback): {len(data.get('hashes', []))} maç seçili")
                return data
    except Exception as e:
        print(f"[FreeMatches] Config file load error: {e}")
    return {'hashes': [], 'teams': [], 'free_count': 3}

def save_free_matches_config(data):
    ok = False
    hashes = data.get('hashes', [])
    teams = data.get('teams', [])
    # 1. Supabase free_matches tablosuna yaz
    try:
        _db = get_supabase_client()
        if _db and _db.is_available:
            import httpx as _httpx
            _base_h = {
                'apikey': _db.key, 'Authorization': f'Bearer {_db.key}',
                'Content-Type': 'application/json'
            }
            # Önce tüm aktif satırları sil
            del_r = _httpx.delete(
                f"{_db.url}/rest/v1/free_matches?active=eq.true",
                headers=_base_h, timeout=8
            )
            if del_r.status_code in [200, 204]:
                # Yeni satırları ekle
                if hashes:
                    rows_to_insert = []
                    for i, h in enumerate(hashes):
                        team = teams[i] if i < len(teams) else {}
                        fixture_date = team.get('date', '') or None
                        if fixture_date and len(fixture_date) >= 10:
                            fixture_date = fixture_date[:10]  # YYYY-MM-DD
                        else:
                            fixture_date = None
                        rows_to_insert.append({
                            'match_id_hash': h,
                            'home_team': team.get('home', ''),
                            'away_team': team.get('away', ''),
                            'league': team.get('league', '') or None,
                            'fixture_date': fixture_date,
                            'active': True
                        })
                    ins_r = _httpx.post(
                        f"{_db.url}/rest/v1/free_matches",
                        headers={**_base_h, 'Prefer': 'return=minimal'},
                        json=rows_to_insert, timeout=10
                    )
                    if ins_r.status_code in [200, 201, 204]:
                        print(f"[FreeMatches] Saved {len(hashes)} matches to free_matches table")
                        ok = True
                    else:
                        print(f"[FreeMatches] free_matches INSERT error: HTTP {ins_r.status_code} - {ins_r.text[:200]}")
                else:
                    print(f"[FreeMatches] Cleared all free matches from table")
                    ok = True
            elif del_r.status_code in [404]:
                print(f"[FreeMatches] free_matches table not found, use alarm_settings")
            else:
                print(f"[FreeMatches] free_matches DELETE error: HTTP {del_r.status_code}")
    except Exception as e:
        print(f"[FreeMatches] free_matches save error: {e}")
    # 2. alarm_settings'e her zaman yaz (free_count + eski sistem uyumluluğu)
    try:
        _db = get_supabase_client()
        if _db and _db.is_available:
            import httpx as _httpx
            url = f"{_db.url}/rest/v1/alarm_settings?on_conflict=alarm_type"
            headers = {
                'apikey': _db.key, 'Authorization': f'Bearer {_db.key}',
                'Content-Type': 'application/json', 'Prefer': 'resolution=merge-duplicates,return=minimal'
            }
            payload = {'alarm_type': 'free_matches_config', 'enabled': True, 'config': data}
            r = _httpx.post(url, headers=headers, json=payload, timeout=10)
            if r.status_code in [200, 201, 204]:
                if not ok:
                    print(f"[FreeMatches] Saved to alarm_settings (fallback): {len(hashes)} maç")
                ok = True
    except Exception as e:
        print(f"[FreeMatches] alarm_settings save error: {e}")
    # 3. Local dosyaya da yaz (yedek)
    try:
        with open(FREE_MATCHES_CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        ok = ok or True
    except Exception as e:
        print(f"[FreeMatches] Config file save error: {e}")
    return ok

free_matches_config = load_free_matches_config()


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


_dropping_alarms_cache = {'data': None, 'ts': 0}
_DROPPING_ALARMS_CACHE_TTL = 90

@app.route('/api/dropping/alarms', methods=['GET'])
def get_dropping_alarms():
    """Get all Dropping Alert alarms - reads from Supabase first, fallback to local JSON only on error"""
    import time as _t
    now = _t.time()
    if _dropping_alarms_cache['data'] is not None and (now - _dropping_alarms_cache['ts']) < _DROPPING_ALARMS_CACHE_TTL:
        return jsonify(_dropping_alarms_cache['data'])
    supabase_alarms = get_dropping_alarms_from_supabase()
    if supabase_alarms is not None:
        _dropping_alarms_cache['data'] = supabase_alarms
        _dropping_alarms_cache['ts'] = now
        return jsonify(supabase_alarms)
    return jsonify(dropping_alarms)


@app.route('/api/dropping/delete', methods=['POST'])
def delete_dropping_alarms():
    """Delete all Dropping Alert alarms from both Supabase and local JSON"""
    global dropping_alarms
    try:
        dropping_alarms = []
        save_dropping_alarms_to_file(dropping_alarms)
        delete_alarms_from_supabase('dropping_alarms')
        _dropping_alarms_cache['data'] = None
        _dropping_alarms_cache['ts'] = 0
        print("[Dropping] All alarms deleted")
        return jsonify({'success': True})
    except Exception as e:
        print(f"[Dropping] Delete error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500




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
@license_required
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
@license_required
def get_all_alarms_batch():
    """
    Batch endpoint - Returns all 7 alarm types in a single request.
    Uses server-side cache to reduce response time from ~2s to <50ms.
    Triggers lazy app warmup if not started yet.
    
    Query params:
    - types: comma-separated list of alarm types to include (default: all)
      Example: ?types=sharp,bigmoney,mim
    - refresh: set to 'true' to force cache refresh
    """
    trigger_app_warmup()
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
    per_table_counts = []
    for alarm_type in types_to_fetch:
        fetch_func, fallback = alarm_fetchers[alarm_type]
        try:
            supabase_data = fetch_func()
            if supabase_data is not None:
                result[alarm_type] = supabase_data
                per_table_counts.append(f"{alarm_type}={len(supabase_data)}")
            else:
                result[alarm_type] = fallback
                per_table_counts.append(f"{alarm_type}=FALLBACK({len(fallback)})")
        except Exception as e:
            print(f"[Alarms/All] Error fetching {alarm_type}: {e}")
            result[alarm_type] = fallback
            per_table_counts.append(f"{alarm_type}=ERR")
    print(f"[Alarms/All] Per-table: {', '.join(per_table_counts)}")
    
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
@license_required
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
    
    if not match_found:
        try:
            import httpx as _httpx
            _client = get_supabase_client()
            if _client and _client.is_available:
                _fix_url = f"{_client._rest_url('fixtures')}?match_id_hash=eq.{match_id}&select=*&limit=1"
                _fix_resp = _httpx.get(_fix_url, headers=_client._headers(), timeout=10)
                if _fix_resp.status_code == 200:
                    _fix_data = _fix_resp.json()
                    if _fix_data:
                        _f = _fix_data[0]
                        match_found = True
                        match_metadata = {
                            'match_id': match_id,
                            'internal_id': _f.get('internal_id'),
                            'home': _f.get('home_team', ''),
                            'away': _f.get('away_team', ''),
                            'league': _f.get('league', ''),
                            'kickoff_utc': _f.get('kickoff_utc', ''),
                            'fixture_date': _f.get('fixture_date', ''),
                            'source': 'fixture_table'
                        }
                        print(f"[MatchSnapshot] Fixture found: {match_metadata['home']} vs {match_metadata['away']}")
        except Exception as e:
            print(f"[MatchSnapshot] Fixture lookup error: {e}")
    
    if not match_found:
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
        if rpc_data and isinstance(rpc_data, dict) and rpc_data.get('moneyway'):
            result['moneyway'] = rpc_data.get('moneyway', [])
        else:
            try:
                import httpx as _httpx
                client = get_supabase_client()
                if client and client.is_available:
                    url = f"{client._rest_url('moneyway_snapshots')}?match_id_hash=eq.{match_id}&select=market,selection,odds,volume,share,scraped_at_utc&order=scraped_at_utc.asc"
                    resp = _httpx.get(url, headers=client._headers(), timeout=15)
                    if resp.status_code == 200:
                        result['moneyway'] = resp.json()
                        print(f"[MatchSnapshot] Moneyway direct: {len(result['moneyway'])} rows for {match_id}")
                    else:
                        print(f"[MatchSnapshot] Moneyway direct error: HTTP {resp.status_code}")
                        result['moneyway'] = []
                else:
                    result['moneyway'] = []
            except Exception as e:
                print(f"[MatchSnapshot] Moneyway direct error: {e}")
                result['moneyway'] = []
    
    if 'dropping_odds' in sections_to_include:
        if rpc_data and isinstance(rpc_data, dict) and rpc_data.get('dropping_odds'):
            result['dropping_odds'] = rpc_data.get('dropping_odds', [])
        else:
            try:
                import httpx as _httpx
                from urllib.parse import quote
                client = get_supabase_client()
                dropping_data = []
                if client and client.is_available and match_metadata and match_metadata.get('home'):
                    home = match_metadata.get('home', '')
                    away = match_metadata.get('away', '')
                    
                    drop_tables = {
                        'dropping_1x2_hist': '1X2',
                        'dropping_ou25_hist': 'OU25',
                        'dropping_btts_hist': 'BTTS',
                    }
                    
                    for table_name, market in drop_tables.items():
                        try:
                            url = f"{client._rest_url(table_name)}?Home=eq.{quote(home)}&Away=eq.{quote(away)}&select=*&order=ScrapedAt.asc"
                            dr_resp = _httpx.get(url, headers=client._headers(), timeout=15)
                            if dr_resp.status_code == 200:
                                rows = dr_resp.json()
                                for row in rows:
                                    row['market'] = market
                                    row['scraped_at_utc'] = row.get('ScrapedAt', '')
                                dropping_data.extend(rows)
                        except Exception as te:
                            print(f"[MatchSnapshot] Dropping {table_name} error: {te}")
                    
                    print(f"[MatchSnapshot] Dropping direct: {len(dropping_data)} rows for {match_id}")
                
                result['dropping_odds'] = dropping_data
            except Exception as e:
                print(f"[MatchSnapshot] Dropping direct error: {e}")
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
                    'interval_minutes': state.get('interval_minutes', 9),
                    'last_scrape': state.get('last_scrape'),
                    'next_scrape': state.get('next_scrape'),
                    'last_rows': state.get('last_rows', 0),
                    'last_alarm_count': state.get('last_alarm_count', 0),
                    'status_text': state.get('status', 'Bekliyor...')
                })
            except:
                pass
        
        return jsonify({
            'status': 'ok',
            'running': False,
            'is_scraping': False,
            'is_disabled': True,
            'interval_minutes': 9,
            'last_scrape': None,
            'next_scrape': None,
            'last_rows': 0,
            'last_alarm_count': 0,
            'status_text': 'Scraper Engine workflow aktif'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e), 'running': False})


@app.route('/scraper/control', methods=['POST'])
def scraper_control():
    """Scraper başlat/durdur kontrolü - Sadece Desktop (EXE) modu"""
    try:
        data = request.get_json() or {}
        action = data.get('action', '')
        
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
        
        return jsonify({'status': 'disabled', 'message': 'Scraping handled by Scraper Engine workflow'})
    
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
        
        return jsonify({'status': 'disabled', 'message': 'Scraping handled by Scraper Engine workflow'})
    
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
            <span class="badge">Interval: <span id="intervalValue">9</span> dk</span>
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
                    document.getElementById('intervalValue').textContent = data.interval_minutes || 9;
                    document.getElementById('lastRows').textContent = data.last_rows || '-';
                });
        }
        updateStatus();
        setInterval(updateStatus, 60000);
        
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
    """Admin Panel - requires login, triggers lazy warmup on first visit"""
    if not session.get('admin_authenticated'):
        return redirect('/admin/login')
    trigger_admin_warmup()
    return render_template('admin.html')


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin Login Page"""
    if request.method == 'POST':
        submitted_url = request.form.get('supabase_url', '').strip()
        submitted_key = request.form.get('supabase_key', '').strip()
        real_url = os.environ.get('SUPABASE_URL', '')
        real_key = os.environ.get('SUPABASE_ANON_KEY', '')
        if submitted_url == real_url and submitted_key == real_key and real_url and real_key:
            session['admin_authenticated'] = True
            return redirect('/admin')
        else:
            return render_template('admin_login.html', error='Geçersiz bilgiler. Lütfen tekrar deneyin.')
    return render_template('admin_login.html', error=None)

@app.route('/admin/logout')
def admin_logout():
    """Admin Logout"""
    session.pop('admin_authenticated', None)
    return redirect('/admin/login')


_analyses_cache = {'analysis': {'data': None, 'ts': 0}, 'moves': {'data': None, 'ts': 0}}
_ANALYSES_CACHE_TTL = 60

@app.route('/api/analyses', methods=['GET'])
def get_analyses():
    """Get analyses list - PRO only (admin bypass with referer check)"""
    import time as _time
    referer = request.headers.get('Referer', '')
    is_admin = request.args.get('admin') == 'true' and '/admin' in referer
    if is_admin:
        category = request.args.get('category', None)
        data = db.get_analyses(category)
        return jsonify(data)
    license_key = request.headers.get('X-License-Key') or request.args.get('license_key')
    if license_key:
        lic = license_select('licenses', 'plan,status,expires_at', {'key': license_key})
        if lic:
            license_data = lic[0]
            if license_data.get('status') == 'revoked':
                return jsonify({'error': 'LICENSE_REVOKED', 'message': 'Bu lisans iptal edilmis.'}), 403
            expires_at = license_data.get('expires_at')
            if expires_at:
                try:
                    from datetime import datetime
                    exp_date = datetime.fromisoformat(expires_at.replace('Z', '+00:00').replace('+00:00', ''))
                    if exp_date < datetime.utcnow():
                        return jsonify({'error': 'LICENSE_EXPIRED', 'message': 'Lisans suresi dolmus.'}), 403
                except:
                    pass
            plan = license_data.get('plan') or 'core'
            category = request.args.get('category', None)
            if plan != 'pro' and category != 'moves':
                return jsonify({'error': 'PRO_REQUIRED', 'message': 'Bu ozellik PRO uyelikte aktif.'}), 403
        else:
            return jsonify({'error': 'INVALID_KEY'}), 401
    else:
        category = request.args.get('category', None)
        if category != 'moves':
            return jsonify({'error': 'PRO_REQUIRED', 'message': 'Bu ozellik PRO uyelikte aktif.'}), 403
    
    category = request.args.get('category', None)
    cache_key = category or 'all'
    now = _time.time()
    if cache_key in _analyses_cache and _analyses_cache[cache_key]['data'] is not None and (now - _analyses_cache[cache_key]['ts']) < _ANALYSES_CACHE_TTL:
        return jsonify(_analyses_cache[cache_key]['data'])
    data = db.get_analyses(category)
    _analyses_cache[cache_key] = {'data': data, 'ts': now}
    return jsonify(data)

@app.route('/api/admin/matches-for-dropdown')
def admin_matches_for_dropdown():
    """Return match list for admin analysis dropdown (admin session required)"""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401
    try:
        matches_raw = db.get_all_matches_with_latest('moneyway_1x2')
        result = []
        for m in matches_raw:
            home = m.get('home_team', '')
            away = m.get('away_team', '')
            league = m.get('league', '')
            date = m.get('date', '')
            match_hash = m.get('match_id_hash', generate_match_id(home, away, league, date))
            result.append({
                'home_team': home,
                'away_team': away,
                'league': league,
                'date': date,
                'match_id': match_hash
            })
        return jsonify({'matches': result, 'total': len(result)})
    except Exception as e:
        print(f"[Admin] matches-for-dropdown error: {e}")
        return jsonify({'matches': [], 'total': 0})


@app.route('/api/admin/free-matches-config', methods=['GET'])
def get_free_matches_config():
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401
    global free_matches_config
    return jsonify(free_matches_config)


@app.route('/api/admin/free-matches-config', methods=['POST'])
def set_free_matches_config():
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401
    global free_matches_config
    data = request.get_json() or {}
    hashes = data.get('hashes', [])[:5]
    teams = data.get('teams', [])[:5]
    try:
        free_count = min(max(int(data.get('free_count', 3)), 0), 5)
    except (TypeError, ValueError):
        free_count = 3
    config = {'hashes': hashes, 'teams': teams, 'free_count': free_count}
    if save_free_matches_config(config):
        free_matches_config = config
        return jsonify({'success': True, 'count': len(hashes), 'free_count': free_count})
    return jsonify({'success': False, 'error': 'Kayıt hatası'}), 500


@app.route('/api/analyses', methods=['POST'])
def create_analysis():
    """Create new analysis with optional image upload"""
    title = request.form.get('title', '')
    content = request.form.get('content', '')
    category = request.form.get('category', 'analysis')
    match_id_hash = request.form.get('match_id_hash', None) or None
    odds = request.form.get('odds', None) or None
    confidence_raw = request.form.get('confidence', None)
    confidence = None
    if confidence_raw:
        try:
            confidence = round(max(1, min(10, float(confidence_raw))) * 2) / 2
        except (ValueError, TypeError):
            pass
    
    if not title or not content:
        return jsonify({'status': 'error', 'message': 'Başlık ve içerik zorunludur'}), 400
    
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    MAX_FILE_SIZE = 5 * 1024 * 1024
    
    image_url = None
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename:
            import uuid
            ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'png'
            if ext not in ALLOWED_EXTENSIONS:
                return jsonify({'status': 'error', 'message': 'Sadece resim dosyaları yüklenebilir (png, jpg, gif, webp)'}), 400
            file_data = file.read()
            if len(file_data) > MAX_FILE_SIZE:
                return jsonify({'status': 'error', 'message': 'Dosya boyutu 5MB\'dan küçük olmalıdır'}), 400
            file_path = f"analyses/{uuid.uuid4().hex}.{ext}"
            content_type = file.content_type or 'image/png'
            image_url = db.upload_to_storage('smartxflow', file_path, file_data, content_type)
    
    preference = request.form.get('preference', None) or None
    analyst_id_raw = request.form.get('analyst_id', None)
    analyst_id = None
    if analyst_id_raw:
        try:
            analyst_id = int(analyst_id_raw)
        except (ValueError, TypeError):
            pass

    result = db.create_analysis(title, content, image_url, category, match_id_hash, odds, confidence, analyst_id, preference=preference)
    if result:
        for k in _analyses_cache:
            _analyses_cache[k] = {'data': None, 'ts': 0}
        _invalidate_analysts_cache()
        _match_hashes_cache['data'] = None
        _match_hashes_cache['ts'] = 0
        return jsonify({'status': 'ok', 'data': result})
    return jsonify({'status': 'error', 'message': 'Analiz oluşturulamadı'}), 500

@app.route('/api/analyses/<int:analysis_id>', methods=['PUT'])
def update_analysis_endpoint(analysis_id):
    """Update analysis"""
    title = request.form.get('title', '')
    content = request.form.get('content', '')
    image_url = None
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename:
            ext = file.filename.rsplit('.', 1)[-1].lower()
            if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                file_path = f"analyses/{uuid.uuid4().hex}.{ext}"
                image_url = db.upload_file(file_path, file.read(), file.content_type)
    match_id_hash = request.form.get('match_id_hash', None) or None
    odds = request.form.get('odds', None) or None
    confidence_raw = request.form.get('confidence', None)
    confidence = None
    if confidence_raw:
        try:
            confidence = round(max(1, min(10, float(confidence_raw))) * 2) / 2
        except (ValueError, TypeError):
            pass
    preference = request.form.get('preference', None) or None
    analyst_id_raw = request.form.get('analyst_id', None)
    analyst_id = None
    if analyst_id_raw:
        try:
            analyst_id = int(analyst_id_raw)
        except (ValueError, TypeError):
            pass
    success = db.update_analysis(analysis_id, title, content, image_url, match_id_hash, odds, confidence, analyst_id, preference=preference)
    if success:
        for k in _analyses_cache:
            _analyses_cache[k] = {'data': None, 'ts': 0}
        _invalidate_analysts_cache()
        _match_hashes_cache['data'] = None
        _match_hashes_cache['ts'] = 0
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 500

@app.route('/api/analyses/<int:analysis_id>/result', methods=['PUT'])
def update_analysis_result_endpoint(analysis_id):
    """Update analysis result (won/lost/push/void)"""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401
    data = request.get_json(silent=True) or {}
    result_val = data.get('result', '')
    if result_val not in ('won', 'lost', 'push', 'void', ''):
        return jsonify({'status': 'error', 'message': 'Geçersiz sonuç'}), 400
    result_note = data.get('result_note', None)
    if result_val == '':
        result_val = None
    success = db.update_analysis_result(analysis_id, result_val, result_note)
    if success:
        for k in _analyses_cache:
            _analyses_cache[k] = {'data': None, 'ts': 0}
        _invalidate_analysts_cache()
        _match_hashes_cache['data'] = None
        _match_hashes_cache['ts'] = 0
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 500

_match_hashes_cache = {'data': None, 'ts': 0}
_MATCH_HASHES_CACHE_TTL = 120

@app.route('/api/analyses/match-hashes')
def get_analysis_match_hashes():
    """Return list of match_id_hash values that have analyses + active count"""
    import time as _time
    now = _time.time()
    if _match_hashes_cache['data'] is not None and (now - _match_hashes_cache['ts']) < _MATCH_HASHES_CACHE_TTL:
        return jsonify(_match_hashes_cache['data'])
    try:
        analyses = db.get_analyses(category='analysis')
        hashes = list(set(a.get('match_id_hash') for a in analyses if a.get('match_id_hash')))
        active_count = sum(1 for a in analyses if not a.get('result'))
        result = {'hashes': hashes, 'active_count': active_count}
        _match_hashes_cache['data'] = result
        _match_hashes_cache['ts'] = now
        return jsonify(result)
    except Exception as e:
        print(f"[API] match-hashes error: {e}")
        return jsonify({'hashes': [], 'active_count': 0})

@app.route('/api/analyses/<int:analysis_id>', methods=['DELETE'])
def delete_analysis_endpoint(analysis_id):
    """Delete analysis"""
    success = db.delete_analysis(analysis_id)
    if success:
        for k in _analyses_cache:
            _analyses_cache[k] = {'data': None, 'ts': 0}
        _invalidate_analysts_cache()
        _match_hashes_cache['data'] = None
        _match_hashes_cache['ts'] = 0
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 500

_analysts_cache = {'data': None, 'ts': 0}
_ANALYSTS_CACHE_TTL = 120

def _invalidate_analysts_cache():
    _analysts_cache['data'] = None
    _analysts_cache['ts'] = 0

@app.route('/api/analysts', methods=['GET'])
def get_analysts_endpoint():
    """Get all analysts with stats"""
    import time as _time
    active_only = request.args.get('active', 'false') == 'true'
    cache_key_suffix = '_active' if active_only else '_all'
    now = _time.time()
    cached = _analysts_cache.get('data')
    cached_suffix = _analysts_cache.get('suffix')
    if cached is not None and cached_suffix == cache_key_suffix and (now - _analysts_cache['ts']) < _ANALYSTS_CACHE_TTL:
        return jsonify(cached)
    analysts = db.get_analysts(active_only=active_only)
    stats = db.get_analyst_stats()
    for a in analysts:
        aid = a.get('id')
        s = stats.get(aid, {})
        a['stats'] = {
            'total': s.get('total', 0),
            'won': s.get('won', 0),
            'lost': s.get('lost', 0),
            'push': s.get('push', 0),
            'void': s.get('void', 0),
            'pending': s.get('pending', 0),
            'success_pct': s.get('success_pct', 0.0),
            'avg_odds': s.get('avg_odds', 0.0),
            'roi_pct': s.get('roi_pct', 0.0),
            'net_profit': s.get('net_profit', 0.0)
        }
    _analysts_cache['data'] = analysts
    _analysts_cache['suffix'] = cache_key_suffix
    _analysts_cache['ts'] = now
    return jsonify(analysts)


_underdog_result_col_migrated = False


def _build_unified_underdog_signals():
    """App ve admin panelinin AYNI underdog sinyal listesini görmesi için ortak helper.

    1. DB'den tüm kayıtları çek (sinyal_engine + app tarafından kaydedilmiş)
    2. Anlık cache'den live sinyalleri hesapla
    3. (home, away, code) bazlı merge — date format farklılığını tolere eder
    4. Volume >= 800 filtresi (sinyal_engine.py ile senkron)
    5. (home, away, code) bazlı dedup — en yüksek volume'u tut
    """
    def _pv(v):
        try:
            return float(str(v).replace('£', '').replace(',', '').replace(' ', '').strip()) if v else 0.0
        except Exception:
            return 0.0

    odds_threshold = 2.90
    # PCT eşiği hacime göre kademelenir (sinyal_engine.py ile senkron)
    # vol >= 5000 → %50, vol 800-5000 → %55

    db_signals = _fetch_all_underdog_signals()

    matches_data = _server_matches_cache.get('moneyway_1x2_all') or _server_matches_cache.get('moneyway_1x2') or []
    live_signals = []
    for m in matches_data:
        odds_obj = m.get('odds') or {}
        home = m.get('home_team', '')
        away = m.get('away_team', '')
        league = m.get('league', '')
        date = m.get('date', '')
        volume = odds_obj.get('Volume', '')
        vol_val = _pv(volume)
        if vol_val < 800:
            continue
        required_pct = 50.0 if vol_val >= 5000 else 55.0
        for code, label, raw_odds, raw_pct, raw_amt in [
            ('1', 'Ev Sahibi', odds_obj.get('Odds1', '-'), odds_obj.get('Pct1', ''), odds_obj.get('Amt1', '')),
            ('2', 'Deplasman', odds_obj.get('Odds2', '-'), odds_obj.get('Pct2', ''), odds_obj.get('Amt2', '')),
        ]:
            try:
                odds_val = float(str(raw_odds).replace(',', '.')) if raw_odds and raw_odds != '-' else 0.0
            except Exception:
                odds_val = 0.0
            try:
                pct_val = float(str(raw_pct).replace('%', '').strip()) if raw_pct else 0.0
            except Exception:
                pct_val = 0.0
            if odds_val >= odds_threshold and pct_val >= required_pct:
                live_signals.append({
                    'match_key': f"{home}|{away}|{date}",
                    'home_team': home, 'away_team': away, 'league': league,
                    'date': date, 'match_date': date,
                    'selection_code': code, 'selection_label': label,
                    'odds': str(raw_odds), 'pct': str(raw_pct), 'amt': str(raw_amt),
                    'volume': volume, 'current_odds': '', 'current_pct': '',
                    'current_amt': '', 'current_volume': '', 'last_updated_at': '',
                    'score': '', 'result': '',
                })

    db_hak = {(s.get('home_team', ''), s.get('away_team', ''), s.get('selection_code', '')) for s in db_signals}
    all_signals = list(db_signals)
    for ls in live_signals:
        hak = (ls['home_team'], ls['away_team'], ls['selection_code'])
        if hak not in db_hak:
            all_signals.append(ls)
            db_hak.add(hak)

    all_signals = [s for s in all_signals if _pv(s.get('volume', '')) >= 800]

    seen = {}
    for s in all_signals:
        key = (s.get('home_team', ''), s.get('away_team', ''), s.get('selection_code', ''))
        if key not in seen:
            seen[key] = dict(s)
        else:
            ex = seen[key]
            s_has_cur = bool(s.get('last_updated_at'))
            ex_has_cur = bool(ex.get('last_updated_at'))
            if s_has_cur and not ex_has_cur:
                ex['current_odds'] = s.get('current_odds') or ex.get('current_odds') or ''
                ex['current_pct'] = s.get('current_pct') or ex.get('current_pct') or ''
                ex['current_amt'] = s.get('current_amt') or ex.get('current_amt') or ''
                ex['current_volume'] = s.get('current_volume') or ex.get('current_volume') or ''
                ex['last_updated_at'] = s.get('last_updated_at') or ''
            elif _pv(s.get('volume', '')) > _pv(ex.get('volume', '')):
                new_s = dict(s)
                if not s_has_cur and ex_has_cur:
                    new_s['current_odds'] = ex.get('current_odds') or ''
                    new_s['current_pct'] = ex.get('current_pct') or ''
                    new_s['current_amt'] = ex.get('current_amt') or ''
                    new_s['current_volume'] = ex.get('current_volume') or ''
                    new_s['last_updated_at'] = ex.get('last_updated_at') or ''
                seen[key] = new_s

    # Cache'den anlık veri ile current_* doldur ve is_stale hesapla
    cache_lookup = {}
    for m in matches_data:
        h = (m.get('home_team', '') or '').lower().strip()
        a = (m.get('away_team', '') or '').lower().strip()
        odds_obj = m.get('odds') or {}
        for code, raw_pct, raw_odds, raw_amt in [
            ('1', odds_obj.get('Pct1', ''), odds_obj.get('Odds1', ''), odds_obj.get('Amt1', '')),
            ('2', odds_obj.get('Pct2', ''), odds_obj.get('Odds2', ''), odds_obj.get('Amt2', '')),
        ]:
            if h and a:
                cache_lookup[(h, a, code)] = {
                    'current_pct': str(raw_pct) if raw_pct else '',
                    'current_odds': str(raw_odds) if raw_odds and raw_odds != '-' else '',
                    'current_amt': str(raw_amt) if raw_amt else '',
                    'current_volume': str(odds_obj.get('Volume', '')) if odds_obj.get('Volume') else '',
                }

    result = []
    for s in seen.values():
        sd = dict(s)
        h = (sd.get('home_team', '') or '').lower().strip()
        a = (sd.get('away_team', '') or '').lower().strip()
        code = sd.get('selection_code', '')
        cur = cache_lookup.get((h, a, code))
        if cur:
            if not sd.get('current_pct'):  sd['current_pct']    = cur['current_pct']
            if not sd.get('current_odds'): sd['current_odds']   = cur['current_odds']
            if not sd.get('current_amt'):  sd['current_amt']    = cur['current_amt']
            if not sd.get('current_volume'): sd['current_volume'] = cur['current_volume']
        # is_stale: sinyal anında tetiklendi ama şu an eşiğin altına düştü
        is_stale = False
        cur_pct_raw = sd.get('current_pct', '')
        if cur_pct_raw and not sd.get('score'):  # bitmemiş maç + current_pct var
            try:
                cur_pct_val = float(str(cur_pct_raw).replace('%', '').strip())
                cur_vol = _pv(sd.get('current_volume', '') or sd.get('volume', ''))
                req_pct = 50.0 if cur_vol >= 5000 else 55.0
                is_stale = cur_pct_val < req_pct
            except Exception:
                pass
        sd['is_stale'] = is_stale
        result.append(sd)
    return result


@app.route('/api/underdog-pressure', methods=['GET'])
@license_required
def underdog_pressure_endpoint():
    """Return matches where an underdog (odds >= 2.90) attracts >= 50% of money.
    Current live signals are saved to DB; all historical signals are returned."""
    global _underdog_result_col_migrated
    if not _underdog_result_col_migrated:
        _underdog_result_col_migrated = True
        try:
            _ensure_underdog_result_column()
        except Exception:
            pass
    from datetime import date as _date
    import re as _re

    # Canlı sinyalleri DB'ye kaydet
    matches_data = _server_matches_cache.get('moneyway_1x2_all') or _server_matches_cache.get('moneyway_1x2') or []
    live_signals_to_save = []
    for m in matches_data:
        odds_obj = m.get('odds') or {}
        home = m.get('home_team', '')
        away = m.get('away_team', '')
        league = m.get('league', '')
        date = m.get('date', '')
        volume = odds_obj.get('Volume', '')
        try:
            volume_val = float(str(volume).replace('£', '').replace(',', '').replace(' ', '').strip()) if volume else 0.0
        except (ValueError, TypeError):
            volume_val = 0.0
        if volume_val < 800:
            continue
        # Hacim kademesine göre pct eşiği (sinyal_engine.py ile senkron)
        required_pct = 50.0 if volume_val >= 5000 else 55.0
        for code, label, raw_odds, raw_pct, raw_amt in [
            ('1', 'Ev Sahibi', odds_obj.get('Odds1', '-'), odds_obj.get('Pct1', ''), odds_obj.get('Amt1', '')),
            ('2', 'Deplasman', odds_obj.get('Odds2', '-'), odds_obj.get('Pct2', ''), odds_obj.get('Amt2', '')),
        ]:
            try:
                odds_val = float(str(raw_odds).replace(',', '.')) if raw_odds and raw_odds != '-' else 0.0
            except (ValueError, TypeError):
                odds_val = 0.0
            try:
                pct_val = float(str(raw_pct).replace('%', '').strip()) if raw_pct else 0.0
            except (ValueError, TypeError):
                pct_val = 0.0
            if odds_val >= 2.90 and pct_val >= required_pct:
                live_signals_to_save.append({
                    'home_team': home, 'away_team': away, 'league': league, 'date': date,
                    'selection_code': code, 'selection_label': label,
                    'odds': raw_odds, 'pct': raw_pct, 'amt': raw_amt, 'volume': volume,
                })

    if live_signals_to_save:
        try:
            _save_underdog_signals(live_signals_to_save)
        except Exception as e:
            print(f"[UnderdogPressure] save error: {e}")

    try:
        _update_underdog_signal_scores()
    except Exception as e:
        print(f"[UnderdogPressure] score update error: {e}")

    # Ortak helper — admin ile aynı liste
    all_signals = _build_unified_underdog_signals()

    today_str = _date.today().strftime('%Y-%m-%d')

    def _is_today_or_future(date_val):
        if not date_val:
            return True
        try:
            dv = str(date_val)
            if len(dv) >= 10 and dv[4] == '-':
                return dv[:10] >= today_str
            m2 = _re.search(r'(\d{2})\.(\w{3})', dv)
            if m2:
                months = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
                day = int(m2.group(1)); mon = months.get(m2.group(2), 0)
                from datetime import date as _d2
                yr = _d2.today().year
                try:
                    d_obj = _d2(yr, mon, day)
                    return d_obj >= _d2.today()
                except Exception:
                    pass
        except Exception:
            pass
        return True

    active_signals = [s for s in all_signals if _is_today_or_future(s.get('date'))]

    avg_odds = 0.0
    avg_pct = 0.0
    if active_signals:
        odds_list = []
        pct_list = []
        for s in active_signals:
            try:
                odds_list.append(float(str(s['odds']).replace(',', '.')))
            except Exception:
                pass
            try:
                pct_list.append(float(str(s['pct']).replace('%', '').strip()))
            except Exception:
                pass
        if odds_list:
            avg_odds = round(sum(odds_list) / len(odds_list), 2)
        if pct_list:
            avg_pct = round(sum(pct_list) / len(pct_list), 1)

    return jsonify({
        'signals': all_signals,
        'count': len(active_signals),
        'avg_odds': avg_odds,
        'avg_pct': avg_pct,
    })


def _normalize_match_date(date_str):
    """Betwatch tarih formatını ('10.Apr 14:00:00') ISO datetime'a çevirir ('2026-04-10T14:00').
    Zaten ISO formatta olanlar (YYYY-MM-DD...) değiştirilmeden döner.
    """
    if not date_str:
        return ''
    s = str(date_str)
    if s[:4].isdigit() and len(s) >= 10:
        return s
    import re as _re
    from datetime import date as _d
    m = _re.search(r'(\d{2})\.(\w{3})', s)
    if m:
        months = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5,
                  'Jun': 6, 'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10,
                  'Nov': 11, 'Dec': 12}
        day = int(m.group(1))
        mon = months.get(m.group(2).capitalize(), 0)
        if mon:
            iso_date = _d(_d.today().year, mon, day).isoformat()
            t = _re.search(r'(\d{2}):(\d{2})(?::\d{2})?', s)
            if t:
                return f"{iso_date}T{t.group(1)}:{t.group(2)}"
            return iso_date
    return s


def _fetch_all_confirmed_money_signals():
    """confirmed_money_signals tablosundan en son 1000 sinyali çek (created_at desc)."""
    try:
        supabase = get_supabase_client()
        if not supabase or not supabase.is_available:
            return []
        headers = supabase._headers()
        url = (
            f"{supabase._rest_url('confirmed_money_signals')}"
            f"?select=*&order=created_at.desc,home_team.asc&limit=1000"
        )
        resp = supabase._get_http_client().get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            rows = resp.json()
            _backfill_match_date_times(rows, 'confirmed_money_signals')
            result = []
            for r in rows:
                result.append({
                    'id': r.get('id'),
                    'match_key': r.get('match_key', ''),
                    'home_team': r.get('home_team', ''),
                    'away_team': r.get('away_team', ''),
                    'league': r.get('league', ''),
                    'date': _normalize_match_date(r.get('match_date', '')),
                    'match_date': _normalize_match_date(r.get('match_date', '')),
                    'selection_code': r.get('selection_code', ''),
                    'selection_label': r.get('selection_label', ''),
                    'odds_16h': r.get('odds_16h', ''),
                    'odds_now': r.get('odds_now', ''),
                    'current_odds': r.get('current_odds') or '',
                    'pct_now': r.get('pct_now', ''),
                    'current_pct': r.get('current_pct') or '',
                    'volume_now': r.get('volume_now', ''),
                    'current_volume': r.get('current_volume') or '',
                    'odds_drop_pct': r.get('odds_drop_pct') or '',
                    'last_updated_at': r.get('last_updated_at') or '',
                    'created_at': r.get('created_at') or '',
                    'result': r.get('result') or '',
                })
            return result
        return []
    except Exception as e:
        print(f"[ConfirmedMoneySignals] fetch error: {e}")
        return []


def _fetch_all_confirmed_money_v2_signals():
    """confirmed_money_v2_signals tablosundan en son 1000 sinyali çek (created_at desc)."""
    try:
        supabase = get_supabase_client()
        if not supabase or not supabase.is_available:
            return []
        headers = supabase._headers()
        url = (
            f"{supabase._rest_url('confirmed_money_v2_signals')}"
            f"?select=*&order=created_at.desc,home_team.asc&limit=1000"
        )
        resp = supabase._get_http_client().get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            rows = resp.json()
            _backfill_match_date_times(rows, 'confirmed_money_v2_signals')
            result = []
            for r in rows:
                result.append({
                    'id': r.get('id'),
                    'match_key': r.get('match_key', ''),
                    'home_team': r.get('home_team', ''),
                    'away_team': r.get('away_team', ''),
                    'league': r.get('league', ''),
                    'date': _normalize_match_date(r.get('match_date', '')),
                    'match_date': _normalize_match_date(r.get('match_date', '')),
                    'selection_code': r.get('selection_code', ''),
                    'selection_label': r.get('selection_label', ''),
                    'odds_16h': r.get('odds_16h', ''),
                    'odds_now': r.get('odds_now', ''),
                    'current_odds': r.get('current_odds') or '',
                    'pct_now': r.get('pct_now', ''),
                    'current_pct': r.get('current_pct') or '',
                    'volume_now': r.get('volume_now', ''),
                    'current_volume': r.get('current_volume') or '',
                    'odds_drop_pct': r.get('odds_drop_pct') or '',
                    'last_updated_at': r.get('last_updated_at') or '',
                    'created_at': r.get('created_at') or '',
                    'result': r.get('result') or '',
                })
            return result
        return []
    except Exception as e:
        print(f"[ConfirmedMoneyV2Signals] fetch error: {e}")
        return []


def _cm_odds_reversed(s):
    """True if current_odds > odds_now — signal is no longer valid (odds bounced back)."""
    try:
        return float(str(s.get('current_odds') or '').strip()) > float(str(s.get('odds_now') or '').strip())
    except Exception:
        return False


def _cm_in_odds_range(s):
    """True if odds_now is within the allowed CM selection range [1.35, 2.20].
    Returns False for missing or malformed odds_now values."""
    try:
        v = float(str(s.get('odds_now') or '').strip())
        return 1.35 <= v <= 2.20
    except Exception:
        return False


def _cm_still_valid(s):
    """Endpoint güvenlik filtresi: ilk snap (odds_16h) ile current_odds arasındaki
    düşüş CM_ODDS_DROP_PCT (%4) eşiğinin altındaysa sinyal artık geçersizdir.
    Veri eksikse sinyali göster (fail-open)."""
    try:
        ref = float(str(s.get('odds_16h') or '').strip())
        cur = float(str(s.get('current_odds') or '').strip())
        if ref <= 0 or cur <= 0:
            return True
        drop_pct = (ref - cur) / ref
        return drop_pct >= CM_ODDS_DROP_PCT
    except Exception:
        return True


def _cm_v2_in_odds_range(s):
    """True if odds_now is within the allowed CMv2 selection range [1.55, 2.20]."""
    try:
        v = float(str(s.get('odds_now') or '').strip())
        return 1.55 <= v <= 2.20
    except Exception:
        return False


CMV2_ODDS_DROP_PCT_LOCAL = 0.07  # %7 düşüş eşiği — sinyal_engine.py ile aynı
EML_PCT_THRESHOLD_LOCAL = 85.0   # %85 yüzde eşiği — sinyal_engine.py ile aynı


def _cm_v2_still_valid(s):
    """CMv2 güvenlik filtresi: ilk snap (odds_16h) ile current_odds arasındaki
    düşüş CMV2_ODDS_DROP_PCT (%7) eşiğinin altındaysa sinyal artık geçersizdir."""
    try:
        ref = float(str(s.get('odds_16h') or '').strip())
        cur = float(str(s.get('current_odds') or '').strip())
        if ref <= 0 or cur <= 0:
            return True
        drop_pct = (ref - cur) / ref
        return drop_pct >= CMV2_ODDS_DROP_PCT_LOCAL
    except Exception:
        return True


@app.route('/api/confirmed-money', methods=['GET'])
@license_required
def confirmed_money_endpoint():
    """Confirmed Money sinyallerini döndür (90 günlük, DB'den). 60s server cache."""
    global _cm_signals_cache, _cm_signals_cache_time
    from datetime import date as _date

    def _is_today_or_future(d):
        if not d:
            return False
        try:
            return str(d) >= str(_date.today())
        except Exception:
            return False

    now = time.time()
    # Cache kontrolü — 60 saniye geçerli
    if _cm_signals_cache is not None and (now - _cm_signals_cache_time) < CM_SIGNALS_CACHE_TTL:
        all_signals = _cm_signals_cache
    else:
        raw = _fetch_all_confirmed_money_signals()
        # Deduplication: aynı (home, away, selection_code) için tek kayıt tut
        # Tercih: last_updated_at dolu olanı; ikisi de doluysa created_at yenisini al
        # current_* değerleri her iki kayıttan birleştirilir
        _cm_seen = {}
        for s in raw:
            key = (s.get('home_team', ''), s.get('away_team', ''), s.get('selection_code', ''))
            if key not in _cm_seen:
                _cm_seen[key] = dict(s)
            else:
                ex = _cm_seen[key]
                s_has_cur = bool(s.get('last_updated_at'))
                ex_has_cur = bool(ex.get('last_updated_at'))
                if s_has_cur and not ex_has_cur:
                    ex['current_odds'] = s.get('current_odds') or ex.get('current_odds') or ''
                    ex['current_pct'] = s.get('current_pct') or ex.get('current_pct') or ''
                    ex['current_volume'] = s.get('current_volume') or ex.get('current_volume') or ''
                    ex['last_updated_at'] = s.get('last_updated_at') or ''
        deduped = list(_cm_seen.values())
        # Geçmiş maçlar (sig_date < bugün) tarih kaydı olarak kalır.
        # Aktif maçlar için: oran ters dönmüşse, aralık dışıysa veya
        # ilk snap'a göre düşüş %4 altına düştüyse sinyal listeden kalkar.
        today_str = str(_date.today())
        all_signals = []
        for s in deduped:
            sig_date = str(s.get('date') or s.get('match_date') or '')
            is_past = sig_date and sig_date < today_str
            if is_past:
                all_signals.append(s)
            elif (not _cm_odds_reversed(s)
                  and _cm_in_odds_range(s)
                  and _cm_still_valid(s)):
                all_signals.append(s)
        _cm_signals_cache = all_signals
        _cm_signals_cache_time = now

    active_signals = [s for s in all_signals if _is_today_or_future(s.get('date'))]

    avg_drop = 0.0
    avg_pct = 0.0
    if active_signals:
        drop_list = []
        pct_list = []
        for s in active_signals:
            try:
                drop_list.append(float(str(s.get('odds_drop_pct', '') or 0)))
            except Exception:
                pass
            try:
                pct_list.append(float(str(s.get('pct_now', '') or 0).replace('%', '').strip()))
            except Exception:
                pass
        if drop_list:
            avg_drop = round(sum(drop_list) / len(drop_list), 2)
        if pct_list:
            avg_pct = round(sum(pct_list) / len(pct_list), 1)

    return jsonify({
        'signals': all_signals,
        'count': len(active_signals),
        'avg_drop_pct': avg_drop,
        'avg_pct': avg_pct,
    })


@app.route('/api/confirmed-money-v2', methods=['GET'])
@license_required
def confirmed_money_v2_endpoint():
    """Confirmed Money V2 sinyallerini döndür (90 günlük, DB'den). 60s server cache."""
    global _cm_v2_signals_cache, _cm_v2_signals_cache_time
    from datetime import date as _date

    def _is_today_or_future(d):
        if not d:
            return False
        try:
            return str(d) >= str(_date.today())
        except Exception:
            return False

    now = time.time()
    today_str = str(_date.today())
    if _cm_v2_signals_cache is not None and (now - _cm_v2_signals_cache_time) < CM_V2_SIGNALS_CACHE_TTL:
        all_signals = _cm_v2_signals_cache
    else:
        raw = _fetch_all_confirmed_money_v2_signals()
        # V2 tablosu yoksa/boşsa — V1 verisini V2 kriterleriyle filtrele (fallback)
        if not raw:
            raw_v1 = _fetch_all_confirmed_money_signals()
            raw = []
            for s in raw_v1:
                try:
                    sc = s.get('selection_code', '')
                    if sc == 'X':
                        continue
                    pct_raw = str(s.get('pct_now', '') or '').replace('%', '').strip()
                    pct_val = float(pct_raw) if pct_raw else 0.0
                    if pct_val < 88.0:
                        continue
                    drop_raw = str(s.get('odds_drop_pct', '') or '')
                    drop_val = float(drop_raw) if drop_raw else 0.0
                    if drop_val < 7.0:
                        continue
                    odds_raw = str(s.get('odds_now', '') or '')
                    odds_val = float(odds_raw) if odds_raw else 0.0
                    if not (1.55 <= odds_val <= 2.20):
                        continue
                    raw.append(s)
                except Exception:
                    continue
        _cm_v2_seen = {}
        for s in raw:
            key = (s.get('home_team', ''), s.get('away_team', ''), s.get('selection_code', ''))
            if key not in _cm_v2_seen:
                _cm_v2_seen[key] = dict(s)
            else:
                ex = _cm_v2_seen[key]
                s_has_cur = bool(s.get('last_updated_at'))
                ex_has_cur = bool(ex.get('last_updated_at'))
                if s_has_cur and not ex_has_cur:
                    ex['current_odds'] = s.get('current_odds') or ex.get('current_odds') or ''
                    ex['current_pct'] = s.get('current_pct') or ex.get('current_pct') or ''
                    ex['current_volume'] = s.get('current_volume') or ex.get('current_volume') or ''
                    ex['last_updated_at'] = s.get('last_updated_at') or ''
        deduped = list(_cm_v2_seen.values())
        # Geçmiş maçları her zaman göster; sadece bugün/gelecek aktif sinyallerde oran filtresi uygula
        all_signals = []
        for s in deduped:
            sig_date = str(s.get('date') or s.get('match_date') or '')
            is_past = sig_date and sig_date < today_str
            if is_past:
                all_signals.append(s)
            elif (not _cm_odds_reversed(s)
                  and _cm_v2_in_odds_range(s)
                  and _cm_v2_still_valid(s)):
                all_signals.append(s)
        _cm_v2_signals_cache = all_signals
        _cm_v2_signals_cache_time = now

    active_signals = [s for s in all_signals if _is_today_or_future(s.get('date'))]

    avg_drop = 0.0
    avg_pct = 0.0
    if active_signals:
        drop_list = []
        pct_list = []
        for s in active_signals:
            try:
                drop_list.append(float(str(s.get('odds_drop_pct', '') or 0)))
            except Exception:
                pass
            try:
                pct_list.append(float(str(s.get('pct_now', '') or 0).replace('%', '').strip()))
            except Exception:
                pass
        if drop_list:
            avg_drop = round(sum(drop_list) / len(drop_list), 2)
        if pct_list:
            avg_pct = round(sum(pct_list) / len(pct_list), 1)

    return jsonify({
        'signals': all_signals,
        'count': len(active_signals),
        'avg_drop_pct': avg_drop,
        'avg_pct': avg_pct,
    })


@app.route('/api/admin/confirmed-signals', methods=['GET'])
def admin_get_confirmed_signals():
    """Return all confirmed money signals for admin (last 90 days), deduped.
    App ile aynı _cm_signals_cache kullanılır — liste her zaman birebir aynı."""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401

    global _cm_signals_cache, _cm_signals_cache_time
    now = time.time()
    if _cm_signals_cache is not None and (now - _cm_signals_cache_time) < CM_SIGNALS_CACHE_TTL:
        signals = _cm_signals_cache
    else:
        raw = _fetch_all_confirmed_money_signals()
        _cm_seen = {}
        for s in raw:
            key = (s.get('home_team', ''), s.get('away_team', ''), s.get('selection_code', ''))
            if key not in _cm_seen:
                _cm_seen[key] = s
        deduped = list(_cm_seen.values())
        signals = [s for s in deduped if not _cm_odds_reversed(s) and _cm_in_odds_range(s)]
        _cm_signals_cache = signals
        _cm_signals_cache_time = now

    with _approved_signals_lock:
        approved = _load_approved_signals()
    enriched = []
    for s in signals:
        ak = 'cm|{}|{}|{}'.format(s.get('home_team', ''), s.get('away_team', ''), s.get('selection_code', ''))
        enriched.append({**s, 'is_approved': ak in approved})
    return jsonify({'signals': enriched, 'count': len(enriched)})


@app.route('/api/admin/confirmed-signals-v2', methods=['GET'])
def admin_get_confirmed_signals_v2():
    """Return all CMv2 signals for admin (last 1000), deduped."""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401
    global _cm_v2_admin_signals_cache, _cm_v2_admin_signals_cache_time
    now = time.time()
    if _cm_v2_admin_signals_cache is not None and (now - _cm_v2_admin_signals_cache_time) < CM_V2_SIGNALS_CACHE_TTL:
        signals = _cm_v2_admin_signals_cache
    else:
        raw = _fetch_all_confirmed_money_v2_signals()
        _cm_v2_seen = {}
        for s in raw:
            key = (s.get('home_team', ''), s.get('away_team', ''), s.get('selection_code', ''))
            if key not in _cm_v2_seen:
                _cm_v2_seen[key] = s
        signals = list(_cm_v2_seen.values())
        _cm_v2_admin_signals_cache = signals
        _cm_v2_admin_signals_cache_time = now
    with _approved_signals_lock:
        approved = _load_approved_signals()
    enriched = []
    for s in signals:
        ak = 'cmv2|{}|{}|{}'.format(s.get('home_team', ''), s.get('away_team', ''), s.get('selection_code', ''))
        enriched.append({**s, 'is_approved': ak in approved})
    return jsonify({'signals': enriched, 'count': len(enriched)})


@app.route('/api/admin/cm-signal-result/<int:signal_id>', methods=['PATCH'])
def admin_set_cm_signal_result(signal_id):
    """Set the result (win/loss/null) for a CM signal by ID."""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401
    data = request.get_json(silent=True) or {}
    result_val = data.get('result')  # 'win', 'loss', or null/empty → clear
    if result_val not in ('win', 'loss', None, ''):
        return jsonify({'error': 'Invalid result value. Use win, loss, or null.'}), 400
    try:
        supabase = get_supabase_client()
        if not supabase or not supabase.is_available:
            return jsonify({'error': 'DB unavailable'}), 503
        key = supabase.key
        headers = {
            'apikey': key,
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
            'Prefer': 'return=minimal',
        }
        patch_url = f"{supabase._rest_url('confirmed_money_signals')}?id=eq.{signal_id}"
        patch_data = {'result': result_val if result_val else None}
        resp = supabase._get_http_client().patch(patch_url, headers=headers, json=patch_data, timeout=10)
        if resp.status_code in (200, 204):
            # Invalidate server-side cache so next fetch picks up new result
            global _cm_signals_cache, _cm_signals_cache_time
            _cm_signals_cache = None
            _cm_signals_cache_time = 0
            return jsonify({'ok': True, 'signal_id': signal_id, 'result': result_val})
        if resp.status_code == 400:
            # Likely missing column — return structured migration error for frontend
            body = resp.text[:500]
            migration_sql = 'ALTER TABLE confirmed_money_signals ADD COLUMN IF NOT EXISTS result text;'
            return jsonify({'error': 'MIGRATION_NEEDED', 'migration_sql': migration_sql, 'detail': body}), 400
        return jsonify({'error': f'DB error {resp.status_code}', 'detail': resp.text[:200]}), 500
    except Exception as e:
        print(f"[CM-Result] PATCH error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/cmv2-signal-result/<int:signal_id>', methods=['PATCH'])
def admin_set_cmv2_signal_result(signal_id):
    """Set the result (win/loss/null) for a CMv2 signal by ID."""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401
    data = request.get_json(silent=True) or {}
    result_val = data.get('result')
    if result_val not in ('win', 'loss', None, ''):
        return jsonify({'error': 'Invalid result value. Use win, loss, or null.'}), 400
    try:
        supabase = get_supabase_client()
        if not supabase or not supabase.is_available:
            return jsonify({'error': 'DB unavailable'}), 503
        key = supabase.key
        headers = {
            'apikey': key,
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
            'Prefer': 'return=minimal',
        }
        patch_url = f"{supabase._rest_url('confirmed_money_v2_signals')}?id=eq.{signal_id}"
        patch_data = {'result': result_val if result_val else None}
        resp = supabase._get_http_client().patch(patch_url, headers=headers, json=patch_data, timeout=10)
        if resp.status_code in (200, 204):
            global _cm_v2_admin_signals_cache, _cm_v2_admin_signals_cache_time
            _cm_v2_admin_signals_cache = None
            _cm_v2_admin_signals_cache_time = 0
            return jsonify({'ok': True, 'signal_id': signal_id, 'result': result_val})
        if resp.status_code == 400:
            body = resp.text[:500]
            migration_sql = 'ALTER TABLE confirmed_money_v2_signals ADD COLUMN IF NOT EXISTS result text;'
            return jsonify({'error': 'MIGRATION_NEEDED', 'migration_sql': migration_sql, 'detail': body}), 400
        return jsonify({'error': f'DB error {resp.status_code}', 'detail': resp.text[:200]}), 500
    except Exception as e:
        print(f"[CMv2-Result] PATCH error: {e}")
        return jsonify({'error': str(e)}), 500


def _fetch_all_eml_signals():
    """early_money_lock_signals tablosundan en son 1000 sinyali çek (created_at desc)."""
    try:
        supabase = get_supabase_client()
        if not supabase or not supabase.is_available:
            return []
        headers = supabase._headers()
        url = (
            f"{supabase._rest_url('early_money_lock_signals')}"
            f"?select=*&order=created_at.desc,home_team.asc&limit=1000"
        )
        resp = supabase._get_http_client().get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            rows = resp.json()
            result = []
            for r in rows:
                result.append({
                    'id': r.get('id'),
                    'match_key': r.get('match_key', ''),
                    'home_team': r.get('home_team', ''),
                    'away_team': r.get('away_team', ''),
                    'league': r.get('league', ''),
                    'date': _normalize_match_date(r.get('match_date', '')),
                    'match_date': _normalize_match_date(r.get('match_date', '')),
                    'kickoff_utc': r.get('kickoff_utc', ''),
                    'selection_code': r.get('selection_code', ''),
                    'selection_label': r.get('selection_label', ''),
                    'pct_now': r.get('pct_now', ''),
                    'volume_now': r.get('volume_now', ''),
                    'amt_now': r.get('amt_now', ''),
                    'hours_before_kickoff': r.get('hours_before_kickoff'),
                    'consecutive_snapshots': r.get('consecutive_snapshots', 5),
                    'created_at': r.get('created_at') or '',
                    'last_updated_at': r.get('last_updated_at') or '',
                    'result': r.get('result') or '',
                })
            return result
        return []
    except Exception as e:
        print(f"[EMLSignals] fetch error: {e}")
        return []


def _fetch_all_fake_sharp_signals():
    """fake_sharp_signals tablosundan en son 1000 sinyali çek (created_at desc)."""
    try:
        supabase = get_supabase_client()
        if not supabase or not supabase.is_available:
            return []
        headers = supabase._headers()
        url = (
            f"{supabase._rest_url('fake_sharp_signals')}"
            f"?select=*&order=created_at.desc,home_team.asc&limit=1000"
        )
        resp = supabase._get_http_client().get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            rows = resp.json()
            _backfill_match_date_times(rows, 'fake_sharp_signals')
            result = []
            for r in rows:
                result.append({
                    'id': r.get('id'),
                    'match_key': r.get('match_key', ''),
                    'home_team': r.get('home_team', ''),
                    'away_team': r.get('away_team', ''),
                    'league': r.get('league', ''),
                    'date': _normalize_match_date(r.get('match_date', '')),
                    'match_date': _normalize_match_date(r.get('match_date', '')),
                    'selection_code': r.get('selection_code', ''),
                    'selection_label': r.get('selection_label', ''),
                    'odds_16h': r.get('odds_16h', ''),
                    'odds_now': r.get('odds_now', ''),
                    'current_odds': r.get('current_odds') or '',
                    'pct_now': r.get('pct_now', ''),
                    'current_pct': r.get('current_pct') or '',
                    'volume_now': r.get('volume_now', ''),
                    'current_volume': r.get('current_volume') or '',
                    'odds_rise_pct': r.get('odds_rise_pct') or '',
                    'last_updated_at': r.get('last_updated_at') or '',
                    'created_at': r.get('created_at') or '',
                    'result': r.get('result') or '',
                })
            return result
        return []
    except Exception as e:
        print(f"[FakeSharpSignals] fetch error: {e}")
        return []


@app.route('/api/fake-sharp', methods=['GET'])
@license_required
def fake_sharp_endpoint():
    """Fake Sharp sinyallerini döndür (DB'den). 60s server cache."""
    global _fs_signals_cache, _fs_signals_cache_time
    from datetime import date as _date

    def _is_today_or_future(d):
        if not d:
            return False
        try:
            return str(d) >= str(_date.today())
        except Exception:
            return False

    now = time.time()
    if _fs_signals_cache is not None and (now - _fs_signals_cache_time) < FS_SIGNALS_CACHE_TTL:
        all_signals = _fs_signals_cache
    else:
        raw = _fetch_all_fake_sharp_signals()
        _fs_seen = {}
        for s in raw:
            key = (s.get('home_team', ''), s.get('away_team', ''), s.get('selection_code', ''))
            if key not in _fs_seen:
                _fs_seen[key] = dict(s)
            else:
                ex = _fs_seen[key]
                s_has_cur = bool(s.get('last_updated_at'))
                ex_has_cur = bool(ex.get('last_updated_at'))
                if s_has_cur and not ex_has_cur:
                    ex['current_odds'] = s.get('current_odds') or ex.get('current_odds') or ''
                    ex['current_pct'] = s.get('current_pct') or ex.get('current_pct') or ''
                    ex['current_volume'] = s.get('current_volume') or ex.get('current_volume') or ''
                    ex['last_updated_at'] = s.get('last_updated_at') or ''
        all_signals = list(_fs_seen.values())
        # Güvenlik filtresi: current_odds, odds_16h'a göre %4 yükseliş eşiğinin altına düştüyse sinyali gizle
        def _fs_still_valid(s):
            try:
                o16 = float(str(s.get('odds_16h') or 0))
                ocur = float(str(s.get('current_odds') or s.get('odds_now') or 0))
                if o16 <= 0 or ocur <= 0:
                    return True
                rise = (ocur - o16) / o16
                return rise >= 0.04
            except Exception:
                return True
        all_signals = [s for s in all_signals if _fs_still_valid(s)]
        _fs_signals_cache = all_signals
        _fs_signals_cache_time = now

    active_signals = [s for s in all_signals if _is_today_or_future(s.get('date'))]

    avg_rise = 0.0
    avg_pct = 0.0
    if active_signals:
        rise_list = []
        pct_list = []
        for s in active_signals:
            try:
                rise_list.append(float(str(s.get('odds_rise_pct', '') or 0)))
            except Exception:
                pass
            try:
                pct_list.append(float(str(s.get('pct_now', '') or 0).replace('%', '').strip()))
            except Exception:
                pass
        if rise_list:
            avg_rise = round(sum(rise_list) / len(rise_list), 2)
        if pct_list:
            avg_pct = round(sum(pct_list) / len(pct_list), 1)

    return jsonify({
        'signals': all_signals,
        'count': len(active_signals),
        'avg_rise_pct': avg_rise,
        'avg_pct': avg_pct,
    })


@app.route('/api/admin/fake-sharp-signals', methods=['GET'])
def admin_get_fake_sharp_signals():
    """Return all fake sharp signals for admin.
    App ile aynı _fs_signals_cache kullanılır."""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401

    global _fs_signals_cache, _fs_signals_cache_time
    now = time.time()
    if _fs_signals_cache is not None and (now - _fs_signals_cache_time) < FS_SIGNALS_CACHE_TTL:
        signals = _fs_signals_cache
    else:
        raw = _fetch_all_fake_sharp_signals()
        _fs_seen = {}
        for s in raw:
            key = (s.get('home_team', ''), s.get('away_team', ''), s.get('selection_code', ''))
            if key not in _fs_seen:
                _fs_seen[key] = s
        signals = list(_fs_seen.values())
        _fs_signals_cache = signals
        _fs_signals_cache_time = now

    with _approved_signals_lock:
        approved = _load_approved_signals()
    enriched = []
    for s in signals:
        ak = 'fs|{}|{}|{}'.format(s.get('home_team', ''), s.get('away_team', ''), s.get('selection_code', ''))
        enriched.append({**s, 'is_approved': ak in approved})
    return jsonify({'signals': enriched, 'count': len(enriched)})


@app.route('/api/admin/fs-signal-result/<int:signal_id>', methods=['PATCH'])
def admin_set_fs_signal_result(signal_id):
    """Set the result (win/loss/null) for a Fake Sharp signal by ID."""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401
    data = request.get_json(silent=True) or {}
    result_val = data.get('result')
    if result_val not in ('win', 'loss', None, ''):
        return jsonify({'error': 'Invalid result value. Use win, loss, or null.'}), 400
    try:
        supabase = get_supabase_client()
        if not supabase or not supabase.is_available:
            return jsonify({'error': 'DB unavailable'}), 503
        key = supabase.key
        headers = {
            'apikey': key,
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
            'Prefer': 'return=minimal',
        }
        patch_url = f"{supabase._rest_url('fake_sharp_signals')}?id=eq.{signal_id}"
        patch_data = {'result': result_val if result_val else None}
        resp = supabase._get_http_client().patch(patch_url, headers=headers, json=patch_data, timeout=10)
        if resp.status_code in (200, 204):
            global _fs_signals_cache, _fs_signals_cache_time
            _fs_signals_cache = None
            _fs_signals_cache_time = 0
            return jsonify({'ok': True, 'signal_id': signal_id, 'result': result_val})
        if resp.status_code == 400:
            body = resp.text[:500]
            migration_sql = 'ALTER TABLE fake_sharp_signals ADD COLUMN IF NOT EXISTS result text;'
            return jsonify({'error': 'MIGRATION_NEEDED', 'migration_sql': migration_sql, 'detail': body}), 400
        return jsonify({'error': f'DB error {resp.status_code}', 'detail': resp.text[:200]}), 500
    except Exception as e:
        print(f"[FS-Result] PATCH error: {e}")
        return jsonify({'error': str(e)}), 500


# ============================================================
# EARLY MONEY LOCK API ENDPOINTS
# ============================================================

@app.route('/api/early-money-lock', methods=['GET'])
@license_required
def early_money_lock_endpoint():
    """Early Money Lock sinyallerini döndür (DB'den). 60s server cache."""
    global _eml_signals_cache, _eml_signals_cache_time
    from datetime import date as _date

    def _is_today_or_future(d):
        if not d:
            return False
        try:
            return str(d) >= str(_date.today())
        except Exception:
            return False

    now = time.time()
    if _eml_signals_cache is not None and (now - _eml_signals_cache_time) < EML_SIGNALS_CACHE_TTL:
        all_signals = _eml_signals_cache
    else:
        raw = _fetch_all_eml_signals()
        _seen = {}
        for s in raw:
            key = (s.get('home_team', ''), s.get('away_team', ''), s.get('selection_code', ''))
            if key not in _seen:
                _seen[key] = s
        deduped = list(_seen.values())

        # Aktif maçlar için canlı pct lookup'ı (moneyway latest cache)
        matches_data = _server_matches_cache.get('moneyway_1x2_all') or _server_matches_cache.get('moneyway_1x2') or []
        cache_lookup = {}
        for m in matches_data:
            h = (m.get('home_team', '') or '').lower().strip()
            a = (m.get('away_team', '') or '').lower().strip()
            odds_obj = m.get('odds') or {}
            for code, raw_pct in [
                ('1', odds_obj.get('Pct1', '')),
                ('2', odds_obj.get('Pct2', '')),
                ('X', odds_obj.get('PctX', '')),
            ]:
                if h and a:
                    cache_lookup[(h, a, code)] = str(raw_pct) if raw_pct else ''

        # Geçmiş maçlar olduğu gibi; aktif maçlarda canlı pct EML eşiğinin altına
        # düştüyse sinyal listeden kalkar (canlı veri yoksa fail-open).
        today_str = str(_date.today())
        all_signals = []
        for s in deduped:
            sig_date = str(s.get('date') or s.get('match_date') or '')
            is_past = sig_date and sig_date < today_str
            if is_past:
                all_signals.append(s)
                continue
            h = (s.get('home_team', '') or '').lower().strip()
            a = (s.get('away_team', '') or '').lower().strip()
            code = s.get('selection_code', '')
            cur_pct_raw = cache_lookup.get((h, a, code), '')
            if not cur_pct_raw:
                all_signals.append(s)
                continue
            try:
                cur_pct_val = float(str(cur_pct_raw).replace('%', '').strip())
                if cur_pct_val >= EML_PCT_THRESHOLD_LOCAL:
                    all_signals.append(s)
            except Exception:
                all_signals.append(s)

        _eml_signals_cache = all_signals
        _eml_signals_cache_time = now

    active_signals = [s for s in all_signals if _is_today_or_future(s.get('date'))]

    avg_pct = 0.0
    if active_signals:
        pct_list = []
        for s in active_signals:
            try:
                pct_list.append(float(str(s.get('pct_now', '') or 0).replace('%', '').strip()))
            except Exception:
                pass
        if pct_list:
            avg_pct = round(sum(pct_list) / len(pct_list), 1)

    return jsonify({
        'signals': all_signals,
        'count': len(active_signals),
        'avg_pct': avg_pct,
    })


@app.route('/api/admin/early-money-lock-signals', methods=['GET'])
def admin_get_eml_signals():
    """Return all EML signals for admin."""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401

    global _eml_signals_cache, _eml_signals_cache_time
    now = time.time()
    if _eml_signals_cache is not None and (now - _eml_signals_cache_time) < EML_SIGNALS_CACHE_TTL:
        signals = _eml_signals_cache
    else:
        signals = _fetch_all_eml_signals()
        _eml_signals_cache = signals
        _eml_signals_cache_time = now

    with _approved_signals_lock:
        approved = _load_approved_signals()
    enriched = []
    for s in signals:
        ak = 'eml|{}|{}|{}'.format(s.get('home_team', ''), s.get('away_team', ''), s.get('selection_code', ''))
        enriched.append({**s, 'is_approved': ak in approved})
    return jsonify({'signals': enriched, 'count': len(enriched)})


@app.route('/api/admin/eml-signal-result/<int:signal_id>', methods=['PATCH'])
def admin_set_eml_signal_result(signal_id):
    """Set the result (win/loss/null) for an EML signal by ID."""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401
    data = request.get_json(silent=True) or {}
    result_val = data.get('result')
    if result_val not in ('win', 'loss', None, ''):
        return jsonify({'error': 'Invalid result value. Use win, loss, or null.'}), 400
    try:
        supabase = get_supabase_client()
        if not supabase or not supabase.is_available:
            return jsonify({'error': 'DB unavailable'}), 503
        key = supabase.key
        headers = {
            'apikey': key,
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
            'Prefer': 'return=minimal',
        }
        patch_url = f"{supabase._rest_url('early_money_lock_signals')}?id=eq.{signal_id}"
        patch_data = {'result': result_val if result_val else None}
        resp = supabase._get_http_client().patch(patch_url, headers=headers, json=patch_data, timeout=10)
        if resp.status_code in (200, 204):
            global _eml_signals_cache, _eml_signals_cache_time
            _eml_signals_cache = None
            _eml_signals_cache_time = 0
            return jsonify({'ok': True, 'signal_id': signal_id, 'result': result_val})
        return jsonify({'error': f'DB error {resp.status_code}', 'detail': resp.text[:200]}), 500
    except Exception as e:
        print(f"[EML-Result] PATCH error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/admin/setup-eml-table', methods=['POST'])
def admin_setup_eml_table():
    """Early Money Lock migration SQL'ini döndür (admin bilgi endpoint'i)."""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401
    migration_sql = """CREATE TABLE IF NOT EXISTS early_money_lock_signals (
    id bigserial PRIMARY KEY,
    match_key text NOT NULL,
    home_team text,
    away_team text,
    league text,
    match_date text,
    kickoff_utc text,
    selection_code text NOT NULL,
    selection_label text,
    pct_now text,
    volume_now text,
    consecutive_snapshots integer DEFAULT 5,
    created_at timestamptz DEFAULT now(),
    last_updated_at timestamptz,
    result text,
    UNIQUE (match_key, selection_code)
);"""
    return jsonify({'migration_sql': migration_sql, 'message': 'Supabase SQL Editor\'da bu SQL\'i çalıştırın.'})


@app.route('/api/admin/underdog-signals', methods=['GET'])
def admin_get_underdog_signals():
    """Return all underdog signals for admin (includes result field).
    _build_unified_underdog_signals() kullanılır — app ile birebir aynı liste."""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401

    signals = _build_unified_underdog_signals()

    results_map = _load_ud_results()
    with _approved_signals_lock:
        approved = _load_approved_signals()
    enriched = []
    for sig in signals:
        mk = sig.get('match_key', '')
        sc = sig.get('selection_code', '')
        if not sig.get('result'):
            sig['result'] = results_map.get(f"{mk}|{sc}", '')
        ak = 'ud|{}|{}|{}'.format(sig.get('home_team', ''), sig.get('away_team', ''), sc)
        enriched.append({**sig, 'is_approved': ak in approved})
    return jsonify({'signals': enriched, 'count': len(enriched)})


@app.route('/api/admin/underdog-signals/result', methods=['PATCH'])
def admin_update_underdog_result():
    """Update won/lost result for an underdog signal (stored in data/underdog_results.json)."""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401
    data = request.get_json(silent=True) or {}
    match_key = data.get('match_key', '').strip()
    selection_code = data.get('selection_code', '').strip()
    result_val = data.get('result', '')
    if result_val not in ('won', 'lost', ''):
        return jsonify({'status': 'error', 'message': 'Geçersiz sonuç (won/lost/boş)'}), 400
    if not match_key or not selection_code:
        return jsonify({'status': 'error', 'message': 'match_key ve selection_code zorunlu'}), 400
    try:
        _save_ud_result(match_key, selection_code, result_val)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/underdog-signals/import-date', methods=['POST'])
def admin_import_underdog_signals_for_date():
    """Fetch moneyway_1x2_history data for a given date, apply underdog filters,
    and upsert matching signals into underdog_signals table.
    Accepts date via query param (?date=YYYY-MM-DD) or JSON body."""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401

    # Accept date from query param OR JSON body
    data = request.get_json(silent=True) or {}
    target_date = (request.args.get('date', '').strip()
                   or str(data.get('date', '')).strip())
    if not target_date:
        return jsonify({'status': 'error', 'message': 'date zorunlu (YYYY-MM-DD)'}), 400

    try:
        from datetime import datetime, timedelta, time as _time_cls
        from urllib.parse import quote as _url_quote
        import pytz
        datetime.strptime(target_date, '%Y-%m-%d')
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Geçersiz tarih formatı (YYYY-MM-DD)'}), 400

    try:
        from datetime import datetime, timedelta, time as _time_cls
        from urllib.parse import quote as _url_quote
        import pytz

        supabase = get_supabase_client()
        if not supabase or not supabase.is_available:
            return jsonify({'status': 'error', 'message': 'DB bağlantısı yok'}), 500

        tr_tz = pytz.timezone('Europe/Istanbul')
        target_dt = datetime.strptime(target_date, '%Y-%m-%d').date()

        # Convert Istanbul date range to UTC for fixtures query
        day_start_tr = tr_tz.localize(datetime.combine(target_dt, _time_cls.min))
        day_end_tr   = tr_tz.localize(datetime.combine(target_dt + timedelta(days=1), _time_cls.min))
        day_start_utc = day_start_tr.astimezone(pytz.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
        day_end_utc   = day_end_tr.astimezone(pytz.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')

        headers = supabase._headers()

        # Step 1: fetch fixtures for the date
        fix_url = (
            f"{supabase._rest_url('fixtures')}?select=match_id_hash,home_team,away_team,"
            f"league,kickoff_utc&kickoff_utc=gte.{_url_quote(day_start_utc)}"
            f"&kickoff_utc=lt.{_url_quote(day_end_utc)}&order=kickoff_utc.asc&limit=1000"
        )
        fix_resp = supabase._get_http_client().get(fix_url, headers=headers, timeout=15)
        if fix_resp.status_code != 200:
            return jsonify({'status': 'error', 'message': f'fixtures fetch error: {fix_resp.status_code}'}), 500

        fixtures = fix_resp.json()
        if not fixtures:
            return jsonify({'status': 'ok', 'imported': 0, 'skipped': 0, 'date': target_date,
                            'message': 'Bu tarih için fixture bulunamadı'})

        # Step 2: fetch the latest history snapshot per hash reliably.
        # Use small batches (10 hashes) with high per-batch limit (2000 rows)
        # so the worst-case 200 snapshots/match are always covered within the batch window.
        hashes = [f.get('match_id_hash', '') for f in fixtures if f.get('match_id_hash')]
        odds_cache = {}
        batch_errors = []
        batch_size = 10          # 10 hashes per request
        per_batch_limit = 2000   # covers up to 200 snapshots per hash
        for i in range(0, len(hashes), batch_size):
            batch = hashes[i:i+batch_size]
            hash_list = ','.join(batch)
            if not hash_list:
                continue
            h_url = (f"{supabase._rest_url('moneyway_1x2_history')}?"
                     f"match_id_hash=in.({hash_list})"
                     f"&order=scraped_at.desc&limit={per_batch_limit}")
            h_resp = supabase._get_http_client().get(h_url, headers=headers, timeout=30)
            if h_resp.status_code == 200:
                for row in h_resp.json():
                    h = row.get('match_id_hash', '')
                    # Keep only the first (= most recent) row per hash
                    if h and h not in odds_cache:
                        odds_cache[h] = row
            else:
                msg = f"batch {i//batch_size+1}: HTTP {h_resp.status_code}"
                batch_errors.append(msg)
                print(f"[UnderdogImport] history fetch warning — {msg}")

        # Step 3: apply underdog thresholds and build signals list (sinyal_engine.py ile senkron)
        odds_threshold = 2.90
        signals = []
        for fix in fixtures:
            mhash = fix.get('match_id_hash', '')
            row   = odds_cache.get(mhash)
            if not row:
                continue
            home   = fix.get('home_team', '')
            away   = fix.get('away_team', '')
            league = fix.get('league', '')
            date   = fix.get('kickoff_utc', target_date)
            volume = row.get('volume', '')
            try:
                vol_val = float(str(volume).replace('£', '').replace(',', '').replace(' ', '').strip()) if volume else 0.0
            except (ValueError, TypeError):
                vol_val = 0.0
            if vol_val < 800:
                continue
            required_pct = 50.0 if vol_val >= 5000 else 55.0
            candidates = [
                ('1', 'Ev Sahibi', row.get('odds1', '-'), row.get('pct1', ''), row.get('amt1', '')),
                ('2', 'Deplasman', row.get('odds2', '-'), row.get('pct2', ''), row.get('amt2', '')),
            ]
            for code, label, raw_odds, raw_pct, raw_amt in candidates:
                try:
                    odds_val = float(str(raw_odds).replace(',', '.')) if raw_odds and raw_odds != '-' else 0.0
                except (ValueError, TypeError):
                    odds_val = 0.0
                try:
                    pct_val = float(str(raw_pct).replace('%', '').strip()) if raw_pct else 0.0
                except (ValueError, TypeError):
                    pct_val = 0.0
                if odds_val >= odds_threshold and pct_val >= required_pct:
                    signals.append({
                        'home_team': home, 'away_team': away, 'league': league,
                        'date': date, 'selection_code': code, 'selection_label': label,
                        'odds': str(raw_odds), 'pct': str(raw_pct),
                        'amt': str(raw_amt), 'volume': str(volume),
                    })

        if not signals:
            return jsonify({'status': 'ok', 'imported': 0, 'skipped': 0, 'date': target_date,
                            'message': 'Eşiği geçen sinyal bulunamadı'})

        # Step 4: upsert and get accurate imported/skipped counts.
        # return=representation with resolution=ignore-duplicates returns only inserted rows.
        records = []
        for s in signals:
            match_key = f"{s['home_team']}|{s['away_team']}|{s.get('date','')}"
            records.append({
                'match_key': match_key,
                'home_team': s.get('home_team', ''),
                'away_team': s.get('away_team', ''),
                'league': s.get('league', ''),
                'match_date': _normalize_to_iso_datetime_tr(s.get('date', '')),
                'selection_code': s.get('selection_code', ''),
                'odds': str(s.get('odds', '')),
                'pct': str(s.get('pct', '')),
                'amt': str(s.get('amt', '')),
                'volume': str(s.get('volume', '')),
            })
        upsert_headers = dict(headers)
        upsert_headers['Prefer'] = 'resolution=ignore-duplicates,return=representation'
        url = f"{supabase._rest_url('underdog_signals')}?on_conflict=match_key,selection_code"
        upsert_resp = supabase._get_http_client().post(
            url, headers=upsert_headers, json=records, timeout=15)
        if upsert_resp.status_code in (200, 201):
            inserted = upsert_resp.json() if upsert_resp.text else []
            imported = len(inserted) if isinstance(inserted, list) else len(records)
        else:
            err_body = upsert_resp.text[:300] if upsert_resp.text else ''
            print(f"[UnderdogImport] upsert non-2xx: {upsert_resp.status_code} {err_body}")
            return jsonify({'status': 'error',
                            'message': f'DB upsert hatası: {upsert_resp.status_code}',
                            'detail': err_body}), 500
        skipped = len(signals) - imported

        print(f"[UnderdogImport] date={target_date} signals={len(signals)} imported={imported} skipped={skipped}")
        result = {'status': 'ok', 'imported': imported, 'skipped': skipped,
                  'date': target_date, 'fixtures_checked': len(fixtures),
                  'fixtures_with_odds': len(odds_cache)}
        if batch_errors:
            result['warnings'] = batch_errors
        return jsonify(result)

    except Exception as e:
        import traceback
        print(f"[UnderdogImport] error: {traceback.format_exc()}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/admin/approved-signals', methods=['GET'])
def admin_get_approved_signals_list():
    """Return all approved signals (admin)."""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401
    with _approved_signals_lock:
        data = _load_approved_signals()
    return jsonify({'approved': data, 'count': len(data)})


@app.route('/api/admin/approve-signal', methods=['POST'])
def admin_approve_signal():
    """Approve a signal — save full signal data to approved_signals.json."""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401
    body = request.get_json(silent=True) or {}
    approve_key = body.get('approve_key', '').strip()
    if not approve_key:
        return jsonify({'error': 'approve_key required'}), 400
    with _approved_signals_lock:
        data = _load_approved_signals()
        data[approve_key] = {
            'signal_type': body.get('signal_type', ''),
            'match_key': body.get('match_key', ''),
            'selection_code': body.get('selection_code', ''),
            'home_team': body.get('home_team', ''),
            'away_team': body.get('away_team', ''),
            'league': body.get('league', ''),
            'match_date': body.get('match_date', ''),
            'odds': body.get('odds', ''),
            'pct': body.get('pct', ''),
            'amt': body.get('amt', ''),
            'volume': body.get('volume', ''),
            'approved_at': datetime.utcnow().isoformat() + 'Z',
        }
        if not _save_approved_signals(data):
            return jsonify({'error': 'SAVE_FAILED', 'message': 'Onay kaydedilemedi'}), 500
    return jsonify({'status': 'ok', 'approve_key': approve_key})


@app.route('/api/admin/approved-signal-result', methods=['PATCH'])
def admin_update_approved_signal_result():
    """Update result (win/loss/'') for an approved signal."""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401
    data = request.get_json(silent=True) or {}
    approve_key = data.get('approve_key', '').strip()
    result_val = data.get('result', '')
    if not approve_key:
        return jsonify({'error': 'approve_key required'}), 400
    if result_val not in ('win', 'loss', ''):
        return jsonify({'error': 'Invalid result. Use win, loss, or ""'}), 400
    with _approved_signals_lock:
        signals = _load_approved_signals()
        if approve_key not in signals:
            return jsonify({'error': 'Signal not found'}), 404
        signals[approve_key]['result'] = result_val
        if not _save_approved_signals(signals):
            return jsonify({'error': 'SAVE_FAILED', 'message': 'Sonuç kaydedilemedi'}), 500
    return jsonify({'status': 'ok', 'approve_key': approve_key, 'result': result_val})


@app.route('/api/admin/approve-signal', methods=['DELETE'])
def admin_unapprove_signal():
    """Remove approval from a signal."""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401
    body = request.get_json(silent=True) or {}
    approve_key = body.get('approve_key', '').strip()
    if not approve_key:
        return jsonify({'error': 'approve_key required'}), 400
    with _approved_signals_lock:
        data = _load_approved_signals()
        removed = approve_key in data
        data.pop(approve_key, None)
        if not _save_approved_signals(data):
            return jsonify({'error': 'SAVE_FAILED', 'message': 'Onay kaldırılamadı'}), 500
    return jsonify({'status': 'ok', 'removed': removed})


@app.route('/api/approved-signals', methods=['GET'])
@license_required
def get_approved_signals_public():
    """Public endpoint — returns all approved signals (license required)."""
    with _approved_signals_lock:
        data = _load_approved_signals()
    signals = []
    for key, sig in data.items():
        signals.append({**sig, 'approve_key': key})
    signals.sort(key=lambda x: x.get('approved_at', ''), reverse=True)
    return jsonify({'signals': signals, 'count': len(signals)})


@app.route('/api/analysts', methods=['POST'])
def create_analyst_endpoint():
    """Create new analyst (admin only)"""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'status': 'error', 'message': 'İsim zorunludur'}), 400
    bio = request.form.get('bio', '').strip() or None
    avatar_url = None
    if 'avatar' in request.files:
        file = request.files['avatar']
        if file and file.filename:
            import uuid
            ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'png'
            if ext in ('png', 'jpg', 'jpeg', 'gif', 'webp'):
                file_data = file.read()
                if len(file_data) <= 5 * 1024 * 1024:
                    file_path = f"analysts/{uuid.uuid4().hex}.{ext}"
                    content_type = file.content_type or 'image/png'
                    avatar_url = db.upload_to_storage('smartxflow', file_path, file_data, content_type)
    result = db.create_analyst(name, avatar_url, bio)
    if result:
        _invalidate_analysts_cache()
        return jsonify({'status': 'ok', 'data': result})
    return jsonify({'status': 'error', 'message': 'Analizci oluşturulamadı'}), 500

@app.route('/api/analysts/<int:analyst_id>', methods=['PUT'])
def update_analyst_endpoint(analyst_id):
    """Update analyst (admin only)"""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401
    update_data = {}
    name = request.form.get('name', '').strip()
    if name:
        update_data['name'] = name
    bio = request.form.get('bio', None)
    if bio is not None:
        update_data['bio'] = bio.strip() or None
    is_active = request.form.get('is_active', None)
    if is_active is not None:
        update_data['is_active'] = is_active == 'true'
    if 'avatar' in request.files:
        file = request.files['avatar']
        if file and file.filename:
            import uuid
            ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'png'
            if ext in ('png', 'jpg', 'jpeg', 'gif', 'webp'):
                file_data = file.read()
                if len(file_data) <= 5 * 1024 * 1024:
                    file_path = f"analysts/{uuid.uuid4().hex}.{ext}"
                    content_type = file.content_type or 'image/png'
                    avatar_url = db.upload_to_storage('smartxflow', file_path, file_data, content_type)
                    if avatar_url:
                        update_data['avatar_url'] = avatar_url
    if not update_data:
        return jsonify({'status': 'error', 'message': 'Güncellenecek veri yok'}), 400
    success = db.update_analyst(analyst_id, update_data)
    if success:
        _invalidate_analysts_cache()
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 500

@app.route('/api/analysts/<int:analyst_id>', methods=['DELETE'])
def delete_analyst_endpoint(analyst_id):
    """Delete analyst (admin only)"""
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'UNAUTHORIZED'}), 401
    success = db.delete_analyst(analyst_id)
    if success:
        _invalidate_analysts_cache()
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 500


@app.route('/api/analysts/<int:analyst_id>/analyses', methods=['GET'])
def get_analyst_analyses_endpoint(analyst_id):
    """Get analyst profile with analyses grouped by date"""
    from datetime import datetime, timedelta
    import pytz
    
    analysts = db.get_analysts(active_only=True)
    analyst = next((a for a in analysts if a.get('id') == analyst_id), None)
    if not analyst:
        return jsonify({'error': 'Analizci bulunamadı'}), 404
    
    stats_map = db.get_analyst_stats()
    s = stats_map.get(analyst_id, {})
    analyst['stats'] = {
        'total': s.get('total', 0),
        'won': s.get('won', 0),
        'lost': s.get('lost', 0),
        'push': s.get('push', 0),
        'void': s.get('void', 0),
        'pending': s.get('pending', 0),
        'success_pct': s.get('success_pct', 0.0),
        'avg_odds': s.get('avg_odds', 0.0),
        'roi_pct': s.get('roi_pct', 0.0),
        'net_profit': s.get('net_profit', 0.0)
    }
    
    all_analyses = db.get_analyses('analysis')
    analyst_analyses = [a for a in all_analyses if a.get('analyst_id') == analyst_id]
    
    tz = pytz.timezone('Europe/Istanbul')
    grouped = {}
    for item in analyst_analyses:
        try:
            dt = datetime.fromisoformat(item['created_at'].replace('Z', '+00:00'))
            dt_tr = dt.astimezone(tz)
            date_key = dt_tr.strftime('%Y-%m-%d')
        except:
            date_key = 'unknown'
        if date_key not in grouped:
            grouped[date_key] = []
        grouped[date_key].append(item)
    
    sorted_dates = sorted(grouped.keys(), reverse=True)
    date_groups = []
    for dk in sorted_dates:
        date_groups.append({
            'date': dk,
            'items': grouped[dk]
        })
    
    return jsonify({
        'analyst': analyst,
        'date_groups': date_groups
    })


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
        setInterval(updateStatus, 60000);
        
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
        plan = data.get('plan', 'core')
        if plan not in ('core', 'pro'):
            plan = 'core'
        is_free = bool(data.get('is_free', False))
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
        
        # Satış anındaki fiyatı hesapla
        sub_type = _classify_subscription(duration_days, plan)
        current_pricing = _load_pricing()
        if is_free or sub_type == 'free_trial':
            computed_price_paid = 0.0
        else:
            p = current_pricing.get(sub_type, {})
            computed_price_paid = float(p.get('price', 0)) if isinstance(p, dict) else 0.0

        # Insert license
        insert_data = {
            'key': key,
            'email': email,
            'duration_days': duration_days,
            'expires_at': expires_at.isoformat(),
            'status': 'active',
            'max_devices': max_devices,
            'note': note or None,
            'plan': plan,
            'is_free': is_free,
            'price_paid': computed_price_paid
        }
        if telegram_membership:
            insert_data['telegram_membership'] = telegram_membership
        if telegram_username:
            insert_data['telegram_username'] = telegram_username
        result = license_insert('licenses', insert_data)
        # price_paid kolonu henüz eklenmemişse kolonsuz tekrar dene
        if result is None:
            insert_data.pop('price_paid', None)
            result = license_insert('licenses', insert_data)
        
        if result:
            _license_cache['data'] = None
            return jsonify({'success': True, 'key': key})
        else:
            return jsonify({'success': False, 'error': 'Veritabani hatasi'})
            
    except Exception as e:
        license_logging.error(f"Create license error: {e}")
        return jsonify({'success': False, 'error': str(e)})


_license_cache = {'data': None, 'ts': 0, 'ttl': 30}

@app.route('/api/licenses/list')
def list_licenses():
    """List all licenses with device counts (cached 30s)"""
    try:
        if not get_license_db():
            return jsonify({'success': False, 'error': 'Supabase baglantisi yok'})
        
        import time as _time
        now = _time.time()
        force = request.args.get('force') == '1'
        if not force and _license_cache['data'] and (now - _license_cache['ts']) < _license_cache['ttl']:
            return jsonify(_license_cache['data'])
        
        licenses = license_select('licenses', '*', None, 'created_at', True) or []
        devices = license_select('license_devices', 'license_key') or []
        device_counts = {}
        for d in devices:
            key = d.get('license_key')
            device_counts[key] = device_counts.get(key, 0) + 1
        for lic in licenses:
            lic['device_count'] = device_counts.get(lic.get('key'), 0)
        
        result = {'success': True, 'licenses': licenses}
        _license_cache['data'] = result
        _license_cache['ts'] = now
        return jsonify(result)
        
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
    """Extend or reduce license expiry date"""
    try:
        if not get_license_db():
            return jsonify({'success': False, 'error': 'Supabase baglantisi yok'})
        
        data = request.get_json() or {}
        key = data.get('key', '').strip()
        days = int(data.get('days', 30))
        
        if not key:
            return jsonify({'success': False, 'error': 'Key gerekli'})
        
        if days == 0:
            return jsonify({'success': True, 'message': 'Degisiklik yok'})
        
        if abs(days) > 90:
            return jsonify({'success': False, 'error': 'Maksimum 90 gun eklenebilir/cikarilabilir'})
        
        lic = license_select('licenses', 'expires_at', {'key': key})
        if not lic:
            return jsonify({'success': False, 'error': 'Lisans bulunamadi'})
        
        from datetime import datetime, timedelta
        current_expires = lic[0].get('expires_at')
        
        try:
            exp_date = datetime.fromisoformat(current_expires.replace('Z', '+00:00').replace('+00:00', ''))
        except:
            exp_date = datetime.utcnow()
        
        now = datetime.utcnow()
        if days > 0 and exp_date < now:
            exp_date = now
        
        new_expires = exp_date + timedelta(days=days)
        
        if new_expires < now - timedelta(days=365):
            return jsonify({'success': False, 'error': 'Bitis tarihi cok eskiye ayarlanamaz'})
        
        update_data = {'expires_at': new_expires.isoformat()}
        if days > 0:
            update_data['status'] = 'active'
        
        result = license_update('licenses', update_data, {'key': key})
        
        if result:
            return jsonify({'success': True, 'new_expires': new_expires.isoformat()})
        else:
            return jsonify({'success': False, 'error': 'Guncelleme basarisiz'})
            
    except Exception as e:
        license_logging.error(f"Extend license error: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/licenses/update', methods=['POST'])
def update_license():
    """Update license email, telegram username, and membership"""
    try:
        if not get_license_db():
            return jsonify({'success': False, 'error': 'Supabase baglantisi yok'})
        
        data = request.get_json() or {}
        key = data.get('key', '').strip()
        email = data.get('email', '').strip()
        telegram_username = data.get('telegram_username', '').strip()
        telegram_membership = data.get('telegram_membership', False)
        
        if not key:
            return jsonify({'success': False, 'error': 'Key gerekli'})
        
        update_data = {
            'email': email or None,
            'telegram_username': telegram_username or None,
            'telegram_membership': telegram_membership
        }
        if 'plan' in data and data['plan'] in ('core', 'pro'):
            update_data['plan'] = data['plan']
        if 'max_devices' in data:
            md = int(data['max_devices'])
            if 1 <= md <= 10:
                update_data['max_devices'] = md
        
        result = license_update('licenses', update_data, {'key': key})
        
        if result:
            _license_cache['data'] = None
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Guncelleme basarisiz'})
            
    except Exception as e:
        license_logging.error(f"Update license error: {e}")
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
        
        license_delete('licenses', {'key': key})
        _license_cache['data'] = None
        return jsonify({'success': True})
        
    except Exception as e:
        license_logging.error(f"Delete license error: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/licenses/validate', methods=['POST'])
def validate_license():
    """Validate license for app activation"""
    try:
        if not get_license_db():
            return jsonify({'valid': False, 'error': 'Supabase baglantisi yok'})
        
        data = request.get_json() or {}
        key = data.get('key', '').strip()
        device_id = data.get('device_id', '').strip()[:16]  # varchar(16) limit
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
        try:
            devices = license_select('license_devices', 'device_id,id,activated_at', {'license_key': key}) or []
        except Exception as dev_err:
            print(f"[Validate] Device query error: {dev_err}")
            devices = []
        device_ids = [d.get('device_id') for d in devices]
        max_devices = license_data.get('max_devices', 1)
        
        if device_id in device_ids:
            if len(devices) > max_devices:
                sorted_devs = sorted(devices, key=lambda d: (d.get('activated_at') or '', d.get('id', 0)))
                allowed_ids = [d.get('device_id') for d in sorted_devs[-max_devices:]]
                if device_id not in allowed_ids:
                    try:
                        license_delete('license_devices', {'license_key': key, 'device_id': device_id})
                        print(f"[Validate] Over-limit cleanup: removed {device_id} for key={key[:8]}...")
                    except Exception:
                        pass
                    return jsonify({
                        'valid': False,
                        'error': 'Baska bir cihazdan giris yapildi, bu oturum sonlandirildi',
                        'device_limit': True
                    })
            
            license_update('license_devices', {
                'last_seen': datetime.utcnow().isoformat()
            }, {'license_key': key, 'device_id': device_id})
            
            session['license_valid'] = True
            session['license_key'] = key
            session['license_expires'] = expires_at or ''
            session['license_plan'] = license_data.get('plan') or 'core'
            session.permanent = True
            
            exp_dt = None
            if expires_at:
                try:
                    exp_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00').replace('+00:00', ''))
                except:
                    pass
            _validated_licenses[key] = {'expires': exp_dt, 'plan': license_data.get('plan') or 'core', 'cached_at': time.time()}
            
            return jsonify({
                'valid': True,
                'days_left': days_left,
                'expires_at': expires_at,
                'email': license_data.get('email'),
                'plan': license_data.get('plan') or 'core'
            })
        
        if len(device_ids) >= max_devices:
            sorted_devs = sorted(devices, key=lambda d: (d.get('activated_at') or '', d.get('id', 0)))
            devices_to_remove = sorted_devs[:len(devices) - max_devices + 1]
            for old_dev in devices_to_remove:
                old_did = old_dev.get('device_id')
                try:
                    license_delete('license_devices', {'license_key': key, 'device_id': old_did})
                    print(f"[Validate] Kicked old device: {old_did} for key={key[:8]}...")
                except Exception as del_err:
                    print(f"[Validate] Failed to kick device {old_did}: {del_err}")
        
        license_insert('license_devices', {
            'license_key': key,
            'device_id': device_id,
            'device_name': device_name or None
        })
        
        session['license_valid'] = True
        session['license_key'] = key
        session['license_expires'] = expires_at or ''
        session['license_plan'] = license_data.get('plan') or 'core'
        session.permanent = True
        
        exp_dt = None
        if expires_at:
            try:
                exp_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00').replace('+00:00', ''))
            except:
                pass
        _validated_licenses[key] = {'expires': exp_dt, 'plan': license_data.get('plan') or 'core', 'cached_at': time.time()}
        
        return jsonify({
            'valid': True,
            'days_left': days_left,
            'expires_at': expires_at,
            'email': license_data.get('email'),
            'new_device': True,
            'plan': license_data.get('plan') or 'core'
        })
        
    except Exception as e:
        license_logging.error(f"Validate license error: {e}")
        return jsonify({'valid': False, 'error': str(e)})

@app.route('/api/license/status', methods=['GET'])
def license_status():
    try:
        key = session.get('license_key') or request.headers.get('X-License-Key', '').strip()
        if not key:
            return jsonify({'valid': False, 'error': 'NO_KEY'}), 401
        
        device_id = (request.args.get('device_id', '') or request.headers.get('X-Device-Id', ''))[:16]
        
        if not get_license_db():
            return jsonify({'valid': False, 'error': 'DB_UNAVAILABLE'}), 500
        
        lic = license_select('licenses', 'expires_at,status,max_devices', {'key': key})
        if not lic:
            return jsonify({'valid': False, 'error': 'LICENSE_NOT_FOUND', 'days_left': 0}), 404
        
        license_data = lic[0]
        
        if license_data.get('status') == 'revoked':
            return jsonify({'valid': False, 'error': 'LICENSE_REVOKED', 'days_left': 0})
        
        from datetime import datetime
        now = datetime.utcnow()
        expires_at = license_data.get('expires_at')
        days_left = 9999
        
        if expires_at:
            try:
                exp_date = _parse_expires_naive(expires_at)
                if exp_date:
                    if exp_date < now:
                        return jsonify({'valid': False, 'error': 'LICENSE_EXPIRED', 'days_left': 0, 'expires_at': expires_at})
                    days_left = (exp_date - now).days
            except:
                days_left = 0
        
        if device_id:
            try:
                devices = license_select('license_devices', 'device_id,id,activated_at', {'license_key': key}) or []
            except Exception as dev_err:
                print(f"[LicenseStatus] Device query error: {dev_err}")
                devices = []
            device_ids = [d.get('device_id') for d in devices]
            max_devices = license_data.get('max_devices', 1)
            
            if device_id not in device_ids:
                if len(devices) >= max_devices:
                    return jsonify({'valid': False, 'error': 'DEVICE_KICKED', 'days_left': days_left, 'message': 'Baska bir cihazdan giris yapildi'})
        
        return jsonify({'valid': True, 'days_left': days_left, 'expires_at': expires_at})
    except Exception as e:
        return jsonify({'valid': False, 'error': str(e)}), 500

@app.route('/api/licenses/logout', methods=['POST'])
def license_logout():
    session.pop('license_valid', None)
    session.pop('license_key', None)
    session.pop('license_expires', None)
    session.pop('license_plan', None)
    return jsonify({'success': True})


@app.route('/api/test/activate', methods=['POST'])
def activate_test_mode():
    session['license_plan'] = 'test'
    session['license_valid'] = True
    session.permanent = True
    return jsonify({'success': True, 'plan': 'test'})


@app.route('/api/test/free-matches')
def get_free_matches():
    try:
        pinned = free_matches_config.get('hashes', [])
        if pinned:
            teams = free_matches_config.get('teams', [])
            print(f"[TestFree] Pinned hashes ({len(pinned)}): {pinned}")
            return jsonify({'hashes': pinned, 'teams': teams})
        cached, hit = get_cached_matches('moneyway_1x2_today_future')
        if not cached:
            cached, hit = get_cached_matches('moneyway_1x2_all')
        if not cached:
            cached, hit = get_cached_matches('dropping_1x2_today_future')
        if not cached:
            return jsonify({'hashes': [], 'teams': []})
        vol_map = {}
        team_map = {}
        for m in cached:
            h = m.get('match_id', '')
            if not h:
                continue
            if h not in vol_map:
                odds = m.get('odds', {})
                v_str = odds.get('Volume', '0')
                vol_map[h] = _parse_vol(v_str)
                team_map[h] = {'home': m.get('home_team', ''), 'away': m.get('away_team', '')}
        free_count = min(max(int(free_matches_config.get('free_count', 3)), 0), 5)
        sorted_matches = sorted(vol_map.items(), key=lambda x: x[1], reverse=True)
        top_hashes = [h for h, v in sorted_matches[:free_count]]
        teams = [team_map.get(h, {}) for h in top_hashes]
        print(f"[TestFree] Top {free_count} hashes (volume-based): {top_hashes}")
        return jsonify({'hashes': top_hashes, 'teams': teams})
    except Exception as e:
        print(f"[API] /api/test/free-matches hata: {e}")
        return jsonify({'hashes': [], 'teams': []})


def _parse_vol(v_str):
    if not v_str or v_str == '-':
        return 0
    s = str(v_str).replace('£', '').replace('$', '').replace('€', '').replace(',', '').replace(' ', '').strip()
    try:
        if s.upper().endswith('M'):
            return float(s[:-1]) * 1_000_000
        elif s.upper().endswith('K'):
            return float(s[:-1]) * 1_000
        return float(s)
    except:
        return 0


# ============================================
# ANALYTICS & HEARTBEAT SYSTEM
# ============================================

@app.route('/api/heartbeat', methods=['POST'])
def heartbeat():
    """App heartbeat - tracks online users"""
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


def _classify_subscription(duration_days, plan):
    """Classify license by duration_days and plan into subscription category"""
    plan = (plan or 'core').lower()
    d = duration_days or 30
    if d == 0:
        return f'{plan}_lifetime'
    elif d == 1:
        return 'free_trial'
    elif d == 3:
        return 'free_trial'
    elif d <= 7:
        return 'free_trial'
    elif d <= 14:
        return 'free_trial'
    elif d <= 30:
        return f'{plan}_monthly'
    elif d <= 90:
        return f'{plan}_quarterly'
    elif d <= 365:
        return f'{plan}_yearly'
    else:
        return f'{plan}_lifetime'

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
        
        _lic_cols = 'status,expires_at,duration_days,created_at,plan,price_paid,is_free'
        licenses = license_select('licenses', _lic_cols) or []
        if not licenses:
            # price_paid kolonu yoksa veya tablo boşsa; kolon olmadan tekrar dene
            _lic_cols_fb = 'status,expires_at,duration_days,created_at,plan,is_free'
            _test = license_select('licenses', _lic_cols_fb)
            if _test is not None and isinstance(_test, list) and len(_test) > 0:
                licenses = _test
        sessions = license_select('user_sessions', 'license_key,device_id,last_seen') or []
        devices = license_select('license_devices', 'license_key') or []
        
        price_map = _load_pricing()
        
        total_licenses = len(licenses)
        active_licenses = 0
        expired_licenses = 0
        new_today = 0
        new_this_week = 0
        new_this_month = 0
        expiring_soon = 0
        month_ago = now - timedelta(days=30)
        
        sub_counts = {
            'free_trial': 0,
            'core_monthly': 0, 'core_quarterly': 0, 'core_yearly': 0, 'core_lifetime': 0,
            'pro_monthly': 0, 'pro_quarterly': 0, 'pro_yearly': 0, 'pro_lifetime': 0
        }
        
        total_revenue = 0
        revenue_today = 0
        revenue_week = 0
        revenue_month = 0
        
        for lic in licenses:
            status = lic.get('status', 'active')
            expires_at = lic.get('expires_at')
            duration = lic.get('duration_days', 30)
            created_at = lic.get('created_at', '')
            plan = lic.get('plan', 'core')
            
            sub_type = _classify_subscription(duration, plan)
            if sub_type in sub_counts:
                sub_counts[sub_type] += 1
            
            if status == 'revoked':
                continue
            
            lic_price = 0
            if not lic.get('is_free', False) and sub_type != 'free_trial':
                price_paid = lic.get('price_paid')
                if price_paid is not None:
                    lic_price = float(price_paid)
                elif sub_type in price_map:
                    lic_price = price_map[sub_type].get('price', 0)
            total_revenue += lic_price
            
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
                    revenue_today += lic_price
                if created >= week_ago:
                    new_this_week += 1
                    revenue_week += lic_price
                if created >= month_ago:
                    new_this_month += 1
                    revenue_month += lic_price
            except:
                pass
        
        free_count = int(price_map.get('free_count', {}).get('price', 0))
        if free_count > 0:
            best_price = price_map.get('pro_monthly', {}).get('price', 0) or price_map.get('core_monthly', {}).get('price', 0)
            free_deduction = free_count * best_price
            total_revenue = max(0, total_revenue - free_deduction)
        
        online_users = 0
        for sess in sessions:
            try:
                last_seen = datetime.fromisoformat(sess.get('last_seen', '').replace('Z', '+00:00').replace('+00:00', ''))
                if last_seen >= five_min_ago:
                    online_users += 1
            except:
                pass
        
        total_devices = len(devices)
        
        return jsonify({
            'success': True,
            'data': {
                'total_licenses': total_licenses,
                'active_licenses': active_licenses,
                'expired_licenses': expired_licenses,
                'online_users': online_users,
                'total_devices': total_devices,
                'subscription_types': sub_counts,
                'new_today': new_today,
                'new_this_week': new_this_week,
                'new_this_month': new_this_month,
                'expiring_soon': expiring_soon,
                'total_revenue': total_revenue,
                'revenue_today': revenue_today,
                'revenue_week': revenue_week,
                'revenue_month': revenue_month,
                'pricing': price_map,
                'server_time': now.isoformat()
            }
        })
        
    except Exception as e:
        license_logging.error(f"Analytics dashboard error: {e}")
        return jsonify({'success': False, 'error': str(e)})


PRICING_FILE = os.path.join(os.path.dirname(__file__), 'pricing_config.json')

def _load_pricing():
    """Load pricing config from local JSON file"""
    try:
        if os.path.exists(PRICING_FILE):
            with open(PRICING_FILE, 'r') as f:
                data = json.load(f)
                if data:
                    return data
    except Exception as e:
        print(f'[Pricing] Load error: {e}')
    return {}

def _save_pricing_file(data):
    """Save pricing config to local JSON file"""
    with open(PRICING_FILE, 'w') as f:
        json.dump(data, f, indent=2)


@app.route('/api/pricing/get')
def get_pricing():
    """Get all pricing config"""
    try:
        return jsonify({'success': True, 'pricing': _load_pricing()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/pricing/save', methods=['POST'])
def save_pricing():
    """Save pricing config"""
    try:
        data = request.get_json() or {}
        plan_key = data.get('plan_key', '').strip()
        price = float(data.get('price', 0))
        
        if not plan_key:
            return jsonify({'success': False, 'error': 'plan_key gerekli'})
        
        from datetime import datetime
        now = datetime.utcnow().isoformat()
        
        previous_pricing = _load_pricing()
        pricing = dict(previous_pricing)
        pricing[plan_key] = {
            'price': price,
            'updated_at': now
        }
        _save_pricing_file(pricing)
        
        return jsonify({'success': True})
    except Exception as e:
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


_payment_spam_cache = {}

def _send_payment_telegram(order_no, plan_name, price, full_name, email):
    import requests as _req
    bot_token = os.environ.get('PAYMENT_BOT_TOKEN')
    chat_id = os.environ.get('PAYMENT_CHAT_ID')
    if not bot_token or not chat_id:
        print("[Payment TG] PAYMENT_BOT_TOKEN or PAYMENT_CHAT_ID not set, skipping.")
        return
    from datetime import datetime
    import pytz
    now_tr = datetime.now(pytz.timezone('Europe/Istanbul')).strftime('%d.%m.%Y %H:%M')
    text = (
        f"💰 <b>Yeni Ödeme Talebi</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📋 <b>Sipariş No:</b> <code>{order_no}</code>\n"
        f"📦 <b>Paket:</b> {plan_name}\n"
        f"💵 <b>Tutar:</b> {price}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Ad Soyad:</b> {full_name}\n"
        f"📧 <b>E-posta:</b> {email}\n"
        f"🕐 <b>Tarih:</b> {now_tr}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ SmartXFlow Ödeme Sistemi"
    )
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    resp = _req.post(url, json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'}, timeout=10)
    if resp.status_code == 200:
        print(f"[Payment TG] Notification sent for {order_no}")
    else:
        print(f"[Payment TG] Failed: {resp.status_code} {resp.text}")

@app.route('/api/payment-request', methods=['POST'])
def payment_request():
    import re, time as _time
    from datetime import datetime
    import pytz
    try:
        tr_tz = pytz.timezone('Europe/Istanbul')
        tr_now = datetime.now(tr_tz)
        if tr_now.hour < 10 or tr_now.hour >= 19:
            return jsonify({'status': 'error', 'message': 'Satın alma işlemleri yalnızca 10:00 – 19:00 (Türkiye saati) arasında yapılabilir.'}), 403

        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'Geçersiz istek.'}), 400

        plan_id = (data.get('plan_id') or '').strip()
        plan_name = (data.get('plan_name') or '').strip()
        price = (data.get('price') or '').strip()
        payment_ref = (data.get('payment_ref') or '').strip()
        order_no = (data.get('order_no') or '').strip()
        full_name = (data.get('full_name') or '').strip()
        email = (data.get('email') or '').strip().lower()

        if not all([plan_id, plan_name, price, full_name, email]):
            return jsonify({'status': 'error', 'message': 'Tüm alanları doldurunuz.'}), 400

        if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
            return jsonify({'status': 'error', 'message': 'Geçerli bir e-posta giriniz.'}), 400

        spam_key = f"{email}|{payment_ref}"
        now = _time.time()
        if spam_key in _payment_spam_cache and (now - _payment_spam_cache[spam_key]) < 60:
            return jsonify({'status': 'error', 'message': 'Bu talep zaten gönderildi. 1 dakika bekleyiniz.'}), 429

        _payment_spam_cache[spam_key] = now

        old_keys = [k for k, v in _payment_spam_cache.items() if (now - v) > 300]
        for k in old_keys:
            del _payment_spam_cache[k]

        print(f"[Payment] New request: {order_no} | {plan_name} | {price} | {full_name} | {email}")

        try:
            sb = get_supabase_client()
            if sb and sb.is_available:
                import httpx as _httpx
                url = f"{sb._rest_url('payment_requests')}"
                resp = _httpx.post(url, headers=sb._headers(), json={
                    'plan_id': plan_id,
                    'plan_name': plan_name,
                    'price': price,
                    'payment_ref': payment_ref,
                    'order_no': order_no,
                    'full_name': full_name,
                    'email': email,
                    'status': 'pending'
                }, timeout=10)
                if resp.status_code in (200, 201):
                    print(f"[Payment] Saved to Supabase: {order_no}")
                else:
                    print(f"[Payment] Supabase insert failed: {resp.status_code} {resp.text}")
        except Exception as db_err:
            print(f"[Payment] Supabase insert failed (non-critical): {db_err}")

        import threading
        def _tg_async():
            try:
                _send_payment_telegram(order_no, plan_name, price, full_name, email)
            except Exception as tg_err:
                print(f"[Payment] Telegram notification failed (non-critical): {tg_err}")
        threading.Thread(target=_tg_async, daemon=True).start()

        return jsonify({'status': 'ok', 'message': 'Talep alındı.'})
    except Exception as e:
        print(f"[Payment] Error: {e}")
        return jsonify({'status': 'error', 'message': 'Bir hata oluştu.'}), 500


@app.route('/api/admin/orders', methods=['GET'])
def get_admin_orders():
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        sb = get_supabase_client()
        if not sb or not sb.is_available:
            return jsonify({'orders': [], 'error': 'Supabase not available'})
        import httpx as _httpx
        url = f"{sb._rest_url('payment_requests')}?select=*&order=created_at.desc"
        resp = _httpx.get(url, headers=sb._headers(), timeout=10)
        if resp.status_code == 200:
            return jsonify({'orders': resp.json()})
        else:
            print(f"[Admin Orders] Supabase error: {resp.status_code} {resp.text}")
            return jsonify({'orders': [], 'error': f'HTTP {resp.status_code}'})
    except Exception as e:
        print(f"[Admin Orders] Error: {e}")
        return jsonify({'orders': [], 'error': str(e)})


@app.route('/api/admin/orders/update-status', methods=['POST'])
def update_order_status():
    if not session.get('admin_authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        data = request.get_json()
        order_no = (data.get('order_no') or '').strip()
        status = (data.get('status') or '').strip()
        if not order_no or status not in ('approved', 'rejected'):
            return jsonify({'success': False, 'error': 'Geçersiz parametre.'}), 400
        sb = get_supabase_client()
        if not sb or not sb.is_available:
            return jsonify({'success': False, 'error': 'Supabase not available'}), 500
        import httpx as _httpx
        from urllib.parse import quote
        url = f"{sb._rest_url('payment_requests')}?order_no=eq.{quote(order_no)}"
        resp = _httpx.patch(url, headers=sb._headers(), json={'status': status}, timeout=10)
        if resp.status_code in (200, 204):
            print(f"[Orders] Status updated: {order_no} -> {status}")
            return jsonify({'success': True})
        else:
            print(f"[Orders] Status update failed: {resp.status_code} {resp.text}")
            return jsonify({'success': False, 'error': f'HTTP {resp.status_code}'}), 500
    except Exception as e:
        print(f"[Orders] Status update error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def _send_watchdog_telegram(message: str, is_error: bool = True) -> bool:
    import requests as _req
    bot_token = os.environ.get('PAYMENT_BOT_TOKEN')
    chat_id = os.environ.get('PAYMENT_CHAT_ID')
    if not bot_token or not chat_id:
        print("[Watchdog] Telegram Token/ChatID eksik")
        return False
    try:
        emoji = "\U0001f534" if is_error else "\U0001f7e2"
        url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
        data = {'chat_id': chat_id, 'text': f"{emoji} {message}", 'parse_mode': 'HTML'}
        r = _req.post(url, data=data, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"[Watchdog] Telegram hata: {e}")
        return False

def _get_last_scrape_time():
    import requests as _req
    supabase_url = os.environ.get('SUPABASE_URL')
    supabase_key = os.environ.get('SUPABASE_ANON_KEY')
    if not supabase_url or not supabase_key:
        return None
    try:
        headers = {"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"}
        url = f"{supabase_url}/rest/v1/scraper_signal?source=eq.replit&order=created_at.desc&limit=1&select=created_at"
        r = _req.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data:
                from datetime import datetime as _dt
                ts = data[0]['created_at']
                if ts.endswith('Z'):
                    ts = ts[:-1] + '+00:00'
                return _dt.fromisoformat(ts)
    except Exception as e:
        print(f"[Watchdog] Son scrape zamanı alınamadı: {e}")
    return None



def _is_production():
    return bool(os.environ.get('REPLIT_DEPLOYMENT') or os.environ.get('REPL_DEPLOYMENT'))


def _initialize_server():
    host = '0.0.0.0'
    port = 5000
    mode_name = "CLIENT" if is_client_mode() else "SERVER"

    print("=" * 50, flush=True)
    print("SmartXFlow Monitor", flush=True)
    print("=" * 50, flush=True)
    print(f"Mode: {mode_name}", flush=True)
    print(f"Supabase: {'Connected' if db.is_supabase_available else 'Not Connected'}", flush=True)
    print(f"Templates path: {template_dir}", flush=True)
    print(f"Static path: {static_dir}", flush=True)
    print(f"Templates exist: {os.path.exists(template_dir)}", flush=True)
    print(f"Static exist: {os.path.exists(static_dir)}", flush=True)
    print("=" * 50, flush=True)

    if is_server_mode():
        start_server_scheduler()
        if not _is_production():
            start_cleanup_scheduler()
        start_alarm_scheduler()
        print("[Init] Web-only mode - scraper/alarm managed by run_services.sh", flush=True)

    if is_client_mode():
        host = '127.0.0.1'
        is_desktop = os.environ.get('SMARTX_DESKTOP') == '1'
        if not is_desktop:
            import webbrowser
            webbrowser.open(f'http://127.0.0.1:{port}')

    return host, port


def main():
    """Main entry point - Flask web server on 0.0.0.0:5000"""
    try:
        host, port = _initialize_server()

        if _is_production():
            print(f"[Production] Starting gunicorn on {host}:{port}...", flush=True)
            try:
                from gunicorn.app.base import BaseApplication

                class SmartXFlowApp(BaseApplication):
                    def __init__(self, flask_app, options=None):
                        self.options = options or {}
                        self.application = flask_app
                        super().__init__()

                    def load_config(self):
                        for key, value in self.options.items():
                            if key in self.cfg.settings and value is not None:
                                self.cfg.set(key.lower(), value)

                    def load(self):
                        return self.application

                def _try_acquire_cleanup_lock(pid):
                    lock_file = '/tmp/smartxflow_cleanup.lock'
                    try:
                        fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                        os.write(fd, str(pid).encode())
                        os.close(fd)
                        return True
                    except FileExistsError:
                        try:
                            with open(lock_file, 'r') as _lf:
                                owner_pid = int(_lf.read().strip())
                            try:
                                os.kill(owner_pid, 0)
                                return False
                            except ProcessLookupError:
                                os.remove(lock_file)
                                return _try_acquire_cleanup_lock(pid)
                        except Exception:
                            return False
                    except Exception:
                        return False

                def post_worker_init(worker):
                    import random as _rnd
                    delay = _rnd.uniform(0, 3)
                    print(f"[Gunicorn] Worker {worker.pid} started, warmup delay={delay:.1f}s...", flush=True)
                    time.sleep(delay)
                    if _try_acquire_cleanup_lock(worker.pid):
                        print(f"[Gunicorn] Worker {worker.pid} acquired cleanup lock, starting scheduler...", flush=True)
                        start_cleanup_scheduler()
                    else:
                        print(f"[Gunicorn] Worker {worker.pid} skipping cleanup scheduler (another worker owns it)", flush=True)
                    print(f"[Gunicorn] Worker {worker.pid} triggering eager warmup...", flush=True)
                    trigger_app_warmup()

                def worker_exit(server, worker):
                    print(f"[Gunicorn] Worker {worker.pid} exiting gracefully...", flush=True)
                    for lf_path, lf_name in [
                        ('/tmp/smartxflow_cleanup.lock', 'cleanup'),
                        ('/tmp/smartxflow_warmup.lock', 'warmup'),
                    ]:
                        try:
                            with open(lf_path, 'r') as _lf:
                                owner_pid = int(_lf.read().strip())
                            if owner_pid == worker.pid:
                                os.remove(lf_path)
                                print(f"[Gunicorn] Worker {worker.pid} released {lf_name} lock", flush=True)
                        except Exception:
                            pass

                options = {
                    'bind': f'{host}:{port}',
                    'workers': 2,
                    'threads': 4,
                    'timeout': 300,
                    'graceful_timeout': 30,
                    'max_requests': 5000,
                    'max_requests_jitter': 500,
                    'preload_app': True,
                    'worker_class': 'gthread',
                    'accesslog': '-',
                    'errorlog': '-',
                    'loglevel': 'info',
                    'post_worker_init': post_worker_init,
                    'worker_exit': worker_exit,
                }
                SmartXFlowApp(app, options).run()
            except ImportError:
                print("[Production] gunicorn not available, falling back to Flask dev server", flush=True)
                app.run(host=host, port=port, debug=False)
        else:
            print(f"Starting Flask on http://{host}:{port}...", flush=True)
            trigger_app_warmup()
            app.run(host=host, port=port, debug=False)
    except OSError as e:
        if "10048" in str(e) or "Address already in use" in str(e):
            print(f"[FATAL] Port {port} kullanımda! 15s bekleyip tekrar denenecek...", flush=True)
            time.sleep(15)
            try:
                app.run(host=host, port=port, debug=False)
            except Exception as e2:
                print(f"[FATAL] Port {port} hala kullanımda: {e2}", flush=True)
                sys.exit(1)
        else:
            raise
    except Exception as e:
        import traceback
        print("FATAL ERROR:", str(e), flush=True)
        traceback.print_exc()
        print("[Recovery] 10s sonra yeniden başlatılıyor...", flush=True)
        time.sleep(10)
        try:
            app.run(host=host, port=port, debug=False)
        except Exception as e2:
            print(f"[Recovery] İkinci deneme de başarısız: {e2}", flush=True)
            sys.exit(1)


if __name__ == '__main__':
    main()
