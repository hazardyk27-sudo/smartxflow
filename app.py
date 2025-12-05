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
alarm_scheduler_thread = None
last_cleanup_date = None
last_alarm_calc_time = None


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


def run_alarm_calculations():
    """Run all alarm calculations"""
    global sharp_alarms, insider_alarms, big_money_alarms, volume_shock_alarms, last_alarm_calc_time
    
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
        
        # Insider alarms - eski alarmlar korunur, yeniler eklenir (oran değişirse)
        try:
            new_insider = calculate_insider_scores(sharp_config, insider_alarms)
            if new_insider:
                # Mevcut alarmları koru, yenileri ekle
                insider_alarms = merge_insider_alarms(insider_alarms, new_insider)
                save_insider_alarms_to_file(insider_alarms)
                print(f"[Alarm Scheduler] Insider: {len(insider_alarms)} alarms")
        except Exception as e:
            print(f"[Alarm Scheduler] Insider error: {e}")
        
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
        
        # Dropping alarms - uses global dropping_config (refreshed from Supabase)
        try:
            new_dropping = calculate_dropping_scores(dropping_config)
            if new_dropping:
                global dropping_alarms
                dropping_alarms = new_dropping
                save_dropping_alarms_to_file(dropping_alarms)
                print(f"[Alarm Scheduler] Dropping: {len(dropping_alarms)} alarms")
        except Exception as e:
            print(f"[Alarm Scheduler] Dropping error: {e}")
        
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
    """Start periodic alarm calculation scheduler"""
    global alarm_scheduler_thread
    
    interval_seconds = 600  # 10 minutes
    
    def alarm_loop():
        print(f"[Alarm Scheduler] Started - interval: {interval_seconds // 60} minutes")
        # Wait 60 seconds before first calculation (let server fully start)
        time.sleep(60)
        
        while True:
            run_alarm_calculations()
            time.sleep(interval_seconds)
    
    alarm_scheduler_thread = threading.Thread(target=alarm_loop, daemon=True)
    alarm_scheduler_thread.start()


def start_server_scheduler():
    """Start background scheduler for server mode - runs scraper periodically"""
    global server_scheduler_thread, server_scheduler_stop, scrape_status
    
    if not is_server_mode():
        return
    
    if is_scraper_disabled():
        print("[Server Mode] Scraper disabled via DISABLE_SCRAPER env variable")
        print("[Server Mode] Running as UI-only, data comes from Supabase (standalone scraper)")
        scrape_status['auto_running'] = False
        return
    
    server_scheduler_stop.clear()
    interval_seconds = get_scrape_interval_seconds()
    scrape_status['auto_running'] = True
    scrape_status['interval_minutes'] = interval_seconds // 60
    
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
                    
            elif alarm_type == 'publictrap' and config:
                old = publicmove_config.copy()
                publicmove_config.update(config)
                publicmove_config['enabled'] = enabled
                if old != publicmove_config:
                    changes.append('publictrap')
                    
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

# ==================== HALK TUZAĞI ALARM SYSTEM ====================
# (Sharp alarm'ın birebir kopyası, farklı isim)
PUBLICMOVE_CONFIG_FILE = 'publicmove_config.json'
PUBLICMOVE_ALARMS_FILE = 'publicmove_alarms.json'

def load_publicmove_config_from_file():
    """Load Public Move config from JSON file"""
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
        if os.path.exists(PUBLICMOVE_CONFIG_FILE):
            with open(PUBLICMOVE_CONFIG_FILE, 'r') as f:
                saved_config = json.load(f)
                default_config.update(saved_config)
                print(f"[PublicMove] Config loaded from {PUBLICMOVE_CONFIG_FILE}: min_sharp_score={default_config.get('min_sharp_score')}")
    except Exception as e:
        print(f"[PublicMove] Config load error: {e}")
    return default_config

def save_publicmove_config_to_file(config):
    """Save Public Move config to JSON file"""
    try:
        with open(PUBLICMOVE_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"[PublicMove] Config saved to {PUBLICMOVE_CONFIG_FILE}")
        return True
    except Exception as e:
        print(f"[PublicMove] Config save error: {e}")
        return False

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
    """Save Public Move alarms to JSON file"""
    try:
        with open(PUBLICMOVE_ALARMS_FILE, 'w') as f:
            json.dump(alarms, f, indent=2, ensure_ascii=False)
        print(f"[PublicMove] Saved {len(alarms)} alarms to {PUBLICMOVE_ALARMS_FILE}")
        return True
    except Exception as e:
        print(f"[PublicMove] Alarms save error: {e}")
        return False

publicmove_alarms = load_publicmove_alarms_from_file()
publicmove_calculating = False
publicmove_calc_progress = ""

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


