"""
SmartXFlow - Betting Odds Monitor
Desktop application with embedded web interface
"""

import os
import sys
import threading
import webbrowser

def resource_path(relative_path):
    """Get absolute path to resource for PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)

os.chdir(resource_path('.'))

from flask import Flask, render_template, jsonify, request
import json
import time
from datetime import datetime

from scraper.core import run_scraper, get_cookie_string
from services.supabase_client import LocalDatabase

template_folder = resource_path('templates')
static_folder = resource_path('static')

app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
app.secret_key = os.environ.get('SESSION_SECRET', 'smartxflow-secret-key')

db = LocalDatabase()

scrape_status = {
    "running": False,
    "auto_running": False,
    "last_result": None,
    "last_scrape_time": None
}

auto_scrape_thread = None
stop_auto_event = threading.Event()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/match/<home>/<away>')
def match_detail(home, away):
    return render_template('match_detail.html', home=home, away=away)


@app.route('/api/matches')
def get_matches():
    market = request.args.get('market', 'moneyway_1x2')
    matches = db.get_all_matches()
    
    enriched = []
    for m in matches:
        history = db.get_match_history(m['home_team'], m['away_team'], market)
        
        odds = {}
        if history:
            latest = history[-1]
            if market in ['moneyway_1x2', 'dropping_1x2']:
                odds = {
                    '1': latest.get('Odds1', latest.get('1', '-')),
                    'X': latest.get('OddsX', latest.get('X', '-')),
                    '2': latest.get('Odds2', latest.get('2', '-'))
                }
            elif market in ['moneyway_ou25', 'dropping_ou25']:
                odds = {
                    'Under': latest.get('Under', '-'),
                    'Over': latest.get('Over', '-')
                }
            elif market in ['moneyway_btts', 'dropping_btts']:
                odds = {
                    'Yes': latest.get('Yes', '-'),
                    'No': latest.get('No', '-')
                }
        
        enriched.append({
            'home_team': m.get('home_team', ''),
            'away_team': m.get('away_team', ''),
            'league': m.get('league', ''),
            'date': m.get('date', ''),
            'odds': odds,
            'history_count': len(history)
        })
    
    return jsonify(enriched)


@app.route('/api/match/history')
def get_match_history():
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
    global scrape_status
    
    if scrape_status['running']:
        return jsonify({'status': 'error', 'message': 'Scrape already running'})
    
    scrape_status['running'] = True
    
    def do_scrape():
        global scrape_status
        try:
            result = run_scraper()
            scrape_status['last_result'] = result
            scrape_status['last_scrape_time'] = datetime.now().isoformat()
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
    global scrape_status, auto_scrape_thread, stop_auto_event
    
    data = request.get_json() or {}
    action = data.get('action', 'toggle')
    interval = int(data.get('interval', 5))
    
    if action == 'start' and not scrape_status['auto_running']:
        scrape_status['auto_running'] = True
        stop_auto_event.clear()
        
        def auto_loop():
            global scrape_status
            while not stop_auto_event.is_set():
                if not scrape_status['running']:
                    scrape_status['running'] = True
                    try:
                        result = run_scraper()
                        scrape_status['last_result'] = result
                        scrape_status['last_scrape_time'] = datetime.now().isoformat()
                    except Exception as e:
                        scrape_status['last_result'] = {'status': 'error', 'error': str(e)}
                    finally:
                        scrape_status['running'] = False
                
                for _ in range(interval * 60):
                    if stop_auto_event.is_set():
                        break
                    time.sleep(1)
            
            scrape_status['auto_running'] = False
        
        auto_scrape_thread = threading.Thread(target=auto_loop)
        auto_scrape_thread.daemon = True
        auto_scrape_thread.start()
        
        return jsonify({'status': 'ok', 'auto_running': True})
    
    elif action == 'stop':
        stop_auto_event.set()
        scrape_status['auto_running'] = False
        return jsonify({'status': 'ok', 'auto_running': False})
    
    return jsonify({'status': 'ok', 'auto_running': scrape_status['auto_running']})


@app.route('/api/status')
def get_status():
    return jsonify({
        'running': scrape_status['running'],
        'auto_running': scrape_status['auto_running'],
        'last_result': scrape_status['last_result'],
        'last_scrape_time': scrape_status['last_scrape_time'],
        'cookie_set': bool(get_cookie_string())
    })


@app.route('/api/markets')
def get_markets():
    return jsonify([
        {'key': 'moneyway_1x2', 'label': 'Moneyway 1X2', 'icon': 'chart-line'},
        {'key': 'moneyway_ou25', 'label': 'Moneyway O/U 2.5', 'icon': 'chart-line'},
        {'key': 'moneyway_btts', 'label': 'Moneyway BTTS', 'icon': 'chart-line'},
        {'key': 'dropping_1x2', 'label': 'Dropping 1X2', 'icon': 'arrow-trend-down'},
        {'key': 'dropping_ou25', 'label': 'Dropping O/U 2.5', 'icon': 'arrow-trend-down'},
        {'key': 'dropping_btts', 'label': 'Dropping BTTS', 'icon': 'arrow-trend-down'}
    ])


def run_server():
    """Run Flask server"""
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)


def main():
    """Main entry point - starts server and opens browser"""
    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    
    time.sleep(1)
    
    webbrowser.open('http://127.0.0.1:5000')
    
    print("SmartXFlow is running at http://127.0.0.1:5000")
    print("Press Ctrl+C to exit")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--server':
        app.run(host='0.0.0.0', port=5000, debug=False)
    else:
        main()
