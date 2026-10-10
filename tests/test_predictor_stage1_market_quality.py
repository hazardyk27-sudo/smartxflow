from __future__ import annotations

import unittest

from predictor_orchestrator.stage1_evidence import build_stage1_evidence
from predictor_policy.stage1_quality import enforce_stage1_market_quality
from predictor_policy.validator import PredictorPolicyError


class Stage1MarketQualityTests(unittest.TestCase):
    @staticmethod
    def _payload(*, quality, signals=None):
        return {
            "screening_results": [
                {
                    "fixture_id": "m1",
                    "selected": True,
                    "temporal_reviewed": True,
                    "attention_signals": signals or ["PRICE_CONFIRMATION"],
                }
            ],
            "matches": [
                {
                    "fixture_id": "m1",
                    "preference": {"market": "1X2", "selection": "Home", "price": 2.0},
                    "sxf_evidence": {"market_quality": quality},
                }
            ],
        }

    def test_low_liquidity_is_not_automatic_drop(self):
        payload = self._payload(
            quality={
                "liquidity_band": "LOW",
                "evidence_weight": "LOW",
                "share_only_risk": False,
                "underdog_status": "NOT_UNDERDOG",
            }
        )
        enforce_stage1_market_quality(payload)

    def test_share_only_candidate_is_rejected(self):
        payload = self._payload(
            quality={
                "liquidity_band": "LIMITED",
                "evidence_weight": "LOW",
                "share_only_risk": True,
                "underdog_status": "NOT_UNDERDOG",
            },
            signals=["PERSISTENCE", "SATURATION"],
        )
        with self.assertRaises(PredictorPolicyError) as ctx:
            enforce_stage1_market_quality(payload)
        self.assertIn("SXF-S1-012", str(ctx.exception))

    def test_high_odds_low_money_underdog_cannot_be_frozen_preference(self):
        payload = self._payload(
            quality={
                "liquidity_band": "LOW",
                "evidence_weight": "LOW",
                "share_only_risk": False,
                "underdog_status": "LOW_CONFIDENCE_MARKET_MOVE",
            },
            signals=["PRICE_CONFIRMATION", "PERSISTENCE"],
        )
        with self.assertRaises(PredictorPolicyError) as ctx:
            enforce_stage1_market_quality(payload)
        self.assertIn("SXF-S1-013", str(ctx.exception))

    def test_qualified_underdog_is_allowed(self):
        payload = self._payload(
            quality={
                "liquidity_band": "NORMAL",
                "evidence_weight": "NORMAL",
                "share_only_risk": False,
                "underdog_status": "QUALIFIED",
            },
            signals=["PRICE_CONFIRMATION", "PERSISTENCE"],
        )
        enforce_stage1_market_quality(payload)

    def test_server_owned_evidence_derives_liquidity_and_underdog_quality(self):
        context = {
            "fixtures": [
                {
                    "fixture_id": "m1",
                    "markets": {
                        "1X2": {
                            "Away": {
                                "history_count": 8,
                                "first": {
                                    "observed_at": "2026-10-10T00:00:00+00:00",
                                    "odds": 4.0,
                                    "share": 35.0,
                                    "amount": 1200.0,
                                    "volume": 5000.0,
                                },
                                "h6": {
                                    "observed_at": "2026-10-10T01:00:00+00:00",
                                    "odds": 3.9,
                                    "share": 45.0,
                                    "amount": 3000.0,
                                    "volume": 8000.0,
                                },
                                "h3": {
                                    "observed_at": "2026-10-10T02:00:00+00:00",
                                    "odds": 3.75,
                                    "share": 55.0,
                                    "amount": 5200.0,
                                    "volume": 11000.0,
                                },
                                "last": {
                                    "observed_at": "2026-10-10T03:00:00+00:00",
                                    "odds": 3.55,
                                    "share": 60.0,
                                    "amount": 7000.0,
                                    "volume": 15000.0,
                                },
                                "odds_range": [3.55, 4.0],
                                "reversal_segments": 1,
                                "latest_age_seconds": 0,
                            }
                        }
                    },
                }
            ]
        }
        evidence = build_stage1_evidence(context, fixture_id="m1", market="1X2", selection="Away")
        self.assertIsNotNone(evidence)
        quality = evidence["market_quality"]
        self.assertEqual(quality["liquidity_band"], "NORMAL")
        self.assertEqual(quality["underdog_status"], "QUALIFIED")
        self.assertTrue(quality["persistent_price_move"])


if __name__ == "__main__":
    unittest.main()
