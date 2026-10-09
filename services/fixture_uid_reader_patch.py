"""UID-aware adapters for UI-facing Supabase readers.

Fixture Identity V2 deliberately keeps ``match_id_hash`` as a compatibility
fingerprint. Once legacy hash uniqueness is retired, two physical rematches may
legitimately share that fingerprint. Any reader that dictionaries fixtures by
``match_id_hash`` would therefore collapse one physical event.

This module patches only UI-facing read methods. It preserves legacy fallback for
historical rows whose fixture UID can never be proven, while preferring
``fixture_uid`` whenever current data carries it.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
from urllib.parse import quote

import pytz

from core.hash_utils import make_fixture_identity_key


_MAX_FIXTURES = 10000
_FIRST_PAGE_RPC = "sxf_matches_first_page_v1"
_MAX_FIRST_PAGE = 100


def _physical_key(row: Mapping[str, Any]):
    home = row.get("home_team", row.get("home", ""))
    away = row.get("away_team", row.get("away", ""))
    league = row.get("league", "")
    kickoff = row.get("kickoff_utc", row.get("date", ""))
    return make_fixture_identity_key(home, away, league, kickoff)


def _fixture_read_key(row: Mapping[str, Any]):
    uid = str(row.get("fixture_uid") or "").strip()
    if uid:
        return ("uid", uid)
    physical = _physical_key(row)
    if physical is not None:
        return ("physical", physical)
    # Last-resort compatibility only. This does not merge proven physical rows;
    # it is used only for malformed legacy rows that have no UID/physical key.
    return ("legacy", str(row.get("match_id_hash") or "").strip(), id(row))


def _fetch_fixture_rows(client: Any, *, date_gte: Optional[str] = None) -> List[Dict[str, Any]]:
    if not getattr(client, "is_available", False):
        return []
    url = (
        f"{client._rest_url('fixtures')}"
        "?select=fixture_uid,match_id_hash,home_team,away_team,league,kickoff_utc,fixture_date"
        f"&limit={_MAX_FIXTURES}"
    )
    if date_gte:
        url += f"&fixture_date=gte.{quote(date_gte, safe='')}"
    response = client._get_http_client().get(url, headers=client._headers(), timeout=30)
    if response.status_code != 200:
        print(f"[FixtureUIDReader] fixtures fetch error: {response.status_code}")
        return []
    payload = response.json()
    return payload if isinstance(payload, list) else []


def _unique_physical_uid_map(fixtures: Iterable[Mapping[str, Any]]) -> Dict[Any, str]:
    values: Dict[Any, set[str]] = defaultdict(set)
    for fixture in fixtures or []:
        key = _physical_key(fixture)
        uid = str(fixture.get("fixture_uid") or "").strip()
        if key is not None and uid:
            values[key].add(uid)
    return {
        key: next(iter(uids))
        for key, uids in values.items()
        if len(uids) == 1
    }


def enrich_matches_with_fixture_uids(client: Any, matches: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach UID to UI match rows by exact physical identity, never by hash alone."""
    result = list(matches or [])
    missing = [m for m in result if isinstance(m, dict) and not str(m.get("fixture_uid") or "").strip()]
    if not missing:
        return result
    try:
        fixtures = _fetch_fixture_rows(client)
        uid_by_physical = _unique_physical_uid_map(fixtures)
    except Exception as exc:
        print(f"[FixtureUIDReader] UID enrichment skipped: {exc}")
        return result

    tagged = 0
    for match in missing:
        key = _physical_key(match)
        uid = uid_by_physical.get(key)
        if uid:
            match["fixture_uid"] = uid
            tagged += 1
    if tagged:
        print(f"[FixtureUIDReader] attached fixture_uid to {tagged} UI match row(s)")
    return result



