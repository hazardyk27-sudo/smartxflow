from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import alarm_calculator_legacy as _legacy

PAGE_SIZE = 1000
MAX_ROWS = 50000
SIGNAL_PAD_MINUTES = 5

_BIG_MARKET = {"1X2": "1X2", "OU25": "O/U 2.5", "BTTS": "BTTS"}
_BIG_SELECTION = {
    ("1X2", "1"): "1",
    ("1X2", "X"): "X",
    ("1X2", "2"): "2",
    ("OU25", "O"): "Over",
    ("OU25", "U"): "Under",
    ("BTTS", "Y"): "Yes",
    ("BTTS", "N"): "No",
}


def _as_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in {"0", "false", "off", "no", "disabled", ""}


def _dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _effective_config(calculator: Any, alarm_type: str) -> Dict[str, Any]:
    defaults = dict(calculator._default_configs().get(alarm_type, {}))
    live = calculator.configs.get(alarm_type) or {}
    aliases = {
        "mim": {
            "min_impact_for_alarm": ("min_impact_threshold",),
            "min_market_volume": ("min_prev_volume",),
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


def _normalize_fraction(value: float) -> float:
    return value / 100.0 if value > 1.0 else value


def _load_previous_signals(calculator: Any, signal: Dict[str, Any], count: int = 2) -> List[Dict[str, Any]]:
    signal_id = signal.get("id")
    if signal_id is None:
        return []
    source = str(signal.get("source") or "replit")
    rows = calculator._get(
        "scraper_signal",
        f"select=id,created_at,source&id=lt.{int(signal_id)}"
        f"&source=eq.{source}&order=id.desc&limit={int(count)}",
    ) or []
    return rows


def _load_fixtures(calculator: Any, hashes: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    ordered = sorted({str(value) for value in hashes if value})
    result: Dict[str, Dict[str, Any]] = {}
    for start in range(0, len(ordered), 80):
        chunk = ordered[start:start + 80]
        if not chunk:
            continue
        rows = calculator._get(
            "fixtures",
            "select=match_id_hash,home_team,away_team,league,kickoff_utc,fixture_date"
            f"&match_id_hash=in.({','.join(chunk)})",
        ) or []
        for row in rows:
            match_hash = str(row.get("match_id_hash") or "")
            if match_hash:
                result[match_hash] = row
    return result


def _fetch_recent_snapshot_window(calculator: Any) -> Dict[str, Any]:
    signal = getattr(calculator, "_active_signal", None)
    if not isinstance(signal, dict):
        raise RuntimeError("incremental alarm calculation requires active scraper signal")

    cache_key = str(signal.get("id") or signal.get("created_at") or "")
    cached = getattr(calculator, "_recent_snapshot_cache", None)
    if isinstance(cached, dict) and cached.get("cache_key") == cache_key:
        return cached

    current_dt = _dt(signal.get("created_at"))
    if current_dt is None:
        raise RuntimeError("scraper signal created_at is missing or invalid")

    previous = _load_previous_signals(calculator, signal, count=2)
    previous_times = [_dt(row.get("created_at")) for row in previous]
    previous_times = [value for value in previous_times if value is not None]

    immediate_previous = previous_times[0] if previous_times else None
    if previous_times:
        start_dt = min(previous_times) - timedelta(minutes=SIGNAL_PAD_MINUTES)
    else:
        start_dt = current_dt - timedelta(minutes=30)

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

    if len(rows) >= MAX_ROWS:
        _legacy.log(
            f"[RecentAlarm] snapshot window reached safety cap ({MAX_ROWS}); "
            "results may be incomplete"
        )

    by_key: Dict[Tuple[str, str, str], Dict[str, Dict[str, Any]]] = {}
    for row in rows:
        match_hash = str(row.get("match_id_hash") or "")
        market = str(row.get("market") or "")
        selection = str(row.get("selection") or "")
        ts = str(row.get("scraped_at_utc") or "")
        if not match_hash or market not in {"1X2", "OU25", "BTTS"} or not selection or not ts:
            continue
        by_key.setdefault((match_hash, market, selection), {})[ts] = row

    series: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = {}
    current_keys = set()
    for key, by_ts in by_key.items():
        ordered_rows = [by_ts[ts] for ts in sorted(by_ts)]
        ordered_rows = ordered_rows[-3:]
        if len(ordered_rows) < 2:
            continue
        latest_dt = _dt(ordered_rows[-1].get("scraped_at_utc"))
        if latest_dt is None:
            continue
        if immediate_previous is None or latest_dt > immediate_previous:
            current_keys.add(key)
        series[key] = ordered_rows

    fixtures = _load_fixtures(calculator, (key[0] for key in current_keys))
    payload = {
        "cache_key": cache_key,
        "signal": signal,
        "series": series,
        "current_keys": current_keys,
        "fixtures": fixtures,
        "rows_loaded": len(rows),
        "window_start": start_dt,
        "window_end": current_dt,
        "immediate_previous": immediate_previous,
    }
    calculator._recent_snapshot_cache = payload
    _legacy.log(
        f"[RecentAlarm] signal={cache_key} rows={len(rows)} "
        f"series={len(series)} changed={len(current_keys)} "
        f"window={_iso_z(start_dt)}..{_iso_z(current_dt)}"
    )
    return payload


def _parse_history(raw: Any) -> List[Dict[str, Any]]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    try:
        parsed = json.loads(raw)
        return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []
    except Exception:
        return []


def _dedupe_history(items: Iterable[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
    seen = set()
    output = []
    for item in sorted(items, key=lambda row: str(row.get("trigger_at") or "")):
        trigger = str(item.get("trigger_at") or "")
        if not trigger or trigger in seen:
            continue
        seen.add(trigger)
        output.append(item)
    return output[-limit:]


def _bigmoney_incremental(calculator: Any) -> int:
    started = time.monotonic()
    config = calculator.configs.get("bigmoney") or {}
    if not _as_bool(config.get("enabled"), True):
        _legacy.log("[BigMoney Incremental] disabled")
        return 0

    limit = _legacy.parse_float(config.get("big_money_limit"))
    if limit <= 0:
        _legacy.log("[BigMoney Incremental] invalid big_money_limit")
        return 0

    window = _fetch_recent_snapshot_window(calculator)
    existing = calculator._get(
        "bigmoney_alarms",
        "select=match_id_hash,market,selection,incoming_money,total_selection,is_huge,"
        "trigger_at,created_at,alarm_history&limit=5000",
    ) or []
    existing_map = {
        (str(row.get("match_id_hash") or ""), str(row.get("market") or ""), str(row.get("selection") or "")): row
        for row in existing
    }

    alarms: List[Dict[str, Any]] = []
    skipped_fixture = 0
    for key in window["current_keys"]:
        rows = window["series"].get(key) or []
        if len(rows) < 2:
            continue
        match_hash, market, selection = key
        current = rows[-1]
        previous = rows[-2]
        current_volume = _legacy.parse_volume(current.get("volume"))
        previous_volume = _legacy.parse_volume(previous.get("volume"))
        incoming = current_volume - previous_volume
        if incoming < limit:
            continue

        fixture = window["fixtures"].get(match_hash)
        if not fixture:
            skipped_fixture += 1
            continue

        previous_incoming = 0.0
        if len(rows) >= 3:
            previous_incoming = (
                _legacy.parse_volume(rows[-2].get("volume"))
                - _legacy.parse_volume(rows[-3].get("volume"))
            )
        is_huge = previous_incoming >= limit
        huge_total = incoming + previous_incoming if is_huge else 0.0

        display_market = _BIG_MARKET.get(market, market)
        display_selection = _BIG_SELECTION.get((market, selection), selection)
        trigger_at = current.get("scraped_at_utc") or _legacy.now_turkey_iso()

        old = existing_map.get((match_hash, display_market, display_selection))
        history_items: List[Dict[str, Any]] = []
        if old:
            history_items.extend(_parse_history(old.get("alarm_history")))
            old_trigger = old.get("trigger_at")
            if old_trigger and old_trigger != trigger_at:
                history_items.append({
                    "incoming_money": _legacy.parse_volume(old.get("incoming_money")),
                    "trigger_at": old_trigger,
                    "selection_total": _legacy.parse_volume(old.get("total_selection")),
                    "is_huge": bool(old.get("is_huge")),
                })

        alarm = {
            "match_id_hash": match_hash,
            "home": fixture.get("home_team", ""),
            "away": fixture.get("away_team", ""),
            "league": fixture.get("league", ""),
            "market": display_market,
            "selection": display_selection,
            "incoming_money": round(incoming, 2),
            "selection_total": round(current_volume, 2),
            "is_huge": is_huge,
            "huge_total": round(huge_total, 2),
            "alarm_type": "HUGE MONEY" if is_huge else "BIG MONEY",
            "match_date": fixture.get("fixture_date") or "",
            "trigger_at": trigger_at,
            "created_at": _legacy.now_turkey_iso(),
            "alarm_history": json.dumps(_dedupe_history(history_items)),
        }
        alarms.append(alarm)

    if not alarms:
        _legacy.log(
            f"[BigMoney Incremental] 0 alarm | rows={window['rows_loaded']} "
            f"changed={len(window['current_keys'])} fixture_missing={skipped_fixture} "
            f"elapsed={time.monotonic() - started:.3f}s"
        )
        return 0

    count = calculator._upsert_alarms(
        "bigmoney_alarms",
        alarms,
        ["match_id_hash", "market", "selection"],
    )
    _legacy.log(
        f"[BigMoney Incremental] upserted={count} candidates={len(alarms)} "
        f"rows={window['rows_loaded']} fixture_missing={skipped_fixture} "
        f"elapsed={time.monotonic() - started:.3f}s"
    )
    return count


def _mim_incremental(calculator: Any) -> int:
    started = time.monotonic()
    config = _effective_config(calculator, "mim")
    if not _as_bool(config.get("enabled"), True):
        _legacy.log("[MIM Incremental] disabled")
        return 0

    defaults = calculator._default_configs().get("mim", {})
    min_impact = _normalize_fraction(
        _legacy.parse_float(config.get("min_impact_for_alarm"))
        or _legacy.parse_float(config.get("min_impact_threshold"))
        or float(defaults.get("min_impact_for_alarm", 0.20))
    )
    min_market_volume = (
        _legacy.parse_float(config.get("min_market_volume"))
        or _legacy.parse_float(config.get("min_prev_volume"))
        or float(defaults.get("min_market_volume", 1000))
    )
    min_new_money = (
        _legacy.parse_float(config.get("min_new_money"))
        if config.get("min_new_money") is not None
        else float(defaults.get("min_new_money", 300))
    )
    if min_impact <= 0 or min_market_volume < 0 or min_new_money < 0:
        _legacy.log("[MIM Incremental] invalid thresholds")
        return 0

    window = _fetch_recent_snapshot_window(calculator)

    current_by_market: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for key in window["current_keys"]:
        rows = window["series"].get(key) or []
        if len(rows) < 2:
            continue
        match_hash, market, selection = key
        current = rows[-1]
        ts = str(current.get("scraped_at_utc") or "")
        bucket = current_by_market.setdefault(
            (match_hash, market),
            {"timestamp": ts, "selections": {}},
        )
        if ts > str(bucket.get("timestamp") or ""):
            bucket["timestamp"] = ts
            bucket["selections"] = {}
        if ts == bucket.get("timestamp"):
            bucket["selections"][selection] = current

    existing = calculator._get(
        "mim_alarms",
        "select=match_id_hash,market,selection,impact,incoming_volume,trigger_at,alarm_history&limit=5000",
    ) or []
    existing_map = {
        (str(row.get("match_id_hash") or ""), str(row.get("market") or ""), str(row.get("selection") or "")): row
        for row in existing
    }

    alarms: List[Dict[str, Any]] = []
    skipped_fixture = 0
    for key in window["current_keys"]:
        rows = window["series"].get(key) or []
        if len(rows) < 2:
            continue
        match_hash, market, selection = key
        current = rows[-1]
        previous = rows[-2]

        market_bucket = current_by_market.get((match_hash, market)) or {}
        if str(current.get("scraped_at_utc") or "") != str(market_bucket.get("timestamp") or ""):
            continue
        current_market_volume = sum(
            _legacy.parse_volume(row.get("volume"))
            for row in (market_bucket.get("selections") or {}).values()
        )
        if current_market_volume < min_market_volume or current_market_volume <= 0:
            continue

        previous_volume = _legacy.parse_volume(previous.get("volume"))
        current_volume = _legacy.parse_volume(current.get("volume"))
        incoming = current_volume - previous_volume
        if incoming < min_new_money:
            continue
        impact = incoming / current_market_volume
        if impact < min_impact:
            continue

        fixture = window["fixtures"].get(match_hash)
        if not fixture:
            skipped_fixture += 1
            continue

        trigger_at = current.get("scraped_at_utc") or _legacy.now_turkey_iso()
        old = existing_map.get((match_hash, market, selection))
        history_items: List[Dict[str, Any]] = []
        if old:
            history_items.extend(_parse_history(old.get("alarm_history")))
            old_trigger = old.get("trigger_at")
            if old_trigger and old_trigger != trigger_at:
                history_items.append({
                    "impact_score": _legacy.parse_float(old.get("impact")),
                    "incoming_volume": _legacy.parse_volume(old.get("incoming_volume")),
                    "trigger_at": old_trigger,
                })

        alarm = {
            "match_id_hash": match_hash,
            "home": fixture.get("home_team", ""),
            "away": fixture.get("away_team", ""),
            "league": fixture.get("league", ""),
            "market": market,
            "selection": selection,
            "impact_score": round(impact, 4),
            "prev_volume": round(previous_volume, 2),
            "curr_volume": round(current_volume, 2),
            "incoming_volume": round(incoming, 2),
            "total_market_volume": round(current_market_volume, 2),
            "match_date": fixture.get("fixture_date") or "",
            "trigger_at": trigger_at,
            "created_at": _legacy.now_turkey_iso(),
            "alarm_type": "mim",
            "alarm_history": json.dumps(_dedupe_history(history_items)),
        }
        alarms.append(alarm)

    if not alarms:
        _legacy.log(
            f"[MIM Incremental] 0 alarm | rows={window['rows_loaded']} "
            f"changed={len(window['current_keys'])} fixture_missing={skipped_fixture} "
            f"elapsed={time.monotonic() - started:.3f}s"
        )
        return 0

    count = calculator._upsert_alarms(
        "mim_alarms",
        alarms,
        ["match_id_hash", "market", "selection"],
    )
    _legacy.log(
        f"[MIM Incremental] upserted={count} candidates={len(alarms)} "
        f"rows={window['rows_loaded']} fixture_missing={skipped_fixture} "
        f"elapsed={time.monotonic() - started:.3f}s"
    )
    return count


def install_recent_alarm_overrides(calculator_cls: Any) -> None:
    """Patch only Alarm Engine's calculator class.

    Other callers continue using the legacy/stabilized implementations unless
    they explicitly install this optimization.
    """
    if getattr(calculator_cls, "_recent_alarm_overrides_installed", False):
        return

    original_bigmoney = calculator_cls.calculate_bigmoney_alarms
    original_mim = calculator_cls.calculate_mim_alarms

    def bigmoney(self: Any) -> int:
        if not isinstance(getattr(self, "_active_signal", None), dict):
            return original_bigmoney(self)
        return _bigmoney_incremental(self)

    def mim(self: Any) -> int:
        if not isinstance(getattr(self, "_active_signal", None), dict):
            return original_mim(self)
        return _mim_incremental(self)

    calculator_cls.calculate_bigmoney_alarms = bigmoney
    calculator_cls.calculate_mim_alarms = mim
    calculator_cls._recent_alarm_overrides_installed = True


def clear_recent_alarm_cache(calculator: Any) -> None:
    for name in ("_recent_snapshot_cache", "_active_signal"):
        if hasattr(calculator, name):
            try:
                delattr(calculator, name)
            except Exception:
                setattr(calculator, name, None)
