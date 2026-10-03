from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import alarm_calculator_legacy as _legacy
from alarm_recent_base import (
    PAGE_SIZE,
    MAX_ROWS,
    SIGNAL_PAD_MINUTES,
    _BIG_MARKET,
    _BIG_SELECTION,
    _as_bool,
    _dedupe_history,
    _dt,
    _iso_z,
    _load_fixtures,
    _load_previous_signals,
    _parse_history,
)

PART2_PREVIOUS_SIGNALS = 5
EXPECTED_SELECTIONS = {
    "1X2": ("1", "X", "2"),
    "OU25": ("O", "U"),
    "BTTS": ("Y", "N"),
}


def _effective_config(calculator: Any, alarm_type: str) -> Dict[str, Any]:
    defaults = dict(calculator._default_configs().get(alarm_type, {}))
    live = calculator.configs.get(alarm_type) or {}
    aliases = {
        "volumeshock": {
            "hacim_soku_min_esik": ("volume_shock_multiplier",),
            "hacim_soku_min_saat": ("min_hours",),
            "min_son_snapshot_para": ("min_incoming",),
        }
    }
    for canonical, alias_keys in aliases.get(alarm_type, {}).items():
        if live.get(canonical) is None:
            for alias in alias_keys:
                if live.get(alias) is not None:
                    defaults[canonical] = live[alias]
                    break
    for key, value in live.items():
        if value is not None:
            defaults[key] = value
    return defaults


def _market_min_volume(config: Dict[str, Any], market: str) -> float:
    if market == "1X2":
        return _legacy.parse_float(config.get("min_volume_1x2"))
    if market == "OU25":
        return _legacy.parse_float(config.get("min_volume_ou25"))
    if market == "BTTS":
        return _legacy.parse_float(config.get("min_volume_btts"))
    return 0.0


def _hours_until_kickoff(kickoff: Any, reference: Any) -> Optional[float]:
    kickoff_dt = _dt(kickoff)
    reference_dt = _dt(reference)
    if kickoff_dt is None or reference_dt is None:
        return None
    return (kickoff_dt - reference_dt).total_seconds() / 3600.0


def _fetch_part2_snapshot_window(calculator: Any) -> Dict[str, Any]:
    signal = getattr(calculator, "_active_signal", None)
    if not isinstance(signal, dict):
        raise RuntimeError("incremental alarm calculation requires active scraper signal")

    cache_key = str(signal.get("id") or signal.get("created_at") or "")
    cached = getattr(calculator, "_part2_snapshot_cache", None)
    if isinstance(cached, dict) and cached.get("cache_key") == cache_key:
        return cached

    current_dt = _dt(signal.get("created_at"))
    if current_dt is None:
        raise RuntimeError("scraper signal created_at is missing or invalid")

    previous = _load_previous_signals(calculator, signal, count=PART2_PREVIOUS_SIGNALS)
    previous_times = [_dt(row.get("created_at")) for row in previous]
    previous_times = [value for value in previous_times if value is not None]
    immediate_previous = previous_times[0] if previous_times else None

    if previous_times:
        start_dt = min(previous_times) - timedelta(minutes=SIGNAL_PAD_MINUTES)
    else:
        start_dt = current_dt - timedelta(minutes=90)

    select = "match_id_hash,market,selection,volume,share,odds,scraped_at_utc"
    rows: List[Dict[str, Any]] = []
    offset = 0
    while offset < MAX_ROWS:
        page = calculator._get(
            "moneyway_snapshots",
            f"select={select}"
            f"&scraped_at_utc=gte.{_iso_z(start_dt)}"
            f"&scraped_at_utc=lte.{_iso_z(current_dt)}"
            "&order=scraped_at_utc.asc"
            f"&limit={PAGE_SIZE}&offset={offset}",
        ) or []
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

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

    series = {}
    current_keys = set()
    for key, by_ts in by_key.items():
        ordered = [by_ts[ts] for ts in sorted(by_ts)][-6:]
        if len(ordered) < 2:
            continue
        latest_dt = _dt(ordered[-1].get("scraped_at_utc"))
        if latest_dt is None:
            continue
        series[key] = ordered
        if immediate_previous is None or latest_dt > immediate_previous:
            current_keys.add(key)

    complete_market_states = {}
    current_markets = set()
    for market_key, states in market_states.items():
        market = market_key[1]
        expected = set(EXPECTED_SELECTIONS[market])
        complete = []
        for ts in sorted(states):
            state = states[ts]
            if set(state) >= expected:
                complete.append((ts, {sel: state[sel] for sel in EXPECTED_SELECTIONS[market]}))
        complete = complete[-6:]
        if complete:
            complete_market_states[market_key] = complete
            latest_dt = _dt(complete[-1][0])
            if latest_dt is not None and (immediate_previous is None or latest_dt > immediate_previous):
                current_markets.add(market_key)

    hashes = {key[0] for key in current_keys}
    hashes.update(key[0] for key in current_markets)
    fixtures = _load_fixtures(calculator, hashes)

    payload = {
        "cache_key": cache_key,
        "series": series,
        "current_keys": current_keys,
        "market_states": complete_market_states,
        "current_markets": current_markets,
        "fixtures": fixtures,
        "rows_loaded": len(rows),
    }
    calculator._part2_snapshot_cache = payload
    return payload


