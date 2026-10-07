from __future__ import annotations

import json
from typing import Any

from predictor_policy.validator import load_policy


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def system_prompt(stage: str) -> str:
    stage = stage.upper()
    common = (
        "You are the SmartXFlow Predictor analysis worker. You are not the workflow authority. "
        "The orchestrator owns stage transitions, immutable IDs, timestamps, price provenance and final publication. "
        "Return only the requested structured fields. Never invent fields, odds, fixtures, sources or observations. "
        "All explanatory strings intended for the user must be Turkish. "
        "If evidence is missing, represent uncertainty honestly instead of fabricating support."
    )
    if stage == "STAGE1":
        return common + (
            " Stage 1 uses ONLY the trusted SmartXFlow data supplied in the request. Do not use outside football knowledge. "
            "Review every fixture's full supplied temporal path. Select only attention-worthy SXF candidates. "
            "Every selected candidate must use a native market: 1X2, O/U 2.5, or BTTS. Do not issue BET/WATCH/PASS."
        )
    if stage == "STAGE2":
        return common + (
            " Stage 2 tests the frozen Stage 1 thesis with focused external football research. "
            "Use the 3+1 packet: critical squad impact, market-relevant performance, strongest counter-case, coverage. "
            "Maximum six meaningful facts per match. UNKNOWN is not negative evidence. "
            "Keep FACT and INFERENCE separate. Do not issue BET/WATCH/PASS."
        )
    if stage == "STAGE3":
        return common + (
            " Stage 3 merges frozen Stage 1 and validated Stage 2. Determine thesis first and execution market second. "
            "DNB is forbidden. Never invent a non-native price. The orchestrator will attach trusted price evidence. "
            "Grade quality A+/A/B/C. Consider counterevidence, divergence and execution risk."
        )
    raise ValueError(f"unsupported stage: {stage!r}")


def user_prompt(
    *,
    stage: str,
    trusted_context: dict[str, Any],
    stage1_payload: dict[str, Any] | None,
    stage2_payload: dict[str, Any] | None,
    repair_violations: list[dict[str, str]] | None = None,
    previous_invalid: dict[str, Any] | None = None,
) -> str:
    stage = stage.upper()
    policy = load_policy()
    parts = [
        f"STAGE={stage}",
        "CANONICAL_POLICY=" + _json(policy),
        "TRUSTED_CONTEXT=" + _json(trusted_context),
    ]
    if stage1_payload is not None:
        parts.append("FROZEN_STAGE1=" + _json(stage1_payload))
    if stage2_payload is not None:
        parts.append("VALIDATED_STAGE2=" + _json(stage2_payload))
    if repair_violations:
        parts.append(
            "VALIDATION_REPAIR_REQUIRED="
            + _json(
                {
                    "violations": repair_violations,
                    "instruction": "Regenerate the same stage. Fix every listed rule violation without changing immutable prior-stage truth or inventing data.",
                }
            )
        )
    if previous_invalid is not None:
        parts.append("PREVIOUS_INVALID_OUTPUT=" + _json(previous_invalid))
    return "\n".join(parts)
