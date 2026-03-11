import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import unittest
import json
import tempfile
from datetime import datetime, timedelta

from smartxflow_similarity.parser_layer import build_canonical_match
from smartxflow_similarity.feature_layer import extract_all_features
from smartxflow_similarity.feature_store import build_feature_entry, save_store, load_store
from smartxflow_similarity.similarity_layer import (
    passes_hard_filter, compute_similarity, find_similar_matches,
    compute_market_shape_score, compute_flow_shape_score,
    compute_price_reaction_score, compute_context_score,
)
from smartxflow_similarity.engine_layer import (
    run_engine, compute_result_distribution, explain_single_match,
    compute_overall_explainability,
)


KICKOFF = datetime(2025, 3, 10, 18, 0, 0)


def _make_snap(hours_before, kickoff=KICKOFF, odds1=2.0, oddsx=3.5, odds2=3.5,
               pct1=50, pctx=25, pct2=25, amt1=100000, amtx=50000, amt2=50000,
               volume=200000):
    t = kickoff - timedelta(hours=hours_before)
    return {
        "league": "England Premier League",
        "home": "Home",
        "away": "Away",
        "date": kickoff.isoformat(),
        "volume": str(volume),
        "scraped_at": t.isoformat(),
        "odds1": str(odds1),
        "oddsx": str(oddsx),
        "odds2": str(odds2),
        "pct1": str(pct1),
        "pctx": str(pctx),
        "pct2": str(pct2),
        "amt1": str(amt1),
        "amtx": str(amtx),
        "amt2": str(amt2),
    }


def _build_match(home="Home", away="Away", league="England Premier League",
                 odds1_base=2.0, drift=-0.003, kickoff=KICKOFF, result=None):
    snaps = []
    for h in [0.5, 1.5, 3, 6, 10, 14, 18, 25, 35, 45]:
        snaps.append(_make_snap(
            h, kickoff,
            odds1=odds1_base + drift * h,
            oddsx=3.5 - drift * h * 0.3,
            odds2=3.5 - drift * h * 0.5,
        ))
    for s in snaps:
        s["home"] = home
        s["away"] = away
        s["league"] = league
    rows = {
        "moneyway_1x2_history": snaps,
        "moneyway_ou25_history": [],
        "moneyway_btts_history": [],
        "dropping_1x2_history": [],
        "dropping_ou25_history": [],
        "dropping_btts_history": [],
    }
    cm = build_canonical_match(rows, kickoff_time=kickoff)
    entry = build_feature_entry(cm, result=result)
    return entry


class TestHardFilter(unittest.TestCase):
    def test_same_passes(self):
        e = _build_match()
        self.assertTrue(passes_hard_filter(e, e))

    def test_different_tier_fails(self):
        q = _build_match(league="England Premier League")
        c = _build_match(league="Unknown League 4th Div")
        c["league_tier"] = 5
        q["league_tier"] = 1
        self.assertFalse(passes_hard_filter(q, c))

    def test_different_odds_fails(self):
        q = _build_match(odds1_base=1.30)
        c = _build_match(odds1_base=3.50)
        self.assertFalse(passes_hard_filter(q, c))

    def test_low_quality_fails(self):
        q = _build_match()
        c = _build_match()
        c["data_quality_score"] = 0.1
        self.assertFalse(passes_hard_filter(q, c))


class TestSimilarityScore(unittest.TestCase):
    def test_identical_high_score(self):
        e = _build_match()
        sim = compute_similarity(e, e)
        self.assertGreater(sim["total_score"], 0.5)

    def test_different_lower_score(self):
        q = _build_match(odds1_base=2.0, drift=-0.003)
        c = _build_match(odds1_base=2.3, drift=0.005)
        sim = compute_similarity(q, c)
        same_sim = compute_similarity(q, q)
        self.assertLess(sim["total_score"], same_sim["total_score"])

    def test_block_scores_present(self):
        q = _build_match()
        c = _build_match(odds1_base=2.1)
        sim = compute_similarity(q, c)
        self.assertIn("market_shape", sim["block_scores"])
        self.assertIn("flow_shape", sim["block_scores"])
        self.assertIn("price_reaction", sim["block_scores"])
        self.assertIn("cross_market_draw", sim["block_scores"])
        self.assertIn("context", sim["block_scores"])


class TestFindSimilar(unittest.TestCase):
    def test_finds_similar(self):
        query = _build_match(home="Q1", away="Q2")
        store = [
            _build_match(home="A", away="B", odds1_base=2.05, result="HOME"),
            _build_match(home="C", away="D", odds1_base=2.10, result="DRAW"),
            _build_match(home="E", away="F", odds1_base=5.0, result="AWAY"),
        ]
        results = find_similar_matches(query, store, top_n=5)
        self.assertGreater(len(results), 0)
        self.assertGreater(results[0]["similarity"]["total_score"], 0)

    def test_excludes_self(self):
        entry = _build_match(home="SameHome", away="SameAway")
        store = [entry]
        results = find_similar_matches(entry, store)
        self.assertEqual(len(results), 0)


