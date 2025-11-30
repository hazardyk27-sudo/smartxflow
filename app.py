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
    """Start daily cleanup scheduler for old matches"""
    global cleanup_thread
    
    def cleanup_loop():
        while True:
            cleanup_old_matches()
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
    return render_template('index.html')


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
    """Get match details by team names"""
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


SHARP_CONFIG_FILE = 'sharp_config.json'

def load_sharp_config_from_file():
    """Load Sharp config from JSON file"""
    default_config = {
        'min_volume_1x2': 3000,
        'min_volume_ou25': 1000,
        'min_volume_btts': 500,
        'volume_multiplier': 1.0,
        'odds_multiplier': 1.0,
        'share_multiplier': 1.0,
        'w_volume': 40,
        'w_odds': 35,
        'w_share': 25,
        'min_share': 5,
        'min_sharp_score': 10
    }
    try:
        if os.path.exists(SHARP_CONFIG_FILE):
            with open(SHARP_CONFIG_FILE, 'r') as f:
                saved_config = json.load(f)
                default_config.update(saved_config)
                print(f"[Sharp] Config loaded from {SHARP_CONFIG_FILE}: min_sharp_score={default_config.get('min_sharp_score')}")
    except Exception as e:
        print(f"[Sharp] Config load error: {e}")
    return default_config

def save_sharp_config_to_file(config):
    """Save Sharp config to JSON file"""
    try:
        with open(SHARP_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"[Sharp] Config saved to {SHARP_CONFIG_FILE}")
        return True
    except Exception as e:
        print(f"[Sharp] Config save error: {e}")
        return False

sharp_config = load_sharp_config_from_file()

sharp_alarms = []
sharp_calculating = False
sharp_calc_progress = ""


@app.route('/api/sharp/status', methods=['GET'])
def get_sharp_status():
    """Get Sharp calculation status"""
    return jsonify({
        'calculating': sharp_calculating,
        'progress': sharp_calc_progress,
        'alarm_count': len(sharp_alarms)
    })


@app.route('/api/sharp/config', methods=['GET'])
def get_sharp_config():
    """Get Sharp config"""
    return jsonify(sharp_config)


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
    """Get all Sharp alarms"""
    return jsonify(sharp_alarms)


