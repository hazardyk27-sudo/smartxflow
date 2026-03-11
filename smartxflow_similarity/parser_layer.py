import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from smartxflow_similarity.utils import (
    parse_number, parse_datetime, match_id_hash, is_placeholder_odds
)

MONEYWAY_1X2_ALIASES = {
    "odds1": ["odds1", "odds_1", "home_odds"],
    "oddsx": ["oddsx", "odds_x", "draw_odds"],
    "odds2": ["odds2", "odds_2", "away_odds"],
    "pct1":  ["pct1", "pct_1", "home_pct"],
    "pctx":  ["pctx", "pct_x", "draw_pct"],
    "pct2":  ["pct2", "pct_2", "away_pct"],
    "amt1":  ["amt1", "amt_1", "home_amt"],
    "amtx":  ["amtx", "amt_x", "draw_amt"],
    "amt2":  ["amt2", "amt_2", "away_amt"],
}

MONEYWAY_OU25_ALIASES = {
    "over":     ["over", "odds_over"],
    "under":    ["under", "odds_under"],
    "line":     ["line"],
    "pctover":  ["pctover", "pct_over"],
    "pctunder": ["pctunder", "pct_under"],
    "amtover":  ["amtover", "amt_over"],
    "amtunder": ["amtunder", "amt_under"],
}

MONEYWAY_BTTS_ALIASES = {
    "yes":    ["yes", "odds_yes"],
    "no":     ["no", "odds_no"],
    "pctyes": ["pctyes", "pct_yes"],
    "pctno":  ["pctno", "pct_no"],
    "amtyes": ["amtyes", "amt_yes"],
    "amtno":  ["amtno", "amt_no"],
}

DROPPING_1X2_ALIASES = {
    "odds1":      ["odds1"],
    "oddsx":      ["oddsx"],
    "odds2":      ["odds2"],
    "odds1_prev": ["odds1_prev"],
    "oddsx_prev": ["oddsx_prev"],
    "odds2_prev": ["odds2_prev"],
    "trend1":     ["trend1"],
    "trendx":     ["trendx"],
    "trend2":     ["trend2"],
}

DROPPING_OU25_ALIASES = {
    "over":       ["over"],
    "under":      ["under"],
    "over_prev":  ["over_prev"],
    "under_prev": ["under_prev"],
    "line":       ["line"],
    "trendover":  ["trendover", "trend_over"],
    "trendunder": ["trendunder", "trend_under"],
    "pctover":    ["pctover"],
    "pctunder":   ["pctunder"],
    "amtover":    ["amtover"],
    "amtunder":   ["amtunder"],
}

DROPPING_BTTS_ALIASES = {
    "oddsyes":      ["oddsyes", "odds_yes"],
    "oddsno":       ["oddsno", "odds_no"],
    "oddsyes_prev": ["oddsyes_prev", "odds_yes_prev"],
    "oddsno_prev":  ["oddsno_prev", "odds_no_prev"],
    "trendyes":     ["trendyes", "trend_yes"],
    "trendno":      ["trendno", "trend_no"],
    "pctyes":       ["pctyes"],
    "pctno":        ["pctno"],
    "amtyes":       ["amtyes"],
    "amtno":        ["amtno"],
}

COMMON_ALIASES = {
    "league":       ["league", "lig"],
    "home":         ["home", "ev"],
    "away":         ["away", "deplasman"],
    "date":         ["date", "tarih", "match_date"],
    "volume":       ["volume", "hacim", "total_volume"],
    "scraped_at":   ["scraped_at", "scrape_time", "timestamp"],
    "match_id_hash": ["match_id_hash"],
}

TABLE_ALIAS_MAP = {
    "moneyway_1x2_history":  MONEYWAY_1X2_ALIASES,
    "moneyway_ou25_history": MONEYWAY_OU25_ALIASES,
    "moneyway_btts_history": MONEYWAY_BTTS_ALIASES,
    "dropping_1x2_history":  DROPPING_1X2_ALIASES,
    "dropping_ou25_history": DROPPING_OU25_ALIASES,
    "dropping_btts_history": DROPPING_BTTS_ALIASES,
}


def _resolve_alias(row, canonical, alias_map):
    if canonical in alias_map:
        for alias in alias_map[canonical]:
            if alias in row:
                return row[alias]
    if canonical in row:
        return row[canonical]
    return None


def _resolve_common(row, field):
    return _resolve_alias(row, field, COMMON_ALIASES)


