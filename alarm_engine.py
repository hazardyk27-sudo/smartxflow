#!/usr/bin/env python3
"""
SmartXFlow Alarm Engine v2.3 - 24/7 signal-based incremental calculator.

Signal flow:
Scraper -> scraper_signal (Supabase) -> Alarm Engine -> alarm tables

All six alarms are incremental:
- BigMoney: recent 3-snapshot window.
- MIM: recent 2-snapshot window + current market total.
- VolumeLeader: last 2 complete market states.
- VolumeShock: last 6 snapshots.
- Sharp: last 21 snapshots per changed selection.
- Dropping: immutable opening odds + persistence window + median/recovery guard.

The active-signal path no longer runs the legacy full matches/history prefetch.
"""

import os
import sys
import time
import requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scraper_standalone'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'desktop', 'scraper_standalone'))
from alarm_calculator import AlarmCalculator
from alarm_recent import install_recent_alarm_overrides, clear_recent_alarm_cache

install_recent_alarm_overrides(AlarmCalculator)

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY')
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
POLL_INTERVAL = 30
IDLE_LOG_INTERVAL = 300
ERROR_WAIT = 60
MAX_SIGNAL_AGE_SECONDS = 12 * 60

HEADERS_READ = {'apikey': SUPABASE_ANON_KEY, 'Authorization': f'Bearer {SUPABASE_ANON_KEY}', 'Content-Type': 'application/json'}
HEADERS_WRITE = {'apikey': SUPABASE_SERVICE_KEY, 'Authorization': f'Bearer {SUPABASE_SERVICE_KEY}', 'Content-Type': 'application/json', 'Prefer': 'return=minimal'}
_calculator = None
_HEARTBEAT_TABLE_AVAILABLE = None
_HEARTBEAT_MISSING_LOGGED = False


def _heartbeat_table_missing(response):
    text = getattr(response, 'text', '') or ''
    return response.status_code == 404 and ('scraper_heartbeat' in text or 'PGRST205' in text)


def _log_missing_heartbeat_once():
    global _HEARTBEAT_MISSING_LOGGED
    if not _HEARTBEAT_MISSING_LOGGED:
        print('[Heartbeat] scraper_heartbeat yok; engine liveness scraper_signal processed_at ile izlenecek')
        _HEARTBEAT_MISSING_LOGGED = True


def get_calculator():
    global _calculator
    if _calculator is None:
        key = SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY
        _calculator = AlarmCalculator(SUPABASE_URL, key, logger_callback=lambda msg: print(msg))
    return _calculator


def check_unprocessed_signals():
    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/scraper_signal"
            "?processed=eq.false&signal_type=eq.scrape_complete"
            "&order=created_at.desc&limit=1"
        )
        r = requests.get(url, headers=HEADERS_READ, timeout=15)
        if r.status_code == 200:
            signals = r.json()
            return signals[0] if signals else None
        print(f"[Signal Check] HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"[Signal Check] Hata: {e}")
    return None


def skip_stale_signals(before_id):
    try:
        now = datetime.now(timezone.utc).isoformat()
        url = (
            f"{SUPABASE_URL}/rest/v1/scraper_signal"
            f"?processed=eq.false&signal_type=eq.scrape_complete&id=lt.{before_id}"
        )
        headers = {**HEADERS_WRITE, 'Prefer': 'return=representation'}
        r = requests.patch(url, json={'processed': True, 'processed_at': now}, headers=headers, timeout=20)
        if r.status_code in (200, 204):
            try:
                rows = r.json()
                skipped = len(rows) if isinstance(rows, list) else 0
            except Exception:
                skipped = 0
            if skipped:
                print(f"[Signal] Backlog: {skipped} eski scrape_complete sinyali hesaplanmadan processed")
            return skipped
        print(f"[Signal] Backlog atlama hata: HTTP {r.status_code}")
    except Exception as e:
        print(f"[Signal] Backlog atlama exception: {e}")
    return 0


def mark_signal_processed(signal_id):
    try:
        url = f"{SUPABASE_URL}/rest/v1/scraper_signal?id=eq.{signal_id}"
        data = {'processed': True, 'processed_at': datetime.now(timezone.utc).isoformat()}
        r = requests.patch(url, json=data, headers=HEADERS_WRITE, timeout=10)
        if r.status_code in (200, 204):
            print(f"[Signal] #{signal_id} processed olarak isaretlendi")
            return True
        print(f"[Signal] Mark processed hata: HTTP {r.status_code}")
    except Exception as e:
        print(f"[Signal] Mark processed exception: {e}")
    return False


def update_engine_heartbeat(status, alarm_count=0, error_msg=None):
    global _HEARTBEAT_TABLE_AVAILABLE
    if _HEARTBEAT_TABLE_AVAILABLE is False:
        return False
    try:
        now = datetime.now(timezone.utc).isoformat()
        data = {
            'source': 'alarm_engine',
            'last_heartbeat': now,
            'status': status,
            'match_count': alarm_count,
            'error_message': error_msg,
            'updated_at': now,
        }
        url = f"{SUPABASE_URL}/rest/v1/scraper_heartbeat?on_conflict=source"
        headers = {**HEADERS_WRITE, 'Prefer': 'return=representation,resolution=merge-duplicates'}
        r = requests.post(url, json=data, headers=headers, timeout=10)
        if r.status_code in (200, 201):
            _HEARTBEAT_TABLE_AVAILABLE = True
            return True
        if _heartbeat_table_missing(r):
            _HEARTBEAT_TABLE_AVAILABLE = False
            _log_missing_heartbeat_once()
            return False
        print(f"[Heartbeat] HTTP {r.status_code}: {r.text[:160]}")
        return False
    except Exception as e:
        print(f"[Heartbeat] Hata: {e}")
        return False


def _signal_queue_wait_seconds(signal):
    try:
        created = datetime.fromisoformat(str(signal.get('created_at', '')).replace('Z', '+00:00'))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - created.astimezone(timezone.utc)).total_seconds())
    except Exception:
        return None


