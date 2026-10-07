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
    def _stage1_payload(self):
        return {
            "run_id": "s1-run",
            "stage": "STAGE1",
            "external_research_used": False,
            "scope": {
                "universe_resolved": True,
                "source_fixture_ids": ["m1", "m2", "m3"],
            },
            "screening_results": [
                {"fixture_id": "m1", "temporal_reviewed": True, "selected": False},
                {
                    "fixture_id": "m2",
                    "temporal_reviewed": True,
                    "selected": True,
                    "attention_signals": ["MONEY_ACCELERATION", "PRICE_CONFIRMATION"],
                },
                {"fixture_id": "m3", "temporal_reviewed": True, "selected": False},
            ],
            "matches": [
                {
                    "fixture_id": "m2",
                    "preference": {"market": "1X2", "selection": "Away", "price": 2.35},
                }
            ],
        }

    def _stage2_payload(self):
        return {
            "run_id": "s2-run",
            "stage": "STAGE2",
            "authorized_by_user": True,
            "predecessor_stage1_run_id": "s1-run",
            "stage1_candidate_ids": ["m1"],
            "matches": [
                {
                    "fixture_id": "m1",
                    "frozen_stage1_preference": {"market": "1X2", "selection": "Home"},
                    "research_checks": {
                        "squad_checked": True,
                        "performance_checked": True,
                        "counter_checked": True,
                        "coverage_classified": True,
                    },
                    "facts": [
                        {"claim": "Starter availability checked.", "kind": "FACT", "relationship": "NEUTRAL"},
                        {"claim": "Recent chance creation is stable.", "kind": "FACT", "relationship": "SUPPORTS"},
                        {"claim": "Away transition threat is credible.", "kind": "FACT", "relationship": "CONTRADICTS"},
                    ],
                    "research_support": "Recent underlying performance supports the frozen thesis.",
                    "research_counter": "Away transition threat is credible.",
                    "coverage": "MEDIUM",
                    "verdict": "PARTIALLY_CONFIRMED",
                }
            ],
        }

    def _stage3_payload(self):
        return {
            "run_id": "s3-run",
            "stage": "STAGE3",
            "authorized_by_user": True,
            "predecessor_stage1_run_id": "s1-run",
            "predecessor_stage2_run_id": "s2-run",
            "stage1_candidate_ids": ["m1"],
            "matches": [
                {
                    "fixture_id": "m1",
                    "preference": {"market": "1X2", "selection": "Home"},
                    "stage1_baseline": {"market": "1X2", "selection": "Home"},
                    "stage2_verdict": "PARTIALLY_CONFIRMED",
                    "grade": "A",
                    "decision": "BET",
                    "counter_severity": "MEDIUM",
                    "raw_confidence": 78,
                    "final_confidence": 71,
                    "divergence_state": "MIXED",
                    "execution_type": "NATIVE",
                    "change_driver": "NONE",
                    "rationale": "SXF structure remains sufficiently strong after research.",
                    "strongest_counterargument": "Away transition threat remains the main failure path.",
                    "prediction_at": "2026-10-07T18:00:00+03:00",
                    "decision_recorded_at": "2026-10-07T18:00:00+03:00",
                    "archive_intent": True,
                    "price_evidence": {
                        "fixture_id": "m1",
                        "origin": "SXF_NATIVE",
                        "price": 1.90,
                        "observed_at": "2026-10-07T18:00:00+03:00",
                    },
                }
            ],
        }

    def test_stage1_scans_full_universe_but_reports_only_candidates(self):
        result = validate_stage1(self._stage1_payload())
        self.assertTrue(result.valid, result.violations)

    def test_stage1_rejects_fail_open_missing_universe_resolution(self):
        payload = self._stage1_payload()
        payload["scope"].pop("universe_resolved")
        payload["screening_results"] = []
        payload["matches"] = []
        result = validate_stage1(payload)
        self.assertFalse(result.valid)
        self.assertIn("SXF-S1-002", {item.rule_id for item in result.violations})

    def test_stage1_rejects_partial_internal_scan(self):
        payload = self._stage1_payload()
        payload["screening_results"] = payload["screening_results"][:2]
        result = validate_stage1(payload)
        self.assertFalse(result.valid)
        self.assertIn("SXF-S1-002", {item.rule_id for item in result.violations})

    def test_stage1_accepts_normal_ou_25_spelling(self):
        payload = self._stage1_payload()
        payload["matches"][0]["preference"] = {"market": "O/U 2.5", "selection": "Under 2.5"}
        result = validate_stage1(payload)
        self.assertTrue(result.valid, result.violations)

    def test_stage1_rejects_non_native_market(self):
        payload = self._stage1_payload()
        payload["matches"][0]["preference"] = {"market": "Handicap", "selection": "Away +1.5"}
        result = validate_stage1(payload)
        self.assertFalse(result.valid)
        self.assertIn("SXF-S1-005", {item.rule_id for item in result.violations})

    def test_stage2_enforces_fact_budget_and_3_plus_1_checks(self):
        payload = self._stage2_payload()
        self.assertTrue(validate_stage2(payload).valid)
        payload["matches"][0]["facts"].extend(
            [
                {"claim": "x", "kind": "FACT", "relationship": "NEUTRAL"},
                {"claim": "y", "kind": "FACT", "relationship": "NEUTRAL"},
                {"claim": "z", "kind": "FACT", "relationship": "NEUTRAL"},
                {"claim": "q", "kind": "FACT", "relationship": "NEUTRAL"},
            ]
        )
        result = validate_stage2(payload)
        self.assertFalse(result.valid)
        self.assertIn("SXF-S2-004", {item.rule_id for item in result.violations})

    def test_stage2_rejects_missing_support_or_skipped_check(self):
        payload = self._stage2_payload()
        payload["matches"][0]["research_support"] = ""
        payload["matches"][0]["research_checks"]["performance_checked"] = False
        result = validate_stage2(payload)
        self.assertFalse(result.valid)
        self.assertIn("SXF-S2-005", {item.rule_id for item in result.violations})

    def test_stage3_valid_baseline_passes(self):
        result = validate_stage3(self._stage3_payload())
        self.assertTrue(result.valid, result.violations)

    def test_stage3_rejects_price_evidence_from_other_fixture(self):
        payload = self._stage3_payload()
        payload["matches"][0]["price_evidence"]["fixture_id"] = "m2"
        result = validate_stage3(payload)
        self.assertFalse(result.valid)
        self.assertIn("SXF-PRICE-006", {item.rule_id for item in result.violations})

    def test_stage3_grade_mapping_is_hard(self):
        payload = self._stage3_payload()
        payload["matches"][0]["grade"] = "B"
        result = validate_stage3(payload)
        self.assertFalse(result.valid)
        self.assertIn("SXF-S3-008", {item.rule_id for item in result.violations})

    def test_stage3_rejects_non_native_marked_native(self):
        payload = self._stage3_payload()
        row = payload["matches"][0]
        row["preference"] = {"market": "Handicap", "selection": "Home +1.5"}
        row["execution_type"] = "NATIVE"
        row["change_driver"] = "EXECUTION_OPTIMIZATION"
        row["price_evidence"] = user_supplied_price_evidence(
            fixture_id="m1",
            market="Handicap",
            selection="Home +1.5",
            price=1.72,
            received_at="2026-10-07T18:00:00+03:00",
        )
        result = validate_stage3(payload)
        self.assertFalse(result.valid)
        self.assertIn("SXF-S3-005", {item.rule_id for item in result.violations})

    def test_user_supplied_non_native_price_can_support_bet(self):
        price = user_supplied_price_evidence(
            fixture_id="m1",
            market="Handicap",
            selection="Frosinone +1.5",
            price=1.72,
            received_at="2026-10-07T19:15:00+03:00",
        )
        payload = self._stage3_payload()
        row = payload["matches"][0]
        row["preference"] = {"market": "Handicap", "selection": "Frosinone +1.5"}
        row["stage1_baseline"] = {"market": "1X2", "selection": "Frosinone"}
        row["execution_type"] = "PROTECTION"
        row["change_driver"] = "EXECUTION_OPTIMIZATION"
        row["price_evidence"] = price
        result = validate_stage3(payload)
        self.assertTrue(result.valid, result.violations)

    def test_user_supplied_price_requires_valid_time_when_explicit(self):
        with self.assertRaises(PredictorPolicyError):
            user_supplied_price_evidence(
                fixture_id="m1",
                market="Handicap",
                selection="Frosinone +1.5",
                price=1.72,
                observed_at="not-a-time",
            )

    def test_stage3_rejects_prediction_time_drift(self):
        payload = self._stage3_payload()
        payload["matches"][0]["prediction_at"] = "2026-10-07T17:59:00+03:00"
        result = validate_stage3(payload)
        self.assertFalse(result.valid)
        self.assertIn("SXF-S3-012", {item.rule_id for item in result.violations})

    def test_stage1_vs_stage3_comparison_detects_improvement_and_stage2_attribution(self):
        comparison = compare_stage_preferences(
            fixture_id="m1",
            match={"home": "Home", "away": "Away"},
            stage1_preference={"market": "1X2", "selection": "Away", "price": 3.20},
            stage3_preference={"market": "Double Chance", "selection": "Away X2", "price": 1.72},
            stage3_action="BET",
            final_score="1-1",
            change_driver="BOTH",
        )
        self.assertEqual(comparison.stage1.result, "LOSS")
        self.assertEqual(comparison.stage3.result, "WIN")
        self.assertEqual(comparison.transition, "IMPROVED")
        summary = summarize_comparisons([comparison])
        self.assertEqual(summary["transitions"]["IMPROVED"], 1)
        self.assertEqual(summary["stage1"]["hit_rate"], 0.0)
        self.assertEqual(summary["stage3"]["hit_rate"], 1.0)
        self.assertEqual(summary["stage2_influenced"]["matched_cases"], 1)
        self.assertEqual(summary["by_change_driver"]["BOTH"]["hit_rate_delta"], 1.0)


if __name__ == "__main__":
    unittest.main()
