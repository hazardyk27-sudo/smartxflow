Warning: truncated output (original token count: 125360)
Total output lines: 11636

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
import mimetypes
mimetypes.init()
from functools import wraps
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, jsonify, request, Response, send_from_directory, session, redirect, make_response, g, url_for

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

_poly_tracked_cache = {'data': None, 'ts': 0}
_poly_profile_cache = {}
_poly_profile_inflight = {}   # wallet_key -> threading.Event (in-flight dedup)
_poly_profile_inflight_lock = threading.Lock()
POLY_CACHE_TTL = 120       # profil cache: scraper senkronizasyonundan sonra en fazla 2 dk eski
POLY_LIST_CACHE_TTL = 30   # liste cache: 30 saniye (Hetzner güncellemelerini hızlı yansıt)

_cm_signals_cache = None
_cm_signals_cache_time = 0
CM_SIGNALS_CACHE_TTL = 60
CM_ODDS_DROP_PCT = 0.05  # %5 düşüş eşiği — sinyal_engine.py ile aynı

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
from services.polymarket_client import (
    get_today_matches as poly_get_today_matches,
    search_matches as poly_search_matches,
    get_top_trades as poly_get_top_trades,
    get_stored_trades as poly_get_stored_trades,
    list_tracked_wallets_with_stats as poly_list_tracked_wallets,
    add_tracked_wallet as poly_add_tracked_wallet,
    update_tracked_wallet as poly_update_tracked_wallet,
    remove_tracked_wallet as poly_remove_tracked_wallet,
    get_wallet_profile as poly_get_wallet_profile,
    TRACKED_WALLET_API_CONTRACT_VERSION as POLY_TRACKED_CONTRACT_VERSION,
)
from services import auth_helpers
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

@app.context_processor
def inject_asset_version():
    def asset_v(rel_path):
        try:
            return str(int(os.path.getmtime(os.path.join(static_dir, rel_path))))
        except Exception:
            return '1'
    return {'asset_v': asset_v}

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
_LICENSE_DISK_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.license_cache_local.json')

def _save_license_cache():
    """Persist validated licenses to disk so they survive restarts."""
    try:
        data = {}
        for k, v in _validated_licenses.items():
            exp = v.get('expires')
            if exp and exp > datetime.utcnow():
                data[k] = {
                    'expires': exp.isoformat(),
                    'plan': v.get('plan', 'core'),
                }
        with open(_LICENSE_DISK_CACHE, 'w') as fh:
            json.dump(data, fh)
    except Exception:
        pass

def _load_license_cache():
    """Load persisted license cache on startup (pre-populates in-memory dict)."""
    try:
        if not os.path.exists(_LICENSE_DISK_CACHE):
            return
        with open(_LICENSE_DISK_CACHE, 'r') as fh:
            data = json.load(fh)
        now = datetime.utcnow()
        loaded = 0
        for k, v in data.items():
            try:
                exp_dt = datetime.fromisoformat(v['expires'])
                if exp_dt > now:
                    _validated_licenses[k] = {
                        'expires': exp_dt,
                        'plan': v.get('plan', 'core'),
                        'cached_at': 0,  # force re-validation on next TTL check
                    }
                    loaded += 1
            except Exception:
                pass
        if loaded:
            print(f"[License Cache] Loaded {loaded} entries from disk cache")
    except Exception:
        pass

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
        if lic_data is None:
            # Network error — license_select couldn't reach Supabase
            if key in _validated_licenses:
                _validated_licenses[key]['cached_at'] = time.time()
                print(f"[LicenseRefresh] Network error, extending cache for {key[:8]}... (grace)")
                return None
            print(f"[LicenseRefresh] Network error, no prior cache for {key[:8]}... -> REQUIRED")
            return 'LICENSE_REQUIRED'
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
                    _save_license_cache()
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

# ============================================
# ACCOUNT SESSION CACHE (Supabase Auth) — replaces the old license-key cache.
# Short TTL so we don't call Supabase Auth's API on every single request.
# ============================================
_validated_sessions = {}
_ACCOUNT_SESSION_TTL = 60
_ACCOUNT_MAX_ENTRIES = 200

