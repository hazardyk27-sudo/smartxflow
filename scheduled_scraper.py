#!/usr/bin/env python3
"""
SmartXFlow Scheduled Scraper
Replit Scheduled Deployment için tek seferlik (one-shot) scraper
Her 10 dakikada bir otomatik olarak çalışır
MEVCUT ÇALIŞAN SCRAPER'I KULLANIR
"""
import os
import sys
import time
import requests
from datetime import datetime, timezone
from typing import Optional
import traceback

# standalone_scraper modülünü import et
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scraper_standalone'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'desktop', 'scraper_standalone'))
import standalone_scraper as ss_module
from standalone_scraper import SupabaseWriter, run_scrape

arbworld_cookie = os.environ.get('ARBWORLD_COOKIE', '')
if arbworld_cookie:
    ss_module.HEADERS['Cookie'] = arbworld_cookie
    print(f"[Cookie] ARBWORLD_COOKIE enjekte edildi ({len(arbworld_cookie)} karakter)")
else:
    print("[Cookie] ARBWORLD_COOKIE bulunamadi - cookie'siz devam ediliyor")

MAX_RETRIES = 3
RETRY_DELAYS = [5, 10, 20]
SCRAPER_SOURCE = "replit"

def send_telegram(message: str, is_error: bool = False) -> bool:
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not bot_token or not chat_id:
        print("[Telegram] Token veya Chat ID eksik")
        return False
    
    try:
        emoji = "🔴" if is_error else "🟢"
        url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
        data = {
            'chat_id': chat_id,
            'text': f"{emoji} {message}",
            'parse_mode': 'HTML'
        }
        r = requests.post(url, data=data, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"[Telegram] Hata: {e}")
        return False

def send_alarm_engine_signal(supabase_url: str, supabase_key: str, match_count: int, snapshot_count: int = 0) -> bool:
    """Alarm Engine'e sinyal gönder - scrape tamamlandığında çağrılır"""
    try:
        data = {
            "source": SCRAPER_SOURCE,
            "signal_type": "scrape_complete",
            "match_count": match_count,
            "snapshot_count": snapshot_count,
            "processed": False
        }
        
        url = f"{supabase_url}/rest/v1/scraper_signal"
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        
        r = requests.post(url, json=data, headers=headers, timeout=10)
        print(f"[Signal] HTTP {r.status_code}: {r.text[:200]}")
        success = r.status_code in [200, 201] and len(r.text) > 10
        if success:
            print(f"[Signal] Alarm Engine'e sinyal gönderildi ✓ ({match_count} maç)")
        else:
            print(f"[Signal] Sinyal gönderilemedi - HTTP {r.status_code}")
        return success
    except Exception as e:
        print(f"[Signal] Hata: {e}")
        return False

def update_heartbeat(supabase_url: str, supabase_key: str, status: str, match_count: int = 0, error_msg: Optional[str] = None) -> bool:
    try:
        now = datetime.now(timezone.utc).isoformat()
        data = {
            "source": SCRAPER_SOURCE,
            "last_heartbeat": now,
            "status": status,
            "match_count": match_count,
            "error_message": error_msg,
            "updated_at": now
        }
        
        # Supabase REST API - UPSERT
        url = f"{supabase_url}/rest/v1/scraper_heartbeat?on_conflict=source"
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation,resolution=merge-duplicates"
        }
        
        r = requests.post(url, json=data, headers=headers, timeout=10)
        success = r.status_code in [200, 201]
        if success:
            print(f"[Heartbeat] {status} - {match_count} matches ✓")
        else:
            print(f"[Heartbeat] {status} - HTTP {r.status_code}: {r.text[:100]}")
        return success
    except Exception as e:
        print(f"[Heartbeat] Hata: {e}")
        return False

