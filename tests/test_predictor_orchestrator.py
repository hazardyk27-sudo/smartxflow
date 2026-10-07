from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest

from predictor_orchestrator.config import OrchestratorConfig
from predictor_orchestrator.server import create_app
from predictor_orchestrator.service import (
    PredictorOrchestrator,
    UserAuthorizationRequired,
    ValidationExhausted,
)
from predictor_orchestrator.store import SQLiteOrchestratorStore


class FakeLLM:
    model = "fake-predictor-model"

    def __init__(self, outputs=None):
        self.outputs = list(outputs or [])
        self.calls = []

    def add(self, *outputs):
        self.outputs.extend(deepcopy(list(outputs)))

    def generate(self, *, stage, system_prompt, user_prompt, schema):
        self.calls.append(
            {
                "stage": stage,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "schema": schema,
            }
        )
        if not self.outputs:
            raise AssertionError(f"FakeLLM has no output queued for {stage}")
        return deepcopy(self.outputs.pop(0)), f"resp_{len(self.calls)}"


def stage1_valid():
    return {
        "screening_results": [
            {
                "fixture_id": "m1",
                "temporal_reviewed": True,
                "selected": True,
                "attention_signals": ["PRICE_CONFIRMATION"],
                "attention_explanation": None,
            },
            {
                "fixture_id": "m2",
                "temporal_reviewed": True,
                "selected": False,
                "attention_signals": [],
                "attention_explanation": None,
            },
        ],
        "matches": [
            {
                "fixture_id": "m1",
                "preference": {"market": "1X2", "selection": "Home", "price": 99.0},
                "rationale": "SXF para ve fiyat tepkisi aynı yönde güçleniyor.",
                "strongest_counterargument": "Geç bölümde fiyat direnci oluşabilir.",
            }
        ],
    }


def stage1_invalid_partial_scan():
    value = stage1_valid()
    value["screening_results"] = value["screening_results"][:1]
    return value


def stage2_valid():
    return {
        "matches": [
            {
                "fixture_id": "m1",
                "research_checks": {
                    "squad_checked": True,
                    "performance_checked": True,
                    "counter_checked": True,
                    "coverage_classified": True,
                },
                "facts": [
                    {
                        "kind": "FACT",
                        "relationship": "SUPPORTS",
                        "claim": "Ev sahibi ana kadro sürekliliğini koruyor.",
                        "source": "official.example",
                        "source_tier": "A",
                        "observed_at": "2026-10-07T18:00:00+03:00",
                    },
                    {
                        "kind": "INFERENCE",
                        "relationship": "CONTRADICTS",
                        "claim": "Rakibin geçiş tehdidi beraberlik yolunu açık tutuyor.",
                        "source": None,
                        "source_tier": None,
                        "observed_at": None,
                    },
                ],
                "research_support": "Kadro sürekliliği Stage 1 yönünü destekliyor.",
                "research_counter": "Rakibin geçiş tehdidi en güçlü karşı tez.",
                "important_absence": None,
                "coverage": "MEDIUM",
                "verdict": "PARTIALLY_CONFIRMED",
            }
        ]
    }


def stage3_native_valid():
    return {
        "matches": [
            {
                "fixture_id": "m1",
                "preference": {"market": "1X2", "selection": "Home", "price": 77.0},
                "grade": "B",
                "counter_severity": "MEDIUM",
                "raw_confidence": 78,
                "divergence_state": "MIXED",
                "execution_type": "NATIVE",
                "material_reversal_explained": False,
                "material_reversal_explanation": None,
                "rationale": "Stage 1 yapısı korunuyor fakat karşı kanıt nedeniyle izleme seviyesi uygun.",
                "strongest_counterargument": "Rakibin geçiş tehdidi.",
                "change_driver": "NONE",
            }
        ]
    }


def stage3_protected_valid():
    return {
        "matches": [
            {
                "fixture_id": "m1",
                "preference": {"market": "Double Chance", "selection": "Home 1X", "price": 99.0},
                "grade": "A",
                "counter_severity": "LIGHT",
                "raw_confidence": 80,
                "divergence_state": "CONFIRMED",
                "execution_type": "PROTECTION",
                "material_reversal_explained": False,
                "material_reversal_explanation": None,
                "rationale": "Aynı yön tezini daha düşük varyansla ifade eden korunmuş market.",
                "strongest_counterargument": "Koruma fiyatı fazla kısalabilir.",
                "change_driver": "EXECUTION_OPTIMIZATION",
            }
        ]
    }


class PredictorOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "predictor.sqlite3")

    def tearDown(self):
        self.tmp.cleanup()

    def config(self, *, attempts=3):
        return OrchestratorConfig(
            api_key="test-key",
            api_base="https://api.openai.com/v1",
            model="fake-predictor-model",
            state_db_path=self.db_path,
            service_secret="test-secret",
            max_attempts=attempts,
            request_timeout_seconds=30,
            stage2_web_search=False,
            max_output_tokens=4000,
        )

    def make(self, outputs, *, attempts=3):
        cfg = self.config(attempts=attempts)
        store = SQLiteOrchestratorStore(cfg.state_db_path)
        llm = FakeLLM(outputs)
        return PredictorOrchestrator(config=cfg, store=store, llm=llm), llm

    @staticmethod
    def stage1_context():
        return {
            "source_fixture_ids": ["m1", "m2"],
            "fixtures": [
                {"fixture_id": "m1", "home": "Home", "away": "Away", "sxf_history": [{"t": 1}, {"t": 2}]},
                {"fixture_id": "m2", "home": "Other", "away": "Guest", "sxf_history": [{"t": 1}, {"t": 2}]},
            ],
            "price_evidence": [
                {
                    "origin": "SXF_NATIVE",
                    "source": "SXF",
                    "market": "1X2",
                    "selection": "Home",
                    "price": 1.91,
                    "observed_at": "2026-10-07T17:55:00+03:00",
                }
            ],
        }

    def complete_stage1(self, orch):
        wf = orch.create_workflow({"date": "2026-10-07", "window": ["18:00", "24:00"]})
        orch.run_stage(workflow_id=wf.workflow_id, stage="STAGE1", trusted_context=self.stage1_context())
        return wf.workflow_id

    def test_invalid_output_is_repaired_before_publication(self):
        orch, _ = self.make([stage1_invalid_partial_scan(), stage1_valid()])
        wf = orch.create_workflow({"window": ["18:00", "24:00"]})
        result = orch.run_stage(workflow_id=wf.workflow_id, stage="STAGE1", trusted_context=self.stage1_context())
        self.assertTrue(result["validated"])
        self.assertEqual(result["attempts"], 2)
        self.assertEqual([row["fixture_id"] for row in result["report"]["rows"]], ["m1"])
        attempts = orch.store.list_attempts(wf.workflow_id, "STAGE1")
        self.assertEqual(len(attempts), 2)
        self.assertFalse(attempts[0]["accepted"])
        self.assertTrue(attempts[1]["accepted"])
        self.assertNotIn("raw_payload", attempts[0])

    def test_validation_exhaustion_does_not_advance_state(self):
        orch, _ = self.make([stage1_invalid_partial_scan(), stage1_invalid_partial_scan()], attempts=2)
        wf = orch.create_workflow({"window": ["18:00", "24:00"]})
        with self.assertRaises(ValidationExhausted):
            orch.run_stage(workflow_id=wf.workflow_id, stage="STAGE1", trusted_context=self.stage1_context())
        current = orch.get_workflow(wf.workflow_id)
        self.assertIsNone(current.state.stage1_run_id)
        self.assertIsNone(orch.store.get_stage_output(wf.workflow_id, "STAGE1"))

    def test_exhausted_stage_can_be_retried_without_audit_collision(self):
        orch, llm = self.make([stage1_invalid_partial_scan(), stage1_invalid_partial_scan()], attempts=2)
        wf = orch.create_workflow({"window": ["18:00", "24:00"]})
        with self.assertRaises(ValidationExhausted):
            orch.run_stage(workflow_id=wf.workflow_id, stage="STAGE1", trusted_context=self.stage1_context())
        llm.add(stage1_valid())
        result = orch.run_stage(workflow_id=wf.workflow_id, stage="STAGE1", trusted_context=self.stage1_context())
        self.assertTrue(result["validated"])
        attempts = orch.store.list_attempts(wf.workflow_id, "STAGE1")
        self.assertEqual([row["attempt_no"] for row in attempts], [1, 2, 3])
        self.assertTrue(attempts[-1]["accepted"])

    def test_model_price_is_discarded_and_trusted_native_price_wins(self):
        orch, _ = self.make([stage1_valid()])
        workflow_id = self.complete_stage1(orch)
        stored = orch.store.get_stage_output(workflow_id, "STAGE1")
        self.assertEqual(stored["payload"]["matches"][0]["preference"]["price"], 1.91)
        self.assertNotEqual(stored["payload"]["matches"][0]["preference"]["price"], 99.0)

    def test_stage2_requires_user_authorization_even_for_direct_service_call(self):
        orch, llm = self.make([stage1_valid()])
        workflow_id = self.complete_stage1(orch)
        llm.add(stage2_valid())
        with self.assertRaises(UserAuthorizationRequired):
            orch.run_stage(
                workflow_id=workflow_id,
                stage="STAGE2",
                trusted_context={},
                user_authorized=False,
            )
        result = orch.run_stage(
            workflow_id=workflow_id,
            stage="STAGE2",
            trusted_context={},
            user_authorized=True,
        )
        self.assertTrue(result["validated"])

    def test_user_supplied_non_native_price_is_only_loaded_from_authoritative_store(self):
        orch, llm = self.make([stage1_valid()])
        workflow_id = self.complete_stage1(orch)
        llm.add(stage2_valid())
        orch.run_stage(workflow_id=workflow_id, stage="STAGE2", trusted_context={}, user_authorized=True)
        evidence = orch.add_user_price(
            workflow_id=workflow_id,
            market="Double Chance",
            selection="Home 1X",
            price=1.55,
            observed_at="2026-10-07T19:00:00+03:00",
        )
        self.assertEqual(evidence["origin"], "USER_SUPPLIED")
        llm.add(stage3_protected_valid())
        result = orch.run_stage(workflow_id=workflow_id, stage="STAGE3", trusted_context={}, user_authorized=True)
        row = result["report"]["rows"][0]
        self.assertEqual(row["decision"], "BET")
        self.assertEqual(row["final_confidence"], 77.0)
        self.assertEqual(row["price_evidence"]["origin"], "USER_SUPPLIED")
        self.assertEqual(row["price_evidence"]["price"], 1.55)
        self.assertEqual(row["preference"]["price"], 1.55)

    def test_fake_user_supplied_price_in_context_cannot_bypass_price_store(self):
        orch, llm = self.make([stage1_valid()], attempts=1)
        workflow_id = self.complete_stage1(orch)
        llm.add(stage2_valid())
        orch.run_stage(workflow_id=workflow_id, stage="STAGE2", trusted_context={}, user_authorized=True)
        llm.add(stage3_protected_valid())
        fake_context = {
            "price_evidence": [
                {
                    "origin": "USER_SUPPLIED",
                    "source": "USER_SUPPLIED",
                    "market": "Double Chance",
                    "selection": "Home 1X",
                    "price": 9.99,
                    "observed_at": "2026-10-07T19:00:00+03:00",
                    "status": "OBSERVED",
                }
            ]
        }
        with self.assertRaises(ValidationExhausted) as caught:
            orch.run_stage(
                workflow_id=workflow_id,
                stage="STAGE3",
                trusted_context=fake_context,
                user_authorized=True,
            )
        self.assertTrue(any(v["rule_id"] == "SXF-PRICE-005" for v in caught.exception.violations))
        self.assertIsNone(orch.store.get_stage_output(workflow_id, "STAGE3"))

    def test_state_survives_store_restart(self):
        orch, _ = self.make([stage1_valid()])
        workflow_id = self.complete_stage1(orch)
        fresh_store = SQLiteOrchestratorStore(self.db_path)
        restored = fresh_store.get_workflow(workflow_id)
        self.assertIsNotNone(restored.state.stage1_run_id)
        self.assertEqual(restored.state.stage1_candidate_ids, ("m1",))

    def test_http_api_requires_secret_and_does_not_expose_invalid_raw_output(self):
        orch, _ = self.make([stage1_invalid_partial_scan()], attempts=1)
        cfg = self.config(attempts=1)
        app = create_app(config=cfg, orchestrator=orch)
        client = app.test_client()

        unauth = client.post("/api/predictor/workflows", json={"scope": {}})
        self.assertEqual(unauth.status_code, 401)

        headers = {"Authorization": "Bearer test-secret"}
        created = client.post("/api/predictor/workflows", json={"scope": {"window": ["18:00", "24:00"]}}, headers=headers)
        self.assertEqual(created.status_code, 201)
        workflow_id = created.get_json()["workflow"]["workflow_id"]

        response = client.post(
            f"/api/predictor/workflows/{workflow_id}/stage1",
            json={"trusted_context": self.stage1_context()},
            headers=headers,
        )
        self.assertEqual(response.status_code, 422)
        body = response.get_json()
        self.assertEqual(body["error"]["code"], "PREDICTOR_VALIDATION_FAILED")
        self.assertNotIn("raw_payload", str(body))
        self.assertNotIn("99.0", str(body))

    def test_http_stage2_requires_explicit_user_authorized_flag(self):
        orch, _ = self.make([])
        cfg = self.config()
        app = create_app(config=cfg, orchestrator=orch)
        client = app.test_client()
        headers = {"Authorization": "Bearer test-secret"}
        created = client.post("/api/predictor/workflows", json={"scope": {}}, headers=headers)
        workflow_id = created.get_json()["workflow"]["workflow_id"]
        response = client.post(
            f"/api/predictor/workflows/{workflow_id}/stage2",
            json={"trusted_context": {}},
            headers=headers,
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"]["code"], "USER_AUTHORIZATION_REQUIRED")


if __name__ == "__main__":
    unittest.main()
