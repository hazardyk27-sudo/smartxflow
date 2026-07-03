"""
Polymarket Client
Public (auth-free) read-only access to Polymarket's Gamma API and Data API.
Used by the /poly page to search football matches and show their largest
matched (executed) orders: wallet address, pseudonym, side, amount, price, time.

No API key required - all endpoints used here are public read-only endpoints.
"""

import re
import time
import threading
import requests
from typing import List, Dict, Any, Optional

GAMMA_BASE = "https://gamma-api.polymarket.com"
DATA_BASE = "https://data-api.polymarket.com"

SOCCER_TAG_ID = 100350  # Verified via GET /tags -> {"id":"100350","label":"Soccer","slug":"soccer"}

_HTTP_TIMEOUT = 10
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (SmartXFlow/poly)",
    "Accept": "application/json",
}

_TR_MAP = {
    'ş': 's', 'Ş': 's', 'ğ': 'g', 'Ğ': 'g', 'ü': 'u', 'Ü': 'u',
    'ı': 'i', 'İ': 'i', 'ö': 'o', 'Ö': 'o', 'ç': 'c', 'Ç': 'c',
}


def _normalize(value: str) -> str:
    if not value:
        return ""
    value = str(value).strip()
    for tr_char, en_char in _TR_MAP.items():
        value = value.replace(tr_char, en_char)
    value = value.lower()
    value = re.sub(r'[^a-z0-9\s]', '', value)
    value = ' '.join(value.split())
    return value


def _get_json(url: str, params: Optional[Dict[str, Any]] = None) -> Any:
    try:
        resp = requests.get(url, params=params, headers=_HEADERS, timeout=_HTTP_TIMEOUT)
        if resp.status_code != 200:
            print(f"[Polymarket] GET {url} -> {resp.status_code}")
            return None
        return resp.json()
    except Exception as e:
        print(f"[Polymarket] Error GET {url}: {e}")
        return None


# ------------------------------------------------------------------
# Event listing / search
# ------------------------------------------------------------------

# Matches "Team A vs. Team B" (base match event). Variant events created by
# Polymarket for the same fixture use a " - Suffix" pattern (e.g.
# "Portugal vs. Spain - More Markets", "- Player Props", "- Exact Score", ...)
# so we exclude anything containing " - " to keep only the main moneyline event.
_MATCH_TITLE_RE = re.compile(r'^(.+?)\s+vs\.?\s+(.+)$', re.IGNORECASE)

_events_cache = {"data": None, "time": 0}
_events_cache_lock = threading.Lock()
_EVENTS_CACHE_TTL = 90


def _parse_match_title(title: str):
    if not title or ' - ' in title:
        return None
    m = _MATCH_TITLE_RE.match(title.strip())
    if not m:
        return None
    home, away = m.group(1).strip(), m.group(2).strip()
    if not home or not away:
        return None
    return home, away