def parse_snapshot_row(row, table_name):
    warnings = []
    table_aliases = TABLE_ALIAS_MAP.get(table_name, {})
    merged_aliases = {**COMMON_ALIASES, **table_aliases}

    result = {}
    for canonical in merged_aliases:
        result[canonical] = _resolve_alias(row, canonical, merged_aliases)

    result["league"] = str(result.get("league") or "").strip()
    result["home"] = str(result.get("home") or "").strip()
    result["away"] = str(result.get("away") or "").strip()
    result["date"] = str(result.get("date") or "").strip()

    vol_raw = result.get("volume")
    result["volume"] = parse_number(vol_raw)

    scraped = result.get("scraped_at")
    result["scraped_at"] = parse_datetime(scraped)

    odds_fields = []
    if table_name == "moneyway_1x2_history":
        odds_fields = ["odds1", "oddsx", "odds2"]
    elif table_name == "moneyway_ou25_history":
        odds_fields = ["over", "under"]
    elif table_name == "moneyway_btts_history":
        odds_fields = ["yes", "no"]
    elif table_name == "dropping_1x2_history":
        odds_fields = ["odds1", "oddsx", "odds2", "odds1_prev", "oddsx_prev", "odds2_prev"]
    elif table_name == "dropping_ou25_history":
        odds_fields = ["over", "under", "over_prev", "under_prev"]
    elif table_name == "dropping_btts_history":
        odds_fields = ["oddsyes", "oddsno", "oddsyes_prev", "oddsno_prev"]

    for f in odds_fields:
        raw = result.get(f)
        parsed = parse_number(raw)
        result[f] = parsed
        if is_placeholder_odds(parsed) and raw is not None:
            warnings.append(f"placeholder_odds:{f}={raw}")

    pct_fields = [k for k in result if k.startswith("pct")]
    amt_fields = [k for k in result if k.startswith("amt")]
    for f in pct_fields + amt_fields:
        result[f] = parse_number(result.get(f))

    trend_fields = [k for k in result if k.startswith("trend")]
    for f in trend_fields:
        val = result.get(f)
        if val is not None:
            result[f] = str(val).strip()

    if result.get("line") is not None:
        result["line"] = parse_number(result["line"])

    if not result["league"] or not result["home"] or not result["away"]:
        warnings.append("missing_match_info")

    if result["scraped_at"] is None:
        warnings.append("missing_scraped_at")

    return result, warnings


def build_canonical_match(match_rows_by_table, kickoff_time=None):
    warnings = []
    meta = {"league": "", "home": "", "away": "", "date": "", "match_id_hash": ""}

    for table_name, rows in match_rows_by_table.items():
        if rows:
            first = rows[0]
            if first.get("league"):
                meta["league"] = first["league"]
            if first.get("home"):
                meta["home"] = first["home"]
            if first.get("away"):
                meta["away"] = first["away"]
            if first.get("date"):
                meta["date"] = first["date"]
            if first.get("match_id_hash"):
                meta["match_id_hash"] = first["match_id_hash"]
            break

    if not meta["match_id_hash"] and meta["league"] and meta["home"] and meta["away"]:
        meta["match_id_hash"] = match_id_hash(meta["league"], meta["home"], meta["away"])

    if kickoff_time is None and meta["date"]:
        kickoff_time = parse_datetime(meta["date"])
    meta["kickoff"] = kickoff_time

    snapshots = {
        "moneyway_1x2": [],
        "moneyway_ou25": [],
        "moneyway_btts": [],
        "dropping_1x2": [],
        "dropping_ou25": [],
        "dropping_btts": [],
    }

    market_key_map = {
        "moneyway_1x2_history":  "moneyway_1x2",
        "moneyway_ou25_history": "moneyway_ou25",
        "moneyway_btts_history": "moneyway_btts",
        "dropping_1x2_history":  "dropping_1x2",
        "dropping_ou25_history": "dropping_ou25",
        "dropping_btts_history": "dropping_btts",
    }

    for table_name, raw_rows in match_rows_by_table.items():
        market_key = market_key_map.get(table_name)
        if not market_key:
            warnings.append(f"unknown_table:{table_name}")
            continue
        for raw_row in raw_rows:
            parsed, row_warnings = parse_snapshot_row(raw_row, table_name)
            warnings.extend(row_warnings)
            snapshots[market_key].append(parsed)

    for key in snapshots:
        snapshots[key].sort(key=lambda x: x.get("scraped_at") or datetime.min)

    total_snapshots = sum(len(v) for v in snapshots.values())
    available_markets = [k for k, v in snapshots.items() if len(v) > 0]
    missing_markets = [k for k, v in snapshots.items() if len(v) == 0]

    if missing_markets:
        warnings.append(f"missing_markets:{','.join(missing_markets)}")

    total_volume = None
    for key in ["moneyway_1x2", "moneyway_ou25", "moneyway_btts"]:
        rows = snapshots[key]
        if rows:
            last = rows[-1]
            v = last.get("volume")
            if v is not None:
                if total_volume is None:
                    total_volume = 0
                total_volume += v

    return {
        "meta": meta,
        "snapshots": snapshots,
        "total_snapshots": total_snapshots,
        "available_markets": available_markets,
        "missing_markets": missing_markets,
        "total_volume": total_volume,
        "warnings": warnings,
    }


def parse_supabase_rows(rows_by_table):
    all_matches = {}
    for table_name, rows in rows_by_table.items():
        for row in rows:
            parsed, _ = parse_snapshot_row(row, table_name)
            mid = parsed.get("match_id_hash") or ""
            if not mid and parsed.get("league") and parsed.get("home") and parsed.get("away"):
                mid = match_id_hash(parsed["league"], parsed["home"], parsed["away"])
            if not mid:
                continue
            if mid not in all_matches:
                all_matches[mid] = {t: [] for t in rows_by_table}
            if table_name not in all_matches[mid]:
                all_matches[mid][table_name] = []
            all_matches[mid][table_name].append(row)

    result = {}
    for mid, tables in all_matches.items():
        result[mid] = build_canonical_match(tables)
    return result
