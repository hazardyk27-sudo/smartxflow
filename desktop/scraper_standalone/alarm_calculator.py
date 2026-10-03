"""
SmartXFlow alarm calculator compatibility wrapper.

The original v1.25 calculator is preserved byte-for-byte in
alarm_calculator_legacy.py. This wrapper keeps the public module/class contract
unchanged while enforcing the live alarm_settings contract for the three alarm
types that previously ignored part of their configuration:

- MIM
- VolumeShock
- Dropping

All callers (`alarm_engine.py`, standalone scraper and Admin) continue importing
`AlarmCalculator` from `alarm_calculator`.
"""

from alarm_calculator_legacy import *  # noqa: F401,F403
import alarm_calculator_legacy as _legacy

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple


def _as_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in {"0", "false", "off", "no", "disabled", ""}


def _first_float(config: Dict[str, Any], keys: Tuple[str, ...], default: float) -> float:
    for key in keys:
        if key in config and config.get(key) is not None:
            value = _legacy.parse_float(config.get(key))
            return value
    return float(default)


def _effective_config(calculator: "AlarmCalculator", alarm_type: str) -> Dict[str, Any]:
    """Merge partial live DB config over canonical defaults.

    The legacy loader returns early when alarm_settings has rows, so missing
    fields in a partial row never receive defaults. For the stabilized alarm
    types we explicitly merge defaults here. Legacy key aliases are migrated
    only when the canonical key is absent from the live DB row, so an explicit
    live value always wins over a fallback default.
    """
    defaults = dict(calculator._default_configs().get(alarm_type, {}))
    live = calculator.configs.get(alarm_type) or {}

    alias_map = {
        "mim": {
            "min_impact_for_alarm": ("min_impact_threshold",),
            "min_market_volume": ("min_prev_volume",),
        },
        "volumeshock": {
            "hacim_soku_min_esik": ("volume_shock_multiplier",),
            "hacim_soku_min_saat": ("min_hours",),
            "min_son_snapshot_para": ("min_incoming",),
        },
    }

    for canonical, aliases in alias_map.get(alarm_type, {}).items():
        if live.get(canonical) is None:
            for alias in aliases:
                if live.get(alias) is not None:
                    defaults[canonical] = live[alias]
                    break

    for key, value in live.items():
        if value is not None:
            defaults[key] = value
    return defaults


def _normalize_fraction(value: float) -> float:
    """Accept both 0.20 and 20 as a 20% threshold."""
    if value > 1.0:
        return value / 100.0
    return value


