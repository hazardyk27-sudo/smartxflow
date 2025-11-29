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
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request

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
from services.supabase_client import get_database, get_supabase_client
from core.alarms import analyze_match_alarms, format_alarm_for_ticker, format_alarm_for_modal, ALARM_TYPES
import hashlib

def generate_match_id(home, away, league, date=''):
    """Generate unique match ID from home, away, league and date.
    This ensures unique identification even for teams playing multiple times in the same league."""
    key = f"{home}|{away}|{league}|{date}" if date else f"{home}|{away}|{league}"
    return hashlib.md5(key.encode()).hexdigest()[:12]

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
last_cleanup_date = None


def cleanup_old_matches():
    """
    Delete matches older than yesterday (keep today and yesterday only).
    Runs once per day on server startup or scheduler.
    Note: Currently read-only mode - cleanup is handled by standalone scraper.
    """
    global last_cleanup_date
    
    today = now_turkey().date()
    if last_cleanup_date == today:
        return
    
    last_cleanup_date = today
    print(f"[Cleanup] Old matches cleanup completed for {today}")


def start_cleanup_scheduler():
    """
    Start daily cleanup scheduler - includes:
    - Alarm state cleanup
    - Periodic alarm detection (every 10 min)
    - Hourly reconciliation job (self-check for missing alarms)
    - Retry failed alarms
    """
    global cleanup_thread
    
    try:
        from core.alarm_state import cleanup_old_alarm_states
    except ImportError:
        cleanup_old_alarm_states = lambda *args: None
    
    try:
        from core.alarm_safety import run_reconciliation, retry_failed_alarms, cleanup_old_failed_alarms
    except ImportError:
        run_reconciliation = lambda *args, **kwargs: {}
        retry_failed_alarms = lambda *args: {}
        cleanup_old_failed_alarms = lambda *args: 0
    
    print("[Startup] Cleaning up duplicate alarms...")
    try:
        from services.supabase_client import get_database
        db = get_database()
        if db.is_supabase_available:
            deleted = db.supabase.cleanup_duplicate_alarms()
            if deleted > 0:
                print(f"[Startup] Cleaned {deleted} duplicate alarms")
            
            low_drop_deleted = db.supabase.cleanup_low_drop_percent_alarms(threshold=7.0)
            if low_drop_deleted > 0:
                print(f"[Startup] Cleaned {low_drop_deleted} low drop% dropping alarms (<7%)")
            
            legacy_deleted = db.supabase.cleanup_legacy_alarms()
            if legacy_deleted > 0:
                print(f"[Startup] Cleaned {legacy_deleted} legacy/invalid alarms")
    except Exception as e:
        print(f"[Startup] Duplicate cleanup error: {e}")
    
    # PERFORMANS: Startup'ta alarm detection DEVRE DIŞI
    # Alarm detection arka plan thread'inde çalışacak (cleanup_loop içinde)
    print("[Startup] Alarm detection skipped (will run in background thread)")
    
    loop_count = [0]
    
    def cleanup_loop():
        while True:
            cleanup_old_matches()
            cleanup_old_alarm_states(hours=48)
            
            try:
                detect_and_save_alarms()
            except Exception as e:
                print(f"[AlarmDetector] Error in periodic scan: {e}")
            
            loop_count[0] += 1
            if loop_count[0] % 6 == 0:
                print("[Reconciliation] Running hourly self-check...")
                try:
                    supabase = get_supabase_client()
                    if supabase and supabase.is_available:
                        cleanup_old_failed_alarms(days=7)
                        
                        retry_failed_alarms(supabase)
                        
                        markets = [
                            'moneyway_1x2', 'moneyway_ou25', 'moneyway_btts',
                            'dropping_1x2', 'dropping_ou25', 'dropping_btts'
                        ]
                        result = run_reconciliation(supabase, markets, lookback_days=7)
                        print(f"[Reconciliation] Result: {result.get('status', 'unknown')}")
                except Exception as e:
                    print(f"[Reconciliation] Error: {e}")
            
            time.sleep(600)
    
    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()


