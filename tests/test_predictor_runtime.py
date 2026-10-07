from __future__ import annotations

from copy import deepcopy
import unittest

from predictor_policy import PredictorPolicyError, PredictorRunState, validate_and_advance


class PredictorRuntimeTests(unittest.TestCase):
    def _stage1(self):
        return {
            "run_id": "s1-run",
            "stage": "STAGE1",
            "external_research_used": False,
            "scope": {"universe_resolved": True, "source_fixture_ids": ["m1"]},
            "screening_results": [
                {
                    "fixture_id": "m1",
                    "temporal_reviewed": True,
                    "selected": True,
                    "attention_signals": ["PRICE_CONFIRMATION"],
                }
            ],
            "matches": [
                {"fixture_id": "m1", "preference": {"market": "1X2", "selection": "Home"}}
            ],
        }

    def _stage2(self):
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
                        {"claim": "No material squad issue found.", "kind": "FACT", "relationship": "NEUTRAL"}
                    ],
                    "research_support": "Underlying performance remains supportive.",
                    "research_counter": "Draw path remains credible.",
                    "coverage": "MEDIUM",
                    "verdict": "PARTIALLY_CONFIRMED",
                }
            ],
        }

    def _stage3(self):
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
                    "counter_severity": "LIGHT",
                    "raw_confidence": 80,
                    "final_confidence": 77,
                    "divergence_state": "CONFIRMED",
                    "execution_type": "NATIVE",
                    "change_driver": "NONE",
                    "rationale": "SXF and research remain aligned.",
                    "strongest_counterargument": "Draw remains the main failure path.",
                    "prediction_at": "2026-10-07T19:00:00+03:00",
                    "decision_recorded_at": "2026-10-07T19:00:00+03:00",
                    "archive_intent": True,
                    "price_evidence": {
                        "fixture_id": "m1",
                        "origin": "SXF_NATIVE",
                        "price": 1.90,
                        "observed_at": "2026-10-07T19:00:00+03:00",
                    },
                }
            ],
        }

    def test_full_sequence_advances(self):
        state = PredictorRunState()
        state = validate_and_advance(state, self._stage1())
        self.assertEqual(state.stage1_run_id, "s1-run")
        state = validate_and_advance(state, self._stage2())
        self.assertEqual(state.stage2_run_id, "s2-run")
        state = validate_and_advance(state, self._stage3())
        self.assertEqual(state.stage3_run_id, "s3-run")

    def test_stage2_cannot_skip_stage1(self):
        with self.assertRaises(PredictorPolicyError):
            validate_and_advance(PredictorRunState(), self._stage2())

    def test_stage3_cannot_skip_stage2(self):
        state = validate_and_advance(PredictorRunState(), self._stage1())
        with self.assertRaises(PredictorPolicyError):
            validate_and_advance(state, self._stage3())

    def test_wrong_predecessor_is_rejected(self):
        state = validate_and_advance(PredictorRunState(), self._stage1())
        payload = self._stage2()
        payload["predecessor_stage1_run_id"] = "other-run"
        with self.assertRaises(PredictorPolicyError):
            validate_and_advance(state, payload)

    def test_duplicate_stage2_fixture_is_rejected_even_when_set_matches(self):
        state = validate_and_advance(PredictorRunState(), self._stage1())
        payload = self._stage2()
        duplicate = deepcopy(payload["matches"][0])
        duplicate["research_support"] = "Different duplicate content must still be rejected."
        payload["matches"].append(duplicate)
        with self.assertRaises(PredictorPolicyError) as caught:
            validate_and_advance(state, payload)
        self.assertIn("duplicate fixture IDs", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
