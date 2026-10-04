#!/usr/bin/env python3
"""Runtime guard for SmartXFlow Sinyal Engine.

This wrapper deliberately leaves the signal-calculation rules in sinyal_engine.py
untouched. It only hardens process/runtime concerns:
- one signal-engine instance per host;
- react only to scraper_signal.signal_type=scrape_complete;
- coalesce multiple pending scrape_complete rows to the newest one;
- stop retrying the missing scraper_heartbeat table after PGRST205/404;
- bind signal-engine match hashing to core.hash_utils.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from urllib.parse import quote as url_quote

import requests

from core.hash_utils import make_match_id_hash
import sinyal_engine as engine

try:
    import fcntl
except ImportError:  # pragma: no cover - production/Replit are Linux
    fcntl = None

_LOCK_PATH = "/tmp/smartxflow_sinyal_engine.lock"
_lock_handle = None
_HEARTBEAT_TABLE_AVAILABLE = None
_HEARTBEAT_MISSING_LOGGED = False


def _heartbeat_table_missing(response) -> bool:
    text = getattr(response, "text", "") or ""
    return getattr(response, "status_code", None) == 404 and (
        "scraper_heartbeat" in text or "PGRST205" in text
    )


def _log_heartbeat_missing_once() -> None:
    global _HEARTBEAT_MISSING_LOGGED
    if not _HEARTBEAT_MISSING_LOGGED:
        engine.log(
            "[Heartbeat] scraper_heartbeat yok; Sinyal Engine heartbeat POST'u "
            "bu proses için devre dışı"
        )
        _HEARTBEAT_MISSING_LOGGED = True


def update_heartbeat(status):
    """Heartbeat table is optional; permanently stop 404/PGRST205 retries."""
    global _HEARTBEAT_TABLE_AVAILABLE
    if _HEARTBEAT_TABLE_AVAILABLE is False:
        return False
    try:
        now = datetime.now(timezone.utc).isoformat()
        key = engine.SUPABASE_SERVICE_KEY or engine.SUPABASE_ANON_KEY
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation,resolution=merge-duplicates",
        }
        data = {
            "source": "sinyal_engine",
            "last_heartbeat": now,
            "status": status,
            "updated_at": now,
        }
        response = requests.post(
            f"{engine.SUPABASE_URL.rstrip('/')}/rest/v1/scraper_heartbeat?on_conflict=source",
            json=data,
            headers=headers,
            timeout=5,
        )
        if response.status_code in (200, 201):
            _HEARTBEAT_TABLE_AVAILABLE = True
            return True
        if _heartbeat_table_missing(response):
            _HEARTBEAT_TABLE_AVAILABLE = False
            _log_heartbeat_missing_once()
            return False
        engine.log(
            f"[Heartbeat] HTTP {response.status_code}: "
            f"{(getattr(response, 'text', '') or '')[:120]}"
        )
    except Exception as exc:
        engine.log(f"[Heartbeat] Hata: {exc}")
    return False


def check_new_scraper_signal(since_ts: str):
    """Return newest scrape_complete timestamp after since_ts, ignoring lease signals."""
    try:
        url = (
            f"{engine.SUPABASE_URL.rstrip('/')}/rest/v1/scraper_signal"
            f"?signal_type=eq.scrape_complete"
            f"&created_at=gt.{url_quote(since_ts, safe='')}"
            f"&order=created_at.desc&limit=1&select=created_at"
        )
        response = requests.get(url, headers=engine._headers_read(), timeout=10)
        if response.status_code == 200:
            rows = response.json()
            if rows:
                return rows[0].get("created_at")
        else:
            engine.log(
                f"[Signal Check] HTTP {response.status_code}: "
                f"{(getattr(response, 'text', '') or '')[:120]}"
            )
    except Exception as exc:
        engine.log(f"[Signal Check] Hata: {exc}")
    return None


def _acquire_singleton_lock() -> bool:
    """Prevent duplicate Sinyal Engine instances after duplicate workflow starts."""
    global _lock_handle
    if fcntl is None:
        return True
    handle = open(_LOCK_PATH, "a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        engine.log("[Runtime] Başka bir Sinyal Engine zaten aktif; ikinci proses kapatılıyor")
        return False
    _lock_handle = handle
    return True


def _canonical_signal_hash(home: str, away: str, league: str) -> str:
    return make_match_id_hash(home, away, league)


def _install_runtime_guards() -> None:
    engine.update_heartbeat = update_heartbeat
    engine.check_new_scraper_signal = check_new_scraper_signal
    # EML/fixture joins must use the exact same helper as every producer.
    engine._make_match_id_hash = _canonical_signal_hash


def main() -> int:
    if not _acquire_singleton_lock():
        return 0
    _install_runtime_guards()
    started = time.monotonic()
    engine.log("[Runtime] Sinyal Engine runtime guard aktif")
    try:
        engine.run_engine()
        return 0
    finally:
        elapsed = time.monotonic() - started
        engine.log(f"[Runtime] Sinyal Engine kapandı (uptime={elapsed:.1f}s)")


if __name__ == "__main__":
    raise SystemExit(main())
