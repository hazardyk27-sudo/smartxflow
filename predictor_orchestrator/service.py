from __future__ import annotations

from datetime import datetime, timezone
import threading
from typing import Any
from uuid import uuid4

from predictor_policy.runtime import validate_and_advance
from predictor_policy.validator import PredictorPolicyError, load_policy, user_supplied_price_evidence

from .config import OrchestratorConfig
from .llm_client import LLMClient
from .prompts import system_prompt, user_prompt
from .renderer import render_payload
from .schemas import schema_for_stage
from .store import SQLiteOrchestratorStore, WorkflowRecord


_GRADE_ACTION = {"A+": "BET", "A": "BET", "B": "WATCH", "C": "PASS"}
_COUNTER_PENALTY = {"NONE": 0, "LIGHT": -3, "MEDIUM": -7, "STRONG": -12, "STRUCTURAL": -20}


class OrchestratorError(RuntimeError):
    status_code = 500
    code = "PREDICTOR_ORCHESTRATOR_ERROR"


class WorkflowNotFound(OrchestratorError):
    status_code = 404
    code = "PREDICTOR_WORKFLOW_NOT_FOUND"


class StageConflict(OrchestratorError):
    status_code = 409
    code = "PREDICTOR_STAGE_CONFLICT"


class UserAuthorizationRequired(StageConflict):
    code = "USER_AUTHORIZATION_REQUIRED"


class TrustedContextRequired(StageConflict):
    code = "PREDICTOR_TRUSTED_CONTEXT_REQUIRED"


class ValidationExhausted(OrchestratorError):
    status_code = 422
    code = "PREDICTOR_VALIDATION_FAILED"

    def __init__(self, violations: list[dict[str, str]]):
        super().__init__("Predictor output failed mandatory validation")
        self.violations = violations


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fixture_id(value: dict[str, Any]) -> str:
    return str(value.get("fixture_id") or value.get("fixture_uid") or value.get("match_id_hash") or "").strip()


def _preference(value: dict[str, Any] | None) -> dict[str, Any]:
    value = value or {}
    return {
        "market": str(value.get("market") or "").strip(),
        "selection": str(value.get("selection") or "").strip(),
    }


def _violation_dicts(exc: PredictorPolicyError) -> list[dict[str, str]]:
    text = str(exc)
    rows: list[dict[str, str]] = []
    for part in text.split("; "):
        if ": " in part:
            rule_id, message = part.split(": ", 1)
            rows.append({"rule_id": rule_id.strip(), "message": message.strip()})
        else:
            rows.append({"rule_id": "PREDICTOR_VALIDATION", "message": part.strip()})
    return rows