def _fetch_first_page_rows(
    client: Any,
    market: str,
    limit: int,
    date_gte: str,
) -> Optional[Tuple[List[Dict[str, Any]], int]]:
    """Fetch only the globally highest-volume first page from the current table.

    The RPC performs numeric volume ordering inside Postgres and returns at most
    ``limit`` current-table rows plus the filtered total count.  No fixture table
    scan and no full market payload crosses the network on this path.
    """
    if not getattr(client, "is_available", False):
        return None

    safe_limit = max(1, min(int(limit or 20), _MAX_FIRST_PAGE))
    url = client._rest_url(f"rpc/{_FIRST_PAGE_RPC}")
    body = {
        "p_market": market,
        "p_limit": safe_limit,
        "p_date_gte": f"{date_gte}T00:00:00+00:00" if date_gte else None,
    }
    try:
        response = client._get_http_client().post(
            url,
            headers=client._headers(),
            json=body,
            timeout=10,
        )
        if response.status_code != 200:
            print(f"[FixtureUIDReader] first-page RPC unavailable: {response.status_code}")
            return None
        payload = response.json()
        if not isinstance(payload, list):
            return None

        rows: List[Dict[str, Any]] = []
        total = 0
        for item in payload:
            if not isinstance(item, dict):
                continue
            row = item.get("row_data")
            if isinstance(row, str):
                try:
                    row = json.loads(row)
                except Exception:
                    row = None
            if isinstance(row, dict):
                rows.append(row)
            try:
                total = max(total, int(item.get("total_count") or 0))
            except (TypeError, ValueError):
                pass
        if rows and total <= 0:
            total = len(rows)
        return rows, total
    except Exception as exc:
        print(f"[FixtureUIDReader] first-page RPC failed: {exc}")
        return None


def _current_row_to_match(client: Any, row: Mapping[str, Any], market: str, tr_tz: Any) -> Dict[str, Any]:
    kickoff_utc = row.get("date", "")
    date_display = kickoff_utc
    if kickoff_utc:
        try:
            kickoff_dt = (
                datetime.fromisoformat(str(kickoff_utc).replace("Z", "+00:00"))
                if isinstance(kickoff_utc, str)
                else kickoff_utc
            )
            date_display = kickoff_dt.astimezone(tr_tz).strftime("%d.%b %H:%M")
        except Exception:
            pass

    try:
        latest = client._normalize_history_row(dict(row), market)
    except Exception:
        latest = client._get_empty_odds(market)

    match: Dict[str, Any] = {
        "fixture_uid": row.get("fixture_uid"),
        "home_team": row.get("home", ""),
        "away_team": row.get("away", ""),
        "league": row.get("league", ""),
        "date": date_display,
        "kickoff_utc": kickoff_utc,
        "latest": latest,
    }
    match_hash = str(row.get("match_id_hash") or "").strip()
    if match_hash:
        match["match_id_hash"] = match_hash
    return match

def get_matches_paginated_uid_safe(
    client: Any,
    market: str,
    limit: int = 20,
    offset: int = 0,
    today_only: bool = False,
) -> Dict[str, Any]:
    """Fixtures-first reader keyed by UID/physical identity, never legacy hash."""
    if not getattr(client, "is_available", False):
        return {"matches": [], "total": 0, "has_more": False}

    try:
        tr_tz = pytz.timezone("Europe/Istanbul")
        now_tr = datetime.now(tr_tz)
        today_date = now_tr.date()
        seven_days_ago = (today_date - timedelta(days=7)).strftime("%Y-%m-%d")
        date_gte = (
            (today_date - timedelta(days=1)).strftime("%Y-%m-%d")
            if today_only
            else seven_days_ago
        )

        # Critical first paint: use the current-table RPC so a 20-row screen never
        # waits for the full fixture/current-market snapshot to cross the network.
        # Offset pages remain on the legacy path until Menu Part 2 introduces real
        # UID-safe pagination for background hydration.
        if offset == 0 and 0 < limit <= _MAX_FIRST_PAGE:
            first_page = _fetch_first_page_rows(client, market, limit, date_gte)
            if first_page is not None:
                current_rows, total = first_page
                matches = [
                    _current_row_to_match(client, row, market, tr_tz)
                    for row in current_rows
                ]
                return {
                    "matches": matches,
                    "total": total,
                    "has_more": total > len(matches),
                    "first_page_fast": True,
                }

        fixtures = _fetch_fixture_rows(client, date_gte=date_gte)
        fixtures = client._dedupe_fixtures(fixtures)

        # A UID is the primary key. Exact physical identity is the safe fallback
        # during mixed old/new data. Legacy hash is intentionally not a key.
        fixtures_by_identity: Dict[Any, Dict[str, Any]] = {}
        for fixture in fixtures:
            fixtures_by_identity[_fixture_read_key(fixture)] = fixture

        if not fixtures_by_identity:
            return {"matches": [], "total": 0, "has_more": False}

        main_odds = client._fetch_main_table_odds(market, date_gte=date_gte)
        matches: List[Dict[str, Any]] = []

        for fixture in fixtures_by_identity.values():
            home = fixture.get("home_team", "")
            away = fixture.get("away_team", "")
            league = fixture.get("league", "")
            kickoff_utc = fixture.get("kickoff_utc", "")
            date_display = fixture.get("fixture_date", "")

            if kickoff_utc:
                try:
                    kickoff_dt = (
                        datetime.fromisoformat(str(kickoff_utc).replace("Z", "+00:00"))
                        if isinstance(kickoff_utc, str)
                        else kickoff_utc
                    )
                    date_display = kickoff_dt.astimezone(tr_tz).strftime("%d.%b %H:%M")
                except Exception:
                    pass

            row = main_odds.get((home, away, kickoff_utc))
            latest = (
                client._normalize_history_row(row, market)
                if row
                else client._get_empty_odds(market)
            )
            matches.append(
                {
                    "fixture_uid": fixture.get("fixture_uid"),
                    "home_team": home,
                    "away_team": away,
                    "league": league,
                    "date": date_display,
                    "match_id_hash": fixture.get("match_id_hash", ""),
                    "kickoff_utc": kickoff_utc,
                    "latest": latest,
                }
            )

        # Preserve the legacy method's API contract: it returned the full set and
        # reported has_more=False even though limit/offset arguments exist.
        return {"matches": matches, "total": len(matches), "has_more": False}
    except Exception as exc:
        print(f"[FixtureUIDReader] paginated reader error: {exc}")
        return {"matches": [], "total": 0, "has_more": False}