def _leader_from_state(market: str, state: Dict[str, Dict[str, Any]]):
    expected = EXPECTED_SELECTIONS.get(market) or ()
    amounts = [(selection, _legacy.parse_volume(state[selection].get("volume"))) for selection in expected]
    total = sum(amount for _, amount in amounts)
    if total <= 0:
        return None
    shares = [(selection, amount / total * 100.0) for selection, amount in amounts]
    leader = max(shares, key=lambda item: item[1])
    return leader[0], leader[1], total


def _volumeleader_incremental(calculator: Any) -> int:
    config = _effective_config(calculator, "volumeleader")
    if not _as_bool(config.get("enabled"), True):
        return 0
    threshold = _legacy.parse_float(config.get("leader_threshold")) or 50.0
    window = _fetch_part2_snapshot_window(calculator)
    existing = calculator._get("volume_leader_alarms", "select=home,away,market,old_leader,new_leader&limit=5000") or []
    existing_keys = {(str(r.get("home") or ""), str(r.get("away") or ""), str(r.get("market") or ""), str(r.get("old_leader") or ""), str(r.get("new_leader") or "")) for r in existing}
    alarms = []

    for market_key in window["current_markets"]:
        states = window["market_states"].get(market_key) or []
        if len(states) < 2:
            continue
        match_hash, market = market_key
        _, previous_state = states[-2]
        current_ts, current_state = states[-1]
        previous_leader = _leader_from_state(market, previous_state)
        current_leader = _leader_from_state(market, current_state)
        if previous_leader is None or current_leader is None:
            continue
        old_selection, old_share, _ = previous_leader
        new_selection, new_share, current_total = current_leader
        if current_total < _market_min_volume(config, market):
            continue
        if old_selection == new_selection or new_share < threshold:
            continue
        fixture = window["fixtures"].get(match_hash)
        if not fixture:
            continue
        display_market = _BIG_MARKET.get(market, market)
        old_display = _BIG_SELECTION.get((market, old_selection), old_selection)
        new_display = _BIG_SELECTION.get((market, new_selection), new_selection)
        dedupe_key = (str(fixture.get("home_team") or ""), str(fixture.get("away_team") or ""), display_market, old_display, new_display)
        if dedupe_key in existing_keys:
            continue
        alarms.append({
            "match_id_hash": match_hash,
            "home": fixture.get("home_team", ""),
            "away": fixture.get("away_team", ""),
            "league": fixture.get("league", ""),
            "market": display_market,
            "old_leader": old_display,
            "old_leader_share": round(old_share, 1),
            "new_leader": new_display,
            "new_leader_share": round(new_share, 1),
            "total_volume": round(current_total, 2),
            "match_date": fixture.get("fixture_date") or "",
            "trigger_at": current_ts,
            "created_at": _legacy.now_turkey_iso(),
            "alarm_type": "volumeleader",
        })
        existing_keys.add(dedupe_key)

    if not alarms:
        return 0
    return len(alarms) if calculator._post("volume_leader_alarms", alarms, on_conflict="home,away,market,old_leader,new_leader") else 0