@app.route('/api/sharp/alarms', methods=['DELETE'])
def delete_sharp_alarms():
    """Delete all Sharp alarms"""
    global sharp_alarms
    sharp_alarms = []
    supabase = get_supabase_client()
    if supabase and supabase.is_available:
        try:
            supabase.delete_all_sharp_alarms()
        except:
            pass
    return jsonify({'success': True})


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
        sharp_calc_progress = f"Tamamlandi! {len(sharp_alarms)} alarm bulundu."
        sharp_calculating = False
        return jsonify({'success': True, 'count': len(sharp_alarms)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        sharp_calculating = False
        sharp_calc_progress = f"Hata: {str(e)}"
        return jsonify({'success': False, 'error': str(e)}), 500


def calculate_sharp_scores(config):
    """Calculate Sharp scores for all matches based on config"""
    global sharp_calc_progress
    alarms = []
    all_candidates = []
    supabase = get_supabase_client()
    if not supabase or not supabase.is_available:
        print("[Sharp] Supabase not available")
        return alarms
    
    markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts']
    market_names = {'moneyway_1x2': '1X2', 'moneyway_ou25': 'O/U 2.5', 'moneyway_btts': 'BTTS'}
    
    for idx, market in enumerate(markets):
        try:
            if '1x2' in market:
                min_volume = config.get('min_volume_1x2', 3000)
                selections = ['1', 'X', '2']
            elif 'ou25' in market:
                min_volume = config.get('min_volume_ou25', 1000)
                selections = ['Over', 'Under']
            else:
                min_volume = config.get('min_volume_btts', 500)
                selections = ['Yes', 'No']
            
            history_table = f"{market}_history"
            matches = supabase.get_all_matches_with_latest(market)
            
            if not matches:
                print(f"[Sharp] No matches for {market}")
                continue
            
            sharp_calc_progress = f"{market_names.get(market, market)} isleniyor... ({idx+1}/3)"
            print(f"[Sharp] Processing {len(matches)} matches for {market}, min_volume: {min_volume}")
            processed = 0
            
            for match in matches:
                home = match.get('home_team', match.get('home', match.get('Home', '')))
                away = match.get('away_team', match.get('away', match.get('Away', '')))
                
                if not home or not away:
                    continue
                
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
                    alarm = calculate_selection_sharp(
                        home, away, market, selection, sel_idx,
                        history, volume, config
                    )
                    if alarm:
                        all_candidates.append(alarm)
                        if alarm.get('triggered'):
                            alarms.append(alarm)
            
            print(f"[Sharp] Processed {processed} matches with sufficient volume for {market}")
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
    
    alarms.sort(key=lambda x: x.get('sharp_score', 0), reverse=True)
    return alarms


def calculate_selection_sharp(home, away, market, selection, sel_idx, history, volume, config):
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
    
    last_10 = history[-10:] if len(history) >= 10 else history
    
    amounts = []
    for snap in last_10:
        amt = parse_volume(snap.get(amount_key, '0'))
        if amt > 0:
            amounts.append(amt)
    
    if len(amounts) < 2:
        return None
    
    current_amount = amounts[-1]
    avg_last_10_amounts = sum(amounts[:-1]) / len(amounts[:-1]) if len(amounts) > 1 else 1
    
    if avg_last_10_amounts <= 0:
        return None
    
    shock_raw = current_amount / avg_last_10_amounts
    volume_multiplier = config.get('volume_multiplier', 1)
    shock_value = shock_raw * volume_multiplier
    
    latest = history[-1]
    previous = history[-2] if len(history) >= 2 else history[-1]
    
    odds_before = parse_float(previous.get(odds_key, '0'))
    odds_after = parse_float(latest.get(odds_key, '0'))
    
    if odds_before > 0 and odds_after < odds_before:
        drop_pct = ((odds_before - odds_after) / odds_before) * 100
    else:
        drop_pct = 0
    
    odds_multiplier = config.get('odds_multiplier', 1)
    odds_value = drop_pct * odds_multiplier
    
    share_before = parse_float(str(previous.get(share_key, '0')).replace('%', ''))
    share_after = parse_float(str(latest.get(share_key, '0')).replace('%', ''))
    
    share_diff = share_after - share_before
    if share_diff < 0:
        share_diff = 0
    
    current_share = share_after
    
    share_multiplier = config.get('share_multiplier', 1)
    share_value = share_diff * share_multiplier
    
    w_volume = config.get('w_volume', 40)
    w_odds = config.get('w_odds', 35)
    w_share = config.get('w_share', 25)
    
    volume_contrib = shock_value * (w_volume / 100)
    odds_contrib = odds_value * (w_odds / 100)
    share_contrib = share_value * (w_share / 100)
    
    sharp_score = volume_contrib + odds_contrib + share_contrib
    
    min_share_threshold = config.get('min_share', 5)
    min_sharp_score = config.get('min_sharp_score', 10)
    
    triggered = (
        current_share >= min_share_threshold and
        shock_value > 0 and
        odds_value > 0 and
        share_value > 0 and
        sharp_score >= min_sharp_score
    )
    
    return {
        'home': home,
        'away': away,
        'market': market,
        'selection': selection,
        'created_at': now_turkey_formatted(),
        'current_amount': current_amount,
        'avg_last_10_amounts': avg_last_10_amounts,
        'shock_raw': shock_raw,
        'volume_multiplier': volume_multiplier,
        'shock_value': shock_value,
        'w_volume': w_volume,
        'volume_contrib': volume_contrib,
        'previous_odds': odds_before,
        'current_odds': odds_after,
        'drop_pct': drop_pct,
        'odds_multiplier': odds_multiplier,
        'odds_value': odds_value,
        'w_odds': w_odds,
        'odds_contrib': odds_contrib,
        'previous_share': share_before,
        'current_share': share_after,
        'share_diff': share_diff,
        'share_multiplier': share_multiplier,
        'share_value': share_value,
        'w_share': w_share,
        'share_contrib': share_contrib,
        'sharp_score': sharp_score,
        'min_sharp_score': min_sharp_score,
        'triggered': triggered
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
    """Parse float from string"""
    if not val:
        return 0
    try:
        cleaned = str(val).replace(',', '.').strip()
        return float(cleaned) if cleaned else 0
    except:
        return 0


@app.route('/admin')
def admin_panel():
    """Admin Panel"""
    return render_template('admin.html')


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
