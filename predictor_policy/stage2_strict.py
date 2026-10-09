from __future__ import annotations

from copy import deepcopy
from typing import Any

from .stage2_quality import validate_stage2_quality
from .validator import ValidationResult, Violation, validate_stage2 as _legacy_validate_stage2


def _legacy_compatible_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Feed legacy invariant checks without restoring boolean-trust semantics.

    The old validator still expects four boolean check markers. The strict Stage 2
    schema replaces those markers with evidence-backed check objects. This adapter
    derives the legacy markers from the presence of those structured checks so the
    old carry-forward/auth/budget/verdict invariants remain active while the strict
    validator decides whether the checks are genuinely supported by evidence.
    """
    value = deepcopy(payload)
    for match in value.get("matches") or []:
        if not isinstance(match, dict):
            continue
        checks = match.get("research_checks")
        if not isinstance(checks, dict):
            checks = {}
            match["research_checks"] = checks
        checks["squad_checked"] = isinstance(checks.get("squad"), dict)
        checks["performance_checked"] = isinstance(checks.get("performance"), dict)
        checks["counter_checked"] = isinstance(checks.get("counter"), dict)
        checks["coverage_classified"] = str(match.get("coverage") or "").upper() in {"HIGH", "MEDIUM", "LOW"}
    return value


def _source_timestamp_violations(payload: dict[str, Any]) -> list[Violation]:
    violations: list[Violation] = []
    for match_index, match in enumerate(payload.get("matches") or []):
        if not isinstance(match, dict):
            continue
        match_id = str(match.get("fixture_id") or match.get("fixture_uid") or match.get("match_id_hash") or match_index)
        for fact_index, fact in enumerate(match.get("facts") or []):
            if not isinstance(fact, dict) or str(fact.get("kind") or "").upper() != "FACT":
                continue
            fact_id = str(fact.get("fact_id") or fact_index)
            if not isinstance(fact.get("source"), str) or not fact["source"].strip():
                violations.append(Violation("SXF-S2-009", f"{match_id}: FACT {fact_id} requires source"))
            if not isinstance(fact.get("observed_at"), str) or not fact["observed_at"].strip():
                violations.append(Violation("SXF-S2-012", f"{match_id}: FACT {fact_id} requires observed_at"))
            if not isinstance(fact.get("evidence_at"), str) or not fact["evidence_at"].strip():
                violations.append(Violation("SXF-S2-012", f"{match_id}: FACT {fact_id} requires evidence_at"))
    return violations


def _two_sided_evidence_violations(payload: dict[str, Any]) -> list[Violation]:
    """Meaningful coverage must actively test both sides of the frozen thesis.

    LOW/UNKNOWN research is deliberately allowed to stay unresolved; forcing a
    fabricated supporting or contradicting fact in an obscure competition would
    violate the UNKNOWN-is-not-negative rule. MEDIUM/HIGH claims, however, must
    prove that both support and disconfirmation were actually found and cited.
    """
    violations: list[Violation] = []
    for index, match in enumerate(payload.get("matches") or []):
        if not isinstance(match, dict):
            continue
        coverage = str(match.get("coverage") or "").upper()
        if coverage not in {"MEDIUM", "HIGH"}:
            continue
        match_id = str(match.get("fixture_id") or match.get("fixture_uid") or match.get("match_id_hash") or index)
        support_ids = [str(item).strip() for item in match.get("support_fact_ids") or [] if str(item).strip()]
        counter_ids = [str(item).strip() for item in match.get("counter_fact_ids") or [] if str(item).strip()]
        if not support_ids:
            violations.append(Violation("SXF-S2-013", f"{match_id}: {coverage} coverage requires at least one real supporting FACT"))
        if not counter_ids:
            violations.append(Violation("SXF-S2-013", f"{match_id}: {coverage} coverage requires at least one real contradicting FACT"))
    return violations


def validate_stage2_strict(payload: dict[str, Any]) -> ValidationResult:
    legacy = _legacy_validate_stage2(_legacy_compatible_payload(payload))
    violations = list(legacy.violations)
    violations.extend(_source_timestamp_violations(payload))
    violations.extend(_two_sided_evidence_violations(payload))
    violations.extend(validate_stage2_quality(payload))

    # Keep repair output useful: identical rule/message pairs can arise when the
    # direct guardrail and deep evidence validator catch the same deficiency.
    unique: list[Violation] = []
    seen: set[tuple[str, str]] = set()
    for item in violations:
        key = (item.rule_id, item.message)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return ValidationResult(not unique, tuple(unique))
