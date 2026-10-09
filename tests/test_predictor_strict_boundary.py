from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from predictor_orchestrator.archive_publisher import ArchivePublicationError, build_archive_case
from predictor_orchestrator.config import OrchestratorConfig
from predictor_orchestrator.service import OrchestratorError
from predictor_orchestrator.strict_service import StrictPredictorOrchestrator
from predictor_orchestrator.store import SQLiteOrchestratorStore
from tests.test_predictor_orchestrator import (
    FakeLLM,
    stage1_valid,
    stage2_valid,
    stage3_protected_valid,
)


class FakeArchivePublisher:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls = []

    def publish(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        if self.fail:
            raise RuntimeError("synthetic archive outage")
        row = kwargs["stage3_payload"]["matches"][0]
        return {
            "status": "RECORDED",
            "formal_cases": 1,
            "cases": [
                {
                    "fixture_id": row["fixture_id"],
                    "case_id": "20261008-m1-strict-boundary",
                    "archive_status": "RECORDED",
                    "archive_reference": "https://example.invalid/case",
                    "archive_commit": "a" * 40,
                    "checksum_summary": "b" * 64,
                    "error": None,
                    "diary_status": "RECORDED",
                    "diary_reference": "https://example.invalid/diary",
                }
            ],
            "diary_status": "RECORDED",
            "diary": {
                "status": "RECORDED",
                "reference": "https://example.invalid/diary",
                "commit": "c" * 40,
                "idempotent": False,
                "error": None,
            },
        }


class StrictPredictorBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "predictor.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def config(self):
        return OrchestratorConfig(
            api_key="test-key",
            api_base="https://api.openai.com/v1",
            model="fake-predictor-model",
            state_db_path=self.db_path,
            service_secret="test-secret",
            max_attempts=3,
            request_timeout_seconds=30,
            stage2_web_search=False,
            max_output_tokens=4000,
        )

    @staticmethod
    def _selection_feature(now: datetime, *, first_odds: float = 2.10, last_odds: float = 1.91, first_share: float = 42.0, last_share: float = 58.0, first_amount: float = 1200.0, last_amount: float = 3600.0):
        first_at = (now - timedelta(hours=3)).isoformat()
        h1_at = (now - timedelta(hours=1)).isoformat()
        last_at = now.isoformat()
        first = {"observed_at": first_at, "odds": first_odds, "share": first_share, "amount": first_amount, "volume": 5000.0}
        h1 = {"observed_at": h1_at, "odds": 1.98, "share": 53.0, "amount": 2800.0, "volume": 6900.0}
        last = {"observed_at": last_at, "odds": last_odds, "share": last_share, "amount": last_amount, "volume": 7800.0}
        return {
            "history_count": 8,
            "first": first,
            "last": last,
            "odds_range": [last_odds, first_odds],
            "reversal_segments": 1,
            "latest_age_seconds": 30,
            "h24": None,
            "h12": None,
            "h6": None,
            "h3": first,
            "h1": h1,
            "m30": None,
            "m15": None,
        }

    @classmethod
    def stage1_context(cls):
        now = datetime.now(timezone.utc)
        kickoff1 = (now + timedelta(days=1)).isoformat()
        kickoff2 = (now + timedelta(days=1, hours=1)).isoformat()
        home = cls._selection_feature(now)
        draw = cls._selection_feature(now, first_odds=3.50, last_odds=3.65, first_share=28.0, last_share=24.0, first_amount=800.0, last_amount=900.0)
        away = cls._selection_feature(now, first_odds=3.80, last_odds=4.10, first_share=30.0, last_share=18.0, first_amount=900.0, last_amount=700.0)
        over = cls._selection_feature(now, first_odds=1.95, last_odds=1.88, first_share=51.0, last_share=55.0, first_amount=1000.0, last_amount=1700.0)
        under = cls._selection_feature(now, first_odds=1.90, last_odds=1.98, first_share=49.0, last_share=45.0, first_amount=950.0, last_amount=1200.0)
        return {
            "source": "SXF_PRODUCTION_READ_ONLY",
            "source_fixture_ids": ["m1", "m2"],
            "fixtures": [
                {
                    "fixture_id": "m1",
                    "home": "Home",
                    "away": "Away",
                    "league": "League",
                    "kickoff_utc": kickoff1,
                    "markets": {
                        "1X2": {"Home": home, "Draw": draw, "Away": away},
                        "OU2.5": {"Over 2.5": over, "Under 2.5": under},
                    },
                },
                {
                    "fixture_id": "m2",
                    "home": "Other",
                    "away": "Guest",
                    "league": "League",
                    "kickoff_utc": kickoff2,
                    "markets": {},
                },
            ],
            "price_evidence": [
                {
                    "fixture_id": "m1",
                    "origin": "SXF_NATIVE",
                    "source": "SXF",
                    "market": "1X2",
                    "selection": "Home",
                    "price": 1.91,
                    "observed_at": now.isoformat(),
                    "status": "OBSERVED",
                }
            ],
        }

    def make(self, publisher):
        cfg = self.config()
        store = SQLiteOrchestratorStore(cfg.state_db_path)
        return StrictPredictorOrchestrator(
            config=cfg,
            store=store,
            llm=FakeLLM([]),
            archive_publisher=publisher,
        )

    def start(self, orch):
        wf = orch.create_workflow(
            {
                "date": "2026-10-08",
                "window_tr": ["18:00", "24:00"],
                "timezone": "Europe/Istanbul",
                "future_only": False,
            }
        )
        orch.store.save_trusted_context(wf.workflow_id, "STAGE1", self.stage1_context())
        return wf.workflow_id

    def complete_to_stage2(self, orch, workflow_id):
        stage1 = orch.submit_generated_stage(
            workflow_id=workflow_id,
            stage="STAGE1",
            generated=stage1_valid(),
            agent_model="chatgpt-test",
        )
        self.assertTrue(stage1["formal_publication"])
        self.assertEqual(stage1["publication_receipt"]["status"], "ACCEPTED_PERSISTED")
        self.assertEqual(len(stage1["publication_receipt"]["payload_sha256"]), 64)
        self.assertEqual(stage1["report"], orch.store.get_stage_output(workflow_id, "STAGE1")["rendered"])

        stage2 = orch.submit_generated_stage(
            workflow_id=workflow_id,
            stage="STAGE2",
            generated=stage2_valid(),
            user_authorized=True,
            agent_model="chatgpt-test",
        )
        self.assertTrue(stage2["formal_publication"])
        self.assertEqual(stage2["publication_receipt"]["status"], "ACCEPTED_PERSISTED")
        self.assertIn("EKSİK / KADRO ETKİ DEĞERLENDİRMESİ", stage2["report"]["text"])
        self.assertIn("SAYISAL BAĞLAM", stage2["report"]["text"])
        self.assertIsNotNone(stage2["report"]["rows"][0]["frozen_stage1_evidence"])

    def test_user_visible_result_is_reloaded_from_durable_accepted_stage(self):
        orch = self.make(None)
        workflow_id = self.start(orch)
        result = orch.submit_generated_stage(
            workflow_id=workflow_id,
            stage="STAGE1",
            generated=stage1_valid(),
            agent_model="chatgpt-test",
        )
        accepted = orch.store.get_stage_output(workflow_id, "STAGE1")
        self.assertIsNotNone(accepted)
        self.assertTrue(result["validated"])
        self.assertTrue(result["formal_publication"])
        self.assertEqual(result["report"], accepted["rendered"])
        self.assertEqual(result["publication_receipt"]["stage_run_id"], accepted["stage_run_id"])
        self.assertEqual(result["publication_receipt"]["accepted_at"], accepted["accepted_at"])
        self.assertEqual(len(result["publication_receipt"]["receipt_sha256"]), 64)
        evidence = accepted["payload"]["matches"][0]["sxf_evidence"]["selected_selection"]
        self.assertEqual(evidence["first"]["odds"], 2.10)
        self.assertEqual(evidence["last"]["odds"], 1.91)
        self.assertEqual(evidence["open_to_latest"]["amount_delta"], 2400.0)
        self.assertEqual(evidence["open_to_latest"]["share_delta_pp"], 16.0)
        self.assertEqual(evidence["open_to_latest"]["amount_velocity_per_hour"], 800.0)
        self.assertIn("KULLANILAN HAM SXF VERİSİ", result["report"]["text"])
        self.assertIn("AÇILIŞ → SON DEĞİŞİM", result["report"]["text"])
        self.assertIn("NATIVE CROSS-MARKET SON DURUM", result["report"]["text"])

    def test_stage1_fails_closed_without_trusted_numeric_evidence(self):
        orch = self.make(None)
        workflow_id = self.start(orch)
        trusted = orch.store.get_trusted_context(workflow_id, "STAGE1")
        broken = deepcopy(trusted["context"])
        broken["fixtures"][0]["markets"] = {}
        orch.store.save_trusted_context(workflow_id, "STAGE1", broken)
        with self.assertRaises(OrchestratorError):
            orch.submit_generated_stage(
                workflow_id=workflow_id,
                stage="STAGE1",
                generated=stage1_valid(),
                agent_model="chatgpt-test",
            )

    def test_stage3_bet_automatically_records_archive_and_diary_receipts(self):
        publisher = FakeArchivePublisher()
        orch = self.make(publisher)
        workflow_id = self.start(orch)
        self.complete_to_stage2(orch, workflow_id)
        orch.add_user_price(
            workflow_id=workflow_id,
            fixture_id="m1",
            market="Double Chance",
            selection="Home 1X",
            price=1.55,
            observed_at="2026-10-08T17:10:00+00:00",
        )
        result = orch.submit_generated_stage(
            workflow_id=workflow_id,
            stage="STAGE3",
            generated=stage3_protected_valid(),
            user_authorized=True,
            agent_model="chatgpt-test",
        )
        self.assertTrue(result["formal_publication"])
        self.assertEqual(result["report"]["rows"][0]["decision"], "BET")
        self.assertEqual(result["archive"]["status"], "RECORDED")
        self.assertEqual(result["archive"]["diary_status"], "RECORDED")
        rows = orch.lifecycle_store.list_for_stage(workflow_id, result["stage_run_id"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["archive_status"], "RECORDED")
        self.assertEqual(rows[0]["diary_status"], "RECORDED")
        self.assertEqual(len(publisher.calls), 1)

    def test_archive_outage_is_pending_and_cannot_erase_accepted_stage3(self):
        publisher = FakeArchivePublisher(fail=True)
        orch = self.make(publisher)
        workflow_id = self.start(orch)
        self.complete_to_stage2(orch, workflow_id)
        orch.add_user_price(
            workflow_id=workflow_id,
            fixture_id="m1",
            market="Double Chance",
            selection="Home 1X",
            price=1.55,
            observed_at="2026-10-08T17:10:00+00:00",
        )
        result = orch.submit_generated_stage(
            workflow_id=workflow_id,
            stage="STAGE3",
            generated=stage3_protected_valid(),
            user_authorized=True,
            agent_model="chatgpt-test",
        )
        self.assertTrue(result["validated"])
        self.assertTrue(result["formal_publication"])
        self.assertEqual(result["archive"]["status"], "ARCHIVE_PENDING")
        self.assertEqual(result["archive"]["diary_status"], "DIARY_PENDING")
        self.assertIsNotNone(orch.store.get_stage_output(workflow_id, "STAGE3"))
        current = orch.get_workflow(workflow_id)
        self.assertEqual(current.state.stage3_run_id, result["stage_run_id"])

    def test_archive_case_does_not_fabricate_stage2_evidence_timestamps(self):
        stage1_payload = {
            "matches": [
                {
                    "fixture_id": "abc123def456",
                    "preference": {"market": "1X2", "selection": "Home", "price": 1.9},
                    "rationale": "Native SXF support.",
                }
            ]
        }
        stage2_payload = {
            "matches": [
                {
                    "fixture_id": "abc123def456",
                    "facts": [
                        {
                            "kind": "INFERENCE",
                            "relationship": "CONTRADICTS",
                            "claim": "Untimestamped inference stays separate.",
                            "source": None,
                            "observed_at": None,
                        }
                    ],
                    "verdict": "PARTIALLY_CONFIRMED",
                }
            ]
        }
        stage3_row = {
            "fixture_id": "abc123def456",
            "preference": {"market": "1X2", "selection": "Home", "price": 1.9},
            "stage1_baseline": {"market": "1X2", "selection": "Home"},
            "stage2_verdict": "PARTIALLY_CONFIRMED",
            "grade": "B",
            "decision": "WATCH",
            "counter_severity": "MEDIUM",
            "raw_confidence": 70,
            "final_confidence": 63,
            "divergence_state": "MIXED",
            "execution_type": "NATIVE",
            "rationale": "Formal rationale.",
            "strongest_counterargument": "Formal counterargument.",
            "change_driver": "NONE",
            "prediction_at": "2026-10-08T17:15:00+00:00",
            "price_evidence": {
                "fixture_id": "abc123def456",
                "origin": "SXF_NATIVE",
                "source": "SXF",
                "market": "1X2",
                "selection": "Home",
                "price": 1.9,
                "observed_at": "2026-10-08T17:00:00+00:00",
            },
        }
        context = {
            "fixtures": [
                {
                    "fixture_id": "abc123def456",
                    "home": "Home",
                    "away": "Away",
                    "league": "League",
                    "kickoff_utc": "2026-10-08T18:00:00+00:00",
                }
            ],
            "price_evidence": [stage3_row["price_evidence"]],
        }
        case = build_archive_case(
            workflow_scope={"timezone": "Europe/Istanbul"},
            stage1_payload=stage1_payload,
            stage2_payload=stage2_payload,
            stage3_row=stage3_row,
            stage1_context=context,
            source_commit="d" * 40,
        )
        self.assertEqual(len(case["evidence"]), 1)
        self.assertEqual(case["evidence"][0]["source"], "SmartXFlow accepted Stage 1")
        self.assertEqual(case["prediction"]["stage2_inferences"][0]["kind"], "INFERENCE")
        self.assertNotIn("observed_at", case["prediction"]["stage2_inferences"][0])

    def test_bet_archive_case_fails_closed_without_real_price(self):
        with self.assertRaises(ArchivePublicationError):
            build_archive_case(
                workflow_scope={},
                stage1_payload={"matches": []},
                stage2_payload={"matches": []},
                stage3_row={
                    "fixture_id": "abc123def456",
                    "preference": {"market": "Double Chance", "selection": "Home 1X"},
                    "decision": "BET",
                    "prediction_at": "2026-10-08T17:15:00+00:00",
                    "rationale": "Rationale",
                    "strongest_counterargument": "Counter",
                },
                stage1_context={
                    "fixtures": [
                        {
                            "fixture_id": "abc123def456",
                            "home": "Home",
                            "away": "Away",
                            "league": "League",
                            "kickoff_utc": "2026-10-08T18:00:00+00:00",
                        }
                    ],
                    "price_evidence": [],
                },
                source_commit="d" * 40,
            )


if __name__ == "__main__":
    unittest.main()
