from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from predictor_orchestrator.config import OrchestratorConfig
from predictor_orchestrator.strict_service import StrictPredictorOrchestrator
from predictor_orchestrator.store import SQLiteOrchestratorStore
from tests.test_predictor_orchestrator import FakeLLM, stage1_valid, stage2_valid
from tests.test_predictor_strict_boundary import FakeArchivePublisher


class StrictStage3NativePriceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "predictor.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def make(self):
        cfg = OrchestratorConfig(
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
        publisher = FakeArchivePublisher()
        orch = StrictPredictorOrchestrator(
            config=cfg,
            store=SQLiteOrchestratorStore(cfg.state_db_path),
            llm=FakeLLM([]),
            archive_publisher=publisher,
        )
        return orch, publisher

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

    @staticmethod
    def native_stage3_bet():
        return {
            "matches": [
                {
                    "fixture_id": "m1",
                    "preference": {"market": "1X2", "selection": "Home", "price": 99.0},
                    "grade": "A",
                    "counter_severity": "LIGHT",
                    "raw_confidence": 82,
                    "divergence_state": "CONFIRMED",
                    "execution_type": "NATIVE",
                    "material_reversal_explained": False,
                    "material_reversal_explanation": None,
                    "rationale": "Stage 1 fiyat ve para yönü araştırma sonrası korunuyor.",
                    "strongest_counterargument": "Rakibin geçiş tehdidi tamamen ortadan kalkmış değil.",
                    "change_driver": "NONE",
                }
            ]
        }

    def test_external_stage3_native_bet_uses_server_owned_stage1_price(self):
        orch, publisher = self.make()
        workflow = orch.create_workflow(
            {
                "date": "2026-10-08",
                "window_tr": ["18:00", "24:00"],
                "timezone": "Europe/Istanbul",
                "future_only": False,
            }
        )
        workflow_id = workflow.workflow_id
        orch.store.save_trusted_context(workflow_id, "STAGE1", self.stage1_context())

        orch.submit_generated_stage(
            workflow_id=workflow_id,
            stage="STAGE1",
            generated=stage1_valid(),
            agent_model="chatgpt-test",
        )
        orch.submit_generated_stage(
            workflow_id=workflow_id,
            stage="STAGE2",
            generated=stage2_valid(),
            user_authorized=True,
            agent_model="chatgpt-test",
        )
        result = orch.submit_generated_stage(
            workflow_id=workflow_id,
            stage="STAGE3",
            generated=self.native_stage3_bet(),
            user_authorized=True,
            agent_model="chatgpt-test",
        )

        accepted = orch.store.get_stage_output(workflow_id, "STAGE3")
        self.assertIsNotNone(accepted)
        row = accepted["payload"]["matches"][0]
        self.assertEqual(row["decision"], "BET")
        self.assertEqual(row["preference"]["price"], 1.91)
        self.assertEqual(row["price_evidence"]["fixture_id"], "m1")
        self.assertEqual(row["price_evidence"]["origin"], "SXF_NATIVE")
        self.assertEqual(row["price_evidence"]["price"], 1.91)
        self.assertEqual(result["report"]["rows"][0]["preference"]["price"], 1.91)
        self.assertEqual(result["archive"]["status"], "RECORDED")
        self.assertEqual(len(publisher.calls), 1)
        archived_row = publisher.calls[0]["stage3_payload"]["matches"][0]
        self.assertEqual(archived_row["preference"]["price"], 1.91)
        self.assertEqual(archived_row["price_evidence"]["origin"], "SXF_NATIVE")


if __name__ == "__main__":
    unittest.main()