def _volumeshock_incremental(calculator: Any) -> int:
    config = _effective_config(calculator, "volumeshock")
    if not _as_bool(config.get("enabled"), True):
        return 0
    defaults = calculator._default_configs().get("volumeshock", {})
    shock_mult = _legacy.parse_float(config.get("hacim_soku_min_esik")) or float(defaults.get("hacim_soku_min_esik", 7))
    min_hours = _legacy.parse_float(config.get("hacim_soku_min_saat")) if config.get("hacim_soku_min_saat") is not None else float(defaults.get("hacim_soku_min_saat", 2))
    min_incoming = _legacy.parse_float(config.get("min_son_snapshot_para")) if config.get("min_son_snapshot_para") is not None else float(defaults.get("min_son_snapshot_para", 499))
    window = _fetch_part2_snapshot_window(calculator)
    existing = calculator._get("volumeshock_alarms", "select=match_id_hash,market,selection,volume_shock_value,incoming_money,trigger_at,alarm_history&limit=5000") or []
    existing_map = {(str(r.get("match_id_hash") or ""), str(r.get("market") or ""), str(r.get("selection") or "")): r for r in existing}
    alarms = []

    for key in window["current_keys"]:
        rows = window["series"].get(key) or []
        if len(rows) < 6:
            continue
        match_hash, market, selection = key
        current = rows[-1]
        current_amount = int(_legacy.parse_volume(current.get("volume")))
        previous_amount = int(_legacy.parse_volume(rows[-2].get("volume")))
        incoming = current_amount - previous_amount
        if incoming <= 0 or incoming < min_incoming:
            continue
        previous_changes = []
        for idx in range(1, 5):
            diff = int(_legacy.parse_volume(rows[idx].get("volume"))) - int(_legacy.parse_volume(rows[idx - 1].get("volume")))
            if diff > 0:
                previous_changes.append(diff)
        if not previous_changes:
            continue
        avg_previous = sum(previous_changes) / len(previous_changes)
        if avg_previous < 1:
            continue
        shock_value = incoming / avg_previous
        if shock_value < shock_mult:
            continue
        current_ts = str(current.get("scraped_at_utc") or "")
        state = None
        for ts, candidate in reversed(window["market_states"].get((match_hash, market)) or []):
            if ts == current_ts:
                state = candidate
                break
        if state is None:
            continue
        current_total = sum(_legacy.parse_volume(state[sel].get("volume")) for sel in EXPECTED_SELECTIONS[market])
        if current_total < _market_min_volume(config, market):
            continue
        fixture = window["fixtures"].get(match_hash)
        if not fixture:
            continue
        if min_hours > 0:
            hours = _hours_until_kickoff(fixture.get("kickoff_utc"), current_ts)
            if hours is None or hours < min_hours:
                continue
        display_market = _BIG_MARKET.get(market, market)
        display_selection = _BIG_SELECTION.get((market, selection), selection)
        old = existing_map.get((match_hash, display_market, display_selection))
        if old and _legacy.parse_float(old.get("volume_shock_value")) >= shock_value:
            continue
        history_items = []
        if old:
            history_items.extend(_parse_history(old.get("alarm_history")))
            if old.get("trigger_at") and old.get("trigger_at") != current_ts:
                history_items.append({"incoming_money": _legacy.parse_volume(old.get("incoming_money")), "trigger_at": old.get("trigger_at"), "volume_shock_value": _legacy.parse_float(old.get("volume_shock_value"))})
        alarms.append({
            "match_id_hash": match_hash,
            "home": fixture.get("home_team", ""),
            "away": fixture.get("away_team", ""),
            "league": fixture.get("league", ""),
            "market": display_market,
            "selection": display_selection,
            "volume_shock_value": round(shock_value, 2),
            "incoming_money": incoming,
            "avg_previous": round(avg_previous, 0),
            "match_date": fixture.get("fixture_date") or "",
            "trigger_at": current_ts,
            "created_at": _legacy.now_turkey_iso(),
            "alarm_type": "volumeshock",
            "alarm_history": json.dumps(_dedupe_history(history_items)),
        })

    if not alarms:
        return 0
    return calculator._upsert_alarms("volumeshock_alarms", alarms, ["match_id_hash", "market", "selection"])


def install_part2_alarm_overrides(calculator_cls: Any) -> None:
    if getattr(calculator_cls, "_part2_alarm_overrides_installed", False):
        return
    original_volumeleader = calculator_cls.calculate_volumeleader_alarms
    original_volumeshock = calculator_cls.calculate_volumeshock_alarms

    def volumeleader(self: Any) -> int:
        if not isinstance(getattr(self, "_active_signal", None), dict):
            return original_volumeleader(self)
        return _volumeleader_incremental(self)

    def volumeshock(self: Any) -> int:
        if not isinstance(getattr(self, "_active_signal", None), dict):
            return original_volumeshock(self)
        return _volumeshock_incremental(self)

    calculator_cls.calculate_volumeleader_alarms = volumeleader
    calculator_cls.calculate_volumeshock_alarms = volumeshock
    calculator_cls._part2_alarm_overrides_installed = True


def clear_part2_alarm_cache(calculator: Any) -> None:
    if hasattr(calculator, "_part2_snapshot_cache"):
        try:
            delattr(calculator, "_part2_snapshot_cache")
        except Exception:
            setattr(calculator, "_part2_snapshot_cache", None)