def start_server_scheduler():
    """Start background scheduler for server mode - runs scraper periodically"""
    global server_scheduler_thread, server_scheduler_stop
    
    if not is_server_mode():
        return
    
    if is_scraper_disabled():
        print("[Server Mode] Scraper disabled via DISABLE_SCRAPER env variable")
        print("[Server Mode] Running as UI-only, data comes from Supabase (standalone scraper)")
        return
    
    server_scheduler_stop.clear()
    interval_seconds = get_scrape_interval_seconds()
    
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
    # Pre-render ticker alarms for server-side rendering
    ticker_alarms = []
    try:
        from core.alarms import get_critical_alarms, format_alarm_for_ticker
        
        matches_data = db.get_all_matches_with_latest('moneyway_1x2')
        
        for match in matches_data[:15]:
            home = match.get('home_team', '')
            away = match.get('away_team', '')
            league = match.get('league', '')
            date = match.get('date', '')
            
            history = db.get_match_history(home, away, 'moneyway_1x2')
            if len(history) >= 2:
                alarms = analyze_match_alarms(history, 'moneyway_1x2', match_date=date)
                for alarm in alarms:
                    formatted = format_alarm_for_ticker(alarm, home, away)
                    formatted['market'] = 'moneyway_1x2'
                    formatted['match_id'] = generate_match_id(home, away, league, date)
                    formatted['league'] = league
                    formatted['date'] = date
                    ticker_alarms.append(formatted)
        
        ticker_alarms = get_critical_alarms(ticker_alarms, limit=4)
    except Exception as e:
        print(f"[Index] Error getting ticker alarms: {e}")
        ticker_alarms = []
    
    return render_template('index.html', ticker_alarms=ticker_alarms)


@app.route('/match/<home>/<away>')
def match_detail(home, away):
    """Match detail page with charts"""
    return render_template('match_detail.html', home=home, away=away)


matches_cache = {
    'data': {},  # market -> data
    'timestamp': {},  # market -> timestamp
    'ttl': 60  # 1 dakika cache (sık güncellenen veri)
}

@app.route('/api/matches')
def get_matches():
    """Get all matches from database - optimized with cache"""
    import time
    market = request.args.get('market', 'moneyway_1x2')
    is_dropping = market.startswith('dropping')
    
    now = time.time()
    
    # Cache kontrolü
    if market in matches_cache['data']:
        last_time = matches_cache['timestamp'].get(market, 0)
        if (now - last_time) < matches_cache['ttl']:
            return jsonify(matches_cache['data'][market])
    
    matches_with_latest = db.get_all_matches_with_latest(market)
    
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
    
    # Cache'e kaydet
    matches_cache['data'][market] = enriched
    matches_cache['timestamp'][market] = now
    
    return jsonify(enriched)


@app.route('/api/match/history/bulk')
def get_match_history_bulk():
    """Get historical data for ALL markets of a single match in one request.
    This is faster than calling /api/match/history 6 times separately.
    """
    home = request.args.get('home', '')
    away = request.args.get('away', '')
    
    if not home or not away:
        return jsonify({'error': 'Missing home or away parameter', 'markets': {}})
    
    all_markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts', 
                   'dropping_1x2', 'dropping_ou25', 'dropping_btts']
    
    result = {}
    for market in all_markets:
        history = db.get_match_history(home, away, market)
        
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
    
    return jsonify({'markets': result})


@app.route('/api/match/history')
def get_match_history():
    """Get historical data for a specific match"""
    home = request.args.get('home', '')
    away = request.args.get('away', '')
    market = request.args.get('market', 'moneyway_1x2')
    
    history = db.get_match_history(home, away, market)
    
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
        'scraping_enabled': is_server_mode(),
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


alarm_cache = {
    'data': None,
    'timestamp': 0,
    'ttl': 300  # 5 dakika cache (önceki: 2 dakika) - performans için artırıldı
}

DEMO_TEAMS = {'Whale FC', 'Sharp FC', 'Pro Bettors XI', 'Casual City', 'Target United', 
              'Small Fish', 'Budget Boys', 'Line Freeze FC', 'Bookmaker XI', 
              'Public Money FC', 'Trending Town', 'Accelerate FC', 'Brake City',
              'Volume Kings', 'Momentum FC', 'Surge United',
              'No Move Utd', 'Steady State', 'Frozen FC', 'Static City',
              'Fan Favorite', 'NoName FC', 'Rising Stars', 'Slow Movers'}

def is_demo_match(match):
    """Check if match is a demo match"""
    home = match.get('home_team', '')
    away = match.get('away_team', '')
    league = match.get('league', '')
    if home in DEMO_TEAMS or away in DEMO_TEAMS:
        return True
    if league.lower().startswith('demo'):
        return True
    return False