def merge_insider_alarms(existing_alarms, new_alarms):
    """
    Merge existing and new insider alarms.
    - Keep existing alarms (don't delete old ones)
    - Add new alarms (avoid duplicates)
    - Remove D-2+ alarms (old matches)
    """
    today = now_turkey().date()
    yesterday = today - timedelta(days=1)
    
    # Create unique key for each alarm
    def alarm_key(alarm):
        return f"{alarm.get('home', '')}_{alarm.get('away', '')}_{alarm.get('market', '')}_{alarm.get('selection', '')}_{alarm.get('event_time', '')}"
    
    # Start with existing alarms
    merged = {}
    
    # Add existing alarms (filter out D-2+ ones)
    for alarm in existing_alarms:
        match_date_str = alarm.get('match_date', '')
        try:
            # Parse match date
            if match_date_str:
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
                
                # Skip D-2+ alarms
                if match_date < yesterday:
                    continue
        except:
            pass  # Keep alarm if date parsing fails
        
        key = alarm_key(alarm)
        merged[key] = alarm
    
    # Add new alarms
    added_count = 0
    for alarm in new_alarms:
        key = alarm_key(alarm)
        if key not in merged:
            merged[key] = alarm
            added_count += 1
    
    result = list(merged.values())
    print(f"[Insider] Merged: {len(existing_alarms)} existing + {added_count} new = {len(result)} total (D-2+ filtered)")
    
    return result


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
        new_alarms = calculate_insider_scores(sharp_config, insider_alarms)
        insider_alarms = merge_insider_alarms(insider_alarms, new_alarms)
        save_insider_alarms_to_file(insider_alarms)
        return jsonify({'success': True, 'count': len(insider_alarms)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


def calculate_insider_scores(config, existing_alarms=None):
    """
    Calculate Insider Info alarms with rolling window approach.
    
    INSIDER ALARM CONDITIONS (must be met for consecutive snapshots):
    1. HacimSok < insider_hacim_sok_esigi (default: 2)
    2. OranDususu >= insider_oran_dusus_esigi (default: 3%)
    3. GelenPara < insider_max_para (default: 5000)
    
    These conditions must persist for insider_sure_dakika minutes (default: 30)
    which equals 3 consecutive 10-minute snapshots.
    
    DUPLICATE PREVENTION: If alarm already exists for same match+market+selection
    and the odds haven't changed since last alarm, don't create a new alarm.
    """
    alarms = []
    existing_alarms = existing_alarms or []
    
    # Build lookup dict for existing alarms: key -> last_odds
    existing_odds_map = {}
    for ea in existing_alarms:
        key = f"{ea.get('home', '')}_{ea.get('away', '')}_{ea.get('market', '')}_{ea.get('selection', '')}"
        existing_odds_map[key] = ea.get('last_odds', 0)
    
    supabase = get_supabase_client()
    if not supabase or not supabase.is_available:
        print("[Insider] Supabase not available")
        return alarms
    
    # Get config parameters with Turkish names
    hacim_sok_esigi = config.get('insider_hacim_sok_esigi', 2)
    oran_dusus_esigi = config.get('insider_oran_dusus_esigi', 3)
    sure_dakika = config.get('insider_sure_dakika', 30)
    max_para = config.get('insider_max_para', 5000)
    max_odds_esigi = config.get('insider_max_odds_esigi', 10.0)  # Max odds threshold - filter out high odds
    
    # Calculate required consecutive snapshots (10 min per snapshot)
    snapshot_interval = 10  # minutes
    required_streak = max(1, sure_dakika // snapshot_interval)
    
    print(f"[Insider] Config: HacimSok<{hacim_sok_esigi}, OranDusus>={oran_dusus_esigi}%, Sure={sure_dakika}dk ({required_streak} snapshot), MaxPara<{max_para}, MaxOdds<{max_odds_esigi}")
    
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
                    
                    # Max odds filter - skip selections with odds higher than threshold
                    last_odds = parse_float(history[-1].get(odds_key, '0'))
                    if last_odds > max_odds_esigi:
                        continue  # Skip this selection - odds too high
                    
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
                            'amount_change': amount_change,
                            'amount': current_amount  # Store actual amount for window calculation
                        })
                    
                    # ========================================================
                    # YENİ MANTIK: Açılıştan bugüne oran düşüşü + düşüş anı etrafındaki snapshotlar
                    # ========================================================
                    
                    # Son snapshot'taki oran
                    current_odds = snapshot_metrics[-1]['odds'] if snapshot_metrics else 0
                    
                    # Açılıştan bugüne oran düşüşü (%)
                    if opening_odds > 0 and current_odds > 0 and current_odds < opening_odds:
                        opening_to_now_drop_pct = ((opening_odds - current_odds) / opening_odds) * 100
                    else:
                        opening_to_now_drop_pct = 0
                    
                    # KOŞUL 1: Açılıştan bugüne oran düşüşü >= eşik
                    if opening_to_now_drop_pct < oran_dusus_esigi:
                        continue  # Yeterli düşüş yok, sonraki selection'a geç
                    
                    # ========================================================
                    # En büyük YÜZDESEL oran düşüşünün gerçekleştiği anı bul
                    # ========================================================
                    max_drop_index = -1
                    max_single_drop_pct = 0
                    
                    for i in range(1, len(snapshot_metrics)):
                        prev_odds = snapshot_metrics[i-1]['odds']
                        curr_odds = snapshot_metrics[i]['odds']
                        
                        if prev_odds > 0 and curr_odds < prev_odds:
                            # YÜZDESEL düşüş hesapla (mutlak değil)
                            single_drop_pct = ((prev_odds - curr_odds) / prev_odds) * 100
                            if single_drop_pct > max_single_drop_pct:
                                max_single_drop_pct = single_drop_pct
                                max_drop_index = i
                    
                    # Eğer düşüş anı bulunamadıysa, son snapshot'ı kullan
                    if max_drop_index == -1:
                        max_drop_index = len(snapshot_metrics) - 1
                    
                    # ========================================================
                    # Düşüş anının etrafındaki snapshotlara bak
                    # required_streak: Toplam bakılacak snapshot sayısı (admin'den ayarlanabilir)
                    # Örnek: 7 snapshot = 3 öncesi + 1 düşüş anı + 3 sonrası
                    # ========================================================
                    half_window = required_streak // 2
                    
                    # Window sınırlarını hesapla
                    window_start_idx = max(0, max_drop_index - half_window)
                    window_end_idx = min(len(snapshot_metrics), max_drop_index + half_window + 1)
                    
                    # Window'u al
                    window = snapshot_metrics[window_start_idx:window_end_idx]
                    
                    if len(window) < 2:
                        continue  # Yeterli snapshot yok
                    
                    # Check if ALL snapshots in window meet conditions (HacimSok, GelenPara)
                    all_qualify = True
                    for snap_metric in window:
                        # Condition 1: HacimSok < esik (düşük hacim şoku = sessiz hareket)
                        if snap_metric['hacim_sok'] >= hacim_sok_esigi:
                            all_qualify = False
                            break
                        # Condition 2: GelenPara < max_para (düşük para girişi)
                        if snap_metric['gelen_para'] >= max_para:
                            all_qualify = False
                            break
                    
                    alarm_triggered = all_qualify
                    best_window = window if all_qualify else None
                    best_window_drop_pct = opening_to_now_drop_pct  # Açılıştan bugüne düşüş
                    
                    if alarm_triggered and best_window:
                        # DUPLICATE PREVENTION: Check if alarm already exists with same odds
                        alarm_key = f"{home}_{away}_{market_names.get(market, market)}_{selection}"
                        last_odds_val = parse_float(history[-1].get(odds_key, '0'))
                        
                        if alarm_key in existing_odds_map:
                            prev_last_odds = existing_odds_map[alarm_key]
                            # If odds haven't changed, skip creating duplicate alarm
                            if abs(last_odds_val - prev_last_odds) < 0.01:
                                print(f"[Insider] SKIP: {home} vs {away} [{selection}] - oran degismedi ({last_odds_val:.2f} = {prev_last_odds:.2f})")
                                continue
                        
                        # Use last snapshot in window for alarm details
                        last_snap = best_window[-1]
                        first_snap = best_window[0]
                        
                        # Calculate averages over the window
                        avg_hacim_sok = sum(s['hacim_sok'] for s in best_window) / len(best_window)
                        
                        # Gelen Para: Window boyunca gelen toplam para (son - ilk)
                        window_first_amount = first_snap.get('amount', 0)
                        window_last_amount = last_snap.get('amount', 0)
                        window_gelen_para = max(0, window_last_amount - window_first_amount)
                        
                        # Event time: hareketin tespit edildiği snapshot zamanı
                        last_snap_idx = last_snap['index']
                        first_snap_idx = first_snap['index']
                        event_time = history[last_snap_idx].get('scrapedat', '') if last_snap_idx < len(history) else ''
                        
                        # Açılıştan bugüne oran bilgileri (YENİ)
                        window_start_odds = opening_odds  # Açılış oranı
                        window_end_odds = current_odds    # Şu anki oran (son snapshot)
                        
                        # Açılıştan bugüne düşüş yüzdesi
                        window_odds_drop_pct = opening_to_now_drop_pct
                        
                        # Snapshot detayları (her snapshot için oran, zaman ve para)
                        snapshot_details = []
                        for snap in best_window:
                            snap_idx = snap['index']
                            snap_odds = snap['odds']
                            snap_amount = snap.get('amount', 0)
                            snap_time = history[snap_idx].get('scrapedat', '') if snap_idx < len(history) else ''
                            snapshot_details.append({
                                'odds': snap_odds,
                                'amount': snap_amount,
                                'time': snap_time
                            })
                        
                        created_at = now_turkey().strftime('%d.%m.%Y %H:%M')
                        last_odds = parse_float(history[-1].get(odds_key, '0'))
                        
                        # Düşüş anı zamanı (drop_time)
                        drop_time = history[max_drop_index].get('scrapedat', '') if max_drop_index < len(history) else ''
                        
                        alarm = {
                            'home': home,
                            'away': away,
                            'market': market_names.get(market, market),
                            'selection': selection,
                            'hacim_sok': avg_hacim_sok,
                            'oran_dusus_pct': window_odds_drop_pct,  # Açılıştan bugüne düşüş
                            'gelen_para': window_gelen_para,  # Window boyunca toplam gelen para (son - ilk)
                            'opening_odds': opening_odds,
                            'last_odds': last_odds,
                            # Düşüş anı bilgisi (YENİ)
                            'drop_time': drop_time,
                            'drop_index': max_drop_index,
                            # Snapshot window bilgileri
                            'window_start_odds': window_start_odds,
                            'window_end_odds': window_end_odds,
                            'window_odds_drop_pct': window_odds_drop_pct,
                            'snapshot_details': snapshot_details,
                            # Config
                            'insider_hacim_sok_esigi': hacim_sok_esigi,
                            'insider_oran_dusus_esigi': oran_dusus_esigi,
                            'insider_sure_dakika': sure_dakika,
                            'insider_max_para': max_para,
                            'insider_max_odds_esigi': max_odds_esigi,
                            'snapshot_count': required_streak,
                            'match_date': match_date_str,
                            'event_time': event_time,
                            'created_at': created_at,
                            'triggered': True
                        }
                        alarms.append(alarm)
                        drop_snap_time = drop_time[:16] if drop_time else ''
                        print(f"[Insider] ALARM: {home} vs {away} [{selection}] Acilis->Simdi: {opening_odds:.2f}->{current_odds:.2f} ({opening_to_now_drop_pct:.1f}%), DususAni: {drop_snap_time}, Window: {len(best_window)} snap")
        
        except Exception as e:
            print(f"[Insider] Error processing {market}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"[Insider] Total alarms found: {len(alarms)}")
    return alarms


# ============================================================================
# BIG MONEY ALARM SYSTEM
# ============================================================================

BIG_MONEY_CONFIG_FILE = 'big_money_config.json'
BIG_MONEY_ALARMS_FILE = 'big_money_alarms.json'

big_money_calculating = False
big_money_calc_progress = ""

def load_big_money_config():
    """Load Big Money config from JSON file"""
    try:
        if os.path.exists(BIG_MONEY_CONFIG_FILE):
            with open(BIG_MONEY_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                print(f"[BigMoney] Config loaded: limit={config.get('big_money_limit', 15000)}")
                return config
    except Exception as e:
        print(f"[BigMoney] Config load error: {e}")
    return {'big_money_limit': 15000}

def save_big_money_config(config):
    """Save Big Money config to JSON file"""
    try:
        with open(BIG_MONEY_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"[BigMoney] Config saved: limit={config.get('big_money_limit')}")
        return True
    except Exception as e:
        print(f"[BigMoney] Config save error: {e}")
        return False

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
    """Save Big Money alarms to JSON file"""
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
    """Get Big Money config"""
    return jsonify(big_money_config)


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
    """Get all Big Money alarms"""
    return jsonify(big_money_alarms)


@app.route('/api/bigmoney/delete', methods=['POST'])
def delete_big_money_alarms():
    """Delete all Big Money alarms"""
    global big_money_alarms
    try:
        big_money_alarms = []
        save_big_money_alarms_to_file(big_money_alarms)
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
    
    limit = config.get('big_money_limit', 15000)
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
                                'scrapedat': history[i].get('scrapedat', '')
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
                    event_time = max_snapshot.get('scrapedat', '')
                    created_at = now_turkey().strftime('%d.%m.%Y %H:%M')
                    
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
                        'created_at': created_at
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
DROPPING_ALARMS_FILE = 'dropping_alarms.json'

dropping_calculating = False
dropping_calc_progress = ""

def load_dropping_config():
    """Load Dropping Alert config from JSON file"""
    try:
        if os.path.exists(DROPPING_CONFIG_FILE):
            with open(DROPPING_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                print(f"[Dropping] Config loaded: L1={config.get('min_drop_l1', 7)}-{config.get('max_drop_l1', 10)}%, L2={config.get('min_drop_l2', 10)}-{config.get('max_drop_l2', 15)}%, L3={config.get('min_drop_l3', 15)}%+")
                return config
    except Exception as e:
        print(f"[Dropping] Config load error: {e}")
    return {
        'enabled': True,
        'min_drop_l1': 7,
        'max_drop_l1': 10,
        'min_drop_l2': 10,
        'max_drop_l2': 15,
        'min_drop_l3': 15,
        'l2_enabled': True,
        'l3_enabled': True,
        'persistence_minutes': 30,
        'persistence_enabled': True,
        'min_volume_1x2': 3000,
        'min_volume_ou25': 1000,
        'min_volume_btts': 500
    }

def save_dropping_config(config):
    """Save Dropping Alert config to JSON file"""
    try:
        with open(DROPPING_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"[Dropping] Config saved")
        return True
    except Exception as e:
        print(f"[Dropping] Config save error: {e}")
        return False

def load_dropping_alarms_from_file():
    """Load Dropping Alert alarms from JSON file"""
    try:
        if os.path.exists(DROPPING_ALARMS_FILE):
            with open(DROPPING_ALARMS_FILE, 'r') as f:
                alarms = json.load(f)
                print(f"[Dropping] Loaded {len(alarms)} alarms from {DROPPING_ALARMS_FILE}")
                return alarms
    except Exception as e:
        print(f"[Dropping] Alarms load error: {e}")
    return []

def save_dropping_alarms_to_file(alarms):
    """Save Dropping Alert alarms to JSON file"""
    try:
        with open(DROPPING_ALARMS_FILE, 'w') as f:
            json.dump(alarms, f, indent=2, ensure_ascii=False)
        print(f"[Dropping] Saved {len(alarms)} alarms to {DROPPING_ALARMS_FILE}")
        return True
    except Exception as e:
        print(f"[Dropping] Alarms save error: {e}")
        return False

dropping_config = load_dropping_config()
dropping_alarms = load_dropping_alarms_from_file()


@app.route('/api/dropping/config', methods=['GET'])
def get_dropping_config():
    """Get Dropping Alert config"""
    return jsonify(dropping_config)


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


@app.route('/api/dropping/alarms', methods=['GET'])
def get_dropping_alarms():
    """Get all Dropping Alert alarms"""
    return jsonify(dropping_alarms)


@app.route('/api/dropping/delete', methods=['POST'])
def delete_dropping_alarms():
    """Delete all Dropping Alert alarms"""
    global dropping_alarms
    try:
        dropping_alarms = []
        save_dropping_alarms_to_file(dropping_alarms)
        print("[Dropping] All alarms deleted")
        return jsonify({'success': True})
    except Exception as e:
        print(f"[Dropping] Delete error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/dropping/status', methods=['GET'])
def get_dropping_status():
    """Get Dropping Alert calculation status"""
    return jsonify({
        'calculating': dropping_calculating,
        'progress': dropping_calc_progress,
        'alarm_count': len(dropping_alarms)
    })


@app.route('/api/dropping/calculate', methods=['POST'])
def calculate_dropping_alarms_endpoint():
    """Calculate Dropping Alert alarms based on config"""
    global dropping_alarms, dropping_calculating
    try:
        dropping_calculating = True
        dropping_alarms = calculate_dropping_scores(dropping_config)
        save_dropping_alarms_to_file(dropping_alarms)
        dropping_calculating = False
        return jsonify({'success': True, 'count': len(dropping_alarms)})
    except Exception as e:
        dropping_calculating = False
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


def find_drop_trigger_time(full_history, odds_key, threshold_pct):
    """
    Find when the drop was first detected by scanning history snapshots.
    Returns the scrapedat of the first snapshot where drop >= threshold.
    
    Args:
        full_history: List of history rows ordered by scrapedat (ascending)
        odds_key: The odds column name (e.g., 'odds1', 'under', 'oddsyes')
        threshold_pct: Minimum drop percentage to consider (e.g., 7%)
    
    Returns:
        scrapedat string when drop first detected, or None
    """
    if not full_history or len(full_history) < 2:
        return None
    
    # Get opening odds from first snapshot
    first_row = full_history[0]
    opening_odds_str = first_row.get(odds_key, '')
    
    # Parse opening odds
    try:
        if opening_odds_str in (None, '', '-'):
            return None
        opening_odds = float(str(opening_odds_str).replace(',', '.').split('\n')[0])
        if opening_odds <= 0:
            return None
    except:
        return None
    
    # Scan through history to find first drop >= threshold
    for row in full_history[1:]:  # Skip first row (it's the opening)
        current_odds_str = row.get(odds_key, '')
        
        try:
            if current_odds_str in (None, '', '-'):
                continue
            current_odds = float(str(current_odds_str).replace(',', '.').split('\n')[0])
            if current_odds <= 0:
                continue
        except:
            continue
        
        # Calculate drop percentage
        if current_odds < opening_odds:
            drop_pct = ((opening_odds - current_odds) / opening_odds) * 100
            if drop_pct >= threshold_pct:
                # Found the first snapshot where drop crossed threshold
                return row.get('scrapedat', '')
    
    return None


def calculate_dropping_scores(config):
    """
    Calculate Dropping Alert alarms based on opening odds vs current odds drop percentage.
    Uses get_6h_odds_history which efficiently compares first snapshot vs last snapshot.
    
    IMPORTANT: Only creates alarms for matches that exist in BOTH Moneyway AND Dropping markets:
    - 1X2 selections: Match must be in moneyway_1x2 AND dropping_1x2
    - O/U 2.5 selections: Match must be in moneyway_ou25 AND dropping_ou25
    - BTTS selections: Match must be in moneyway_btts AND dropping_btts
    
    L1: min_drop_l1% - max_drop_l1% drop (e.g., 7-10%)
    L2: min_drop_l2% - max_drop_l2% drop (e.g., 10-15%)
    L3: min_drop_l3%+ drop (e.g., 15%+)
    
    TIMESTAMP PRESERVATION:
    - created_at: Set to the time when drop was FIRST detected (from history scrapedat)
    - event_time: Updated on each recalculation to show latest refresh time
    """
    global dropping_calc_progress
    alarms = []
    supabase = get_supabase_client()
    if not supabase or not supabase.is_available:
        print("[Dropping] Supabase not available")
        return alarms
    
    # Load existing alarms to preserve created_at timestamps
    existing_alarms = load_dropping_alarms_from_file()
    existing_map = {}
    for ea in existing_alarms:
        # Key: match_id + market + selection
        key = f"{ea.get('match_id', '')}|{ea.get('market', '')}|{ea.get('selection', '')}"
        existing_map[key] = ea
    print(f"[Dropping] Loaded {len(existing_map)} existing alarms for timestamp preservation")
    
    min_drop_l1 = config.get('min_drop_l1', 7)
    max_drop_l1 = config.get('max_drop_l1', 10)
    min_drop_l2 = config.get('min_drop_l2', 10)
    max_drop_l2 = config.get('max_drop_l2', 15)
    min_drop_l3 = config.get('min_drop_l3', 15)
    l2_enabled = config.get('l2_enabled', True)
    l3_enabled = config.get('l3_enabled', True)
    
    max_odds_1x2 = config.get('max_odds_1x2', 5.0)
    max_odds_ou25 = config.get('max_odds_ou25', 3.0)
    max_odds_btts = config.get('max_odds_btts', 3.0)
    max_odds_map = {
        'dropping_1x2': max_odds_1x2,
        'dropping_ou25': max_odds_ou25,
        'dropping_btts': max_odds_btts
    }
    
    print(f"[Dropping] Config: L1={min_drop_l1}-{max_drop_l1}%, L2={min_drop_l2}-{max_drop_l2}%, L3={min_drop_l3}%+")
    print(f"[Dropping] Max Odds: 1X2={max_odds_1x2}, OU={max_odds_ou25}, BTTS={max_odds_btts}")
    
    markets = ['dropping_1x2', 'dropping_ou25', 'dropping_btts']
    market_names = {'dropping_1x2': '1X2', 'dropping_ou25': 'O/U 2.5', 'dropping_btts': 'BTTS'}
    moneyway_markets = {'dropping_1x2': 'moneyway_1x2', 'dropping_ou25': 'moneyway_ou25', 'dropping_btts': 'moneyway_btts'}
    selection_map = {
        'dropping_1x2': {'odds1': '1', 'oddsx': 'X', 'odds2': '2'},
        'dropping_ou25': {'under': 'Under', 'over': 'Over'},
        'dropping_btts': {'oddsyes': 'Yes', 'oddsno': 'No'}
    }
    
    created_at = now_turkey().strftime('%d.%m.%Y %H:%M')
    
    for idx, market in enumerate(markets):
        try:
            dropping_calc_progress = f"{market_names.get(market, market)} isleniyor... ({idx+1}/3)"
            
            # Get corresponding Moneyway market data to check if match exists there + get match dates
            moneyway_market = moneyway_markets.get(market)
            moneyway_matches = set()
            moneyway_dates = {}
            if moneyway_market:
                moneyway_data = supabase.get_all_matches_with_latest(moneyway_market)
                if moneyway_data:
                    for m in moneyway_data:
                        home = (m.get('home') or m.get('home_team') or m.get('Home') or '').lower().strip()
                        away = (m.get('away') or m.get('away_team') or m.get('Away') or '').lower().strip()
                        match_date_raw = m.get('date') or ''
                        if home and away:
                            key = f"{home}|{away}"
                            moneyway_matches.add(key)
                            moneyway_dates[key] = match_date_raw
                    print(f"[Dropping] Loaded {len(moneyway_matches)} matches from {moneyway_market} for cross-check")
            
            trend_data = supabase.get_6h_odds_history(market)
            if not trend_data:
                print(f"[Dropping] No trend data for {market}")
                continue
            
            print(f"[Dropping] Processing {len(trend_data)} matches for {market}")
            sel_map = selection_map.get(market, {})
            skipped_count = 0
            
            for match_key, match_data in trend_data.items():
                home = match_data.get('home', '')
                away = match_data.get('away', '')
                league = match_data.get('league', '')
                values = match_data.get('values', {})
                
                # Check if match exists in corresponding Moneyway market
                home_lower = home.lower().strip()
                away_lower = away.lower().strip()
                match_check_key = f"{home_lower}|{away_lower}"
                
                # Get match_date from moneyway data
                match_date = moneyway_dates.get(match_check_key, '')
                
                if moneyway_matches and match_check_key not in moneyway_matches:
                    # Try partial match for team name variations
                    found = False
                    found_key = None
                    for mw_key in moneyway_matches:
                        mw_home, mw_away = mw_key.split('|')
                        if (home_lower in mw_home or mw_home in home_lower) and \
                           (away_lower in mw_away or mw_away in away_lower):
                            found = True
                            found_key = mw_key
                            break
                    if not found:
                        skipped_count += 1
                        continue
                    # Get date from partial match
                    if found_key:
                        match_date = moneyway_dates.get(found_key, '')
                
                if not home or not away:
                    continue
                
                for odds_key, sel_data in values.items():
                    selection = sel_map.get(odds_key, odds_key)
                    
                    opening_odds = sel_data.get('old')
                    current_odds = sel_data.get('new')
                    pct_change = sel_data.get('pct_change', 0)
                    trend = sel_data.get('trend', 'stable')
                    
                    if opening_odds is None or current_odds is None:
                        continue
                    
                    if opening_odds <= 0 or current_odds <= 0:
                        continue
                    
                    if trend != 'down':
                        continue
                    
                    max_odds_limit = max_odds_map.get(market, 5.0)
                    if opening_odds > max_odds_limit:
                        continue
                    
                    drop_pct = abs(pct_change)
                    
                    level = None
                    if drop_pct >= min_drop_l3 and l3_enabled:
                        level = 'L3'
                    elif min_drop_l2 <= drop_pct < max_drop_l2 and l2_enabled:
                        level = 'L2'
                    elif min_drop_l1 <= drop_pct < max_drop_l1:
                        level = 'L1'
                    
                    if not level:
                        continue
                    
                    if not match_date or match_date == '2025' or len(match_date) < 5:
                        continue
                    
                    match_id = generate_match_id(home, away, league, match_date)
                    market_name = market_names.get(market, market)
                    
                    # Check if alarm already exists to preserve created_at
                    alarm_key = f"{match_id}|{market_name}|{selection}"
                    existing_alarm = existing_map.get(alarm_key)
                    
                    # Find when the drop was first detected by scanning history
                    full_history = match_data.get('full_history', [])
                    trigger_scrapedat = find_drop_trigger_time(full_history, odds_key, min_drop_l1)
                    
                    # Convert ISO format to Turkey time format (DD.MM.YYYY HH:MM)
                    actual_event_time = created_at  # fallback
                    if trigger_scrapedat:
                        try:
                            from datetime import datetime
                            import pytz
                            # Parse ISO format: 2025-12-04T17:13:01
                            if 'T' in trigger_scrapedat:
                                dt = datetime.fromisoformat(trigger_scrapedat.replace('Z', '+00:00'))
                                turkey_tz = pytz.timezone('Europe/Istanbul')
                                if dt.tzinfo is None:
                                    dt = pytz.UTC.localize(dt)
                                dt_turkey = dt.astimezone(turkey_tz)
                                actual_event_time = dt_turkey.strftime('%d.%m.%Y %H:%M')
                        except Exception as e:
                            print(f"[Dropping] Date parse error: {e}")
                    
                    # Use existing created_at if alarm exists, otherwise use actual event time
                    alarm_created_at = existing_alarm.get('created_at', actual_event_time) if existing_alarm else actual_event_time
                    
                    alarm = {
                        'home': home,
                        'away': away,
                        'home_team': home,
                        'away_team': away,
                        'match_id': match_id,
                        'league': league,
                        'market': market_name,
                        'selection': selection,
                        'level': level,
                        'opening_odds': round(opening_odds, 2),
                        'current_odds': round(current_odds, 2),
                        'drop_pct': round(drop_pct, 2),
                        'volume': 0,
                        'match_date': match_date,
                        'fixture_date': match_date,
                        'event_time': created_at,
                        'created_at': alarm_created_at
                    }
                    alarms.append(alarm)
                    print(f"[Dropping] {level}: {home} vs {away} [{selection}] {opening_odds:.2f}->{current_odds:.2f} ({drop_pct:.1f}%) date={match_date}")
            
            if skipped_count > 0:
                print(f"[Dropping] Skipped {skipped_count} matches not found in {moneyway_market}")
        
        except Exception as e:
            print(f"[Dropping] Error processing {market}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Tetiklenme zamanına göre sırala (en yeni en üstte)
    alarms.sort(key=lambda x: parse_created_at_for_sort(x.get('created_at', '')), reverse=True)
    
    print(f"[Dropping] Total alarms found: {len(alarms)}")
    return alarms


# ============================================================================
# VOLUME SHOCK (HACİM ŞOKU) ALARM SYSTEM
# ============================================================================

VOLUME_SHOCK_CONFIG_FILE = 'volume_shock_config.json'
VOLUME_SHOCK_ALARMS_FILE = 'volume_shock_alarms.json'

volume_shock_calculating = False
volume_shock_calc_progress = ""
volume_shock_alarms = []

def load_volume_shock_config():
    """Load Volume Shock config from JSON file"""
    try:
        if os.path.exists(VOLUME_SHOCK_CONFIG_FILE):
            with open(VOLUME_SHOCK_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                print(f"[VolumeShock] Config loaded: min_saat={config.get('hacim_soku_min_saat', 5)}, min_esik={config.get('hacim_soku_min_esik', 4)}")
                return config
    except Exception as e:
        print(f"[VolumeShock] Config load error: {e}")
    return {'hacim_soku_min_saat': 5, 'hacim_soku_min_esik': 4, 'enabled': True}

def save_volume_shock_config(config):
    """Save Volume Shock config to JSON file"""
    try:
        with open(VOLUME_SHOCK_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"[VolumeShock] Config saved: min_saat={config.get('hacim_soku_min_saat')}, min_esik={config.get('hacim_soku_min_esik')}")
        return True
    except Exception as e:
        print(f"[VolumeShock] Config save error: {e}")
        return False

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
    """Save Volume Shock alarms to JSON file"""
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
    """Get Volume Shock config"""
    return jsonify(volume_shock_config)

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
    """Get all Volume Shock alarms"""
    return jsonify(volume_shock_alarms)

@app.route('/api/volumeshock/delete', methods=['POST'])
def delete_volume_shock_alarms():
    """Delete all Volume Shock alarms"""
    global volume_shock_alarms
    volume_shock_alarms = []
    save_volume_shock_alarms_to_file(volume_shock_alarms)
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
    
    min_saat = config.get('hacim_soku_min_saat', 5)
    min_esik = config.get('hacim_soku_min_esik', 4)
    enabled = config.get('enabled', True)
    
    # Minimum volume eşikleri
    min_volume_1x2 = config.get('min_volume_1x2', 1000)
    min_volume_ou25 = config.get('min_volume_ou25', 500)
    min_volume_btts = config.get('min_volume_btts', 300)
    min_son_snapshot_para = config.get('min_son_snapshot_para', 300)
    
    if not enabled:
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
                min_volume = min_volume_1x2
            elif 'ou25' in market:
                selections = ['Over', 'Under']
                amount_keys = ['amtover', 'amtunder']
                min_volume = min_volume_ou25
            else:
                selections = ['Yes', 'No']
                amount_keys = ['amtyes', 'amtno']
                min_volume = min_volume_btts
            
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
                        snapshot_time_str = history[i].get('scrapedat', '')
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
                            
                            # Son 5 snapshot'ın ortalamasını al
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


# ==================== HALK TUZAĞI API ENDPOINTS ====================

@app.route('/api/publicmove/status', methods=['GET'])
def get_publicmove_status():
    """Get Public Move calculation status"""
    return jsonify({
        'calculating': publicmove_calculating,
        'progress': publicmove_calc_progress,
        'alarm_count': len(publicmove_alarms)
    })


@app.route('/api/publicmove/config', methods=['GET'])
def get_publicmove_config():
    """Get Public Move config"""
    return jsonify(publicmove_config)


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
    """Get all Public Move alarms"""
    return jsonify(publicmove_alarms)


@app.route('/api/publicmove/alarms', methods=['DELETE'])
def delete_publicmove_alarms():
    """Delete all Public Move alarms"""
    global publicmove_alarms
    publicmove_alarms = []
    save_publicmove_alarms_to_file(publicmove_alarms)
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
    supabase = get_supabase_client()
    if not supabase or not supabase.is_available:
        print("[PublicMove] Supabase not available")
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
    
    min_amount_change = config.get('min_amount_change', 500)
    volume_multiplier = config.get('volume_multiplier', 1)
    max_volume_cap = config.get('max_volume_cap', 40)
    max_odds_cap = config.get('max_odds_cap', 35)
    max_share_cap = config.get('max_share_cap', 25)
    min_share_threshold = config.get('min_share', 5)
    min_sharp_score = config.get('min_sharp_score', 10)
    
    odds_ranges = [
        (config.get('odds_range_1_min', 1.01), config.get('odds_range_1_max', 1.50), config.get('odds_range_1_mult', 10), config.get('odds_range_1_min_drop', 1)),
        (config.get('odds_range_2_min', 1.50), config.get('odds_range_2_max', 2.10), config.get('odds_range_2_mult', 8), config.get('odds_range_2_min_drop', 2)),
        (config.get('odds_range_3_min', 2.10), config.get('odds_range_3_max', 3.50), config.get('odds_range_3_mult', 5), config.get('odds_range_3_min_drop', 3)),
        (config.get('odds_range_4_min', 3.50), config.get('odds_range_4_max', 10.00), config.get('odds_range_4_mult', 3), config.get('odds_range_4_min_drop', 5)),
    ]
    default_odds_multiplier = config.get('odds_multiplier', 1)
    default_min_drop = config.get('min_drop', 1)
    
    share_ranges = [
        (config.get('share_range_1_min', 0), config.get('share_range_1_max', 50), config.get('share_range_1_mult', 1)),
        (config.get('share_range_2_min', 50), config.get('share_range_2_max', 75), config.get('share_range_2_mult', 1.5)),
        (config.get('share_range_3_min', 75), config.get('share_range_3_max', 90), config.get('share_range_3_mult', 2)),
        (config.get('share_range_4_min', 90), config.get('share_range_4_max', 100), config.get('share_range_4_mult', 3)),
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
                'triggered': sharp_score >= min_sharp_score,
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
                                
                                # 2 saatten az kaldıysa Sharp sayılmaz
                                if 0 < hours_to_match < 2:
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
    
    min_amount_change = config.get('min_amount_change', 500)
    volume_multiplier = config.get('volume_multiplier', 1)
    max_volume_cap = config.get('max_volume_cap', 40)
    max_odds_cap = config.get('max_odds_cap', 35)
    max_share_cap = config.get('max_share_cap', 25)
    min_share_threshold = config.get('min_share', 5)
    min_sharp_score = config.get('min_sharp_score', 10)
    
    odds_ranges = [
        (config.get('odds_range_1_min', 1.01), config.get('odds_range_1_max', 1.50), config.get('odds_range_1_mult', 10), config.get('odds_range_1_min_drop', 1)),
        (config.get('odds_range_2_min', 1.50), config.get('odds_range_2_max', 2.10), config.get('odds_range_2_mult', 8), config.get('odds_range_2_min_drop', 2)),
        (config.get('odds_range_3_min', 2.10), config.get('odds_range_3_max', 3.50), config.get('odds_range_3_mult', 5), config.get('odds_range_3_min_drop', 3)),
        (config.get('odds_range_4_min', 3.50), config.get('odds_range_4_max', 10.00), config.get('odds_range_4_mult', 3), config.get('odds_range_4_min_drop', 5)),
    ]
    default_odds_multiplier = config.get('odds_multiplier', 1)
    default_min_drop = 0
    
    share_ranges = [
        (config.get('share_range_1_min', 0), config.get('share_range_1_max', 50), config.get('share_range_1_mult', 1)),
        (config.get('share_range_2_min', 50), config.get('share_range_2_max', 75), config.get('share_range_2_mult', 1.5)),
        (config.get('share_range_3_min', 75), config.get('share_range_3_max', 90), config.get('share_range_3_mult', 2)),
        (config.get('share_range_4_min', 90), config.get('share_range_4_max', 100), config.get('share_range_4_mult', 3)),
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
            sharp_score >= min_sharp_score
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
    
    event_time = best_candidate['curr_snap'].get('scrapedat', '')
    
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
    """Load Volume Leader config from JSON file"""
    default_config = {
        'min_volume_1x2': 5000,
        'min_volume_ou25': 2000,
        'min_volume_btts': 1000,
        'leader_threshold': 50,  # Minimum % to be considered leader
        'enabled': True
    }
    try:
        if os.path.exists(VOLUME_LEADER_CONFIG_FILE):
            with open(VOLUME_LEADER_CONFIG_FILE, 'r') as f:
                saved_config = json.load(f)
                default_config.update(saved_config)
                print(f"[VolumeLeader] Config loaded: min_1x2={default_config.get('min_volume_1x2')}, threshold={default_config.get('leader_threshold')}%")
    except Exception as e:
        print(f"[VolumeLeader] Config load error: {e}")
    return default_config

def save_volume_leader_config(config):
    """Save Volume Leader config to JSON file"""
    try:
        with open(VOLUME_LEADER_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"[VolumeLeader] Config saved: min_1x2={config.get('min_volume_1x2')}, threshold={config.get('leader_threshold')}%")
        return True
    except Exception as e:
        print(f"[VolumeLeader] Config save error: {e}")
        return False

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
    """Save Volume Leader alarms to JSON file"""
    try:
        with open(VOLUME_LEADER_ALARMS_FILE, 'w') as f:
            json.dump(alarms, f, indent=2, ensure_ascii=False)
        print(f"[VolumeLeader] Saved {len(alarms)} alarms to {VOLUME_LEADER_ALARMS_FILE}")
        return True
    except Exception as e:
        print(f"[VolumeLeader] Alarms save error: {e}")
        return False

volume_leader_config = load_volume_leader_config()
volume_leader_alarms = load_volume_leader_alarms_from_file()


@app.route('/api/volumeleader/config', methods=['GET'])
def get_volume_leader_config():
    """Get Volume Leader config"""
    return jsonify(volume_leader_config)


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
    """Get Volume Leader alarms"""
    return jsonify(volume_leader_alarms)


@app.route('/api/volumeleader/alarms', methods=['DELETE'])
def delete_volume_leader_alarms():
    """Delete all Volume Leader alarms"""
    global volume_leader_alarms
    volume_leader_alarms = []
    save_volume_leader_alarms_to_file(volume_leader_alarms)
    return jsonify({'success': True})


@app.route('/api/volumeleader/status', methods=['GET'])
def get_volume_leader_status():
    """Get Volume Leader calculation status"""
    return jsonify({
        'calculating': volume_leader_calculating,
        'progress': volume_leader_calc_progress
    })


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
    
    leader_threshold = config.get('leader_threshold', 50)
    print(f"[VolumeLeader] Config: threshold={leader_threshold}%")
    
    markets = ['moneyway_1x2', 'moneyway_ou25', 'moneyway_btts']
    market_names = {'moneyway_1x2': '1X2', 'moneyway_ou25': 'O/U 2.5', 'moneyway_btts': 'BTTS'}
    
    # Prematch rule: D-2+ matches excluded
    today = now_turkey().date()
    yesterday = today - timedelta(days=1)
    
    for idx, market in enumerate(markets):
        try:
            if '1x2' in market:
                min_volume = config.get('min_volume_1x2', 5000)
                selections = ['1', 'X', '2']
                share_keys = ['pct1', 'pctx', 'pct2']
                amount_keys = ['amt1', 'amtx', 'amt2']
            elif 'ou25' in market:
                min_volume = config.get('min_volume_ou25', 2000)
                selections = ['Over', 'Under']
                share_keys = ['pctover', 'pctunder']
                amount_keys = ['amtover', 'amtunder']
            else:
                min_volume = config.get('min_volume_btts', 1000)
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
                    history_url = f"{supabase.url}/rest/v1/{history_table}?home=eq.{home_enc}&away=eq.{away_enc}&order=scrapedat.desc&limit=50"
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


@app.route('/api/alarm-settings')
def get_alarm_settings():
    """Get all alarm settings from database"""
    try:
        supabase = get_supabase_client()
        if supabase and supabase.is_available:
            settings = supabase.get_alarm_settings()
            return jsonify({'status': 'ok', 'settings': settings})
        return jsonify({'status': 'error', 'message': 'Supabase not available'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/alarm-settings/<alarm_type>', methods=['GET', 'PUT'])
def manage_alarm_setting(alarm_type):
    """Get or update a specific alarm setting"""
    try:
        supabase = get_supabase_client()
        if not supabase or not supabase.is_available:
            return jsonify({'status': 'error', 'message': 'Supabase not available'})
        
        if request.method == 'GET':
            setting = supabase.get_alarm_setting(alarm_type)
            if setting:
                return jsonify({'status': 'ok', 'setting': setting})
            return jsonify({'status': 'error', 'message': 'Setting not found'})
        
        elif request.method == 'PUT':
            data = request.get_json() or {}
            enabled = data.get('enabled', True)
            config = data.get('config', {})
            
            result = supabase.update_alarm_setting(alarm_type, enabled, config)
            if result:
                print(f"[Admin] Updated alarm setting: {alarm_type} -> enabled={enabled}, config={config}")
                return jsonify({'status': 'ok', 'message': f'{alarm_type} ayarları güncellendi'})
            return jsonify({'status': 'error', 'message': 'Update failed'})
    
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
                    'interval_minutes': state.get('interval_minutes', 10),
                    'last_scrape': state.get('last_scrape'),
                    'next_scrape': state.get('next_scrape'),
                    'last_rows': state.get('last_rows', 0),
                    'last_alarm_count': state.get('last_alarm_count', 0),
                    'status_text': state.get('status', 'Bekliyor...')
                })
            except:
                pass
        
        # Server modunda scrape_status kullan
        is_running = scrape_status.get('running', False)
        is_auto = scrape_status.get('auto_running', False)
        is_disabled = is_scraper_disabled()
        
        if is_disabled:
            status_text = 'Devre Dışı (Standalone)'
        elif is_running:
            status_text = 'Veri çekiliyor...'
        elif is_auto:
            status_text = 'Çalışıyor'
        else:
            status_text = 'Durduruldu'
        
        return jsonify({
            'status': 'ok',
            'running': is_auto or is_running,
            'is_scraping': is_running,
            'is_disabled': is_disabled,
            'interval_minutes': scrape_status.get('interval_minutes', 10),
            'last_scrape': scrape_status.get('last_scrape_time'),
            'next_scrape': scrape_status.get('next_scrape_time'),
            'last_rows': 0,
            'last_alarm_count': 0,
            'status_text': status_text
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e), 'running': False})


@app.route('/scraper/control', methods=['POST'])
def scraper_control():
    """Scraper başlat/durdur kontrolü - Desktop ve Server modları"""
    global scrape_status, server_scheduler_thread, server_scheduler_stop
    
    try:
        data = request.get_json() or {}
        action = data.get('action', '')
        
        # EXE (Desktop) modunda scraper_admin fonksiyonlarını kullan
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
        
        # Scraper devre dışıysa (Standalone mode)
        if is_scraper_disabled():
            return jsonify({'status': 'error', 'message': 'Scraper devre dışı (Standalone mode)'})
        
        # Server modunda
        if action == 'start':
            if scrape_status.get('auto_running'):
                return jsonify({'status': 'ok', 'message': 'Zaten çalışıyor'})
            
            # Server scheduler'ı başlat
            server_scheduler_stop.clear()
            scrape_status['auto_running'] = True
            scrape_status['interval_minutes'] = get_scrape_interval_seconds() // 60
            
            def scheduler_loop():
                global scrape_status
                interval_seconds = get_scrape_interval_seconds()
                print(f"[Server Scheduler] Restarted - interval: {interval_seconds // 60} minutes")
                
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
                
                scrape_status['auto_running'] = False
                scrape_status['next_scrape_time'] = None
                print("[Server Scheduler] Stopped")
            
            server_scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
            server_scheduler_thread.start()
            
            return jsonify({'status': 'ok', 'message': 'Scraper başlatıldı', 'running': True})
        
        elif action == 'stop':
            if not scrape_status.get('auto_running'):
                return jsonify({'status': 'ok', 'message': 'Zaten durdurulmuş'})
            
            server_scheduler_stop.set()
            scrape_status['auto_running'] = False
            scrape_status['next_scrape_time'] = None
            
            return jsonify({'status': 'ok', 'message': 'Scraper durduruldu', 'running': False})
        
        else:
            return jsonify({'status': 'error', 'message': 'Geçersiz action'})
    
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
        
        # Server modunda global değişkeni güncelle
        global scrape_status
        scrape_status['interval_minutes'] = new_interval
        
        return jsonify({'status': 'ok', 'message': f'Interval {new_interval} dakika olarak ayarlandı', 'interval': new_interval})
    
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
    from flask import Response
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
            <span class="badge">Interval: <span id="intervalValue">10</span> dk</span>
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
                    document.getElementById('intervalValue').textContent = data.interval_minutes || 10;
                    document.getElementById('lastRows').textContent = data.last_rows || '-';
                });
        }
        updateStatus();
        setInterval(updateStatus, 5000);
        
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
            start_alarm_scheduler()
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
