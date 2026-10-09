from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
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
    now = datetime.now(timezone.utc)
    observed = (now - timedelta(minutes=10)).isoformat()
    recent = (now - timedelta(hours=2)).isoformat()
    performance_time = (now - timedelta(days=2)).isoformat()
    return {
        "matches": [
            {
                "fixture_id": "m1",
                "research_checks": {
                    "squad": {"status": "VERIFIED", "fact_ids": ["f1"], "note": "Güncel kadro/availability kaynağı kontrol edildi."},
                    "performance": {"status": "VERIFIED", "fact_ids": ["f2"], "note": "Yakın dönem market-relevant performans kontrol edildi."},
                    "counter": {"status": "VERIFIED", "fact_ids": ["f3"], "note": "Frozen Stage 1 tezine karşı en güçlü senaryo ayrıca araştırıldı."},
                },
                "facts": [
                    {
                        "fact_id": "f1",
                        "kind": "FACT",
                        "category": "SQUAD",
                        "materiality": "MATERIAL",
                        "relationship": "NEUTRAL",
                        "claim": "Güncel resmi kadro bilgisinde ev sahibi çekirdeğini bozan material bir eksik görünmüyor.",
                        "source": "https://www.uefa.com/news/test-squad",
                        "source_tier": "A",
                        "observed_at": observed,
                        "evidence_at": recent,
                        "derived_from_fact_ids": [],
                        "corroborating_sources": [],
                    },
                    {
                        "fact_id": "f2",
                        "kind": "FACT",
                        "category": "PERFORMANCE",
                        "materiality": "MATERIAL",
                        "relationship": "SUPPORTS",
                        "claim": "Yakın dönem üretim/şut profili ev sahibinin Stage 1 yönünü destekliyor.",
                        "source": "https://www.fotmob.com/matches/test-performance",
                        "source_tier": "C",
                        "observed_at": observed,
                        "evidence_at": performance_time,
                        "derived_from_fact_ids": [],
                        "corroborating_sources": [],
                    },
                    {
                        "fact_id": "f3",
                        "kind": "FACT",
                        "category": "CONTEXT",
                        "materiality": "MATERIAL",
                        "relationship": "CONTRADICTS",
                        "claim": "Rakibin geçiş tehdidi ve güncel maç bağlamı beraberlik/deplasman yolunu açık tutuyor.",
                        "source": "https://www.reuters.com/sports/soccer/test-counter",
                        "source_tier": "B",
                        "observed_at": observed,
                        "evidence_at": recent,
                        "derived_from_fact_ids": [],
                        "corroborating_sources": [],
                    },
                ],
                "support_fact_ids": ["f2"],
                "counter_fact_ids": ["f3"],
                "research_support": "Yakın dönem üretim kalitesi Stage 1 yönünü destekliyor.",
                "research_counter": "Rakibin geçiş tehdidi en güçlü doğrulanmış karşı tez.",
                "research_synthesis": "Dış araştırma frozen Stage 1 tezini kısmen doğruluyor; performans desteği var fakat rakibin geçiş tehdidi nedeniyle tam doğrulama yok.",
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
        kickoff = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        return {
            "source_fixture_ids": ["m1", "m2"],
            "fixtures": [
                {"fixture_id": "m1", "home": "Home", "away": "Away", "kickoff_utc": kickoff, "sxf_history": [{"t": 1}, {"t": 2}]},
                {"fixture_id": "m2", "home": "Other", "away": "Guest", "kickoff_utc": kickoff, "sxf_history": [{"t": 1}, {"t": 2}]},
            ],
            "price_evidence": [
                {
                    "fixture_id": "m1",
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
            fixture_id="m1",
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
                    "fixture_id": "m1",
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

    def test_same_market_selection_price_cannot_cross_fixtures(self):
        orch, llm = self.make([stage1_valid()])
        workflow_id = self.complete_stage1(orch)
        orch.add_user_price(
            workflow_id=workflow_id,
            fixture_id="other-fixture",
            market="Double Chance",
            selection="Home 1X",
            price=9.99,
            observed_at="2026-10-07T19:00:00+03:00",
        )
        self.assertIsNone(orch.store.find_user_price(workflow_id, "m1", "Double Chance", "Home 1X"))
        exact = orch.store.find_user_price(workflow_id, "other-fixture", "Double Chance", "Home 1X")
        self.assertEqual(exact["price"], 9.99)

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

    def test_stage1_context_endpoint_is_server_owned_and_hashed(self):
        class FakeSource:
            def __init__(self, context):
                self.context = deepcopy(context)
                self.calls = []
            def build_stage1_context(self, scope):
                self.calls.append(deepcopy(scope))
                return deepcopy(self.context)

        orch, _ = self.make([])
        cfg = self.config()
        source = FakeSource(self.stage1_context())
        app = create_app(config=cfg, orchestrator=orch, stage1_source=source)
        client = app.test_client()
        headers = {"Authorization": "Bearer test-secret"}
        created = client.post("/api/predictor/workflows", json={"scope": {"date": "2026-10-07", "window_tr": ["18:00", "24:00"]}}, headers=headers)
        workflow_id = created.get_json()["workflow"]["workflow_id"]
        prepared = client.post(f"/api/predictor/workflows/{workflow_id}/stage1/context", headers=headers)
        self.assertEqual(prepared.status_code, 200, prepared.get_data(as_text=True))
        body = prepared.get_json()
        self.assertEqual(len(body["context_sha256"]), 64)
        self.assertEqual(body["analysis_context"]["source_fixture_ids"], ["m1", "m2"])
        stored = orch.store.get_trusted_context(workflow_id, "STAGE1")
        self.assertEqual(stored["context_sha256"], body["context_sha256"])
        self.assertEqual(source.calls[0]["date"], "2026-10-07")

    def test_external_stage1_requires_server_owned_context(self):
        orch, _ = self.make([])
        cfg = self.config()
        app = create_app(config=cfg, orchestrator=orch)
        client = app.test_client()
        headers = {"Authorization": "Bearer test-secret"}
        created = client.post("/api/predictor/workflows", json={"scope": {}}, headers=headers)
        workflow_id = created.get_json()["workflow"]["workflow_id"]
        response = client.post(
            f"/api/predictor/workflows/{workflow_id}/stage1/submit",
            json={"generated": stage1_valid()},
            headers=headers,
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"]["code"], "PREDICTOR_TRUSTED_CONTEXT_REQUIRED")

    def test_external_agent_submit_recomposes_authority_fields(self):
        orch, _ = self.make([])
        cfg = self.config()
        app = create_app(config=cfg, orchestrator=orch)
        client = app.test_client()
        headers = {"Authorization": "Bearer test-secret"}
        created = client.post("/api/predictor/workflows", json={"scope": {"window": ["18:00", "24:00"]}}, headers=headers)
        workflow_id = created.get_json()["workflow"]["workflow_id"]
        orch.store.save_trusted_context(workflow_id, "STAGE1", self.stage1_context())
        generated = stage1_valid()
        generated["run_id"] = "evil-model-run"
        generated["stage"] = "STAGE3"
        generated["external_research_used"] = True
        response = client.post(
            f"/api/predictor/workflows/{workflow_id}/stage1/submit",
            json={
                "trusted_context": {"source_fixture_ids": ["evil-fixture"]},
                "generated": generated,
                "agent_model": "chatgpt-test-agent",
            },
            headers=headers,
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        body = response.get_json()
        self.assertTrue(body["validated"])
        stored = orch.store.get_stage_output(workflow_id, "STAGE1")
        self.assertEqual(stored["payload"]["stage"], "STAGE1")
        self.assertFalse(stored["payload"]["external_research_used"])
        self.assertNotEqual(stored["payload"]["run_id"], "evil-model-run")
        self.assertEqual(stored["model"], "chatgpt-test-agent")

    def test_external_agent_invalid_submit_fails_closed_without_raw_leak(self):
        orch, _ = self.make([])
        cfg = self.config()
        app = create_app(config=cfg, orchestrator=orch)
        client = app.test_client()
        headers = {"Authorization": "Bearer test-secret"}
        created = client.post("/api/predictor/workflows", json={"scope": {}}, headers=headers)
        workflow_id = created.get_json()["workflow"]["workflow_id"]
        orch.store.save_trusted_context(workflow_id, "STAGE1", self.stage1_context())
        generated = stage1_invalid_partial_scan()
        generated["secret_model_note"] = "must-never-leak"
        response = client.post(
            f"/api/predictor/workflows/{workflow_id}/stage1/submit",
            json={"trusted_context": {"source_fixture_ids": ["evil"]}, "generated": generated},
            headers=headers,
        )
        self.assertEqual(response.status_code, 422)
        text = response.get_data(as_text=True)
        self.assertNotIn("must-never-leak", text)
        self.assertIsNone(orch.store.get_stage_output(workflow_id, "STAGE1"))
        self.assertIsNone(orch.get_workflow(workflow_id).state.stage1_run_id)

    def test_external_agent_stage2_requires_explicit_authorization(self):
        orch, _ = self.make([stage1_valid()])
        workflow_id = self.complete_stage1(orch)
        cfg = self.config()
        app = create_app(config=cfg, orchestrator=orch)
        client = app.test_client()
        headers = {"Authorization": "Bearer test-secret"}
        response = client.post(
            f"/api/predictor/workflows/{workflow_id}/stage2/submit",
            json={"generated": stage2_valid()},
            headers=headers,
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.get_json()["error"]["code"], "USER_AUTHORIZATION_REQUIRED")

    def test_http_price_endpoint_requires_fixture_id(self):
        orch, _ = self.make([])
        cfg = self.config()
        app = create_app(config=cfg, orchestrator=orch)
        client = app.test_client()
        headers = {"Authorization": "Bearer test-secret"}
        created = client.post("/api/predictor/workflows", json={"scope": {}}, headers=headers)
        workflow_id = created.get_json()["workflow"]["workflow_id"]
        response = client.post(
            f"/api/predictor/workflows/{workflow_id}/prices",
            json={"market": "Double Chance", "selection": "Home 1X", "price": 1.55},
            headers=headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"]["code"], "BAD_REQUEST")

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