def _bind_history_uid_preference() -> None:
    """Prefer fixture_uid for new history; fall back to legacy lookup if absent."""
    from . import display_history_fallback as fallback

    if getattr(fallback, "_fixture_uid_reader_bound", False):
        return

    original_cache_key = fallback._cache_key
    original_fetch = fallback._fetch_latest_history_row

    def cache_key(match: Dict[str, Any], market: str) -> tuple:
        uid = str(match.get("fixture_uid") or "").strip()
        if uid:
            return market, "fixture_uid", uid
        return original_cache_key(match, market)

    def fetch_latest_history_row(client: Any, match: Dict[str, Any], market: str):
        uid = str(match.get("fixture_uid") or "").strip()
        if uid and market in fallback._SUPPORTED_MARKETS and getattr(client, "is_available", False):
            history_table = f"{market}_history"
            url = (
                f"{client._rest_url(history_table)}?select=*"
                f"&fixture_uid=eq.{quote(uid, safe='')}"
                "&order=scraped_at.desc&limit=1"
            )
            try:
                response = client._get_http_client().get(url, headers=client._headers(), timeout=8)
                if response.status_code == 200:
                    rows = response.json()
                    if isinstance(rows, list) and rows:
                        return rows[0]
            except Exception as exc:
                print(f"[FixtureUIDReader] UID history lookup failed for {uid}: {exc}")
        # Historical rows before V2 may legitimately have NULL fixture_uid.
        return original_fetch(client, match, market)

    fallback._cache_key = cache_key
    fallback._fetch_latest_history_row = fetch_latest_history_row
    fallback._fixture_uid_reader_bound = True


def bind_fixture_uid_reader_patch() -> None:
    """Bind UID-first identity to UI readers while retaining legacy fallback."""
    from . import supabase_client as supabase_client

    client_cls = supabase_client.SupabaseClient
    if getattr(client_cls, "_fixture_uid_reader_bound", False):
        return

    original_all = client_cls.get_all_matches_with_latest

    def get_all_matches_with_latest(self, market: str, date_filter: str = None):
        matches = original_all(self, market, date_filter)
        return enrich_matches_with_fixture_uids(self, matches)

    def get_matches_paginated(self, market: str, limit: int = 20, offset: int = 0, today_only: bool = False):
        return get_matches_paginated_uid_safe(self, market, limit, offset, today_only)

    client_cls.get_all_matches_with_latest = get_all_matches_with_latest
    client_cls.get_matches_paginated = get_matches_paginated
    client_cls._fixture_uid_reader_bound = True

    # Patch history lookup before display_history_fallback captures/binds readers.
    _bind_history_uid_preference()
