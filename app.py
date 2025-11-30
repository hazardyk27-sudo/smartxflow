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
        'max_volume_cap': 40,
        'max_odds_cap': 35,
        'max_share_cap': 25,
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
    """Save Sharp alarms to JSON file"""
    try:
        with open(SHARP_ALARMS_FILE, 'w') as f:
            json.dump(alarms, f, indent=2, ensure_ascii=False)
        print(f"[Sharp] Saved {len(alarms)} alarms to {SHARP_ALARMS_FILE}")
        return True
    except Exception as e:
        print(f"[Sharp] Alarms save error: {e}")
        return False

sharp_alarms = load_sharp_alarms_from_file()
sharp_calculating = False
sharp_calc_progress = ""

# ==================== INSIDER INFO ALARM SYSTEM ====================
INSIDER_ALARMS_FILE = 'insider_alarms.json'

def load_insider_alarms_from_file():
    """Load Insider alarms from JSON file"""
    try:
        if os.path.exists(INSIDER_ALARMS_FILE):
            with open(INSIDER_ALARMS_FILE, 'r') as f:
                alarms = json.load(f)
                print(f"[Insider] Loaded {len(alarms)} alarms from {INSIDER_ALARMS_FILE}")
                return alarms
    except Exception as e:
        print(f"[Insider] Alarms load error: {e}")
    return []

def save_insider_alarms_to_file(alarms):
    """Save Insider alarms to JSON file"""
    try:
        with open(INSIDER_ALARMS_FILE, 'w') as f:
            json.dump(alarms, f, indent=2, ensure_ascii=False)
        print(f"[Insider] Saved {len(alarms)} alarms to {INSIDER_ALARMS_FILE}")
        return True
    except Exception as e:
        print(f"[Insider] Alarms save error: {e}")
        return False

insider_alarms = load_insider_alarms_from_file()


@app.route('/api/insider/alarms', methods=['GET'])
def get_insider_alarms():
    """Get all Insider alarms"""
    return jsonify(insider_alarms)


