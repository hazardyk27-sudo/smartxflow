from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import re
from typing import Any, Iterable


_POLICY_PATH = Path(__file__).with_name("policy.json")
_NATIVE_MARKETS = {"1X2", "OU2.5", "BTTS"}
_FINAL_ACTIONS = {"BET", "WATCH", "PASS"}
_GRADE_ACTION = {"A+": "BET", "A": "BET", "B": "WATCH", "C": "PASS"}
_COUNTER_PENALTY = {"NONE": 0, "LIGHT": -3, "MEDIUM": -7, "STRONG": -12, "STRUCTURAL": -20}
_ALLOWED_PRICE_ORIGINS = {"SXF_NATIVE", "EXTERNAL_VERIFIED", "USER_SUPPLIED", "THRESHOLD_ONLY"}
_ALLOWED_ATTENTION_SIGNALS = {
    "MONEY_ACCELERATION",
    "PRICE_CONFIRMATION",
    "PRICE_RESISTANCE",
    "DIVERGENCE",
    "REVERSAL",
    "PERSISTENCE",
    "LIQUIDITY_ADJUSTED_MOVE",
    "CROSS_MARKET_CONFIRMATION",
    "CROSS_MARKET_CONFLICT",
    "LATE_MOVE",
    "SATURATION",
    "OTHER",
}
_ALLOWED_STAGE2_VERDICTS = {"CONFIRMED", "PARTIALLY_CONFIRMED", "CONTRADICTED", "UNEXPLAINED"}
_ALLOWED_COVERAGE = {"HIGH", "MEDIUM", "LOW"}
_ALLOWED_RELATIONSHIPS = {"SUPPORTS", "CONTRADICTS", "NEUTRAL"}
_ALLOWED_FACT_KINDS = {"FACT", "INFERENCE"}
_ALLOWED_DIVERGENCE = {"CONFIRMED", "MIXED", "ADVERSE", "MATERIAL_REVERSAL"}
_ALLOWED_EXECUTION_TYPES = {"NATIVE", "PROTECTION", "AGGRESSION"}
_ALLOWED_CHANGE_DRIVERS = {"NONE", "STAGE2_RESEARCH", "EXECUTION_OPTIMIZATION", "MARKET_UPDATE", "BOTH"}


class PredictorPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class Violation:
    rule_id: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    violations: tuple[Violation, ...]

    def raise_for_errors(self) -> None:
        if self.valid:
            return
        rendered = "; ".join(f"{item.rule_id}: {item.message}" for item in self.violations)
        raise PredictorPolicyError(rendered)


def load_policy() -> dict[str, Any]:
    with _POLICY_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _canonical_market(value: Any) -> str:
    raw = str(value or "").upper().strip()
    compact = re.sub(r"[^A-Z0-9]+", "", raw)
    aliases = {
        "1X2": "1X2",
        "MATCHODDS": "1X2",
        "FULLTIMERESULT": "1X2",
        "OU25": "OU2.5",
        "OVERUNDER25": "OU2.5",
        "BTTS": "BTTS",
        "BOTHTEAMSTOSCORE": "BTTS",
        "KG": "BTTS",
    }
    return aliases.get(compact, raw)


def _is_native_market(value: Any) -> bool:
    return _canonical_market(value) in _NATIVE_MARKETS


def _is_dnb(market: Any, selection: Any) -> bool:
    joined = f"{market or ''} {selection or ''}".lower()
    compact = re.sub(r"[^a-z0-9]+", "", joined)
    return "drawnobet" in compact or re.search(r"(?:^|\W)dnb(?:$|\W)", joined) is not None


def _parse_iso(value: Any) -> datetime | None:
    if not _nonempty(value):
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _fixture_id(match: dict[str, Any]) -> str:
    return str(match.get("fixture_uid") or match.get("match_id_hash") or match.get("fixture_id") or "").strip()


def _id_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _validate_run_id(payload: dict[str, Any]) -> list[Violation]:
    if not _nonempty(payload.get("run_id")):
        return [Violation("SXF-WF-005", "run_id is required")]
    return []


