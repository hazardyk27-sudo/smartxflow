from __future__ import annotations

import time
import traceback
import urllib.parse
from datetime import timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

import alarm_calculator_legacy as _legacy
from alarm_recent_base import (
    PAGE_SIZE,
    MAX_ROWS,
    SIGNAL_PAD_MINUTES,
    _BIG_MARKET,
    _BIG_SELECTION,
    _as_bool,
    _dt,
    _iso_z,
    _load_fixtures,
    _load_previous_signals,
)
from alarm_recent_part2 import EXPECTED_SELECTIONS, _market_min_volume

SHARP_PREVIOUS_SIGNALS = 21
OPENING_BATCH_SIZE = 80
OPENING_QUERY_LIMIT = 2000
CLEANUP_INTERVAL_SECONDS = 3600


def _effective_config(calculator: Any, alarm_type: str) -> Dict[str, Any]:
    defaults = dict(calculator._default_configs().get(alarm_type, {}))
    live = calculator.configs.get(alarm_type) or {}
    for key, value in live.items():
        if value is not None:
            defaults[key] = value
    return defaults


def _fetch_rows(
    calculator: Any,
    start_dt,
    end_dt,
) -> List[Dict[str, Any]]:
    select = "match_id_hash,market,selection,volume,share,odds,scraped_at_utc"
    rows: List[Dict[str, Any]] = []
    offset = 0
    while offset < MAX_ROWS:
        page = calculator._get(
            "moneyway_snapshots",
            f"select={select}"
            f"&scraped_at_utc=gte.{_iso_z(start_dt)}"
            f"&scraped_at_utc=lte.{_iso_z(end_dt)}"
            "&order=scraped_at_utc.asc"
            f"&limit={PAGE_SIZE}&offset={offset}",
        ) or []
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    if len(rows) >= MAX_ROWS:
        _legacy.log(f"[Alarm Incremental] safety cap reached: {MAX_ROWS} snapshot rows")
    return rows


def _group_snapshot_rows(
    rows: Iterable[Dict[str, Any]],
    max_per_key: Optional[int] = None,
) -> Tuple[
    Dict[Tuple[str, str, str], List[Dict[str, Any]]],
    Dict[Tuple[str, str], List[Tuple[str, Dict[str, Dict[str, Any]]]]],
]:
    by_key: Dict[Tuple[str, str, str], Dict[str, Dict[str, Any]]] = {}
    market_states: Dict[Tuple[str, str], Dict[str, Dict[str, Dict[str, Any]]]] = {}

    for row in rows:
        match_hash = str(row.get("match_id_hash") or "")
        market = str(row.get("market") or "")
        selection = str(row.get("selection") or "")
        ts = str(row.get("scraped_at_utc") or "")
        if not match_hash or market not in EXPECTED_SELECTIONS or selection not in EXPECTED_SELECTIONS[market] or not ts:
            continue
        by_key.setdefault((match_hash, market, selection), {})[ts] = row
        market_states.setdefault((match_hash, market), {}).setdefault(ts, {})[selection] = row

    series: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
    for key, by_ts in by_key.items():
        ordered = [by_ts[ts] for ts in sorted(by_ts)]
        if max_per_key is not None:
            ordered = ordered[-max_per_key:]
        if ordered:
            series[key] = ordered

    complete_states: Dict[Tuple[str, str], List[Tuple[str, Dict[str, Dict[str, Any]]]]] = {}
    for market_key, states in market_states.items():
        market = market_key[1]
        expected = set(EXPECTED_SELECTIONS[market])
        complete = []
        for ts in sorted(states):
            state = states[ts]
            if set(state) >= expected:
                complete.append((ts, {sel: state[sel] for sel in EXPECTED_SELECTIONS[market]}))
        if complete:
            complete_states[market_key] = complete
    return series, complete_states


def _latest_market_state(
    states: Dict[Tuple[str, str], List[Tuple[str, Dict[str, Dict[str, Any]]]]],
    match_hash: str,
    market: str,
    timestamp: str,
) -> Optional[Dict[str, Dict[str, Any]]]:
    for ts, state in reversed(states.get((match_hash, market)) or []):
        if ts == timestamp:
            return state
    return None


