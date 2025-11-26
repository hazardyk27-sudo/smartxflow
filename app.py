"""
SmartXFlow - Betting Odds Monitor
Flask Web Application with modern dark theme UI

Mode-aware architecture:
- SERVER mode (Replit): Runs scraper, writes to SQLite, syncs to Supabase
- CLIENT mode (EXE): Only reads from Supabase, no scraping
"""

import os
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, jsonify, request

from core.settings import init_mode, is_server_mode, is_client_mode, get_scrape_interval_seconds
from services.supabase_client import get_database
from core.alarms import analyze_match_alarms, format_alarm_for_ticker, format_alarm_for_modal, ALARM_TYPES

app = Flask(__name__)
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


def start_server_scheduler():
    """Start background scheduler for server mode - runs scraper periodically"""
    global server_scheduler_thread, server_scheduler_stop
    
    if not is_server_mode():
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
                    print(f"[Server Scheduler] Running scrape at {datetime.now().isoformat()}")
                    result = run_scraper()
                    scrape_status['last_result'] = result
                    scrape_status['last_scrape_time'] = datetime.now().isoformat()
                    scrape_status['last_supabase_sync'] = datetime.now().isoformat()
                    print(f"[Server Scheduler] Scrape completed")
                except Exception as e:
                    print(f"[Server Scheduler] Error: {e}")
                    scrape_status['last_result'] = {'status': 'error', 'error': str(e)}
                finally:
                    scrape_status['running'] = False
            
            next_time = datetime.now() + timedelta(seconds=interval_seconds)
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
        
        enriched.append({
            'home_team': m.get('home_team', ''),
            'away_team': m.get('away_team', ''),
            'league': m.get('league', ''),
            'date': m.get('date', ''),
            'odds': {**odds, **prev_odds},
            'history_count': 1
        })
    
    return jsonify(enriched)


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
            scrape_status['last_scrape_time'] = datetime.now().isoformat()
            scrape_status['last_supabase_sync'] = datetime.now().isoformat()
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
                    scrape_status['last_supabase_sync'] = datetime.now().isoformat()
                    
                    next_time = datetime.now() + timedelta(minutes=interval)
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
                            scrape_status['last_scrape_time'] = datetime.now().isoformat()
                            scrape_status['last_supabase_sync'] = datetime.now().isoformat()
                        except Exception as e:
                            scrape_status['last_result'] = {'status': 'error', 'error': str(e)}
                        finally:
                            scrape_status['running'] = False
                    
                    next_time = datetime.now() + timedelta(minutes=scrape_status['interval_minutes'])
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
        dt = datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
        turkey_offset = timedelta(hours=3)
        turkey_time = dt + turkey_offset
        return turkey_time.strftime("%H:%M")
    except:
        return "--:--"


@app.route('/api/status')
def get_status():
    """Get current scrape status with mode information"""
    mode = "server" if is_server_mode() else "client"
    
    last_time_tr = get_turkey_time_str(scrape_status['last_scrape_time'])
    
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
        'scraping_enabled': is_server_mode()
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


@app.route('/api/alarms')
def get_all_alarms():
    """Get all active alarms for ticker - one per match, max 12"""
    try:
        match_best_alarms = {}
        matches = db.get_all_matches()
        
        markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts', 
                   'dropping_1x2', 'dropping_ou25', 'dropping_btts']
        
        for m in matches:
            home = m.get('home_team', '')
            away = m.get('away_team', '')
            match_key = f"{home}_{away}"
            
            for market in markets:
                history = db.get_match_history(home, away, market)
                if len(history) >= 2:
                    alarms = analyze_match_alarms(history, market)
                    for alarm in alarms:
                        formatted = format_alarm_for_ticker(alarm, home, away)
                        formatted['market'] = market
                        formatted['match_id'] = match_key
                        
                        current_best = match_best_alarms.get(match_key)
                        if not current_best or formatted['priority'] < current_best['priority']:
                            match_best_alarms[match_key] = formatted
        
        all_alarms = list(match_best_alarms.values())
        all_alarms.sort(key=lambda x: x.get('priority', 99))
        
        return jsonify({
            'alarms': all_alarms[:12],
            'total': len(all_alarms)
        })
    except Exception as e:
        print(f"[Alarms API] Error: {e}")
        return jsonify({'alarms': [], 'total': 0, 'error': str(e)})


@app.route('/api/match/alarms')
def get_match_alarms():
    """Get alarms for a specific match"""
    home = request.args.get('home', '')
    away = request.args.get('away', '')
    
    try:
        all_alarms = []
        markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts']
        
        for market in markets:
            history = db.get_match_history(home, away, market)
            if len(history) >= 2:
                alarms = analyze_match_alarms(history, market)
                for alarm in alarms:
                    formatted = format_alarm_for_modal(alarm)
                    formatted['market'] = market
                    all_alarms.append(formatted)
        
        all_alarms.sort(key=lambda x: x.get('priority', 99))
        
        return jsonify({
            'alarms': all_alarms,
            'alarm_types': ALARM_TYPES
        })
    except Exception as e:
        print(f"[Match Alarms API] Error: {e}")
        return jsonify({'alarms': [], 'error': str(e)})


if __name__ == '__main__':
    if is_server_mode():
        start_server_scheduler()
    
    app.run(host='0.0.0.0', port=5000, debug=False)