def _active_candidate_ids(payload: dict[str, Any], *, rule_id: str) -> tuple[set[str], list[Violation]]:
    violations: list[Violation] = []
    if "stage1_candidate_ids" not in payload:
        return set(), [Violation(rule_id, "stage1_candidate_ids must be present, including an explicit empty list when Stage 1 selected no candidates")]
    original = set(_id_list(payload.get("stage1_candidate_ids")))
    if "user_scope_override_ids" not in payload:
        return original, violations
    if payload.get("scope_change_authorized_by_user") is not True:
        violations.append(Violation(rule_id, "user_scope_override_ids requires scope_change_authorized_by_user=true"))
    return set(_id_list(payload.get("user_scope_override_ids"))), violations


def _validate_visible_preference(match: dict[str, Any], *, rule_id: str) -> list[Violation]:
    violations: list[Violation] = []
    preference = match.get("preference") or match.get("sxf_preference") or {}
    if not isinstance(preference, dict):
        return [Violation(rule_id, "preference must be an object")]
    if not _nonempty(preference.get("market")):
        violations.append(Violation(rule_id, "visible match is missing preference.market"))
    if not _nonempty(preference.get("selection")):
        violations.append(Violation(rule_id, "visible match is missing preference.selection"))
    return violations


def validate_stage1(payload: dict[str, Any]) -> ValidationResult:
    violations: list[Violation] = []
    violations.extend(_validate_run_id(payload))
    if str(payload.get("stage") or "").upper() != "STAGE1":
        violations.append(Violation("SXF-WF-001", "payload.stage must be STAGE1"))
    if payload.get("external_research_used") is True:
        violations.append(Violation("SXF-S1-001", "external research is forbidden in Stage 1"))
    if str(payload.get("decision") or "").upper() in _FINAL_ACTIONS:
        violations.append(Violation("SXF-S1-008", "Stage 1 may not issue BET/WATCH/PASS"))

    scope = payload.get("scope")
    if not isinstance(scope, dict) or scope.get("universe_resolved") is not True:
        violations.append(Violation("SXF-S1-002", "scope.universe_resolved=true is required before Stage 1 can pass"))
        scope = scope if isinstance(scope, dict) else {}

    source_ids = _id_list(scope.get("source_fixture_ids"))
    if "source_fixture_ids" not in scope or not isinstance(scope.get("source_fixture_ids"), list):
        violations.append(Violation("SXF-S1-002", "scope.source_fixture_ids must be an explicit list, including [] for a resolved empty universe"))

    screening_results = payload.get("screening_results")
    if not isinstance(screening_results, list):
        violations.append(Violation("SXF-S1-002", "screening_results must be a list containing one result for every source fixture"))
        screening_results = []

    screening_ids: list[str] = []
    selected_ids: set[str] = set()
    for index, row in enumerate(screening_results):
        if not isinstance(row, dict):
            violations.append(Violation("SXF-S1-002", f"screening_results[{index}] must be an object"))
            continue
        fixture_id = _fixture_id(row)
        if not fixture_id:
            violations.append(Violation("SXF-S1-002", f"screening_results[{index}] requires fixture identity"))
            continue
        screening_ids.append(fixture_id)
        if row.get("temporal_reviewed") is not True:
            violations.append(Violation("SXF-S1-006", f"{fixture_id}: temporal_reviewed=true is required"))
        selected = row.get("selected")
        if not isinstance(selected, bool):
            violations.append(Violation("SXF-S1-002", f"{fixture_id}: selected must be boolean"))
            continue
        if selected:
            selected_ids.add(fixture_id)
            signals = row.get("attention_signals")
            if not isinstance(signals, list) or not signals:
                violations.append(Violation("SXF-S1-007", f"{fixture_id}: selected candidate requires at least one structured attention signal"))
                signals = []
            normalized = {str(item or "").upper() for item in signals}
            unknown = normalized - _ALLOWED_ATTENTION_SIGNALS
            if unknown:
                violations.append(Violation("SXF-S1-007", f"{fixture_id}: unsupported attention signal(s): {sorted(unknown)}"))
            if "OTHER" in normalized and not _nonempty(row.get("attention_explanation")):
                violations.append(Violation("SXF-S1-007", f"{fixture_id}: OTHER attention signal requires attention_explanation"))

    if len(screening_ids) != len(set(screening_ids)):
        violations.append(Violation("SXF-S1-002", "screening_results contains duplicate fixture identities"))
    if set(screening_ids) != set(source_ids):
        violations.append(Violation("SXF-S1-002", "screening_results must cover the full resolved source universe exactly"))

    matches = payload.get("matches")
    if not isinstance(matches, list):
        violations.append(Violation("SXF-S1-003", "matches must be a list"))
        matches = []
    reported_ids: list[str] = []
    for index, match in enumerate(matches):
        if not isinstance(match, dict):
            violations.append(Violation("SXF-S1-003", f"matches[{index}] must be an object"))
            continue
        match_id = _fixture_id(match)
        if not match_id:
            violations.append(Violation("SXF-S1-003", f"matches[{index}] requires fixture identity"))
            continue
        reported_ids.append(match_id)
        if str(match.get("decision") or "").upper() in _FINAL_ACTIONS:
            violations.append(Violation("SXF-S1-008", f"{match_id}: Stage 1 row may not issue BET/WATCH/PASS"))
        violations.extend(_validate_visible_preference(match, rule_id="SXF-S1-004"))
        preference = match.get("preference") or match.get("sxf_preference") or {}
        if isinstance(preference, dict) and _nonempty(preference.get("market")) and not _is_native_market(preference.get("market")):
            violations.append(Violation("SXF-S1-005", f"{match_id}: Stage 1 preference market must be native: {preference.get('market')!r}"))
        if isinstance(preference, dict) and _is_dnb(preference.get("market"), preference.get("selection")):
            violations.append(Violation("SXF-S3-006", f"{match_id}: DNB is forbidden"))

    if len(reported_ids) != len(set(reported_ids)):
        violations.append(Violation("SXF-S1-003", "matches contains duplicate reported candidates"))
    if set(reported_ids) != selected_ids:
        violations.append(Violation("SXF-S1-003", "user-facing Stage 1 matches must exactly equal internally selected screening candidates"))

    return ValidationResult(not violations, tuple(violations))


