import os
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))
CALC_DIR = os.path.join(ROOT, "desktop", "scraper_standalone")
if CALC_DIR not in sys.path:
    sys.path.insert(0, CALC_DIR)

import alarm_calculator as stable


def _bare_calculator(configs=None):
    calc = object.__new__(stable.AlarmCalculator)
    calc.configs = configs or {}
    calc._history_cache = {}
    calc._matches_cache = {}
    calc._active_hashes_checked = False
    calc._active_hashes_cache = []
    return calc


def test_effective_config_merges_partial_live_settings_and_legacy_aliases():
    calc = _bare_calculator({
        "mim": {
            "enabled": True,
            "min_impact_threshold": 0.33,
            "min_prev_volume": 2500,
        }
    })
    cfg = stable._effective_config(calc, "mim")
    assert cfg["min_impact_for_alarm"] == 0.33
    assert cfg["min_market_volume"] == 2500
    assert cfg["min_new_money"] == 300


def test_volumeshock_gate_enforces_market_volume_and_minimum_hours():
    assert stable._volumeshock_candidate_ok(2000, 1999, 3.0, 2.0)
    assert not stable._volumeshock_candidate_ok(1500, 1999, 3.0, 2.0)
    assert not stable._volumeshock_candidate_ok(2000, 1999, 1.5, 2.0)
    assert not stable._volumeshock_candidate_ok(2000, 1999, None, 2.0)


def test_hours_until_kickoff_is_timezone_safe():
    hours = stable._hours_until_kickoff(
        "2026-10-03T21:00:00+03:00",
        "2026-10-03T18:00:00+03:00",
    )
    assert round(hours, 3) == 3.0


def test_dropping_persistence_requires_full_window():
    history = [
        {"scraped_at": "2026-10-03T17:20:00+03:00", "odds1": 2.00},
        {"scraped_at": "2026-10-03T17:30:00+03:00", "odds1": 1.82},
        {"scraped_at": "2026-10-03T17:40:00+03:00", "odds1": 1.81},
        {"scraped_at": "2026-10-03T17:50:00+03:00", "odds1": 1.80},
        {"scraped_at": "2026-10-03T18:00:00+03:00", "odds1": 1.80},
        {"scraped_at": "2026-10-03T18:10:00+03:00", "odds1": 1.79},
        {"scraped_at": "2026-10-03T18:20:00+03:00", "odds1": 1.78},
    ]
    assert stable._dropping_persistence_ok(
        history, "odds1", opening_odds=2.00, min_drop_pct=8.0, persistence_minutes=30
    )


def test_dropping_persistence_rejects_break_inside_window():
    history = [
        {"scraped_at": "2026-10-03T17:20:00+03:00", "odds1": 2.00},
        {"scraped_at": "2026-10-03T17:30:00+03:00", "odds1": 1.82},
        {"scraped_at": "2026-10-03T17:40:00+03:00", "odds1": 1.81},
        {"scraped_at": "2026-10-03T17:50:00+03:00", "odds1": 1.80},
        {"scraped_at": "2026-10-03T18:00:00+03:00", "odds1": 1.99},
        {"scraped_at": "2026-10-03T18:10:00+03:00", "odds1": 1.99},
        {"scraped_at": "2026-10-03T18:20:00+03:00", "odds1": 1.78},
    ]
    assert not stable._dropping_persistence_ok(
        history, "odds1", opening_odds=2.00, min_drop_pct=8.0, persistence_minutes=30
    )


def test_disabled_alarm_boolean_is_respected():
    assert stable._as_bool(False) is False
    assert stable._as_bool("false") is False
    assert stable._as_bool("off") is False
    assert stable._as_bool(True) is True
