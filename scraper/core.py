"""
SmartXFlow Scraper Core
Real arbworld scraper integration with 6 markets
Now writes to both SQLite (local) and Supabase (cloud)
"""

import os
import time
import requests as http_requests
from typing import Dict, Any, Optional, Callable

from scraper.moneyway import scrape_all, DATASETS
from services.supabase_client import get_database

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY", "")


MARKET_KEY_MAP = {
    "moneyway-1x2": "moneyway_1x2",
    "moneyway-ou25": "moneyway_ou25",
    "moneyway-btts": "moneyway_btts",
    "dropping-1x2": "dropping_1x2",
    "dropping-ou25": "dropping_ou25",
    "dropping-btts": "dropping_btts"
}


def get_cookie_string() -> str:
    """Get cookie string from embedded config or environment"""
    cookie = ""
    
    try:
        import embedded_config
        cookie = getattr(embedded_config, 'EMBEDDED_COOKIE', '')
    except (ImportError, AttributeError):
        pass
    
    if not cookie:
        cookie = os.getenv('ARBWORLD_COOKIE', '')
    
    return cookie


def sync_to_supabase(scraped_data: Dict[str, Any], progress_callback: Optional[Callable] = None) -> Dict[str, int]:
    """
    Sync scraped data to Supabase.
    Returns counts of synced matches and snapshots.
    """
    db = get_database()
    
    if not db.is_supabase_available:
        return {"matches": 0, "snapshots": 0}
    
    total_snapshots = 0
    seen_matches = set()
    
    results = scraped_data.get("results", [])
    
    for result in results:
        dataset_key = result.get("key", "")
        market_key = MARKET_KEY_MAP.get(dataset_key, dataset_key.replace("-", "_"))
        rows = result.get("data", [])
        
        if not rows:
            continue
        
        synced = db.save_scraped_data(market_key, rows)
        total_snapshots += synced
        
        for row in rows:
            home = row.get('Home', '')
            away = row.get('Away', '')
            
            if not home or not away:
                continue
            
            match_key = f"{home}_{away}"
            seen_matches.add(match_key)
    
    return {
        "matches": len(seen_matches),
        "snapshots": total_snapshots
    }


def write_scraper_signal(match_count: int) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[Scraper] Supabase config eksik, sinyal yazılamadı")
        return False
    try:
        url = f"{SUPABASE_URL}/rest/v1/scraper_signal"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        payload = {
            "match_count": match_count,
            "source": "replit",
            "processed": False
        }
        r = http_requests.post(url, json=payload, headers=headers, timeout=10)
        if r.status_code in (200, 201):
            print(f"[Scraper] scraper_signal yazıldı (match_count={match_count})")
            return True
        else:
            print(f"[Scraper] Signal yazma hatası: {r.status_code} - {r.text[:200]}")
            return False
    except Exception as e:
        print(f"[Scraper] Signal yazma exception: {e}")
        return False


def run_scraper(
    output_dir: Optional[str] = None,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
    sync_supabase: bool = True
) -> Dict[str, Any]:
    """
    Run the real arbworld scraper for all 6 markets.
    
    Markets:
    - Moneyway: 1X2, Over/Under 2.5, BTTS
    - Dropping Odds: 1X2, Over/Under 2.5, BTTS
    
    Args:
        output_dir: Directory to save scraped data (default: ./data)
        progress_callback: Optional callback for progress updates
        sync_supabase: Whether to sync to Supabase (default: True)
        
    Returns:
        dict with status, matches count, snapshots count, duration
    """
    start_time = time.time()
    
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    
    os.makedirs(output_dir, exist_ok=True)
    
    cookie_string = get_cookie_string()
    
    try:
        result = scrape_all(
            output_dir=output_dir,
            verbose=False,
            cookie_string=cookie_string,
            progress_cb=progress_callback
        )
        
        total_rows = sum(r.get("rows", 0) for r in result.get("results", []))
        
        supabase_stats = {"matches": 0, "snapshots": 0}
        if sync_supabase:
            if progress_callback:
                progress_callback("Syncing to Supabase...", 0, 1)
            supabase_stats = sync_to_supabase(result, progress_callback)
            if progress_callback:
                progress_callback("Supabase sync complete", 1, 1)
        
        duration = time.time() - start_time
        
        if sync_supabase and supabase_stats["snapshots"] > 0:
            write_scraper_signal(supabase_stats["matches"])
        
        return {
            "status": "ok",
            "matches": total_rows,
            "snapshots": total_rows * len(DATASETS),
            "duration_sec": round(duration, 2),
            "db_path": result.get("db_path", ""),
            "markets": [r["key"] for r in result.get("results", [])],
            "supabase": {
                "synced": supabase_stats["snapshots"] > 0,
                "matches": supabase_stats["matches"],
                "snapshots": supabase_stats["snapshots"]
            }
        }
        
    except Exception as e:
        duration = time.time() - start_time
        return {
            "status": "error",
            "error": str(e),
            "matches": 0,
            "snapshots": 0,
            "duration_sec": round(duration, 2)
        }