def validate_stage2(payload: dict[str, Any]) -> ValidationResult:
    violations: list[Violation] = []
    violations.extend(_validate_run_id(payload))
    if str(payload.get("stage") or "").upper() != "STAGE2":
        violations.append(Violation("SXF-WF-001", "payload.stage must be STAGE2"))
    if payload.get("authorized_by_user") is not True:
        violations.append(Violation("SXF-S2-001", "Stage 2 requires explicit user authorization"))
    if not _nonempty(payload.get("predecessor_stage1_run_id")):
        violations.append(Violation("SXF-S2-001", "predecessor_stage1_run_id is required"))
    if str(payload.get("decision") or "").upper() in _FINAL_ACTIONS:
        violations.append(Violation("SXF-S2-007", "Stage 2 may not issue BET/WATCH/PASS"))

    expected, carry_violations = _active_candidate_ids(payload, rule_id="SXF-S2-002")
    violations.extend(carry_violations)
    matches = payload.get("matches")
    if not isinstance(matches, list):
        violations.append(Violation("SXF-S2-002", "matches must be a list"))
        matches = []
    actual = {_fixture_id(item) for item in matches if isinstance(item, dict) and _fixture_id(item)}
    if actual != expected:
        violations.append(Violation("SXF-S2-002", "Stage 2 must carry the active Stage 1 candidate set exactly"))

    for index, match in enumerate(matches):
        if not isinstance(match, dict):
            violations.append(Violation("SXF-S2-002", f"matches[{index}] must be an object"))
            continue
        match_id = _fixture_id(match) or str(index)
        if str(match.get("decision") or "").upper() in _FINAL_ACTIONS:
            violations.append(Violation("SXF-S2-007", f"{match_id}: Stage 2 row may not issue BET/WATCH/PASS"))
        frozen = match.get("frozen_stage1_preference") or {}
        if not isinstance(frozen, dict) or not _nonempty(frozen.get("market")) or not _nonempty(frozen.get("selection")):
            violations.append(Violation("SXF-S2-003", f"{match_id}: frozen Stage 1 preference is required"))
        elif not _is_native_market(frozen.get("market")):
            violations.append(Violation("SXF-S2-003", f"{match_id}: frozen Stage 1 preference must remain native"))

        checks = match.get("research_checks")
        if not isinstance(checks, dict):
            violations.append(Violation("SXF-S2-005", f"{match_id}: research_checks object is required"))
            checks = {}
        for key in ("squad_checked", "performance_checked", "counter_checked", "coverage_classified"):
            if checks.get(key) is not True:
                violations.append(Violation("SXF-S2-005", f"{match_id}: research_checks.{key}=true is required"))

        facts = match.get("facts")
        if not isinstance(facts, list):
            violations.append(Violation("SXF-S2-004", f"{match_id}: facts must be a list"))
            facts = []
        if len(facts) > 6:
            violations.append(Violation("SXF-S2-004", f"{match_id}: {len(facts)} meaningful facts exceeds maximum 6"))
        if not _nonempty(match.get("research_support")):
            violations.append(Violation("SXF-S2-005", f"{match_id}: strongest research support is required; use an explicit UNKNOWN/NO_MATERIAL_SUPPORT statement when coverage yields no support"))
        if not _nonempty(match.get("research_counter")):
            violations.append(Violation("SXF-S2-005", f"{match_id}: strongest counter-case is required"))
        coverage = str(match.get("coverage") or "").upper()
        if coverage not in _ALLOWED_COVERAGE:
            violations.append(Violation("SXF-S2-005", f"{match_id}: coverage must be HIGH/MEDIUM/LOW"))
        verdict = str(match.get("verdict") or "").upper()
        if verdict not in _ALLOWED_STAGE2_VERDICTS:
            violations.append(Violation("SXF-S2-005", f"{match_id}: invalid Stage 2 verdict"))

        for fact_index, fact in enumerate(facts):
            if not isinstance(fact, dict):
                violations.append(Violation("SXF-S2-008", f"{match_id}: facts[{fact_index}] must be an object"))
                continue
            relationship = str(fact.get("relationship") or "").upper()
            if relationship not in _ALLOWED_RELATIONSHIPS:
                violations.append(Violation("SXF-S2-008", f"{match_id}: fact relationship must be SUPPORTS/CONTRADICTS/NEUTRAL"))
            kind = str(fact.get("kind") or "").upper()
            if kind not in _ALLOWED_FACT_KINDS:
                violations.append(Violation("SXF-S2-008", f"{match_id}: fact kind must be FACT or INFERENCE"))
            if not _nonempty(fact.get("claim")):
                violations.append(Violation("SXF-S2-008", f"{match_id}: facts[{fact_index}].claim is required"))

    return ValidationResult(not violations, tuple(violations))


