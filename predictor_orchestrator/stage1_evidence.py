from __future__ import annotations

from datetime import datetime
from typing import Any


_WINDOW_NAMES = ("h24", "h12", "h6", "h3", "h1", "m30", "m15")
_UNDERDOG_ODDS_MIN = 2.90
_UNDERDOG_MIN_VOLUME = 10000.0
_UNDERDOG_MIN_AMOUNT = 5000.0


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _canonical_market(value: Any) -> str:
    raw = str(value or "").upper().strip()
    compact = "".join(ch for ch in raw if ch.isalnum())
    return {
        "1X2": "1X2",
        "MATCHODDS": "1X2",
        "FULLTIMERESULT": "1X2",
        "OU25": "OU2.5",
        "OVERUNDER25": "OU2.5",
        "BTTS": "BTTS",
        "BOTHTEAMSTOSCORE": "BTTS",
        "KG": "BTTS",
    }.get(compact, raw)


def _parse_iso(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _point(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    odds = _number(value.get("odds"))
    share = _number(value.get("share"))
    amount = _number(value.get("amount"))
    if odds is None or share is None or amount is None:
        return None
    return {
        "observed_at": value.get("observed_at"),
        "odds": odds,
        "share": share,
        "amount": amount,
        "volume": _number(value.get("volume")),
    }


def _metrics(start: dict[str, Any] | None, end: dict[str, Any] | None) -> dict[str, Any] | None:
    if not start or not end:
        return None
    start_odds = _number(start.get("odds"))
    end_odds = _number(end.get("odds"))
    start_share = _number(start.get("share"))
    end_share = _number(end.get("share"))
    start_amount = _number(start.get("amount"))
    end_amount = _number(end.get("amount"))
    if None in {start_odds, end_odds, start_share, end_share, start_amount, end_amount}:
        return None
    odds_delta = end_odds - start_odds
    odds_delta_pct = (odds_delta / start_odds * 100.0) if start_odds else None
    implied_start = (100.0 / start_odds) if start_odds and start_odds > 0 else None
    implied_end = (100.0 / end_odds) if end_odds and end_odds > 0 else None
    amount_delta = end_amount - start_amount
    amount_delta_pct = (amount_delta / start_amount * 100.0) if start_amount else None
    start_volume = _number(start.get("volume"))
    end_volume = _number(end.get("volume"))
    volume_delta = None if start_volume is None or end_volume is None else end_volume - start_volume
    hours = None
    start_at = _parse_iso(start.get("observed_at"))
    end_at = _parse_iso(end.get("observed_at"))
    if start_at is not None and end_at is not None:
        seconds = (end_at - start_at).total_seconds()
        if seconds > 0:
            hours = seconds / 3600.0
    return {
        "odds_delta": round(odds_delta, 4),
        "odds_delta_pct": None if odds_delta_pct is None else round(odds_delta_pct, 2),
        "implied_probability_delta_pp": None if implied_start is None or implied_end is None else round(implied_end - implied_start, 2),
        "share_delta_pp": round(end_share - start_share, 2),
        "amount_delta": round(amount_delta, 2),
        "amount_delta_pct": None if amount_delta_pct is None else round(amount_delta_pct, 2),
        "volume_delta": None if volume_delta is None else round(volume_delta, 2),
        "elapsed_hours": None if hours is None else round(hours, 3),
        "amount_velocity_per_hour": None if hours is None else round(amount_delta / hours, 2),
    }


def _selection_evidence(feature: Any) -> dict[str, Any] | None:
    if not isinstance(feature, dict):
        return None
    first = _point(feature.get("first"))
    last = _point(feature.get("last"))
    if last is None:
        return None
    windows: dict[str, Any] = {}
    for name in _WINDOW_NAMES:
        start = _point(feature.get(name))
        if start is None:
            windows[name] = None
            continue
        windows[name] = {
            "from": start,
            "to": last,
            "metrics": _metrics(start, last),
        }
    odds_range = feature.get("odds_range")
    if not isinstance(odds_range, list) or len(odds_range) != 2:
        odds_range = [None, None]
    return {
        "history_count": int(feature.get("history_count") or 0),
        "first": first,
        "last": last,
        "odds_range": [_number(odds_range[0]), _number(odds_range[1])],
        "reversal_segments": int(feature.get("reversal_segments") or 0),
        "latest_age_seconds": int(feature.get("latest_age_seconds") or 0),
        "open_to_latest": _metrics(first, last) if first is not None else None,
        "windows": windows,
    }


def _liquidity_band(volume: float | None) -> str:
    if volume is None or volume < 5000.0:
        return "LOW"
    if volume < 10000.0:
        return "LIMITED"
    if volume < 25000.0:
        return "NORMAL"
    return "STRONG"


def _persistent_price_move(selected: dict[str, Any]) -> tuple[bool, int]:
    open_metrics = selected.get("open_to_latest") if isinstance(selected.get("open_to_latest"), dict) else {}
    overall = _number(open_metrics.get("odds_delta_pct"))
    if overall is None or abs(overall) < 1.0 or int(selected.get("history_count") or 0) < 3:
        return False, 0
    direction = 1 if overall > 0 else -1
    supporting_points: set[str] = set()
    windows = selected.get("windows") if isinstance(selected.get("windows"), dict) else {}
    for name in _WINDOW_NAMES:
        item = windows.get(name)
        if not isinstance(item, dict):
            continue
        metrics = item.get("metrics") if isinstance(item.get("metrics"), dict) else {}
        move = _number(metrics.get("odds_delta_pct"))
        source = item.get("from") if isinstance(item.get("from"), dict) else {}
        observed_at = str(source.get("observed_at") or "").strip()
        if move is None or not observed_at:
            continue
        if direction * move >= 0.5:
            supporting_points.add(observed_at)
    persistent = len(supporting_points) >= 2 and int(selected.get("reversal_segments") or 0) <= 2
    return persistent, len(supporting_points)


def _market_quality(selected: dict[str, Any], *, market: str, selection: str) -> dict[str, Any]:
    last = selected.get("last") if isinstance(selected.get("last"), dict) else {}
    latest_volume = _number(last.get("volume"))
    latest_amount = _number(last.get("amount"))
    latest_share = _number(last.get("share"))
    latest_odds = _number(last.get("odds"))
    band = _liquidity_band(latest_volume)

    if band in {"LOW", "LIMITED"}:
        evidence_weight = "LOW"
    elif band == "NORMAL":
        evidence_weight = "NORMAL" if (latest_amount or 0.0) >= 5000.0 else "LOW"
    else:
        evidence_weight = "STRONG" if (latest_amount or 0.0) >= 10000.0 else "NORMAL"

    persistent, supporting_windows = _persistent_price_move(selected)
    open_metrics = selected.get("open_to_latest") if isinstance(selected.get("open_to_latest"), dict) else {}
    odds_move = abs(_number(open_metrics.get("odds_delta_pct")) or 0.0)
    amount_delta = abs(_number(open_metrics.get("amount_delta")) or 0.0)
    share_only_risk = odds_move < 1.0 and amount_delta < 1000.0 and (latest_amount or 0.0) < 5000.0

    underdog_status = "NOT_UNDERDOG"
    is_1x2_side = market == "1X2" and selection in {"Home", "Away"}
    if is_1x2_side and latest_odds is not None and latest_odds >= _UNDERDOG_ODDS_MIN:
        if (
            (latest_volume or 0.0) >= _UNDERDOG_MIN_VOLUME
            and (latest_amount or 0.0) >= _UNDERDOG_MIN_AMOUNT
            and persistent
        ):
            underdog_status = "QUALIFIED"
        else:
            underdog_status = "LOW_CONFIDENCE_MARKET_MOVE"

    return {
        "latest_volume": latest_volume,
        "latest_amount": latest_amount,
        "latest_share": latest_share,
        "latest_odds": latest_odds,
        "liquidity_band": band,
        "evidence_weight": evidence_weight,
        "persistent_price_move": persistent,
        "persistence_supporting_windows": supporting_windows,
        "share_only_risk": share_only_risk,
        "underdog_status": underdog_status,
        "thresholds": {
            "liquidity_low_lt": 5000.0,
            "liquidity_limited_lt": 10000.0,
            "liquidity_normal_lt": 25000.0,
            "underdog_odds_min": _UNDERDOG_ODDS_MIN,
            "underdog_min_volume": _UNDERDOG_MIN_VOLUME,
            "underdog_min_amount": _UNDERDOG_MIN_AMOUNT,
        },
    }


def build_stage1_evidence(
    context: dict[str, Any],
    *,
    fixture_id: str,
    market: str,
    selection: str,
) -> dict[str, Any] | None:
    fixture: dict[str, Any] | None = None
    for item in context.get("fixtures") or []:
        if not isinstance(item, dict):
            continue
        current_id = str(item.get("fixture_id") or item.get("fixture_uid") or item.get("match_id_hash") or "").strip()
        if current_id == fixture_id:
            fixture = item
            break
    if fixture is None:
        return None

    canonical_market = _canonical_market(market)
    markets = fixture.get("markets") if isinstance(fixture.get("markets"), dict) else {}
    market_rows = markets.get(canonical_market) if isinstance(markets.get(canonical_market), dict) else {}
    selected_feature = market_rows.get(selection)
    selected = _selection_evidence(selected_feature)
    if selected is None:
        return None

    market_comparison: list[dict[str, Any]] = []
    for name, feature in market_rows.items():
        evidence = _selection_evidence(feature)
        if evidence is None:
            continue
        market_comparison.append(
            {
                "selection": str(name),
                "first": evidence["first"],
                "last": evidence["last"],
                "open_to_latest": evidence["open_to_latest"],
                "history_count": evidence["history_count"],
            }
        )

    cross_market_snapshot: list[dict[str, Any]] = []
    for other_market, selections in markets.items():
        if not isinstance(selections, dict):
            continue
        for name, feature in selections.items():
            evidence = _selection_evidence(feature)
            if evidence is None:
                continue
            cross_market_snapshot.append(
                {
                    "market": str(other_market),
                    "selection": str(name),
                    "last": evidence["last"],
                    "open_to_latest": evidence["open_to_latest"],
                    "history_count": evidence["history_count"],
                }
            )

    return {
        "source": "SXF_PRODUCTION_READ_ONLY",
        "fixture_id": fixture_id,
        "market": canonical_market,
        "selection": selection,
        "selected_selection": selected,
        "market_quality": _market_quality(selected, market=canonical_market, selection=selection),
        "market_comparison": market_comparison,
        "cross_market_snapshot": cross_market_snapshot,
    }
