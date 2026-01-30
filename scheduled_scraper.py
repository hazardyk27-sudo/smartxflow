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
from standalone_scraper import SupabaseWriter, run_scrape

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
        return
    
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
    
    print("=" * 60)
    print(f"Tamamlandı: {rows} satır")
    if error:
        print(f"Son hata: {error}")
    print("=" * 60)

if __name__ == "__main__":
    main()
