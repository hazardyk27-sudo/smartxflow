#!/usr/bin/env python3
"""
SmartXFlow Alarm Engine v2.1 - 24/7 Signal-Based Alarm Calculator
Scraper'dan gelen sinyalleri dinler ve alarm hesaplamalarini tetikler.

Signal flow:
Scraper -> scraper_signal (Supabase) -> Alarm Engine -> alarm tables

v2.1 incremental rollout:
- BigMoney reads only the current/previous snapshots it needs.
- MIM reads only the current/previous snapshots it needs.
- Other alarm types keep the existing calculator path for now.
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

HEADERS_READ = {
    'apikey': SUPABASE_ANON_KEY,
    'Authorization': f'Bearer {SUPABASE_ANON_KEY}',
    'Content-Type': 'application/json'
}

HEADERS_WRITE = {
    'apikey': SUPABASE_SERVICE_KEY,
    'Authorization': f'Bearer {SUPABASE_SERVICE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=minimal'
}

_calculator = None


def get_calculator():
    global _calculator
    if _calculator is None:
        key = SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY
        _calculator = AlarmCalculator(
            supabase_url=SUPABASE_URL,
            supabase_key=key,
            logger_callback=lambda msg: print(msg)
        )
    return _calculator


def check_unprocessed_signals():
    """Fetch the NEWEST unprocessed signal, not the oldest.

    run_all_calculations() still recalculates the non-incremental alarm types
    from current DB state. BigMoney and MIM are patched to use the active
    signal's small recent snapshot window.
    """
    try:
        url = f"{SUPABASE_URL}/rest/v1/scraper_signal?processed=eq.false&order=created_at.desc&limit=1"
        r = requests.get(url, headers=HEADERS_READ, timeout=15)
        if r.status_code == 200:
            signals = r.json()
            return signals[0] if signals else None
        print(f"[Signal Check] HTTP {r.status_code}: {r.text[:200]}")
        return None
    except Exception as e:
        print(f"[Signal Check] Hata: {e}")
        return None


def skip_stale_signals(before_id):
    """Mark older pending signals processed without replaying stale full scans."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        url = f"{SUPABASE_URL}/rest/v1/scraper_signal?processed=eq.false&id=lt.{before_id}"
        data = {"processed": True, "processed_at": now}
        headers = {**HEADERS_WRITE, 'Prefer': 'return=representation'}
        r = requests.patch(url, json=data, headers=headers, timeout=20)
        if r.status_code in (200, 204):
            try:
                rows = r.json()
                skipped = len(rows) if isinstance(rows, list) else 0
            except Exception:
                skipped = 0
            if skipped:
                print(
                    f"[Signal] Backlog: {skipped} eski sinyal (id<{before_id}) "
                    "hesaplanmadan processed olarak isaretlendi"
                )
            return skipped
        print(f"[Signal] Backlog atlama hata: HTTP {r.status_code}: {r.text[:200]}")
        return 0
    except Exception as e:
        print(f"[Signal] Backlog atlama exception: {e}")
        return 0


def mark_signal_processed(signal_id):
    try:
        url = f"{SUPABASE_URL}/rest/v1/scraper_signal?id=eq.{signal_id}"
        data = {
            "processed": True,
            "processed_at": datetime.now(timezone.utc).isoformat()
        }
        r = requests.patch(url, json=data, headers=HEADERS_WRITE, timeout=10)
        if r.status_code in [200, 204]:
            print(f"[Signal] #{signal_id} processed olarak isaretlendi")
            return True
        print(f"[Signal] Mark processed hata: HTTP {r.status_code}")
        return False
    except Exception as e:
        print(f"[Signal] Mark processed exception: {e}")
        return False


def update_engine_heartbeat(status, alarm_count=0, error_msg=None):
    try:
        now = datetime.now(timezone.utc).isoformat()
        data = {
            "source": "alarm_engine",
            "last_heartbeat": now,
            "status": status,
            "match_count": alarm_count,
            "error_message": error_msg,
            "updated_at": now
        }
        url = f"{SUPABASE_URL}/rest/v1/scraper_heartbeat?on_conflict=source"
        headers = {
            **HEADERS_WRITE,
            'Prefer': 'return=representation,resolution=merge-duplicates'
        }
        r = requests.post(url, json=data, headers=headers, timeout=10)
        return r.status_code in [200, 201]
    except Exception:
        return False


def _signal_queue_wait_seconds(signal):
    try:
        created = datetime.fromisoformat(str(signal.get('created_at', '')).replace('Z', '+00:00'))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - created.astimezone(timezone.utc)).total_seconds())
    except Exception:
        return None