def check_master_status(supabase_url: str, supabase_key: str) -> tuple:
    try:
        url = f"{supabase_url}/rest/v1/scraper_heartbeat?select=*"
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}"
        }
        
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return True, "api_error_fallback"
        
        rows = r.json()
        if not rows:
            return True, "no_master"
        
        now = datetime.now(timezone.utc)
        
        for row in rows:
            if row.get("source") == SCRAPER_SOURCE:
                continue
            
            last_beat = row.get("last_heartbeat")
            if last_beat:
                from dateutil import parser
                beat_time = parser.parse(last_beat)
                if beat_time.tzinfo is None:
                    beat_time = beat_time.replace(tzinfo=timezone.utc)
                diff_minutes = (now - beat_time).total_seconds() / 60
                
                if diff_minutes < 5 and row.get("status") == "active":
                    return False, f"{row.get('source')} is master ({diff_minutes:.1f} min ago)"
        
        return True, "i_am_master"
    except Exception as e:
        print(f"[Master Check] Hata: {e}, devam ediyorum")
        return True, "error_fallback"

def log_callback(message: str):
    print(f"[Scraper] {message}")

def run_with_retry(writer: SupabaseWriter) -> tuple:
    last_error = None
    
    for attempt in range(MAX_RETRIES):
        try:
            print(f"\n[Scrape] Deneme {attempt + 1}/{MAX_RETRIES}")
            rows = run_scrape(writer, logger_callback=log_callback)
            
            if rows and rows > 0:
                print(f"[Scrape] Başarılı: {rows} satır yazıldı")
                return rows, None
            else:
                last_error = "Veri çekilemedi veya boş döndü"
                print(f"[Scrape] {last_error}")
                
        except requests.exceptions.SSLError as e:
            last_error = f"SSL Hatası: {str(e)[:150]}"
            print(f"[Scrape] {last_error}")
        except requests.exceptions.Timeout as e:
            last_error = f"Timeout: {str(e)[:150]}"
            print(f"[Scrape] {last_error}")
        except requests.exceptions.RequestException as e:
            last_error = f"Request Hatası: {str(e)[:150]}"
            print(f"[Scrape] {last_error}")
        except Exception as e:
            last_error = f"Genel Hata: {str(e)[:150]}"
            print(f"[Scrape] {last_error}")
            traceback.print_exc()
        
        if attempt < MAX_RETRIES - 1:
            delay = RETRY_DELAYS[attempt]
            print(f"[Scrape] {delay} saniye bekleniyor...")
            time.sleep(delay)
    
    return 0, last_error

def main():
    print("=" * 60)
    print("SmartXFlow Scheduled Scraper (Replit)")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)
    
    # Supabase credentials
    supabase_url = os.environ.get('SUPABASE_URL')
    supabase_key = os.environ.get('SUPABASE_ANON_KEY')
    
    if not supabase_url or not supabase_key:
        error_msg = "SUPABASE_URL veya SUPABASE_ANON_KEY eksik!"
        print(f"[FATAL] {error_msg}")
        send_telegram(f"SCRAPER FATAL: {error_msg}", is_error=True)
        sys.exit(1)
    
    # Master/Slave kontrolü
    is_master, reason = check_master_status(supabase_url, supabase_key)
    if not is_master:
        print(f"[Master] Başka bir scraper aktif: {reason}")
        print("[Master] Slave modunda, veri yazmıyorum")
        update_heartbeat(supabase_url, supabase_key, "standby", 0, reason)
        return True
    
    print(f"[Master] Ben master oluyorum: {reason}")
    update_heartbeat(supabase_url, supabase_key, "starting", 0)
    
    # Supabase writer oluştur
    try:
        writer = SupabaseWriter(supabase_url, supabase_key)
        print("[Supabase] Writer oluşturuldu")
    except Exception as e:
        error_msg = f"Supabase Writer hatası: {e}"
        print(f"[FATAL] {error_msg}")
        send_telegram(f"SCRAPER FATAL: {error_msg}", is_error=True)
        update_heartbeat(supabase_url, supabase_key, "error", 0, error_msg[:200])
        sys.exit(1)
    
    # Scrape with retry
    rows, error = run_with_retry(writer)
    
    if error:
        send_telegram(f"SCRAPER HATA (3 retry sonrası):\n{error}", is_error=True)
        update_heartbeat(supabase_url, supabase_key, "error", rows, error[:200])
    else:
        update_heartbeat(supabase_url, supabase_key, "active", rows)
        # Alarm Engine'e sinyal gönder
        send_alarm_engine_signal(supabase_url, supabase_key, rows, rows)
    
    print("=" * 60)
    print(f"Tamamlandı: {rows} satır")
    if error:
        print(f"Son hata: {error}")
    print("=" * 60)
    
    return error is None

