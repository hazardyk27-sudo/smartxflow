"""Display-only latest-history fallback for started fixtures.

Current market tables intentionally contain only the authoritative prematch feed.
Once a match starts, its current row may be pruned while the fixture/result remains
visible in the UI.  For display only, restore the final prematch snapshot from the
history table.  Alarm and signal engines do not use this module.
"""

from __future__ import annotations

from datetime import datetime, timezone
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


def _fetch_latest_history_row(client: Any, match: Dict[str, Any], market: str) -> Optional[Dict[str, Any]]:
    """Fetch one latest snapshot for one fixture using an indexed exact filter.

    match_id_hash is preferred because it avoids broad history scans.  The
    home/away/league fallback exists only for legacy fixture rows without a hash.
    """
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
    fetch_latest = fetcher or _fetch_latest_history_row
    restored = 0

    for match in result:
        if not isinstance(match, dict):
            continue
        if _has_display_values(match.get("latest"), market):
            continue
        if not _fixture_has_started(match, now_utc=now_utc):
            continue

        try:
            history_row = fetch_latest(client, match, market)
        except Exception as exc:
            print(f"[DisplayFallback] lookup error: {exc}")
            continue
        if not history_row:
            continue

        try:
            latest = client._normalize_history_row(history_row, market)
        except Exception as exc:
            print(f"[DisplayFallback] normalize error: {exc}")
            continue
        if not _has_display_values(latest, market):
            continue

        # Metadata is display-only and lets callers distinguish a frozen final
        # prematch value from an actively updating current-table value.
        latest = dict(latest)
        latest["DataSource"] = "history_fallback"
        latest["IsHistorical"] = True
        match["latest"] = latest
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
        enriched = enrich_started_matches_from_history(self, matches, market)
        if enriched is matches:
            return payload
        result = dict(payload)
        result["matches"] = enriched
        return result

    client_cls.get_all_matches_with_latest = get_all_matches_with_latest
    client_cls.get_matches_paginated = get_matches_paginated
    client_cls._display_history_fallback_bound = True