@app.route('/api/insider/delete', methods=['POST'])
def delete_insider_alarms():
    """Delete all Insider alarms"""
    global insider_alarms
    try:
        insider_alarms = []
        save_insider_alarms_to_file(insider_alarms)
        print("[Insider] All alarms deleted")
        return jsonify({'success': True})
    except Exception as e:
        print(f"[Insider] Delete error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/insider/calculate', methods=['POST'])
def calculate_insider_alarms_endpoint():
    """Calculate Insider Info alarms based on config"""
    global insider_alarms
    try:
        insider_alarms = calculate_insider_scores(sharp_config)
        save_insider_alarms_to_file(insider_alarms)
        return jsonify({'success': True, 'count': len(insider_alarms)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


def calculate_insider_scores(config):
    """
    Calculate Insider Info alarms with rolling window approach.
    
    INSIDER ALARM CONDITIONS (must be met for consecutive snapshots):
    1. HacimSok < insider_hacim_sok_esigi (default: 2)
    2. OranDususu >= insider_oran_dusus_esigi (default: 3%)
    3. GelenPara < insider_max_para (default: 5000)
    
    These conditions must persist for insider_sure_dakika minutes (default: 30)
    which equals 3 consecutive 10-minute snapshots.
    """
    alarms = []
    supabase = get_supabase_client()
    if not supabase or not supabase.is_available:
        print("[Insider] Supabase not available")
        return alarms
    
    # Get config parameters with Turkish names
    hacim_sok_esigi = config.get('insider_hacim_sok_esigi', 2)
    oran_dusus_esigi = config.get('insider_oran_dusus_esigi', 3)
    sure_dakika = config.get('insider_sure_dakika', 30)
    max_para = config.get('insider_max_para', 5000)
    
    # Calculate required consecutive snapshots (10 min per snapshot)
    snapshot_interval = 10  # minutes
    required_streak = max(1, sure_dakika // snapshot_interval)
    
    print(f"[Insider] Config: HacimSok<{hacim_sok_esigi}, OranDusus>={oran_dusus_esigi}%, Sure={sure_dakika}dk ({required_streak} snapshot), MaxPara<{max_para}")
    
    markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts']
    market_names = {'moneyway_1x2': '1X2', 'moneyway_ou25': 'O/U 2.5', 'moneyway_btts': 'BTTS'}
    
    # Prematch kuralı: D-2+ maçlar hariç tutulur (Sharp ile aynı)
    today = now_turkey().date()
    yesterday = today - timedelta(days=1)
    
    for market in markets:
        try:
            if '1x2' in market:
                selections = ['1', 'X', '2']
                odds_keys = ['odds1', 'oddsx', 'odds2']
                amount_keys = ['amt1', 'amtx', 'amt2']
            elif 'ou25' in market:
                selections = ['Over', 'Under']
                odds_keys = ['over', 'under']
                amount_keys = ['amtover', 'amtunder']
            else:
                selections = ['Yes', 'No']
                odds_keys = ['oddsyes', 'oddsno']
                amount_keys = ['amtyes', 'amtno']
            
            history_table = f"{market}_history"
            matches = supabase.get_all_matches_with_latest(market)
            if not matches:
                continue
            
            # D-2+ filtresi uygula - sadece bugün ve yarın maçlarını işle
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
                        
                        # D-2 veya daha eski maçları atla
                        if match_date < yesterday:
                            continue
                        filtered_matches.append(match)
                    except:
                        filtered_matches.append(match)
                else:
                    filtered_matches.append(match)
            
            print(f"[Insider] Processing {len(filtered_matches)}/{len(matches)} matches for {market} (D-2+ filtered)")
            
            for match in filtered_matches:
                home = match.get('home_team', match.get('home', match.get('Home', '')))
                away = match.get('away_team', match.get('away', match.get('Away', '')))
                
                if not home or not away:
                    continue
                
                # Use faster history fetch (same as Sharp) - tek request
                history = supabase.get_match_history_for_sharp(home, away, history_table)
                if not history or len(history) < required_streak + 1:
                    continue
                
                match_date_str = match.get('date', '')
                
                for sel_idx, selection in enumerate(selections):
                    odds_key = odds_keys[sel_idx]
                    amount_key = amount_keys[sel_idx]
                    
                    # Get opening odds (first snapshot)
                    opening_odds = parse_float(history[0].get(odds_key, '0'))
                    if opening_odds <= 0:
                        continue
                    
                    # Calculate metrics for each snapshot
                    snapshot_metrics = []
                    for i, snap in enumerate(history):
                        current_odds = parse_float(snap.get(odds_key, '0'))
                        current_amount = parse_volume(snap.get(amount_key, '0'))
                        
                        # Calculate odds drop from opening
                        if current_odds > 0 and current_odds < opening_odds:
                            odds_drop_pct = ((opening_odds - current_odds) / opening_odds) * 100
                        else:
                            odds_drop_pct = 0
                        
                        # Calculate amount change and shock from previous snapshot
                        if i > 0:
                            prev_amount = parse_volume(history[i-1].get(amount_key, '0'))
                            amount_change = current_amount - prev_amount
                            
                            # Calculate average of previous amounts for shock
                            prev_amounts = []
                            for j in range(max(0, i-5), i):
                                amt = parse_volume(history[j].get(amount_key, '0'))
                                if amt > 0:
                                    prev_amounts.append(amt)
                            
                            if prev_amounts and amount_change > 0:
                                avg_prev = sum(prev_amounts) / len(prev_amounts)
                                hacim_sok = amount_change / avg_prev if avg_prev > 0 else 0
                            else:
                                hacim_sok = 0
                            
                            # Gelen para = amount_change (positive money flow)
                            gelen_para = max(0, amount_change)
                        else:
                            hacim_sok = 0
                            gelen_para = 0
                            amount_change = 0
                        
                        snapshot_metrics.append({
                            'index': i,
                            'odds': current_odds,
                            'odds_drop_pct': odds_drop_pct,
                            'hacim_sok': hacim_sok,
                            'gelen_para': gelen_para,
                            'amount_change': amount_change
                        })
                    
                    # Check rolling windows for consecutive qualifying snapshots
                    alarm_triggered = False
                    best_window = None
                    
                    for window_start in range(1, len(snapshot_metrics) - required_streak + 1):
                        window = snapshot_metrics[window_start:window_start + required_streak]
                        
                        # Check if ALL snapshots in window meet conditions
                        all_qualify = True
                        for snap_metric in window:
                            # Condition 1: HacimSok < esik
                            if snap_metric['hacim_sok'] >= hacim_sok_esigi:
                                all_qualify = False
                                break
                            # Condition 2: OranDusus >= esik
                            if snap_metric['odds_drop_pct'] < oran_dusus_esigi:
                                all_qualify = False
                                break
                            # Condition 3: GelenPara < max_para
                            if snap_metric['gelen_para'] >= max_para:
                                all_qualify = False
                                break
                        
                        if all_qualify:
                            alarm_triggered = True
                            best_window = window
                            break  # Take first qualifying window
                    
                    if alarm_triggered and best_window:
                        # Use last snapshot in window for alarm details
                        last_snap = best_window[-1]
                        first_snap = best_window[0]
                        
                        # Calculate averages over the window
                        avg_hacim_sok = sum(s['hacim_sok'] for s in best_window) / len(best_window)
                        avg_gelen_para = sum(s['gelen_para'] for s in best_window) / len(best_window)
                        max_odds_drop = max(s['odds_drop_pct'] for s in best_window)
                        
                        created_at = now_turkey().strftime('%d.%m.%Y %H:%M')
                        last_odds = parse_float(history[-1].get(odds_key, '0'))
                        
                        alarm = {
                            'home': home,
                            'away': away,
                            'market': market_names.get(market, market),
                            'selection': selection,
                            'hacim_sok': avg_hacim_sok,
                            'oran_dusus_pct': max_odds_drop,
                            'gelen_para': avg_gelen_para,
                            'opening_odds': opening_odds,
                            'last_odds': last_odds,
                            'insider_hacim_sok_esigi': hacim_sok_esigi,
                            'insider_oran_dusus_esigi': oran_dusus_esigi,
                            'insider_sure_dakika': sure_dakika,
                            'insider_max_para': max_para,
                            'snapshot_count': required_streak,
                            'match_date': match_date_str,
                            'created_at': created_at,
                            'triggered': True
                        }
                        alarms.append(alarm)
                        print(f"[Insider] ALARM: {home} vs {away} [{selection}] HacimSok={avg_hacim_sok:.2f}x, OranDusus={max_odds_drop:.1f}%, GelenPara=£{avg_gelen_para:.0f}")
        
        except Exception as e:
            print(f"[Insider] Error processing {market}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"[Insider] Total alarms found: {len(alarms)}")
    return alarms


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
    save_sharp_alarms_to_file(sharp_alarms)
    supabase = get_supabase_client()
    if supabase and supabase.is_available:
        try:
            supabase.delete_all_sharp_alarms()
        except:
            pass
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
                    except Exception as e:
                        print(f"[Sharp] Date parse error for {home} vs {away}: {match_date_str} - {e}")
                        # Parse hatası varsa devam et
                
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
                        history, volume, config, match_date_str
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
    
    alarms.sort(key=lambda x: x.get('sharp_score', 0), reverse=True)
    return alarms


def calculate_selection_sharp(home, away, market, selection, sel_idx, history, volume, config, match_date_str=''):
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
    
    # GELEN PARA = Son snapshot - Bir önceki snapshot
    # Örnek: amounts = [..., 414, 1629]
    # amount_change = 1629 - 414 = 1215 (son aralıkta gelen para)
    last_amount = amounts[-1]
    previous_amount = amounts[-2]
    amount_change = last_amount - previous_amount
    
    # Negatif değişim (para çekilmesi) alarm tetiklememeli
    if amount_change <= 0:
        return None
    
    # Gelen para minimum eşik kontrolü
    min_amount_change = config.get('min_amount_change', 500)
    if amount_change < min_amount_change:
        return None
    
    # Son 2 amount HARİÇ, önceki amount'ların ortalaması
    # Örnek: amounts = [10, 10, 30, 30, 54, 54, 100, 150, 414, 1629]
    # previous_amounts = [10, 10, 30, 30, 54, 54, 100, 150] (son 2 hariç: 414, 1629)
    # avg = sum(previous_amounts) / len(previous_amounts)
    if len(amounts) >= 3:
        previous_amounts = amounts[:-2]  # Son 2 hariç
        avg_last_amounts = sum(previous_amounts) / len(previous_amounts)
    else:
        # Sadece 2 snapshot varsa, bir öncekini ortalama olarak kullan
        avg_last_amounts = previous_amount
    
    if avg_last_amounts <= 0:
        return None
    
    # Gelen para / önceki ortalaması = shock
    shock_raw = amount_change / avg_last_amounts
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
    
    # CAP değerleri - her kriterin maksimum katkısını sınırlar
    max_volume_cap = config.get('max_volume_cap', 40)
    max_odds_cap = config.get('max_odds_cap', 35)
    max_share_cap = config.get('max_share_cap', 25)
    
    # Her kriter için puan hesapla (CAP ile sınırla)
    volume_contrib = min(shock_value, max_volume_cap)
    odds_contrib = min(odds_value, max_odds_cap)
    share_contrib = min(share_value, max_share_cap)
    
    # SharpScore = hacim_puani + oran_puani + pay_puani
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
        'match_date': match_date_str,
        'created_at': now_turkey_formatted(),
        'amount_change': amount_change,
        'avg_last_amounts': avg_last_amounts,
        'shock_raw': shock_raw,
        'volume_multiplier': volume_multiplier,
        'shock_value': shock_value,
        'max_volume_cap': max_volume_cap,
        'volume_contrib': volume_contrib,
        'previous_odds': odds_before,
        'current_odds': odds_after,
        'drop_pct': drop_pct,
        'odds_multiplier': odds_multiplier,
        'odds_value': odds_value,
        'max_odds_cap': max_odds_cap,
        'odds_contrib': odds_contrib,
        'previous_share': share_before,
        'current_share': share_after,
        'share_diff': share_diff,
        'share_multiplier': share_multiplier,
        'share_value': share_value,
        'max_share_cap': max_share_cap,
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