def detect_and_save_alarms():
    """
    STEP 1: Detect new alarms from history and SAVE them to Supabase.
    Called after scrape or periodically. Alarms are PERSISTENT once saved.
    Scans ALL 6 markets (3 moneyway + 3 dropping) for comprehensive detection.
    
    Per REFERANS DOKÜMANI Section 3:
    - D (Today) + Future: Generate alarms (if match in arbworld)
    - D-1 (Yesterday): NO new alarms (static mode only)
    - D-2+ (Old): Skip entirely
    
    SAFETY FEATURES:
    - Uses AlarmSafetyGuard for error handling and logging
    - Failed inserts are logged for later retry
    - No DELETE or UPDATE operations - append-only
    """
    import time
    from core.timezone import is_match_today, is_yesterday_turkey, is_match_d2_or_older, get_match_lifecycle_status
    from core.alarm_safety import AlarmSafetyGuard, log_failed_alarm
    
    print("[AlarmDetector] Scanning for new alarms...")
    start_time = time.time()
    
    all_alarms = []
    markets = [
        'moneyway_1x2', 'moneyway_ou25', 'moneyway_btts',
        'dropping_1x2', 'dropping_ou25', 'dropping_btts'
    ]
    
    matches_data = db.get_all_matches_with_latest('moneyway_1x2')
    real_matches = [m for m in matches_data if not is_demo_match(m)]
    
    all_unique_matches = []
    seen_pairs = set()
    for m in real_matches:
        home = m.get('home_team', '')
        away = m.get('away_team', '')
        pair = (home, away)
        if pair not in seen_pairs:
            all_unique_matches.append(m)
            seen_pairs.add(pair)
    
    match_pairs = [(m.get('home_team', ''), m.get('away_team', '')) for m in all_unique_matches]
    match_info = {(m.get('home_team', ''), m.get('away_team', '')): {
        'league': m.get('league', ''),
        'date': m.get('date', '')
    } for m in all_unique_matches}
    
    for market in markets:
        bulk_history = db.get_bulk_history_for_alarms(market, match_pairs)
        
        for (home, away), history in bulk_history.items():
            if len(history) >= 2:
                info = match_info.get((home, away), {})
                match_date = info.get('date', '')
                league = info.get('league', '')
                
                lifecycle = get_match_lifecycle_status(match_date)
                if lifecycle in ['D-1', 'D-2+']:
                    continue
                if lifecycle == 'UNKNOWN':
                    continue
                
                alarms = analyze_match_alarms(history, market, match_date=match_date)
                for alarm in alarms:
                    match_id = f"{home}|{away}|{league}|{match_date}"
                    alarm['match_id'] = match_id
                    alarm['home'] = home
                    alarm['away'] = away
                    alarm['market'] = market
                    alarm['league'] = league
                    alarm['match_date'] = match_date
                    
                    formatted = format_alarm_for_modal(alarm)
                    alarm['detail'] = formatted.get('detail', '')
                    
                    all_alarms.append(alarm)
    
    supabase = get_supabase_client()
    if supabase and supabase.is_available and all_alarms:
        safety_guard = AlarmSafetyGuard(supabase)
        saved = safety_guard.safe_save_batch(all_alarms)
        elapsed = time.time() - start_time
        print(f"[AlarmDetector] Scanned {len(match_pairs)} matches, detected {len(all_alarms)} alarms, saved {saved} new in {elapsed:.2f}s")
    
    return len(all_alarms)