def _fetch_soccer_events(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Fetch active, non-closed soccer events from Gamma API (paginated), cached briefly."""
    now = time.time()
    with _events_cache_lock:
        if not force_refresh and _events_cache["data"] is not None and (now - _events_cache["time"]) < _EVENTS_CACHE_TTL:
            return _events_cache["data"]

    all_events: List[Dict[str, Any]] = []
    page_size = 100  # Gamma API silently caps results at 100 per page regardless of requested limit
    offset = 0
    max_pages = 20  # safety cap (~2000 events)
    for _ in range(max_pages):
        page = _get_json(f"{GAMMA_BASE}/events", {
            "tag_id": SOCCER_TAG_ID,
            "active": "true",
            "closed": "false",
            "limit": page_size,
            "offset": offset,
            "order": "endDate",
            "ascending": "true",
        })
        if not page:
            break
        all_events.extend(page)
        if len(page) < page_size:
            break
        offset += page_size

    with _events_cache_lock:
        _events_cache["data"] = all_events
        _events_cache["time"] = now

    return all_events


def _event_to_match(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    parsed = _parse_match_title(event.get("title", ""))
    if not parsed:
        return None
    home, away = parsed
    return {
        "event_id": event.get("id"),
        "slug": event.get("slug"),
        "title": event.get("title"),
        "home": home,
        "away": away,
        "kickoff_utc": event.get("endDate") or event.get("startDate"),
        "volume": event.get("volume"),
    }


def get_today_matches(hours_ahead: int = 36) -> List[Dict[str, Any]]:
    """Return real head-to-head football matches (not futures/outrights) starting
    within the next `hours_ahead` hours, sorted by kickoff time ascending."""
    from datetime import datetime, timezone, timedelta

    events = _fetch_soccer_events()
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=hours_ahead)

    matches = []
    for event in events:
        m = _event_to_match(event)
        if not m or not m["kickoff_utc"]:
            continue
        try:
            kickoff_str = m["kickoff_utc"].replace("Z", "+00:00")
            kickoff_dt = datetime.fromisoformat(kickoff_str)
        except Exception:
            continue
        if now - timedelta(hours=6) <= kickoff_dt <= cutoff:
            matches.append(m)

    matches.sort(key=lambda x: x["kickoff_utc"])
    return matches


def search_matches(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Search all currently-tradeable football matches by team name (fuzzy, normalized)."""
    query_norm = _normalize(query)
    if not query_norm:
        return []

    events = _fetch_soccer_events()
    results = []
    for event in events:
        m = _event_to_match(event)
        if not m:
            continue
        home_norm = _normalize(m["home"])
        away_norm = _normalize(m["away"])
        if query_norm in home_norm or query_norm in away_norm or query_norm in _normalize(m["title"]):
            results.append(m)

    results.sort(key=lambda x: x.get("kickoff_utc") or "")
    return results[:limit]


def get_event_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    events = _get_json(f"{GAMMA_BASE}/events", {"slug": slug})
    if not events:
        return None
    return events[0]


# ------------------------------------------------------------------
# Trades (matched orders) + user profile
# ------------------------------------------------------------------

_profile_cache: Dict[str, Dict[str, Any]] = {}
_profile_cache_lock = threading.Lock()
_PROFILE_CACHE_TTL = 3600


def _get_public_profile(address: str) -> Dict[str, Any]:
    if not address:
        return {}
    addr_key = address.lower()
    now = time.time()
    with _profile_cache_lock:
        cached = _profile_cache.get(addr_key)
        if cached and (now - cached["time"]) < _PROFILE_CACHE_TTL:
            return cached["data"]

    data = _get_json(f"{GAMMA_BASE}/public-profile", {"address": address}) or {}
    if isinstance(data, list):
        data = data[0] if data else {}

    with _profile_cache_lock:
        _profile_cache[addr_key] = {"data": data, "time": now}

    return data


def get_top_trades(slug: str, top_n: int = 30, trades_per_market: int = 200) -> Dict[str, Any]:
    """Fetch the largest matched (executed) trades for a football match by event slug.

    Returns dict:
      {"found": bool, "event": {...}, "trades": [ {wallet, pseudonym, outcome, amount_usdc, price, timestamp_utc}, ... ]}
    """
    event = get_event_by_slug(slug)
    if not event:
        return {"found": False, "event": None, "trades": []}

    markets = event.get("markets") or []
    all_trades = []

    for market in markets:
        condition_id = market.get("conditionId")
        if not condition_id:
            continue
        outcome_label = market.get("groupItemTitle") or market.get("question") or ""

        trades = _get_json(f"{DATA_BASE}/trades", {
            "market": condition_id,
            "limit": trades_per_market,
        })
        if not trades:
            continue

        for t in trades:
            try:
                usdc_size = float(t.get("usdcSize") or t.get("size") or 0)
            except (TypeError, ValueError):
                usdc_size = 0.0
            try:
                price = float(t.get("price") or 0)
            except (TypeError, ValueError):
                price = 0.0

            outcome_idx = t.get("outcomeIndex")
            outcome_name = t.get("outcome") or outcome_label
            side = t.get("side", "")

            all_trades.append({
                "wallet": t.get("proxyWallet", ""),
                "outcome": outcome_name,
                "outcome_index": outcome_idx,
                "side": side,
                "amount_usdc": round(usdc_size, 2),
                "price": price,
                "timestamp": t.get("timestamp"),
            })

    all_trades.sort(key=lambda x: x["amount_usdc"], reverse=True)
    top_trades = all_trades[:top_n]

    unique_wallets = {t["wallet"] for t in top_trades if t["wallet"]}
    for wallet in unique_wallets:
        profile = _get_public_profile(wallet)
        pseudonym = profile.get("pseudonym") or profile.get("name") or profile.get("displayUsernamePublic") or ""
        for t in top_trades:
            if t["wallet"] == wallet:
                t["pseudonym"] = pseudonym

    for t in top_trades:
        t.setdefault("pseudonym", "")
        ts = t.get("timestamp")
        if ts:
            try:
                from datetime import datetime, timezone
                ts_int = int(ts)
                t["timestamp_iso"] = datetime.fromtimestamp(ts_int, tz=timezone.utc).isoformat()
            except Exception:
                t["timestamp_iso"] = None
        else:
            t["timestamp_iso"] = None

    return {
        "found": True,
        "event": {
            "slug": event.get("slug"),
            "title": event.get("title"),
            "kickoff_utc": event.get("endDate"),
        },
        "trades": top_trades,
    }
