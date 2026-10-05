"""Display-only latest-history fallback for started fixtures.

Current market tables intentionally contain only the authoritative prematch feed.
Once a match starts, its current row may be pruned while the fixture/result remains
visible in the UI. For display only, restore the final prematch snapshot from the
history table. Alarm and signal engines do not use this module.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Optional
from urllib.parse import quote


_SUPPORTED_MARKETS = {
    "moneyway_1x2",
    "moneyway_ou25",
    "moneyway_btts",
    "dropping_1x2",
    "dropping_ou25",
    "dropping_btts",
}

_MARKET_VALUE_KEYS = {
    "moneyway_1x2": ("Odds1", "OddsX", "Odds2", "Pct1", "PctX", "Pct2", "Amt1", "AmtX", "Amt2"),
    "dropping_1x2": ("Odds1", "OddsX", "Odds2", "Pct1", "PctX", "Pct2", "Amt1", "AmtX", "Amt2"),
    "moneyway_ou25": ("Under", "Over", "PctUnder", "PctOver", "AmtUnder", "AmtOver"),
    "dropping_ou25": ("Under", "Over", "PctUnder", "PctOver", "AmtUnder", "AmtOver"),
    "moneyway_btts": ("OddsYes", "OddsNo", "PctYes", "PctNo", "AmtYes", "AmtNo"),
    "dropping_btts": ("OddsYes", "OddsNo", "PctYes", "PctNo", "AmtYes", "AmtNo"),
}

_EMPTY_VALUES = {None, "", "-"}
_POSITIVE_CACHE_TTL = 6 * 60 * 60
_NEGATIVE_CACHE_TTL = 5 * 60
_MAX_PARALLEL_LOOKUPS = 8
_history_cache: Dict[tuple, tuple[float, Optional[Dict[str, Any]]]] = {}
_history_cache_lock = threading.Lock()


def _parse_kickoff_utc(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        if isinstance(value, datetime):
            parsed = value
        else:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _fixture_has_started(match: Dict[str, Any], now_utc: Optional[datetime] = None) -> bool:
    kickoff = _parse_kickoff_utc(match.get("kickoff_utc"))
    if kickoff is None:
        return False
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return kickoff <= now.astimezone(timezone.utc)


def _has_display_values(latest: Any, market: str) -> bool:
    if not isinstance(latest, dict):
        return False
    keys = _MARKET_VALUE_KEYS.get(market, ())
    return any(latest.get(key) not in _EMPTY_VALUES for key in keys)


def _cache_key(match: Dict[str, Any], market: str) -> tuple:
    match_hash = str(match.get("match_id_hash") or "").strip().lower()
    if match_hash:
        return market, match_hash
    return (
        market,
        str(match.get("home_team") or "").strip(),
        str(match.get("away_team") or "").strip(),
        str(match.get("league") or "").strip(),
        str(match.get("kickoff_utc") or "").strip(),
    )


def _fetch_latest_history_row(client: Any, match: Dict[str, Any], market: str) -> Optional[Dict[str, Any]]:
    """Fetch one latest snapshot for one fixture using an indexed exact filter."""
    if market not in _SUPPORTED_MARKETS or not getattr(client, "is_available", False):
        return None

    history_table = f"{market}_history"
    match_hash = str(match.get("match_id_hash") or "").strip()
    if match_hash:
        filter_part = f"match_id_hash=eq.{quote(match_hash, safe='')}"
    else:
        home = str(match.get("home_team") or "").strip()
        away = str(match.get("away_team") or "").strip()
        league = str(match.get("league") or "").strip()
        if not home or not away:
            return None
        filters = [
            f"home=eq.{quote(home, safe='')}",
            f"away=eq.{quote(away, safe='')}",
        ]
        if league:
            filters.append(f"league=eq.{quote(league, safe='')}")
        filter_part = "&".join(filters)

    url = (
        f"{client._rest_url(history_table)}?select=*"
        f"&{filter_part}&order=scraped_at.desc&limit=1"
    )
    try:
        response = client._get_http_client().get(url, headers=client._headers(), timeout=8)
        if response.status_code != 200:
            return None
        rows = response.json()
        if isinstance(rows, list) and rows:
            return rows[0]
    except Exception as exc:
        print(f"[DisplayFallback] history lookup failed for {match_hash or 'legacy fixture'}: {exc}")
    return None


def _fetch_latest_history_row_cached(client: Any, match: Dict[str, Any], market: str) -> Optional[Dict[str, Any]]:
    key = _cache_key(match, market)
    now = time.monotonic()
    with _history_cache_lock:
        cached = _history_cache.get(key)
        if cached is not None:
            cached_at, cached_row = cached
            ttl = _POSITIVE_CACHE_TTL if cached_row else _NEGATIVE_CACHE_TTL
            if now - cached_at < ttl:
                return dict(cached_row) if cached_row else None
            _history_cache.pop(key, None)

    row = _fetch_latest_history_row(client, match, market)
    stored = dict(row) if isinstance(row, dict) else None
    with _history_cache_lock:
        _history_cache[key] = (now, stored)
    return dict(stored) if stored else None


def _apply_history_row(client: Any, match: Dict[str, Any], market: str, history_row: Optional[Dict[str, Any]]) -> bool:
    if not history_row:
        return False
    try:
        latest = client._normalize_history_row(history_row, market)
    except Exception as exc:
        print(f"[DisplayFallback] normalize error: {exc}")
        return False
    if not _has_display_values(latest, market):
        return False

    latest = dict(latest)
    latest["DataSource"] = "history_fallback"
    latest["IsHistorical"] = True
    match["latest"] = latest
    return True


def enrich_started_matches_from_history(
    client: Any,
    matches: Iterable[Dict[str, Any]],
    market: str,
    *,
    now_utc: Optional[datetime] = None,
    fetcher: Optional[Callable[[Any, Dict[str, Any], str], Optional[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """Fill only display-empty, already-started fixtures from their latest history row."""
    if market not in _SUPPORTED_MARKETS:
        return list(matches or [])

    result = list(matches or [])
    candidates = [
        match for match in result
        if isinstance(match, dict)
        and not _has_display_values(match.get("latest"), market)
        and _fixture_has_started(match, now_utc=now_utc)
    ]
    if not candidates:
        return result

    restored = 0
    if fetcher is not None:
        # Injectable sequential path keeps unit tests deterministic.
        for match in candidates:
            try:
                row = fetcher(client, match, market)
            except Exception as exc:
                print(f"[DisplayFallback] lookup error: {exc}")
                continue
            if _apply_history_row(client, match, market, row):
                restored += 1
    else:
        # A today page can contain dozens of already-started fixtures. Exact
        # per-hash reads are reliable, so run a small bounded pool and cache the
        # immutable final prematch snapshot instead of serially blocking the API.
        workers = min(_MAX_PARALLEL_LOOKUPS, len(candidates))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="display-history") as pool:
            futures = {
                pool.submit(_fetch_latest_history_row_cached, client, match, market): match
                for match in candidates
            }
            for future in as_completed(futures):
                match = futures[future]
                try:
                    row = future.result()
                except Exception as exc:
                    print(f"[DisplayFallback] lookup error: {exc}")
                    continue
                if _apply_history_row(client, match, market, row):
                    restored += 1

    if restored:
        print(f"[DisplayFallback] Restored {restored} started fixture(s) from {market}_history")
    return result


def bind_display_history_fallback() -> None:
    """Attach the fallback to UI-facing SupabaseClient match readers only."""
    from . import supabase_client as _supabase_client

    client_cls = _supabase_client.SupabaseClient
    if getattr(client_cls, "_display_history_fallback_bound", False):
        return

    original_all = client_cls.get_all_matches_with_latest
    original_paginated = client_cls.get_matches_paginated

    def get_all_matches_with_latest(self, market: str, date_filter: str = None):
        matches = original_all(self, market, date_filter)
        return enrich_started_matches_from_history(self, matches, market)

    def get_matches_paginated(self, market: str, limit: int = 20, offset: int = 0, today_only: bool = False):
        payload = original_paginated(self, market, limit, offset, today_only)
        if not isinstance(payload, dict):
            return payload
        matches = payload.get("matches")
        if not isinstance(matches, list):
            return payload
        result = dict(payload)
        result["matches"] = enrich_started_matches_from_history(self, matches, market)
        return result

    client_cls.get_all_matches_with_latest = get_all_matches_with_latest
    client_cls.get_matches_paginated = get_matches_paginated
    client_cls._display_history_fallback_bound = True