def get_last_signal_time() -> Optional[datetime]:
    """Supabase'den son scraper_signal zamanını al"""
    try:
        supabase_url = os.environ.get('SUPABASE_URL')
        supabase_key = os.environ.get('SUPABASE_ANON_KEY')
        if not supabase_url or not supabase_key:
            return None
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}"
        }
        url = f"{supabase_url}/rest/v1/scraper_signal?source=eq.replit&order=created_at.desc&limit=1&select=created_at"
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data:
                ts = data[0]['created_at']
                from datetime import datetime as dt
                if ts.endswith('Z'):
                    ts = ts[:-1] + '+00:00'
                return dt.fromisoformat(ts)
    except Exception as e:
        print(f"[Loop] Son sinyal zamanı alınamadı: {e}")
    return None

def run_loop():
    """9 dakikada bir scrape döngüsü + 10 dk watchdog"""
    INTERVAL_MINUTES = 9
    INTERVAL_SECONDS = INTERVAL_MINUTES * 60
    WATCHDOG_MINUTES = 10
    WATCHDOG_SECONDS = WATCHDOG_MINUTES * 60
    print(f"[Loop] Scraper {INTERVAL_MINUTES} dakikada bir çalışacak")
    print(f"[Watchdog] {WATCHDOG_MINUTES} dk veri gelmezse Telegram uyarısı gönderilecek")
    
    last_successful_scrape = None
    watchdog_alert_sent = False
    
    last_signal = get_last_signal_time()
    if last_signal:
        now = datetime.now(timezone.utc)
        elapsed = (now - last_signal).total_seconds()
        remaining = INTERVAL_SECONDS - elapsed
        last_successful_scrape = last_signal
        if remaining > 30:
            wait_min = remaining / 60
            print(f"[Loop] Son scrape {elapsed/60:.1f} dk önce yapılmış, {wait_min:.1f} dk bekleniyor...")
            time.sleep(remaining)
        else:
            print(f"[Loop] Son scrape {elapsed/60:.1f} dk önce, süre dolmuş - hemen çalışıyor")
    
    while True:
        scrape_ok = False
        try:
            result = main()
            scrape_ok = result if isinstance(result, bool) else True
            if scrape_ok:
                last_successful_scrape = datetime.now(timezone.utc)
                if watchdog_alert_sent:
                    send_telegram(f"<b>SCRAPER TEKRAR ÇALIŞIYOR</b>\nScraper normale döndü, veri akışı devam ediyor.", is_error=False)
                    watchdog_alert_sent = False
        except Exception as e:
            print(f"[Loop] main() hatası: {e}")
            traceback.print_exc()
        
        if not scrape_ok or last_successful_scrape is None:
            now = datetime.now(timezone.utc)
            if last_successful_scrape is not None:
                elapsed = (now - last_successful_scrape).total_seconds()
            else:
                elapsed = WATCHDOG_SECONDS + 1
            
            if elapsed >= WATCHDOG_SECONDS and not watchdog_alert_sent:
                elapsed_min = elapsed / 60
                send_telegram(
                    f"<b>⚠️ SCRAPER UYARI</b>\n"
                    f"Scraper <b>{elapsed_min:.0f} dakikadır</b> veri çekemiyor!\n"
                    f"Son başarılı: {last_successful_scrape.strftime('%H:%M UTC') if last_successful_scrape else 'Hiç'}",
                    is_error=True
                )
                watchdog_alert_sent = True
                print(f"[Watchdog] Telegram uyarısı gönderildi ({elapsed_min:.0f} dk)")
        
        print(f"\n[Loop] Sonraki çalışma {INTERVAL_MINUTES} dakika sonra...")
        time.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    run_loop()
