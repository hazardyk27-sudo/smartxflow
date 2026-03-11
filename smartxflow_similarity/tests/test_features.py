import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import unittest
from datetime import datetime, timedelta
from smartxflow_similarity.utils import compute_no_vig
from smartxflow_similarity.feature_layer import (
    assign_phase, assign_aggregate_block, split_into_phases,
    classify_reaction, detect_late_reversal, detect_phase_shift,
    compute_phase_odds_features, compute_phase_novig_features,
    compute_price_response_efficiency, compute_money_pct_vs_nv_gap,
    compute_draw_regime, compute_cross_market_features,
    extract_market_features, extract_all_features,
    compute_phase_dominance, compute_timing_signature,
)
from smartxflow_similarity.parser_layer import build_canonical_match


def _make_snap(hours_before_kickoff, kickoff, odds1=2.0, oddsx=3.5, odds2=3.5,
               pct1=50, pctx=25, pct2=25, amt1=100000, amtx=50000, amt2=50000,
               volume=200000):
    t = kickoff - timedelta(hours=hours_before_kickoff)
    return {
        "league": "Test League",
        "home": "Home",
        "away": "Away",
        "date": kickoff.isoformat(),
        "volume": volume,
        "scraped_at": t,
        "odds1": odds1,
        "oddsx": oddsx,
        "odds2": odds2,
        "pct1": pct1,
        "pctx": pctx,
        "pct2": pct2,
        "amt1": amt1,
        "amtx": amtx,
        "amt2": amt2,
    }


KICKOFF = datetime(2025, 3, 10, 18, 0, 0)


class TestPhaseAssignment(unittest.TestCase):
    def test_p1(self):
        self.assertEqual(assign_phase(0.5), "P1_0to1h")

    def test_p2(self):
        self.assertEqual(assign_phase(1.5), "P2_1to2h")

    def test_p3(self):
        self.assertEqual(assign_phase(3.0), "P3_2to4h")

    def test_p10(self):
        self.assertEqual(assign_phase(50), "P10_40plus")

    def test_none(self):
        self.assertIsNone(assign_phase(None))

    def test_boundary_p1_p2(self):
        self.assertEqual(assign_phase(1.0), "P2_1to2h")


class TestAggregateBlock(unittest.TestCase):
    def test_late_block(self):
        self.assertEqual(assign_aggregate_block(2.0), "late_block")

    def test_mid_block(self):
        self.assertEqual(assign_aggregate_block(10.0), "mid_block")

    def test_early_block(self):
        self.assertEqual(assign_aggregate_block(20.0), "early_block")

    def test_boundary_late_mid(self):
        self.assertEqual(assign_aggregate_block(4.0), "mid_block")

    def test_boundary_mid_early(self):
        self.assertEqual(assign_aggregate_block(16.0), "early_block")


class TestSplitIntoPhases(unittest.TestCase):
    def test_basic_split(self):
        snaps = [
            _make_snap(0.5, KICKOFF),
            _make_snap(1.5, KICKOFF),
            _make_snap(5.0, KICKOFF),
            _make_snap(25.0, KICKOFF),
        ]
        phases, blocks = split_into_phases(snaps, KICKOFF)
        self.assertEqual(len(phases["P1_0to1h"]), 1)
        self.assertEqual(len(phases["P2_1to2h"]), 1)
        self.assertEqual(len(phases["P4_4to8h"]), 1)
        self.assertEqual(len(phases["P8_20to30h"]), 1)
        self.assertEqual(len(blocks["late_block"]), 2)
        self.assertEqual(len(blocks["mid_block"]), 1)
        self.assertEqual(len(blocks["early_block"]), 1)


class TestNoVig(unittest.TestCase):
    def test_basic(self):
        nv = compute_no_vig([2.0, 3.5, 3.5])
        self.assertIsNotNone(nv)
        self.assertAlmostEqual(sum(nv), 1.0, places=5)
        self.assertGreater(nv[0], nv[1])

    def test_two_way(self):
        nv = compute_no_vig([1.90, 1.90])
        self.assertAlmostEqual(nv[0], 0.5, places=5)

    def test_invalid(self):
        self.assertIsNone(compute_no_vig([0.5, 3.0, 4.0]))
        self.assertIsNone(compute_no_vig([None, 3.0, 4.0]))


