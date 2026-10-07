"""Indexed first-snapshot loader for the Sinyal Engine runtime.

The legacy loader walks the entire ``moneyway_1x2_history`` table in
``scraped_at`` order with deep OFFSET pagination.  That preserves the desired
semantics (the first valid odds row for an active fixture) but becomes
increasingly expensive as history grows.

This module keeps the same fixture identity used by the legacy loader
(``home|away|date``) and asks PostgREST for exactly one indexed row per active
fixture whose current odds are already valid.  Results are cached briefly;
the cache is intentionally short-lived because retention/backfill operations
can move the earliest row that still exists in the history table.

It is installed only by ``sinyal_engine_runtime.py``.  The calculation rules in
``sinyal_engine.py`` remain untouched.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from typing import Any, Callable

import requests

_CACHE_TTL_SECONDS = 30 * 60
_CACHE_MAX_ENTRIES = 5000
_MAX_WORKERS = 12
_CURRENT_TABLE_LIMIT = 5000

# composite_key -> (expires_monotonic, history_row)
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _composite(row: dict[str, Any]) -> str:
    home = str(row.get("home") or "").strip()
    away = str(row.get("away") or "").strip()
    date = str(row.get("date") or "").strip()
    if not home or not away or not date:
        return ""
    return f"{home}|{away}|{date}"


def _add_aliases(target: dict[str, list[dict[str, Any]]], key: str, row: dict[str, Any]) -> None:
    """Mirror the legacy return shape: composite key plus legacy hash alias."""
    bucket = [row]
    target[key] = bucket
    real_hash = str(row.get("match_id_hash") or "").strip()
    if real_hash and real_hash != key:
        target[real_hash] = bucket


def _prune_cache(now: float) -> None:
    expired = [key for key, (expires_at, _row) in _cache.items() if expires_at <= now]
    for key in expired:
        _cache.pop(key, None)

    if len(_cache) <= _CACHE_MAX_ENTRIES:
        return
    # Expiry order also approximates insertion age because every entry receives
    # the same TTL.  Keep the newest entries and bound process memory.
    overflow = len(_cache) - _CACHE_MAX_ENTRIES
    oldest = sorted(_cache.items(), key=lambda item: item[1][0])[:overflow]
    for key, _value in oldest:
        _cache.pop(key, None)


def _fetch_current_candidates(engine: Any, unresolved: set[str]) -> dict[str, dict[str, Any]] | None:
    """Return unresolved active rows whose current 1X2 odds are already valid.

    A current row with missing odds cannot pass CM/CMv2/FakeSharp odds checks,
    so it does not need an historical reference yet.  This is what prevents the
    old scan from walking to the end of history looking for fixtures that have
    never produced a valid odds row.
    """
    try:
        url = f"{engine.SUPABASE_URL.rstrip('/')}/rest/v1/moneyway_1x2"
        params = [
            ("select", "home,away,date,odds1,oddsx,odds2"),
            ("limit", str(_CURRENT_TABLE_LIMIT)),
        ]
        response = requests.get(
            url,
            params=params,
            headers=engine._headers_read(),
            timeout=25,
        )
    except Exception as exc:
        engine.log(f"[FirstSnapIndexed] current-table request failed: {exc}")
        return None

    if response.status_code != 200:
        engine.log(
            f"[FirstSnapIndexed] current-table HTTP {response.status_code}: "
            f"{(getattr(response, 'text', '') or '')[:160]}"
        )
        return None

    try:
        rows = response.json()
    except Exception as exc:
        engine.log(f"[FirstSnapIndexed] current-table JSON error: {exc}")
        return None
    if not isinstance(rows, list):
        engine.log("[FirstSnapIndexed] current-table response is not a list")
        return None

    candidates: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = _composite(row)
        if not key or key not in unresolved:
            continue
        if not engine._row_has_valid_odds(row):
            continue
        candidates[key] = row
    return candidates


def _fetch_one_history_row(engine: Any, key: str, current_row: dict[str, Any]):
    """Fetch the exact earliest valid history row for one physical match key."""
    url = f"{engine.SUPABASE_URL.rstrip('/')}/rest/v1/moneyway_1x2_history"
    params = [
        (
            "select",
            "home,away,date,odds1,oddsx,odds2,pct1,pctx,pct2,scraped_at,match_id_hash",
        ),
        ("home", f"eq.{current_row.get('home', '')}"),
        ("away", f"eq.{current_row.get('away', '')}"),
        ("date", f"eq.{current_row.get('date', '')}"),
        # Production history stores missing odds as empty strings.  Filtering
        # them server-side is equivalent to the legacy _row_has_valid_odds gate
        # for the observed dataset, while avoiding transfer of hundreds of blank
        # rows before the market opens.
        ("odds1", "neq."),
        ("oddsx", "neq."),
        ("odds2", "neq."),
        ("order", "scraped_at.asc"),
        ("limit", "1"),
    ]
    try:
        response = requests.get(
            url,
            params=params,
            headers=engine._headers_read(),
            timeout=12,
        )
    except Exception as exc:
        return key, None, f"request failed: {exc}"

    if response.status_code != 200:
        return key, None, f"HTTP {response.status_code}: {(getattr(response, 'text', '') or '')[:120]}"

    try:
        rows = response.json()
    except Exception as exc:
        return key, None, f"JSON error: {exc}"
    if not isinstance(rows, list):
        return key, None, "response is not a list"
    if not rows:
        # A valid current row can race the history append by one scrape.  Do not
        # cache the miss; the next signal cycle will retry it.
        return key, None, None

    row = rows[0]
    if not isinstance(row, dict) or not engine._row_has_valid_odds(row):
        return key, None, "server filter returned an invalid odds row"
    if _composite(row) != key:
        return key, None, "history identity mismatch"
    return key, row, None


def _indexed_fetch(engine: Any, legacy: Callable, active_keys=None):
    if active_keys is None:
        return legacy(active_keys)

    active = {str(key) for key in active_keys if key}
    if not active:
        return {}

    started = time.monotonic()
    now = started
    _prune_cache(now)

    result: dict[str, list[dict[str, Any]]] = {}
    unresolved: set[str] = set()
    cache_hits = 0
    for key in active:
        cached = _cache.get(key)
        if cached and cached[0] > now:
            cache_hits += 1
            _add_aliases(result, key, cached[1])
        else:
            unresolved.add(key)

    if not unresolved:
        engine.log(
            f"[FirstSnapIndexed] active={len(active)} cache_hits={cache_hits} "
            f"queries=0 elapsed={time.monotonic() - started:.3f}s"
        )
        return result

    candidates = _fetch_current_candidates(engine, unresolved)
    if candidates is None:
        # Preserve existing behavior if the optimization cannot prove current
        # state.  This path should be exceptional; correctness wins over speed.
        engine.log("[FirstSnapIndexed] current state unproven; falling back to legacy scan")
        return legacy(active_keys)

    if not candidates:
        engine.log(
            f"[FirstSnapIndexed] active={len(active)} cache_hits={cache_hits} "
            f"eligible=0 queries=0 elapsed={time.monotonic() - started:.3f}s"
        )
        return result

    errors = 0
    misses = 0
    fetched = 0
    workers = min(_MAX_WORKERS, max(1, len(candidates)))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="sxf-firstsnap") as pool:
        futures = {
            pool.submit(_fetch_one_history_row, engine, key, row): key
            for key, row in candidates.items()
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                _returned_key, row, error = future.result()
            except Exception as exc:  # pragma: no cover - defensive guard
                row = None
                error = f"worker failed: {exc}"
            if error:
                errors += 1
                engine.log(f"[FirstSnapIndexed] {key}: {error}")
                continue
            if row is None:
                misses += 1
                continue
            fetched += 1
            _cache[key] = (time.monotonic() + _CACHE_TTL_SECONDS, row)
            _add_aliases(result, key, row)

    _prune_cache(time.monotonic())
    engine.log(
        f"[FirstSnapIndexed] active={len(active)} cache_hits={cache_hits} "
        f"eligible={len(candidates)} fetched={fetched} misses={misses} "
        f"errors={errors} queries={len(candidates)} "
        f"elapsed={time.monotonic() - started:.3f}s"
    )
    return result


def install_first_snapshot_fetch(engine: Any) -> None:
    """Install the indexed loader once, preserving the legacy fallback."""
    current = engine.fetch_first_snapshots
    if getattr(current, "_smartxflow_indexed_first_snapshot", False):
        return

    legacy = current

    def wrapped(active_keys=None):
        return _indexed_fetch(engine, legacy, active_keys)

    wrapped._smartxflow_indexed_first_snapshot = True
    wrapped._smartxflow_legacy_first_snapshot = legacy
    engine.fetch_first_snapshots = wrapped
