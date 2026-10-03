import os
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))
CALC_DIR = os.path.join(ROOT, "desktop", "scraper_standalone")
if CALC_DIR not in sys.path:
    sys.path.insert(0, CALC_DIR)

import alarm_recent_part2 as part2


class FakeCalculator:
    def __init__(self):
        self.configs = {
            "volumeleader": {
                "enabled": True,
                "min_volume_1x2": 2000,
                "min_volume_ou25": 1000,
                "min_volume_btts": 600,
                "leader_threshold": 50,
            },
            "volumeshock": {
                "enabled": True,
                "min_volume_1x2": 2000,
                "min_volume_ou25": 1000,
                "min_volume_btts": 600,
                "hacim_soku_min_esik": 7,
                "hacim_soku_min_saat": 2,
                "min_son_snapshot_para": 499,
            },
        }
        self._active_signal = {
            "id": 20,
            "source": "replit",
            "created_at": "2026-10-03T18:10:00+00:00",
        }
        self.posts = []
        self.upserts = []
        self.snapshot_get_calls = 0

    def _default_configs(self):
        return {
            "volumeleader": dict(self.configs["volumeleader"]),
            "volumeshock": dict(self.configs["volumeshock"]),
        }

    def _get(self, table, params=""):
        if table == "scraper_signal":
            return [
                {"id": 19, "created_at": "2026-10-03T18:00:00+00:00", "source": "replit"},
                {"id": 18, "created_at": "2026-10-03T17:50:00+00:00", "source": "replit"},
                {"id": 17, "created_at": "2026-10-03T17:40:00+00:00", "source": "replit"},
                {"id": 16, "created_at": "2026-10-03T17:30:00+00:00", "source": "replit"},
                {"id": 15, "created_at": "2026-10-03T17:20:00+00:00", "source": "replit"},
            ]
        if table == "moneyway_snapshots":
            self.snapshot_get_calls += 1
            if "offset=0" not in params:
                return []
            timestamps = [
                "2026-10-03T17:19:30+00:00",
                "2026-10-03T17:29:30+00:00",
                "2026-10-03T17:39:30+00:00",
                "2026-10-03T17:49:30+00:00",
                "2026-10-03T17:59:30+00:00",
                "2026-10-03T18:09:30+00:00",
            ]
            one = [700, 800, 900, 1000, 1200, 1100]
            draw = [600, 700, 800, 900, 1000, 900]
            two = [500, 600, 700, 800, 900, 2500]
            rows = []
            for idx, ts in enumerate(timestamps):
                total = one[idx] + draw[idx] + two[idx]
                for selection, volume in (("1", one[idx]), ("X", draw[idx]), ("2", two[idx])):
                    rows.append({
                        "match_id_hash": "abc123",
                        "market": "1X2",
                        "selection": selection,
                        "volume": volume,
                        "share": volume / total * 100,
                        "odds": 2.0,
                        "scraped_at_utc": ts,
                    })
            return rows
        if table == "fixtures":
            return [{
                "match_id_hash": "abc123",
                "home_team": "Home",
                "away_team": "Away",
                "league": "League",
                "kickoff_utc": "2026-10-03T21:00:00+00:00",
                "fixture_date": "2026-10-03",
            }]
        if table in {"volume_leader_alarms", "volumeshock_alarms"}:
            return []
        return []

    def _post(self, table, payload, on_conflict=None):
        self.posts.append((table, payload, on_conflict))
        return True

    def _upsert_alarms(self, table, alarms, key_fields):
        self.upserts.append((table, alarms, key_fields))
        return len(alarms)


def test_part2_window_is_shared_and_keeps_six_per_selection():
    calc = FakeCalculator()
    first = part2._fetch_part2_snapshot_window(calc)
    second = part2._fetch_part2_snapshot_window(calc)
    assert first is second
    assert calc.snapshot_get_calls == 1
    assert len(first["series"][("abc123", "1X2", "2")]) == 6
    assert ("abc123", "1X2") in first["current_markets"]


def test_volumeleader_uses_only_last_two_complete_market_states():
    calc = FakeCalculator()
    count = part2._volumeleader_incremental(calc)
    assert count == 1
    table, alarms, conflict = calc.posts[-1]
    assert table == "volume_leader_alarms"
    assert conflict == "home,away,market,old_leader,new_leader"
    alarm = alarms[0]
    assert alarm["old_leader"] == "1"
    assert alarm["new_leader"] == "2"
    assert alarm["total_volume"] == 4500
    assert alarm["new_leader_share"] > 50


def test_volumeshock_uses_current_delta_and_four_previous_positive_deltas():
    calc = FakeCalculator()
    count = part2._volumeshock_incremental(calc)
    assert count == 1
    table, alarms, keys = calc.upserts[-1]
    assert table == "volumeshock_alarms"
    assert keys == ["match_id_hash", "market", "selection"]
    alarm = alarms[0]
    assert alarm["selection"] == "2"
    assert alarm["incoming_money"] == 1600
    assert alarm["avg_previous"] == 100
    assert alarm["volume_shock_value"] == 16.0


def test_volumeshock_rejects_when_kickoff_is_too_close():
    calc = FakeCalculator()
    original_get = calc._get
    def get_with_close_kickoff(table, params=""):
        if table == "fixtures":
            return [{
                "match_id_hash": "abc123",
                "home_team": "Home",
                "away_team": "Away",
                "league": "League",
                "kickoff_utc": "2026-10-03T19:00:00+00:00",
                "fixture_date": "2026-10-03",
            }]
        return original_get(table, params)
    calc._get = get_with_close_kickoff
    assert part2._volumeshock_incremental(calc) == 0
    assert calc.upserts == []


def test_volumeshock_requires_real_positive_baseline():
    calc = FakeCalculator()
    original_get = calc._get
    def flat_baseline(table, params=""):
        rows = original_get(table, params)
        if table != "moneyway_snapshots":
            return rows
        adjusted = []
        for row in rows:
            copy = dict(row)
            if copy["selection"] == "2":
                if copy["scraped_at_utc"] != "2026-10-03T18:09:30+00:00":
                    copy["volume"] = 500
                else:
                    copy["volume"] = 2100
            adjusted.append(copy)
        return adjusted
    calc._get = flat_baseline
    assert part2._volumeshock_incremental(calc) == 0
    assert calc.upserts == []


def test_disabled_part2_alarms_do_not_read_snapshots():
    calc = FakeCalculator()
    calc.configs["volumeleader"]["enabled"] = False
    calc.configs["volumeshock"]["enabled"] = False
    assert part2._volumeleader_incremental(calc) == 0
    assert part2._volumeshock_incremental(calc) == 0
    assert calc.snapshot_get_calls == 0