class TestReactionClassification(unittest.TestCase):
    def test_accepted_move(self):
        r = classify_reaction(0.05, 10000, 0.02, 5.0, 100000)
        self.assertEqual(r, "ACCEPTED_MOVE")

    def test_freeze(self):
        r = classify_reaction(0.002, 8000, 0.001, 2.0, 100000)
        self.assertEqual(r, "FREEZE")

    def test_absorbed_pressure(self):
        r = classify_reaction(0.01, 8000, 0.005, 3.0, 100000)
        self.assertEqual(r, "ABSORBED_PRESSURE")

    def test_true_rlm(self):
        r = classify_reaction(0.05, -6000, -0.02, -3.0, 100000)
        self.assertEqual(r, "TRUE_RLM")

    def test_noise(self):
        r = classify_reaction(0.005, 500, 0.001, 0.5, 100000)
        self.assertEqual(r, "NOISE")

    def test_none_input(self):
        r = classify_reaction(None, None, None, None, 100000)
        self.assertEqual(r, "NOISE")


class TestLateReversal(unittest.TestCase):
    def test_reversal_detected(self):
        phase_reactions = {}
        phase_features = {
            "P8_20to30h": {"odds_0_drift": 0.05},
            "P9_30to40h": {"odds_0_drift": 0.03},
            "P1_0to1h": {"odds_0_drift": -0.06},
            "P2_1to2h": {"odds_0_drift": -0.04},
        }
        for p in ["P1_0to1h", "P2_1to2h", "P3_2to4h", "P4_4to8h", "P5_8to12h",
                   "P6_12to16h", "P7_16to20h", "P8_20to30h", "P9_30to40h", "P10_40plus"]:
            if p not in phase_features:
                phase_features[p] = {}
        result = detect_late_reversal(phase_reactions, phase_features)
        self.assertTrue(result)

    def test_no_reversal(self):
        phase_features = {}
        for p in ["P1_0to1h", "P2_1to2h", "P3_2to4h", "P4_4to8h", "P5_8to12h",
                   "P6_12to16h", "P7_16to20h", "P8_20to30h", "P9_30to40h", "P10_40plus"]:
            phase_features[p] = {"odds_0_drift": 0.03}
        result = detect_late_reversal({}, phase_features)
        self.assertFalse(result)


class TestPhaseShift(unittest.TestCase):
    def test_shift_detected(self):
        reactions = {
            "P5_8to12h": {0: "ACCEPTED_MOVE"},
            "P2_1to2h": {0: "TRUE_RLM"},
        }
        self.assertTrue(detect_phase_shift(reactions))

    def test_no_shift(self):
        reactions = {
            "P5_8to12h": {0: "ACCEPTED_MOVE"},
            "P2_1to2h": {0: "ACCEPTED_MOVE"},
        }
        self.assertFalse(detect_phase_shift(reactions))


class TestPriceResponseEfficiency(unittest.TestCase):
    def test_strong_response(self):
        pre = compute_price_response_efficiency(0.10, 1000, 1000000)
        self.assertGreater(pre, 0)

    def test_weak_response(self):
        pre_weak = compute_price_response_efficiency(0.01, 100000, 1000000)
        pre_strong = compute_price_response_efficiency(0.10, 1000, 1000000)
        self.assertLess(pre_weak, pre_strong)

    def test_zero_volume(self):
        pre = compute_price_response_efficiency(0.05, 0, 0)
        self.assertEqual(pre, 0.0)


class TestMoneyPctVsNvGap(unittest.TestCase):
    def test_positive_gap(self):
        gap = compute_money_pct_vs_nv_gap(70, 0.50)
        self.assertAlmostEqual(gap, 0.20, places=2)

    def test_negative_gap(self):
        gap = compute_money_pct_vs_nv_gap(30, 0.50)
        self.assertAlmostEqual(gap, -0.20, places=2)

    def test_none(self):
        self.assertIsNone(compute_money_pct_vs_nv_gap(None, 0.50))