def validate_price_evidence(
    preference: dict[str, Any],
    price_evidence: dict[str, Any] | None,
    *,
    decision: str,
    fixture_id: str | None = None,
) -> list[Violation]:
    violations: list[Violation] = []
    market = preference.get("market")
    selection = preference.get("selection")
    if _is_dnb(market, selection):
        return [Violation("SXF-S3-006", "DNB is forbidden")]

    native = _is_native_market(market)
    if price_evidence is None:
        if decision == "BET" and not native:
            violations.append(Violation("SXF-PRICE-005", "formal non-native BET requires actual observed execution price evidence"))
        return violations
    if not isinstance(price_evidence, dict):
        return [Violation("SXF-PRICE-001", "price_evidence must be an object")]

    origin = str(price_evidence.get("origin") or "").upper()
    if fixture_id is not None:
        evidence_fixture_id = str(price_evidence.get("fixture_id") or "").strip()
        if evidence_fixture_id != str(fixture_id).strip():
            violations.append(Violation("SXF-PRICE-006", "price evidence fixture_id must exactly match the execution fixture"))
    if origin not in _ALLOWED_PRICE_ORIGINS:
        return [Violation("SXF-PRICE-001", f"invalid price origin: {origin!r}")]
    if origin == "SXF_NATIVE" and not native:
        violations.append(Violation("SXF-PRICE-001", "SXF_NATIVE price origin cannot be attached to a non-native execution market"))

    if origin == "THRESHOLD_ONLY":
        if decision == "BET":
            violations.append(Violation("SXF-PRICE-005", "threshold-only price cannot support a formal priced BET"))
        threshold = price_evidence.get("minimum_acceptable_price")
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or threshold <= 1:
            violations.append(Violation("SXF-PRICE-005", "THRESHOLD_ONLY requires minimum_acceptable_price > 1"))
        return violations

    price = price_evidence.get("price")
    if not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 1:
        violations.append(Violation("SXF-PRICE-001", "actual observed price must be numeric and > 1"))
    if _parse_iso(price_evidence.get("observed_at")) is None:
        violations.append(Violation("SXF-PRICE-002", "actual observed price requires timezone-aware observed_at"))

    if origin == "EXTERNAL_VERIFIED" and not _nonempty(price_evidence.get("source")):
        violations.append(Violation("SXF-PRICE-001", "EXTERNAL_VERIFIED price requires source"))
    if origin == "USER_SUPPLIED":
        if str(price_evidence.get("market") or "").strip() != str(market or "").strip():
            violations.append(Violation("SXF-PRICE-003", "USER_SUPPLIED market must exactly match the execution preference market"))
        if str(price_evidence.get("selection") or "").strip() != str(selection or "").strip():
            violations.append(Violation("SXF-PRICE-003", "USER_SUPPLIED selection must exactly match the execution preference selection"))
        status = str(price_evidence.get("status") or "OBSERVED").upper()
        if status not in {"OBSERVED", "STALE", "NEEDS_CONFIRMATION"}:
            violations.append(Violation("SXF-PRICE-004", "invalid USER_SUPPLIED price status"))
        if status != "OBSERVED" and decision == "BET":
            violations.append(Violation("SXF-PRICE-004", "stale/ambiguous USER_SUPPLIED price cannot support formal BET"))

    return violations


