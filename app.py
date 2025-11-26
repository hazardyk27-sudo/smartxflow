"""
SmartXFlow - Web Application
Supabase'den veri okur ve gösterir (READ-ONLY)
Scraper ile ilgisi yok - bağımsız çalışır

APP_MODE:
- CLIENT: Windows EXE - Sadece Supabase'ten okur, scraper yok
- SERVER: Replit - Scraper aktif (şu an kullanılmıyor)
"""

import os
import sys
import webbrowser
import threading
from datetime import datetime
from flask import Flask, render_template, jsonify, request

APP_MODE = os.getenv("APP_MODE", "CLIENT")


def resource_path(relative_path):
    """PyInstaller EXE icinde dogru path'i bulmak icin"""
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def get_supabase_credentials():
    """Get Supabase credentials from embedded config or environment"""
    try:
        config_path = resource_path("embedded_config.py")
        if os.path.exists(config_path):
            import embedded_config
            url = getattr(embedded_config, 'EMBEDDED_SUPABASE_URL', '')
            key = getattr(embedded_config, 'EMBEDDED_SUPABASE_KEY', '')
            if url and key:
                return url, key
    except Exception:
        pass
    
    try:
        import embedded_config
        url = getattr(embedded_config, 'EMBEDDED_SUPABASE_URL', '')
        key = getattr(embedded_config, 'EMBEDDED_SUPABASE_KEY', '')
        if url and key:
            return url, key
    except ImportError:
        pass
    
    url = os.environ.get('SUPABASE_URL', '')
    key = os.environ.get('SUPABASE_ANON_KEY', '') or os.environ.get('SUPABASE_KEY', '')
    return url, key

SUPABASE_URL, SUPABASE_KEY = get_supabase_credentials()

import httpx

template_dir = resource_path("templates")
static_dir = resource_path("static")

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
app.secret_key = os.environ.get('SESSION_SECRET', 'smartxflow-secret-key')

ALARM_TYPES = {
    'reverse_line_move': {'name': 'Reverse Line Move (RLM)', 'icon': '🔴', 'color': '#ff4444'},
    'sharp_move': {'name': 'Sharp Move', 'icon': '🟢', 'color': '#00c851'},
    'big_money': {'name': 'Big Money Move', 'icon': '⚠', 'color': '#ffbb33'},
    'line_freeze': {'name': 'Line Freeze', 'icon': '🔵', 'color': '#33b5e5'},
    'public_money': {'name': 'Public Money Surge', 'icon': '🟡', 'color': '#ffeb3b'},
    'momentum': {'name': 'Momentum Spike', 'icon': '🟣', 'color': '#aa66cc'}
}


def get_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }


