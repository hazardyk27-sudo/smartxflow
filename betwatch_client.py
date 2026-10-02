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


def _norm_market_label(value: str) -> str:
    """Normalize Betwatch market/runner labels for resilient matching."""
    return " ".join(str(value or "").strip().lower().replace("&", " and ").split())


def _runner_matches_team(label: str, team: str) -> bool:
    """Best-effort exact-ish team label match without fuzzy cross-team guessing."""
    if not label or not team:
        return False
    nl = _norm_market_label(label)
    nt = _norm_market_label(team)
    return nl == nt or nl.startswith(nt + " ") or nl.endswith(" " + nt)


def _double_chance_code(label: str, home: str = "", away: str = ""):
    """Map a Double Chance runner label to 1X / X2 / 12.

    Supports generic labels (Home or Draw, Draw or Away, Home or Away),
    compact labels (1X/X2/12), and team-aware labels such as
    "Arsenal or Draw" / "Draw or Chelsea".
    """
    n = _norm_market_label(label)
    compact = n.replace(" ", "").replace("/", "").replace("-", "")
    if compact in ("1x", "x1"):
        return "1X"
    if compact in ("x2", "2x"):
        return "X2"
    if compact in ("12", "21"):
        return "12"

    has_draw = "draw" in n or "tie" in n
    home_hit = _runner_matches_team(n.replace(" or ", " "), home) or "home" in n
    away_hit = _runner_matches_team(n.replace(" or ", " "), away) or "away" in n

    # Team-aware matching for common "<team> or Draw" labels.
    if home:
        nh = _norm_market_label(home)
        home_hit = home_hit or nh in n
    if away:
        na = _norm_market_label(away)
        away_hit = away_hit or na in n

    if has_draw and home_hit and not away_hit:
        return "1X"
    if has_draw and away_hit and not home_hit:
        return "X2"
    if home_hit and away_hit and not has_draw:
        return "12"

    if n in ("home or draw", "draw or home"):
        return "1X"
    if n in ("draw or away", "away or draw"):
        return "X2"
    if n in ("home or away", "away or home"):
        return "12"
    return None


def map_market(mkt_name: str, runners: list, home: str = "", away: str = ""):
    """
    Betwatch market adını ve runner listesini (market_key, [(sel_code, runner)])
    formatına dönüştürür.

    Canonical V2 market keys:
      - 1X2: Match Odds
      - DC: Double Chance (optional provider market)
      - DNB: Draw no Bet
      - OU25: Over/Under 2.5 Goals
      - BTTS: Both teams to Score?

    IMPORTANT: Double Chance is optional. If the provider does not expose the
    market, SmartXFlow must not synthesize odds, matched amount or money share.
    """
    name = (mkt_name or "").strip()
    nname = _norm_market_label(name)

    if name == "Match Odds":
        if len(runners) < 2:
            return None, []
        sels = []
        for i, r in enumerate(runners):
            r_name = (r.get("name") or "").lower()
            if "draw" in r_name:
                sels.append(("X", r))
            elif home and _runner_matches_team(r.get("name", ""), home):
                sels.append(("1", r))
            elif away and _runner_matches_team(r.get("name", ""), away):
                sels.append(("2", r))
            elif not sels or (sels and "X" not in [s[0] for s in sels] and i == 0):
                sels.append(("1", r))
            else:
                sels.append(("2", r))
        if len(sels) == 3 and sels[1][0] != "X":
            sels[1] = ("X", sels[1][1])
        return "1X2", sels

    if nname.startswith("double chance"):
        sels = []
        for r in runners:
            code = _double_chance_code(r.get("name", ""), home, away)
            if code:
                sels.append((code, r))
        return ("DC", sels) if sels else (None, [])

    if nname.startswith("draw no bet"):
        sels = []
        for i, r in enumerate(runners):
            label = r.get("name", "")
            if home and _runner_matches_team(label, home):
                sels.append(("1", r))
            elif away and _runner_matches_team(label, away):
                sels.append(("2", r))
            elif i == 0:
                sels.append(("1", r))
            elif i == 1:
                sels.append(("2", r))
        return ("DNB", sels) if len(sels) >= 2 else (None, [])

    if name.startswith("Over/Under 2.5"):
        sels = []
        for r in runners:
            r_name = (r.get("name") or "").lower()
            if "over" in r_name:
                sels.append(("O", r))
            elif "under" in r_name:
                sels.append(("U", r))
        return ("OU25", sels) if sels else (None, [])

    if name == "Both teams to Score?":
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