def validate_stage3(payload: dict[str, Any]) -> ValidationResult:
    violations: list[Violation] = []
    violations.extend(_validate_run_id(payload))
    if str(payload.get("stage") or "").upper() != "STAGE3":
        violations.append(Violation("SXF-WF-001", "payload.stage must be STAGE3"))
    if payload.get("authorized_by_user") is not True:
        violations.append(Violation("SXF-S3-001", "Stage 3 requires explicit user authorization"))
    if not _nonempty(payload.get("predecessor_stage1_run_id")) or not _nonempty(payload.get("predecessor_stage2_run_id")):
        violations.append(Violation("SXF-S3-001", "predecessor_stage1_run_id and predecessor_stage2_run_id are required"))

    expected, carry_violations = _active_candidate_ids(payload, rule_id="SXF-S1-009")
    violations.extend(carry_violations)
    matches = payload.get("matches")
    if not isinstance(matches, list):
        violations.append(Violation("SXF-S1-009", "matches must be a list"))
        matches = []
    actual = {_fixture_id(item) for item in matches if isinstance(item, dict) and _fixture_id(item)}
    if actual != expected:
        violations.append(Violation("SXF-S1-009", "Stage 3 must carry the active Stage 1 candidate set exactly"))

    for index, match in enumerate(matches):
        if not isinstance(match, dict):
            violations.append(Violation("SXF-S3-007", f"matches[{index}] must be an object"))
            continue
        match_id = _fixture_id(match) or str(index)
        violations.extend(_validate_visible_preference(match, rule_id="SXF-S3-010"))
        preference = match.get("preference") or {}
        if isinstance(preference, dict) and _is_dnb(preference.get("market"), preference.get("selection")):
            violations.append(Violation("SXF-S3-006", f"{match_id}: DNB is forbidden"))

        decision = str(match.get("decision") or "").upper()
        grade = str(match.get("grade") or "").upper()
        if grade not in _GRADE_ACTION:
            violations.append(Violation("SXF-S3-007", f"{match_id}: grade must be A+/A/B/C"))
        elif decision != _GRADE_ACTION[grade]:
            violations.append(Violation("SXF-S3-008", f"{match_id}: grade {grade} requires {_GRADE_ACTION[grade]}, got {decision or '<missing>'}"))
        if decision not in _FINAL_ACTIONS:
            violations.append(Violation("SXF-S3-008", f"{match_id}: decision must be BET/WATCH/PASS"))

        severity = str(match.get("counter_severity") or "").upper()
        if severity not in _COUNTER_PENALTY:
            violations.append(Violation("SXF-S3-003", f"{match_id}: invalid counter severity"))
        else:
            raw = match.get("raw_confidence")
            final = match.get("final_confidence")
            if isinstance(raw, (int, float)) and not isinstance(raw, bool) and isinstance(final, (int, float)) and not isinstance(final, bool):
                expected_final = float(raw) + _COUNTER_PENALTY[severity]
                if abs(float(final) - expected_final) > 1e-9:
                    violations.append(Violation("SXF-S3-003", f"{match_id}: final confidence must apply {severity} penalty {_COUNTER_PENALTY[severity]}"))
            else:
                violations.append(Violation("SXF-S3-003", f"{match_id}: raw_confidence and final_confidence are required numeric fields"))

        divergence = str(match.get("divergence_state") or "").upper()
        if divergence not in _ALLOWED_DIVERGENCE:
            violations.append(Violation("SXF-S3-004", f"{match_id}: invalid divergence_state"))
        if divergence == "MATERIAL_REVERSAL" and grade in {"A+", "A"}:
            if match.get("material_reversal_explained") is not True or not _nonempty(match.get("material_reversal_explanation")):
                violations.append(Violation("SXF-S3-004", f"{match_id}: A+/A after MATERIAL_REVERSAL requires explicit verified explanation"))

        execution_type = str(match.get("execution_type") or "").upper()
        if execution_type not in _ALLOWED_EXECUTION_TYPES:
            violations.append(Violation("SXF-S3-005", f"{match_id}: execution_type must be NATIVE/PROTECTION/AGGRESSION"))
        elif isinstance(preference, dict):
            is_native = _is_native_market(preference.get("market"))
            if is_native and execution_type != "NATIVE":
                violations.append(Violation("SXF-S3-005", f"{match_id}: native execution market must use execution_type=NATIVE"))
            if not is_native and execution_type == "NATIVE":
                violations.append(Violation("SXF-S3-005", f"{match_id}: non-native execution market must use PROTECTION or AGGRESSION"))

        stage1 = match.get("stage1_baseline") or {}
        if not isinstance(stage1, dict) or not _nonempty(stage1.get("market")) or not _nonempty(stage1.get("selection")):
            violations.append(Violation("SXF-PERF-001", f"{match_id}: frozen stage1_baseline market/selection is required"))
        elif not _is_native_market(stage1.get("market")):
            violations.append(Violation("SXF-PERF-001", f"{match_id}: stage1_baseline must remain a native SXF market"))

        stage2_verdict = str(match.get("stage2_verdict") or "").upper()
        if stage2_verdict not in _ALLOWED_STAGE2_VERDICTS:
            violations.append(Violation("SXF-S3-011", f"{match_id}: valid stage2_verdict is required"))
        if not _nonempty(match.get("rationale")):
            violations.append(Violation("SXF-S3-011", f"{match_id}: rationale is required"))
        if not _nonempty(match.get("strongest_counterargument")):
            violations.append(Violation("SXF-S3-011", f"{match_id}: strongest_counterargument is required"))

        changed = False
        if isinstance(stage1, dict) and isinstance(preference, dict):
            changed = (
                _canonical_market(stage1.get("market")),
                str(stage1.get("selection") or "").strip(),
            ) != (
                _canonical_market(preference.get("market")),
                str(preference.get("selection") or "").strip(),
            )
        change_driver = str(match.get("change_driver") or "").upper()
        if change_driver not in _ALLOWED_CHANGE_DRIVERS:
            violations.append(Violation("SXF-PERF-005", f"{match_id}: change_driver must be one of {sorted(_ALLOWED_CHANGE_DRIVERS)}"))
        elif changed and change_driver == "NONE":
            violations.append(Violation("SXF-PERF-005", f"{match_id}: changed Stage 3 preference requires a non-NONE change_driver"))
        elif not changed and change_driver != "NONE":
            violations.append(Violation("SXF-PERF-005", f"{match_id}: unchanged preference requires change_driver=NONE"))

        prediction_at = _parse_iso(match.get("prediction_at"))
        recorded_at = _parse_iso(match.get("decision_recorded_at"))
        if prediction_at is None or recorded_at is None:
            violations.append(Violation("SXF-S3-012", f"{match_id}: timezone-aware prediction_at and decision_recorded_at are required"))
        elif prediction_at != recorded_at:
            violations.append(Violation("SXF-S3-012", f"{match_id}: prediction_at must equal decision_recorded_at"))

        archive_intent = match.get("archive_intent")
        expected_archive = decision in {"BET", "WATCH"}
        if not isinstance(archive_intent, bool):
            violations.append(Violation("SXF-ARCH-001", f"{match_id}: archive_intent boolean is required"))
        elif archive_intent != expected_archive:
            violations.append(Violation("SXF-ARCH-001", f"{match_id}: archive_intent must be {expected_archive} for {decision}"))

        violations.extend(validate_price_evidence(
            preference if isinstance(preference, dict) else {},
            match.get("price_evidence"),
            decision=decision,
            fixture_id=match_id,
        ))

    return ValidationResult(not violations, tuple(violations))