def _current_market_total(state: Optional[Dict[str, Dict[str, Any]]]) -> float:
    if not state:
        return 0.0
    return sum(_legacy.parse_volume(row.get("volume")) for row in state.values())


def _fetch_sharp_window(calculator: Any) -> Dict[str, Any]:
    signal = getattr(calculator, "_active_signal", None)
    if not isinstance(signal, dict):
        raise RuntimeError("Sharp incremental mode requires an active scraper signal")
    cache_key = str(signal.get("id") or signal.get("created_at") or "")
    cached = getattr(calculator, "_sharp_snapshot_cache", None)
    if isinstance(cached, dict) and cached.get("cache_key") == cache_key:
        return cached

    current_dt = _dt(signal.get("created_at"))
    if current_dt is None:
        raise RuntimeError("Sharp signal created_at is invalid")
    previous = _load_previous_signals(calculator, signal, count=SHARP_PREVIOUS_SIGNALS)
    previous_times = [_dt(row.get("created_at")) for row in previous]
    previous_times = [value for value in previous_times if value is not None]
    immediate_previous = previous_times[0] if previous_times else None
    start_dt = (
        min(previous_times) - timedelta(minutes=SIGNAL_PAD_MINUTES)
        if previous_times
        else current_dt - timedelta(hours=4)
    )

    rows = _fetch_rows(calculator, start_dt, current_dt)
    series, states = _group_snapshot_rows(rows, max_per_key=21)
    current_keys = set()
    for key, key_rows in series.items():
        latest_dt = _dt(key_rows[-1].get("scraped_at_utc"))
        if latest_dt is not None and (immediate_previous is None or latest_dt > immediate_previous):
            current_keys.add(key)
    fixtures = _load_fixtures(calculator, (key[0] for key in current_keys))
    payload = {
        "cache_key": cache_key,
        "series": series,
        "states": states,
        "current_keys": current_keys,
        "fixtures": fixtures,
        "rows_loaded": len(rows),
    }
    calculator._sharp_snapshot_cache = payload
    _legacy.log(
        f"[Sharp Incremental] rows={len(rows)} series={len(series)} changed={len(current_keys)}"
    )
    return payload


def _odds_bucket(config: Dict[str, Any], current_odds: float) -> Tuple[float, float]:
    base = _legacy.parse_float(config.get("odds_multiplier")) or 1.0
    for idx in range(1, 5):
        low = _legacy.parse_float(config.get(f"odds_range_{idx}_min"))
        high = _legacy.parse_float(config.get(f"odds_range_{idx}_max")) or 99.0
        mult = _legacy.parse_float(config.get(f"odds_range_{idx}_mult")) or base
        min_drop = _legacy.parse_float(config.get(f"odds_range_{idx}_min_drop"))
        if low <= current_odds <= high:
            return mult, min_drop
    return base, 0.0


def _share_multiplier(config: Dict[str, Any], current_share: float) -> float:
    base = _legacy.parse_float(config.get("share_multiplier")) or 1.0
    for idx in range(1, 5):
        low = _legacy.parse_float(config.get(f"share_range_{idx}_min"))
        high = _legacy.parse_float(config.get(f"share_range_{idx}_max")) or 100.0
        if low <= current_share <= high:
            return _legacy.parse_float(config.get(f"share_range_{idx}_mult")) or base
    return base


