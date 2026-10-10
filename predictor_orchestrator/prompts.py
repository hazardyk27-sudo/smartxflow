from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from predictor_policy.validator import load_policy


_STAGE2_PROTOCOL_PATH = Path(__file__).resolve().parents[1] / ".agents" / "predictor" / "STAGE2_FOCUSED_RESEARCH.md"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_stage2_protocol() -> str:
    try:
        text = _STAGE2_PROTOCOL_PATH.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"Stage 2 research protocol is unavailable: {_STAGE2_PROTOCOL_PATH}") from exc
    if not text:
        raise RuntimeError("Stage 2 research protocol is empty")
    return text


def system_prompt(stage: str) -> str:
    stage = stage.upper()
    common = (
        "You are the SmartXFlow Predictor analysis worker. You are not the workflow authority. "
        "The orchestrator owns stage transitions, immutable IDs, timestamps, price provenance and final publication. "
        "Return only the requested structured fields. Never invent fields, odds, fixtures, sources, observations or statistics. "
        "All explanatory strings intended for the user must be Turkish. "
        "If evidence is missing, represent uncertainty honestly instead of fabricating support."
    )
    if stage == "STAGE1":
        return common + (
            " Stage 1 uses ONLY the trusted SmartXFlow data supplied in the request. Do not use outside football knowledge. "
            "Review every fixture's full supplied temporal path. Explicitly compare the available first/open, h24, h12, h6, h3, h1, m30, m15 and latest checkpoints; a missing checkpoint is null and must never be synthesized from another point. "
            "For every selected candidate, the rationale must explicitly explain which observed odds, money amount, money/share movement, velocity, liquidity/volume, reversal and cross-market behavior made the match noteworthy. Avoid vague labels such as 'strong money' unless the supplied numeric path actually demonstrates it. "
            "LIQUIDITY GUARDRAIL: total selected-market volume below 5,000 is NOT an automatic DROP, but it is LOW liquidity and can never be described as strong evidence; 5,000-9,999 is LIMITED and remains low-confidence even when other evidence is interesting; 10,000-24,999 is NORMAL; 25,000+ is STRONG liquidity, but strong liquidity alone is not a selection signal. "
            "MONEY-SHARE GUARDRAIL: money share and share change are context only. Extreme share, 90%+ concentration or a large share jump may never by themselves create a Stage 1 candidate. Absolute selection money and market liquidity determine evidence weight, while price response, persistence, reversal, velocity and cross-market behavior determine whether the concentration is informative. "
            "UNDERDOG GUARDRAIL: for a 1X2 Home/Away selection priced 2.90 or higher, a price contraction or underdog-pressure pattern may become a frozen Stage 1 preference only when trusted evidence shows at least 10,000 total 1X2 market volume, at least 5,000 absolute money on that selected side, and a persistent price move across the available temporal path. Otherwise treat it only as LOW_CONFIDENCE_MARKET_MOVE and do not select it as a Stage 1 candidate. Draw and non-1X2 markets are not classified as underdogs by this rule. "
            "The formal renderer will attach the exact server-owned SXF evidence packet, so your explanation must stay consistent with those trusted numbers. "
            "Select only attention-worthy SXF candidates. Every selected candidate must use a native market: 1X2, O/U 2.5, or BTTS. Do not issue BET/WATCH/PASS."
        )
    if stage == "STAGE2":
        return common + (
            " Stage 2 is an evidence-backed adversarial test of the frozen Stage 1 thesis, not an independent pick generator. "
            "The full canonical Stage 2 research protocol is included in the user prompt and is mandatory. Follow its source order, market-specific questions, source-quality rules, freshness rules, H2H limits and 3+1 structure. "
            "Every FACT must have a real URL, a correctly classified source tier, observed_at, evidence_at and a stable fact_id. "
            "Every FACT or INFERENCE must explain WHY IT MATTERS through importance_reason; do not merely state a news item. "
            "When a performance check is VERIFIED, include at least one source-backed quantitative_context metric with metric, numeric value, unit and sample. Never invent xG, minutes, starts, goals or any other number. "
            "Every match must contain absence_assessment. If a material absence is identified, state who/what is absent, role, availability, LOW/MEDIUM/HIGH/CRITICAL importance, direction versus the frozen Stage 1 thesis, evidence fact_ids and a concrete importance reason. If the importance cannot be established, use UNKNOWN rather than guessing. "
            "Research checks must cite fact_ids; never claim a check was completed with a boolean or unsupported assertion. "
            "For MEDIUM/HIGH coverage, use enough independent evidence to support both the main case and the strongest counter-case. "
            "Maximum six meaningful facts per match. UNKNOWN is not negative evidence. Keep FACT and INFERENCE separate. "
            "Do not create a new Stage 2 betting preference and do not issue BET/WATCH/PASS."
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
    ]
    if stage == "STAGE2":
        parts.append("STAGE2_RESEARCH_PROTOCOL_BEGIN\n" + load_stage2_protocol() + "\nSTAGE2_RESEARCH_PROTOCOL_END")
    parts.append("TRUSTED_CONTEXT=" + _json(trusted_context))
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