def _reject_stale_or_invalid_signal(signal, queue_wait):
    signal_id = signal.get('id')
    if signal_id is None:
        update_engine_heartbeat('error', error_msg='scrape_complete signal id missing')
        return False

    if queue_wait is None:
        reason = 'scrape_complete created_at invalid; calculation skipped'
    else:
        reason = (
            f'scrape_complete stale ({queue_wait:.1f}s > '
            f'{MAX_SIGNAL_AGE_SECONDS}s); calculation skipped'
        )

    print(f"[Signal] #{signal_id} {reason}")
    if not mark_signal_processed(signal_id):
        update_engine_heartbeat('error', error_msg=f'{reason}; mark processed failed')
        return False

    update_engine_heartbeat('stale_input', alarm_count=0, error_msg=reason)
    return True


def process_signal(signal):
    signal_id = signal.get('id')
    queue_wait = _signal_queue_wait_seconds(signal)
    print("\n" + "=" * 60)
    print(f"SINYAL ALGILANDI - #{signal_id}")
    print(f"Kaynak: {signal.get('source', 'unknown')} | Mac sayisi: {signal.get('match_count', 0)}")
    print(f"Zaman: {signal.get('created_at', 'N/A')}")
    if queue_wait is not None:
        print(f"[Timing] queue_wait={queue_wait:.3f}s")
    print("=" * 60)

    if queue_wait is None or queue_wait > MAX_SIGNAL_AGE_SECONDS:
        return _reject_stale_or_invalid_signal(signal, queue_wait)

    update_engine_heartbeat('calculating')
    started = time.monotonic()
    calc = None
    try:
        calc = get_calculator()
        calc._active_signal = signal
        total_alarms = calc.run_all_calculations()
        elapsed = time.monotonic() - started
        mark_signal_processed(signal_id)
        print(f"\n[Engine] Hesaplama tamamlandi - {total_alarms} alarm | calculation={elapsed:.3f}s")
        update_engine_heartbeat('idle', alarm_count=total_alarms)
        return True
    except Exception as e:
        elapsed = time.monotonic() - started
        print(f"[Engine] Hesaplama hatasi ({elapsed:.3f}s): {e}")
        import traceback
        traceback.print_exc()
        update_engine_heartbeat('error', error_msg=str(e)[:200])
        return False
    finally:
        if calc is not None:
            clear_recent_alarm_cache(calc)


def run_engine():
    print("=" * 60)
    print("SMARTXFLOW ALARM ENGINE v2.3")
    print("Incremental: BigMoney + MIM + VolumeLeader + VolumeShock + Sharp + Dropping")
    print("Legacy full history prefetch: OFF for active scraper signals")
    print(f"Poll interval: {POLL_INTERVAL}s | Max signal age: {MAX_SIGNAL_AGE_SECONDS}s")
    print(f"Supabase URL: {SUPABASE_URL[:30]}..." if SUPABASE_URL else "Supabase URL: NOT SET")
    print("=" * 60)
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        print("[FATAL] SUPABASE_URL veya SUPABASE_ANON_KEY ayarlanmamis!")
        while True:
            time.sleep(60)
            url = os.environ.get('SUPABASE_URL')
            key = os.environ.get('SUPABASE_ANON_KEY')
            if url and key:
                globals()['SUPABASE_URL'] = url
                globals()['SUPABASE_ANON_KEY'] = key
                globals()['HEADERS_READ'] = {'apikey': key, 'Authorization': f'Bearer {key}'}
                svc = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
                if svc:
                    globals()['SUPABASE_SERVICE_KEY'] = svc
                    globals()['HEADERS_WRITE'] = {'apikey': svc, 'Authorization': f'Bearer {svc}', 'Content-Type': 'application/json', 'Prefer': 'return=minimal'}
                return run_engine()
    get_calculator()
    update_engine_heartbeat('started')
    print(f"[Engine] Baslatildi - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    last_idle_log = time.time()
    consecutive_errors = 0
    while True:
        try:
            signal = check_unprocessed_signals()
            if signal:
                consecutive_errors = 0
                skip_stale_signals(signal['id'])
                if not process_signal(signal):
                    time.sleep(ERROR_WAIT)
                continue
            now = time.time()
            if now - last_idle_log >= IDLE_LOG_INTERVAL:
                update_engine_heartbeat('idle')
                last_idle_log = now
            time.sleep(POLL_INTERVAL)
            consecutive_errors = 0
        except KeyboardInterrupt:
            update_engine_heartbeat('stopped')
            break
        except Exception as e:
            consecutive_errors += 1
            wait_time = min(ERROR_WAIT * consecutive_errors, 300)
            update_engine_heartbeat('error', error_msg=str(e)[:200])
            time.sleep(wait_time)


if __name__ == '__main__':
    run_engine()
