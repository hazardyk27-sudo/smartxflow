#!/usr/bin/env python3
"""
SmartXFlow Alarm Engine - 24/7 Signal-Based Alarm Calculator
Scraper'dan gelen sinyalleri dinler ve alarm hesaplamalarını tetikler.
Signal flow: Scraper -> scraper_signal (Supabase) -> Alarm Engine -> alarm tables
"""

import os
import sys
import time
import requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from alarm_calculator_new import (
    run_all_calculations,
    clear_error_flags,
    get_error_status,
    SETTINGS_CACHE
)

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


def check_unprocessed_signals():
    try:
        url = f"{SUPABASE_URL}/rest/v1/scraper_signal?processed=eq.false&order=created_at.asc&limit=1"
        r = requests.get(url, headers=HEADERS_READ, timeout=15)
        if r.status_code == 200:
            signals = r.json()
            return signals[0] if signals else None
        else:
            print(f"[Signal Check] HTTP {r.status_code}: {r.text[:200]}")
            return None
    except Exception as e:
        print(f"[Signal Check] Hata: {e}")
        return None


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
        else:
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


def process_signal(signal):
    signal_id = signal.get('id')
    match_count = signal.get('match_count', 0)
    source = signal.get('source', 'unknown')

    print("\n" + "=" * 60)
    print(f"SINYAL ALGILANDI - #{signal_id}")
    print(f"Kaynak: {source} | Mac sayisi: {match_count}")
    print(f"Zaman: {signal.get('created_at', 'N/A')}")
    print("=" * 60)

    SETTINGS_CACHE.clear()
    clear_error_flags()

    update_engine_heartbeat("calculating")

    try:
        alarms = run_all_calculations(write_to_db=True)

        total_alarms = sum(len(v) for v in alarms.values()) if alarms else 0

        error_status = get_error_status()
        if error_status.get('ssl_error'):
            print(f"[Engine] SSL hatasi algilandi - sinyal tekrar denenmek uzere birakildi")
            update_engine_heartbeat("ssl_error", error_msg=error_status.get('ssl_error_message'))
            return False

        mark_signal_processed(signal_id)

        print(f"\n[Engine] Hesaplama tamamlandi - {total_alarms} alarm uretildi")
        update_engine_heartbeat("idle", alarm_count=total_alarms)
        return True

    except Exception as e:
        print(f"[Engine] Hesaplama hatasi: {e}")
        update_engine_heartbeat("error", error_msg=str(e)[:200])
        return False


def run_engine():
    print("=" * 60)
    print("SMARTXFLOW ALARM ENGINE v1.0")
    print("Signal-based alarm calculator")
    print(f"Poll interval: {POLL_INTERVAL}s")
    print(f"Supabase URL: {SUPABASE_URL[:30]}..." if SUPABASE_URL else "Supabase URL: NOT SET")
    print("=" * 60)

    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        print("[FATAL] SUPABASE_URL veya SUPABASE_ANON_KEY ayarlanmamis!")
        sys.exit(1)

    if not SUPABASE_SERVICE_KEY:
        print("[UYARI] SUPABASE_SERVICE_ROLE_KEY ayarlanmamis - yazma islemi basarisiz olabilir")

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