def process_signal(signal):
    signal_id = signal.get('id')
    match_count = signal.get('match_count', 0)
    source = signal.get('source', 'unknown')
    queue_wait = _signal_queue_wait_seconds(signal)

    print("\n" + "=" * 60)
    print(f"SINYAL ALGILANDI - #{signal_id}")
    print(f"Kaynak: {source} | Mac sayisi: {match_count}")
    print(f"Zaman: {signal.get('created_at', 'N/A')}")
    if queue_wait is not None:
        print(f"[Timing] queue_wait={queue_wait:.3f}s")
    print("=" * 60)

    update_engine_heartbeat("calculating")
    calculation_started = time.monotonic()
    calc = None

    try:
        calc = get_calculator()
        calc._active_signal = signal
        total_alarms = calc.run_all_calculations()
        calculation_seconds = time.monotonic() - calculation_started

        mark_signal_processed(signal_id)

        print(
            f"\n[Engine] Hesaplama tamamlandi - {total_alarms} alarm uretildi | "
            f"calculation={calculation_seconds:.3f}s"
        )
        update_engine_heartbeat("idle", alarm_count=total_alarms)
        return True

    except Exception as e:
        calculation_seconds = time.monotonic() - calculation_started
        print(f"[Engine] Hesaplama hatasi ({calculation_seconds:.3f}s): {e}")
        import traceback
        traceback.print_exc()
        update_engine_heartbeat("error", error_msg=str(e)[:200])
        return False

    finally:
        if calc is not None:
            clear_recent_alarm_cache(calc)


def run_engine():
    print("=" * 60)
    print("SMARTXFLOW ALARM ENGINE v2.1")
    print("BigMoney + MIM: incremental recent-snapshot mode")
    print("Other alarms: existing calculation path")
    print(f"Poll interval: {POLL_INTERVAL}s")
    print(f"Supabase URL: {SUPABASE_URL[:30]}..." if SUPABASE_URL else "Supabase URL: NOT SET")
    print("=" * 60)

    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        print("[FATAL] SUPABASE_URL veya SUPABASE_ANON_KEY ayarlanmamis!")
        print("[Engine] 60s bekleyip tekrar kontrol edilecek...")
        while True:
            time.sleep(60)
            url = os.environ.get('SUPABASE_URL')
            key = os.environ.get('SUPABASE_ANON_KEY')
            if url and key:
                globals()['SUPABASE_URL'] = url
                globals()['SUPABASE_ANON_KEY'] = key
                globals()['HEADERS_READ'] = {
                    "apikey": key,
                    "Authorization": f"Bearer {key}"
                }
                svc = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')
                if svc:
                    globals()['SUPABASE_SERVICE_KEY'] = svc
                    globals()['HEADERS_WRITE'] = {
                        "apikey": svc,
                        "Authorization": f"Bearer {svc}",
                        "Content-Type": "application/json",
                        "Prefer": "return=minimal"
                    }
                print("[Engine] Supabase credentials bulundu, yeniden baslatiliyor")
                return run_engine()
            print("[Engine] Supabase credentials hala eksik, bekleniyor...")

    if not SUPABASE_SERVICE_KEY:
        print("[UYARI] SUPABASE_SERVICE_ROLE_KEY ayarlanmamis - yazma islemi basarisiz olabilir")

    get_calculator()
    print("[Engine] AlarmCalculator basariyla yuklendi")

    update_engine_heartbeat("started")
    print(f"\n[Engine] Baslatildi - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("[Engine] Sinyal bekleniyor...\n")

    last_idle_log = time.time()
    consecutive_errors = 0

    while True:
        try:
            signal = check_unprocessed_signals()

            if signal:
                consecutive_errors = 0
                skip_stale_signals(signal['id'])
                success = process_signal(signal)
                if not success:
                    time.sleep(ERROR_WAIT)
                continue

            now = time.time()
            if now - last_idle_log >= IDLE_LOG_INTERVAL:
                print(f"[Engine] Beklemede... {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}")
                update_engine_heartbeat("idle")
                last_idle_log = now

            time.sleep(POLL_INTERVAL)
            consecutive_errors = 0

        except KeyboardInterrupt:
            print("\n[Engine] Durduruldu (Ctrl+C)")
            update_engine_heartbeat("stopped")
            break

        except Exception as e:
            consecutive_errors += 1
            wait_time = min(ERROR_WAIT * consecutive_errors, 300)
            print(f"[Engine] Beklenmeyen hata ({consecutive_errors}): {e}")
            print(f"[Engine] {wait_time}s bekleniyor...")
            update_engine_heartbeat("error", error_msg=str(e)[:200])
            time.sleep(wait_time)


if __name__ == '__main__':
    run_engine()
