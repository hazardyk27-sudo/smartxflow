from __future__ import annotations

import unittest

from predictor_policy import (
    PredictorPolicyError,
    compare_stage_preferences,
    summarize_comparisons,
    user_supplied_price_evidence,
    validate_stage1,
    validate_stage2,
    validate_stage3,
)


class PredictorPolicyTests(unittest.TestCase):
    def test_stage1_scans_full_universe_but_reports_only_candidates(self):
        payload = {
            "stage": "STAGE1",
            "external_research_used": False,
            "scope": {
                "source_fixture_ids": ["m1", "m2", "m3"],
                "screened_fixture_ids": ["m1", "m2", "m3"],
            },
            "matches": [
                {
                    "fixture_id": "m2",
                    "screening": {"selected": True, "attention_reasons": ["late money acceleration"]},
                    "preference": {"market": "1X2", "selection": "Away", "price": 2.35},
                }
            ],
        }
        result = validate_stage1(payload)
        self.assertTrue(result.valid, result.violations)

    def test_stage1_rejects_partial_internal_scan(self):
        payload = {
            "stage": "STAGE1",
            "external_research_used": False,
            "scope": {
                "source_fixture_ids": ["m1", "m2"],
                "screened_fixture_ids": ["m1"],
            },
            "matches": [],
        }
        result = validate_stage1(payload)
        self.assertFalse(result.valid)
        self.assertIn("SXF-S1-002", {item.rule_id for item in result.violations})

    def test_stage1_rejects_non_native_market(self):
        payload = {
            "stage": "STAGE1",
            "external_research_used": False,
            "scope": {"source_fixture_ids": ["m1"], "screened_fixture_ids": ["m1"]},
            "matches": [
                {
                    "fixture_id": "m1",
                    "screening": {"selected": True, "attention_reasons": ["price response"]},
                    "preference": {"market": "Handicap", "selection": "Away +1.5"},
                }
            ],
        }
        result = validate_stage1(payload)
        self.assertFalse(result.valid)
        self.assertIn("SXF-S1-005", {item.rule_id for item in result.violations})

    def test_stage2_enforces_fact_budget_counter_and_authorization(self):
        payload = {
            "stage": "STAGE2",
            "authorized_by_user": True,
            "stage1_candidate_ids": ["m1"],
            "matches": [
                {
                    "fixture_id": "m1",
                    "frozen_stage1_preference": {"market": "1X2", "selection": "Home"},
                    "facts": [
                        {"kind": "FACT", "relationship": "SUPPORTS"},
                        {"kind": "FACT", "relationship": "SUPPORTS"},
                        {"kind": "FACT", "relationship": "SUPPORTS"},
                        {"kind": "FACT", "relationship": "NEUTRAL"},
                        {"kind": "INFERENCE", "relationship": "SUPPORTS"},
                        {"kind": "FACT", "relationship": "CONTRADICTS"},
                    ],
                    "research_counter": "Away transition threat is credible.",
                    "coverage": "MEDIUM",
                    "verdict": "PARTIALLY_CONFIRMED",
                }
            ],
        }
        self.assertTrue(validate_stage2(payload).valid)
        payload["matches"][0]["facts"].append({"kind": "FACT", "relationship": "NEUTRAL"})
        result = validate_stage2(payload)
        self.assertFalse(result.valid)
        self.assertIn("SXF-S2-004", {item.rule_id for item in result.violations})

    def test_stage3_grade_mapping_is_hard(self):
        base = {
            "stage": "STAGE3",
            "authorized_by_user": True,
            "stage1_candidate_ids": ["m1"],
            "matches": [
                {
                    "fixture_id": "m1",
                    "preference": {"market": "1X2", "selection": "Home"},
                    "stage1_baseline": {"market": "1X2", "selection": "Home"},
                    "grade": "B",
                    "decision": "BET",
                    "counter_severity": "MEDIUM",
                    "raw_confidence": 78,
                    "final_confidence": 71,
                    "divergence_state": "MIXED",
                    "execution_type": "NATIVE",
                    "prediction_at": "2026-10-07T18:00:00+03:00",
                    "archive_intent": True,
                    "price_evidence": {"origin": "SXF_NATIVE", "price": 1.90, "observed_at": "2026-10-07T18:00:00+03:00"},
                }
            ],
        }
        result = validate_stage3(base)
        self.assertFalse(result.valid)
        self.assertIn("SXF-S3-008", {item.rule_id for item in result.violations})

    def test_user_supplied_non_native_price_can_support_bet(self):
        price = user_supplied_price_evidence(
            market="Handicap",
            selection="Frosinone +1.5",
            price=1.72,
            observed_at="2026-10-07T19:15:00+03:00",
        )
        payload = {
            "stage": "STAGE3",
            "authorized_by_user": True,
            "stage1_candidate_ids": ["m1"],
            "matches": [
                {
                    "fixture_id": "m1",
                    "preference": {"market": "Handicap", "selection": "Frosinone +1.5"},
                    "stage1_baseline": {"market": "1X2", "selection": "Frosinone"},
                    "grade": "A",
                    "decision": "BET",
                    "counter_severity": "LIGHT",
                    "raw_confidence": 80,
                    "final_confidence": 77,
                    "divergence_state": "CONFIRMED",
                    "execution_type": "PROTECTION",
                    "prediction_at": "2026-10-07T19:16:00+03:00",
                    "archive_intent": True,
                    "price_evidence": price,
                }
            ],
        }
        result = validate_stage3(payload)
        self.assertTrue(result.valid, result.violations)

    def test_user_supplied_price_must_match_exact_market_and_selection(self):
        with self.assertRaises(PredictorPolicyError):
            user_supplied_price_evidence(
                market="Handicap",
                selection="Frosinone +1.5",
                price=1.72,
                observed_at="not-a-time",
            )

    def test_stage1_vs_stage3_comparison_detects_improvement(self):
        comparison = compare_stage_preferences(
            fixture_id="m1",
            match={"home": "Home", "away": "Away"},
            stage1_preference={"market": "1X2", "selection": "Away", "price": 3.20},
            stage3_preference={"market": "Double Chance", "selection": "Away X2", "price": 1.72},
            stage3_action="BET",
            final_score="1-1",
        )
        self.assertEqual(comparison.stage1.result, "LOSS")
        self.assertEqual(comparison.stage3.result, "WIN")
        self.assertEqual(comparison.transition, "IMPROVED")
        summary = summarize_comparisons([comparison])
        self.assertEqual(summary["transitions"]["IMPROVED"], 1)
        self.assertEqual(summary["stage1"]["hit_rate"], 0.0)
        self.assertEqual(summary["stage3"]["hit_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
