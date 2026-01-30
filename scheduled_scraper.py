#!/usr/bin/env python3
"""
SmartXFlow Scheduled Scraper
Replit Scheduled Deployment için tek seferlik (one-shot) scraper
Her 10 dakikada bir otomatik olarak çalışır
"""
import os
import sys
import time
import json
import hashlib
import requests
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import traceback

from scraper.moneyway import DATASETS, EXTRACTOR_MAP, HEADERS, fetch_table, parse_cookie_string
from services.supabase_client import get_supabase_client

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

def update_heartbeat(supabase, status: str, match_count: int = 0, error_msg: Optional[str] = None) -> bool:
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
        
        result = supabase.table("scraper_heartbeat").upsert(data, on_conflict="source").execute()
        print(f"[Heartbeat] {status} - {match_count} matches")
        return True
    except Exception as e:
        print(f"[Heartbeat] Hata: {e}")
        return False

def normalize_field(value: str) -> str:
    if not value:
        return ""
    value = value.strip()
    value = value.replace('ı', 'i').replace('İ', 'I')
    value = value.lower()
    value = ' '.join(value.split())
    return value

def generate_match_id(home: str, away: str, league: str) -> str:
    home_norm = normalize_field(home)
    away_norm = normalize_field(away)
    league_norm = normalize_field(league)
    canonical = f"{league_norm}|{home_norm}|{away_norm}"
    return hashlib.md5(canonical.encode('utf-8')).hexdigest()[:12]

def check_master_status(supabase) -> Tuple[bool, str]:
    try:
        result = supabase.table("scraper_heartbeat").select("*").execute()
        
        if not result.data:
            return True, "no_master"
        
        now = datetime.now(timezone.utc)
        
        for row in result.data:
            if row.get("source") == SCRAPER_SOURCE:
                continue
            
            last_beat = row.get("last_heartbeat")
            if last_beat:
                from dateutil import parser
                beat_time = parser.parse(last_beat)
                diff_minutes = (now - beat_time).total_seconds() / 60
                
                if diff_minutes < 5 and row.get("status") == "active":
                    return False, f"{row.get('source')} is master ({diff_minutes:.1f} min ago)"
        
        return True, "i_am_master"
    except Exception as e:
        print(f"[Master Check] Hata: {e}, devam ediyorum")
        return True, "error_fallback"

def scrape_with_retry(market_key: str, url: str) -> Tuple[List, Optional[str]]:
    error: Optional[str] = None
    for attempt in range(MAX_RETRIES):
        try:
            print(f"[Scrape] {market_key} - Deneme {attempt + 1}/{MAX_RETRIES}")
            
            result = scrape_all(market_key, verbose=False)
            data = list(result) if result else []
            
            if data and len(data) > 0:
                print(f"[Scrape] {market_key} - {len(data)} maç bulundu")
                return data, None
            else:
                error = f"Boş veri döndü: {market_key}"
                print(f"[Scrape] {error}")
                
        except requests.exceptions.SSLError as e:
            error = f"SSL Hatası: {str(e)[:100]}"
            print(f"[Scrape] {error}")
        except requests.exceptions.Timeout as e:
            error = f"Timeout: {str(e)[:100]}"
            print(f"[Scrape] {error}")
        except requests.exceptions.RequestException as e:
            error = f"Request Hatası: {str(e)[:100]}"
            print(f"[Scrape] {error}")
        except Exception as e:
            error = f"Genel Hata: {str(e)[:100]}"
            print(f"[Scrape] {error}")
            traceback.print_exc()
        
        if attempt < MAX_RETRIES - 1:
            delay = RETRY_DELAYS[attempt]
            print(f"[Scrape] {delay} saniye bekleniyor...")
            time.sleep(delay)
    
    return [], error