class PredictorOrchestrator:
    """Mandatory publication gate for Predictor model output."""

    def __init__(self, *, config: OrchestratorConfig, store: SQLiteOrchestratorStore, llm: LLMClient):
        self.config = config
        self.store = store
        self.llm = llm
        self._lock = threading.RLock()
        self.policy_version = int(load_policy().get("policy_version") or 0)

    def create_workflow(self, scope: dict[str, Any]) -> WorkflowRecord:
        if not isinstance(scope, dict):
            raise OrchestratorError("scope must be an object")
        workflow_id = f"pred_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:10]}"
        return self.store.create_workflow(workflow_id, scope)

    def get_workflow(self, workflow_id: str) -> WorkflowRecord:
        record = self.store.get_workflow(workflow_id)
        if record is None:
            raise WorkflowNotFound(workflow_id)
        return record

    def add_user_price(self, *, workflow_id: str, fixture_id: str, market: str, selection: str, price: float, observed_at: str | None = None, status: str = "OBSERVED") -> dict[str, Any]:
        self.get_workflow(workflow_id)
        fixture_id = str(fixture_id or "").strip()
        if not fixture_id:
            raise OrchestratorError("fixture_id is required for user-supplied price evidence")
        evidence = user_supplied_price_evidence(
            fixture_id=fixture_id,
            market=market,
            selection=selection,
            price=price,
            observed_at=observed_at,
            received_at=_now(),
            status=status,
        )
        self.store.add_user_price(
            workflow_id=workflow_id,
            fixture_id=evidence["fixture_id"],
            market=evidence["market"],
            selection=evidence["selection"],
            price=float(evidence["price"]),
            observed_at=evidence["observed_at"],
            status=evidence["status"],
        )
        return evidence

    @staticmethod
    def _stage_name(stage: str) -> str:
        normalized = str(stage or "").upper()
        if normalized not in {"STAGE1", "STAGE2", "STAGE3"}:
            raise OrchestratorError(f"unsupported stage {stage!r}")
        return normalized

    @staticmethod
    def _stage1_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {_fixture_id(item): item for item in payload.get("matches") or [] if isinstance(item, dict) and _fixture_id(item)}

    @staticmethod
    def _stage2_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {_fixture_id(item): item for item in payload.get("matches") or [] if isinstance(item, dict) and _fixture_id(item)}

    @staticmethod
    def _trusted_price(context: dict[str, Any], fixture_id: str, market: str, selection: str, *, allowed_origins: set[str]) -> dict[str, Any] | None:
        for item in context.get("price_evidence") or []:
            if not isinstance(item, dict):
                continue
            origin = str(item.get("origin") or "").upper()
            if origin not in allowed_origins:
                continue
            if str(item.get("fixture_id") or "").strip() != str(fixture_id or "").strip():
                continue
            if str(item.get("market") or "").strip() == market and str(item.get("selection") or "").strip() == selection:
                return dict(item)
        return None

    def _compose_stage1(self, *, stage_run_id: str, generated: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        if "source_fixture_ids" not in context or not isinstance(context.get("source_fixture_ids"), list):
            raise OrchestratorError("Stage 1 trusted_context.source_fixture_ids must be an explicit list")
        source_ids = [str(x) for x in context["source_fixture_ids"]]
        matches: list[dict[str, Any]] = []
        for item in generated.get("matches") or []:
            if not isinstance(item, dict):
                continue
            pref = _preference(item.get("preference"))
            trusted = self._trusted_price(context, _fixture_id(item), pref["market"], pref["selection"], allowed_origins={"SXF_NATIVE"})
            if trusted and isinstance(trusted.get("price"), (int, float)):
                pref["price"] = float(trusted["price"])
            matches.append({
                "fixture_id": _fixture_id(item),
                "preference": pref,
                "rationale": item.get("rationale"),
                "strongest_counterargument": item.get("strongest_counterargument"),
            })
        return {
            "run_id": stage_run_id,
            "stage": "STAGE1",
            "external_research_used": False,
            "scope": {"universe_resolved": True, "source_fixture_ids": source_ids},
            "screening_results": generated.get("screening_results") or [],
            "matches": matches,
        }

    def _compose_stage2(self, *, workflow: WorkflowRecord, stage_run_id: str, generated: dict[str, Any], stage1_payload: dict[str, Any]) -> dict[str, Any]:
        stage1_by_id = self._stage1_map(stage1_payload)
        matches: list[dict[str, Any]] = []
        for item in generated.get("matches") or []:
            if not isinstance(item, dict):
                continue
            fixture_id = _fixture_id(item)
            baseline = _preference((stage1_by_id.get(fixture_id) or {}).get("preference"))
            matches.append({
                "fixture_id": fixture_id,
                "frozen_stage1_preference": baseline,
                "research_checks": item.get("research_checks"),
                "facts": item.get("facts"),
                "research_support": item.get("research_support"),
                "research_counter": item.get("research_counter"),
                "important_absence": item.get("important_absence"),
                "coverage": item.get("coverage"),
                "verdict": item.get("verdict"),
            })
        return {
            "run_id": stage_run_id,
            "stage": "STAGE2",
            "authorized_by_user": True,
            "predecessor_stage1_run_id": workflow.state.stage1_run_id,
            "stage1_candidate_ids": list(workflow.state.stage1_candidate_ids),
            "matches": matches,
        }

    def _compose_stage3(self, *, workflow: WorkflowRecord, stage_run_id: str, generated: dict[str, Any], stage1_payload: dict[str, Any], stage2_payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        stage1_by_id = self._stage1_map(stage1_payload)
        stage2_by_id = self._stage2_map(stage2_payload)
        recorded_at = _now()
        matches: list[dict[str, Any]] = []
        for item in generated.get("matches") or []:
            if not isinstance(item, dict):
                continue
            fixture_id = _fixture_id(item)
            pref = _preference(item.get("preference"))
            grade = str(item.get("grade") or "").upper()
            decision = _GRADE_ACTION.get(grade, "")
            severity = str(item.get("counter_severity") or "").upper()
            raw_confidence = item.get("raw_confidence")
            final_confidence = raw_confidence
            if isinstance(raw_confidence, (int, float)) and not isinstance(raw_confidence, bool):
                final_confidence = float(raw_confidence) + _COUNTER_PENALTY.get(severity, 0)
            price_evidence = self.store.find_user_price(workflow.workflow_id, fixture_id, pref["market"], pref["selection"])
            if price_evidence is None:
                price_evidence = self._trusted_price(context, fixture_id, pref["market"], pref["selection"], allowed_origins={"SXF_NATIVE", "EXTERNAL_VERIFIED", "THRESHOLD_ONLY"})
            if price_evidence and isinstance(price_evidence.get("price"), (int, float)):
                pref["price"] = float(price_evidence["price"])
            baseline = _preference((stage1_by_id.get(fixture_id) or {}).get("preference"))
            stage2 = stage2_by_id.get(fixture_id) or {}
            matches.append({
                "fixture_id": fixture_id,
                "preference": pref,
                "stage1_baseline": baseline,
                "stage2_verdict": stage2.get("verdict"),
                "grade": grade,
                "decision": decision,
                "counter_severity": severity,
                "raw_confidence": raw_confidence,
                "final_confidence": final_confidence,
                "divergence_state": item.get("divergence_state"),
                "execution_type": item.get("execution_type"),
                "material_reversal_explained": item.get("material_reversal_explained"),
                "material_reversal_explanation": item.get("material_reversal_explanation"),
                "rationale": item.get("rationale"),
                "strongest_counterargument": item.get("strongest_counterargument"),
                "change_driver": item.get("change_driver"),
                "prediction_at": recorded_at,
                "decision_recorded_at": recorded_at,
                "archive_intent": decision in {"BET", "WATCH"},
                "price_evidence": price_evidence,
            })
        return {
            "run_id": stage_run_id,
            "stage": "STAGE3",
            "authorized_by_user": True,
            "predecessor_stage1_run_id": workflow.state.stage1_run_id,
            "predecessor_stage2_run_id": workflow.state.stage2_run_id,
            "stage1_candidate_ids": list(workflow.state.stage1_candidate_ids),
            "matches": matches,
        }

    def _compose(self, *, workflow: WorkflowRecord, stage: str, stage_run_id: str, generated: dict[str, Any], context: dict[str, Any], stage1_payload: dict[str, Any] | None, stage2_payload: dict[str, Any] | None) -> dict[str, Any]:
        if stage == "STAGE1":
            return self._compose_stage1(stage_run_id=stage_run_id, generated=generated, context=context)
        if stage == "STAGE2":
            if stage1_payload is None:
                raise StageConflict("Stage 2 requires accepted Stage 1")
            return self._compose_stage2(workflow=workflow, stage_run_id=stage_run_id, generated=generated, stage1_payload=stage1_payload)
        if stage == "STAGE3":
            if stage1_payload is None or stage2_payload is None:
                raise StageConflict("Stage 3 requires accepted Stage 1 and Stage 2")
            return self._compose_stage3(workflow=workflow, stage_run_id=stage_run_id, generated=generated, stage1_payload=stage1_payload, stage2_payload=stage2_payload, context=context)
        raise OrchestratorError(f"unsupported stage {stage}")

    def _preflight(self, workflow: WorkflowRecord, stage: str, *, user_authorized: bool) -> None:
        if self.store.get_stage_output(workflow.workflow_id, stage) is not None:
            raise StageConflict(f"{stage} already completed")
        if stage == "STAGE1" and workflow.state.stage1_run_id:
            raise StageConflict("Stage 1 already completed")
        if stage == "STAGE2":
            if not user_authorized:
                raise UserAuthorizationRequired("Stage 2 requires explicit user authorization")
            if not workflow.state.stage1_run_id:
                raise StageConflict("Stage 2 cannot start before Stage 1")
        if stage == "STAGE3":
            if not user_authorized:
                raise UserAuthorizationRequired("Stage 3 requires explicit user authorization")
            if not workflow.state.stage1_run_id or not workflow.state.stage2_run_id:
                raise StageConflict("Stage 3 cannot start before Stage 1 and Stage 2")

    def submit_generated_stage(self, *, workflow_id: str, stage: str, generated: dict[str, Any], user_authorized: bool = False, agent_model: str = "chatgpt-agent-external") -> dict[str, Any]:
        stage = self._stage_name(stage)
        if not isinstance(generated, dict):
            raise OrchestratorError("generated must be an object")
        model_name = str(agent_model or "chatgpt-agent-external").strip()[:128] or "chatgpt-agent-external"
        with self._lock:
            workflow = self.get_workflow(workflow_id)
            self._preflight(workflow, stage, user_authorized=user_authorized)
            trusted_record = self.store.get_trusted_context(workflow_id, stage)
            if stage == "STAGE1" and trusted_record is None:
                raise TrustedContextRequired("Stage 1 requires server-owned trusted SXF context")
            trusted_context = trusted_record["context"] if trusted_record else {}
            stage1_record = self.store.get_stage_output(workflow_id, "STAGE1")
            stage2_record = self.store.get_stage_output(workflow_id, "STAGE2")
            stage1_payload = stage1_record["payload"] if stage1_record else None
            stage2_payload = stage2_record["payload"] if stage2_record else None
            stage_run_id = f"{workflow_id}:{stage.lower()}:{uuid4().hex[:10]}"
            payload = self._compose(workflow=workflow, stage=stage, stage_run_id=stage_run_id, generated=generated, context=trusted_context, stage1_payload=stage1_payload, stage2_payload=stage2_payload)
            try:
                new_state = validate_and_advance(workflow.state, payload)
            except PredictorPolicyError as exc:
                violations = _violation_dicts(exc)
                self.store.save_attempt(workflow_id=workflow_id, stage=stage, attempt_no=1, model=model_name, raw_payload=payload, violations=violations, accepted=False)
                raise ValidationExhausted(violations) from exc
            rendered = render_payload(payload)
            self.store.accept_stage(workflow_id=workflow_id, stage=stage, stage_run_id=stage_run_id, payload=payload, rendered=rendered, model=model_name, policy_version=self.policy_version, new_state=new_state)
            return {
                "workflow_id": workflow_id,
                "stage": stage,
                "stage_run_id": stage_run_id,
                "policy_version": self.policy_version,
                "attempts": 1,
                "validated": True,
                "context_sha256": trusted_record["context_sha256"] if trusted_record else None,
                "report": rendered,
            }

    def run_stage(self, *, workflow_id: str, stage: str, trusted_context: dict[str, Any], user_authorized: bool = False) -> dict[str, Any]:
        stage = self._stage_name(stage)
        if not isinstance(trusted_context, dict):
            raise OrchestratorError("trusted_context must be an object")
        with self._lock:
            workflow = self.get_workflow(workflow_id)
            self._preflight(workflow, stage, user_authorized=user_authorized)
            stage1_record = self.store.get_stage_output(workflow_id, "STAGE1")
            stage2_record = self.store.get_stage_output(workflow_id, "STAGE2")
            stage1_payload = stage1_record["payload"] if stage1_record else None
            stage2_payload = stage2_record["payload"] if stage2_record else None
            stage_run_id = f"{workflow_id}:{stage.lower()}:{uuid4().hex[:10]}"
            repair_violations: list[dict[str, str]] | None = None
            previous_invalid: dict[str, Any] | None = None
            last_violations: list[dict[str, str]] = []
            for attempt in range(1, self.config.max_attempts + 1):
                generated, _response_id = self.llm.generate(
                    stage=stage,
                    system_prompt=system_prompt(stage),
                    user_prompt=user_prompt(stage=stage, trusted_context=trusted_context, stage1_payload=stage1_payload, stage2_payload=stage2_payload, repair_violations=repair_violations, previous_invalid=previous_invalid),
                    schema=schema_for_stage(stage),
                )
                payload = self._compose(workflow=workflow, stage=stage, stage_run_id=stage_run_id, generated=generated, context=trusted_context, stage1_payload=stage1_payload, stage2_payload=stage2_payload)
                try:
                    new_state = validate_and_advance(workflow.state, payload)
                except PredictorPolicyError as exc:
                    last_violations = _violation_dicts(exc)
                    self.store.save_attempt(workflow_id=workflow_id, stage=stage, attempt_no=attempt, model=self.llm.model, raw_payload=payload, violations=last_violations, accepted=False)
                    repair_violations = last_violations
                    previous_invalid = generated
                    continue
                rendered = render_payload(payload)
                self.store.accept_stage(workflow_id=workflow_id, stage=stage, stage_run_id=stage_run_id, payload=payload, rendered=rendered, model=self.llm.model, policy_version=self.policy_version, new_state=new_state)
                self.store.save_attempt(workflow_id=workflow_id, stage=stage, attempt_no=attempt, model=self.llm.model, raw_payload=payload, violations=[], accepted=True)
                return {
                    "workflow_id": workflow_id,
                    "stage": stage,
                    "stage_run_id": stage_run_id,
                    "policy_version": self.policy_version,
                    "attempts": attempt,
                    "validated": True,
                    "report": rendered,
                }
            raise ValidationExhausted(last_violations)