class TestResultDistribution(unittest.TestCase):
    def test_basic_distribution(self):
        matches = [
            {"candidate": {"result": "HOME"}, "similarity": {"total_score": 0.8}},
            {"candidate": {"result": "HOME"}, "similarity": {"total_score": 0.7}},
            {"candidate": {"result": "DRAW"}, "similarity": {"total_score": 0.6}},
            {"candidate": {"result": "AWAY"}, "similarity": {"total_score": 0.5}},
        ]
        dist = compute_result_distribution(matches)
        self.assertEqual(dist["simple"]["total"], 4)
        self.assertEqual(dist["simple"]["home"], 50.0)
        self.assertEqual(dist["simple"]["draw"], 25.0)
        self.assertEqual(dist["simple"]["away"], 25.0)

    def test_weighted_favors_higher_sim(self):
        matches = [
            {"candidate": {"result": "HOME"}, "similarity": {"total_score": 0.9}},
            {"candidate": {"result": "AWAY"}, "similarity": {"total_score": 0.3}},
        ]
        dist = compute_result_distribution(matches)
        self.assertGreater(dist["weighted"]["home"], dist["weighted"]["away"])

    def test_empty(self):
        dist = compute_result_distribution([])
        self.assertEqual(dist["simple"]["total"], 0)

    def test_percentages_sum_100(self):
        matches = [
            {"candidate": {"result": "HOME"}, "similarity": {"total_score": 0.8}},
            {"candidate": {"result": "DRAW"}, "similarity": {"total_score": 0.7}},
            {"candidate": {"result": "AWAY"}, "similarity": {"total_score": 0.6}},
        ]
        dist = compute_result_distribution(matches)
        total_simple = dist["simple"]["home"] + dist["simple"]["draw"] + dist["simple"]["away"]
        self.assertAlmostEqual(total_simple, 100.0, places=0)
        total_weighted = dist["weighted"]["home"] + dist["weighted"]["draw"] + dist["weighted"]["away"]
        self.assertAlmostEqual(total_weighted, 100.0, places=0)

    def test_no_results(self):
        matches = [
            {"candidate": {"result": None}, "similarity": {"total_score": 0.8}},
        ]
        dist = compute_result_distribution(matches)
        self.assertEqual(dist["simple"]["total"], 0)


class TestExplainability(unittest.TestCase):
    def test_single_match_explanation(self):
        query = _build_match(home="Q1", away="Q2")
        candidate = _build_match(home="C1", away="C2", odds1_base=2.05, result="HOME")
        sim = compute_similarity(query, candidate)
        match_result = {"candidate": candidate, "similarity": sim}

        exp = explain_single_match(query, match_result)
        self.assertIn("match_name", exp)
        self.assertIn("similarity_score", exp)
        self.assertIn("top_3_similar_blocks", exp)
        self.assertIn("top_2_divergent_blocks", exp)
        self.assertIn("closest_phases", exp)
        self.assertIn("farthest_phases", exp)
        self.assertIn("pattern_label", exp)
        self.assertEqual(len(exp["top_3_similar_blocks"]), 3)
        self.assertGreaterEqual(len(exp["top_2_divergent_blocks"]), 1)

    def test_overall_explainability(self):
        query = _build_match(home="Q", away="Q2")
        explanations = [
            {
                "top_3_similar_blocks": [
                    {"block": "market_shape", "score": 0.8, "label": "MS"},
                    {"block": "flow_shape", "score": 0.7, "label": "FS"},
                    {"block": "context", "score": 0.6, "label": "CTX"},
                ],
                "top_2_divergent_blocks": [
                    {"block": "cross_market_draw", "score": 0.3, "label": "CMD"},
                    {"block": "price_reaction", "score": 0.4, "label": "PR"},
                ],
                "pattern_label": "Test Pattern",
            }
        ]
        overall = compute_overall_explainability(query, [], explanations)
        self.assertIn("top_3_common_traits", overall)
        self.assertIn("top_2_risk_traits", overall)
        self.assertIn("main_pattern_label", overall)
        self.assertEqual(overall["main_pattern_label"], "Test Pattern")


class TestFeatureStore(unittest.TestCase):
    def test_save_and_load(self):
        entries = [
            _build_match(home="A", away="B", result="HOME"),
            _build_match(home="C", away="D", result="DRAW"),
        ]
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as f:
            tmpfile = f.name

        try:
            save_store(entries, tmpfile)
            loaded = load_store(tmpfile)
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[0]["match_name"], "A vs B")
            self.assertEqual(loaded[1]["result"], "DRAW")
        finally:
            os.unlink(tmpfile)


class TestRunEngine(unittest.TestCase):
    def test_full_engine_run(self):
        query = _build_match(home="Query", away="Team")
        store = [
            _build_match(home="A", away="B", odds1_base=2.05, result="HOME"),
            _build_match(home="C", away="D", odds1_base=1.95, result="DRAW"),
            _build_match(home="E", away="F", odds1_base=2.10, result="AWAY"),
            _build_match(home="G", away="H", odds1_base=2.02, result="HOME"),
        ]
        result = run_engine(query, store)

        self.assertIn("query_summary", result)
        self.assertIn("similar_matches", result)
        self.assertIn("result_distribution", result)
        self.assertIn("overall_explainability", result)
        self.assertGreater(result["matches_found"], 0)

        for m in result["similar_matches"]:
            self.assertIn("similarity_score", m)
            self.assertIn("top_3_similar_blocks", m)
            self.assertIn("top_2_divergent_blocks", m)
            self.assertIn("closest_phases", m)
            self.assertIn("farthest_phases", m)
            self.assertIn("pattern_label", m)

        dist = result["result_distribution"]
        if dist["simple"]["total"] > 0:
            total = dist["simple"]["home"] + dist["simple"]["draw"] + dist["simple"]["away"]
            self.assertAlmostEqual(total, 100.0, places=0)


if __name__ == "__main__":
    unittest.main()