class TestDrawRegime(unittest.TestCase):
    def test_draw_regime_active(self):
        market_features = {
            "moneyway_1x2": {
                "opening_nv": [0.45, 0.28, 0.27],
                "closing_nv": [0.40, 0.32, 0.28],
            },
            "moneyway_ou25": {
                "opening_nv": [0.50, 0.50],
                "closing_nv": [0.42, 0.58],
            },
            "moneyway_btts": {
                "opening_nv": [0.50, 0.50],
                "closing_nv": [0.42, 0.58],
            },
        }
        cross = compute_cross_market_features(market_features)
        dr = compute_draw_regime(market_features, cross)
        self.assertGreater(dr["draw_regime_score"], 0.0)
        self.assertGreater(dr["under_strength"], 0.0)
        self.assertGreater(dr["btts_no_strength"], 0.0)


class TestPhaseOddsFeatures(unittest.TestCase):
    def test_basic(self):
        snaps = [
            {"odds1": 2.0, "oddsx": 3.5, "odds2": 3.5},
            {"odds1": 1.90, "oddsx": 3.60, "odds2": 3.60},
            {"odds1": 1.85, "oddsx": 3.70, "odds2": 3.70},
        ]
        f = compute_phase_odds_features(snaps, ["odds1", "oddsx", "odds2"])
        self.assertEqual(f["odds_0_start"], 2.0)
        self.assertEqual(f["odds_0_end"], 1.85)
        self.assertAlmostEqual(f["odds_0_drift"], -0.15, places=5)
        self.assertEqual(f["odds_0_min"], 1.85)
        self.assertEqual(f["odds_0_max"], 2.0)
        self.assertIsNotNone(f["odds_0_velocity"])
        self.assertIsNotNone(f["odds_0_acceleration"])


class TestTimingSignature(unittest.TestCase):
    def test_late_driven(self):
        phase_features = {}
        for p in ["P1_0to1h", "P2_1to2h", "P3_2to4h"]:
            phase_features[p] = {"odds_0_drift": 0.10}
        for p in ["P4_4to8h", "P5_8to12h", "P6_12to16h", "P7_16to20h",
                   "P8_20to30h", "P9_30to40h", "P10_40plus"]:
            phase_features[p] = {"odds_0_drift": 0.01}
        ts = compute_timing_signature(phase_features, 1)
        self.assertEqual(ts["dominant_timing"], "late_driven")


class TestExtractAllFeatures(unittest.TestCase):
    def test_full_pipeline(self):
        snaps_1x2 = []
        for h in [0.5, 1.5, 3, 6, 10, 14, 18, 25, 35, 45]:
            snaps_1x2.append(_make_snap(
                h, KICKOFF,
                odds1=2.0 - h * 0.003,
                oddsx=3.5 + h * 0.001,
                odds2=3.5 + h * 0.002,
            ))

        rows = {
            "moneyway_1x2_history": snaps_1x2,
            "moneyway_ou25_history": [],
            "moneyway_btts_history": [],
            "dropping_1x2_history": [],
            "dropping_ou25_history": [],
            "dropping_btts_history": [],
        }
        cm = build_canonical_match(rows, kickoff_time=KICKOFF)
        features = extract_all_features(cm)

        self.assertIn("market_features", features)
        self.assertIn("cross_market", features)
        self.assertIn("draw_regime", features)
        self.assertIn("context", features)
        self.assertIn("active_market_weights", features)

        mf = features["market_features"]["moneyway_1x2"]
        self.assertIsNotNone(mf)
        self.assertGreater(mf["total_snapshots"], 0)
        self.assertGreater(mf["phase_coverage"], 0)
        self.assertIn("phase_features", mf)
        self.assertIn("block_features", mf)
        self.assertIn("timing_signature", mf)
        self.assertIn("has_late_reversal", mf)
        self.assertIn("has_phase_shift", mf)

        self.assertIn("late_block", mf["block_features"])
        self.assertIn("mid_block", mf["block_features"])
        self.assertIn("early_block", mf["block_features"])

        ctx = features["context"]
        self.assertIn("data_quality_score", ctx)
        self.assertIn("league_tier", ctx)
        self.assertIn("volume_bucket", ctx)


if __name__ == "__main__":
    unittest.main()
