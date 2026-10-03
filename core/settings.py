"""
SmartXFlow Settings & Mode Configuration

SMARTXFLOW_MODE environment variable controls the application behavior:
- "server": Runs scraper, writes to SQLite, syncs to Supabase (Replit backend)
- "client": Only reads from Supabase, no scraping (End-user EXE app)

Default: "server" when running on Replit, "client" when running as EXE
"""

import inspect
import os
import json
from dataclasses import dataclass, asdict
from typing import Optional
from enum import Enum

from core.retention_guard import install_supabase_cleanup_guard

# Preview/Replit safety: when SMARTXFLOW_DISABLE_RETENTION_CLEANUP is enabled,
# protect the web-side Supabase retention delete path before app startup.
install_supabase_cleanup_guard()


class AppMode(Enum):
    SERVER = "server"
    CLIENT = "client"


def get_app_mode() -> AppMode:
    """
    Determine the application mode based on environment.
    
    Priority:
    1. SMARTXFLOW_MODE environment variable (explicit override)
    2. REPL_ID exists -> server mode (running on Replit)
    3. Otherwise -> client mode (running as EXE)
    """
    mode_env = os.environ.get("SMARTXFLOW_MODE", "").lower()
    
    if mode_env == "server":
        return AppMode.SERVER
    elif mode_env == "client":
        return AppMode.CLIENT
    
    if os.environ.get("REPL_ID"):
        return AppMode.SERVER
    
    return AppMode.CLIENT


def is_server_mode() -> bool:
    """Check if running in server mode (scraping enabled)"""
    return get_app_mode() == AppMode.SERVER


def is_scraper_disabled() -> bool:
    """Check if scraper is explicitly disabled via DISABLE_SCRAPER env variable"""
    return os.environ.get("DISABLE_SCRAPER", "").lower() in ("true", "1", "yes")


def is_client_mode() -> bool:
    """Check if running in client mode (read-only from Supabase)"""
    return get_app_mode() == AppMode.CLIENT


def get_scrape_interval_seconds() -> int:
    """Get scraper interval in seconds (server mode only) - default 9 minutes"""
    interval_env = os.environ.get("SCRAPE_INTERVAL_MINUTES", "9")
    try:
        minutes = int(interval_env)
        return max(1, min(60, minutes)) * 60
    except ValueError:
        return 9 * 60


def get_supabase_poll_interval_seconds() -> int:
    """Get Supabase polling interval in seconds (client mode)"""
    interval_env = os.environ.get("SUPABASE_POLL_INTERVAL_SECONDS", "30")
    try:
        seconds = int(interval_env)
        return max(10, min(300, seconds))
    except ValueError:
        return 30


def _register_learning_archive_api_from_caller() -> bool:
    """Attach the internal archive route to the Flask app that called init_mode().

    app.py constructs its Flask instance immediately before calling init_mode(). Keeping the
    registration here avoids coupling the Learning Archive package to user/session routes while
    leaving the public /api/match/... auth contract untouched.
    """
    frame = inspect.currentframe()
    try:
        caller = frame.f_back.f_back if frame and frame.f_back else None
        flask_app = caller.f_globals.get("app") if caller is not None else None
        if flask_app is None or not hasattr(flask_app, "add_url_rule"):
            return False
        from learning_archive.server_api import register_learning_archive_routes
        register_learning_archive_routes(flask_app)
        return True
    except Exception as exc:
        print(f"[LearningArchive] Internal API registration skipped: {exc}")
        return False
    finally:
        # Avoid retaining frame references longer than necessary.
        del frame


def init_mode():
    """Initialize/log the application mode and register server-only internal APIs."""
    mode = get_app_mode()
    scraper_disabled = is_scraper_disabled()
    
    mode_name = "SERVER" if mode == AppMode.SERVER else "CLIENT"
    print(f"=" * 50)
    print(f"SmartXFlow Mode: {mode_name}")
    
    if mode == AppMode.SERVER:
        if scraper_disabled:
            print(f"  - Scraper: DISABLED (DISABLE_SCRAPER=true)")
            print(f"  - SQLite: ENABLED (local cache)")
            print(f"  - Supabase: READ-ONLY (UI mode)")
        else:
            interval = get_scrape_interval_seconds() // 60
            print(f"  - Scraper: ENABLED (every {interval} minutes)")
            print(f"  - SQLite: ENABLED (local cache)")
            print(f"  - Supabase: WRITE + READ")
        if _register_learning_archive_api_from_caller():
            print(f"  - Learning Archive API: REGISTERED")
    else:
        poll = get_supabase_poll_interval_seconds()
        print(f"  - Scraper: DISABLED")
        print(f"  - SQLite: DISABLED")
        print(f"  - Supabase: READ-ONLY (poll every {poll}s)")
    
    print(f"=" * 50)
    
    return mode


@dataclass
class Settings:
    scrape_value: int = 1
    scrape_unit_index: int = 0
    cookie_string: Optional[str] = None


class SettingsManager:
    def __init__(self, path: str):
        self.path = path
    
    def load(self) -> Settings:
        if not os.path.exists(self.path):
            return Settings()
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        v = int(data.get("scrape_value", 1))
        u = int(data.get("scrape_unit_index", 0))
        c = data.get("cookie_string")
        return Settings(scrape_value=max(1, v), scrape_unit_index=0 if u == 0 else 1, cookie_string=c)
    
    def save(self, s: Settings) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(asdict(s), f, ensure_ascii=False, indent=2)