def validate_payload(payload: dict[str, Any]) -> ValidationResult:
    stage = str(payload.get("stage") or "").upper()
    if stage == "STAGE1":
        return validate_stage1(payload)
    if stage == "STAGE2":
        return validate_stage2(payload)
    if stage == "STAGE3":
        return validate_stage3(payload)
    return ValidationResult(False, (Violation("SXF-WF-001", f"unsupported stage: {stage or '<missing>'}"),))


def user_supplied_price_evidence(
    *,
    fixture_id: str,
    market: str,
    selection: str,
    price: float,
    observed_at: str | None = None,
    received_at: str | None = None,
    status: str = "OBSERVED",
) -> dict[str, Any]:
    effective_time = observed_at or received_at
    if effective_time is None:
        effective_time = datetime.now(timezone.utc).isoformat()
    fixture_id = str(fixture_id or "").strip()
    if not fixture_id:
        raise PredictorPolicyError("SXF-PRICE-006: USER_SUPPLIED price requires fixture_id")
    evidence = {
        "fixture_id": fixture_id,
        "origin": "USER_SUPPLIED",
        "source": "USER_SUPPLIED",
        "market": market,
        "selection": selection,
        "price": price,
        "observed_at": effective_time,
        "status": status.upper(),
    }
    violations = validate_price_evidence(
        {"market": market, "selection": selection},
        evidence,
        decision="WATCH",
        fixture_id=fixture_id,
    )
    if violations:
        rendered = "; ".join(f"{item.rule_id}: {item.message}" for item in violations)
        raise PredictorPolicyError(rendered)
    return evidence


def format_violations(violations: Iterable[Violation]) -> str:
    return "\n".join(f"{item.rule_id}: {item.message}" for item in violations)
