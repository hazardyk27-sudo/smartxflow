"""
betwatch_client.py — Betwatch API v1 shared client
Base URL: https://api.betwatch.fr/api/v1
Auth: Authorization: Token <Betwach_api_key>
Rate limits: live ≤ 1 req/10s, prematch ≤ 1 req/40s
"""

import os
import requests

from core.fixture_identity_payload_stage import stage_betwatch_authoritative_payload
from core.fixture_identity_shadow import stage_betwatch_identity_payload
from core.fixture_uid_authoritative_activation import install_provider_authoritative_fixture_writer_patch

BETWATCH_BASE_URL = "https://api.betwatch.fr/api/v1"

# The deployed server-side prematch runtime can resolve this desktop copy first.
# Installing is safe because behavior changes only when the explicit flag is on.
install_provider_authoritative_fixture_writer_patch()


def get_betwatch_headers() -> dict:
    api_key = os.environ.get("Betwach_api_key", "")
    return {
        "Authorization": f"Token {api_key}",
        "Accept": "application/json",
        "User-Agent": "SmartXFlow/2.0",
    }


def fetch_prematch(timeout: int = 30) -> list:
    """GET /football/prematch — tüm prematch maçları döndürür."""
    r = requests.get(
        f"{BETWATCH_BASE_URL}/football/prematch",
        headers=get_betwatch_headers(),
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    matches = data if isinstance(data, list) else []

    # Keep both Identity V2 stages in sync with the root client. The authoritative
    # copy is memory-only and is consumed only when its feature flag is enabled.
    try:
        stage_betwatch_identity_payload(matches)
        stage_betwatch_authoritative_payload(matches)
    except Exception as exc:
        print(f"[IdentityV2] WARN — payload stage atlandı: {str(exc)[:200]}", flush=True)

    return matches


def fetch_live(timeout: int = 30) -> list:
    """GET /football/live — tüm canlı maçları döndürür (live_info dahil)."""
    r = requests.get(
        f"{BETWATCH_BASE_URL}/football/live",
        headers=get_betwatch_headers(),
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


def normalize_kickoff(ko: str) -> str:
    """Betwatch kickoff 'Z' suffix → '+00:00' format."""
    if not ko:
        return ""
    if ko.endswith("Z"):
        return ko[:-1] + "+00:00"
    return ko


def map_market(mkt_name: str, runners: list, *, home=None, away=None, **_legacy_kwargs):
    """
    Betwatch market adını ve runner listesini (market_key, [(sel_code, runner)]) formatına dönüştürür.
    Desteklenen marketler: Match Odds (1X2), Over/Under 2.5 Goals (OU25), Both teams to Score? (BTTS)
    Diğerleri için (None, []) döner.

    ``home``/``away`` takım adlarıyla doğrulanabilir 1X2 eşlemesi yapar;
    belirsiz/çift koşucular sinyale dönüştürülmez.
    """
    name = (mkt_name or "").strip()

    if name == "Match Odds":
        # A provider may supply [home,draw,away], [home,away,draw] or
        # [draw,home,away]. Never turn a team runner into "X" based on
        # its *position*; that corrupted money/side assignment.
        if not isinstance(runners, list) or not 2 <= len(runners) <= 3:
            return None, []
        normalize = lambda s: " ".join(str(s or "").casefold().split())
        home_name, away_name = normalize(home), normalize(away)
        recognized = {}
        unknown = []
        for runner in runners:
            if not isinstance(runner, dict):
                return None, []
            label = normalize(runner.get("name"))
            if not label:
                return None, []
            if label in ("x", "draw", "the draw", "tie", "match draw", "beraberlik"):
                side = "X"
            elif label in ("1", "home", "home win", "v1") or (home_name and label == home_name and home_name != away_name):
                side = "1"
            elif label in ("2", "away", "away win", "v2") or (away_name and label == away_name and home_name != away_name):
                side = "2"
            else:
                unknown.append(runner)
                continue
            if side in recognized:
                return None, []  # Duplicate side: never overwrite its volume.
            recognized[side] = runner

        # If one team was explicitly resolved, a single unidentified runner
        # can be assigned to the *other* team. Otherwise the source is
        # ambiguous; missing outcomes must remain missing, not invented.
        if unknown:
            unclaimed_team_sides = {"1", "2"} - recognized.keys()
            if len(unknown) != 1 or len(unclaimed_team_sides) != 1:
                return None, []
            recognized[unclaimed_team_sides.pop()] = unknown[0]
        if len(recognized) < 2:
            return None, []
        return "1X2", [(side, recognized[side]) for side in ("1", "X", "2")
                       if side in recognized]

    elif name.startswith("Over/Under 2.5"):
        sels = []
        for r in runners:
            r_name = (r.get("name") or "").lower()
            if "over" in r_name:
                sels.append(("O", r))
            elif "under" in r_name:
                sels.append(("U", r))
        return ("OU25", sels) if sels else (None, [])

    elif name == "Both teams to Score?":
        sels = []
        for r in runners:
            r_name = (r.get("name") or "").lower()
            if r_name in ("yes", "y"):
                sels.append(("Y", r))
            elif r_name in ("no", "n"):
                sels.append(("N", r))
        return ("BTTS", sels) if sels else (None, [])

    return None, []


def betwatch_live_minute(live_info: dict) -> str:
    """live_info dict'inden dakika string'i üret."""
    if not live_info:
        return ""
    if live_info.get("finished"):
        return "FT"
    if live_info.get("is_ht"):
        return "HT"
    t = live_info.get("time", 0) or 0
    return f"{t}'"


def betwatch_live_score(live_info: dict) -> str:
    """live_info dict'inden skor string'i üret."""
    if not live_info:
        return ""
    g1 = live_info.get("goal_v1", 0) or 0
    g2 = live_info.get("goal_v2", 0) or 0
    return f"{g1}-{g2}"
