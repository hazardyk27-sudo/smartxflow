"""
betwatch_client.py — Betwatch API v1 shared client
Base URL: https://api.betwatch.fr/api/v1
Auth: Authorization: Token <Betwach_api_key>
Rate limits: live ≤ 1 req/10s, prematch ≤ 1 req/40s
"""

import os
import requests

BETWATCH_BASE_URL = "https://api.betwatch.fr/api/v1"


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
    return data if isinstance(data, list) else []


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


def map_market(mkt_name: str, runners: list):
    """
    Betwatch market adını ve runner listesini (market_key, [(sel_code, runner)]) formatına dönüştürür.
    Desteklenen marketler: Match Odds (1X2), Over/Under 2.5 Goals (OU25), Both teams to Score? (BTTS)
    Diğerleri için (None, []) döner.
    """
    name = (mkt_name or "").strip()

    if name == "Match Odds":
        if len(runners) < 2:
            return None, []
        sels = []
        for i, r in enumerate(runners):
            r_name = (r.get("name") or "").lower()
            if "draw" in r_name:
                sels.append(("X", r))
            elif not sels or (sels and "X" not in [s[0] for s in sels] and i == 0):
                sels.append(("1", r))
            else:
                sels.append(("2", r))
        if len(sels) == 3 and sels[1][0] != "X":
            sels[1] = ("X", sels[1][1])
        return "1X2", sels

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
    if t > 0:
        return f"{t}'"
    return ""


def betwatch_live_score(live_info: dict) -> str:
    """live_info dict'inden skor string'i üret."""
    if not live_info:
        return ""
    g1 = live_info.get("goal_v1", 0) or 0
    g2 = live_info.get("goal_v2", 0) or 0
    return f"{g1}-{g2}"
