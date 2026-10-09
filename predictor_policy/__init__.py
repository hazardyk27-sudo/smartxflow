from .validator import (
    PredictorPolicyError,
    ValidationResult,
    Violation,
    format_violations,
    load_policy,
    user_supplied_price_evidence,
    validate_payload as _validate_payload_base,
    validate_stage1,
    validate_stage2 as _validate_stage2_base,
    validate_stage3,
)
from .stage2_quality import validate_stage2_quality
from .stage_comparison import (
    StageComparison,
    StageOutcome,
    compare_stage_preferences,
    summarize_comparisons,
)
from .runtime import PredictorRunState, validate_and_advance


def validate_stage2(payload):
    base = _validate_stage2_base(payload)
    violations = list(base.violations)
    violations.extend(validate_stage2_quality(payload))
    return ValidationResult(not violations, tuple(violations))


def validate_payload(payload):
    base = _validate_payload_base(payload)
    if str(payload.get("stage") or "").upper() != "STAGE2":
        return base
    violations = list(base.violations)
    violations.extend(validate_stage2_quality(payload))
    return ValidationResult(not violations, tuple(violations))


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
    "validate_stage3",
    "StageComparison",
    "StageOutcome",
    "compare_stage_preferences",
    "summarize_comparisons",
    "PredictorRunState",
    "validate_and_advance",
]