def save_to_supabase(supabase, market_key: str, data: List[Dict]) -> int:
    saved = 0
    now = datetime.now(timezone.utc).isoformat()
    
    is_moneyway = market_key.startswith("moneyway")
    table_name = "moneyway_snapshots" if is_moneyway else "dropping_odds_snapshots"
    
    market_map = {
        "moneyway-1x2": "1X2",
        "moneyway-ou25": "OU25",
        "moneyway-btts": "BTTS",
        "dropping-1x2": "1X2",
        "dropping-ou25": "OU25",
        "dropping-btts": "BTTS"
    }
    market = market_map.get(market_key, "1X2")
    
    for row in data:
        try:
            home = row.get("Home", "")
            away = row.get("Away", "")
            league = row.get("League", "")
            
            if not home or not away:
                continue
            
            match_id_hash = generate_match_id(home, away, league)
            
            if is_moneyway:
                if market == "1X2":
                    selections = [
                        {"selection": "1", "odds": row.get("Odds1"), "volume": row.get("Amt1"), "share": row.get("Pct1")},
                        {"selection": "X", "odds": row.get("OddsX"), "volume": row.get("AmtX"), "share": row.get("PctX")},
                        {"selection": "2", "odds": row.get("Odds2"), "volume": row.get("Amt2"), "share": row.get("Pct2")}
                    ]
                elif market == "OU25":
                    selections = [
                        {"selection": "O", "odds": row.get("Over"), "volume": row.get("AmtOver"), "share": row.get("PctOver")},
                        {"selection": "U", "odds": row.get("Under"), "volume": row.get("AmtUnder"), "share": row.get("PctUnder")}
                    ]
                else:
                    selections = [
                        {"selection": "Y", "odds": row.get("Yes"), "volume": row.get("AmtYes"), "share": row.get("PctYes")},
                        {"selection": "N", "odds": row.get("No"), "volume": row.get("AmtNo"), "share": row.get("PctNo")}
                    ]
                
                for sel in selections:
                    snapshot = {
                        "match_id_hash": match_id_hash,
                        "market": market,
                        "selection": sel["selection"],
                        "odds": parse_decimal(sel["odds"]),
                        "volume": parse_volume(sel["volume"]),
                        "share": parse_decimal(sel["share"]),
                        "scraped_at_utc": now
                    }
                    supabase.table(table_name).insert(snapshot).execute()
                    saved += 1
            else:
                if market == "1X2":
                    selections = [
                        {"selection": "1", "current_odds": row.get("Odds1"), "opening_odds": row.get("Odds1_prev")},
                        {"selection": "X", "current_odds": row.get("OddsX"), "opening_odds": row.get("OddsX_prev")},
                        {"selection": "2", "current_odds": row.get("Odds2"), "opening_odds": row.get("Odds2_prev")}
                    ]
                elif market == "OU25":
                    selections = [
                        {"selection": "O", "current_odds": row.get("Over"), "opening_odds": row.get("Over_prev")},
                        {"selection": "U", "current_odds": row.get("Under"), "opening_odds": row.get("Under_prev")}
                    ]
                else:
                    selections = [
                        {"selection": "Y", "current_odds": row.get("OddsYes"), "opening_odds": row.get("OddsYes_prev")},
                        {"selection": "N", "current_odds": row.get("OddsNo"), "opening_odds": row.get("OddsNo_prev")}
                    ]
                
                for sel in selections:
                    opening = parse_decimal(sel["opening_odds"])
                    current = parse_decimal(sel["current_odds"])
                    drop_pct = 0
                    if opening and current and opening > 0:
                        drop_pct = ((opening - current) / opening) * 100
                    
                    snapshot = {
                        "match_id_hash": match_id_hash,
                        "market": market,
                        "selection": sel["selection"],
                        "opening_odds": opening,
                        "current_odds": current,
                        "drop_pct": round(drop_pct, 2),
                        "volume": parse_volume(row.get("Volume")),
                        "scraped_at_utc": now
                    }
                    supabase.table(table_name).insert(snapshot).execute()
                    saved += 1
                    
        except Exception as e:
            print(f"[Save] Hata: {e}")
            continue
    
    return saved

def parse_decimal(value) -> Optional[float]:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip().replace('%', '').replace('£', '').replace(',', '').replace(' ', '')
        if not s or s == '-':
            return None
        return float(s)
    except:
        return None

def parse_volume(value) -> Optional[float]:
    if value is None:
        return None
    try:
        s = str(value).strip().replace('£', '').replace(',', '').replace(' ', '')
        if not s or s == '-':
            return None
        return float(s)
    except:
        return None

def main():
    print("=" * 60)
    print("SmartXFlow Scheduled Scraper")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)
    
    try:
        supabase = get_supabase_client()
        print("[Supabase] Bağlantı başarılı")
    except Exception as e:
        error_msg = f"Supabase bağlantı hatası: {e}"
        print(f"[FATAL] {error_msg}")
        send_telegram(f"SCRAPER FATAL: {error_msg}", is_error=True)
        sys.exit(1)
    
    is_master, reason = check_master_status(supabase)
    if not is_master:
        print(f"[Master] Başka bir scraper aktif: {reason}")
        print("[Master] Slave modunda bekliyorum, veri yazmıyorum")
        update_heartbeat(supabase, "standby", 0, reason)
        return
    
    print(f"[Master] Ben master oluyorum: {reason}")
    update_heartbeat(supabase, "starting", 0)
    
    total_saved = 0
    errors = []
    
    for market_key, url in DATASETS.items():
        data, error = scrape_with_retry(market_key, url)
        
        if error:
            errors.append(f"{market_key}: {error}")
            continue
        
        if data:
            saved = save_to_supabase(supabase, market_key, data)
            total_saved += saved
            print(f"[Save] {market_key}: {saved} kayıt yazıldı")
        
        time.sleep(2)
    
    if errors:
        error_summary = "\n".join(errors[:3])
        if len(errors) > 3:
            error_summary += f"\n... ve {len(errors) - 3} hata daha"
        
        send_telegram(f"SCRAPER HATALAR:\n{error_summary}", is_error=True)
        update_heartbeat(supabase, "error", total_saved, error_summary[:200])
    else:
        update_heartbeat(supabase, "active", total_saved)
    
    print("=" * 60)
    print(f"Tamamlandı: {total_saved} kayıt yazıldı")
    if errors:
        print(f"Hatalar: {len(errors)}")
    print("=" * 60)

if __name__ == "__main__":
    main()