def fetch_market_data(market):
    """Fetch data from Supabase history table"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        print(f"[DEBUG] fetch_market_data: No Supabase credentials!")
        return []
    
    table = f"{market}_history"
    url = f"{SUPABASE_URL}/rest/v1/{table}?select=*&order=scrapedat.desc"
    
    try:
        print(f"[DEBUG] Fetching {market} from {table}...")
        resp = httpx.get(url, headers=get_headers(), timeout=15)
        print(f"[DEBUG] Response status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"[DEBUG] Got {len(data)} rows for {market}")
            return data
        else:
            print(f"[DEBUG] Error response: {resp.text[:200]}")
        return []
    except Exception as e:
        print(f"[ERROR] fetch_market_data {market}: {e}")
        return []


def get_latest_for_each_match(data, market):
    """Get latest record for each match"""
    matches = {}
    
    for row in data:
        match_id = row.get('id') or row.get('ID', '')
        if not match_id:
            continue
        
        if match_id not in matches:
            matches[match_id] = row
    
    return list(matches.values())


def g(row, *keys):
    """Get value from row trying multiple key variations"""
    for key in keys:
        val = row.get(key) or row.get(key.lower()) or row.get(key.upper())
        if val:
            return val
    return ''


def format_match(row, market):
    """Format match data for frontend"""
    is_dropping = market.startswith('dropping')
    
    match = {
        'id': g(row, 'id', 'ID'),
        'league': g(row, 'league', 'League'),
        'date': g(row, 'date', 'Date'),
        'home_team': g(row, 'home', 'Home'),
        'away_team': g(row, 'away', 'Away'),
        'volume': g(row, 'volume', 'Volume'),
        'scraped_at': g(row, 'scrapedat', 'ScrapedAt')
    }
    
    details = {}
    
    if '1x2' in market:
        details = {
            'Odds1': g(row, 'odds1', 'Odds1'),
            'OddsX': g(row, 'oddsx', 'OddsX'),
            'Odds2': g(row, 'odds2', 'Odds2'),
            'Pct1': g(row, 'pct1', 'Pct1'),
            'Amt1': g(row, 'amt1', 'Amt1'),
            'PctX': g(row, 'pctx', 'PctX'),
            'AmtX': g(row, 'amtx', 'AmtX'),
            'Pct2': g(row, 'pct2', 'Pct2'),
            'Amt2': g(row, 'amt2', 'Amt2'),
            'Volume': g(row, 'volume', 'Volume')
        }
        if is_dropping:
            details.update({
                'Odds1_prev': g(row, 'odds1_prev', 'Odds1_prev'),
                'OddsX_prev': g(row, 'oddsx_prev', 'OddsX_prev'),
                'Odds2_prev': g(row, 'odds2_prev', 'Odds2_prev'),
                'Trend1': g(row, 'trend1', 'Trend1'),
                'TrendX': g(row, 'trendx', 'TrendX'),
                'Trend2': g(row, 'trend2', 'Trend2')
            })
    
    elif 'ou25' in market:
        details = {
            'Under': g(row, 'under', 'Under'),
            'Line': g(row, 'line', 'Line'),
            'Over': g(row, 'over', 'Over'),
            'PctUnder': g(row, 'pctunder', 'PctUnder'),
            'AmtUnder': g(row, 'amtunder', 'AmtUnder'),
            'PctOver': g(row, 'pctover', 'PctOver'),
            'AmtOver': g(row, 'amtover', 'AmtOver'),
            'Volume': g(row, 'volume', 'Volume')
        }
        if is_dropping:
            details.update({
                'Under_prev': g(row, 'under_prev', 'Under_prev'),
                'Over_prev': g(row, 'over_prev', 'Over_prev'),
                'TrendUnder': g(row, 'trendunder', 'TrendUnder'),
                'TrendOver': g(row, 'trendover', 'TrendOver')
            })
    
    elif 'btts' in market:
        details = {
            'OddsYes': g(row, 'yes', 'Yes', 'oddsyes', 'OddsYes'),
            'OddsNo': g(row, 'no', 'No', 'oddsno', 'OddsNo'),
            'PctYes': g(row, 'pctyes', 'PctYes'),
            'AmtYes': g(row, 'amtyes', 'AmtYes'),
            'PctNo': g(row, 'pctno', 'PctNo'),
            'AmtNo': g(row, 'amtno', 'AmtNo'),
            'Volume': g(row, 'volume', 'Volume')
        }
        if is_dropping:
            details.update({
                'OddsYes_prev': g(row, 'oddsyes_prev', 'OddsYes_prev'),
                'OddsNo_prev': g(row, 'oddsno_prev', 'OddsNo_prev'),
                'TrendYes': g(row, 'trendyes', 'TrendYes'),
                'TrendNo': g(row, 'trendno', 'TrendNo')
            })
    
    match['details'] = details
    return match


def analyze_alarms(match, market):
    """Analyze match for alarm conditions"""
    alarms = []
    
    try:
        volume_str = match.get('volume', '0').replace('£', '').replace(',', '').strip()
        volume = float(volume_str) if volume_str else 0
    except:
        volume = 0
    
    if volume > 100000:
        alarms.append({
            'type': 'big_money',
            'message': f"High volume: £{volume:,.0f}"
        })
    
    if 'dropping' in market:
        for key in ['trend1', 'trendX', 'trend2', 'trendUnder', 'trendOver', 'trendYes', 'trendNo']:
            trend = match.get(key, '')
            if trend and trend.lower() in ['down', 'up']:
                alarms.append({
                    'type': 'sharp_move',
                    'message': f"Odds movement detected"
                })
                break
    
    return alarms


@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/matches')
def get_matches():
    market = request.args.get('market', 'moneyway_1x2')
    
    data = fetch_market_data(market)
    latest = get_latest_for_each_match(data, market)
    
    matches = []
    for row in latest:
        match = format_match(row, market)
        match['alarms'] = analyze_alarms(match, market)
        matches.append(match)
    
    return jsonify(matches)


@app.route('/api/match/<match_id>/history')
def get_match_history_by_id(match_id):
    market = request.args.get('market', 'moneyway_1x2')
    
    table = f"{market}_history"
    url = f"{SUPABASE_URL}/rest/v1/{table}?id=eq.{match_id}&select=*&order=scrapedat.asc"
    
    try:
        resp = httpx.get(url, headers=get_headers(), timeout=15)
        if resp.status_code == 200:
            history = resp.json()
            return jsonify({
                'history': history,
                'count': len(history)
            })
    except Exception as e:
        print(f"Error: {e}")
    
    return jsonify({'history': [], 'count': 0})


@app.route('/api/match/history')
def get_match_history():
    """Get match history by home/away team names"""
    home = request.args.get('home', '')
    away = request.args.get('away', '')
    market = request.args.get('market', 'moneyway_1x2')
    
    if not home or not away:
        return jsonify({'history': [], 'count': 0})
    
    table = f"{market}_history"
    url = f"{SUPABASE_URL}/rest/v1/{table}?home=ilike.{home}*&away=ilike.{away}*&select=*&order=scrapedat.asc"
    
    try:
        resp = httpx.get(url, headers=get_headers(), timeout=15)
        if resp.status_code == 200:
            history = resp.json()
            formatted = []
            for row in history:
                formatted.append({
                    'ScrapedAt': g(row, 'scrapedat', 'ScrapedAt'),
                    'Odds1': g(row, 'odds1', 'Odds1'),
                    'OddsX': g(row, 'oddsx', 'OddsX'),
                    'Odds2': g(row, 'odds2', 'Odds2'),
                    'Pct1': g(row, 'pct1', 'Pct1'),
                    'PctX': g(row, 'pctx', 'PctX'),
                    'Pct2': g(row, 'pct2', 'Pct2'),
                    'Amt1': g(row, 'amt1', 'Amt1'),
                    'AmtX': g(row, 'amtx', 'AmtX'),
                    'Amt2': g(row, 'amt2', 'Amt2'),
                    'Volume': g(row, 'volume', 'Volume'),
                    'Under': g(row, 'under', 'Under'),
                    'Over': g(row, 'over', 'Over'),
                    'Line': g(row, 'line', 'Line'),
                    'OddsYes': g(row, 'yes', 'Yes', 'oddsyes', 'OddsYes'),
                    'OddsNo': g(row, 'no', 'No', 'oddsno', 'OddsNo'),
                    'Trend1': g(row, 'trend1', 'Trend1'),
                    'TrendX': g(row, 'trendx', 'TrendX'),
                    'Trend2': g(row, 'trend2', 'Trend2')
                })
            return jsonify({
                'history': formatted,
                'count': len(formatted)
            })
    except Exception as e:
        print(f"Error fetching history: {e}")
    
    return jsonify({'history': [], 'count': 0})


@app.route('/api/match/alarms')
def get_match_alarms():
    """Get alarms for a specific match"""
    home = request.args.get('home', '')
    away = request.args.get('away', '')
    
    return jsonify({'alarms': [], 'count': 0})


@app.route('/api/alarms')
def get_alarms():
    all_alarms = []
    
    for market in ['moneyway_1x2', 'dropping_1x2', 'moneyway_ou25', 'dropping_ou25']:
        data = fetch_market_data(market)
        latest = get_latest_for_each_match(data, market)
        
        for row in latest:
            match = format_match(row, market)
            alarms = analyze_alarms(match, market)
            
            for alarm in alarms:
                all_alarms.append({
                    'match': f"{match['home_team']} vs {match['away_team']}",
                    'league': match['league'],
                    'type': alarm['type'],
                    'message': alarm['message'],
                    'market': market
                })
    
    return jsonify({
        'alarms': all_alarms[:20],
        'count': len(all_alarms)
    })


@app.route('/api/status')
def get_status():
    connected = bool(SUPABASE_URL and SUPABASE_KEY)
    
    if connected:
        try:
            url = f"{SUPABASE_URL}/rest/v1/moneyway_1x2_history?select=scrapedat&order=scrapedat.desc&limit=1"
            resp = httpx.get(url, headers=get_headers(), timeout=10)
            if resp.status_code == 200 and resp.json():
                last_update = resp.json()[0].get('scrapedat', '')
            else:
                last_update = None
        except:
            last_update = None
    else:
        last_update = None
    
    return jsonify({
        'supabase_connected': connected,
        'last_data_update': last_update,
        'mode': APP_MODE.lower(),
        'version': '1.0'
    })


def open_browser():
    """Open browser after Flask starts"""
    import time
    time.sleep(1.5)
    webbrowser.open('http://127.0.0.1:5000')


def main():
    """Main entry point"""
    print("=" * 50)
    print("SmartXFlow Alarm V1.01")
    print("=" * 50)
    print(f"Mode: {APP_MODE}")
    print(f"Supabase URL: {'Connected' if SUPABASE_URL else 'NOT SET'}")
    print(f"Supabase Key: {'Set' if SUPABASE_KEY else 'NOT SET'}")
    print(f"Templates: {template_dir}")
    print(f"Static: {static_dir}")
    print("=" * 50)
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("\nWARNING: Supabase credentials not found!")
        print("Please ensure embedded_config.py is included in the build.")
        print("Or set SUPABASE_URL and SUPABASE_ANON_KEY environment variables.")
    
    if getattr(sys, 'frozen', False):
        threading.Thread(target=open_browser, daemon=True).start()
    
    print(f"\nStarting server on http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        import traceback
        print("\n" + "=" * 50)
        print("FATAL ERROR during startup:")
        print("=" * 50)
        print(str(e))
        print("\nFull traceback:")
        traceback.print_exc()
        print("=" * 50)
        input("\nPress ENTER to close...")
