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
            "research_cutoff_at": "2026-10-07T16:00:00+00:00",
            "matches": [
                {
                    "fixture_id": "m1",
                    "fixture_kickoff_utc": "2026-10-07T19:00:00+00:00",
                    "frozen_stage1_preference": {"market": "1X2", "selection": "Home"},
                    "research_checks": {
                        "squad": {"status": "VERIFIED", "fact_ids": ["f1"], "note": "Güncel kadro kaynağı kontrol edildi."},
                        "performance": {"status": "VERIFIED", "fact_ids": ["f2"], "note": "Yakın dönem performansı kontrol edildi."},
                        "counter": {"status": "VERIFIED", "fact_ids": ["f3"], "note": "En güçlü karşı senaryo ayrı araştırıldı."},
                    },
                    "facts": [
                        {
                            "fact_id": "f1",
                            "claim": "Ana kadro çekirdeğinde material bir eksik görünmüyor.",
                            "kind": "FACT",
                            "category": "SQUAD",
                            "materiality": "MATERIAL",
                            "relationship": "NEUTRAL",
                            "source": "https://www.uefa.com/news/test-squad",
                            "source_tier": "A",
                            "observed_at": "2026-10-07T15:00:00+00:00",
                            "evidence_at": "2026-10-07T14:00:00+00:00",
                            "derived_from_fact_ids": [],
                            "corroborating_sources": [],
                        },
                        {
                            "fact_id": "f2",
                            "claim": "Yakın dönem şut ve üretim profili ev sahibini destekliyor.",
                            "kind": "FACT",
                            "category": "PERFORMANCE",
                            "materiality": "MATERIAL",
                            "relationship": "SUPPORTS",
                            "source": "https://www.fotmob.com/matches/test",
                            "source_tier": "C",
                            "observed_at": "2026-10-07T15:05:00+00:00",
                            "evidence_at": "2026-10-05T20:00:00+00:00",
                            "derived_from_fact_ids": [],
                            "corroborating_sources": [],
                        },
                        {
                            "fact_id": "f3",
                            "claim": "Rakibin geçiş tehdidi ve son deplasman performansı beraberlik/away yolunu açık tutuyor.",
                            "kind": "FACT",
                            "category": "CONTEXT",
                            "materiality": "MATERIAL",
                            "relationship": "CONTRADICTS",
                            "source": "https://www.reuters.com/sports/soccer/test-counter",
                            "source_tier": "B",
                            "observed_at": "2026-10-07T15:10:00+00:00",
                            "evidence_at": "2026-10-07T12:00:00+00:00",
                            "derived_from_fact_ids": [],
                            "corroborating_sources": [],
                        },
                    ],
                    "support_fact_ids": ["f2"],
                    "counter_fact_ids": ["f3"],
                    "research_support": "Yakın dönem üretim kalitesi frozen Stage 1 yönünü destekliyor.",
                    "research_counter": "Rakibin geçiş tehdidi ve deplasman performansı ana karşı tez.",
                    "research_synthesis": "Dış araştırma Stage 1 yönünü destekliyor ancak rakibin geçiş tehdidi nedeniyle tam doğrulama vermiyor.",
                    "important_absence": None,
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

    def test_stage2_enforces_fact_budget_and_evidence_backed_3_plus_1_checks(self):
        payload = self._stage2_payload()
        self.assertTrue(validate_stage2(payload).valid, validate_stage2(payload).violations)
        payload["matches"][0]["facts"].extend([
            {**payload["matches"][0]["facts"][0], "fact_id": "f4"},
            {**payload["matches"][0]["facts"][0], "fact_id": "f5"},
            {**payload["matches"][0]["facts"][0], "fact_id": "f6"},
            {**payload["matches"][0]["facts"][0], "fact_id": "f7"},
        ])
        result = validate_stage2(payload)
        self.assertFalse(result.valid)
        self.assertIn("SXF-S2-004", {item.rule_id for item in result.violations})

    def test_stage2_rejects_boolean_research_check_bypass(self):
        payload = self._stage2_payload()
        payload["matches"][0]["research_checks"] = {
            "squad_checked": True,
            "performance_checked": True,
            "counter_checked": True,
            "coverage_classified": True,
        }
        result = validate_stage2(payload)
        self.assertFalse(result.valid)
        self.assertIn("SXF-S2-010", {item.rule_id for item in result.violations})

    def test_stage2_rejects_fact_without_source_or_timestamp(self):
        payload = self._stage2_payload()
        fact = payload["matches"][0]["facts"][1]
        fact["source"] = None
        fact["source_tier"] = None
        fact["observed_at"] = None
        fact["evidence_at"] = None
        result = validate_stage2(payload)
        self.assertFalse(result.valid)
        ids = {item.rule_id for item in result.violations}
        self.assertIn("SXF-S2-009", ids)
        self.assertIn("SXF-S2-012", ids)

    def test_stage2_rejects_false_source_tier(self):
        payload = self._stage2_payload()
        payload["matches"][0]["facts"][1]["source_tier"] = "B"
        result = validate_stage2(payload)
        self.assertFalse(result.valid)
        self.assertIn("SXF-S2-011", {item.rule_id for item in result.violations})

    def test_stage2_rejects_stale_squad_news(self):
        payload = self._stage2_payload()
        payload["matches"][0]["facts"][0]["evidence_at"] = "2026-09-01T12:00:00+00:00"
        result = validate_stage2(payload)
        self.assertFalse(result.valid)
        self.assertIn("SXF-S2-012", {item.rule_id for item in result.violations})

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
