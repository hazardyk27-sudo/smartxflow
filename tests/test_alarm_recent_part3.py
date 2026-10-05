import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(__file__))
CALC_DIR = os.path.join(ROOT, "desktop", "scraper_standalone")
if CALC_DIR not in sys.path:
    sys.path.insert(0, CALC_DIR)

import alarm_recent_part3 as part3


def _rows(count=21, market="1X2", selection="1"):
    start = datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc)
    rows = []
    for i in range(count):
        rows.append({
            "match_id_hash": "abc123",
            "market": market,
            "selection": selection,
            "volume": 1000 + i * 100,
            "share": 40 + i * 0.2,
            "odds": 2.20 - i * 0.01,
            "scraped_at_utc": (start + timedelta(minutes=10 * i)).isoformat(),
        })
    return rows


def test_sharp_uses_only_last_21_rows_and_generic_odds_field():
    rows = _rows(21, market="BTTS", selection="Y")
    rows[-1]["volume"] = rows[-2]["volume"] + 2500
    rows[-1]["odds"] = 1.70
    cfg = {
        "min_sharp_score": 1,
        "min_amount_change": 100,
        "min_share": 1,
        "volume_multiplier": 15,
        "max_volume_cap": 124,
        "max_odds_cap": 125,
        "max_share_cap": 10,
        "odds_range_1_min": 1.01,
        "odds_range_1_max": 1.80,
        "odds_range_1_mult": 20,
        "odds_range_1_min_drop": 1,
        "share_range_1_min": 1,
        "share_range_1_max": 100,
        "share_range_1_mult": 1,
    }
    result = part3._sharp_candidate(cfg, rows, current_market_volume=10000)
    assert result is not None
    assert result["amount_change"] == 2500
    assert result["current_odds"] == 1.70
    assert result["odds_multiplier_bucket"] == 20
    assert result["sharp_score"] > 1


def test_sharp_respects_min_share_setting():
    rows = _rows()
    rows[-1]["volume"] = rows[-2]["volume"] + 3000
    rows[-1]["share"] = 2
    rows[-1]["odds"] = 1.80
    cfg = {"min_sharp_score": 1, "min_amount_change": 100, "min_share": 5}
    assert part3._sharp_candidate(cfg, rows, 10000) is None


def test_dropping_persistence_uses_opening_and_recent_window_only():
    start = datetime(2026, 10, 3, 15, 0, tzinfo=timezone.utc)
    rows = []
    for i in range(16):
        rows.append({
            "odds": 1.80,
            "scraped_at_utc": (start + timedelta(minutes=10 * i)).isoformat(),
        })
    cfg = {
        "min_drop_l1": 8,
        "min_drop_l2": 13,
        "min_drop_l3": 20,
        "l2_enabled": True,
        "l3_enabled": True,
        "persistence_enabled": True,
        "persistence_minutes": 120,
    }
    result = part3._dropping_eval(rows, opening_odds=2.00, config=cfg)
    assert result is not None
    assert result["qualifies"] is True
    assert result["level"] == "L1"
    assert round(result["drop_pct"], 2) == 10.00


def test_dropping_recovery_requires_two_clean_medians():
    rows = [
        {"odds": 1.80, "scraped_at_utc": "2026-10-03T17:00:00+00:00"},
        {"odds": 1.99, "scraped_at_utc": "2026-10-03T17:10:00+00:00"},
        {"odds": 1.99, "scraped_at_utc": "2026-10-03T17:20:00+00:00"},
        {"odds": 1.99, "scraped_at_utc": "2026-10-03T17:30:00+00:00"},
    ]
    cfg = {
        "min_drop_l1": 8,
        "min_drop_l2": 13,
        "min_drop_l3": 20,
        "persistence_enabled": False,
    }
    result = part3._dropping_eval(rows, 2.00, cfg)
    assert result["qualifies"] is False
    assert result["recovered"] is True


class NoPrefetchCalculator:
    def __init__(self):
        self.configs = {}
        self._history_cache = {}
        self._matches_cache = {}
        self._active_hashes_cache = []
        self._active_hashes_checked = False
        self._incremental_cleanup_at = -part3.CLEANUP_INTERVAL_SECONDS
        self.calls = []

    def refresh_configs(self):
        self.calls.append("refresh")

    def calculate_bigmoney_alarms(self):
        self.calls.append("bigmoney")
        return 1

    def calculate_sharp_alarms(self):
        self.calls.append("sharp")
        return 2

    def calculate_volumeshock_alarms(self):
        self.calls.append("volumeshock")
        return 3

    def calculate_dropping_alarms(self):
        self.calls.append("dropping")
        return 4

    def calculate_volumeleader_alarms(self):
        self.calls.append("volumeleader")
        return 5

    def calculate_mim_alarms(self):
        self.calls.append("mim")
        return 6

    def calculate_insider_alarms(self):
        raise AssertionError("legacy Insider motor must not run in production incremental path")

    def calculate_publicmove_alarms(self):
        raise AssertionError("legacy PublicMove motor must not run in production incremental path")

    def _cleanup_expired_match_alarms(self):
        self.calls.append("cleanup")

    def get_matches_with_latest(self, *_args, **_kwargs):
        raise AssertionError("legacy match prefetch must not run")

    def batch_fetch_history(self, *_args, **_kwargs):
        raise AssertionError("legacy history prefetch must not run")


def test_six_alarm_runner_skips_legacy_full_prefetch_and_unsupported_motors():
    calc = NoPrefetchCalculator()
    total = part3._run_all_incremental(calc)
    assert total == 21
    assert calc.calls[:7] == [
        "refresh", "bigmoney", "sharp", "volumeshock", "dropping", "volumeleader", "mim"
    ]
    assert "cleanup" in calc.calls
