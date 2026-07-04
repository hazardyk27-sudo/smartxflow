"""
Polymarket Client
Public (auth-free) read-only access to Polymarket's Gamma API and Data API.
Used by the /poly page to search football matches and show their largest
matched (executed) orders: wallet address, pseudonym, side, amount, price, time.

No API key required - all endpoints used here are public read-only endpoints.
"""

import os
import re
import time
import threading
import requests
from typing import List, Dict, Any, Optional

GAMMA_BASE = "https://gamma-api.polymarket.com"
DATA_BASE = "https://data-api.polymarket.com"

SOCCER_TAG_ID = 100350  # Verified via GET /tags -> {"id":"100350","label":"Soccer","slug":"soccer"}

# Only trades at/above this USDC size are shown in the per-match trade table
# (and are therefore the only ones a wallet-address search can match against).
# Aggregate stats (total volume, per-selection market chips) still use ALL
# trades regardless of size - this threshold only curates the trade ledger.
MIN_TRADE_AMOUNT_USDC = 1000.0

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


_TRADES_PAGE_LIMIT = 500
_TRADES_MAX_PAGES = 12  # cap at 6000 trades/market to bound request latency (first-fill only)
_TRADES_INCREMENTAL_MAX_PAGES = 400  # ~200k rows safety net when a checkpoint exists; incremental fetch must not stop before reaching since_ts


def _fetch_all_trades(condition_id: str, max_pages: int = _TRADES_MAX_PAGES) -> List[Dict[str, Any]]:
    """Fully paginate the Data API /trades endpoint for a single condition (market),
    so per-outcome volume sums reflect ALL matched trades, not a capped sample.
    Bounded by max_pages as a latency safety net for extremely high-volume markets.
    """
    all_rows: List[Dict[str, Any]] = []
    offset = 0
    for _ in range(max_pages):
        page = _get_json(f"{DATA_BASE}/trades", {
            "market": condition_id,
            "limit": _TRADES_PAGE_LIMIT,
            "offset": offset,
        })
        if not page:
            break
        all_rows.extend(page)
        if len(page) < _TRADES_PAGE_LIMIT:
            break
        offset += _TRADES_PAGE_LIMIT
    return all_rows


def _fetch_new_trades(condition_id: str, since_ts: Optional[int] = None, max_pages: Optional[int] = None):
    """Incrementally fetch only NEW trades for a market (condition_id), newer than
    `since_ts` (unix seconds). The Data API /trades endpoint returns newest-first,
    so we page forward and stop as soon as we reach a trade at or before `since_ts`
    (or run out of pages). If `since_ts` is None, performs a bounded first-fill
    (same cap as _fetch_all_trades) instead of pulling unlimited history.

    IMPORTANT: when `since_ts` is provided (incremental/checkpoint mode), pagination
    must not stop before actually reaching the checkpoint — the caller advances its
    checkpoint to MAX(traded_at) of whatever gets returned/stored here, so a premature
    cutoff (e.g. hitting an arbitrary page cap) would permanently skip older trades
    that lie between the cap and `since_ts`. Incremental calls therefore use a much
    higher safety net (`_TRADES_INCREMENTAL_MAX_PAGES`) than the first-fill cap.

    Returns rows in newest-first order (caller should not assume any particular
    order is required for storage, since each row is upserted independently).
    """
    if max_pages is None:
        max_pages = _TRADES_INCREMENTAL_MAX_PAGES if since_ts is not None else _TRADES_MAX_PAGES
    new_rows: List[Dict[str, Any]] = []
    offset = 0
    hit_page_cap = True
    for _ in range(max_pages):
        page = _get_json(f"{DATA_BASE}/trades", {
            "market": condition_id,
            "limit": _TRADES_PAGE_LIMIT,
            "offset": offset,
        })
        if not page:
            break

        reached_known = False
        for t in page:
            try:
                ts = int(t.get("timestamp") or 0)
            except (TypeError, ValueError):
                ts = 0
            if since_ts is not None and ts <= since_ts:
                reached_known = True
                break
            new_rows.append(t)

        if reached_known:
            hit_page_cap = False
            break
        if len(page) < _TRADES_PAGE_LIMIT:
            hit_page_cap = False
            break
        offset += _TRADES_PAGE_LIMIT
    else:
        hit_page_cap = True

    truncated = since_ts is not None and hit_page_cap
    if truncated:
        print(
            f"[Polymarket] WARNING: _fetch_new_trades hit page cap ({max_pages} pages) "
            f"before reaching checkpoint for condition={condition_id}; returned rows are "
            f"an incomplete prefix. Caller must NOT advance its checkpoint past the oldest "
            f"row actually persisted, or older un-fetched trades will be permanently skipped."
        )

    return new_rows, truncated


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