def _sharp_candidate(
    config: Dict[str, Any],
    rows: List[Dict[str, Any]],
    current_market_volume: float,
) -> Optional[Dict[str, float]]:
    if len(rows) < 2:
        return None
    current = rows[-1]
    previous = rows[-2]
    current_odds = _legacy.parse_float(current.get("odds"))
    previous_odds = _legacy.parse_float(previous.get("odds"))
    if current_odds <= 0 or previous_odds <= 0:
        return None

    current_amount = _legacy.parse_volume(current.get("volume"))
    previous_amount = _legacy.parse_volume(previous.get("volume"))
    amount_change = current_amount - previous_amount
    min_amount_change = _legacy.parse_float(config.get("min_amount_change"))
    if amount_change <= 0 or amount_change < min_amount_change:
        return None

    min_share = _legacy.parse_float(config.get("min_share"))
    current_share = _legacy.parse_float(current.get("share"))
    previous_share = _legacy.parse_float(previous.get("share"))
    if min_share > 0 and current_share < min_share:
        return None

    prior_amounts = [_legacy.parse_volume(row.get("volume")) for row in rows[-21:-1]]
    non_zero = [amount for amount in prior_amounts if amount > 0]
    if non_zero:
        avg_last_amounts = sum(non_zero) / len(non_zero)
    elif previous_amount > 0:
        avg_last_amounts = previous_amount
    else:
        avg_last_amounts = 1000.0

    volume_multiplier = _legacy.parse_float(config.get("volume_multiplier")) or 1.0
    max_volume_cap = _legacy.parse_float(config.get("max_volume_cap")) or 40.0
    shock_raw = amount_change / avg_last_amounts
    shock_value = shock_raw * volume_multiplier
    volume_contrib = min(shock_value, max_volume_cap)

    drop_pct = ((previous_odds - current_odds) / previous_odds) * 100.0
    if drop_pct <= 0:
        return None
    odds_multiplier, min_drop = _odds_bucket(config, current_odds)
    if min_drop > 0 and drop_pct < min_drop:
        return None
    max_odds_cap = _legacy.parse_float(config.get("max_odds_cap")) or 10.0
    odds_value = drop_pct * odds_multiplier
    odds_contrib = min(odds_value, max_odds_cap)

    share_diff = current_share - previous_share
    share_multiplier = _share_multiplier(config, current_share)
    share_value = share_diff * share_multiplier
    max_share_cap = _legacy.parse_float(config.get("max_share_cap")) or 10.0
    share_contrib = min(max(0.0, share_value), max_share_cap)
    sharp_score = volume_contrib + odds_contrib + share_contrib
    min_score = _legacy.parse_float(config.get("min_sharp_score"))
    if sharp_score < min_score:
        return None

    return {
        "amount_change": amount_change,
        "avg_last_amounts": avg_last_amounts,
        "shock_raw": shock_raw,
        "volume_multiplier": volume_multiplier,
        "shock_value": shock_value,
        "max_volume_cap": max_volume_cap,
        "volume_contrib": volume_contrib,
        "previous_odds": previous_odds,
        "current_odds": current_odds,
        "drop_pct": drop_pct,
        "odds_multiplier_base": _legacy.parse_float(config.get("odds_multiplier")) or 1.0,
        "odds_multiplier_bucket": odds_multiplier,
        "odds_multiplier": odds_multiplier,
        "odds_value": odds_value,
        "max_odds_cap": max_odds_cap,
        "odds_contrib": odds_contrib,
        "previous_share": previous_share,
        "current_share": current_share,
        "share_diff": share_diff,
        "share_multiplier": share_multiplier,
        "share_value": share_value,
        "max_share_cap": max_share_cap,
        "share_contrib": share_contrib,
        "sharp_score": sharp_score,
        "current_market_volume": current_market_volume,
    }


