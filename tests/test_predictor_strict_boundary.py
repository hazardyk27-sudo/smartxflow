from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from predictor_orchestrator.archive_publisher import ArchivePublicationError, build_archive_case
from predictor_orchestrator.config import OrchestratorConfig
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
    def stage1_context():
        return {
            "source": "SXF_PRODUCTION_READ_ONLY",
            "source_fixture_ids": ["m1", "m2"],
            "fixtures": [
                {
                    "fixture_id": "m1",
                    "home": "Home",
                    "away": "Away",
                    "league": "League",
                    "kickoff_utc": "2026-10-08T18:00:00+00:00",
                    "markets": {},
                },
                {
                    "fixture_id": "m2",
                    "home": "Other",
                    "away": "Guest",
                    "league": "League",
                    "kickoff_utc": "2026-10-08T19:00:00+00:00",
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
                    "observed_at": "2026-10-08T17:00:00+00:00",
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