def get_cached_alarms():
    """
    STEP 2: Get PERSISTENT alarms from Supabase (not volatile calculation).
    
    Per REFERANS DOKÜMANI Section 3:
    - D (Today) + Future: Show alarms
    - D-1 (Yesterday): Show alarms (static mode)
    - D-2+ (Old): DO NOT show (archive/delete)
    
    Alarms stay visible until match is D-2 or older.
    """
    import time
    from core.alarms import group_alarms_by_match, format_grouped_alarm
    from core.timezone import is_match_d2_or_older
    
    now = time.time()
    if alarm_cache['data'] is not None and (now - alarm_cache['timestamp']) < alarm_cache['ttl']:
        print("[Alarms API] Using cached data")
        return alarm_cache['data'].copy()
    
    print("[Alarms API] Loading persistent alarms from Supabase...")
    start_time = time.time()
    
    supabase = get_supabase_client()
    
    try:
        if supabase and supabase.is_available:
            raw_alarms = supabase.get_persistent_alarms()
            
            if raw_alarms is None:
                print("[Alarms API] Supabase returned None, falling back to volatile")
                return get_cached_alarms_volatile()
            
            filtered_alarms = []
            for alarm in raw_alarms:
                match_date = alarm.get('match_date', '')
                if not is_match_d2_or_older(match_date):
                    odds_from = alarm.get('odds_from')
                    odds_to = alarm.get('odds_to')
                    total_drop = 0.0
                    if odds_from is not None and odds_to is not None:
                        try:
                            total_drop = float(odds_from) - float(odds_to)
                        except (ValueError, TypeError):
                            total_drop = 0.0
                    
                    alarm_type = alarm.get('alarm_type', '')
                    money_diff = float(alarm.get('money_diff', 0) or 0)
                    money_pct = 0
                    money_diff_val = money_diff
                    
                    alarm_data = {
                        'type': alarm_type,
                        'side': alarm.get('side', ''),
                        'money_diff': money_diff_val,
                        'odds_from': odds_from,
                        'odds_to': odds_to,
                        'total_drop': total_drop,
                        'money_pct': money_pct,
                        'timestamp': alarm.get('triggered_at', ''),
                        'window_start': alarm.get('window_start', ''),
                        'window_end': alarm.get('window_end', ''),
                        'home': alarm.get('home', ''),
                        'away': alarm.get('away', ''),
                        'market': alarm.get('market', ''),
                        'league': alarm.get('league', ''),
                        'match_date': match_date
                    }
                    
                    db_detail = alarm.get('detail', '')
                    if db_detail:
                        alarm_data['detail'] = db_detail
                    else:
                        formatted = format_alarm_for_modal(alarm_data)
                        alarm_data['detail'] = formatted.get('detail', '')
                    
                    filtered_alarms.append(alarm_data)
            
            grouped = group_alarms_by_match(filtered_alarms)
            formatted = [format_grouped_alarm(g) for g in grouped]
            
            elapsed = time.time() - start_time
            print(f"[Alarms API] Loaded {len(raw_alarms)} total, {len(filtered_alarms)} for today/future matches, {len(formatted)} groups in {elapsed:.2f}s")
            
            alarm_cache['data'] = formatted
            alarm_cache['timestamp'] = now
            
            return formatted.copy()
        else:
            print("[Alarms API] Supabase not available, falling back to volatile calculation")
            return get_cached_alarms_volatile()
    except Exception as e:
        print(f"[Alarms API] Error loading persistent alarms: {e}, falling back to volatile")
        import traceback
        traceback.print_exc()
        return get_cached_alarms_volatile()

def get_cached_alarms_volatile():
    """
    FALLBACK: Volatile alarm calculation when Supabase is not available.
    
    Per REFERANS DOKÜMANI Section 3:
    - D (Today) + Future: Show alarms
    - D-1 (Yesterday): Show alarms (static mode)
    - D-2+ (Old): DO NOT show
    """
    import time
    from core.alarms import group_alarms_by_match, format_grouped_alarm
    from core.timezone import is_match_d2_or_older, get_match_lifecycle_status
    
    print("[Alarms API] Using volatile alarm calculation (fallback)...")
    start_time = time.time()
    
    all_alarms = []
    markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts']
    
    matches_data = db.get_all_matches_with_latest('moneyway_1x2')
    real_matches = [m for m in matches_data if not is_demo_match(m)]
    
    all_unique_matches = []
    seen_pairs = set()
    for m in real_matches:
        home = m.get('home_team', '')
        away = m.get('away_team', '')
        pair = (home, away)
        if pair not in seen_pairs:
            all_unique_matches.append(m)
            seen_pairs.add(pair)
    
    match_pairs = [(m.get('home_team', ''), m.get('away_team', '')) for m in all_unique_matches]
    match_info = {(m.get('home_team', ''), m.get('away_team', '')): {
        'league': m.get('league', ''),
        'date': m.get('date', '')
    } for m in all_unique_matches}
    
    for market in markets:
        bulk_history = db.get_bulk_history_for_alarms(market, match_pairs)
        
        for (home, away), history in bulk_history.items():
            if len(history) >= 2:
                info = match_info.get((home, away), {})
                match_date = info.get('date', '')
                
                if is_match_d2_or_older(match_date):
                    continue
                
                alarms = analyze_match_alarms(history, market, match_date=match_date)
                for alarm in alarms:
                    alarm['home'] = home
                    alarm['away'] = away
                    alarm['market'] = market
                    alarm['league'] = info.get('league', '')
                    alarm['match_date'] = match_date
                    all_alarms.append(alarm)
    
    grouped = group_alarms_by_match(all_alarms)
    formatted = [format_grouped_alarm(g) for g in grouped]
    
    elapsed = time.time() - start_time
    print(f"[Alarms API] Volatile calculation in {elapsed:.2f}s, {len(formatted)} alarm groups")
    
    alarm_cache['data'] = formatted
    alarm_cache['timestamp'] = time.time()
    
    return formatted.copy()


