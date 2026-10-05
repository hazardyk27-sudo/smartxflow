#!/usr/bin/env python3
"""Runtime guard for SmartXFlow Sinyal Engine.

This wrapper deliberately leaves the signal-calculation rules in sinyal_engine.py
untouched. It hardens process/runtime and input-freshness concerns:
- one signal-engine instance per host;
- react only to scraper_signal.signal_type=scrape_complete;
- coalesce multiple pending scrape_complete rows to the newest one;
- refuse signal calculations when the latest prematch scrape is stale;
- use only the current prematch table as the latest-state input;
- fail closed when current-table data cannot be read;
- reject fixtures whose kickoff is missing, invalid, or already reached;
- stop retrying the missing scraper_heartbeat table after PGRST205/404;
- bind signal-engine match hashing to core.hash_utils.
"""
from __future__ import annotations

import os
import re
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
MAX_PREMATCH_AGE_SECONDS = 12 * 60
CURRENT_TABLE_LIMIT = 5000
_lock_handle = None
_HEARTBEAT_TABLE_AVAILABLE = None
_HEARTBEAT_MISSING_LOGGED = False

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


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


def update_heartbeat(status, error_message=None):
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
            "error_message": error_message,
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


def _parse_utc(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _latest_scrape_complete_timestamp():
    """Read the newest successful prematch scrape timestamp, fail closed on errors."""
    try:
        url = (
            f"{engine.SUPABASE_URL.rstrip('/')}/rest/v1/scraper_signal"
            "?signal_type=eq.scrape_complete"
            "&order=created_at.desc&limit=1&select=created_at"
        )
        response = requests.get(url, headers=engine._headers_read(), timeout=10)
        if response.status_code != 200:
            engine.log(
                f"[Freshness] scraper_signal HTTP {response.status_code}: "
                f"{(getattr(response, 'text', '') or '')[:120]}"
            )
            return None
        rows = response.json()
        if not isinstance(rows, list) or not rows:
            engine.log("[Freshness] scrape_complete bulunamadı")
            return None
        return rows[0].get("created_at")
    except Exception as exc:
        engine.log(f"[Freshness] scrape_complete okunamadı: {exc}")
        return None


def _parse_current_kickoff(raw_date, now_utc):
    """Parse Betwatch/ISO kickoff choosing the nearest plausible calendar year.

    The legacy parser rolls dates older than seven days into the next year. That
    is useful for some EML lookups but unsafe for a current-table gate because a
    stale September row in early October could become a false next-year match.
    """
    if not raw_date:
        return None
    text = str(raw_date).strip()

    iso = _parse_utc(text)
    if iso is not None:
        return iso

    match = re.match(
        r"^\s*(\d{1,2})\.([A-Za-z]{3})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?",
        text,
    )
    if not match:
        return None

    month = _MONTHS.get(match.group(2).lower())
    if not month:
        return None
    try:
        day = int(match.group(1))
        hour = int(match.group(3))
        minute = int(match.group(4))
        second = int(match.group(5) or 0)
    except Exception:
        return None

    candidates = []
    for year in (now_utc.year - 1, now_utc.year, now_utc.year + 1):
        try:
            candidates.append(
                datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
            )
        except ValueError:
            continue
    if not candidates:
        return None
    return min(candidates, key=lambda value: abs((value - now_utc).total_seconds()))


def _fetch_current_snapshots_strict(now_utc=None):
    """Read current Moneyway 1X2 rows only and apply a strict prematch gate.

    Returns ``(snapshots, active_keys)`` on a proven read. A successful empty
    response is a valid zero-match state. ``(None, None)`` means input state
    could not be proven and the entire signal scan must be skipped.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    try:
        url = (
            f"{engine.SUPABASE_URL.rstrip('/')}/rest/v1/moneyway_1x2"
            "?select=home,away,league,date,odds1,oddsx,odds2,"
            "pct1,pctx,pct2,amt1,amtx,amt2,volume"
            f"&limit={CURRENT_TABLE_LIMIT}"
        )
        response = requests.get(url, headers=engine._headers_read(), timeout=25)
        if response.status_code != 200:
            engine.log(
                f"[Current Input] moneyway_1x2 HTTP {response.status_code}: "
                f"{(getattr(response, 'text', '') or '')[:120]}"
            )
            return None, None
        rows = response.json()
        if not isinstance(rows, list):
            engine.log("[Current Input] moneyway_1x2 beklenmeyen response; scan iptal")
            return None, None
    except Exception as exc:
        engine.log(f"[Current Input] moneyway_1x2 okunamadı: {exc}")
        return None, None

    snapshots = {}
    active_keys = set()
    started = 0
    invalid_kickoff = 0
    invalid_identity = 0

    for row in rows:
        home = str(row.get("home") or "").strip()
        away = str(row.get("away") or "").strip()
        date = str(row.get("date") or "").strip()
        if not home or not away or not date:
            invalid_identity += 1
            continue

        kickoff = _parse_current_kickoff(date, now_utc)
        if kickoff is None:
            invalid_kickoff += 1
            continue
        if kickoff <= now_utc:
            started += 1
            continue

        key = f"{home}|{away}|{date}"
        clean = dict(row)
        clean["match_id_hash"] = key
        snapshots[key] = clean
        active_keys.add(key)

    engine.log(
        f"[Current Input] rows={len(rows)} active={len(snapshots)} "
        f"started={started} invalid_kickoff={invalid_kickoff} "
        f"invalid_identity={invalid_identity}"
    )
    return snapshots, active_keys


def run_scan_guarded():
    """Run the five signal engines only on fresh, proven current prematch data."""
    now_utc = datetime.now(timezone.utc)
    latest_ts = _latest_scrape_complete_timestamp()
    latest_dt = _parse_utc(latest_ts)
    if latest_dt is None:
        reason = "latest scrape_complete missing/invalid; signal scan skipped"
        engine.log(f"[Freshness] {reason}")
        update_heartbeat("stale_input", reason)
        return False

    age_seconds = max(0.0, (now_utc - latest_dt).total_seconds())
    if age_seconds > MAX_PREMATCH_AGE_SECONDS:
        reason = (
            f"prematch input stale ({age_seconds:.1f}s > "
            f"{MAX_PREMATCH_AGE_SECONDS}s); signal scan skipped"
        )
        engine.log(f"[Freshness] {reason}")
        update_heartbeat("stale_input", reason)
        return False

    snapshots, active_keys = _fetch_current_snapshots_strict(now_utc=now_utc)
    if snapshots is None:
        reason = "current prematch set could not be proven; signal scan skipped"
        update_heartbeat("stale_input", reason)
        return False

    if not snapshots:
        engine.log("[SinyalEngine] Doğrulanmış current sette aktif prematch maç yok")
        return True

    snapshot_lookup = engine.build_snapshot_lookup(snapshots)
    history = engine.fetch_recent_history(active_keys)
    first_snaps = engine.fetch_first_snapshots(active_keys)

    engine.run_underdog_scan(snapshots, snapshot_lookup, active_keys)
    engine.run_cm_scan(
        snapshots,
        snapshot_lookup,
        active_keys,
        history=history,
        first_snaps=first_snaps,
    )
    engine.run_cm_v2_scan(
        snapshots,
        snapshot_lookup,
        active_keys,
        history=history,
        first_snaps=first_snaps,
    )
    engine.run_fs_scan(
        snapshots,
        snapshot_lookup,
        active_keys,
        history=history,
        first_snaps=first_snaps,
    )
    engine.run_eml_scan(snapshots, active_keys)
    return True


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
    engine.run_scan = run_scan_guarded
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
