import os
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))
CALC_DIR = os.path.join(ROOT, "desktop", "scraper_standalone")
if CALC_DIR not in sys.path:
    sys.path.insert(0, CALC_DIR)

import alarm_recent


class FakeCalculator:
    def __init__(self):
        self.configs = {
            "bigmoney": {"enabled": True, "big_money_limit": 1000},
            "mim": {
                "enabled": True,
                "min_impact_for_alarm": 0.20,
                "min_market_volume": 1000,
                "min_new_money": 300,
            },
        }
        self._active_signal = {
            "id": 10,
            "source": "replit",
            "created_at": "2026-10-03T18:10:00+00:00",
        }
        self.upserts = []
        self.snapshot_get_calls = 0

    def _default_configs(self):
        return {
            "mim": {
                "enabled": True,
                "min_impact_for_alarm": 0.20,
                "min_market_volume": 1000,
                "min_new_money": 300,
            }
        }

    def _get(self, table, params=""):
        if table == "scraper_signal":
            return [
                {"id": 9, "created_at": "2026-10-03T18:00:00+00:00", "source": "replit"},
                {"id": 8, "created_at": "2026-10-03T17:50:00+00:00", "source": "replit"},
            ]
        if table == "moneyway_snapshots":
            self.snapshot_get_calls += 1
            if "offset=0" not in params:
                return []
            return [
                {"match_id_hash": "abc123", "market": "1X2", "selection": "1", "volume": 1000, "share": 40, "odds": 2.10, "scraped_at_utc": "2026-10-03T17:49:30+00:00"},
                {"match_id_hash": "abc123", "market": "1X2", "selection": "X", "volume": 800, "share": 32, "odds": 3.20, "scraped_at_utc": "2026-10-03T17:49:30+00:00"},
                {"match_id_hash": "abc123", "market": "1X2", "selection": "2", "volume": 700, "share": 28, "odds": 3.60, "scraped_at_utc": "2026-10-03T17:49:30+00:00"},
                {"match_id_hash": "abc123", "market": "1X2", "selection": "1", "volume": 2200, "share": 55, "odds": 2.00, "scraped_at_utc": "2026-10-03T17:59:30+00:00"},
                {"match_id_hash": "abc123", "market": "1X2", "selection": "X", "volume": 900, "share": 22, "odds": 3.25, "scraped_at_utc": "2026-10-03T17:59:30+00:00"},
                {"match_id_hash": "abc123", "market": "1X2", "selection": "2", "volume": 900, "share": 23, "odds": 3.70, "scraped_at_utc": "2026-10-03T17:59:30+00:00"},
                {"match_id_hash": "abc123", "market": "1X2", "selection": "1", "volume": 3600, "share": 69, "odds": 1.90, "scraped_at_utc": "2026-10-03T18:09:30+00:00"},
                {"match_id_hash": "abc123", "market": "1X2", "selection": "X", "volume": 1000, "share": 19, "odds": 3.30, "scraped_at_utc": "2026-10-03T18:09:30+00:00"},
                {"match_id_hash": "abc123", "market": "1X2", "selection": "2", "volume": 650, "share": 12, "odds": 3.90, "scraped_at_utc": "2026-10-03T18:09:30+00:00"},
            ]
        if table == "fixtures":
            return [{
                "match_id_hash": "abc123",
                "home_team": "Home",
                "away_team": "Away",
                "league": "League",
                "kickoff_utc": "2026-10-03T20:00:00+00:00",
                "fixture_date": "2026-10-03",
            }]
        if table in {"bigmoney_alarms", "mim_alarms"}:
            return []
        return []

    def _upsert_alarms(self, table, alarms, key_fields):
        self.upserts.append((table, alarms, key_fields))
        return len(alarms)


def test_recent_snapshot_window_is_shared_and_keeps_only_three_per_key():
    calc = FakeCalculator()
    first = alarm_recent._fetch_recent_snapshot_window(calc)
    second = alarm_recent._fetch_recent_snapshot_window(calc)

    assert first is second
    assert calc.snapshot_get_calls == 1
    assert len(first["series"][("abc123", "1X2", "1")]) == 3
    assert ("abc123", "1X2", "1") in first["current_keys"]


def test_bigmoney_uses_only_recent_three_snapshots_and_marks_consecutive_as_huge():
    calc = FakeCalculator()
    count = alarm_recent._bigmoney_incremental(calc)

    assert count == 1
    table, alarms, keys = calc.upserts[-1]
    assert table == "bigmoney_alarms"
    assert keys == ["match_id_hash", "market", "selection"]
    alarm = alarms[0]
    assert alarm["incoming_money"] == 1400
    assert alarm["is_huge"] is True
    assert alarm["huge_total"] == 2600
    assert alarm["selection_total"] == 3600


def test_mim_uses_only_last_two_snapshots_and_current_market_total():
    calc = FakeCalculator()
    count = alarm_recent._mim_incremental(calc)

    assert count == 1
    table, alarms, keys = calc.upserts[-1]
    assert table == "mim_alarms"
    assert keys == ["match_id_hash", "market", "selection"]
    alarm = alarms[0]
    assert alarm["incoming_volume"] == 1400
    assert alarm["total_market_volume"] == 5250
    assert round(alarm["impact_score"], 4) == round(1400 / 5250, 4)


def test_disabled_bigmoney_does_not_read_snapshots():
    calc = FakeCalculator()
    calc.configs["bigmoney"]["enabled"] = False
    assert alarm_recent._bigmoney_incremental(calc) == 0
    assert calc.snapshot_get_calls == 0


def test_disabled_mim_does_not_read_snapshots():
    calc = FakeCalculator()
    calc.configs["mim"]["enabled"] = False
    assert alarm_recent._mim_incremental(calc) == 0
    assert calc.snapshot_get_calls == 0