@app.route('/api/alarms')
def get_all_alarms():
    """Get all active alarms - grouped by match+type with pagination and server-side filter/sort"""
    try:
        page = request.args.get('page', 0, type=int)
        page_size = request.args.get('page_size', 30, type=int)
        type_filter = request.args.get('filter', 'all')
        sort_by = request.args.get('sort', 'newest')
        search_query = request.args.get('search', '').strip().lower()
        
        page_size = min(page_size, 50)
        
        formatted = get_cached_alarms()
        
        if search_query:
            formatted = [a for a in formatted if 
                         search_query in a.get('home', '').lower() or 
                         search_query in a.get('away', '').lower()]
        
        if type_filter != 'all':
            formatted = [a for a in formatted if a.get('type', '') == type_filter]
        
        if sort_by == 'money':
            formatted.sort(key=lambda x: x.get('max_money', 0), reverse=True)
        elif sort_by == 'odds':
            formatted.sort(key=lambda x: x.get('max_drop', 0), reverse=True)
        else:
            formatted.sort(key=lambda x: x.get('priority', 99))
        
        total_count = len(formatted)
        start_idx = page * page_size
        end_idx = start_idx + page_size
        paginated = formatted[start_idx:end_idx]
        
        print(f"[Alarms API] Found {total_count} alarms, returning {len(paginated)} for page {page}")
        
        return jsonify({
            'alarms': paginated,
            'total': total_count,
            'page': page,
            'page_size': page_size,
            'has_more': end_idx < total_count,
            'event_count': sum(g['count'] for g in formatted)
        })
    except Exception as e:
        print(f"[Alarms API] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'alarms': [], 'total': 0, 'page': 0, 'has_more': False, 'error': str(e)})


@app.route('/api/alarms/scan')
def trigger_alarm_scan():
    """Manually trigger alarm detection and save to database"""
    try:
        count = detect_and_save_alarms()
        alarm_cache['data'] = None
        alarm_cache['timestamp'] = 0
        
        return jsonify({
            'status': 'success',
            'detected': count,
            'message': f'Scanned and saved {count} alarms'
        })
    except Exception as e:
        print(f"[Alarm Scan] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(e)})


@app.route('/api/alarms/reconcile')
def trigger_reconciliation():
    """
    RECONCILIATION ENDPOINT - Self-check for missing alarms.
    
    This endpoint:
    1. Compares expected alarms (from history) with DB alarms
    2. Inserts any missing alarms
    3. Returns detailed report
    
    Can be called manually or by scheduled job.
    """
    try:
        from core.alarm_safety import run_reconciliation, retry_failed_alarms
        
        supabase = get_supabase_client()
        if not supabase or not supabase.is_available:
            return jsonify({'status': 'error', 'error': 'Supabase not available'})
        
        retry_result = retry_failed_alarms(supabase)
        
        markets = [
            'moneyway_1x2', 'moneyway_ou25', 'moneyway_btts',
            'dropping_1x2', 'dropping_ou25', 'dropping_btts'
        ]
        result = run_reconciliation(supabase, markets, lookback_days=7)
        
        alarm_cache['data'] = None
        alarm_cache['timestamp'] = 0
        
        return jsonify({
            'status': result.get('status', 'unknown'),
            'reconciliation': {
                'expected': result.get('expected', 0),
                'found': result.get('found', 0),
                'missing': result.get('missing', 0),
                'fixed': result.get('inserted', 0)
            },
            'retry': retry_result,
            'message': f"Reconciliation complete: {result.get('missing', 0)} missing, {result.get('inserted', 0)} fixed"
        })
    except Exception as e:
        print(f"[Reconciliation] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'error': str(e)})


@app.route('/api/alarms/safety-check')
def safety_check():
    """
    SAFETY CHECK ENDPOINT - Verify alarm system integrity.
    
    Checks:
    1. No DELETE operations in code
    2. Failed alarms log status
    3. Last reconciliation result
    """
    try:
        from core.alarm_safety import verify_no_delete_operations, get_failed_alarms
        import os
        import json
        
        delete_check = verify_no_delete_operations()
        
        failed_alarms = get_failed_alarms()
        
        recon_log_path = os.path.join(os.path.dirname(__file__), 'data', 'reconciliation_log.json')
        last_recon = None
        if os.path.exists(recon_log_path):
            try:
                with open(recon_log_path, 'r') as f:
                    recon_log = json.load(f)
                    if recon_log:
                        last_recon = recon_log[-1]
            except:
                pass
        
        return jsonify({
            'status': 'healthy' if delete_check['safe'] and len(failed_alarms) == 0 else 'warning',
            'checks': {
                'no_delete_operations': delete_check['safe'],
                'delete_issues': delete_check.get('issues', []),
                'failed_alarms_count': len(failed_alarms),
                'failed_alarms_sample': failed_alarms[:3] if failed_alarms else [],
                'last_reconciliation': last_recon
            },
            'message': 'Alarm system integrity verified' if delete_check['safe'] else 'Issues found - check details'
        })
    except Exception as e:
        print(f"[Safety Check] Error: {e}")
        return jsonify({'status': 'error', 'error': str(e)})


ticker_cache = {
    'data': None,
    'timestamp': 0,
    'ttl': 120  # 2 dakika cache (önceki: 1 dakika) - performans için artırıldı
}

@app.route('/api/alarms/ticker')
def get_ticker_alarms():
    """Get critical alarms for borsa bandı - uses same cache as alarm list for consistency"""
    import time
    try:
        from core.alarms import ALARM_TYPES
        
        now = time.time()
        if ticker_cache['data'] is not None and (now - ticker_cache['timestamp']) < ticker_cache['ttl']:
            return jsonify(ticker_cache['data'])
        
        grouped_alarms = get_cached_alarms()
        
        ticker_alarms = []
        for group in grouped_alarms:
            home = group.get('home', '')
            away = group.get('away', '')
            league = group.get('league', '')
            date = group.get('date', '')
            match_id = group.get('match_id', '')
            alarm_type = group.get('type', '')
            alarm_info = ALARM_TYPES.get(alarm_type, {})
            
            events = group.get('events', [])
            for event in events:
                money_diff = event.get('money_diff', 0)
                ticker_alarms.append({
                    'type': alarm_type,
                    'icon': alarm_info.get('icon', ''),
                    'name': alarm_info.get('name', alarm_type),
                    'color': alarm_info.get('color', '#888'),
                    'home': home,
                    'away': away,
                    'side': event.get('side', ''),
                    'money_text': f"+£{int(money_diff):,}" if money_diff > 0 else '',
                    'odds_from': event.get('odds_from'),
                    'odds_to': event.get('odds_to'),
                    'priority': alarm_info.get('priority', 99),
                    'critical': alarm_info.get('critical', False),
                    'timestamp': event.get('timestamp', ''),
                    'market': group.get('market', 'moneyway_1x2'),
                    'match_id': match_id,
                    'league': league,
                    'date': date
                })
        
        ticker_alarms.sort(key=lambda x: (x.get('priority', 99), x.get('timestamp', '')))
        critical = [a for a in ticker_alarms if a.get('critical', False)][:20]
        if len(critical) < 20:
            critical = ticker_alarms[:20]
        
        print(f"[Ticker API] Using cached alarms: {len(ticker_alarms)} total, {len(critical)} shown")
        
        result = {
            'alarms': critical,
            'total': len(ticker_alarms)
        }
        
        ticker_cache['data'] = result
        ticker_cache['timestamp'] = now
        
        return jsonify(result)
    except Exception as e:
        print(f"[Ticker API] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'alarms': [], 'total': 0})


odds_trend_cache = {
    'data': {},  # market -> data
    'timestamp': {},  # market -> timestamp
    'ttl': 300  # 5 dakika cache
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
    """Get match details by team names - used when opening from alarm list"""
    home = request.args.get('home', '')
    away = request.args.get('away', '')
    
    if not home or not away:
        return jsonify({'success': False, 'error': 'Missing home or away parameter'})
    
    try:
        match_data = None
        for market in ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts', 'dropping_1x2', 'dropping_ou25', 'dropping_btts']:
            matches_list = db.get_all_matches_with_latest(market)
            for m in matches_list:
                if m.get('home_team') == home and m.get('away_team') == away:
                    match_data = m
                    break
            if match_data:
                break
        
        if match_data:
            odds_data = match_data.get('odds') or match_data.get('details') or {}
            return jsonify({
                'success': True,
                'match': {
                    'home_team': home,
                    'away_team': away,
                    'league': match_data.get('league', ''),
                    'date': match_data.get('date', ''),
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


def get_match_alarms_data(home: str, away: str, today_only: bool = True) -> list:
    """
    Core function to get alarms for a specific match.
    SYNCHRONIZED: Uses the same cached alarm data as alarm list for consistency.
    This ensures all 3 UIs (bant, alarm list, match modal) show identical data.
    """
    from core.timezone import is_today_turkey
    
    grouped_alarms = get_cached_alarms()
    
    match_alarms = []
    for group in grouped_alarms:
        g_home = group.get('home', '')
        g_away = group.get('away', '')
        
        if g_home.lower() == home.lower() and g_away.lower() == away.lower():
            alarm_type = group.get('type', '')
            events = group.get('events', [])
            
            for event in events:
                if today_only and not is_today_turkey(event.get('timestamp', '')):
                    continue
                
                match_alarms.append({
                    'name': group.get('name', alarm_type),
                    'type': alarm_type,
                    'icon': group.get('icon', ''),
                    'color': group.get('color', '#888'),
                    'description': event.get('description', ''),
                    'detail': event.get('detail', ''),
                    'side': event.get('side', ''),
                    'market': group.get('market', ''),
                    'timestamp': event.get('timestamp', ''),
                    'money_diff': event.get('money_diff', 0),
                    'odds_from': event.get('odds_from'),
                    'odds_to': event.get('odds_to'),
                    'priority': group.get('priority', 99)
                })
    
    match_alarms.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    return match_alarms

@app.route('/api/match/alarms')
def get_match_alarms():
    """Get alarms for a specific match"""
    home = request.args.get('home', '')
    away = request.args.get('away', '')
    today_only = request.args.get('today_only', 'true').lower() == 'true'
    
    try:
        all_alarms = get_match_alarms_data(home, away, today_only)
        
        return jsonify({
            'alarms': all_alarms,
            'alarm_types': ALARM_TYPES
        })
    except Exception as e:
        print(f"[Match Alarms API] Error: {e}")
        return jsonify({'alarms': [], 'error': str(e)})


@app.route('/admin')
def admin_panel():
    """Admin Panel - Alarm configuration UI"""
    return render_template('admin.html')


@app.route('/admin/alarm-config', methods=['GET'])
def get_alarm_config():
    """Get current alarm configuration"""
    try:
        from core.alarm_config import load_alarm_config, config_to_dict
        cfg = load_alarm_config()
        return jsonify(config_to_dict(cfg))
    except Exception as e:
        print(f"[Admin API] Error loading config: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/admin/alarm-config', methods=['POST'])
def update_alarm_config():
    """Update alarm configuration"""
    try:
        from core.alarm_config import dict_to_config, save_alarm_config, config_to_dict
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        cfg = dict_to_config(data)
        success = save_alarm_config(cfg)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Configuration saved successfully',
                'config': config_to_dict(cfg)
            })
        else:
            return jsonify({'error': 'Failed to save configuration'}), 500
    except Exception as e:
        print(f"[Admin API] Error saving config: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/admin/reload-config', methods=['POST'])
def reload_config():
    """Reload configuration from file"""
    try:
        from core.alarm_config import reload_alarm_config, config_to_dict
        cfg = reload_alarm_config()
        return jsonify({
            'success': True,
            'message': 'Configuration reloaded',
            'config': config_to_dict(cfg)
        })
    except Exception as e:
        print(f"[Admin API] Error reloading config: {e}")
        return jsonify({'error': str(e)}), 500


def main():
    """Main entry point with error handling for EXE"""
    try:
        mode_name = "CLIENT" if is_client_mode() else "SERVER"
        
        print("=" * 50)
        print("SmartXFlow Alarm V1.01")
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
