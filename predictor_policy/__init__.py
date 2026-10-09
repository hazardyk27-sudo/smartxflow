from .validator import (
    PredictorPolicyError,
    ValidationResult,
    Violation,
    format_violations,
    load_policy,
    user_supplied_price_evidence,
    validate_payload as _validate_payload_base,
    validate_stage1,
    validate_stage3,
)
from .stage2_quality import validate_stage2_quality
from .stage2_strict import validate_stage2_strict
from .stage_comparison import (
    StageComparison,
    StageOutcome,
    compare_stage_preferences,
    summarize_comparisons,
)
from .runtime import PredictorRunState, validate_and_advance


def validate_stage2(payload):
    return validate_stage2_strict(payload)


def validate_payload(payload):
    if str(payload.get("stage") or "").upper() == "STAGE2":
        return validate_stage2_strict(payload)
    return _validate_payload_base(payload)


__all__ = [
    "PredictorPolicyError",
    "ValidationResult",
    "Violation",
    "format_violations",
    "load_policy",
    "user_supplied_price_evidence",
    "validate_payload",
    "validate_stage1",
    "validate_stage2",
    "validate_stage2_quality",
    "validate_stage2_strict",
    "validate_stage3",
    "StageComparison",
    "StageOutcome",
    "compare_stage_preferences",
    "summarize_comparisons",
    "PredictorRunState",
    "validate_and_advance",
]