def _sharp_incremental(calculator: Any) -> int:
    started = time.monotonic()
    config = _effective_config(calculator, "sharp")
    if not _as_bool(config.get("enabled"), True):
        _legacy.log("[Sharp Incremental] disabled")
        return 0
    window = _fetch_sharp_window(calculator)
    alarms = []
    for key in window["current_keys"]:
        match_hash, market, selection = key
        rows = window["series"].get(key) or []
        if len(rows) < 2:
            continue
        current_ts = str(rows[-1].get("scraped_at_utc") or "")
        state = _latest_market_state(window["states"], match_hash, market, current_ts)
        total_volume = _current_market_total(state)
        if total_volume < _market_min_volume(config, market):
            continue
        candidate = _sharp_candidate(config, rows, total_volume)
        if not candidate:
            continue
        fixture = window["fixtures"].get(match_hash)
        if not fixture:
            continue
        display_market = _BIG_MARKET.get(market, market)
        display_selection = _BIG_SELECTION.get((market, selection), selection)
        alarm = {
            "match_id_hash": match_hash,
            "home": fixture.get("home_team", ""),
            "away": fixture.get("away_team", ""),
            "league": fixture.get("league", ""),
            "market": display_market,
            "selection": display_selection,
            "match_date": fixture.get("fixture_date") or "",
            "trigger_at": current_ts,
            "created_at": _legacy.now_turkey_iso(),
            "alarm_type": "sharp",
        }
        for field, value in candidate.items():
            if field == "current_market_volume":
                continue
            alarm[field] = round(value, 4) if field == "shock_raw" else round(value, 2)
        alarms.append(alarm)

    if not alarms:
        _legacy.log(
            f"[Sharp Incremental] 0 alarm | rows={window['rows_loaded']} elapsed={time.monotonic()-started:.3f}s"
        )
        return 0
    count = calculator._upsert_alarms("sharp_alarms", alarms, ["match_id_hash", "market", "selection"])
    _legacy.log(
        f"[Sharp Incremental] upserted={count} rows={window['rows_loaded']} elapsed={time.monotonic()-started:.3f}s"
    )
    return count


def _fetch_dropping_window(calculator: Any, persistence_minutes: float) -> Dict[str, Any]:
    signal = getattr(calculator, "_active_signal", None)
    if not isinstance(signal, dict):
        raise RuntimeError("Dropping incremental mode requires an active scraper signal")
    cache_key = f"{signal.get('id') or signal.get('created_at')}:{persistence_minutes:.3f}"
    cached = getattr(calculator, "_dropping_snapshot_cache", None)
    if isinstance(cached, dict) and cached.get("cache_key") == cache_key:
        return cached

    current_dt = _dt(signal.get("created_at"))
    if current_dt is None:
        raise RuntimeError("Dropping signal created_at is invalid")
    previous = _load_previous_signals(calculator, signal, count=2)
    previous_times = [_dt(row.get("created_at")) for row in previous]
    previous_times = [value for value in previous_times if value is not None]
    immediate_previous = previous_times[0] if previous_times else None
    lookback_minutes = max(60.0, float(persistence_minutes) + 30.0)
    start_dt = current_dt - timedelta(minutes=lookback_minutes)
    rows = _fetch_rows(calculator, start_dt, current_dt)
    series, states = _group_snapshot_rows(rows, max_per_key=None)

    current_keys = set()
    for key, key_rows in series.items():
        latest_dt = _dt(key_rows[-1].get("scraped_at_utc"))
        if latest_dt is not None and (immediate_previous is None or latest_dt > immediate_previous):
            current_keys.add(key)
    fixtures = _load_fixtures(calculator, (key[0] for key in current_keys))
    payload = {
        "cache_key": cache_key,
        "series": series,
        "states": states,
        "current_keys": current_keys,
        "fixtures": fixtures,
        "rows_loaded": len(rows),
    }
    calculator._dropping_snapshot_cache = payload
    _legacy.log(
        f"[Dropping Incremental] rows={len(rows)} series={len(series)} changed={len(current_keys)} lookback={lookback_minutes:.0f}m"
    )
    return payload


def _fetch_opening_odds(
    calculator: Any,
    keys: Iterable[Tuple[str, str, str]],
) -> Dict[Tuple[str, str, str], float]:
    cache = getattr(calculator, "_dropping_opening_cache", None)
    if not isinstance(cache, dict):
        cache = {}
        calculator._dropping_opening_cache = cache
    requested = set(keys)
    missing_hashes = sorted({key[0] for key in requested if key not in cache})
    for start in range(0, len(missing_hashes), OPENING_BATCH_SIZE):
        chunk = missing_hashes[start:start + OPENING_BATCH_SIZE]
        if not chunk:
            continue
        rows = calculator._get(
            "moneyway_snapshots",
            "select=match_id_hash,market,selection,odds,scraped_at_utc"
            f"&match_id_hash=in.({','.join(chunk)})"
            "&odds=gt.0&order=scraped_at_utc.asc"
            f"&limit={OPENING_QUERY_LIMIT}",
        ) or []
        for row in rows:
            key = (
                str(row.get("match_id_hash") or ""),
                str(row.get("market") or ""),
                str(row.get("selection") or ""),
            )
            odds = _legacy.parse_float(row.get("odds"))
            if key in requested and odds > 0 and key not in cache:
                cache[key] = odds
    return cache


