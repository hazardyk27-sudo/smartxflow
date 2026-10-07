from __future__ import annotations

import hashlib
import json
from typing import Any


class FormalPublicationError(RuntimeError):
    pass


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def build_publication_receipt(
    *,
    workflow_id: str,
    stage: str,
    accepted_record: dict[str, Any],
) -> dict[str, Any]:
    """Build an integrity receipt only from a durable accepted-stage record.

    Callers must pass the value returned by SQLiteOrchestratorStore.get_stage_output()
    after accept_stage() committed. Raw/generated/model output is deliberately not a
    supported input to this function.
    """
    if not isinstance(accepted_record, dict):
        raise FormalPublicationError("accepted stage record is required")
    payload = accepted_record.get("payload")
    rendered = accepted_record.get("rendered")
    stage_run_id = str(accepted_record.get("stage_run_id") or "").strip()
    accepted_at = str(accepted_record.get("accepted_at") or "").strip()
    model = str(accepted_record.get("model") or "").strip()
    policy_version = accepted_record.get("policy_version")
    normalized_stage = str(stage or "").upper()
    if not isinstance(payload, dict) or not isinstance(rendered, dict):
        raise FormalPublicationError("accepted stage payload/rendered report is missing")
    if str(payload.get("stage") or "").upper() != normalized_stage:
        raise FormalPublicationError("accepted stage payload does not match requested stage")
    if not stage_run_id or str(payload.get("run_id") or "") != stage_run_id:
        raise FormalPublicationError("accepted stage_run_id does not match persisted payload")
    if not accepted_at or not model or not isinstance(policy_version, int):
        raise FormalPublicationError("accepted stage metadata is incomplete")

    core = {
        "workflow_id": str(workflow_id),
        "stage": normalized_stage,
        "stage_run_id": stage_run_id,
        "accepted_at": accepted_at,
        "model": model,
        "policy_version": policy_version,
        "payload_sha256": _sha256(payload),
        "rendered_sha256": _sha256(rendered),
    }
    return {
        "status": "ACCEPTED_PERSISTED",
        **core,
        "receipt_sha256": _sha256(core),
    }


def formal_result_from_store(
    *,
    store: Any,
    workflow_id: str,
    stage: str,
    expected_stage_run_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read the accepted report back from durable state and issue its receipt."""
    accepted = store.get_stage_output(workflow_id, stage)
    if accepted is None:
        raise FormalPublicationError("accepted stage was not durable after commit")
    if str(accepted.get("stage_run_id") or "") != str(expected_stage_run_id or ""):
        raise FormalPublicationError("durable stage_run_id differs from accepted run")
    report = accepted.get("rendered")
    if not isinstance(report, dict):
        raise FormalPublicationError("durable rendered report is invalid")
    receipt = build_publication_receipt(
        workflow_id=workflow_id,
        stage=stage,
        accepted_record=accepted,
    )
    return report, receipt