_closed_events_cache = {"data": None, "time": 0}
_closed_events_cache_lock = threading.Lock()
_CLOSED_EVENTS_CACHE_TTL = 180


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


def _fetch_closed_soccer_events(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Fetch recently-closed (finished) soccer events from Gamma API, newest first.
    Stops paginating once events are older than ~3 days back (we only need yesterday)."""
    from datetime import datetime, timezone, timedelta

    now = time.time()
    with _closed_events_cache_lock:
        if not force_refresh and _closed_events_cache["data"] is not None and (now - _closed_events_cache["time"]) < _CLOSED_EVENTS_CACHE_TTL:
            return _closed_events_cache["data"]

    stop_before = datetime.now(timezone.utc) - timedelta(days=3)
    all_events: List[Dict[str, Any]] = []
    page_size = 100
    offset = 0
    max_pages = 6  # safety cap (~600 events, newest-first so recent matches come first)
    for _ in range(max_pages):
        page = _get_json(f"{GAMMA_BASE}/events", {
            "tag_id": SOCCER_TAG_ID,
            "closed": "true",
            "limit": page_size,
            "offset": offset,
            "order": "endDate",
            "ascending": "false",
        })
        if not page:
            break
        all_events.extend(page)
        oldest_end = page[-1].get("endDate")
        if oldest_end:
            try:
                oldest_dt = datetime.fromisoformat(oldest_end.replace("Z", "+00:00"))
                if oldest_dt < stop_before:
                    break
            except Exception:
                pass
        if len(page) < page_size:
            break
        offset += page_size

    with _closed_events_cache_lock:
        _closed_events_cache["data"] = all_events
        _closed_events_cache["time"] = now

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


def _compute_match_window(hours_ahead: Optional[int], day_filter: Optional[str]):
    """Shared cutoff-window logic for get_today_matches(), used by both the
    Supabase-backed path and the live-API fallback so behavior stays identical."""
    from datetime import datetime, timezone, timedelta
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Europe/Istanbul")
    except Exception:
        tz = timezone(timedelta(hours=3))

    now = datetime.now(timezone.utc)
    now_local = now.astimezone(tz)

    if day_filter == 'today':
        start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = now_local.replace(hour=23, minute=59, second=59, microsecond=0)
        back_cutoff = start_local.astimezone(timezone.utc)
        cutoff = end_local.astimezone(timezone.utc)
    elif day_filter == 'yesterday':
        start_local = (now_local - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_local = (now_local - timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0)
        back_cutoff = start_local.astimezone(timezone.utc)
        cutoff = end_local.astimezone(timezone.utc)
    else:
        start_of_yesterday_local = (now_local - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        back_cutoff = start_of_yesterday_local.astimezone(timezone.utc)
        cutoff = (now + timedelta(hours=hours_ahead)) if hours_ahead is not None else None

    return back_cutoff, cutoff


def get_today_matches(hours_ahead: Optional[int] = 36, day_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return real head-to-head football matches (not futures/outrights).

    Default mode (day_filter=None): matches that started anytime since the beginning
    of yesterday (Europe/Istanbul calendar day) or will start within the next
    `hours_ahead` hours. If `hours_ahead` is None, no upper bound is applied — ALL
    currently active/tradeable (non-closed) upcoming matches are returned, no matter
    how far in the future their kickoff is.

    If `day_filter` is 'today' or 'yesterday', ignores `hours_ahead` and instead
    returns only matches whose kickoff falls within that single Europe/Istanbul
    calendar day — used for the "Bugün" / "Dün" filter tabs.

    Reads from our own Supabase `polymarket_matches` table (same scraper-populated
    source as search_matches()) instead of hitting Polymarket's live Gamma API on
    every page load/tab switch. Falls back to the live API if Supabase is
    unreachable/misconfigured.
    """
    from datetime import datetime

    back_cutoff, cutoff = _compute_match_window(hours_ahead, day_filter)

    rows = _fetch_stored_matches()
    if rows is None:
        return _get_today_matches_live(hours_ahead, day_filter)

    matches = []
    for row in rows:
        home = row.get("home") or ""
        away = row.get("away") or ""
        kickoff_utc = row.get("kickoff_utc")
        if not home or not away or not kickoff_utc:
            continue
        try:
            kickoff_dt = datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00"))
        except Exception:
            continue
        if kickoff_dt >= back_cutoff and (cutoff is None or kickoff_dt <= cutoff):
            matches.append({
                "event_id": row.get("event_id"),
                "slug": row.get("slug"),
                "title": f"{home} vs. {away}",
                "home": home,
                "away": away,
                "kickoff_utc": kickoff_utc,
                "volume": None,
            })

    matches.sort(key=lambda x: x["kickoff_utc"])
    return matches


def _get_today_matches_live(hours_ahead: Optional[int] = 36, day_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Legacy fallback: build the match list directly from Polymarket's live
    Gamma API. Only used when Supabase is unreachable/misconfigured."""
    from datetime import datetime

    back_cutoff, cutoff = _compute_match_window(hours_ahead, day_filter)
    events = _fetch_soccer_events() + _fetch_closed_soccer_events()

    seen_ids = set()
    matches = []
    for event in events:
        event_id = event.get("id")
        if event_id in seen_ids:
            continue
        m = _event_to_match(event)
        if not m or not m["kickoff_utc"]:
            continue
        try:
            kickoff_str = m["kickoff_utc"].replace("Z", "+00:00")
            kickoff_dt = datetime.fromisoformat(kickoff_str)
        except Exception:
            continue
        if kickoff_dt >= back_cutoff and (cutoff is None or kickoff_dt <= cutoff):
            seen_ids.add(event_id)
            matches.append(m)

    matches.sort(key=lambda x: x["kickoff_utc"])
    return matches


def search_matches(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Search football matches by team name (fuzzy, normalized).

    Reads from our own Supabase `polymarket_matches` table (populated incrementally
    every 5 minutes by polymarket_scraper.py, which already covers everything from
    the start of yesterday onward - including closed/finished matches) instead of
    hitting Polymarket's live Gamma API on every keystroke/search. This avoids the
    slow live pagination (`_fetch_soccer_events` + `_fetch_closed_soccer_events`)
    that made search take several seconds per query.

    Falls back to the live API only if Supabase is unreachable/misconfigured, so
    search still works even if the scraper table is empty or unavailable.
    """
    query_norm = _normalize(query)
    if not query_norm:
        return []

    rows = _fetch_stored_matches()
    if rows is None:
        return _search_matches_live(query_norm, limit)

    results = []
    for row in rows:
        home = row.get("home") or ""
        away = row.get("away") or ""
        if not home or not away:
            continue
        home_norm = _normalize(home)
        away_norm = _normalize(away)
        title_norm = _normalize(f"{home} vs. {away}")
        if query_norm in home_norm or query_norm in away_norm or query_norm in title_norm:
            results.append({
                "event_id": row.get("event_id"),
                "slug": row.get("slug"),
                "title": f"{home} vs. {away}",
                "home": home,
                "away": away,
                "kickoff_utc": row.get("kickoff_utc"),
                "volume": None,
            })

    results.sort(key=lambda x: x.get("kickoff_utc") or "")
    return results[:limit]


_stored_matches_cache = {"data": None, "time": 0}
_stored_matches_cache_lock = threading.Lock()
_STORED_MATCHES_CACHE_TTL = 30


def _fetch_stored_matches(force_refresh: bool = False) -> Optional[List[Dict[str, Any]]]:
    """Read all rows from the Supabase `polymarket_matches` table (scraper-populated),
    with a short in-process cache so repeated searches within the same few seconds
    don't re-hit Supabase. Returns None if Supabase isn't configured/reachable
    (caller should fall back to the live API in that case)."""
    now = time.time()
    with _stored_matches_cache_lock:
        if not force_refresh and _stored_matches_cache["data"] is not None and (now - _stored_matches_cache["time"]) < _STORED_MATCHES_CACHE_TTL:
            return _stored_matches_cache["data"]

    base = _supabase_base_url()
    if not base:
        return None
    headers = _supabase_headers()
    try:
        resp = requests.get(
            f"{base}/rest/v1/polymarket_matches",
            headers=headers,
            params={"select": "event_id,slug,home,away,kickoff_utc", "order": "kickoff_utc.desc", "limit": 5000},
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        rows = resp.json()
    except Exception:
        return None

    with _stored_matches_cache_lock:
        _stored_matches_cache["data"] = rows
        _stored_matches_cache["time"] = now
    return rows


def _search_matches_live(query_norm: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Legacy fallback: search directly against Polymarket's live Gamma API.
    Only used when Supabase is unreachable/misconfigured."""
    events = _fetch_soccer_events() + _fetch_closed_soccer_events()
    seen_ids = set()
    results = []
    for event in events:
        event_id = event.get("id")
        if event_id in seen_ids:
            continue
        m = _event_to_match(event)
        if not m:
            continue
        home_norm = _normalize(m["home"])
        away_norm = _normalize(m["away"])
        if query_norm in home_norm or query_norm in away_norm or query_norm in _normalize(m["title"]):
            seen_ids.add(event_id)
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


def _selection_label(group_item_title: str) -> str:
    """Turn a Polymarket sub-market's groupItemTitle into a human 1X2-style
    selection label, e.g. 'Draw (Team A vs. Team B)' -> 'Beraberlik'."""
    if not group_item_title:
        return "Bilinmiyor"
    if group_item_title.lower().startswith("draw"):
        return "Beraberlik"
    return group_item_title


# Extra sub-markets to pull in from the sibling "- More Markets" event.
# Maps the sibling market's groupItemTitle -> our internal market_type key.
_EXTRA_MARKET_TYPES = {
    "o/u 2.5": "ou25",
    "both teams to score": "btts",
}


def _fetch_more_markets_event(base_slug: str) -> Optional[Dict[str, Any]]:
    """Fetch the sibling '<slug>-more-markets' event that carries O/U and BTTS
    sub-markets for a given main match event, if it exists."""
    events = _get_json(f"{GAMMA_BASE}/events", {"slug": f"{base_slug}-more-markets"})
    if not events:
        return None
    return events[0]


def _market_selection_side(market_type: str, raw_group_title: str, raw_outcome: str):
    """Return (selection_label, side_label) for a trade given its market type."""
    raw_outcome_l = (raw_outcome or "").strip().lower()
    if market_type == "1x2":
        selection = _selection_label(raw_group_title)
        if raw_outcome_l == "yes":
            side = "Evet"
        elif raw_outcome_l == "no":
            side = "Hayır"
        else:
            side = raw_outcome or "-"
        return selection, side
    if market_type == "ou25":
        selection = "Toplam Gol 2.5"
        if raw_outcome_l == "over":
            side = "2.5 Üst"
        elif raw_outcome_l == "under":
            side = "2.5 Alt"
        else:
            side = raw_outcome or "-"
        return selection, side
    if market_type == "btts":
        selection = "Karşılıklı Gol (KG)"
        if raw_outcome_l == "yes":
            side = "KG Var"
        elif raw_outcome_l == "no":
            side = "KG Yok"
        else:
            side = raw_outcome or "-"
        return selection, side
    return raw_group_title or "-", raw_outcome or "-"


def get_event_market_specs(slug: str):
    """Return (event, specs) where specs is a list of (market_type, condition_id, market)
    for the event's main 1X2 markets plus its sibling "More Markets" event's O/U 2.5 and
    BTTS sub-markets. Used by the incremental trade-ledger scraper. Returns (None, [])
    if the event cannot be found."""
    event = get_event_by_slug(slug)
    if not event:
        return None, []

    base_slug = event.get("slug") or slug
    more_markets_event = _fetch_more_markets_event(base_slug)

    specs = []
    for market in (event.get("markets") or []):
        condition_id = market.get("conditionId")
        if condition_id:
            specs.append(("1x2", condition_id, market))

    if more_markets_event:
        for market in (more_markets_event.get("markets") or []):
            raw_label = (market.get("groupItemTitle") or "").strip().lower()
            market_type = _EXTRA_MARKET_TYPES.get(raw_label)
            condition_id = market.get("conditionId")
            if market_type and condition_id:
                specs.append((market_type, condition_id, market))

    return event, specs


def _supabase_headers() -> Dict[str, str]:
    key = os.environ.get('SUPABASE_ANON_KEY', '') or os.environ.get('SUPABASE_KEY', '')
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def _supabase_base_url() -> str:
    return (os.environ.get('SUPABASE_URL', '') or '').rstrip('/')


_1X2_OUTCOME_LABELS = {"yes": "Evet", "no": "Hayır"}
_OU25_OUTCOME_LABELS = {"over": "2.5 Üst", "under": "2.5 Alt"}
_BTTS_OUTCOME_LABELS = {"yes": "KG Var", "no": "KG Yok"}
_SIDE_LABELS = {"buy": "Alım", "sell": "Satım"}
_MARKET_TYPE_LABELS = {"1x2": "1X2", "ou25": "2.5 Üst/Alt", "btts": "Karşılıklı Gol"}


def _bet_display_fields(market_type: str, selection_raw: str, outcome_raw: str) -> Dict[str, str]:
    """Map a stored trade row onto the same (selection, side, group) convention
    used by get_top_trades()/_market_selection_side(), so the frontend's
    existing badge coloring and market-summary grouping work unchanged
    regardless of which data source served the response.
    `selection` = team name / fixed market label. `side` = outcome polarity
    (Evet/Hayır, 2.5 Üst/Alt, KG Var/Yok) - NOT the buy/sell action.
    """
    mt = (market_type or "").strip().lower()
    o = (outcome_raw or "").strip().lower()
    if mt == "ou25":
        selection = "Toplam Gol 2.5"
        side = _OU25_OUTCOME_LABELS.get(o, outcome_raw or "-")
        group = "2.5 Üst/Alt"
    elif mt == "btts":
        selection = "Karşılıklı Gol (KG)"
        side = _BTTS_OUTCOME_LABELS.get(o, outcome_raw or "-")
        group = "Karşılıklı Gol (KG)"
    else:
        selection = selection_raw or "-"
        side = _1X2_OUTCOME_LABELS.get(o, outcome_raw or "-")
        group = f"1X2 · {side}"
    return {"selection": selection, "side": side, "group": group}


def get_stored_trades(slug: str, top_n: int = 3000) -> Optional[Dict[str, Any]]:
    """Read the trade ledger for a match from our own Supabase tables
    (`polymarket_matches` + `polymarket_trades`), populated incrementally by
    polymarket_scraper.py. Unlike get_top_trades() (live Polymarket API call),
    this data already has match_phase (prematch/live) precomputed per trade,
    so it can be used to split bets by phase without extra API calls.

    Returns None if the match isn't tracked yet or has no stored trades
    (caller should fall back to get_top_trades() in that case).
    """
    base = _supabase_base_url()
    if not base:
        return None
    headers = _supabase_headers()

    try:
        r = requests.get(
            f"{base}/rest/v1/polymarket_matches",
            headers=headers,
            params={"select": "event_id,home,away,kickoff_utc,slug", "slug": f"eq.{slug}", "limit": 1},
            timeout=8,
        )
        if r.status_code != 200:
            return None
        rows = r.json()
        if not rows:
            return None
        match = rows[0]
        event_id = match.get("event_id")
        if not event_id:
            return None
    except Exception:
        return None

    # Fetch each phase separately (rather than one combined query ordered by
    # traded_at desc) so that high-volume matches with lots of recent LIVE
    # trades don't crowd the older PREMATCH trades out of a single row cap.
    select_cols = "wallet,pseudonym,market_type,selection,side,outcome_raw,amount_usdc,price,traded_at,match_phase"
    trade_rows: List[Dict[str, Any]] = []
    try:
        for phase in ("prematch", "live"):
            r = requests.get(
                f"{base}/rest/v1/polymarket_trades",
                headers=headers,
                params={
                    "select": select_cols,
                    "event_id": f"eq.{event_id}",
                    "match_phase": f"eq.{phase}",
                    "order": "amount_usdc.desc",
                    "limit": 3000,
                },
                timeout=15,
            )
            if r.status_code != 200:
                continue
            trade_rows.extend(r.json())
    except Exception:
        return None

    if not trade_rows:
        return {
            "found": True,
            "source": "stored",
            "event": {
                "slug": match.get("slug") or slug,
                "title": f"{match.get('home', '')} vs {match.get('away', '')}",
                "kickoff_utc": match.get("kickoff_utc"),
                "total_volume": 0.0,
            },
            "markets": [],
            "markets_by_phase": {"all": [], "prematch": [], "live": []},
            "trades": [],
            "phase_counts": {"prematch": 0, "live": 0},
            "phase_volume": {"all": 0.0, "prematch": 0.0, "live": 0.0},
        }

    # volume_sums is tracked per-phase (plus an "all" bucket) so the UI can
    # show market breakdowns/totals that match whichever phase filter (Tümü /
    # Maç Öncesi / Canlı) the user has selected.
    volume_sums: Dict[str, Dict[tuple, float]] = {"all": {}, "prematch": {}, "live": {}}
    phase_volume = {"prematch": 0.0, "live": 0.0}
    phase_counts = {"prematch": 0, "live": 0}
    entries_order: List[tuple] = []

    for row in trade_rows:
        phase = row.get("match_phase") or "prematch"
        if phase not in phase_volume:
            phase = "prematch"
        amt = float(row.get("amount_usdc") or 0)
        phase_volume[phase] += amt
        phase_counts[phase] += 1

        mt = row.get("market_type") or "1x2"
        sel = row.get("selection") or ""
        outc = row.get("outcome_raw") or ""
        key = (mt, sel, outc)
        volume_sums["all"][key] = volume_sums["all"].get(key, 0.0) + amt
        volume_sums[phase][key] = volume_sums[phase].get(key, 0.0) + amt
        if key not in entries_order:
            entries_order.append(key)

    def _build_market_summaries(sums: Dict[tuple, float]) -> List[Dict[str, Any]]:
        by_group: Dict[str, List[Dict[str, Any]]] = {}
        for (mt, sel, outc) in entries_order:
            vol = sums.get((mt, sel, outc), 0.0)
            fields = _bet_display_fields(mt, sel, outc)
            by_group.setdefault(fields["group"], []).append({
                "selection": fields["selection"],
                "side": fields["side"],
                "volume": round(vol, 2),
            })
        summaries: List[Dict[str, Any]] = []
        for group, items in by_group.items():
            total = sum(i["volume"] for i in items) or 0.0
            for i in items:
                i["pct"] = round((i["volume"] / total) * 100, 1) if total > 0 else 0.0
                summaries.append({"group": group, "selection": i["selection"], "side": i["side"], "volume": i["volume"], "pct": i["pct"]})
        return summaries

    markets_by_phase = {
        "all": _build_market_summaries(volume_sums["all"]),
        "prematch": _build_market_summaries(volume_sums["prematch"]),
        "live": _build_market_summaries(volume_sums["live"]),
    }
    market_summaries = markets_by_phase["all"]

    trade_rows.sort(key=lambda t: float(t.get("amount_usdc") or 0), reverse=True)
    qualifying_rows = [t for t in trade_rows if float(t.get("amount_usdc") or 0) >= MIN_TRADE_AMOUNT_USDC]
    top_trades = qualifying_rows[:top_n]
    display_trades = []
    for t in top_trades:
        fields = _bet_display_fields(t.get("market_type"), t.get("selection"), t.get("outcome_raw"))
        action = (t.get("side") or "").strip().lower()
        phase = t.get("match_phase") or "prematch"
        if phase not in ("prematch", "live"):
            phase = "prematch"
        display_trades.append({
            "wallet": t.get("wallet", ""),
            "pseudonym": t.get("pseudonym") or "",
            "selection": fields["selection"],
            "side": fields["side"],
            "action": _SIDE_LABELS.get(action, t.get("side") or "-"),
            "amount_usdc": round(float(t.get("amount_usdc") or 0), 2),
            "price": float(t.get("price") or 0),
            "timestamp_iso": t.get("traded_at"),
            "phase": phase,
        })

    total_volume = phase_volume["prematch"] + phase_volume["live"]

    return {
        "found": True,
        "source": "stored",
        "event": {
            "slug": match.get("slug") or slug,
            "title": f"{match.get('home', '')} vs {match.get('away', '')}",
            "kickoff_utc": match.get("kickoff_utc"),
            "total_volume": round(total_volume, 2),
        },
        "markets": market_summaries,
        "markets_by_phase": markets_by_phase,
        "trades": display_trades,
        "phase_counts": phase_counts,
        "phase_volume": {
            "all": round(total_volume, 2),
            "prematch": round(phase_volume["prematch"], 2),
            "live": round(phase_volume["live"], 2),
        },
    }


def get_top_trades(slug: str, top_n: int = 3000) -> Dict[str, Any]:
    """Fetch the largest matched (executed) trades for a football match by event slug.
    Combines the main 1X2 event with its sibling "More Markets" event to also
    surface Over/Under 2.5 and Both Teams to Score sub-markets.

    Returns dict:
      {"found": bool, "event": {..., "total_volume": float},
       "markets": [ {market_type, group, selection, volume, pct}, ... ],
       "trades": [ {wallet, pseudonym, market_type, selection, side, amount_usdc, price, timestamp_utc}, ... ]}
    """
    event = get_event_by_slug(slug)
    if not event:
        return {"found": False, "event": None, "markets": [], "trades": []}

    base_slug = event.get("slug") or slug
    more_markets_event = _fetch_more_markets_event(base_slug)

    market_specs = []  # list of (market_type, market_dict)
    for market in (event.get("markets") or []):
        market_specs.append(("1x2", market))

    if more_markets_event:
        for market in (more_markets_event.get("markets") or []):
            raw_label = (market.get("groupItemTitle") or "").strip().lower()
            market_type = _EXTRA_MARKET_TYPES.get(raw_label)
            if market_type:
                market_specs.append((market_type, market))

    all_trades = []
    # For every market type (1x2, ou25, btts) each Polymarket sub-market is a
    # binary Yes/No market. Polymarket's own `volume` field on the market
    # combines BOTH sides (e.g. betting "No" on a team still counts toward
    # that team's `volume`), which misleadingly implies "No" money is backing
    # that selection. To show accurate per-side volume, we derive Evet/Hayır
    # (and Üst/Alt, Var/Yok) sums directly from the fully-paginated trades.
    derived_volume_sums: Dict[tuple, float] = {}
    derived_entries = []  # (market_type, selection, side) seen, in order

    for market_type, market in market_specs:
        condition_id = market.get("conditionId")
        if not condition_id:
            continue
        raw_label = market.get("groupItemTitle") or market.get("question") or ""

        # Fully paginate to get an exact (not sampled) per-side volume sum,
        # since a market's single `volume` field combines both Yes and No.
        trades = _fetch_all_trades(condition_id)
        if not trades:
            continue

        for t in trades:
            try:
                price = float(t.get("price") or 0)
            except (TypeError, ValueError):
                price = 0.0
            try:
                # Polymarket's Data API /trades endpoint does NOT return a
                # usdcSize field - "size" is the number of outcome SHARES
                # traded, not a dollar amount. Real USDC value = size * price.
                # (Using raw "size" as if it were dollars badly distorts
                # per-side volume: cheap outcomes need many more shares per
                # dollar than expensive/favorite outcomes, so it understates
                # favorites and overstates underdogs.)
                if t.get("usdcSize") is not None:
                    usdc_size = float(t.get("usdcSize"))
                else:
                    usdc_size = float(t.get("size") or 0) * price
            except (TypeError, ValueError):
                usdc_size = 0.0

            raw_outcome = (t.get("outcome") or "").strip()
            selection, side = _market_selection_side(market_type, raw_label, raw_outcome)

            key = (market_type, selection, side)
            derived_volume_sums[key] = derived_volume_sums.get(key, 0.0) + usdc_size
            if key not in derived_entries:
                derived_entries.append(key)

            all_trades.append({
                "wallet": t.get("proxyWallet", ""),
                "market_type": market_type,
                "selection": selection,
                "side": side,
                "amount_usdc": round(usdc_size, 2),
                "price": price,
                "timestamp": t.get("timestamp"),
            })

    def _with_pct(items):
        total = sum(i["volume"] for i in items) or 0.0
        for i in items:
            i["pct"] = round((i["volume"] / total) * 100, 1) if total > 0 else 0.0
        return items

    market_summaries = []
    onexone_evet_items = [{"selection": sel, "side": side, "volume": round(derived_volume_sums[(mt, sel, side)], 2)}
                          for (mt, sel, side) in derived_entries if mt == "1x2" and side == "Evet"]
    for i in _with_pct(onexone_evet_items):
        market_summaries.append({"market_type": "1x2", "group": "1X2 · Evet", **i})

    onexone_hayir_items = [{"selection": sel, "side": side, "volume": round(derived_volume_sums[(mt, sel, side)], 2)}
                           for (mt, sel, side) in derived_entries if mt == "1x2" and side == "Hayır"]
    for i in _with_pct(onexone_hayir_items):
        market_summaries.append({"market_type": "1x2", "group": "1X2 · Hayır", **i})

    ou25_items = [{"selection": sel, "side": side, "volume": round(derived_volume_sums[(mt, sel, side)], 2)}
                  for (mt, sel, side) in derived_entries if mt == "ou25"]
    for i in _with_pct(ou25_items):
        market_summaries.append({"market_type": "ou25", "group": "2.5 Üst/Alt", **i})

    btts_items = [{"selection": sel, "side": side, "volume": round(derived_volume_sums[(mt, sel, side)], 2)}
                  for (mt, sel, side) in derived_entries if mt == "btts"]
    for i in _with_pct(btts_items):
        market_summaries.append({"market_type": "btts", "group": "Karşılıklı Gol (KG)", **i})

    all_trades.sort(key=lambda x: x["amount_usdc"], reverse=True)
    qualifying_trades = [t for t in all_trades if t["amount_usdc"] >= MIN_TRADE_AMOUNT_USDC]
    top_trades = qualifying_trades[:top_n]

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

    total_volume = sum(i["volume"] for i in market_summaries)

    return {
        "found": True,
        "event": {
            "slug": event.get("slug"),
            "title": event.get("title"),
            "kickoff_utc": event.get("endDate"),
            "total_volume": round(total_volume, 2),
        },
        "markets": market_summaries,
        "trades": top_trades,
    }
