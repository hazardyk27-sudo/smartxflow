"""
SmartXFlow Scraper Core
Real arbworld scraper integration with 6 markets
"""

import os
import time
from typing import Dict, Any, Optional, Callable

from scraper.moneyway import scrape_all, DATASETS


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


def run_scraper(
    output_dir: Optional[str] = None,
    progress_callback: Optional[Callable[[str, int, int], None]] = None
) -> Dict[str, Any]:
    """
    Run the real arbworld scraper for all 6 markets.
    
    Markets:
    - Moneyway: 1X2, Over/Under 2.5, BTTS
    - Dropping Odds: 1X2, Over/Under 2.5, BTTS
    
    Args:
        output_dir: Directory to save scraped data (default: ./data)
        progress_callback: Optional callback for progress updates
        
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
        
        duration = time.time() - start_time
        
        total_rows = sum(r.get("rows", 0) for r in result.get("results", []))
        total_snapshots = total_rows * len(DATASETS)
        
        return {
            "status": "ok",
            "matches": total_rows,
            "snapshots": total_snapshots,
            "duration_sec": round(duration, 2),
            "db_path": result.get("db_path", ""),
            "markets": [r["key"] for r in result.get("results", [])]
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
