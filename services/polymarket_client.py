"""
Polymarket Client
Public (auth-free) read-only access to Polymarket's Gamma API and Data API.
Used by the /poly page to search football matches and show their largest
matched (executed) orders: wallet address, pseudonym, side, amount, price, time.

No API key required - all endpoints used here are public read-only endpoints.
"""

import os
import re
import json
import time
import logging
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

GAMMA_BASE = "https://gamma-api.polymarket.com"
DATA_BASE = "https://data-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"

SOCCER_TAG_ID = 100350  # Verified via GET /tags -> {"id":"100350","label":"Soccer","slug":"soccer"}

# Only trades at/above this USDC size are shown in the per-match trade table
# (and are therefore the only ones a wallet-address search can match against).
# Aggregate stats (total volume, per-selection market chips) still use ALL
# trades regardless of size - this threshold only curates the trade ledger.
MIN_TRADE_AMOUNT_USDC = 100.0
# Only the tracked-wallet flow uses this higher threshold. It applies to the
# canonical POSITION'S total entry stake (sum of BUY fills), not to each fill.
# Example: 600 + 600 BUY on the same outcome = a qualifying 1200 USDC bet.
# SELL proceeds never help a position reach the threshold.
# The general match/trade search above intentionally keeps its 100 USDC rule.
MIN_TRACKED_WALLET_TRADE_AMOUNT_USDC = 1000.0

