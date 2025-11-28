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
    """Start daily cleanup scheduler - includes alarm state cleanup"""
    global cleanup_thread
    
    try:
        from core.alarm_state import cleanup_old_alarm_states
    except ImportError:
        cleanup_old_alarm_states = lambda *args: None
    
    def cleanup_loop():
        while True:
            cleanup_old_matches()
            cleanup_old_alarm_states(hours=48)
            time.sleep(3600)
    
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
                alarms = analyze_match_alarms(history, 'moneyway_1x2')
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


@app.route('/api/matches')
def get_matches():
    """Get all matches from database - optimized single query"""
    market = request.args.get('market', 'moneyway_1x2')
    is_dropping = market.startswith('dropping')
    
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
    'ttl': 120
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

def get_cached_alarms():
    """Get alarms from cache or refresh if expired.
    SYNCHRONIZED: Single source of truth for all 3 UIs (ticker, alarm list, match modal).
    Returns alarms for matches that are TODAY or in the FUTURE (Europe/Istanbul timezone).
    - Match date >= today: Show alarm
    - Match date < today: Don't show (past match)
    - Alarm triggered_at: No filter (we care about match date, not alarm date)
    """
    import time
    from core.alarms import group_alarms_by_match, format_grouped_alarm
    from core.timezone import now_turkey, is_match_today_or_future
    
    now = time.time()
    if alarm_cache['data'] is not None and (now - alarm_cache['timestamp']) < alarm_cache['ttl']:
        print("[Alarms API] Using cached data")
        return alarm_cache['data'].copy()
    
    print("[Alarms API] Refreshing alarm cache (bulk query)...")
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
    
    future_match_count = 0
    for m in all_unique_matches:
        if is_match_today_or_future(m.get('date', '')):
            future_match_count += 1
    
    print(f"[Alarms API] Checking {len(match_pairs)} unique matches ({future_match_count} today/future) for alarms")
    
    for market in markets:
        bulk_history = db.get_bulk_history_for_alarms(market, match_pairs)
        
        for (home, away), history in bulk_history.items():
            if len(history) >= 2:
                info = match_info.get((home, away), {})
                match_date = info.get('date', '')
                
                if not is_match_today_or_future(match_date):
                    continue
                
                alarms = analyze_match_alarms(history, market)
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
    print(f"[Alarms API] Cache refreshed in {elapsed:.2f}s, checked {len(match_pairs)} matches (bulk), found {len(formatted)} alarm groups ({len(all_alarms)} events for today/future matches)")
    
    alarm_cache['data'] = formatted
    alarm_cache['timestamp'] = now
    
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
            formatted = [a for a in formatted if type_filter in a.get('type', '')]
        
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


ticker_cache = {
    'data': None,
    'timestamp': 0,
    'ttl': 60
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


@app.route('/api/odds-trend/<market>')
def get_odds_trend(market):
    """Get 6-hour odds trend data for DROP markets only.
    Returns sparkline data, percent change, and trend direction.
    """
    if not market.startswith('dropping'):
        return jsonify({'error': 'Only DROP markets supported', 'data': {}})
    
    try:
        sb_client = get_supabase_client()
        if sb_client:
            trend_data = sb_client.get_6h_odds_history(market)
        else:
            trend_data = {}
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
