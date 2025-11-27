"""
SmartXFlow - Betting Odds Monitor
Flask Web Application with modern dark theme UI

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
from services.supabase_client import get_database
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


@app.route('/api/alarms')
def get_all_alarms():
    """Get all active alarms - grouped by match+type with event counts"""
    try:
        from core.alarms import group_alarms_by_match, format_grouped_alarm, get_critical_alarms
        
        all_alarms = []
        markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts']
        
        matches_data = db.get_all_matches_with_latest('moneyway_1x2')
        
        for match in matches_data[:50]:
            home = match.get('home_team', '')
            away = match.get('away_team', '')
            
            for market in markets:
                history = db.get_match_history(home, away, market)
                if len(history) >= 2:
                    alarms = analyze_match_alarms(history, market)
                    for alarm in alarms:
                        alarm['home'] = home
                        alarm['away'] = away
                        alarm['market'] = market
                        all_alarms.append(alarm)
        
        grouped = group_alarms_by_match(all_alarms)
        formatted = [format_grouped_alarm(g) for g in grouped]
        
        return jsonify({
            'alarms': formatted,
            'total': len(formatted),
            'event_count': sum(g['count'] for g in formatted)
        })
    except Exception as e:
        print(f"[Alarms API] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'alarms': [], 'total': 0, 'error': str(e)})


@app.route('/api/alarms/ticker')
def get_ticker_alarms():
    """Get critical alarms for borsa bandı - 20 items for scrolling ticker"""
    try:
        from core.alarms import get_critical_alarms, format_alarm_for_ticker, ALARM_TYPES
        
        all_alarms = []
        markets = ['moneyway_1x2']
        
        matches_data = db.get_all_matches_with_latest('moneyway_1x2')
        
        for match in matches_data[:50]:
            home = match.get('home_team', '')
            away = match.get('away_team', '')
            league = match.get('league', '')
            date = match.get('date', '')
            
            for market in markets:
                history = db.get_match_history(home, away, market)
                if len(history) >= 2:
                    alarms = analyze_match_alarms(history, market)
                    for alarm in alarms:
                        formatted = format_alarm_for_ticker(alarm, home, away)
                        formatted['market'] = market
                        formatted['match_id'] = generate_match_id(home, away, league, date)
                        formatted['league'] = league
                        formatted['date'] = date
                        all_alarms.append(formatted)
        
        critical = get_critical_alarms(all_alarms, limit=20)
        
        return jsonify({
            'alarms': critical[:20],
            'total': len(all_alarms)
        })
    except Exception as e:
        print(f"[Ticker API] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'alarms': [], 'total': 0})


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
