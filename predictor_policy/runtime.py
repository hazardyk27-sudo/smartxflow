from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .validator import PredictorPolicyError, validate_payload


@dataclass(frozen=True)
class PredictorRunState:
    stage1_run_id: str | None = None
    stage1_candidate_ids: tuple[str, ...] = ()
    stage2_run_id: str | None = None
    stage3_run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["stage1_candidate_ids"] = list(self.stage1_candidate_ids)
        return data

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "PredictorRunState":
        value = value or {}
        return cls(
            stage1_run_id=value.get("stage1_run_id"),
            stage1_candidate_ids=tuple(str(item) for item in value.get("stage1_candidate_ids") or []),
            stage2_run_id=value.get("stage2_run_id"),
            stage3_run_id=value.get("stage3_run_id"),
        )


def _candidate_ids(payload: dict[str, Any]) -> tuple[str, ...]:
    result: list[str] = []
    for item in payload.get("matches") or []:
        if not isinstance(item, dict):
            continue
        fixture_id = str(item.get("fixture_uid") or item.get("match_id_hash") or item.get("fixture_id") or "").strip()
        if fixture_id:
            result.append(fixture_id)
    return tuple(result)


def validate_and_advance(state: PredictorRunState, payload: dict[str, Any]) -> PredictorRunState:
    result = validate_payload(payload)
    result.raise_for_errors()
    stage = str(payload.get("stage") or "").upper()
    run_id = str(payload.get("run_id") or "").strip()

    if stage == "STAGE1":
        return PredictorRunState(
            stage1_run_id=run_id,
            stage1_candidate_ids=_candidate_ids(payload),
            stage2_run_id=None,
            stage3_run_id=None,
        )

    if stage == "STAGE2":
        if not state.stage1_run_id:
            raise PredictorPolicyError("SXF-WF-005: Stage 2 cannot run before a validated Stage 1")
        if str(payload.get("predecessor_stage1_run_id") or "") != state.stage1_run_id:
            raise PredictorPolicyError("SXF-WF-005: Stage 2 predecessor_stage1_run_id does not match runtime state")
        active = tuple(str(item) for item in (payload.get("user_scope_override_ids") if "user_scope_override_ids" in payload else payload.get("stage1_candidate_ids") or []))
        if set(active) != set(state.stage1_candidate_ids) and payload.get("scope_change_authorized_by_user") is not True:
            raise PredictorPolicyError("SXF-WF-005: Stage 2 candidate set changed without explicit user scope authorization")
        return PredictorRunState(
            stage1_run_id=state.stage1_run_id,
            stage1_candidate_ids=active,
            stage2_run_id=run_id,
            stage3_run_id=None,
        )

    if stage == "STAGE3":
        if not state.stage1_run_id or not state.stage2_run_id:
            raise PredictorPolicyError("SXF-WF-005: Stage 3 cannot run before validated Stage 1 and Stage 2")
        if str(payload.get("predecessor_stage1_run_id") or "") != state.stage1_run_id:
            raise PredictorPolicyError("SXF-WF-005: Stage 3 predecessor_stage1_run_id does not match runtime state")
        if str(payload.get("predecessor_stage2_run_id") or "") != state.stage2_run_id:
            raise PredictorPolicyError("SXF-WF-005: Stage 3 predecessor_stage2_run_id does not match runtime state")
        active = tuple(str(item) for item in (payload.get("user_scope_override_ids") if "user_scope_override_ids" in payload else payload.get("stage1_candidate_ids") or []))
        if set(active) != set(state.stage1_candidate_ids) and payload.get("scope_change_authorized_by_user") is not True:
            raise PredictorPolicyError("SXF-WF-005: Stage 3 candidate set changed without explicit user scope authorization")
        return PredictorRunState(
            stage1_run_id=state.stage1_run_id,
            stage1_candidate_ids=active,
            stage2_run_id=state.stage2_run_id,
            stage3_run_id=run_id,
        )

    raise PredictorPolicyError(f"SXF-WF-001: unsupported stage {stage!r}")