def _median_odds(rows: List[Dict[str, Any]]) -> float:
    values = [_legacy.parse_float(row.get("odds")) for row in rows]
    values = sorted(value for value in values if value > 0)
    if not values:
        return 0.0
    return values[len(values) // 2]


def _persistence_ok(
    rows: List[Dict[str, Any]],
    opening_odds: float,
    min_drop_pct: float,
    persistence_minutes: float,
) -> bool:
    if persistence_minutes <= 0:
        return True
    ordered = sorted(rows, key=lambda row: str(row.get("scraped_at_utc") or ""))
    rolling: List[float] = []
    points: List[Tuple[Any, float]] = []
    for row in ordered:
        odds = _legacy.parse_float(row.get("odds"))
        ts = _dt(row.get("scraped_at_utc"))
        if odds <= 0 or ts is None:
            continue
        rolling.append(odds)
        median = sorted(rolling[-3:])[len(rolling[-3:]) // 2]
        drop_pct = ((opening_odds - median) / opening_odds) * 100.0
        points.append((ts, drop_pct))
    if len(points) < 2:
        return False
    latest_ts = points[-1][0]
    cutoff = latest_ts - timedelta(minutes=float(persistence_minutes))
    anchors = [point for point in points if point[0] <= cutoff]
    if not anchors or anchors[-1][1] < min_drop_pct:
        return False
    inside = [point for point in points if cutoff < point[0] <= latest_ts]
    return bool(inside) and all(drop >= min_drop_pct for _, drop in inside)


def _dropping_eval(
    rows: List[Dict[str, Any]],
    opening_odds: float,
    config: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if opening_odds <= 0 or len(rows) < 2:
        return None
    current_odds = _median_odds(rows[-3:])
    previous_odds = _median_odds(rows[:-1][-3:]) or current_odds
    if current_odds <= 0:
        return None
    l1 = _legacy.parse_float(config.get("min_drop_l1"))
    l2 = _legacy.parse_float(config.get("min_drop_l2"))
    l3 = _legacy.parse_float(config.get("min_drop_l3"))
    current_drop = ((opening_odds - current_odds) / opening_odds) * 100.0 if current_odds < opening_odds else 0.0
    previous_drop = ((opening_odds - previous_odds) / opening_odds) * 100.0 if previous_odds < opening_odds else 0.0
    recovered = current_drop < l1 and previous_drop < l1
    if current_drop < l1:
        return {
            "qualifies": False,
            "recovered": recovered,
            "current_odds": current_odds,
            "drop_pct": current_drop,
        }
    if current_drop >= l3:
        level = "L3"
    elif current_drop >= l2:
        level = "L2"
    else:
        level = "L1"
    if level == "L2" and not _as_bool(config.get("l2_enabled"), True):
        return {"qualifies": False, "recovered": False, "level": level}
    if level == "L3" and not _as_bool(config.get("l3_enabled"), True):
        return {"qualifies": False, "recovered": False, "level": level}
    persistence_enabled = _as_bool(config.get("persistence_enabled"), True)
    persistence_minutes = _legacy.parse_float(config.get("persistence_minutes"))
    if persistence_enabled and not _persistence_ok(rows, opening_odds, l1, persistence_minutes):
        return {"qualifies": False, "recovered": False, "level": level}
    return {
        "qualifies": True,
        "recovered": False,
        "level": level,
        "current_odds": current_odds,
        "drop_pct": current_drop,
    }


def _existing_by_hash(
    calculator: Any,
    table: str,
    fields: str,
    hashes: Iterable[str],
) -> List[Dict[str, Any]]:
    ordered = sorted({str(value) for value in hashes if value})
    rows: List[Dict[str, Any]] = []
    for start in range(0, len(ordered), 80):
        chunk = ordered[start:start + 80]
        if chunk:
            rows.extend(
                calculator._get(
                    table,
                    f"select={fields}&match_id_hash=in.({','.join(chunk)})&limit=5000",
                ) or []
            )
    return rows


def _dropping_incremental(calculator: Any) -> int:
    started = time.monotonic()
    config = _effective_config(calculator, "dropping")
    if not _as_bool(config.get("enabled"), True):
        _legacy.log("[Dropping Incremental] disabled")
        return 0
    persistence_minutes = _legacy.parse_float(config.get("persistence_minutes"))
    if persistence_minutes < 0:
        return 0
    window = _fetch_dropping_window(calculator, persistence_minutes)
    openings = _fetch_opening_odds(calculator, window["current_keys"])
    hashes = {key[0] for key in window["current_keys"]}
    existing = _existing_by_hash(
        calculator,
        "dropping_alarms",
        "match_id_hash,market,selection,opening_odds,current_odds,drop_pct,level,trigger_at",
        hashes,
    )
    existing_map = {
        (str(row.get("match_id_hash") or ""), str(row.get("market") or ""), str(row.get("selection") or "")): row
        for row in existing
    }
    alarms = []
    recovered = []
    max_odds = {
        "1X2": _legacy.parse_float(config.get("max_odds_1x2")) or 999.0,
        "OU25": _legacy.parse_float(config.get("max_odds_ou25")) or 999.0,
        "BTTS": _legacy.parse_float(config.get("max_odds_btts")) or 999.0,
    }

    for key in window["current_keys"]:
        match_hash, market, selection = key
        rows = window["series"].get(key) or []
        opening_odds = openings.get(key, 0.0)
        if opening_odds <= 0 or opening_odds > max_odds.get(market, 999.0):
            continue
        current_ts = str(rows[-1].get("scraped_at_utc") or "") if rows else ""
        state = _latest_market_state(window["states"], match_hash, market, current_ts)
        total_volume = _current_market_total(state)
        if total_volume < _market_min_volume(config, market):
            continue
        result = _dropping_eval(rows, opening_odds, config)
        if not result:
            continue
        display_market = _BIG_MARKET.get(market, market)
        display_selection = _BIG_SELECTION.get((market, selection), selection)
        db_key = (match_hash, display_market, display_selection)
        if result.get("recovered"):
            if db_key in existing_map:
                recovered.append(db_key)
            continue
        if not result.get("qualifies"):
            continue
        fixture = window["fixtures"].get(match_hash)
        if not fixture:
            continue
        alarms.append({
            "match_id_hash": match_hash,
            "home": fixture.get("home_team", ""),
            "away": fixture.get("away_team", ""),
            "league": fixture.get("league", ""),
            "market": display_market,
            "selection": display_selection,
            "opening_odds": round(opening_odds, 2),
            "current_odds": round(float(result["current_odds"]), 2),
            "drop_pct": round(float(result["drop_pct"]), 2),
            "level": result["level"],
            "match_date": fixture.get("fixture_date") or "",
            "trigger_at": current_ts,
            "created_at": _legacy.now_turkey_iso(),
            "alarm_type": "dropping",
        })

    count = 0
    if alarms:
        count = calculator._upsert_alarms(
            "dropping_alarms",
            alarms,
            ["match_id_hash", "market", "selection"],
        )
    deleted = 0
    for match_hash, market, selection in recovered:
        params = (
            f"match_id_hash=eq.{match_hash}"
            f"&market=eq.{urllib.parse.quote(market, safe='')}"
            f"&selection=eq.{urllib.parse.quote(selection, safe='')}"
        )
        if calculator._delete("dropping_alarms", params):
            deleted += 1
    _legacy.log(
        f"[Dropping Incremental] upserted={count} recovered={deleted} "
        f"opening_cache={len(getattr(calculator, '_dropping_opening_cache', {}))} "
        f"elapsed={time.monotonic()-started:.3f}s"
    )
    return count


def _run_all_incremental(calculator: Any) -> int:
    """Run all six alarms without legacy full-table/history prefetch."""
    started = time.monotonic()
    _legacy.log("=" * 50)
    _legacy.log("[ALARM INCREMENTAL] SIX-ALARM CALCULATION STARTED")
    calculator.refresh_configs()
    calculator._history_cache = {}
    calculator._matches_cache = {}
    calculator._active_hashes_checked = False
    calculator._active_hashes_cache = []

    steps = [
        ("BigMoney", calculator.calculate_bigmoney_alarms),
        ("Sharp", calculator.calculate_sharp_alarms),
        ("VolumeShock", calculator.calculate_volumeshock_alarms),
        ("Dropping", calculator.calculate_dropping_alarms),
        ("VolumeLeader", calculator.calculate_volumeleader_alarms),
        ("MIM", calculator.calculate_mim_alarms),
    ]
    total = 0
    counts: Dict[str, int] = {}
    for name, method in steps:
        step_started = time.monotonic()
        try:
            count = int(method() or 0)
        except Exception as exc:
            count = 0
            _legacy.log(f"!!! {name} incremental error: {exc}")
            _legacy.log(traceback.format_exc())
        counts[name] = count
        total += count
        _legacy.log(f"[ALARM INCREMENTAL] {name}={count} ({time.monotonic()-step_started:.3f}s)")

    now_mono = time.monotonic()
    last_cleanup = float(getattr(calculator, "_incremental_cleanup_at", 0.0) or 0.0)
    if now_mono - last_cleanup >= CLEANUP_INTERVAL_SECONDS:
        try:
            calculator._cleanup_expired_match_alarms()
            calculator._incremental_cleanup_at = now_mono
        except Exception as exc:
            _legacy.log(f"[ALARM INCREMENTAL] cleanup error: {exc}")

    calculator.last_alarm_count = total
    calculator.alarm_summary = counts
    calculator._history_cache.clear()
    calculator._matches_cache.clear()
    calculator._active_hashes_cache = []
    calculator._active_hashes_checked = False
    _legacy.log(
        f"[ALARM INCREMENTAL] COMPLETE total={total} elapsed={time.monotonic()-started:.3f}s "
        + ", ".join(f"{name}={count}" for name, count in counts.items())
    )
    _legacy.log("=" * 50)
    return total


def install_part3_alarm_overrides(calculator_cls: Any) -> None:
    if getattr(calculator_cls, "_part3_alarm_overrides_installed", False):
        return
    original_sharp = calculator_cls.calculate_sharp_alarms
    original_dropping = calculator_cls.calculate_dropping_alarms
    original_run_all = calculator_cls.run_all_calculations

    def sharp(self: Any) -> int:
        if not isinstance(getattr(self, "_active_signal", None), dict):
            return original_sharp(self)
        return _sharp_incremental(self)

    def dropping(self: Any) -> int:
        if not isinstance(getattr(self, "_active_signal", None), dict):
            return original_dropping(self)
        return _dropping_incremental(self)

    def run_all(self: Any) -> int:
        if not isinstance(getattr(self, "_active_signal", None), dict):
            return original_run_all(self)
        return _run_all_incremental(self)

    calculator_cls.calculate_sharp_alarms = sharp
    calculator_cls.calculate_dropping_alarms = dropping
    calculator_cls.run_all_calculations = run_all
    calculator_cls._part3_alarm_overrides_installed = True


def clear_part3_alarm_cache(calculator: Any) -> None:
    # Opening odds are immutable for an active fixture and intentionally survive
    # signal cycles. Only per-signal windows are cleared.
    for name in ("_sharp_snapshot_cache", "_dropping_snapshot_cache"):
        if hasattr(calculator, name):
            try:
                delattr(calculator, name)
            except Exception:
                setattr(calculator, name, None)