# Stable public contract for tracked bettor profile/list endpoints.
TRACKED_WALLET_API_CONTRACT_VERSION = "2026-10-02.v2"
TRACKED_WALLET_RAW_RETENTION_DAYS = 365
TRACKED_WALLET_CANONICAL_RETENTION = "durable"
TRACKED_WALLET_CLOSING_LINE_SOURCE = "clob_midpoint"

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
    If Polymarket's hard offset cap (3000) is hit, returns whatever was collected
    so far rather than failing — high-volume markets like World Cup matches will
    still show data from the first N pages.
    """
    all_rows: List[Dict[str, Any]] = []
    offset = 0
    for _ in range(max_pages):
        try:
            page = _get_json(f"{DATA_BASE}/trades", {
                "market": condition_id,
                "limit": _TRADES_PAGE_LIMIT,
                "offset": offset,
            })
        except _OffsetLimitExceeded:
            # Hard Polymarket cap hit — return whatever we have so far.
            break
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
    fetch_failed = False
    _FETCH_RETRIES = 3
    _FETCH_RETRY_DELAY = 1.5
    for _ in range(max_pages):
        page = None
        for attempt in range(_FETCH_RETRIES):
            page = _get_json(f"{DATA_BASE}/trades", {
                "market": condition_id,
                "limit": _TRADES_PAGE_LIMIT,
                "offset": offset,
            })
            if page is not None:
                break
            if attempt < _FETCH_RETRIES - 1:
                time.sleep(_FETCH_RETRY_DELAY)

        if page is None:
            # Request kept failing (timeout/rate-limit/network) even after retries.
            # This is NOT the same as "reached end of data" (empty list) - treat it
            # as a transient failure, not a page-cap truncation, so the caller does
            # not permanently skip a match just because of a temporary API hiccup.
            fetch_failed = True
            break
        if not page:
            hit_page_cap = False
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

    if fetch_failed:
        print(
            f"[Polymarket] WARNING: _fetch_new_trades failed to reach the Data API "
            f"after {_FETCH_RETRIES} retries for condition={condition_id}; skipping this "
            f"cycle without advancing the checkpoint (will retry fully next cycle)."
        )
        return [], True

    truncated = since_ts is not None and hit_page_cap
    if truncated:
        print(
            f"[Polymarket] WARNING: _fetch_new_trades hit page cap ({max_pages} pages) "
            f"before reaching checkpoint for condition={condition_id}; returned rows are "
            f"an incomplete prefix. Caller must NOT advance its checkpoint past the oldest "
            f"row actually persisted, or older un-fetched trades will be permanently skipped."
        )

    return new_rows, truncated


class _OffsetLimitExceeded(Exception):
    """Raised when Polymarket's /activity endpoint rejects an offset beyond
    its hard historical cap (observed: 'max historical activity offset of
    3000 exceeded'). This is NOT a transient failure - deeper history is
    permanently unreachable via this endpoint for this wallet, so callers
    should treat whatever was fetched so far as the complete backfill
    rather than retrying/discarding it."""
    pass


def _get_json(url: str, params: Optional[Dict[str, Any]] = None) -> Any:
    try:
        resp = requests.get(url, params=params, headers=_HEADERS, timeout=_HTTP_TIMEOUT)
        if resp.status_code != 200:
            print(f"[Polymarket] GET {url} -> {resp.status_code}")
            if resp.status_code == 400 and "max historical activity offset" in resp.text.lower():
                raise _OffsetLimitExceeded(resp.text[:200])
            return None
        return resp.json()
    except _OffsetLimitExceeded:
        raise
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

# Market-level resolution (which outcome token actually won) fetched from the
# public CLOB API by conditionId. This is wallet-independent - it tells us
# the true winner of a market regardless of what any individual wallet's
# (possibly asset-less/batched) REDEEM row claims. Once a market is closed
# its resolution never changes, so successful lookups are cached forever for
# the life of the process; unresolved/failed lookups are not cached so they
# get retried on the next request.
_market_resolution_cache: Dict[str, Optional[Dict[str, bool]]] = {}
_market_resolution_lock = threading.Lock()


def _fetch_market_resolution(condition_id: str) -> Optional[Dict[str, bool]]:
    """Look up which specific outcome token won a (closed) market, straight
    from the public CLOB API - wallet-independent ground truth. Returns
    {token_id: is_winner} or None if the market isn't resolved yet / the
    lookup failed. Successful (closed-market) results are cached forever
    for the life of the process since a market's resolution never changes."""
    if not condition_id:
        return None
    with _market_resolution_lock:
        if condition_id in _market_resolution_cache:
            return _market_resolution_cache[condition_id]
    try:
        resp = requests.get(f"{CLOB_BASE}/markets/{condition_id}", timeout=8)
        if resp.status_code != 200:
            return None
        data = resp.json() or {}
    except Exception as e:
        print(f"[Polymarket] CLOB market resolution fetch hatasi ({condition_id[:12]}...): {e}")
        return None

    if not data.get("closed"):
        return None  # not resolved yet - don't cache, retry later

    tokens = data.get("tokens") or []
    resolution = {}
    for t in tokens:
        token_id = t.get("token_id")
        if token_id is not None:
            resolution[token_id] = bool(t.get("winner"))

    if not resolution:
        return None

    with _market_resolution_lock:
        _market_resolution_cache[condition_id] = resolution
    return resolution


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


# Best-effort 3-letter country code -> display name map for events whose
# title doesn't follow the "Team A vs. Team B" pattern (e.g. one-off prop
# markets like "Spread: France (-1.5)"). In that case we fall back to
# decoding the two country codes embedded in the event slug, e.g.
# "fifwc-par-fra-2026-07-04-more-markets" -> Paraguay vs France. Unknown
# codes are shown uppercased rather than dropped, so the Match column is
# never left blank.
_FIFA_COUNTRY_CODES = {
    "arg": "Arjantin", "bra": "Brezilya", "fra": "Fransa", "ger": "Almanya",
    "esp": "İspanya", "spa": "İspanya", "ita": "İtalya", "eng": "İngiltere",
    "por": "Portekiz", "prt": "Portekiz",
    "ned": "Hollanda", "nld": "Hollanda", "net": "Hollanda",
    "bel": "Belçika", "cro": "Hırvatistan", "hrv": "Hırvatistan",
    "uru": "Uruguay", "ury": "Uruguay",
    "mex": "Meksika", "usa": "ABD", "jpn": "Japonya", "jap": "Japonya",
    "kor": "Güney Kore",
    "mar": "Fas", "sen": "Senegal", "gha": "Gana", "ksa": "Suudi Arabistan",
    "aus": "Avustralya", "can": "Kanada", "cmr": "Kamerun", "tun": "Tunus",
    "pol": "Polonya", "swi": "İsviçre", "sui": "İsviçre", "che": "İsviçre",
    "den": "Danimarka",
    "ser": "Sırbistan", "srb": "Sırbistan", "wal": "Galler",
    "irn": "İran", "ira": "İran",
    "qat": "Katar", "ecu": "Ekvador", "cos": "Kosta Rika", "crc": "Kosta Rika",
    "par": "Paraguay", "col": "Kolombiya", "chi": "Şili", "per": "Peru",
    "ven": "Venezuela", "bol": "Bolivya", "nor": "Norveç", "swe": "İsveç",
    "aut": "Avusturya", "sco": "İskoçya", "ukr": "Ukrayna", "tur": "Türkiye",
    "gre": "Yunanistan", "cze": "Çekya", "svk": "Slovakya", "hun": "Macaristan",
    "rou": "Romanya", "rom": "Romanya", "isl": "İzlanda", "ice": "İzlanda",
    "isr": "İsrail", "egy": "Mısır",
    "alg": "Cezayir", "nga": "Nijerya", "nig": "Nijerya",
    "civ": "Fildişi Sahili", "rsa": "Güney Afrika",
    "nzl": "Yeni Zelanda", "chn": "Çin", "ksw": "Kuveyt", "uae": "BAE",
    "irq": "Irak", "jor": "Ürdün", "pan": "Panama", "hon": "Honduras",
    "jam": "Jamaika", "hai": "Haiti", "cuw": "Curaçao", "gua": "Guatemala",
    "sur": "Surinam", "trin": "Trinidad ve Tobago",
    "bih": "Bosna-Hersek", "bos": "Bosna-Hersek",
    "cdr": "Kongo Demokratik Cumhuriyeti",
    "uzb": "Özbekistan", "aze": "Azerbaycan", "geo": "Gürcistan",
    "gib": "Cebelitarık", "kos": "Kosova", "lat": "Letonya",
    "lit": "Litvanya", "mon": "Karadağ", "fin": "Finlandiya",
    "lie": "Lihtenştayn", "smr": "San Marino", "syr": "Suriye",
    "tog": "Togo", "uga": "Uganda", "gui": "Gine", "ang": "Angola",
    "cvi": "Yeşil Burun Adaları", "cub": "Küba", "ind": "Hindistan",
    "leb": "Lübnan", "kaz": "Kazakistan", "slo": "Slovenya",
    "est": "Estonya",
}


# Codes we've already warned about, so an unmapped code (e.g. a club-team
# abbreviation, or a genuinely new country code Polymarket starts using)
# only logs once per process instead of spamming on every request.
_UNKNOWN_SLUG_CODES_WARNED: set = set()


def _lookup_slug_country(code: str) -> str:
    """Resolve a lowercase 3-letter slug code to its Turkish country name,
    logging (once per code) when it falls back to the raw uppercased code
    so gaps in `_FIFA_COUNTRY_CODES` are discoverable instead of silently
    showing an abbreviation to users."""
    name = _FIFA_COUNTRY_CODES.get(code)
    if name is not None:
        return name
    if code not in _UNKNOWN_SLUG_CODES_WARNED:
        _UNKNOWN_SLUG_CODES_WARNED.add(code)
        logger.warning(
            "[Polymarket] Unknown 3-letter slug code '%s' - not in "
            "_FIFA_COUNTRY_CODES, falling back to raw code (may be a club "
            "team, or a missing country mapping)", code
        )
    return code.upper()


def _extract_slug_codes(slug: Optional[str]):
    """Extract the two embedded 3-letter codes from an event slug, e.g.
    'fifwc-par-fra-2026-07-04-more-markets' -> ('par', 'fra'). Returns None
    if the slug doesn't match this shape."""
    if not slug:
        return None
    parts = slug.split('-')
    year_idx = None
    for i, p in enumerate(parts):
        if len(p) == 4 and p.isdigit():
            year_idx = i
            break
    if year_idx is None or year_idx < 2:
        return None
    code1, code2 = parts[year_idx - 2], parts[year_idx - 1]
    if len(code1) != 3 or len(code2) != 3 or not code1.isalpha() or not code2.isalpha():
        return None
    return code1.lower(), code2.lower()


def _parse_slug_teams(slug: Optional[str]):
    """Extract (home, away) from an event slug's embedded 3-letter country
    codes, e.g. 'fifwc-par-fra-2026-07-04-more-markets' -> (Paraguay, Fransa).
    Returns None if the slug doesn't match this shape. Unrecognized codes
    (e.g. club-team abbreviations) fall back to the raw uppercased code -
    see `_slug_codes_known` / `_lookup_stored_match_by_slug` for how callers
    upgrade that to a real name."""
    codes = _extract_slug_codes(slug)
    if not codes:
        return None
    home = _lookup_slug_country(codes[0])
    away = _lookup_slug_country(codes[1])
    return home, away


def _slug_codes_known(slug: Optional[str]) -> bool:
    """True only if BOTH of the slug's embedded codes resolve to a real
    country name via `_FIFA_COUNTRY_CODES` (i.e. `_parse_slug_teams` didn't
    have to fall back to a raw abbreviation for either side)."""
    codes = _extract_slug_codes(slug)
    if not codes:
        return False
    return codes[0] in _FIFA_COUNTRY_CODES and codes[1] in _FIFA_COUNTRY_CODES


def _lookup_stored_match_by_slug(slug: Optional[str]):
    """Look up real home/away team names for an event slug from our own
    Supabase `polymarket_matches` table (scraper-populated). Used as a
    fallback when the slug's embedded codes aren't national-team
    abbreviations we can decode via `_FIFA_COUNTRY_CODES` (e.g. domestic
    club league matches like Moroccan Botola Pro). Returns None if not
    found or Supabase isn't reachable (caller should keep falling back)."""
    if not slug:
        return None
    rows = _fetch_stored_matches()
    if not rows:
        return None
    if slug.endswith("-more-markets"):
        candidates = {slug, slug[: -len("-more-markets")]}
    else:
        candidates = {slug, f"{slug}-more-markets"}
    for row in rows:
        if row.get("slug") in candidates:
            home, away = row.get("home"), row.get("away")
            if home and away:
                return home, away
    return None


def _canonical_base_event_slug(slug: Optional[str]) -> Optional[str]:
    """Normalize sibling event slugs to the main fixture slug."""
    value = str(slug or "").strip()
    if not value:
        return None
    suffix = "-more-markets"
    if value.endswith(suffix):
        value = value[:-len(suffix)]
    return value or None


def _canonical_match_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve one wallet row to SmartXFlow's canonical football match.

    The scraper-populated `polymarket_matches` registry is authoritative for
    event_id, home/away and kickoff. Raw Data API eventId/eventSlug are used as
    stable lookup keys, while title parsing is only a display fallback when an
    old row cannot be linked to the registry.
    """
    raw_event_id = item.get("eventId") or item.get("event_id")
    event_id = str(raw_event_id).strip() if raw_event_id not in (None, "") else None
    raw_slug = item.get("eventSlug") or item.get("event_slug") or item.get("slug")
    base_slug = _canonical_base_event_slug(raw_slug)

    stored_match = None
    rows = _fetch_stored_matches()
    if rows:
        if event_id:
            for row in rows:
                if str(row.get("event_id") or "").strip() == event_id:
                    stored_match = row
                    break
        if stored_match is None and base_slug:
            slug_candidates = {base_slug, f"{base_slug}-more-markets"}
            for row in rows:
                row_slug = str(row.get("slug") or "").strip()
                if row_slug in slug_candidates or _canonical_base_event_slug(row_slug) == base_slug:
                    stored_match = row
                    break

    if stored_match is not None:
        canonical_event_id = str(stored_match.get("event_id") or event_id or "").strip() or None
        canonical_slug = _canonical_base_event_slug(stored_match.get("slug")) or base_slug
        home = str(stored_match.get("home") or "").strip()
        away = str(stored_match.get("away") or "").strip()
        kickoff_utc = stored_match.get("kickoff_utc")
        match_name = f"{home} - {away}" if home and away else (home or away or None)
        match_key = (
            f"event:{canonical_event_id}"
            if canonical_event_id
            else (f"slug:{canonical_slug}" if canonical_slug else None)
        )
        return {
            "match_key": match_key,
            "event_id": canonical_event_id,
            "event_slug": canonical_slug,
            "match_name": match_name,
            "home": home or None,
            "away": away or None,
            "kickoff_utc": kickoff_utc,
            "source": "polymarket_matches",
        }

    # Legacy fallback: keep a stable raw event identity if available, but do
    # not pretend title parsing is authoritative event metadata.
    try:
        _mt, home, away, _selection, _side = _parse_activity_market({
            "title": item.get("title"),
            "slug": raw_slug,
            "outcome": item.get("outcome") or item.get("outcome_raw"),
        })
    except Exception:
        home, away = None, None

    home = str(home or "").strip() or None
    away = str(away or "").strip() or None
    match_name = f"{home} - {away}" if home and away else (home or item.get("title") or None)
    condition_id = item.get("conditionId") or item.get("condition_id")
    match_key = (
        f"event:{event_id}"
        if event_id
        else (f"slug:{base_slug}" if base_slug else (f"condition:{condition_id}" if condition_id else None))
    )
    return {
        "match_key": match_key,
        "event_id": event_id,
        "event_slug": base_slug,
        "match_name": match_name,
        "home": home,
        "away": away,
        "kickoff_utc": item.get("kickoff_utc") or item.get("endDate") or item.get("end_date"),
        "source": "legacy_fallback",
    }


def _with_canonical_match_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    enriched = dict(item)
    meta = _canonical_match_metadata(item)
    enriched.update({
        "match_key": meta.get("match_key"),
        "match_name": meta.get("match_name"),
        "match": meta.get("match_name"),
        "home": meta.get("home"),
        "away": meta.get("away"),
        "kickoff_utc": meta.get("kickoff_utc"),
    })
    if meta.get("event_id"):
        enriched["event_id"] = meta["event_id"]
    if meta.get("event_slug"):
        enriched["slug"] = meta["event_slug"]
    return enriched


_WILL_WIN_TITLE_RE = re.compile(r'^will\s+(.+?)\s+win\b', re.IGNORECASE)


def _parse_will_win_title(title: str):
    """Extract the team name from a one-sided prop title like 'Will US
    Yacoub El Mansour win on 2026-07-05? Yes' -> 'US Yacoub El Mansour'.
    Returns None if the title doesn't match this shape."""
    if not title:
        return None
    m = _WILL_WIN_TITLE_RE.match(title.strip())
    if not m:
        return None
    name = m.group(1).strip()
    return name or None


def _to_decimal_odds(price) -> Optional[float]:
    """Convert a Polymarket outcome probability (0-1) into decimal odds
    (1/price), rounded to 2dp. Returns None for price<=0 (e.g. REDEEM rows
    or missing data) so the caller can render '-' instead of a bogus value."""
    try:
        p = float(price or 0)
    except (TypeError, ValueError):
        return None
    if p <= 0:
        return None
    return round(1.0 / p, 2)


def _fetch_clob_midpoints(
    asset_ids: List[str],
) -> Tuple[Dict[str, float], bool]:
    """Fetch public CLOB midpoint prices for outcome token assets.

    Current Polymarket SDK semantics for POST /midpoints are a JSON object
    mapping token/asset id -> decimal-string midpoint. Partial successful
    chunks are returned with ok=False so callers may persist valid observations
    without pretending the whole batch succeeded.
    """
    clean_assets = list(dict.fromkeys(
        str(asset).strip()
        for asset in asset_ids
        if str(asset or "").strip()
    ))
    if not clean_assets:
        return {}, True

    prices: Dict[str, float] = {}
    complete = True
    batch_size = 100
    for offset in range(0, len(clean_assets), batch_size):
        batch = clean_assets[offset:offset + batch_size]
        try:
            response = requests.post(
                f"{CLOB_BASE}/midpoints",
                headers=_HEADERS,
                json=[{"token_id": asset} for asset in batch],
                timeout=_HTTP_TIMEOUT,
            )
            if response.status_code != 200:
                complete = False
                continue
            payload = response.json()
            if not isinstance(payload, dict):
                complete = False
                continue
            for asset, raw_price in payload.items():
                try:
                    price = float(raw_price)
                except (TypeError, ValueError):
                    continue
                if 0.0 <= price <= 1.0:
                    prices[str(asset)] = price
        except Exception as exc:
            complete = False
            logger.warning("[Polymarket] midpoint batch fetch failed: %s", exc)
    return prices, complete


def _closing_line_metrics(
    entry_price: Any,
    closing_price: Any,
) -> Dict[str, Optional[float]]:
    """Compute bettor-facing closing-line value from probability prices.

    Positive values mean the bettor entered at a cheaper probability than the
    final observed pre-kickoff market price (favorable CLV).
    """
    try:
        entry = float(entry_price)
        close = float(closing_price)
    except (TypeError, ValueError):
        return {
            "closing_decimal": None,
            "clv_probability_pp": None,
            "clv_pct": None,
        }
    if entry <= 0 or entry > 1 or close < 0 or close > 1:
        return {
            "closing_decimal": None,
            "clv_probability_pp": None,
            "clv_pct": None,
        }
    return {
        "closing_decimal": _to_decimal_odds(close),
        "clv_probability_pp": round((close - entry) * 100.0, 2),
        "clv_pct": round(((close / entry) - 1.0) * 100.0, 2),
    }


def _fetch_events_paginated(base_params: Dict[str, Any], page_size: int = 100,
                             stop_check=None) -> List[Dict[str, Any]]:
    """Paginate Gamma API's /events/keyset endpoint (cursor-based via
    `after_cursor`) until the cursor is exhausted - no page-count budget of
    any kind. The plain /events endpoint rejects offsets beyond ~2100 with
    'offset too large, use /events/keyset for deeper pagination', which
    silently truncated the soccer event list once Polymarket's active event
    count grew past that point (e.g. a same-day match landing at list
    position ~2000 was never discovered/stored). A fixed page-count cap on
    this endpoint would reproduce the same bug at a different threshold, so
    the only stop conditions are: an empty page, an absent `next_cursor`, a
    cursor that has been seen before (cycle guard - handles both immediate
    repeats and longer cycles), or `stop_check(page)` returning True (used by
    the closed-events fetch to bail out once it reaches events older than its
    needed window).

    The endpoint silently caps each page at 100 events regardless of the
    `limit` requested (verified: `limit=500` still returns 100)."""
    all_events: List[Dict[str, Any]] = []
    cursor = None
    seen_cursors: set = set()
    while True:
        params = dict(base_params)
        params["limit"] = page_size
        if cursor:
            params["after_cursor"] = cursor
        data = _get_json(f"{GAMMA_BASE}/events/keyset", params)
        if not isinstance(data, dict):
            break
        page = data.get("events") or []
        if not page:
            break
        all_events.extend(page)
        if stop_check and stop_check(page):
            break
        next_cursor = data.get("next_cursor")
        if not next_cursor or next_cursor in seen_cursors:
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    return all_events


def _fetch_soccer_events(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Fetch active, non-closed soccer events from Gamma API (paginated), cached briefly."""
    now = time.time()
    with _events_cache_lock:
        if not force_refresh and _events_cache["data"] is not None and (now - _events_cache["time"]) < _EVENTS_CACHE_TTL:
            return _events_cache["data"]

    all_events = _fetch_events_paginated(
        {"tag_id": SOCCER_TAG_ID, "active": "true", "closed": "false", "order": "endDate", "ascending": "true"},
    )

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

    def _stop_when_older_than_window(page: List[Dict[str, Any]]) -> bool:
        oldest_end = page[-1].get("endDate")
        if not oldest_end:
            return False
        try:
            oldest_dt = datetime.fromisoformat(oldest_end.replace("Z", "+00:00"))
            return oldest_dt < stop_before
        except Exception:
            return False

    all_events = _fetch_events_paginated(
        {"tag_id": SOCCER_TAG_ID, "closed": "true", "order": "endDate", "ascending": "false"},
        stop_check=_stop_when_older_than_window,
    )

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

    rows = _fetch_stored_matches(
        back_cutoff=back_cutoff,
        cutoff=cutoff,
    )
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


def get_all_active_matches(hours_ahead: int = 168) -> List[Dict[str, Any]]:
    """Fetch real head-to-head football matches from the live Gamma API within
    the window [start-of-yesterday .. now+hours_ahead]. Used by the scraper to
    discover newly listed matches (e.g. knockout-round games added by Polymarket
    hours before kickoff) that haven't yet been written to `polymarket_matches`.

    Default `hours_ahead=168` (7 days) keeps the discovery window wide enough to
    catch any upcoming match while avoiding processing thousands of old events."""
    from datetime import datetime, timezone, timedelta
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Europe/Istanbul")
    except Exception:
        tz = timezone(timedelta(hours=3))

    now = datetime.now(timezone.utc)
    now_local = now.astimezone(tz)
    start_of_yesterday_local = (now_local - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    back_cutoff = start_of_yesterday_local.astimezone(timezone.utc)
    forward_cutoff = now + timedelta(hours=hours_ahead)

    events = _fetch_soccer_events(force_refresh=True) + _fetch_closed_soccer_events(force_refresh=True)
    seen_ids: set = set()
    matches: List[Dict[str, Any]] = []
    for event in events:
        event_id = event.get("id")
        if event_id in seen_ids:
            continue
        m = _event_to_match(event)
        if not m or not m.get("kickoff_utc"):
            continue
        try:
            kickoff_dt = datetime.fromisoformat(m["kickoff_utc"].replace("Z", "+00:00"))
        except Exception:
            continue
        if kickoff_dt < back_cutoff or kickoff_dt > forward_cutoff:
            continue
        seen_ids.add(event_id)
        matches.append(m)
    matches.sort(key=lambda x: x.get("kickoff_utc") or "")
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


_stored_matches_cache: Dict[Tuple[Optional[str], Optional[str]], Dict[str, Any]] = {}
_stored_matches_cache_lock = threading.Lock()
_STORED_MATCHES_CACHE_TTL = 30


def _fetch_stored_matches(
    force_refresh: bool = False,
    back_cutoff: Optional[datetime] = None,
    cutoff: Optional[datetime] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Read stored matches, optionally restricting the query at Supabase.

    Match-list callers pass their exact kickoff window so PostgREST returns only
    relevant rows. Search/canonical-identity callers omit bounds and retain the
    existing broad registry read. Cache entries are keyed by the exact window so
    a bounded page load can never poison an unbounded identity/search lookup.
    """
    def _bound_iso(value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    lower_iso = _bound_iso(back_cutoff)
    upper_iso = _bound_iso(cutoff)
    cache_key = (lower_iso, upper_iso)
    now = time.time()
    with _stored_matches_cache_lock:
        cached = _stored_matches_cache.get(cache_key)
        if (
            not force_refresh
            and cached is not None
            and (now - cached["time"]) < _STORED_MATCHES_CACHE_TTL
        ):
            return cached["data"]

    base = _supabase_base_url()
    if not base:
        return None
    headers = _supabase_headers()
    params = [
        ("select", "event_id,slug,home,away,kickoff_utc"),
        ("order", "kickoff_utc.desc"),
        ("limit", "5000"),
    ]
    if lower_iso is not None:
        params.append(("kickoff_utc", f"gte.{lower_iso}"))
    if upper_iso is not None:
        params.append(("kickoff_utc", f"lte.{upper_iso}"))

    try:
        resp = requests.get(
            f"{base}/rest/v1/polymarket_matches",
            headers=headers,
            params=params,
            timeout=8,
        )
        if resp.status_code != 200:
            return None
        rows = resp.json()
        if not isinstance(rows, list):
            return None
    except Exception:
        return None

    with _stored_matches_cache_lock:
        _stored_matches_cache[cache_key] = {"data": rows, "time": now}
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
_MARKET_TYPE_LABELS = {
    "1x2": "1X2",
    "ou25": "Toplam Gol 2.5",
    "btts": "Karşılıklı Gol",
    "special": "Özel Market",
}


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
    select_cols = "wallet,pseudonym,market_type,selection,side,outcome_raw,asset,amount_usdc,price,traded_at,match_phase"
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
        side_raw = (row.get("side") or "").strip().lower()
        # "Satım" (sell) trades reduce the selection's and the match's total
        # volume instead of adding to it - a sell means the trader is
        # unwinding a previously-placed bet on that option, so the net
        # exposure/volume on that outcome goes down, not up.
        signed_amt = -float(row.get("amount_usdc") or 0) if side_raw == "sell" else float(row.get("amount_usdc") or 0)
        amt = signed_amt
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


# ------------------------------------------------------------------
# Takip edilen bahisçiler (tracked wallets) - Task #259
#
# Polymarket'in market-bazlı /trades feed'i, aynı blockchain işleminde birden
# fazla kullanıcının toplu (batch) eşleştiği durumlarda diğer cüzdanların
# payını gizleyip tek bir cüzdana atfedebiliyor (confirmed via direct API
# comparison). Kullanıcının açıkça takibe aldığı belirli cüzdanlar için bunun
# yerine cüzdana özel /activity ve /positions endpoint'leri kullanılır - bunlar
# o cüzdanın TÜM işlemlerini/pozisyonlarını eksiksiz döner. Bu endpoint'ler
# `user=` zorunlu kıldığı için toplu/taranabilir değildir; sadece açıkça takip
# edilen cüzdanlar için çağrılır.
# ------------------------------------------------------------------

_ACTIVITY_PAGE_LIMIT = 500
_ACTIVITY_MAX_PAGES = 200         # ilk dolum (checkpoint yok) - ~100k islem tarama
_ACTIVITY_INCREMENTAL_MAX_PAGES = 200  # checkpoint varken - ~100k islem guvenlik agi

_POSITIONS_PAGE_LIMIT = 500
_POSITIONS_MAX_PAGES = 20


_SOCCER_REGISTRY_CACHE_TTL = 15 * 60
_SOCCER_REGISTRY_BATCH_SIZE = 75

FOOTBALL_CLASS_VERIFIED = "verified_football"
FOOTBALL_CLASS_NON_FOOTBALL = "verified_non_football"
FOOTBALL_CLASS_UNCERTAIN = "uncertain"
FOOTBALL_CLASSIFIER_VERSION = "gamma-soccer-v2"
# Positive Soccer proof is durable. Negative proof is deliberately short-lived
# and must be revalidated so stale taxonomy/mapping cannot permanently hide a
# real football market.
FOOTBALL_NON_FOOTBALL_RECHECK_SECONDS = 60 * 60
_soccer_condition_registry_cache: Dict[str, Tuple[bool, float]] = {}
_soccer_event_registry_cache: Dict[str, Tuple[bool, float]] = {}
_soccer_registry_lock = threading.Lock()


def _registry_id(value: Any) -> str:
    return str(value or "").strip().lower()


def _verified_soccer_condition_ids(
    condition_ids: List[Any],
    force_refresh: bool = False,
) -> Tuple[set, bool]:
    """Return condition IDs verified by Gamma's Soccer tag registry.

    The query combines Gamma's condition_ids filter with tag_id=SOCCER_TAG_ID.
    A successful response that omits a condition is a verified non-soccer
    result. A request failure is different: callers receive ok=False so they
    can retry instead of silently advancing checkpoints with incomplete data.
    """
    wanted = sorted({_registry_id(value) for value in condition_ids if _registry_id(value)})
    if not wanted:
        return set(), True

    now = time.time()
    verified: set = set()
    pending: List[str] = []
    with _soccer_registry_lock:
        for condition_id in wanted:
            cached = _soccer_condition_registry_cache.get(condition_id)
            if (
                not force_refresh
                and cached is not None
                and (now - cached[1]) < _SOCCER_REGISTRY_CACHE_TTL
            ):
                if cached[0]:
                    verified.add(condition_id)
            else:
                pending.append(condition_id)

    for offset in range(0, len(pending), _SOCCER_REGISTRY_BATCH_SIZE):
        chunk = pending[offset:offset + _SOCCER_REGISTRY_BATCH_SIZE]
        data = _get_json(
            f"{GAMMA_BASE}/markets",
            {
                "condition_ids": chunk,
                "tag_id": SOCCER_TAG_ID,
                "related_tags": "false",
                "limit": 100,
            },
        )
        if not isinstance(data, list):
            return verified, False

        returned = {
            _registry_id(market.get("conditionId"))
            for market in data
            if isinstance(market, dict) and market.get("conditionId")
        }
        returned &= set(chunk)

        stamp = time.time()
        with _soccer_registry_lock:
            for condition_id in chunk:
                is_soccer = condition_id in returned
                _soccer_condition_registry_cache[condition_id] = (is_soccer, stamp)
                if is_soccer:
                    verified.add(condition_id)

    return verified, True


def _verified_soccer_event_ids(
    event_ids: List[Any],
    force_refresh: bool = False,
) -> Tuple[set, bool]:
    """Event-ID fallback for rows that carry reliable Gamma event identity."""
    wanted = sorted({_registry_id(value) for value in event_ids if _registry_id(value)})
    if not wanted:
        return set(), True

    now = time.time()
    verified: set = set()
    pending: List[str] = []
    with _soccer_registry_lock:
        for event_id in wanted:
            cached = _soccer_event_registry_cache.get(event_id)
            if (
                not force_refresh
                and cached is not None
                and (now - cached[1]) < _SOCCER_REGISTRY_CACHE_TTL
            ):
                if cached[0]:
                    verified.add(event_id)
            else:
                pending.append(event_id)

    for offset in range(0, len(pending), _SOCCER_REGISTRY_BATCH_SIZE):
        chunk = pending[offset:offset + _SOCCER_REGISTRY_BATCH_SIZE]
        data = _get_json(
            f"{GAMMA_BASE}/events",
            {
                "id": chunk,
                "tag_id": SOCCER_TAG_ID,
                "limit": 100,
            },
        )
        if not isinstance(data, list):
            return verified, False

        returned = {
            _registry_id(event.get("id"))
            for event in data
            if isinstance(event, dict) and event.get("id")
        }
        returned &= set(chunk)

        stamp = time.time()
        with _soccer_registry_lock:
            for event_id in chunk:
                is_soccer = event_id in returned
                _soccer_event_registry_cache[event_id] = (is_soccer, stamp)
                if is_soccer:
                    verified.add(event_id)

    return verified, True


def _gamma_tag_rows(obj: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(obj, dict):
        return []
    tags = obj.get("tags")
    return [tag for tag in tags if isinstance(tag, dict)] if isinstance(tags, list) else []


def _gamma_object_has_soccer_tag(obj: Optional[Dict[str, Any]]) -> bool:
    for tag in _gamma_tag_rows(obj):
        tag_id = _registry_id(tag.get("id"))
        slug = _registry_id(tag.get("slug"))
        label = _registry_id(tag.get("label"))
        if tag_id == str(SOCCER_TAG_ID) or slug == "soccer" or label == "soccer":
            return True
    return False


def _gamma_object_has_explicit_non_soccer_tags(
    obj: Optional[Dict[str, Any]],
) -> bool:
    tags = _gamma_tag_rows(obj)
    return bool(tags) and not _gamma_object_has_soccer_tag(obj)


def _market_parent_event_ids(market: Dict[str, Any]) -> List[str]:
    event_ids: List[str] = []
    direct = _registry_id(market.get("eventId") or market.get("event_id"))
    if direct:
        event_ids.append(direct)
    events = market.get("events")
    if isinstance(events, list):
        for event in events:
            if isinstance(event, dict):
                event_id = _registry_id(event.get("id"))
                if event_id and event_id not in event_ids:
                    event_ids.append(event_id)
    return event_ids


def _parse_registry_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _persisted_classification_is_trusted(
    row: Optional[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> bool:
    if not isinstance(row, dict):
        return False
    classification = row.get("classification")
    if classification == FOOTBALL_CLASS_VERIFIED:
        return True
    if classification != FOOTBALL_CLASS_NON_FOOTBALL:
        return False
    if row.get("classifier_version") not in (None, FOOTBALL_CLASSIFIER_VERSION):
        return False
    checked = _parse_registry_time(row.get("last_checked_at"))
    if checked is None:
        return False
    now = now or datetime.now(timezone.utc)
    return (
        now - checked
    ).total_seconds() <= FOOTBALL_NON_FOOTBALL_RECHECK_SECONDS


def _load_persisted_sport_registry(
    identity_type: str,
    identity_ids: List[str],
) -> Dict[str, Dict[str, Any]]:
    """Best-effort read of durable classification evidence.

    Missing migration/table is intentionally treated as an empty registry so
    rollout never blocks the existing live Gamma verification path.
    """
    ids = sorted({_registry_id(value) for value in identity_ids if _registry_id(value)})
    if not ids:
        return {}
    base = _supabase_base_url()
    if not base:
        return {}

    found: Dict[str, Dict[str, Any]] = {}
    try:
        for offset in range(0, len(ids), 75):
            chunk = ids[offset:offset + 75]
            quoted = ",".join(chunk)
            response = requests.get(
                f"{base}/rest/v1/polymarket_sport_registry",
                headers=_supabase_headers(),
                params={
                    "select": "identity_type,identity_id,event_id,classification,classifier_version,source,last_checked_at,next_retry_at,evidence",
                    "identity_type": f"eq.{identity_type}",
                    "identity_id": f"in.({quoted})",
                },
                timeout=10,
            )
            if response.status_code != 200:
                return found
            rows = response.json()
            if not isinstance(rows, list):
                return found
            for row in rows:
                identity_id = _registry_id(row.get("identity_id"))
                if identity_id:
                    found[identity_id] = row
    except Exception:
        return found
    return found


def _persist_sport_registry_records(records: List[Dict[str, Any]]) -> None:
    if not records:
        return
    base = _supabase_base_url()
    if not base:
        return

    now = datetime.now(timezone.utc).isoformat()
    payload = []
    for record in records:
        identity_type = record.get("identity_type")
        identity_id = _registry_id(record.get("identity_id"))
        classification = record.get("classification")
        if identity_type not in ("event", "condition") or not identity_id:
            continue
        if classification not in (
            FOOTBALL_CLASS_VERIFIED,
            FOOTBALL_CLASS_NON_FOOTBALL,
            FOOTBALL_CLASS_UNCERTAIN,
        ):
            continue
        payload.append({
            "identity_type": identity_type,
            "identity_id": identity_id,
            "event_id": _registry_id(record.get("event_id")) or None,
            "classification": classification,
            "classifier_version": FOOTBALL_CLASSIFIER_VERSION,
            "source": record.get("source") or "gamma",
            "evidence": record.get("evidence") or {},
            "last_checked_at": now,
            "next_retry_at": (
                (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
                if classification == FOOTBALL_CLASS_UNCERTAIN
                else None
            ),
        })
    if not payload:
        return

    # Never downgrade an already verified football identity because a later
    # request became uncertain. Read-before-write also allows a corrected
    # positive Soccer proof to upgrade an older non-football classification.
    by_type: Dict[str, List[str]] = {"event": [], "condition": []}
    for row in payload:
        by_type[row["identity_type"]].append(row["identity_id"])
    existing: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for identity_type, ids in by_type.items():
        for identity_id, row in _load_persisted_sport_registry(identity_type, ids).items():
            existing[(identity_type, identity_id)] = row

    safe_payload = []
    for row in payload:
        old = existing.get((row["identity_type"], row["identity_id"]))
        old_class = old.get("classification") if old else None
        new_class = row["classification"]
        if old_class == FOOTBALL_CLASS_VERIFIED and new_class != FOOTBALL_CLASS_VERIFIED:
            continue
        if (
            old_class == FOOTBALL_CLASS_NON_FOOTBALL
            and new_class == FOOTBALL_CLASS_UNCERTAIN
        ):
            continue
        safe_payload.append(row)
    if not safe_payload:
        return

    try:
        headers = {
            **_supabase_headers(),
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        }
        for offset in range(0, len(safe_payload), 500):
            requests.post(
                f"{base}/rest/v1/polymarket_sport_registry"
                "?on_conflict=identity_type,identity_id",
                headers=headers,
                json=safe_payload[offset:offset + 500],
                timeout=15,
            )
    except Exception:
        pass


def _fetch_direct_gamma_markets(
    condition_ids: List[str],
) -> Tuple[Dict[str, Dict[str, Any]], bool]:
    wanted = sorted({_registry_id(value) for value in condition_ids if _registry_id(value)})
    result: Dict[str, Dict[str, Any]] = {}
    if not wanted:
        return result, True
    for offset in range(0, len(wanted), _SOCCER_REGISTRY_BATCH_SIZE):
        chunk = wanted[offset:offset + _SOCCER_REGISTRY_BATCH_SIZE]
        data = _get_json(
            f"{GAMMA_BASE}/markets",
            {
                "condition_ids": chunk,
                "related_tags": "true",
                "limit": 100,
            },
        )
        if not isinstance(data, list):
            return result, False
        for market in data:
            if not isinstance(market, dict):
                continue
            condition_id = _registry_id(market.get("conditionId"))
            if condition_id in chunk:
                result[condition_id] = market
    return result, True


def _fetch_direct_gamma_events(
    event_ids: List[str],
) -> Tuple[Dict[str, Dict[str, Any]], bool]:
    wanted = sorted({_registry_id(value) for value in event_ids if _registry_id(value)})
    result: Dict[str, Dict[str, Any]] = {}
    if not wanted:
        return result, True
    for offset in range(0, len(wanted), _SOCCER_REGISTRY_BATCH_SIZE):
        chunk = wanted[offset:offset + _SOCCER_REGISTRY_BATCH_SIZE]
        data = _get_json(
            f"{GAMMA_BASE}/events",
            {
                "id": chunk,
                "related_tags": "true",
                "limit": 100,
            },
        )
        if not isinstance(data, list):
            return result, False
        for event in data:
            if not isinstance(event, dict):
                continue
            event_id = _registry_id(event.get("id"))
            if event_id in chunk:
                result[event_id] = event
    return result, True


def _with_sport_classification(
    item: Dict[str, Any],
    classification: str,
    reason: str,
    resolved_event_id: Optional[str] = None,
) -> Dict[str, Any]:
    enriched = dict(item)
    enriched["_sport_classification"] = classification
    enriched["_sport_reason"] = reason
    if resolved_event_id:
        enriched["_sport_resolved_event_id"] = resolved_event_id
    return enriched


def _classify_football_items(
    items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Three-state football gate with conservative negative proof.

    Positive Soccer proof wins immediately. A condition is only called
    VERIFIED_NON_FOOTBALL when its direct Gamma market exists, its parent event
    is resolved, and BOTH the condition and that parent event are absent from
    successful Soccer-tag queries. Missing IDs, lookup failures, conflicting
    parent identities and incomplete metadata become UNCERTAIN instead.
    """
    if not items:
        return {
            "verified_football": [],
            "verified_non_football": [],
            "uncertain": [],
            "verification_complete": True,
        }

    condition_ids = sorted({
        _registry_id(item.get("conditionId") or item.get("condition_id"))
        for item in items
        if _registry_id(item.get("conditionId") or item.get("condition_id"))
    })
    explicit_event_ids = sorted({
        _registry_id(item.get("eventId") or item.get("event_id"))
        for item in items
        if _registry_id(item.get("eventId") or item.get("event_id"))
    })

    persisted_conditions = _load_persisted_sport_registry(
        "condition",
        condition_ids,
    )
    persisted_parent_event_ids = sorted({
        _registry_id(row.get("event_id"))
        for row in persisted_conditions.values()
        if _registry_id(row.get("event_id"))
    })
    persisted_events = _load_persisted_sport_registry(
        "event",
        sorted(set(explicit_event_ids) | set(persisted_parent_event_ids)),
    )

    unresolved_conditions = [
        cid for cid in condition_ids
        if not _persisted_classification_is_trusted(
            persisted_conditions.get(cid)
        )
    ]
    unresolved_events = [
        eid for eid in sorted(set(explicit_event_ids) | set(persisted_parent_event_ids))
        if not _persisted_classification_is_trusted(
            persisted_events.get(eid)
        )
    ]

    verified_conditions, conditions_soccer_ok = _verified_soccer_condition_ids(
        unresolved_conditions,
    )
    negative_candidate_conditions = [
        cid for cid in unresolved_conditions
        if cid not in verified_conditions
    ]
    direct_markets, direct_markets_ok = _fetch_direct_gamma_markets(
        negative_candidate_conditions,
    )

    inferred_event_ids: set = set()
    parent_by_condition: Dict[str, Optional[str]] = {}
    for cid, market in direct_markets.items():
        parents = _market_parent_event_ids(market)
        parent_by_condition[cid] = parents[0] if len(parents) == 1 else None
        inferred_event_ids.update(parents)

    all_event_ids = sorted(set(unresolved_events) | inferred_event_ids)
    verified_events, events_soccer_ok = _verified_soccer_event_ids(all_event_ids)
    negative_candidate_events = [
        event_id for event_id in all_event_ids
        if event_id not in verified_events
    ]
    direct_events, direct_events_ok = _fetch_direct_gamma_events(
        negative_candidate_events,
    )

    football: List[Dict[str, Any]] = []
    non_football: List[Dict[str, Any]] = []
    uncertain: List[Dict[str, Any]] = []
    registry_records: List[Dict[str, Any]] = []

    for item in items:
        cid = _registry_id(item.get("conditionId") or item.get("condition_id"))
        explicit_eid = _registry_id(item.get("eventId") or item.get("event_id"))

        persisted_condition_row = persisted_conditions.get(cid) if cid else None
        persisted_condition_class = (
            persisted_condition_row.get("classification")
            if _persisted_classification_is_trusted(persisted_condition_row)
            else None
        )
        persisted_parent_eid = _registry_id(
            persisted_condition_row.get("event_id")
        ) if persisted_condition_row else ""
        persisted_effective_eid = explicit_eid or persisted_parent_eid
        persisted_event_row = (
            persisted_events.get(persisted_effective_eid)
            if persisted_effective_eid else None
        )
        persisted_event_class = (
            persisted_event_row.get("classification")
            if _persisted_classification_is_trusted(persisted_event_row)
            else None
        )

        if (
            persisted_condition_class == FOOTBALL_CLASS_VERIFIED
            or persisted_event_class == FOOTBALL_CLASS_VERIFIED
        ):
            resolved_eid = persisted_effective_eid or None
            football.append(_with_sport_classification(
                item,
                FOOTBALL_CLASS_VERIFIED,
                "persisted_verified_soccer",
                resolved_eid,
            ))
            continue

        if (
            persisted_condition_class == FOOTBALL_CLASS_NON_FOOTBALL
            or (
                not cid
                and persisted_event_class == FOOTBALL_CLASS_NON_FOOTBALL
            )
        ):
            non_football.append(_with_sport_classification(
                item,
                FOOTBALL_CLASS_NON_FOOTBALL,
                "persisted_verified_non_football",
                explicit_eid or None,
            ))
            continue

        market = direct_markets.get(cid) if cid else None
        parents = _market_parent_event_ids(market) if market else []
        parent_eid = parents[0] if len(parents) == 1 else None

        # Explicit event identity and direct market parent must agree. A
        # mismatch is evidence corruption/ambiguity, never a negative verdict.
        if explicit_eid and parent_eid and explicit_eid != parent_eid:
            uncertain.append(_with_sport_classification(
                item,
                FOOTBALL_CLASS_UNCERTAIN,
                "conflicting_event_identity",
                explicit_eid,
            ))
            continue

        resolved_eid = explicit_eid or parent_eid

        direct_event = direct_events.get(resolved_eid) if resolved_eid else None
        direct_soccer_tag = (
            _gamma_object_has_soccer_tag(market)
            or _gamma_object_has_soccer_tag(direct_event)
        )

        if (
            (cid and cid in verified_conditions)
            or (resolved_eid and resolved_eid in verified_events)
            or direct_soccer_tag
        ):
            football.append(_with_sport_classification(
                item,
                FOOTBALL_CLASS_VERIFIED,
                "gamma_soccer_registry",
                resolved_eid,
            ))
            if cid:
                registry_records.append({
                    "identity_type": "condition",
                    "identity_id": cid,
                    "event_id": resolved_eid,
                    "classification": FOOTBALL_CLASS_VERIFIED,
                    "source": "gamma_soccer_registry",
                    "evidence": {"condition_soccer": cid in verified_conditions},
                })
            if resolved_eid:
                registry_records.append({
                    "identity_type": "event",
                    "identity_id": resolved_eid,
                    "event_id": resolved_eid,
                    "classification": FOOTBALL_CLASS_VERIFIED,
                    "source": "gamma_soccer_registry",
                    "evidence": {"event_soccer": resolved_eid in verified_events},
                })
            continue

        if not cid and not resolved_eid:
            uncertain.append(_with_sport_classification(
                item,
                FOOTBALL_CLASS_UNCERTAIN,
                "missing_gamma_identity",
            ))
            continue

        # Conservative NON_FOOTBALL proof for a market/condition:
        #  1) soccer-filtered condition query completed and omitted it,
        #  2) unfiltered condition lookup resolved the exact market,
        #  3) exactly one parent event was resolved,
        #  4) unfiltered parent event lookup resolved,
        #  5) soccer-filtered parent event query completed and omitted it.
        condition_negative_proven = bool(
            cid
            and conditions_soccer_ok
            and direct_markets_ok
            and market is not None
            and parent_eid
            and direct_events_ok
            and parent_eid in direct_events
            and events_soccer_ok
            and parent_eid not in verified_events
            and cid not in verified_conditions
            and _gamma_object_has_explicit_non_soccer_tags(
                direct_events.get(parent_eid)
            )
        )

        # Event-only rows require both a direct event lookup and a successful
        # Soccer-tag event query before they can be rejected.
        event_negative_proven = bool(
            not cid
            and resolved_eid
            and direct_events_ok
            and resolved_eid in direct_events
            and events_soccer_ok
            and resolved_eid not in verified_events
            and _gamma_object_has_explicit_non_soccer_tags(
                direct_events.get(resolved_eid)
            )
        )

        if condition_negative_proven or event_negative_proven:
            non_football.append(_with_sport_classification(
                item,
                FOOTBALL_CLASS_NON_FOOTBALL,
                "gamma_double_negative",
                resolved_eid,
            ))
            if cid:
                registry_records.append({
                    "identity_type": "condition",
                    "identity_id": cid,
                    "event_id": resolved_eid,
                    "classification": FOOTBALL_CLASS_NON_FOOTBALL,
                    "source": "gamma_double_negative",
                    "evidence": {
                        "direct_market": True,
                        "condition_soccer": False,
                        "direct_parent_event": True,
                        "parent_event_soccer": False,
                    },
                })
            if resolved_eid:
                registry_records.append({
                    "identity_type": "event",
                    "identity_id": resolved_eid,
                    "event_id": resolved_eid,
                    "classification": FOOTBALL_CLASS_NON_FOOTBALL,
                    "source": "gamma_double_negative",
                    "evidence": {
                        "direct_event": True,
                        "event_soccer": False,
                    },
                })
            continue

        reason = "gamma_lookup_incomplete"
        if cid and market is None and direct_markets_ok:
            reason = "condition_not_resolved"
        elif cid and market is not None and len(parents) != 1:
            reason = "parent_event_ambiguous"
        elif resolved_eid and direct_events_ok and resolved_eid not in direct_events:
            reason = "event_not_resolved"
        elif resolved_eid and not _gamma_tag_rows(direct_events.get(resolved_eid)):
            reason = "event_tags_missing"

        uncertain.append(_with_sport_classification(
            item,
            FOOTBALL_CLASS_UNCERTAIN,
            reason,
            resolved_eid,
        ))
        if cid:
            registry_records.append({
                "identity_type": "condition",
                "identity_id": cid,
                "event_id": resolved_eid,
                "classification": FOOTBALL_CLASS_UNCERTAIN,
                "source": reason,
                "evidence": {},
            })

    _persist_sport_registry_records(registry_records)
    return {
        "verified_football": football,
        "verified_non_football": non_football,
        "uncertain": uncertain,
        "verification_complete": not uncertain,
    }


def _filter_verified_football_items(
    items: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], bool]:
    """Compatibility wrapper around the conservative three-state V2 gate."""
    classified = _classify_football_items(items)
    return (
        classified["verified_football"],
        bool(classified["verification_complete"]),
    )


# Title suffix (after the first ':') -> our internal market_type key, mirroring
# _EXTRA_MARKET_TYPES but keyed off the human title text /activity returns
# instead of a market's groupItemTitle.
_ACTIVITY_MARKET_SUFFIX_TYPES = {
    "o/u 2.5": "ou25",
    "both teams to score": "btts",
}


def _parse_activity_market(item: Dict[str, Any]):
    """Return (market_type, home, away, selection, side) for an /activity or
    /positions row, reusing the same display conventions as the match-page
    trade ledger (_market_selection_side / _bet_display_fields).

    `home`/`away` are always populated (never blank) so the UI's Match
    column has something useful to show even for one-off prop markets that
    don't follow the "Team A vs. Team B[: suffix]" title shape (e.g.
    "Spread: France (-1.5)") - those fall back to decoding the event slug's
    country codes, and as a last resort show the raw title."""
    title = item.get("title") or ""
    slug = item.get("slug") or item.get("eventSlug") or ""
    outcome_raw = (item.get("outcome") or "").strip()
    has_suffix = ":" in title
    if has_suffix:
        base_title, suffix = title.split(":", 1)
        market_type = _ACTIVITY_MARKET_SUFFIX_TYPES.get(suffix.strip().lower())
    else:
        base_title, suffix = title, ""
        market_type = None

    parsed = _parse_match_title(base_title.strip())
    is_standard_title = parsed is not None
    home, away = parsed if parsed else (None, None)

    if home is None:
        slug_teams = _parse_slug_teams(slug)
        if slug_teams:
            home, away = slug_teams
            if not _slug_codes_known(slug):
                # The slug's embedded codes aren't in _FIFA_COUNTRY_CODES
                # (most likely a domestic club match, e.g. Moroccan Botola
                # Pro), so `home`/`away` above are raw abbreviations (e.g.
                # "FUS", "UYE"). Try to upgrade to real team names from our
                # own scraper-populated Supabase table first, and fall back
                # to extracting the known side's name from a one-sided
                # "Will X win ...?" title if the match isn't tracked there.
                stored = _lookup_stored_match_by_slug(slug)
                if stored:
                    home, away = stored
                else:
                    will_win_name = _parse_will_win_title(title)
                    if will_win_name:
                        home, away = will_win_name, ""

    if market_type is None:
        # A recognized suffix (e.g. "O/U 2.5") maps to ou25/btts above. Any
        # OTHER suffix (e.g. "O/U 3.5", "Spread (-1.5)") is still a specific,
        # non-1x2 sub-market even though the base title parses as "Team A vs.
        # Team B" - it must never silently fall back to the generic 1x2
        # branch (that used to swallow the handicap/line info entirely).
        if has_suffix:
            market_type = "special"
        else:
            market_type = "1x2" if is_standard_title else "special"

    if market_type in ("ou25", "btts"):
        fields = _bet_display_fields(market_type, "", outcome_raw)
        selection = fields["selection"]
        side = fields["side"]
    elif market_type == "1x2" and is_standard_title:
        selection = outcome_raw or "-"
        side = None
    else:
        # Non-standard one-off market (e.g. spread/handicap props, unusual
        # O/U lines) - Polymarket's own title suffix already carries the
        # specific bet (team + line, e.g. "France (-1.5)" or "O/U 3.5").
        # Use that (cleaned up) as the selection, and the actual outcome the
        # wallet traded (e.g. "Sweden", "Under") as the side, instead of
        # collapsing everything into the raw title string.
        market_type = "special"
        suffix_clean = suffix.strip()
        # "France (-1.5)" -> "France -1.5" (drop the redundant parens)
        suffix_clean = re.sub(r'\(([-+]?\d+(?:\.\d+)?)\)', r'\1', suffix_clean).strip()
        selection = suffix_clean or title.strip() or outcome_raw or "-"
        side = outcome_raw or None

    if home is None:
        home = base_title.strip() or title.strip() or "-"
        away = ""

    return market_type, home, away, selection, side


def _wallet_bet_display_contract(item: Dict[str, Any]) -> Dict[str, str]:
    """Return one stable market/selection contract for tracked-wallet bets.

    The frontend renders these labels directly instead of re-interpreting
    Polymarket title/outcome strings. Existing selection/side fields remain
    available for compatibility.
    """
    market_type = str(item.get("market_type") or "").strip().lower()
    selection_raw = str(item.get("selection") or "").strip()
    side_raw = str(item.get("side") or "").strip()
    outcome_raw = str(item.get("outcome_raw") or item.get("outcome") or "").strip()
    title = str(item.get("title") or "").strip()

    if not market_type:
        parsed_type, _home, _away, parsed_selection, parsed_side = _parse_activity_market({
            "title": title,
            "slug": item.get("slug"),
            "eventSlug": item.get("eventSlug"),
            "outcome": outcome_raw,
        })
        market_type = parsed_type
        if not selection_raw:
            selection_raw = str(parsed_selection or "").strip()
        if not side_raw:
            side_raw = str(parsed_side or "").strip()

    if side_raw.upper() in ("BUY", "SELL"):
        side_raw = ""

    def _choice(value: str) -> str:
        raw = str(value or "").strip()
        low = raw.lower()
        return {
            "draw": "Beraberlik",
            "yes": "Evet",
            "no": "Hayır",
            "over": "Üst",
            "under": "Alt",
            "kg var": "Var",
            "kg yok": "Yok",
            "btts yes": "Var",
            "btts no": "Yok",
        }.get(low, raw)

    mt = market_type or "special"
    market_label = _MARKET_TYPE_LABELS.get(mt, "Özel Market")
    selection_label = ""
    side_label = ""

    if mt == "ou25":
        market_label = "Toplam Gol 2.5"
        source = outcome_raw or side_raw or selection_raw
        low = source.lower()
        if low in ("over", "2.5 üst", "üst"):
            selection_label = "Üst"
        elif low in ("under", "2.5 alt", "alt"):
            selection_label = "Alt"
        else:
            selection_label = _choice(source) or "-"

    elif mt == "btts":
        market_label = "Karşılıklı Gol"
        source = outcome_raw or side_raw or selection_raw
        low = source.lower()
        if low in ("yes", "kg var", "var"):
            selection_label = "Var"
        elif low in ("no", "kg yok", "yok"):
            selection_label = "Yok"
        else:
            selection_label = _choice(source) or "-"

    elif mt == "1x2":
        market_label = "1X2"
        candidate = selection_raw or outcome_raw or side_raw
        selection_label = _choice(candidate) or "-"
        polarity = _choice(outcome_raw)
        if outcome_raw.lower() in ("yes", "no") and polarity != selection_label:
            side_label = polarity
        elif side_raw and _choice(side_raw) != selection_label:
            side_label = _choice(side_raw)

    else:
        suffix = title.split(":", 1)[1].strip() if ":" in title else selection_raw
        suffix_clean = re.sub(r'\(([-+]?\d+(?:\.\d+)?)\)', r'\1', suffix or "").strip()
        total_match = re.search(
            r'(?:o/u|over\s*/\s*under|total(?:\s+goals?)?)\s*([0-9]+(?:\.[0-9]+)?)',
            suffix_clean,
            re.IGNORECASE,
        )
        handicap_like = bool(
            re.search(r'\b(?:spread|handicap)\b', suffix_clean, re.IGNORECASE)
            or re.search(r'[-+]\d+(?:\.\d+)?', suffix_clean)
        )

        if total_match:
            line = total_match.group(1)
            market_label = f"Toplam Gol {line}"
            source = outcome_raw or side_raw
            low = source.lower()
            if low in ("over", "üst"):
                selection_label = "Üst"
            elif low in ("under", "alt"):
                selection_label = "Alt"
            else:
                selection_label = _choice(source or selection_raw) or "-"
        elif handicap_like:
            market_label = "Handikap"
            selection_label = selection_raw or suffix_clean or _choice(outcome_raw) or "-"
            normalized_outcome = _choice(outcome_raw)
            if normalized_outcome and normalized_outcome != selection_label:
                side_label = normalized_outcome
        else:
            market_label = suffix_clean or _MARKET_TYPE_LABELS["special"]
            selection_label = _choice(outcome_raw or side_raw or selection_raw) or "-"
            if selection_raw and _choice(selection_raw) != selection_label and not suffix_clean:
                market_label = _choice(selection_raw)

    bet_label = selection_label
    if side_label and side_label != selection_label:
        bet_label = f"{selection_label} · {side_label}"

    return {
        "market_type": mt,
        "market_label": market_label,
        "selection_label": selection_label or "-",
        "side_label": side_label,
        "bet_label": bet_label or "-",
    }


def _with_wallet_bet_display_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    enriched = _with_canonical_match_metadata(item)
    enriched.update(_wallet_bet_display_contract(enriched))
    return enriched


def fetch_wallet_activity(
    wallet: str,
    since_ts: Optional[int] = None,
    max_pages: Optional[int] = None,
    classification_details: bool = False,
):
    """Fully/incrementally paginate the Data API /activity endpoint for a single
    wallet, filtered server-side to TRADE-type entries and client-side to
    markets verified by Gamma's Soccer tag registry. Returns (rows, truncated) - `truncated=True` means the
    page cap was hit before reaching `since_ts`, so the caller should skip
    storing this batch and retry the full range next cycle (same contract as
    _fetch_new_trades) to avoid a permanent gap.
    """
    if not wallet:
        return [], False
    if max_pages is None:
        max_pages = _ACTIVITY_INCREMENTAL_MAX_PAGES if since_ts is not None else _ACTIVITY_MAX_PAGES

    rows: List[Dict[str, Any]] = []
    offset = 0
    hit_page_cap = True
    for _ in range(max_pages):
        try:
            page = _get_json(f"{DATA_BASE}/activity", {
                "user": wallet,
                "type": "TRADE",
                "limit": _ACTIVITY_PAGE_LIMIT,
                "offset": offset,
            })
        except _OffsetLimitExceeded:
            # Polymarket's hard historical-offset cap was hit. Deeper history
            # is permanently unreachable via this endpoint, so whatever we've
            # accumulated so far IS the complete backfill - not a gap to
            # retry later.
            hit_page_cap = False
            break
        if page is None:
            return rows, True
        if not page:
            hit_page_cap = False
            break

        reached_checkpoint = False
        for item in page:
            ts = item.get("timestamp")
            if since_ts is not None and ts is not None and int(ts) < since_ts:
                reached_checkpoint = True
                break
            rows.append(item)

        if reached_checkpoint:
            hit_page_cap = False
            break
        if len(page) < _ACTIVITY_PAGE_LIMIT:
            hit_page_cap = False
            break
        offset += _ACTIVITY_PAGE_LIMIT
    else:
        hit_page_cap = since_ts is not None

    truncated = since_ts is not None and hit_page_cap
    if truncated:
        if classification_details:
            return rows, True, [], []
        return rows, True

    classified = _classify_football_items(rows)
    football_rows = classified["verified_football"]
    uncertain_rows = classified["uncertain"]
    non_football_rows = classified["verified_non_football"]
    if classification_details:
        return football_rows, False, uncertain_rows, non_football_rows
    if uncertain_rows:
        return [], True
    return football_rows, False


def fetch_wallet_redeems(
    wallet: str,
    since_ts: Optional[int] = None,
    max_pages: Optional[int] = None,
    classification_details: bool = False,
):
    """Fully/incrementally paginate the Data API /activity endpoint for a
    single wallet, filtered server-side to REDEEM-type entries (a wallet
    cashing out a resolved/winning position) and client-side to football
    markets verified by Gamma's Soccer tag registry. This is what makes win-rate durable: once a wallet redeems a
    winning position it disappears from /positions forever, so the win must
    be recorded here at redeem-time or it becomes permanently invisible
    (Task #264). Same (rows, truncated) contract as fetch_wallet_activity."""
    if not wallet:
        return [], False
    if max_pages is None:
        max_pages = _ACTIVITY_INCREMENTAL_MAX_PAGES if since_ts is not None else _ACTIVITY_MAX_PAGES

    rows: List[Dict[str, Any]] = []
    offset = 0
    hit_page_cap = True
    for _ in range(max_pages):
        try:
            page = _get_json(f"{DATA_BASE}/activity", {
                "user": wallet,
                "type": "REDEEM",
                "limit": _ACTIVITY_PAGE_LIMIT,
                "offset": offset,
            })
        except _OffsetLimitExceeded:
            hit_page_cap = False
            break
        if page is None:
            return rows, True
        if not page:
            hit_page_cap = False
            break

        reached_checkpoint = False
        for item in page:
            ts = item.get("timestamp")
            if since_ts is not None and ts is not None and int(ts) < since_ts:
                reached_checkpoint = True
                break
            if item.get("conditionId"):
                rows.append(item)

        if reached_checkpoint:
            hit_page_cap = False
            break
        if len(page) < _ACTIVITY_PAGE_LIMIT:
            hit_page_cap = False
            break
        offset += _ACTIVITY_PAGE_LIMIT
    else:
        hit_page_cap = since_ts is not None

    truncated = since_ts is not None and hit_page_cap
    if truncated:
        if classification_details:
            return rows, True, [], []
        return rows, True

    classified = _classify_football_items(rows)
    football_rows = classified["verified_football"]
    uncertain_rows = classified["uncertain"]
    non_football_rows = classified["verified_non_football"]
    if classification_details:
        return football_rows, False, uncertain_rows, non_football_rows
    if uncertain_rows:
        return [], True
    return football_rows, False


def fetch_wallet_positions(
    wallet: str,
    classification_details: bool = False,
):
    """Fetch ALL current positions (open + unredeemed-resolved) for a wallet via
    the Data API /positions endpoint, then strictly verified against Gamma's Soccer registry.

    Returns (rows, ok). `ok=False` means the API call itself failed (network
    error / non-200), as opposed to the wallet genuinely having zero
    positions right now. Callers must NOT treat ok=False the same as "wallet
    has no positions" - doing so would wipe a valid stored snapshot on a
    transient API hiccup.
    """
    if not wallet:
        return [], True
    rows: List[Dict[str, Any]] = []
    offset = 0
    for _ in range(_POSITIONS_MAX_PAGES):
        page = _get_json(f"{DATA_BASE}/positions", {
            "user": wallet,
            "limit": _POSITIONS_PAGE_LIMIT,
            "offset": offset,
        })
        if page is None:
            return rows, False
        if not page:
            break
        rows.extend(page)
        if len(page) < _POSITIONS_PAGE_LIMIT:
            break
        offset += _POSITIONS_PAGE_LIMIT

    classified = _classify_football_items(rows)
    football_rows = classified["verified_football"]
    uncertain_rows = classified["uncertain"]
    non_football_rows = classified["verified_non_football"]
    if classification_details:
        return football_rows, not uncertain_rows, uncertain_rows, non_football_rows
    if uncertain_rows:
        return [], False
    return football_rows, True


# ---- Supabase CRUD: tracked_wallets / tracked_wallet_activity / tracked_wallet_positions ----

def _parse_wallet_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _filter_wallet_rows_since(
    rows: List[Dict[str, Any]],
    tracked_since: Optional[str],
    date_field: str = "traded_at",
) -> List[Dict[str, Any]]:
    """Keep only records observed after the wallet entered the watch list.

    `tracked_wallets.created_at` is the durable tracking boundary. Filtering
    at read time protects profiles and list stats even when an older backfill
    is still present in the database.
    """
    if not tracked_since:
        return rows
    boundary = _parse_wallet_datetime(tracked_since)
    if boundary is None:
        return rows
    return [
        row for row in rows
        if (row_dt := _parse_wallet_datetime(row.get(date_field))) is not None
        and row_dt >= boundary
    ]


def _filter_tracked_wallet_activity_amount(
    rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Keep raw fills whose canonical position has >= the tracked minimum.

    Qualification is based on total ENTRY stake for one canonical outcome
    position (sum of BUY fills). SELL proceeds are exits, not investment, and
    cannot make an otherwise-small position qualify. Once a position qualifies,
    all of its raw fills are retained for result/display/accounting continuity.
    """
    if not rows:
        return []

    grouped = _group_activity_into_canonical_bets(rows)
    qualifying_keys = {
        bet.get("bet_key")
        for bet in grouped
        if float(bet.get("stake_usdc") or 0) >= MIN_TRACKED_WALLET_TRADE_AMOUNT_USDC
    }
    if not qualifying_keys:
        return []

    qualifying = []
    for idx, row in enumerate(rows):
        key = _canonical_bet_identity(row)
        if key is None:
            key = ("unidentified-fill", idx)
        if key in qualifying_keys:
            qualifying.append(row)
    return qualifying


def _canonical_bet_identity(row: Dict[str, Any]) -> Optional[Tuple[Any, ...]]:
    """Return the stable position identity used for bettor-level bet counts.

    A Polymarket outcome token (asset) is the strongest identity because YES
    and NO under the same condition have different assets. Legacy rows that
    predate reliable asset storage fall back to condition + market/selection
    metadata so repeated fills of the same outcome still collapse without
    merging opposite outcomes.
    """
    wallet = str(row.get("wallet") or "").strip().lower() or None

    asset = str(row.get("asset") or "").strip()
    if asset:
        return ("asset", wallet, asset)

    condition_id = str(row.get("condition_id") or "").strip()
    market_type = _normalize(str(row.get("market_type") or ""))
    selection = _normalize(str(row.get("selection") or ""))

    raw_outcome = row.get("outcome_raw")
    if not raw_outcome:
        legacy_side = str(row.get("side") or "").strip()
        if legacy_side.upper() not in ("BUY", "SELL"):
            raw_outcome = legacy_side
    outcome = _normalize(str(raw_outcome or ""))

    if condition_id and (market_type or selection or outcome):
        return ("condition", wallet, condition_id, market_type, selection, outcome)

    # If a legacy row has a condition but no outcome identity at all, do not
    # collapse every token under that condition into one false "bet".
    tx_hash = str(row.get("transaction_hash") or "").strip()
    traded_at = str(row.get("traded_at") or "").strip()
    if condition_id:
        return ("condition-unknown", wallet, condition_id, tx_hash or traded_at)

    market_hint = _normalize(str(row.get("slug") or row.get("title") or ""))
    if market_hint or selection or outcome:
        return ("legacy", wallet, market_hint, market_type, selection, outcome)

    if tx_hash:
        return ("tx", wallet, tx_hash)
    return None


def _canonical_bet_key_text(identity: Optional[Tuple[Any, ...]]) -> Optional[str]:
    """Serialize one canonical bet identity into a deterministic DB text key."""
    if identity is None:
        return None
    return json.dumps(
        list(identity),
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def _tracked_wallet_activity_action(row: Dict[str, Any]) -> str:
    """Normalize raw Polymarket direction for stake accounting.

    Current rows store BUY/SELL in `action`. Older 1x2 rows may carry that
    value in `side`, so accept it only when it is literally BUY or SELL.
    """
    action = str(row.get("action") or "").strip().upper()
    if action in ("BUY", "SELL"):
        return action
    legacy_side = str(row.get("side") or "").strip().upper()
    if legacy_side in ("BUY", "SELL"):
        return legacy_side
    return "UNKNOWN"


def _group_activity_into_canonical_bets(
    activity_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Collapse qualifying fills into one bettor bet/position per outcome.

    BUY fills establish stake/cost basis. SELL fills are exits and therefore
    never add to investment. Completely action-less legacy positions retain a
    conservative stake fallback so old tracked history is not silently erased.
    """
    grouped: Dict[Tuple[Any, ...], Dict[str, Any]] = {}

    for idx, row in enumerate(activity_rows):
        key = _canonical_bet_identity(row)
        if key is None:
            key = ("unidentified-fill", idx)

        group = grouped.get(key)
        if group is None:
            group = {
                "bet_key": key,
                "wallet": row.get("wallet"),
                "condition_id": row.get("condition_id"),
                "asset": row.get("asset"),
                "market_type": row.get("market_type"),
                "selection": row.get("selection"),
                "side": row.get("side"),
                "outcome_raw": row.get("outcome_raw"),
                "fill_count": 0,
                "gross_fill_volume_usdc": 0.0,
                "buy_fill_count": 0,
                "sell_fill_count": 0,
                "unknown_fill_count": 0,
                "buy_stake_usdc": 0.0,
                "sell_proceeds_usdc": 0.0,
                "unknown_volume_usdc": 0.0,
                "_buy_shares": 0.0,
                "_unknown_shares": 0.0,
                "_buy_price_amount_weight_sum": 0.0,
                "_unknown_price_amount_weight_sum": 0.0,
                "_stored_results": set(),
            }
            grouped[key] = group

        try:
            row_fill_count = int(row.get("fill_count") or 1)
        except (TypeError, ValueError):
            row_fill_count = 1
        row_fill_count = max(row_fill_count, 1)

        try:
            amount = float(row.get("amount_usdc") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        try:
            price = float(row.get("price") or 0)
        except (TypeError, ValueError):
            price = 0.0
        try:
            size = float(row.get("size") or 0)
        except (TypeError, ValueError):
            size = 0.0

        # Data API size = outcome shares. If a legacy row lacks size but has
        # amount+price, amount/price reconstructs the share count.
        effective_shares = size if size > 0 else (amount / price if amount > 0 and price > 0 else 0.0)

        group["fill_count"] += row_fill_count
        group["gross_fill_volume_usdc"] += amount
        if row.get("result") in ("won", "lost"):
            group["_stored_results"].add(row["result"])

        action = _tracked_wallet_activity_action(row)
        if action == "BUY":
            group["buy_fill_count"] += row_fill_count
            group["buy_stake_usdc"] += amount
            group["_buy_shares"] += effective_shares
            group["_buy_price_amount_weight_sum"] += price * amount
        elif action == "SELL":
            group["sell_fill_count"] += row_fill_count
            group["sell_proceeds_usdc"] += amount
        else:
            group["unknown_fill_count"] += row_fill_count
            group["unknown_volume_usdc"] += amount
            group["_unknown_shares"] += effective_shares
            group["_unknown_price_amount_weight_sum"] += price * amount

    for group in grouped.values():
        group["gross_fill_volume_usdc"] = round(group["gross_fill_volume_usdc"], 2)
        group["buy_stake_usdc"] = round(group["buy_stake_usdc"], 2)
        group["sell_proceeds_usdc"] = round(group["sell_proceeds_usdc"], 2)
        group["unknown_volume_usdc"] = round(group["unknown_volume_usdc"], 2)

        if group["buy_fill_count"] > 0:
            stake = group["buy_stake_usdc"]
            shares = group["_buy_shares"]
            fallback_weight = group["_buy_price_amount_weight_sum"]
            stake_source = "buy"
        elif group["sell_fill_count"] == 0 and group["unknown_fill_count"] > 0:
            # Fully legacy position: preserve historical stake semantics.
            stake = group["unknown_volume_usdc"]
            shares = group["_unknown_shares"]
            fallback_weight = group["_unknown_price_amount_weight_sum"]
            stake_source = "legacy_unknown"
        else:
            # SELL-only activity is an exit from a position opened before our
            # tracked window; it is not a new bettor bet/investment.
            stake = 0.0
            shares = 0.0
            fallback_weight = 0.0
            stake_source = "none"

        if stake > 0 and shares > 0:
            avg_entry_price = stake / shares
        elif stake > 0:
            avg_entry_price = fallback_weight / stake
        else:
            avg_entry_price = 0.0

        stored_results = group.pop("_stored_results", set())
        if stored_results == {"won"}:
            stored_result = "won"
        elif stored_results == {"lost"}:
            stored_result = "lost"
        else:
            stored_result = None

        group["stake_usdc"] = round(stake, 2)
        group["avg_entry_price"] = round(avg_entry_price, 6)
        group["stake_source"] = stake_source
        group["stored_result"] = stored_result

        group.pop("_buy_shares", None)
        group.pop("_unknown_shares", None)
        group.pop("_buy_price_amount_weight_sum", None)
        group.pop("_unknown_price_amount_weight_sum", None)

    return list(grouped.values())


def _filter_wallet_redeems_to_activity(
    redeem_rows: List[Dict[str, Any]],
    activity_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Ignore payouts belonging only to hidden, sub-threshold fills."""
    assets = {row.get("asset") for row in activity_rows if row.get("asset")}
    conditions = {
        row.get("condition_id")
        for row in activity_rows
        if row.get("condition_id")
    }
    return [
        row for row in redeem_rows
        if (row.get("asset") and row.get("asset") in assets)
        or (
            not row.get("asset")
            and row.get("condition_id") in conditions
        )
    ]


def _get_wallet_tracking_start(
    base: str,
    headers: Dict[str, str],
    wallet: str,
) -> Optional[str]:
    try:
        response = requests.get(
            f"{base}/rest/v1/tracked_wallets",
            headers=headers,
            params={
                "select": "created_at",
                "wallet": f"eq.{wallet.lower()}",
                "limit": 1,
            },
            timeout=10,
        )
        if response.status_code != 200:
            return None
        rows = response.json()
        return rows[0].get("created_at") if rows else None
    except Exception:
        return None


def _fetch_wallet_stat_summary(base: str, headers: Dict[str, str], wallet: str, tracked_since: Optional[str] = None) -> Dict[str, Any]:
    """Lightweight per-wallet stats for the tracked-wallets LIST view.
    Uses only data observed after tracking started."""
    try:
        r = requests.get(f"{base}/rest/v1/tracked_wallet_activity", headers=headers, params={
            "select": "asset,condition_id,result,market_type,selection,side,action,outcome_raw,amount_usdc,price,size,traded_at",
            "wallet": f"eq.{wallet}",
            "limit": 2000,
        }, timeout=15)
        activity_rows = r.json() if r.status_code == 200 else []
    except Exception:
        activity_rows = []

    try:
        r = requests.get(
            f"{base}/rest/v1/tracked_wallet_positions",
            headers=headers,
            params={
                "select": "condition_id,asset,cur_price,current_value,cash_pnl,redeemable",
                "wallet": f"eq.{wallet}",
                "limit": 500,
            },
            timeout=15,
        )
        position_rows = r.json() if r.status_code == 200 else []
    except Exception:
        position_rows = []

    try:
        r = requests.get(f"{base}/rest/v1/tracked_wallet_redeems", headers=headers, params={
            "select": "condition_id,asset,amount_usdc,traded_at",
            "wallet": f"eq.{wallet}",
            "limit": 2000,
        }, timeout=15)
        redeem_rows = r.json() if r.status_code == 200 else []
    except Exception:
        redeem_rows = []

    activity_rows = _filter_wallet_rows_since(activity_rows, tracked_since)
    activity_rows, football_registry_ok = _filter_verified_football_items(activity_rows)
    if not football_registry_ok:
        activity_rows = []
    activity_rows = _filter_tracked_wallet_activity_amount(activity_rows)
    redeem_rows = _filter_wallet_rows_since(redeem_rows, tracked_since)
    redeem_rows = _filter_wallet_redeems_to_activity(redeem_rows, activity_rows)
    position_rows = _filter_positions_since_tracking(position_rows, activity_rows)
    resolved = _compute_wallet_activity_stats(activity_rows, position_rows, redeem_rows)
    return {
        "win_rate_pct": resolved["win_rate"],
        "resolved_won": resolved["resolved_won"],
        "resolved_lost": resolved["resolved_lost"],
        "resolved_total": resolved["resolved_total"],
        "trade_count": resolved["trade_count"],
        "open_position_count": len(resolved["open_positions"]),
    }


def list_tracked_wallets() -> List[Dict[str, Any]]:
    """Bare wallet list (wallet, nickname, notes, created_at) - used by the
    scraper's own sync loop, which only needs the address to process. No
    per-wallet stat queries here so the 5-min scrape cycle stays cheap."""
    base = _supabase_base_url()
    if not base:
        return []
    try:
        r = requests.get(
            f"{base}/rest/v1/tracked_wallets",
            headers=_supabase_headers(),
            params={"select": "wallet,nickname,notes,created_at", "order": "created_at.desc"},
            timeout=10,
        )
        if r.status_code != 200:
            return []
        return r.json()
    except Exception as e:
        print(f"[TrackedWallets] list hatasi: {e}")
        return []


def _get_wallet_stat_baseline(
    base: str,
    headers: Dict[str, str],
    wallet: str,
) -> Dict[str, Any]:
    """Read the last durable card/profile snapshot before recalculating it.

    This is the anti-regression floor during normalized-table rollout: a short
    raw retention window must never overwrite a previously larger all-history
    snapshot with smaller recent-only totals.
    """
    try:
        response = requests.get(
            f"{base}/rest/v1/tracked_wallets",
            headers=headers,
            params={
                "select": (
                    "created_at,last_synced_at,win_rate,resolved_won,resolved_lost,"
                    "resolved_total,trade_count,total_invested_usdc,avg_bet_size_usdc,"
                    "avg_price,avg_price_decimal,open_position_count,open_exposure_usdc"
                ),
                "wallet": f"eq.{wallet.lower()}",
                "limit": 1,
            },
            timeout=10,
        )
        if response.status_code != 200:
            return {}
        rows = response.json()
        return rows[0] if isinstance(rows, list) and rows else {}
    except Exception:
        return {}


def _fetch_persisted_wallet_bets_for_stats(
    base: str,
    headers: Dict[str, str],
    wallet: str,
) -> Tuple[List[Dict[str, Any]], bool]:
    """Read the complete durable bet ledger with pagination.

    No fixed 5k/10k history cap is allowed here: this table is the long-term
    bettor record and statistics must continue to cover the full stored span.
    """
    rows: List[Dict[str, Any]] = []
    page_size = 1000
    max_pages = 100
    try:
        for page in range(max_pages):
            response = requests.get(
                f"{base}/rest/v1/tracked_wallet_bets",
                headers=headers,
                params={
                    "select": (
                        "bet_key,stake_usdc,avg_entry_price,result,lifecycle_status,"
                        "fill_count,first_traded_at,last_traded_at,sport_classification"
                    ),
                    "wallet": f"eq.{wallet.lower()}",
                    "sport_classification": f"eq.{FOOTBALL_CLASS_VERIFIED}",
                    "order": "first_traded_at.asc.nullsfirst",
                    "limit": page_size,
                    "offset": page * page_size,
                },
                timeout=20,
            )
            if response.status_code != 200:
                return [], False
            page_rows = response.json()
            if not isinstance(page_rows, list):
                return [], False
            rows.extend(page_rows)
            if len(page_rows) < page_size:
                return rows, True
        logger.warning(
            "[WalletBets] stat pagination safety cap reached for %s (%s rows)",
            wallet[:10],
            len(rows),
        )
        return rows, False
    except Exception:
        return [], False


def _compute_persisted_wallet_bet_stats(
    bet_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compute all-history bettor metrics from durable canonical bet rows."""
    entered: List[Dict[str, Any]] = []
    for row in bet_rows:
        try:
            stake = float(row.get("stake_usdc") or 0)
        except (TypeError, ValueError):
            stake = 0.0
        if stake >= MIN_TRACKED_WALLET_TRADE_AMOUNT_USDC:
            entered.append(row)

    total_invested = sum(float(row.get("stake_usdc") or 0) for row in entered)
    trade_count = len(entered)
    fill_count = sum(int(row.get("fill_count") or 0) for row in entered)

    resolved_won = sum(row.get("result") == "won" for row in entered)
    resolved_lost = sum(row.get("result") == "lost" for row in entered)
    resolved_total = resolved_won + resolved_lost

    weighted_price_sum = 0.0
    for row in entered:
        try:
            price = float(row.get("avg_entry_price") or 0)
            stake = float(row.get("stake_usdc") or 0)
        except (TypeError, ValueError):
            continue
        weighted_price_sum += price * stake

    avg_price = weighted_price_sum / total_invested if total_invested else 0.0
    return {
        "resolved_won": resolved_won,
        "resolved_lost": resolved_lost,
        "resolved_total": resolved_total,
        "win_rate": (
            round((resolved_won / resolved_total) * 100, 1)
            if resolved_total else None
        ),
        "trade_count": trade_count,
        "fill_count": fill_count,
        "total_invested_usdc": round(total_invested, 2),
        "avg_bet_size_usdc": (
            round(total_invested / trade_count, 2)
            if trade_count else 0.0
        ),
        "avg_price": round(avg_price, 4),
        "avg_price_decimal": _to_decimal_odds(avg_price) if avg_price else None,
    }


def _baseline_wallet_history_stats(
    baseline: Dict[str, Any],
    raw_stats: Dict[str, Any],
) -> Dict[str, Any]:
    """Return a compatibility-shaped history snapshot from tracked_wallets."""
    return {
        "resolved_won": int(baseline.get("resolved_won") or 0),
        "resolved_lost": int(baseline.get("resolved_lost") or 0),
        "resolved_total": int(baseline.get("resolved_total") or 0),
        "win_rate": baseline.get("win_rate"),
        "trade_count": int(baseline.get("trade_count") or 0),
        # tracked_wallets does not persist raw fill_count; this value is not
        # user-facing and can safely reflect the current audit window.
        "fill_count": int(raw_stats.get("fill_count") or 0),
        "total_invested_usdc": round(
            float(baseline.get("total_invested_usdc") or 0),
            2,
        ),
        "avg_bet_size_usdc": round(
            float(baseline.get("avg_bet_size_usdc") or 0),
            2,
        ),
        "avg_price": round(float(baseline.get("avg_price") or 0), 4),
        "avg_price_decimal": baseline.get("avg_price_decimal"),
    }


def _fetch_persisted_wallet_bets_for_profile(
    base: str,
    headers: Dict[str, str],
    wallet: str,
) -> Tuple[List[Dict[str, Any]], bool]:
    """Read full normalized profile history; never silently stop at 5k rows."""
    select_fields = (
        "bet_key,asset,condition_id,event_id,match_key,match_name,home,away,"
        "slug,kickoff_utc,title,market_type,market_label,selection,side,"
        "outcome_raw,selection_label,side_label,bet_label,lifecycle_status,"
        "result,status_label,stake_usdc,sell_proceeds_usdc,"
        "redeem_proceeds_usdc,avg_entry_price,avg_entry_decimal,pnl_usdc,"
        "pnl_kind,fill_count,buy_fill_count,sell_fill_count,first_traded_at,"
        "last_traded_at,latest_market_price,latest_market_decimal,"
        "latest_market_at,closing_price,closing_decimal,closing_observed_at,"
        "clv_probability_pp,clv_pct,sport_classification,sport_verified_at,"
        "sport_classification_source"
    )
    rows: List[Dict[str, Any]] = []
    page_size = 1000
    max_pages = 100
    try:
        for page in range(max_pages):
            response = requests.get(
                f"{base}/rest/v1/tracked_wallet_bets",
                headers=headers,
                params={
                    "select": select_fields,
                    "wallet": f"eq.{wallet.lower()}",
                    "sport_classification": f"eq.{FOOTBALL_CLASS_VERIFIED}",
                    "order": "last_traded_at.desc.nullslast",
                    "limit": page_size,
                    "offset": page * page_size,
                },
                timeout=20,
            )
            if response.status_code != 200:
                return [], False
            page_rows = response.json()
            if not isinstance(page_rows, list):
                return [], False
            rows.extend(page_rows)
            if len(page_rows) < page_size:
                return rows, True
        logger.warning(
            "[WalletProfile] normalized history pagination cap reached for %s",
            wallet[:10],
        )
        return rows, False
    except Exception:
        return [], False


def _wallet_bet_api_contract(row: Dict[str, Any]) -> Dict[str, Any]:
    """Canonical v2 bettor-bet object; raw BUY/SELL fields are intentionally absent."""
    return {
        "bet_id": row.get("bet_key"),
        "asset_id": row.get("asset"),
        "condition_id": row.get("condition_id"),
        "event_id": row.get("event_id"),
        "match_key": row.get("match_key"),
        "match_name": row.get("match_name") or row.get("match") or row.get("title"),
        "home": row.get("home"),
        "away": row.get("away"),
        "slug": row.get("slug"),
        "kickoff_utc": row.get("kickoff_utc"),
        "market_type": row.get("market_type"),
        "market_label": row.get("market_label"),
        "selection_label": row.get("selection_label"),
        "side_label": row.get("side_label"),
        "bet_label": row.get("bet_label"),
        "lifecycle_status": row.get("lifecycle_status"),
        "status_label": row.get("status_label"),
        "result": row.get("result"),
        "stake_usdc": row.get("stake_usdc"),
        "sell_proceeds_usdc": row.get("sell_proceeds_usdc"),
        "redeem_proceeds_usdc": row.get("redeem_proceeds_usdc"),
        "avg_entry_probability": row.get("avg_entry_price"),
        "avg_entry_decimal": row.get("avg_entry_decimal") or row.get("price"),
        "pnl_usdc": row.get("pnl_usdc"),
        "pnl_kind": row.get("pnl_kind"),
        "latest_market_probability": row.get("latest_market_price"),
        "latest_market_decimal": row.get("latest_market_decimal"),
        "latest_market_at": row.get("latest_market_at"),
        "closing_probability": row.get("closing_price"),
        "closing_decimal": row.get("closing_decimal"),
        "closing_at": row.get("closing_observed_at"),
        "clv_probability_pp": row.get("clv_probability_pp"),
        "clv_pct": row.get("clv_pct"),
        "fill_count": int(row.get("fill_count") or 0),
        "buy_fill_count": int(row.get("buy_fill_count") or 0),
        "sell_fill_count": int(row.get("sell_fill_count") or 0),
        "first_traded_at": row.get("first_traded_at"),
        "last_traded_at": row.get("last_traded_at") or row.get("traded_at"),
        "sport_classification": row.get("sport_classification") or FOOTBALL_CLASS_VERIFIED,
        "sport_verified_at": row.get("sport_verified_at"),
        "sport_classification_source": row.get("sport_classification_source"),
    }


def _validate_wallet_profile_contract(
    stats: Dict[str, Any],
    bets: List[Dict[str, Any]],
    coverage: Dict[str, Any],
) -> Dict[str, Any]:
    """Return non-destructive API/data consistency warnings."""
    issues: List[Dict[str, str]] = []
    ids = [bet.get("bet_id") for bet in bets if bet.get("bet_id")]
    if len(ids) != len(set(ids)):
        issues.append({
            "code": "duplicate_bet_id",
            "message": "Canonical bet ids are not unique.",
        })

    if coverage.get("history_complete"):
        expected = int(stats.get("bet_count") or 0)
        if expected != len(bets):
            issues.append({
                "code": "bet_count_mismatch",
                "message": f"stats.bet_count={expected}, bets={len(bets)}",
            })

    allowed_results = {"won", "lost", "open", "closed", "unknown", None}
    allowed_statuses = {"resolved", "open", "closed", "unknown", None}
    for bet in bets:
        bet_id = str(bet.get("bet_id") or "?")
        try:
            stake = float(bet.get("stake_usdc") or 0)
        except (TypeError, ValueError):
            stake = 0.0
        if stake + 1e-9 < MIN_TRACKED_WALLET_TRADE_AMOUNT_USDC:
            issues.append({
                "code": "below_minimum_stake",
                "message": f"{bet_id} stake={stake}",
            })

        result = bet.get("result")
        status = bet.get("lifecycle_status")
        if result not in allowed_results or status not in allowed_statuses:
            issues.append({
                "code": "invalid_lifecycle_state",
                "message": f"{bet_id} result={result} status={status}",
            })
        if result in ("won", "lost") and status != "resolved":
            issues.append({
                "code": "resolved_state_mismatch",
                "message": f"{bet_id} result={result} status={status}",
            })

        for field in (
            "avg_entry_probability",
            "latest_market_probability",
            "closing_probability",
        ):
            value = bet.get(field)
            if value is None:
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                numeric = -1.0
            if numeric < 0 or numeric > 1:
                issues.append({
                    "code": "invalid_probability",
                    "message": f"{bet_id} {field}={value}",
                })

        close = bet.get("closing_probability")
        entry = bet.get("avg_entry_probability")
        stored_clv = bet.get("clv_probability_pp")
        if close is not None and entry is not None and stored_clv is not None:
            metrics = _closing_line_metrics(entry, close)
            expected_clv = metrics.get("clv_probability_pp")
            try:
                delta = abs(float(stored_clv) - float(expected_clv))
            except (TypeError, ValueError):
                delta = 999.0
            if expected_clv is None or delta > 0.02:
                issues.append({
                    "code": "clv_mismatch",
                    "message": f"{bet_id} stored={stored_clv} expected={expected_clv}",
                })

        kickoff = _parse_wallet_datetime(bet.get("kickoff_utc"))
        closing_at = _parse_wallet_datetime(bet.get("closing_at"))
        if kickoff is not None and closing_at is not None and closing_at >= kickoff:
            issues.append({
                "code": "post_kickoff_closing_line",
                "message": f"{bet_id} closing_at is not pre-kickoff",
            })

    return {
        "status": "ok" if not issues else "warning",
        "issue_count": len(issues),
        "issues": issues[:50],
    }


def _persist_wallet_bet_rows(
    base: str,
    headers: Dict[str, str],
    wallet: str,
    lifecycle_rows: List[Dict[str, Any]],
) -> bool:
    """Upsert normalized bet lifecycles without deleting historical rows.

    Raw fills remain the execution/audit ledger. Normalized bet rows are
    durable and are only updated when that same canonical bet can be rebuilt
    from verified current evidence.
    """
    if not lifecycle_rows:
        return True

    now = datetime.now(timezone.utc).isoformat()
    payload: List[Dict[str, Any]] = []
    for row in lifecycle_rows:
        bet_key = row.get("bet_key")
        if not bet_key:
            continue
        payload.append({
            "wallet": wallet,
            "bet_key": bet_key,
            "asset": row.get("asset"),
            "condition_id": row.get("condition_id"),
            "event_id": row.get("event_id"),
            "match_key": row.get("match_key"),
            "match_name": row.get("match_name") or row.get("match"),
            "home": row.get("home"),
            "away": row.get("away"),
            "slug": row.get("slug"),
            "kickoff_utc": row.get("kickoff_utc"),
            "title": row.get("title"),
            "market_type": row.get("market_type"),
            "market_label": row.get("market_label"),
            "selection": row.get("selection"),
            "side": row.get("side"),
            "outcome_raw": row.get("outcome_raw"),
            "selection_label": row.get("selection_label"),
            "side_label": row.get("side_label"),
            "bet_label": row.get("bet_label"),
            "lifecycle_status": row.get("lifecycle_status"),
            "result": row.get("result"),
            "status_label": row.get("status_label"),
            "stake_usdc": row.get("stake_usdc"),
            "sell_proceeds_usdc": row.get("sell_proceeds_usdc"),
            "redeem_proceeds_usdc": row.get("redeem_proceeds_usdc"),
            "avg_entry_price": row.get("avg_entry_price"),
            "avg_entry_decimal": row.get("avg_entry_decimal"),
            "pnl_usdc": row.get("pnl_usdc"),
            "pnl_kind": row.get("pnl_kind"),
            "fill_count": int(row.get("fill_count") or 0),
            "buy_fill_count": int(row.get("buy_fill_count") or 0),
            "sell_fill_count": int(row.get("sell_fill_count") or 0),
            "first_traded_at": row.get("first_traded_at"),
            "last_traded_at": row.get("last_traded_at"),
            "sport_classification": FOOTBALL_CLASS_VERIFIED,
            "sport_verified_at": now,
            "sport_classification_source": FOOTBALL_CLASSIFIER_VERSION,
            "updated_at": now,
        })

    if not payload:
        return True

    try:
        post_headers = {
            **headers,
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        }
        url = (
            f"{base}/rest/v1/tracked_wallet_bets"
            "?on_conflict=wallet,bet_key"
        )
        for offset in range(0, len(payload), 500):
            response = requests.post(
                url,
                headers=post_headers,
                json=payload[offset:offset + 500],
                timeout=20,
            )
            if response.status_code not in (200, 201, 204):
                print(
                    f"[WalletBets] upsert failed for {wallet[:10]}... "
                    f"HTTP {response.status_code}: {response.text[:160]}"
                )
                return False
        return True
    except Exception as exc:
        print(f"[WalletBets] upsert error for {wallet[:10]}...: {exc}")
        return False


def _persisted_wallet_bet_to_display(row: Dict[str, Any]) -> Dict[str, Any]:
    """Restore compatibility aliases expected by the existing wallet UI."""
    display = dict(row)
    display["amount_usdc"] = row.get("stake_usdc")
    display["price"] = row.get("avg_entry_decimal")
    display["traded_at"] = row.get("last_traded_at")
    display["is_open"] = row.get("lifecycle_status") == "open"
    display["action"] = "Pozisyon"
    return display


def compute_and_save_wallet_stats(
    wallet: str,
    allow_verified_sport_rebase: bool = False,
) -> bool:
    """Compute per-wallet stats from stored DB data and PATCH them back to
    tracked_wallets. Called by the scraper after each sync so the profile
    endpoint reads pre-computed values instead of recalculating on every request."""
    base = _supabase_base_url()
    if not base or not wallet:
        return False
    wallet = wallet.lower()
    headers = _supabase_headers()
    baseline = _get_wallet_stat_baseline(base, headers, wallet)
    tracked_since = baseline.get("created_at") if baseline else None
    if not tracked_since:
        tracked_since = _get_wallet_tracking_start(base, headers, wallet)

    def _fetch_redeems() -> Tuple[List[Dict[str, Any]], bool]:
        try:
            r = requests.get(f"{base}/rest/v1/tracked_wallet_redeems", headers=headers, params={
                "select": "condition_id,asset,event_id,title,slug,amount_usdc,traded_at",
                "wallet": f"eq.{wallet}",
                "limit": 5000,
            }, timeout=20)
            if r.status_code != 200:
                return [], False
            rows = r.json()
            return (
                _filter_wallet_rows_since(rows, tracked_since),
                True,
            ) if isinstance(rows, list) else ([], False)
        except Exception:
            return [], False

    def _fetch_positions() -> Tuple[List[Dict[str, Any]], bool]:
        try:
            r = requests.get(f"{base}/rest/v1/tracked_wallet_positions", headers=headers, params={
                "select": "condition_id,asset,event_id,title,slug,outcome,size,avg_price,cur_price,initial_value,current_value,cash_pnl,percent_pnl,redeemable,end_date",
                "wallet": f"eq.{wallet}",
                "limit": 500,
            }, timeout=20)
            if r.status_code != 200:
                return [], False
            rows = r.json()
            return (rows, True) if isinstance(rows, list) else ([], False)
        except Exception:
            return [], False

    def _fetch_activity_summary() -> Tuple[List[Dict[str, Any]], bool]:
        try:
            r = requests.get(f"{base}/rest/v1/tracked_wallet_activity", headers=headers, params={
                "select": "wallet,asset,condition_id,event_id,result,title,slug,market_type,selection,side,action,outcome_raw,amount_usdc,price,size,traded_at",
                "wallet": f"eq.{wallet}",
                "limit": 10000,
            }, timeout=20)
            if r.status_code != 200:
                return [], False
            rows = r.json()
            return (
                _filter_wallet_rows_since(rows, tracked_since),
                True,
            ) if isinstance(rows, list) else ([], False)
        except Exception:
            return [], False

    with ThreadPoolExecutor(max_workers=3) as pool:
        f_red = pool.submit(_fetch_redeems)
        f_pos = pool.submit(_fetch_positions)
        f_act = pool.submit(_fetch_activity_summary)
        redeem_rows, redeems_ok = f_red.result()
        position_rows, positions_ok = f_pos.result()
        activity_rows, activity_ok = f_act.result()

    # Activity is the source of the card's total/won/lost values. Never
    # replace an already computed row with zeros when this query failed.
    if not activity_ok:
        print(f"[WalletStats] activity fetch failed; keeping existing stats for {wallet[:10]}...")
        return False
    if not redeems_ok:
        print(f"[WalletStats] redeem fetch failed; keeping existing stats for {wallet[:10]}...")
        return False

    activity_rows, football_registry_ok = _filter_verified_football_items(activity_rows)
    if not football_registry_ok:
        print(f"[WalletStats] soccer registry verification failed; keeping existing stats for {wallet[:10]}...")
        return False
    activity_rows = _filter_tracked_wallet_activity_amount(activity_rows)

    redeem_rows = _filter_wallet_redeems_to_activity(redeem_rows, activity_rows)
    position_rows = _filter_positions_since_tracking(position_rows, activity_rows)
    resolved = _compute_resolved_stats(position_rows, redeem_rows)

    # Win rate: CLOB-based resolution — same ground truth as profile display.
    # For each unique condition_id in activity, call CLOB to determine which
    # outcome token won, store in tracked_wallet_activity.result so the
    # profile page reads directly from DB without live API calls on every open.
    resolved_won_ids = resolved["resolved_won_ids"]
    resolved_lost_ids = resolved["resolved_lost_ids"]
    open_assets = {p.get("asset") for p in position_rows if p.get("asset")}

    # Collect condition_ids that still need CLOB resolution.
    cids_needing_clob: set = set()
    for row in activity_rows:
        asset = row.get("asset")
        cid = row.get("condition_id")
        if not asset or asset in open_assets:
            continue
        if not cid:
            continue  # need cid for CLOB resolution
        if row.get("result") in ("won", "lost"):
            continue  # already stored in DB
        if asset in resolved_won_ids or asset in resolved_lost_ids:
            continue  # known from redeems/positions
        cids_needing_clob.add(cid)

    if cids_needing_clob and positions_ok:
        with ThreadPoolExecutor(max_workers=30) as pool:
            futures = [pool.submit(_fetch_market_resolution, cid) for cid in cids_needing_clob]
            for f in as_completed(futures):
                f.result()

    # Determine result per unique asset.
    asset_to_result: Dict[str, str] = {}
    for row in activity_rows:
        asset = row.get("asset")
        cid = row.get("condition_id")
        if not asset or asset in open_assets:
            continue
        if row.get("result") in ("won", "lost"):
            asset_to_result[asset] = row["result"]  # already stored
            continue
        if asset in resolved_won_ids:
            asset_to_result[asset] = "won"
            continue
        if asset in resolved_lost_ids:
            asset_to_result[asset] = "lost"
            continue
        if not positions_ok:
            # Without a fresh positions snapshot we cannot distinguish an
            # unresolved/closed asset from a currently open one. Keep the
            # persisted result untouched instead of guessing via CLOB.
            continue
        if not cid:
            continue  # can't resolve via CLOB without condition_id
        resolution = _fetch_market_resolution(cid)  # from cache after pre-warm
        if resolution is None:
            continue
        is_winner = resolution.get(asset)
        if is_winner is None:
            continue
        asset_to_result[asset] = "won" if is_winner else "lost"

    # PATCH tracked_wallet_activity.result for newly resolved assets (null rows only).
    _patch_headers = {**headers, "Content-Type": "application/json"}
    for _asset, _result_val in asset_to_result.items():
        try:
            requests.patch(
                f"{base}/rest/v1/tracked_wallet_activity",
                headers=_patch_headers,
                params={"wallet": f"eq.{wallet}", "asset": f"eq.{_asset}", "result": "is.null"},
                json={"result": _result_val},
                timeout=10,
            )
        except Exception:
            pass

    for row in activity_rows:
        if row.get("result") not in ("won", "lost") and row.get("asset") in asset_to_result:
            row["result"] = asset_to_result[row["asset"]]

    activity_stats = _compute_wallet_activity_stats(
        activity_rows,
        position_rows,
        redeem_rows,
    )

    if positions_ok:
        lifecycle_rows = _build_display_activity(
            activity_rows,
            position_rows,
            resolved_won_ids,
            resolved_lost_ids,
            redeem_rows,
        )
        if not _persist_wallet_bet_rows(
            base,
            headers,
            wallet,
            lifecycle_rows,
        ):
            print(
                f"[WalletBets] normalized snapshot not persisted for "
                f"{wallet[:10]}...; existing rows preserved"
            )
    else:
        print(
            f"[WalletBets] positions unavailable for {wallet[:10]}...; "
            "normalized snapshot preserved"
        )

    persisted_rows, persisted_ok = _fetch_persisted_wallet_bets_for_stats(
        base,
        headers,
        wallet,
    )
    persisted_stats = (
        _compute_persisted_wallet_bet_stats(persisted_rows)
        if persisted_ok else None
    )

    baseline_count = int(baseline.get("trade_count") or 0)
    baseline_invested = float(baseline.get("total_invested_usdc") or 0)
    raw_count = int(activity_stats.get("trade_count") or 0)
    raw_invested = float(activity_stats.get("total_invested_usdc") or 0)

    persisted_floor_count = 0 if allow_verified_sport_rebase else baseline_count
    persisted_floor_invested = 0.0 if allow_verified_sport_rebase else baseline_invested
    persisted_complete = bool(
        persisted_stats is not None
        and int(persisted_stats.get("trade_count") or 0)
            >= max(persisted_floor_count, raw_count)
        and float(persisted_stats.get("total_invested_usdc") or 0)
            + 0.01 >= max(persisted_floor_invested, raw_invested)
    )

    if persisted_complete:
        history_stats = persisted_stats
    elif (
        not allow_verified_sport_rebase
        and baseline.get("last_synced_at")
        and baseline_count >= raw_count
        and baseline_invested + 0.01 >= raw_invested
    ):
        # Migration/backfill can be partial for a while. Preserve the last
        # larger known history instead of replacing it with a recent raw slice.
        history_stats = _baseline_wallet_history_stats(baseline, activity_stats)
    else:
        # Initial rollout / first sync fallback before tracked_wallet_bets is
        # available. PART 9 keeps this path functional.
        history_stats = activity_stats

    stats_payload = {
        "win_rate": history_stats["win_rate"],
        "resolved_won": history_stats["resolved_won"],
        "resolved_lost": history_stats["resolved_lost"],
        "resolved_total": history_stats["resolved_total"],
        "trade_count": history_stats["trade_count"],
        "total_invested_usdc": history_stats["total_invested_usdc"],
        "avg_bet_size_usdc": history_stats["avg_bet_size_usdc"],
        "avg_price": history_stats["avg_price"],
        "avg_price_decimal": history_stats["avg_price_decimal"],
        "last_synced_at": datetime.now(timezone.utc).isoformat(),
    }
    # A failed positions read must not make a real open-position snapshot look
    # empty. Activity stats remain safe to refresh, while these two fields stay
    # at their previous values in tracked_wallets.
    if positions_ok:
        stats_payload["open_position_count"] = len(resolved["open_positions"])
        stats_payload["open_exposure_usdc"] = round(resolved["open_exposure"], 2)
    else:
        print(f"[WalletStats] positions fetch failed; preserving position stats for {wallet[:10]}...")

    try:
        patch_headers = {**headers, "Content-Type": "application/json"}
        r = requests.patch(
            f"{base}/rest/v1/tracked_wallets",
            headers=patch_headers,
            params={"wallet": f"eq.{wallet}"},
            json=stats_payload,
            timeout=15,
        )
        return r.status_code in (200, 204)
    except Exception as e:
        print(f"[WalletStats] save error for {wallet}: {e}")
        return False


def list_tracked_wallets_with_stats() -> List[Dict[str, Any]]:
    """Single query to tracked_wallets — stats pre-computed by the scraper
    after each sync. No per-wallet sub-queries needed (replaces the old
    ThreadPoolExecutor approach that fired 96 concurrent Supabase requests)."""
    base = _supabase_base_url()
    if not base:
        return []
    try:
        r = requests.get(
            f"{base}/rest/v1/tracked_wallets",
            headers=_supabase_headers(),
            params={
                "select": "wallet,nickname,notes,created_at,win_rate,resolved_won,resolved_lost,resolved_total,trade_count,open_position_count,open_exposure_usdc,last_synced_at",
                "order": "created_at.desc",
            },
            timeout=10,
        )
        if r.status_code != 200:
            return []
        wallets = r.json()
        for w in wallets:
            w["win_rate_pct"] = w.pop("win_rate", None)
            w["bet_count"] = int(w.get("trade_count") or 0)
            w["stats_status"] = "ready" if w.get("last_synced_at") else "pending"
        return wallets
    except Exception as e:
        print(f"[TrackedWallets] list_with_stats hatasi: {e}")
        return []


def add_tracked_wallet(wallet: str, nickname: str, notes: Optional[str] = None) -> bool:
    base = _supabase_base_url()
    if not base or not wallet or not nickname:
        return False
    try:
        headers = _supabase_headers()
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = "return=minimal"
        r = requests.post(
            f"{base}/rest/v1/tracked_wallets",
            headers=headers,
            json=[{"wallet": wallet.lower(), "nickname": nickname, "notes": notes}],
            timeout=10,
        )
        return r.status_code in (200, 201, 204)
    except Exception as e:
        print(f"[TrackedWallets] add hatasi: {e}")
        return False


def update_tracked_wallet(wallet: str, nickname: Optional[str] = None, notes: Optional[str] = None) -> bool:
    base = _supabase_base_url()
    if not base or not wallet:
        return False
    payload = {}
    if nickname is not None:
        payload["nickname"] = nickname
    if notes is not None:
        payload["notes"] = notes
    if not payload:
        return False
    try:
        headers = _supabase_headers()
        headers["Content-Type"] = "application/json"
        headers["Prefer"] = "return=minimal"
        r = requests.patch(
            f"{base}/rest/v1/tracked_wallets",
            headers=headers,
            params={"wallet": f"eq.{wallet.lower()}"},
            json=payload,
            timeout=10,
        )
        return r.status_code in (200, 204)
    except Exception as e:
        print(f"[TrackedWallets] update hatasi: {e}")
        return False


def remove_tracked_wallet(wallet: str) -> bool:
    base = _supabase_base_url()
    if not base or not wallet:
        return False
    try:
        r = requests.delete(
            f"{base}/rest/v1/tracked_wallets",
            headers=_supabase_headers(),
            params={"wallet": f"eq.{wallet.lower()}"},
            timeout=10,
        )
        return r.status_code in (200, 204)
    except Exception as e:
        print(f"[TrackedWallets] remove hatasi: {e}")
        return False


def _compute_resolved_stats(position_rows: List[Dict[str, Any]], redeem_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build resolution evidence and open-position accounting.

    resolved_won_ids / resolved_lost_ids are the asset-first evidence used by
    activity badges and canonical-bet result accounting. The aggregate counters
    returned here remain a fallback snapshot for callers that do not have the
    tracked activity ledger. Bettor win rate itself is computed later in
    _compute_wallet_activity_stats, one canonical entered outcome bet at a time.
    """

    # ── Activity-badge sets (asset-level, unchanged) ─────────────────────
    resolved_won_assets = {
        rw.get("asset")
        for rw in redeem_rows
        if rw.get("asset") and float(rw.get("amount_usdc") or 0) > 0.01
    }
    resolved_lost_assets = {
        rw.get("asset")
        for rw in redeem_rows
        if rw.get("asset") and float(rw.get("amount_usdc") or 0) <= 0.01
    }
    resolved_lost_assets -= resolved_won_assets
    resolved_won_cids_badge = {
        rw.get("condition_id")
        for rw in redeem_rows
        if not rw.get("asset") and rw.get("condition_id") and float(rw.get("amount_usdc") or 0) > 0.01
    }
    resolved_lost_cids_badge = {
        rw.get("condition_id")
        for rw in redeem_rows
        if not rw.get("asset") and rw.get("condition_id") and float(rw.get("amount_usdc") or 0) <= 0.01
    }
    resolved_lost_cids_badge -= resolved_won_cids_badge

    realized_pnl_total = 0.0
    open_positions = []
    for p in position_rows:
        asset = p.get("asset")
        condition_id = p.get("condition_id")
        cur_price = float(p.get("cur_price") or 0)
        redeemable = bool(p.get("redeemable"))
        is_resolved = redeemable and (cur_price <= 0.02 or cur_price >= 0.98)
        if is_resolved:
            won = cur_price >= 0.98
            if asset:
                (resolved_won_assets if won else resolved_lost_assets).add(asset)
            else:
                if won:
                    resolved_won_cids_badge.add(condition_id)
                elif condition_id not in resolved_won_cids_badge:
                    resolved_lost_cids_badge.add(condition_id)
            realized_pnl_total += float(p.get("cash_pnl") or 0)
        else:
            open_positions.append(p)

    resolved_won_ids = resolved_won_cids_badge | resolved_won_assets
    resolved_lost_ids = resolved_lost_cids_badge | resolved_lost_assets

    # ── Win rate: condition_id-based grouping (1 market = 1 bet) ─────────
    # First build an asset→condition_id lookup from rows that have BOTH fields.
    # Old scraper rows may have asset only; new rows have both. Without this
    # normalization the same market gets two separate keys (the asset ID and the
    # condition_id) and is double-counted.
    asset_to_cid: Dict[str, str] = {}
    for rw in redeem_rows:
        a = rw.get("asset")
        c = rw.get("condition_id")
        if a and c:
            asset_to_cid[a] = c
    for p in position_rows:
        a = p.get("asset")
        c = p.get("condition_id")
        if a and c:
            asset_to_cid[a] = c

    def _canonical_cid(row: Dict[str, Any]) -> Optional[str]:
        cid = row.get("condition_id")
        if cid:
            return cid
        asset = row.get("asset")
        if asset:
            return asset_to_cid.get(asset, asset)
        return None

    # Classify each market as won or lost.
    # Priority: actual redeems (definitive). Fallback: resolved positions not
    # yet redeemed (cur_price≥0.98 → won, ≤0.02 → lost). Dedup guard ensures
    # a market already counted via redeems is never double-counted via positions.
    won_markets: set = set()
    all_redeemed_markets: set = set()
    for rw in redeem_rows:
        cid = _canonical_cid(rw)
        if not cid:
            continue
        all_redeemed_markets.add(cid)
        if float(rw.get("amount_usdc") or 0) > 0.01:
            won_markets.add(cid)

    # Resolved positions not yet redeemed (won but haven't clicked Redeem yet,
    # OR lost and position is worthless). Only counted if NOT already in redeems.
    for p in position_rows:
        cur_price = float(p.get("cur_price") or 0)
        redeemable = bool(p.get("redeemable"))
        if not redeemable:
            continue
        if cur_price >= 0.98 or cur_price <= 0.02:
            cid = _canonical_cid(p)
            if not cid or cid in all_redeemed_markets:
                continue  # already counted via redeems, skip
            all_redeemed_markets.add(cid)
            if cur_price >= 0.98:
                won_markets.add(cid)

    lost_markets = all_redeemed_markets - won_markets

    resolved_won = len(won_markets)
    resolved_lost = len(lost_markets)
    resolved_total = resolved_won + resolved_lost
    win_rate = round((resolved_won / resolved_total) * 100, 1) if resolved_total else None

    open_exposure = sum(float(p.get("current_value") or 0) for p in open_positions)

    return {
        "resolved_won_ids": resolved_won_ids,
        "resolved_lost_ids": resolved_lost_ids,
        "resolved_won": resolved_won,
        "resolved_lost": resolved_lost,
        "resolved_total": resolved_total,
        "win_rate": win_rate,
        "open_positions": open_positions,
        "open_exposure": open_exposure,
        "realized_pnl_total": realized_pnl_total,
    }


def _compute_wallet_activity_stats(
    activity_rows: List[Dict[str, Any]],
    position_rows: List[Dict[str, Any]],
    redeem_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build the profile/list summary from the same filtered ledger.

    trade_count is the canonical bettor-bet/position count, while fill_count
    preserves the number of qualifying raw executions. Win/loss and win rate
    are also canonical-bet level: repeated fills count once, while opposite
    outcome assets under the same condition remain distinct bets.
    """
    resolved = _compute_resolved_stats(position_rows, redeem_rows)
    resolved_won_ids = resolved["resolved_won_ids"]
    resolved_lost_ids = resolved["resolved_lost_ids"]
    open_assets = {
        p.get("asset")
        for p in resolved["open_positions"]
        if p.get("asset")
    }

    canonical_bets = _group_activity_into_canonical_bets(activity_rows)
    fill_count = sum(int(bet.get("fill_count") or 0) for bet in canonical_bets)
    entered_bets = [
        bet for bet in canonical_bets
        if float(bet.get("stake_usdc") or 0) > 0
    ]

    def canonical_bet_result(bet: Dict[str, Any]) -> Optional[str]:
        """Resolve exactly one canonical entered outcome bet."""
        asset = bet.get("asset")
        condition_id = bet.get("condition_id")

        # A still-open position never belongs in resolved performance.
        if asset and asset in open_assets:
            return None

        stored_result = bet.get("stored_result")
        if stored_result in ("won", "lost"):
            return stored_result

        # Concrete assets use only asset-level evidence. Never fall back to the
        # shared condition_id here or opposite outcomes would collapse.
        if asset:
            if asset in resolved_won_ids:
                return "won"
            if asset in resolved_lost_ids:
                return "lost"
            return None

        # Legacy asset-less rows may use the condition-level evidence.
        if condition_id in resolved_won_ids:
            return "won"
        if condition_id in resolved_lost_ids:
            return "lost"
        return None

    resolved_results = [canonical_bet_result(bet) for bet in entered_bets]
    resolved_won = sum(result == "won" for result in resolved_results)
    resolved_lost = sum(result == "lost" for result in resolved_results)
    resolved_total = resolved_won + resolved_lost

    # Investment is qualifying BUY cost only. SELL is exit proceeds and must
    # not inflate bettor stake or average bet size.
    total_invested = sum(float(bet.get("stake_usdc") or 0) for bet in entered_bets)
    # Legacy DB/API field name retained for compatibility; its semantics are
    # canonical entered bets/positions rather than raw execution fills.
    trade_count = len(entered_bets)

    # Within a bet, avg_entry_price is share-weighted (cost / shares). Across
    # bets we weight by stake so larger positions contribute proportionally.
    weighted_price_sum = sum(
        float(bet.get("avg_entry_price") or 0) * float(bet.get("stake_usdc") or 0)
        for bet in entered_bets
    )
    avg_price = weighted_price_sum / total_invested if total_invested else 0.0
    return {
        **resolved,
        "resolved_won": resolved_won,
        "resolved_lost": resolved_lost,
        "resolved_total": resolved_total,
        "win_rate": round((resolved_won / resolved_total) * 100, 1) if resolved_total else None,
        "trade_count": trade_count,
        "fill_count": fill_count,
        "total_invested_usdc": round(total_invested, 2),
        "avg_bet_size_usdc": round(total_invested / trade_count, 2) if trade_count else 0.0,
        "avg_price": round(avg_price, 4),
        "avg_price_decimal": _to_decimal_odds(avg_price) if avg_price else None,
    }


def _filter_positions_since_tracking(
    position_rows: List[Dict[str, Any]],
    activity_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Drop positions whose asset has NO activity row within the tracked
    (post tracking-start) window. `activity_rows` here is already filtered
    to traded_at >= tracked_since, so a position surviving this filter is
    one we've actually observed at least one fill for since we started
    watching this wallet (Task #280) - positions built up entirely before
    tracking started, with no further activity since, are excluded."""
    tracked_assets = {a.get("asset") for a in activity_rows if a.get("asset")}
    return [p for p in position_rows if p.get("asset") in tracked_assets]


def get_wallet_profile(wallet: str) -> Optional[Dict[str, Any]]:
    """Build the tracked-wallet profile view (stats + trade history + open
    positions + a simple rule-based summary) from data already collected into
    Supabase by the periodic wallet-tracker job. Returns None if the wallet
    isn't tracked.

    Fast path: stats (win_rate, trade_count, etc.) are read from pre-computed
    columns in tracked_wallets (written by compute_and_save_wallet_stats after
    each scraper sync). Trade history prefers durable tracked_wallet_bets rows; raw activity and
    redeems are fetched only as a rollout/backfill fallback."""
    base = _supabase_base_url()
    if not base or not wallet:
        return None
    wallet = wallet.lower()
    headers = _supabase_headers()

    # 1. Single fast query — tracked_wallets row with pre-computed stats
    try:
        r = requests.get(
            f"{base}/rest/v1/tracked_wallets",
            headers=headers,
            params={
                "select": "wallet,nickname,notes,created_at,win_rate,resolved_won,resolved_lost,resolved_total,trade_count,total_invested_usdc,avg_bet_size_usdc,avg_price,avg_price_decimal,open_position_count,open_exposure_usdc,last_synced_at",
                "wallet": f"eq.{wallet}",
                "limit": 1,
            },
            timeout=10,
        )
        if r.status_code != 200 or not r.json():
            return None
        wallet_row = r.json()[0]
    except Exception as e:
        print(f"[WalletProfile] wallet fetch hatasi: {e}")
        return None

    tracked_since = wallet_row.get("created_at")

    # 2. Prefer durable normalized bet rows. Raw fill/redeem reads remain as a
    # rollout/backfill fallback while the new table is being populated.
    def _fetch_positions():
        try:
            r2 = requests.get(
                f"{base}/rest/v1/tracked_wallet_positions",
                headers=headers,
                params={
                    "select": "condition_id,asset,event_id,title,slug,outcome,size,avg_price,cur_price,initial_value,current_value,cash_pnl,percent_pnl,redeemable,end_date",
                    "wallet": f"eq.{wallet}",
                    "order": "current_value.desc",
                    "limit": 200,
                },
                timeout=15,
            )
            if r2.status_code != 200:
                return [], False
            rows = r2.json()
            return (rows, True) if isinstance(rows, list) else ([], False)
        except Exception as e2:
            print(f"[WalletProfile] positions fetch hatasi: {e2}")
            return [], False

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_bets = pool.submit(
            _fetch_persisted_wallet_bets_for_profile,
            base,
            headers,
            wallet,
        )
        f_pos = pool.submit(_fetch_positions)
        bet_rows, bets_ok = f_bets.result()
        position_rows, positions_ok = f_pos.result()

    persisted_trade_count = int(wallet_row.get("trade_count") or 0)
    persisted_snapshot_complete = (
        persisted_trade_count == 0
        or len(bet_rows) >= persisted_trade_count
    )
    use_persisted_bets = bets_ok and persisted_snapshot_complete
    history_source = (
        "tracked_wallet_bets"
        if use_persisted_bets
        else "raw_fallback"
    )

    if use_persisted_bets:
        display_activity = [
            _persisted_wallet_bet_to_display(row)
            for row in bet_rows
        ]

        open_assets = {
            row.get("asset")
            for row in bet_rows
            if row.get("asset") and row.get("lifecycle_status") == "open"
        }
        open_positions = []
        if positions_ok:
            open_positions = [
                _with_wallet_bet_display_metadata(position)
                for position in position_rows
                if position.get("asset") in open_assets
            ]

        realized_pnl_total = sum(
            float(row.get("pnl_usdc") or 0)
            for row in bet_rows
            if row.get("pnl_kind") == "realized"
        )
        total_redeemed_usdc = sum(
            float(row.get("redeem_proceeds_usdc") or 0)
            for row in bet_rows
        )
    else:
        # Migration not yet applied, normalized snapshot unavailable, or an
        # existing wallet has not been backfilled into tracked_wallet_bets yet.
        def _fetch_activity():
            try:
                activity_params = {
                    "select": "wallet,transaction_hash,asset,condition_id,event_id,result,title,slug,market_type,selection,side,action,outcome_raw,amount_usdc,price,size,traded_at",
                    "wallet": f"eq.{wallet}",
                    "order": "traded_at.desc,id.desc",
                    "limit": 10000,
                }
                if tracked_since:
                    activity_params["traded_at"] = f"gte.{tracked_since}"
                r2 = requests.get(
                    f"{base}/rest/v1/tracked_wallet_activity",
                    headers=headers,
                    params=activity_params,
                    timeout=15,
                )
                if r2.status_code == 200:
                    rows = r2.json()
                    if isinstance(rows, list):
                        return _filter_wallet_rows_since(rows, tracked_since), True
            except Exception:
                pass
            print(f"[WalletProfile] activity fetch hatasi: {wallet[:10]}...")
            return [], False

        def _fetch_redeems():
            try:
                r2 = requests.get(
                    f"{base}/rest/v1/tracked_wallet_redeems",
                    headers=headers,
                    params={
                        "select": "condition_id,asset,amount_usdc,traded_at",
                        "wallet": f"eq.{wallet}",
                        "order": "traded_at.desc",
                        "limit": 1000,
                    },
                    timeout=15,
                )
                if r2.status_code != 200:
                    return [], False
                rows = r2.json()
                return _filter_wallet_rows_since(rows, tracked_since), True
            except Exception as e2:
                print(f"[WalletProfile] redeem fetch hatasi: {e2}")
                return [], False

        with ThreadPoolExecutor(max_workers=2) as pool:
            f_act = pool.submit(_fetch_activity)
            f_red = pool.submit(_fetch_redeems)
            activity_rows, activity_ok = f_act.result()
            redeem_rows, redeems_ok = f_red.result()

        if activity_ok:
            activity_rows = _filter_wallet_rows_since(activity_rows, tracked_since)
            activity_rows, football_registry_ok = _filter_verified_football_items(activity_rows)
            if not football_registry_ok:
                logger.warning(
                    "[WalletProfile] soccer registry verification incomplete for %s; "
                    "showing only rows already verified in this pass",
                    wallet[:10],
                )
            activity_rows = _filter_tracked_wallet_activity_amount(activity_rows)
            redeem_rows = _filter_wallet_redeems_to_activity(redeem_rows, activity_rows)
        if activity_ok and positions_ok:
            position_rows = _filter_positions_since_tracking(position_rows, activity_rows)

        resolved = _compute_resolved_stats(position_rows, redeem_rows)
        resolved_won_ids = resolved["resolved_won_ids"]
        resolved_lost_ids = resolved["resolved_lost_ids"]
        open_positions = [
            _with_wallet_bet_display_metadata(position)
            for position in resolved["open_positions"]
        ]
        realized_pnl_total = resolved["realized_pnl_total"]
        total_redeemed_usdc = sum(
            float(row.get("amount_usdc") or 0)
            for row in redeem_rows
        )
        display_activity = _build_display_activity(
            activity_rows,
            position_rows,
            resolved_won_ids,
            resolved_lost_ids,
            redeem_rows,
        )

    # 4. The persisted tracked_wallets stats are the canonical snapshot shared
    # with the tracked-wallet list. The scraper computes them from canonical
    # positions whose total BUY entry stake is >= 1000 USDC, then persists the
    # result after resolution.
    # Do not replace them with a second live calculation here: that calculation
    # can observe a different resolution snapshot and was the reason the card
    # and profile showed different win rates for the same wallet.
    trade_count = wallet_row.get("trade_count") or 0
    total_invested = float(wallet_row.get("total_invested_usdc") or 0)
    avg_bet_size = float(wallet_row.get("avg_bet_size_usdc") or 0)
    avg_price = float(wallet_row.get("avg_price") or 0)
    avg_price_decimal = wallet_row.get("avg_price_decimal")
    win_rate = wallet_row.get("win_rate")
    resolved_won = wallet_row.get("resolved_won") or 0
    resolved_lost = wallet_row.get("resolved_lost") or 0
    resolved_total = wallet_row.get("resolved_total") or 0
    open_position_count = wallet_row.get("open_position_count") or 0
    open_exposure = float(wallet_row.get("open_exposure_usdc") or 0)

    summary_lines = []
    if trade_count == 0:
        summary_lines.append("Henüz futbol maçlarında kayıtlı bahsi bulunmuyor.")
    else:
        summary_lines.append(f"{trade_count} futbol bahsi, toplam {round(total_invested, 0):,.0f} USDC yatırım.".replace(",", "."))
        if win_rate is not None:
            if win_rate >= 60:
                summary_lines.append(f"Sonuçlanan {resolved_total} bahisin %{win_rate}'ini kazandı - isabet oranı yüksek.")
            elif win_rate <= 35:
                summary_lines.append(f"Sonuçlanan {resolved_total} bahisin sadece %{win_rate}'ini kazandı - isabet oranı düşük.")
            else:
                summary_lines.append(f"Sonuçlanan {resolved_total} bahisin %{win_rate}'ini kazandı - ortalama bir isabet oranı.")
        if avg_price:
            if avg_price <= 0.35:
                summary_lines.append("Genelde düşük ihtimalli (uzun oranlı) taraflara oynuyor - sürpriz/underdog odaklı bir profil.")
            elif avg_price >= 0.65:
                summary_lines.append("Genelde favoriye/yüksek ihtimalli tarafa oynuyor - güvenli/favori odaklı bir profil.")
        if open_position_count:
            summary_lines.append(f"Şu an {open_position_count} açık pozisyonu var, toplam {round(open_exposure, 0):,.0f} USDC değerinde.".replace(",", "."))

    stats = {
        "bet_count": trade_count,
        "trade_count": trade_count,
        "total_invested_usdc": round(total_invested, 2),
        "avg_bet_size_usdc": round(avg_bet_size, 2),
        "avg_entry_probability": avg_price,
        "avg_entry_decimal": avg_price_decimal,
        "avg_price": avg_price,
        "avg_price_decimal": avg_price_decimal,
        "win_rate_pct": win_rate,
        "resolved_won": resolved_won,
        "resolved_lost": resolved_lost,
        "resolved_total": resolved_total,
        "open_position_count": open_position_count,
        "open_exposure_usdc": round(open_exposure, 2),
        "realized_pnl_usdc": round(realized_pnl_total, 2),
        "total_redeemed_usdc": round(total_redeemed_usdc, 2),
    }
    canonical_bets = [
        _wallet_bet_api_contract(row)
        for row in display_activity
    ]
    coverage = {
        "history_source": history_source,
        "history_complete": bool(use_persisted_bets),
        "expected_bet_count": int(trade_count or 0),
        "returned_bet_count": len(canonical_bets),
        "football_only": True,
        "minimum_position_entry_usdc": MIN_TRACKED_WALLET_TRADE_AMOUNT_USDC,
        "canonical_identity": "asset_first",
        "canonical_history_retention": TRACKED_WALLET_CANONICAL_RETENTION,
        "raw_activity_retention_days": TRACKED_WALLET_RAW_RETENTION_DAYS,
        "closing_line_source": TRACKED_WALLET_CLOSING_LINE_SOURCE,
    }
    quality = _validate_wallet_profile_contract(
        stats,
        canonical_bets,
        coverage,
    )

    return {
        "contract_version": TRACKED_WALLET_API_CONTRACT_VERSION,
        "wallet": wallet_row.get("wallet"),
        "nickname": wallet_row.get("nickname"),
        "notes": wallet_row.get("notes"),
        "tracked_since": wallet_row.get("created_at"),
        "last_synced_at": wallet_row.get("last_synced_at"),
        "stats_status": "ready" if wallet_row.get("last_synced_at") else "pending",
        "coverage": coverage,
        "quality": quality,
        "stats": stats,
        "summary": summary_lines,
        "bets": canonical_bets,
        "activity": display_activity,
        "open_positions": open_positions,
    }

_ACTION_LABELS = {"buy": "Alım", "sell": "Satım"}


def _build_display_activity(
    activity_rows: List[Dict[str, Any]],
    position_rows: Optional[List[Dict[str, Any]]] = None,
    resolved_won_ids: Optional[set] = None,
    resolved_lost_ids: Optional[set] = None,
    redeem_rows: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Build one lifecycle row per canonical bettor position.

    BUY and SELL executions are accounting events inside the same bet, not
    separate bets. The row exposes entry stake, exit proceeds, average entry
    odds, current/final P&L, result/status and the latest lifecycle event.
    """
    position_rows = position_rows or []
    redeem_rows = redeem_rows or []
    resolved_won_ids = resolved_won_ids or set()
    resolved_lost_ids = resolved_lost_ids or set()

    position_by_asset: Dict[str, Dict[str, Any]] = {
        p.get("asset"): p for p in position_rows if p.get("asset")
    }

    raw_rows_by_key: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
    for idx, row in enumerate(activity_rows):
        key = _canonical_bet_identity(row)
        if key is None:
            key = ("unidentified-fill", idx)
        raw_rows_by_key.setdefault(key, []).append(row)

    canonical_bets = _group_activity_into_canonical_bets(activity_rows)

    assets_by_condition: Dict[Any, set] = {}
    for bet in canonical_bets:
        cid = bet.get("condition_id")
        asset = bet.get("asset")
        if cid and asset:
            assets_by_condition.setdefault(cid, set()).add(asset)

    def _resolved_result(bet: Dict[str, Any]) -> str:
        asset = bet.get("asset")
        cid = bet.get("condition_id")
        stored = bet.get("stored_result")
        if stored in ("won", "lost"):
            return stored
        if asset:
            if asset in resolved_won_ids:
                return "won"
            if asset in resolved_lost_ids:
                return "lost"
            return "unknown"
        if len(assets_by_condition.get(cid, set())) > 1:
            return "unknown"
        if cid in resolved_won_ids:
            return "won"
        if cid in resolved_lost_ids:
            return "lost"
        return "unknown"

    redeem_by_asset: Dict[str, float] = {}
    redeem_time_by_asset: Dict[str, Optional[str]] = {}
    redeem_by_condition: Dict[Any, float] = {}
    redeem_time_by_condition: Dict[Any, Optional[str]] = {}
    for redeem in redeem_rows:
        try:
            amount = float(redeem.get("amount_usdc") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        asset = redeem.get("asset")
        cid = redeem.get("condition_id")
        traded_at = redeem.get("traded_at")
        if asset:
            redeem_by_asset[asset] = redeem_by_asset.get(asset, 0.0) + amount
            if traded_at and (
                not redeem_time_by_asset.get(asset)
                or str(traded_at) > str(redeem_time_by_asset.get(asset))
            ):
                redeem_time_by_asset[asset] = traded_at
        elif cid and len(assets_by_condition.get(cid, set())) <= 1:
            redeem_by_condition[cid] = redeem_by_condition.get(cid, 0.0) + amount
            if traded_at and (
                not redeem_time_by_condition.get(cid)
                or str(traded_at) > str(redeem_time_by_condition.get(cid))
            ):
                redeem_time_by_condition[cid] = traded_at

    display_rows: List[Dict[str, Any]] = []
    for bet in canonical_bets:
        key = bet.get("bet_key")
        rows = raw_rows_by_key.get(key, [])
        if not rows:
            continue

        stake = float(bet.get("stake_usdc") or 0)
        if stake <= 0:
            continue

        latest_row = rows[0]
        first_traded_at: Optional[str] = None
        last_traded_at: Optional[str] = None
        buy_shares = 0.0
        sell_shares = 0.0

        for row in rows:
            traded_at = row.get("traded_at")
            if traded_at:
                traded_s = str(traded_at)
                if first_traded_at is None or traded_s < first_traded_at:
                    first_traded_at = traded_s
                if last_traded_at is None or traded_s > last_traded_at:
                    last_traded_at = traded_s
                    latest_row = row

            try:
                amount = float(row.get("amount_usdc") or 0)
            except (TypeError, ValueError):
                amount = 0.0
            try:
                price = float(row.get("price") or 0)
            except (TypeError, ValueError):
                price = 0.0
            try:
                size = float(row.get("size") or 0)
            except (TypeError, ValueError):
                size = 0.0
            shares = size if size > 0 else (
                amount / price if amount > 0 and price > 0 else 0.0
            )

            action = _tracked_wallet_activity_action(row)
            if action == "BUY":
                buy_shares += shares
            elif action == "SELL":
                sell_shares += shares

        asset = bet.get("asset")
        cid = bet.get("condition_id")
        current_position = position_by_asset.get(asset) if asset else None
        result = _resolved_result(bet)

        redeem_proceeds = 0.0
        redeem_time = None
        if asset and asset in redeem_by_asset:
            redeem_proceeds = redeem_by_asset[asset]
            redeem_time = redeem_time_by_asset.get(asset)
        elif cid in redeem_by_condition:
            redeem_proceeds = redeem_by_condition[cid]
            redeem_time = redeem_time_by_condition.get(cid)

        if redeem_time and (
            last_traded_at is None or str(redeem_time) > last_traded_at
        ):
            last_traded_at = str(redeem_time)

        sell_proceeds = float(bet.get("sell_proceeds_usdc") or 0)
        fully_sold = (
            buy_shares > 0
            and sell_shares >= (buy_shares * 0.995)
        )

        if result == "won":
            lifecycle_status = "resolved"
            status_label = "Kazandı"
        elif result == "lost":
            lifecycle_status = "resolved"
            status_label = "Kaybetti"
        elif current_position is not None:
            lifecycle_status = "open"
            status_label = "Açık"
            result = "open"
        elif fully_sold:
            lifecycle_status = "closed"
            status_label = "Kapandı"
            result = "closed"
        else:
            lifecycle_status = "unknown"
            status_label = "Bilinmiyor"
            result = "unknown"

        pnl_usdc: Optional[float] = None
        pnl_kind = "unknown"
        if current_position is not None:
            try:
                cash_pnl = current_position.get("cash_pnl")
                if cash_pnl is not None:
                    pnl_usdc = float(cash_pnl)
                    pnl_kind = "current"
            except (TypeError, ValueError):
                pnl_usdc = None
        elif fully_sold:
            pnl_usdc = sell_proceeds + redeem_proceeds - stake
            pnl_kind = "realized"
        elif result == "lost":
            pnl_usdc = sell_proceeds + redeem_proceeds - stake
            pnl_kind = "realized"
        elif result == "won" and redeem_proceeds > 0:
            pnl_usdc = sell_proceeds + redeem_proceeds - stake
            pnl_kind = "realized"

        source = dict(latest_row)
        for field in (
            "wallet", "condition_id", "asset", "market_type",
            "selection", "side", "outcome_raw",
        ):
            if not source.get(field) and bet.get(field) is not None:
                source[field] = bet.get(field)

        if current_position is not None:
            for field in ("title", "slug", "event_id"):
                if current_position.get(field):
                    source[field] = current_position.get(field)

        enriched = _with_wallet_bet_display_metadata(source)
        avg_entry_probability = float(bet.get("avg_entry_price") or 0)
        avg_entry_decimal = (
            _to_decimal_odds(avg_entry_probability)
            if avg_entry_probability else None
        )

        display_rows.append({
            "bet_key": _canonical_bet_key_text(key),
            "title": source.get("title"),
            "match": enriched.get("match") or enriched.get("match_name") or source.get("title") or "-",
            "match_name": enriched.get("match_name"),
            "match_key": enriched.get("match_key"),
            "event_id": enriched.get("event_id"),
            "kickoff_utc": enriched.get("kickoff_utc"),
            "home": enriched.get("home"),
            "away": enriched.get("away"),
            "slug": enriched.get("slug"),
            "market_type": enriched.get("market_type"),
            "market_label": enriched.get("market_label"),
            "selection_label": enriched.get("selection_label"),
            "side_label": enriched.get("side_label"),
            "bet_label": enriched.get("bet_label"),
            "selection": source.get("selection"),
            "side": source.get("side"),
            "asset": asset,
            "condition_id": cid,
            "action": "Pozisyon",
            "is_open": lifecycle_status == "open",
            "result": result,
            "lifecycle_status": lifecycle_status,
            "status_label": status_label,
            "outcome_raw": source.get("outcome_raw") or source.get("outcome"),
            "stake_usdc": round(stake, 2),
            "sell_proceeds_usdc": round(sell_proceeds, 2),
            "redeem_proceeds_usdc": round(redeem_proceeds, 2),
            "amount_usdc": round(stake, 2),
            "avg_entry_price": round(avg_entry_probability, 6),
            "avg_entry_decimal": avg_entry_decimal,
            "price": avg_entry_decimal,
            "pnl_usdc": round(pnl_usdc, 2) if pnl_usdc is not None else None,
            "pnl_kind": pnl_kind,
            "first_traded_at": first_traded_at,
            "last_traded_at": last_traded_at,
            "traded_at": last_traded_at,
            "fill_count": int(bet.get("fill_count") or 0),
            "buy_fill_count": int(bet.get("buy_fill_count") or 0),
            "sell_fill_count": int(bet.get("sell_fill_count") or 0),
        })

    display_rows.sort(
        key=lambda row: row.get("last_traded_at") or "",
        reverse=True,
    )
    return display_rows