def _parse_datetime(value: Any) -> Optional[datetime]:
    """Parse SmartXFlow kickoff/scrape timestamps into timezone-aware UTC."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    dt = None

    # ISO variants first.
    iso_candidates = [text, text.replace("Z", "+00:00")]
    for candidate in iso_candidates:
        try:
            dt = datetime.fromisoformat(candidate)
            break
        except Exception:
            pass

    if dt is None:
        # Common SmartXFlow formats: "18.Dec 09:00:00", "18.Dec 09:00".
        now_tr = _legacy.now_turkey()
        year = now_tr.year
        for fmt in ("%d.%b %H:%M:%S", "%d.%b %H:%M", "%d.%b",
                    "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y",
                    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                if "%Y" not in fmt:
                    # Same rollover rule used elsewhere in the calculator.
                    if parsed.month < now_tr.month - 6:
                        year += 1
                    parsed = parsed.replace(year=year)
                dt = parsed
                break
            except Exception:
                pass

    if dt is None:
        return None

    if dt.tzinfo is None:
        tz = getattr(_legacy, "TURKEY_TZ", None)
        if tz is not None:
            try:
                dt = tz.localize(dt)
            except Exception:
                try:
                    dt = dt.replace(tzinfo=tz)
                except Exception:
                    dt = dt.replace(tzinfo=timezone(timedelta(hours=3)))
        else:
            dt = dt.replace(tzinfo=timezone(timedelta(hours=3)))

    try:
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _hours_until_kickoff(kickoff: Any, reference: Any = None) -> Optional[float]:
    kickoff_dt = _parse_datetime(kickoff)
    if kickoff_dt is None:
        return None
    ref_dt = _parse_datetime(reference) if reference is not None else _parse_datetime(_legacy.now_turkey().isoformat())
    if ref_dt is None:
        return None
    return (kickoff_dt - ref_dt).total_seconds() / 3600.0


def _market_min_volume(config: Dict[str, Any], market_name: str) -> float:
    if market_name == "1X2":
        return _first_float(config, ("min_volume_1x2",), 0.0)
    if market_name in {"O/U 2.5", "OU25"}:
        return _first_float(config, ("min_volume_ou25",), 0.0)
    if market_name == "BTTS":
        return _first_float(config, ("min_volume_btts",), 0.0)
    return 0.0


def _volumeshock_candidate_ok(
    market_volume: float,
    min_market_volume: float,
    hours_to_kickoff: Optional[float],
    min_hours: float,
) -> bool:
    if market_volume < min_market_volume:
        return False
    if min_hours > 0:
        if hours_to_kickoff is None or hours_to_kickoff < min_hours:
            return False
    return True


def _row_timestamp(row: Dict[str, Any]) -> Optional[datetime]:
    return _parse_datetime(row.get("scraped_at_utc") or row.get("scraped_at"))


def _dropping_persistence_ok(
    history: List[Dict[str, Any]],
    odds_key: str,
    opening_odds: float,
    min_drop_pct: float,
    persistence_minutes: float,
) -> bool:
    """Require a continuous, outlier-guarded L1 drop across the configured window.

    Each point is evaluated with a rolling median of the latest up-to-3 valid
    odds, matching the existing median outlier protection. There must be
    evidence at or before the start of the requested window, and every
    evaluated point inside the window must remain at/above the L1 threshold.
    """
    if persistence_minutes <= 0:
        return True
    if opening_odds <= 0:
        return False

    ordered = sorted(
        [row for row in history if _row_timestamp(row) is not None],
        key=lambda row: _row_timestamp(row),
    )
    if not ordered:
        return False

    rolling_odds: List[float] = []
    points: List[Tuple[datetime, float]] = []

    for row in ordered:
        odds = _legacy.parse_float(row.get(odds_key, 0))
        if odds <= 0:
            continue
        rolling_odds.append(odds)
        window = rolling_odds[-3:]
        median_odds = sorted(window)[len(window) // 2]
        drop_pct = ((opening_odds - median_odds) / opening_odds) * 100.0
        ts = _row_timestamp(row)
        if ts is not None:
            points.append((ts, drop_pct))

    if len(points) < 2:
        return False

    latest_ts = points[-1][0]
    cutoff = latest_ts - timedelta(minutes=float(persistence_minutes))
    anchors = [point for point in points if point[0] <= cutoff]
    if not anchors:
        return False

    anchor = anchors[-1]
    if anchor[1] < min_drop_pct:
        return False

    in_window = [point for point in points if cutoff < point[0] <= latest_ts]
    if not in_window:
        return False

    return all(drop_pct >= min_drop_pct for _, drop_pct in in_window)


def _current_market_volume(
    calculator: "AlarmCalculator",
    market_table: str,
    match: Dict[str, Any],
) -> float:
    direct = _legacy.parse_volume(match.get("volume", 0))
    if direct > 0:
        return direct

    home = match.get("home", match.get("Home", ""))
    away = match.get("away", match.get("Away", ""))
    league = match.get("league", "")
    date_str = match.get("date", "")
    match_hash = match.get("match_id_hash") or _legacy.generate_match_id_hash(home, away, league, date_str)
    history = calculator.get_match_history(
        match_hash,
        f"{market_table}_history",
        home,
        away,
        league,
        date_str,
    )
    if not history:
        return 0.0

    latest = history[-1]
    direct = _legacy.parse_volume(latest.get("volume", 0))
    if direct > 0:
        return direct

    amount_keys = {
        "moneyway_1x2": ("amt1", "amtx", "amt2"),
        "moneyway_ou25": ("amtover", "amtunder"),
        "moneyway_btts": ("amtyes", "amtno"),
        "dropping_1x2": ("amt1", "amtx", "amt2"),
        "dropping_ou25": ("amtover", "amtunder"),
        "dropping_btts": ("amtyes", "amtno"),
    }.get(market_table, ())
    return sum(_legacy.parse_volume(latest.get(key, 0)) for key in amount_keys)


class AlarmCalculator(_legacy.AlarmCalculator):
    """Stable rules wrapper around the legacy calculator implementation."""

    def calculate_mim_alarms(self) -> int:
        config = _effective_config(self, "mim")
        if not _as_bool(config.get("enabled"), True):
            _legacy.log("[MIM] Alarm devre dışı")
            return 0

        defaults = self._default_configs()["mim"]
        min_impact = _normalize_fraction(
            _first_float(
                config,
                ("min_impact_for_alarm", "min_impact_threshold"),
                defaults["min_impact_for_alarm"],
            )
        )
        min_market_volume = _first_float(
            config,
            ("min_market_volume", "min_prev_volume"),
            defaults["min_market_volume"],
        )
        min_new_money = _first_float(
            config,
            ("min_new_money",),
            defaults["min_new_money"],
        )

        if min_impact <= 0 or min_market_volume < 0 or min_new_money < 0:
            _legacy.log("[MIM] Geçersiz config: impact/market-volume/new-money eşikleri kontrol edilmeli")
            return 0

        _legacy.log(
            f"[MIM Stable] impact>={min_impact:.4f} (%{min_impact*100:.1f}), "
            f"market>={min_market_volume:.0f}, new_money>={min_new_money:.0f}"
        )

        all_alarms: List[Dict[str, Any]] = []
        markets_config = [
            {
                "table": "moneyway_1x2",
                "name": "1X2",
                "selections": [("1", "amt1", "total_amount_1"),
                               ("X", "amtx", "total_amount_x"),
                               ("2", "amt2", "total_amount_2")],
                "volume_keys": [("amt1", "total_amount_1"),
                                ("amtx", "total_amount_x"),
                                ("amt2", "total_amount_2")],
            },
            {
                "table": "moneyway_ou25",
                "name": "OU25",
                "selections": [("O", "amtover", "total_amount_over"),
                               ("U", "amtunder", "total_amount_under")],
                "volume_keys": [("amtover", "total_amount_over"),
                                ("amtunder", "total_amount_under")],
            },
            {
                "table": "moneyway_btts",
                "name": "BTTS",
                "selections": [("Y", "amtyes", "total_amount_yes"),
                               ("N", "amtno", "total_amount_no")],
                "volume_keys": [("amtyes", "total_amount_yes"),
                                ("amtno", "total_amount_no")],
            },
        ]

        for mkt in markets_config:
            matches = self.get_matches_with_latest(mkt["table"])
            for match in matches:
                if not self._is_valid_match_date(match.get("date", "")):
                    continue

                home = match.get("home", "")
                away = match.get("away", "")
                if not home or not away:
                    continue

                match_hash = match.get("match_id_hash") or _legacy.generate_match_id_hash(
                    home, away, match.get("league", ""), match.get("date", "")
                )
                history = self.get_match_history(
                    match_hash,
                    f"{mkt['table']}_history",
                    home,
                    away,
                    match.get("league", ""),
                    match.get("date", ""),
                )
                if len(history) < 2:
                    continue

                history = sorted(
                    history,
                    key=lambda row: _row_timestamp(row) or datetime.min.replace(tzinfo=timezone.utc),
                )
                latest_per_selection: Dict[str, Dict[str, Any]] = {}

                for idx in range(1, len(history)):
                    prev_snap = history[idx - 1]
                    curr_snap = history[idx]

                    current_components = [
                        _legacy.parse_volume(curr_snap.get(primary) or curr_snap.get(alt, 0))
                        for primary, alt in mkt["volume_keys"]
                    ]
                    current_market_volume = sum(current_components)
                    if current_market_volume < min_market_volume or current_market_volume <= 0:
                        continue

                    for selection, primary, alt in mkt["selections"]:
                        prev_amt = _legacy.parse_volume(prev_snap.get(primary) or prev_snap.get(alt, 0))
                        curr_amt = _legacy.parse_volume(curr_snap.get(primary) or curr_snap.get(alt, 0))
                        incoming = curr_amt - prev_amt
                        if incoming < min_new_money:
                            continue

                        impact = incoming / current_market_volume
                        if impact < min_impact:
                            continue

                        trigger_at = (
                            curr_snap.get("scraped_at_utc")
                            or curr_snap.get("scraped_at")
                            or _legacy.now_turkey_iso()
                        )
                        latest_per_selection[selection] = {
                            "match_id_hash": match_hash,
                            "home": home,
                            "away": away,
                            "league": match.get("league", ""),
                            "market": mkt["name"],
                            "selection": selection,
                            "impact_score": round(impact, 4),
                            "prev_volume": round(prev_amt, 2),
                            "curr_volume": round(curr_amt, 2),
                            "incoming_volume": round(incoming, 2),
                            "total_market_volume": round(current_market_volume, 2),
                            "match_date": _legacy.normalize_date_for_db(match.get("date", "")),
                            "trigger_at": trigger_at,
                            "created_at": _legacy.now_turkey_iso(),
                            "alarm_type": "mim",
                        }

                all_alarms.extend(latest_per_selection.values())

        if not all_alarms:
            _legacy.log("MIM: 0 alarm (stable rules)")
            return 0

        existing = self._get(
            "mim_alarms",
            "select=match_id_hash,market,selection,impact,incoming_volume,trigger_at,alarm_history&limit=5000",
        ) or []
        existing_map = {
            f"{row.get('match_id_hash')}_{row.get('market')}_{row.get('selection')}": row
            for row in existing
        }

        filtered: List[Dict[str, Any]] = []
        for alarm in all_alarms:
            key = f"{alarm['match_id_hash']}_{alarm['market']}_{alarm['selection']}"
            history_items: List[Dict[str, Any]] = []

            old = existing_map.get(key)
            if old:
                raw = old.get("alarm_history") or []
                try:
                    history_items = json.loads(raw) if isinstance(raw, str) else list(raw)
                except Exception:
                    history_items = []
                history_items.append({
                    "impact_score": old.get("impact", 0),
                    "incoming_volume": old.get("incoming_volume", 0),
                    "trigger_at": old.get("trigger_at", ""),
                })

            history_items.append({
                "impact_score": alarm.get("impact_score", 0),
                "incoming_volume": alarm.get("incoming_volume", 0),
                "trigger_at": alarm.get("trigger_at", ""),
            })

            seen = set()
            unique = []
            for item in sorted(history_items, key=lambda x: x.get("trigger_at", "")):
                trigger = item.get("trigger_at", "")
                if trigger and trigger not in seen:
                    seen.add(trigger)
                    unique.append(item)
            alarm["alarm_history"] = json.dumps(unique[-10:])
            filtered.append(alarm)

        count = self._upsert_alarms(
            "mim_alarms",
            filtered,
            ["match_id_hash", "market", "selection"],
        )
        _legacy.log(f"MIM Stable: {count} alarms upserted")
        return count

    def calculate_volumeshock_alarms(self) -> int:
        config = _effective_config(self, "volumeshock")
        if not _as_bool(config.get("enabled"), True):
            _legacy.log("[VolumeShock] Alarm devre dışı")
            return 0

        defaults = self._default_configs()["volumeshock"]
        shock_mult = _first_float(
            config,
            ("hacim_soku_min_esik", "volume_shock_multiplier"),
            defaults["hacim_soku_min_esik"],
        )
        min_hours = _first_float(
            config,
            ("hacim_soku_min_saat", "min_hours"),
            defaults["hacim_soku_min_saat"],
        )
        min_incoming = _first_float(
            config,
            ("min_son_snapshot_para", "min_incoming"),
            defaults["min_son_snapshot_para"],
        )

        if shock_mult <= 0 or min_hours < 0 or min_incoming < 0:
            _legacy.log("[VolumeShock] Geçersiz config")
            return 0

        # Build current match context before the legacy calculation. The base
        # calculator already caches these reads, so this does not duplicate
        # network traffic in normal operation.
        context: Dict[Tuple[str, str], Dict[str, Any]] = {}
        table_to_name = {
            "moneyway_1x2": "1X2",
            "moneyway_ou25": "O/U 2.5",
            "moneyway_btts": "BTTS",
        }
        for table, display in table_to_name.items():
            for match in self.get_matches_with_latest(table):
                home = match.get("home", match.get("Home", ""))
                away = match.get("away", match.get("Away", ""))
                if not home or not away:
                    continue
                match_hash = match.get("match_id_hash") or _legacy.generate_match_id_hash(
                    home, away, match.get("league", ""), match.get("date", "")
                )
                context[(match_hash, display)] = {
                    "match": match,
                    "market_table": table,
                    "market_volume": _current_market_volume(self, table, match),
                    "hours_to_kickoff": _hours_until_kickoff(match.get("date", "")),
                }

        legacy_config = dict(config)
        legacy_config.update({
            "enabled": True,
            "hacim_soku_min_esik": shock_mult,
            "hacim_soku_min_saat": min_hours,
            "min_son_snapshot_para": min_incoming,
        })

        old_config = self.configs.get("volumeshock")
        old_get = self._get
        old_upsert = self._upsert_alarms
        accepted = {"count": 0, "volume_reject": 0, "hours_reject": 0, "context_reject": 0}

        def guarded_get(table: str, params: str = ""):
            rows = old_get(table, params)
            if table != "volumeshock_alarms":
                return rows
            normalized = []
            for row in rows or []:
                copy = dict(row)
                if not copy.get("match_id") and copy.get("match_id_hash"):
                    copy["match_id"] = copy["match_id_hash"]
                normalized.append(copy)
            return normalized

        def guarded_upsert(table: str, alarms: List[Dict], key_fields: List[str]) -> int:
            if table != "volumeshock_alarms":
                return old_upsert(table, alarms, key_fields)

            valid = []
            for alarm in alarms:
                ctx = context.get((alarm.get("match_id_hash", ""), alarm.get("market", "")))
                if not ctx:
                    accepted["context_reject"] += 1
                    continue
                min_market_volume = _market_min_volume(config, alarm.get("market", ""))
                if ctx["market_volume"] < min_market_volume:
                    accepted["volume_reject"] += 1
                    continue
                if not _volumeshock_candidate_ok(
                    ctx["market_volume"],
                    min_market_volume,
                    ctx["hours_to_kickoff"],
                    min_hours,
                ):
                    accepted["hours_reject"] += 1
                    continue
                valid.append(alarm)

            accepted["count"] = len(valid)
            return old_upsert(table, valid, key_fields)

        try:
            self.configs["volumeshock"] = legacy_config
            self._get = guarded_get
            self._upsert_alarms = guarded_upsert
            super().calculate_volumeshock_alarms()
        finally:
            self._get = old_get
            self._upsert_alarms = old_upsert
            if old_config is None:
                self.configs.pop("volumeshock", None)
            else:
                self.configs["volumeshock"] = old_config

        _legacy.log(
            f"[VolumeShock Stable] accepted={accepted['count']} "
            f"volume_reject={accepted['volume_reject']} "
            f"hours_reject={accepted['hours_reject']} "
            f"context_reject={accepted['context_reject']}"
        )
        return accepted["count"]

    def calculate_dropping_alarms(self) -> int:
        config = _effective_config(self, "dropping")
        if not _as_bool(config.get("enabled"), True):
            _legacy.log("[Dropping] Alarm devre dışı")
            return 0

        persistence_enabled = _as_bool(config.get("persistence_enabled"), True)
        persistence_minutes = _first_float(config, ("persistence_minutes",), 30.0)
        l1_min = _first_float(config, ("min_drop_l1",), 8.0)
        l2_enabled = _as_bool(config.get("l2_enabled"), True)
        l3_enabled = _as_bool(config.get("l3_enabled"), True)

        if persistence_minutes < 0 or l1_min <= 0:
            _legacy.log("[Dropping] Geçersiz persistence/L1 config")
            return 0

        old_config = self.configs.get("dropping")
        old_upsert = self._upsert_alarms
        accepted = {
            "count": 0,
            "persistence_reject": 0,
            "volume_reject": 0,
            "level_reject": 0,
            "history_reject": 0,
        }

        market_map = {
            "1X2": ("dropping_1x2", {"1": "odds1", "X": "oddsx", "2": "odds2"}),
            "O/U 2.5": ("dropping_ou25", {"Over": "over", "Under": "under"}),
            "BTTS": ("dropping_btts", {"Yes": "oddsyes", "No": "oddsno"}),
        }

        def guarded_upsert(table: str, alarms: List[Dict], key_fields: List[str]) -> int:
            if table != "dropping_alarms":
                return old_upsert(table, alarms, key_fields)

            valid = []
            for alarm in alarms:
                level = str(alarm.get("level", "")).upper()
                if (level == "L2" and not l2_enabled) or (level == "L3" and not l3_enabled):
                    accepted["level_reject"] += 1
                    continue

                market_name = alarm.get("market", "")
                mapping = market_map.get(market_name)
                if not mapping:
                    accepted["history_reject"] += 1
                    continue

                market_table, odds_map = mapping
                odds_key = odds_map.get(alarm.get("selection", ""))
                if not odds_key:
                    accepted["history_reject"] += 1
                    continue

                match_hash = alarm.get("match_id_hash", "")
                history = self.get_match_history(
                    match_hash,
                    f"{market_table}_history",
                    alarm.get("home", ""),
                    alarm.get("away", ""),
                    alarm.get("league", ""),
                    alarm.get("match_date", ""),
                )
                if not history:
                    accepted["history_reject"] += 1
                    continue

                latest_volume = 0.0
                for row in reversed(history):
                    latest_volume = _legacy.parse_volume(row.get("volume", 0))
                    if latest_volume > 0:
                        break
                min_volume = _market_min_volume(config, market_name)
                if latest_volume < min_volume:
                    accepted["volume_reject"] += 1
                    continue

                if persistence_enabled and not _dropping_persistence_ok(
                    history=history,
                    odds_key=odds_key,
                    opening_odds=_legacy.parse_float(alarm.get("opening_odds", 0)),
                    min_drop_pct=l1_min,
                    persistence_minutes=persistence_minutes,
                ):
                    accepted["persistence_reject"] += 1
                    continue

                valid.append(alarm)

            accepted["count"] = len(valid)
            return old_upsert(table, valid, key_fields)

        try:
            self.configs["dropping"] = config
            self._upsert_alarms = guarded_upsert
            super().calculate_dropping_alarms()
        finally:
            self._upsert_alarms = old_upsert
            if old_config is None:
                self.configs.pop("dropping", None)
            else:
                self.configs["dropping"] = old_config

        _legacy.log(
            f"[Dropping Stable] accepted={accepted['count']} "
            f"persistence_reject={accepted['persistence_reject']} "
            f"volume_reject={accepted['volume_reject']} "
            f"level_reject={accepted['level_reject']} "
            f"history_reject={accepted['history_reject']}"
        )
        return accepted["count"]


def run_alarm_calculations(supabase_url: str, supabase_key: str):
    """Main entry point using the stabilized AlarmCalculator."""
    calculator = AlarmCalculator(supabase_url, supabase_key)
    return calculator.run_all_calculations()


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3:
        run_alarm_calculations(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python alarm_calculator.py <SUPABASE_URL> <SUPABASE_KEY>")