def _purge_session_cache():
    now = time.time()
    expired = [k for k, v in list(_validated_sessions.items()) if (now - v.get('cached_at', 0)) > _ACCOUNT_SESSION_TTL * 5]
    for k in expired:
        _validated_sessions.pop(k, None)
    if len(_validated_sessions) > _ACCOUNT_MAX_ENTRIES:
        sorted_keys = sorted(_validated_sessions.keys(), key=lambda k: _validated_sessions[k].get('cached_at', 0))
        for k in sorted_keys[:len(_validated_sessions) - _ACCOUNT_MAX_ENTRIES]:
            _validated_sessions.pop(k, None)

def _account_block(error, message, status=403):
    if not request.path.startswith('/api/') and 'text/html' in request.headers.get('Accept', ''):
        next_path = request.path
        if error == 'LOGIN_REQUIRED':
            return redirect(f'/login?next={next_path}')
        if error == 'EMAIL_NOT_VERIFIED':
            return redirect('/verify-email')
        if error == 'MEMBERSHIP_REQUIRED':
            return redirect('/membership-required')
        return redirect(f'/login?next={next_path}')
    return jsonify({'error': error, 'message': message}), status

def _legacy_license_session_valid():
    """Temporary compatibility bridge for users who still use a license key.

    This is deliberately kept separate from the account session. It allows the
    old client to continue working during the migration window without making
    license keys a fallback for the new account login flow.
    """
    key = (session.get('license_key') or request.headers.get('X-License-Key', '')).strip()
    if not key:
        return False
    cached = _validated_licenses.get(key)
    now = datetime.utcnow()
    if cached:
        expires = cached.get('expires')
        if not expires or expires > now:
            if time.time() - cached.get('cached_at', 0) <= _LICENSE_CACHE_TTL:
                return True
    try:
        rows = license_select('licenses', 'plan,status,expires_at', {'key': key})
        if not rows:
            return False
        license_data = rows[0]
        if license_data.get('status') == 'revoked':
            return False
        expires_at = license_data.get('expires_at')
        expires = _parse_expires_naive(expires_at) if expires_at else None
        if expires and expires <= now:
            return False
        _validated_licenses[key] = {
            'expires': expires,
            'plan': license_data.get('plan') or 'core',
            'cached_at': time.time(),
        }
        return True
    except Exception:
        # Existing validated licenses may continue during a transient DB outage.
        cached = _validated_licenses.get(key)
        return bool(cached and (not cached.get('expires') or cached['expires'] > now))

def resolve_account_session():
    """
    Validates the current Flask session against Supabase Auth (with a short TTL cache)
    and returns (user, profile) or (None, None) if there is no valid, verified,
    active-membership session. Transparently refreshes an expired access token using
    the stored refresh token before giving up.
    """
    access_token = session.get('sb_access_token')
    refresh_token = session.get('sb_refresh_token')
    if not access_token:
        return None, None

    cached = _validated_sessions.get(access_token)
    if cached and (time.time() - cached.get('cached_at', 0)) <= _ACCOUNT_SESSION_TTL:
        return cached['user'], cached['profile']

    user = auth_helpers.get_user_from_token(access_token)
    if user is None and refresh_token:
        refreshed = auth_helpers.refresh_session(refresh_token)
        if refreshed.get('ok'):
            session['sb_access_token'] = refreshed['access_token']
            session['sb_refresh_token'] = refreshed['refresh_token']
            access_token = refreshed['access_token']
            user = auth_helpers.get_user_from_token(access_token)

    if user is None:
        session.pop('sb_access_token', None)
        session.pop('sb_refresh_token', None)
        return None, None

    profile = auth_helpers.get_or_create_profile(user['id'], user['email'])
    _validated_sessions[access_token] = {'user': user, 'profile': profile, 'cached_at': time.time()}
    if len(_validated_sessions) > _ACCOUNT_MAX_ENTRIES:
        _purge_session_cache()
    return user, profile

def license_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if os.environ.get('SMARTX_DESKTOP') == '1':
            return f(*args, **kwargs)

        # Free-trial "test mode" is an anonymous trial toggle, not part of the
 …113360 tokens truncated…
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
    """Legacy license-key activation screen retired in favor of /login (Supabase account auth)."""
    return redirect('/login')

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

    _load_license_cache()

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
                    'workers': 1,
                    'threads': 8,
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

