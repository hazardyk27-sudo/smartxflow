from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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


def _norm_market(value: Any) -> str:
    raw = str(value or "").upper().strip()
    raw = re.sub(r"[\s_\-/]+", "", raw)
    aliases = {
        "OU25": "OU2.5",
        "OVERUNDER25": "OU2.5",
        "OVERUNDER2.5": "OU2.5",
        "BOTHTEAMSTOSCORE": "BTTS",
        "MATCHODDS": "1X2",
        "FULLTIMERESULT": "1X2",
    }
    return aliases.get(raw, str(value or "").upper().strip())


def _is_dnb(market: Any, selection: Any) -> bool:
    joined = f"{market or ''} {selection or ''}".lower()
    compact = re.sub(r"[^a-z0-9]+", "", joined)
    return "drawnobet" in compact or re.search(r"(?:^|\W)dnb(?:$|\W)", joined) is not None


def _parse_iso(value: Any) -> bool:
    if not _nonempty(value):
        return False
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _fixture_id(match: dict[str, Any]) -> str:
    return str(match.get("fixture_uid") or match.get("match_id_hash") or match.get("fixture_id") or "").strip()


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
    if str(payload.get("stage") or "").upper() != "STAGE1":
        violations.append(Violation("SXF-WF-001", "payload.stage must be STAGE1"))

    if payload.get("external_research_used") is True:
        violations.append(Violation("SXF-S1-001", "external research is forbidden in Stage 1"))

    if str(payload.get("decision") or "").upper() in _FINAL_ACTIONS:
        violations.append(Violation("SXF-S1-008", "Stage 1 may not issue BET/WATCH/PASS"))

    scope = payload.get("scope") or {}
    scanned = list(scope.get("screened_fixture_ids") or [])
    source = list(scope.get("source_fixture_ids") or [])
    matches = list(payload.get("matches") or [])
    reported = [_fixture_id(item) for item in matches if isinstance(item, dict)]

    if source and set(scanned) != set(source):
        violations.append(Violation("SXF-S1-002", "every valid fixture in the user-defined source universe must be screened internally"))
    if scanned and any(match_id not in set(scanned) for match_id in reported if match_id):
        violations.append(Violation("SXF-S1-003", "reported candidate is not part of the screened source universe"))

    seen: set[str] = set()
    for index, match in enumerate(matches):
        if not isinstance(match, dict):
            violations.append(Violation("SXF-S1-003", f"matches[{index}] must be an object"))
            continue
        match_id = _fixture_id(match)
        if match_id:
            if match_id in seen:
                violations.append(Violation("SXF-S1-003", f"duplicate reported candidate: {match_id}"))
            seen.add(match_id)
        screening = match.get("screening") or {}
        if screening.get("selected") is not True:
            violations.append(Violation("SXF-S1-003", f"reported Stage 1 row {match_id or index} must be selected=true"))
        reasons = screening.get("attention_reasons") or []
        if not isinstance(reasons, list) or not any(_nonempty(item) for item in reasons):
            violations.append(Violation("SXF-S1-007", f"reported Stage 1 row {match_id or index} needs at least one attention reason"))
        violations.extend(_validate_visible_preference(match, rule_id="SXF-S1-004"))
        preference = match.get("preference") or match.get("sxf_preference") or {}
        if isinstance(preference, dict) and _nonempty(preference.get("market")):
            if _norm_market(preference.get("market")) not in _NATIVE_MARKETS:
                violations.append(Violation("SXF-S1-005", f"Stage 1 preference market must be native: {preference.get('market')!r}"))
        if _is_dnb(preference.get("market"), preference.get("selection")):
            violations.append(Violation("SXF-S3-006", "DNB is forbidden"))

    return ValidationResult(not violations, tuple(violations))


def validate_stage2(payload: dict[str, Any]) -> ValidationResult:
    violations: list[Violation] = []
    if str(payload.get("stage") or "").upper() != "STAGE2":
        violations.append(Violation("SXF-WF-001", "payload.stage must be STAGE2"))
    if payload.get("authorized_by_user") is not True:
        violations.append(Violation("SXF-S2-001", "Stage 2 requires explicit user authorization"))
    if str(payload.get("decision") or "").upper() in _FINAL_ACTIONS:
        violations.append(Violation("SXF-S2-007", "Stage 2 may not issue BET/WATCH/PASS"))

    expected = set(payload.get("stage1_candidate_ids") or [])
    matches = list(payload.get("matches") or [])
    actual = {_fixture_id(item) for item in matches if isinstance(item, dict) and _fixture_id(item)}
    if expected and actual != expected:
        violations.append(Violation("SXF-S2-002", "Stage 2 must carry the exact Stage 1 candidate set unless the user explicitly changes it"))

    for index, match in enumerate(matches):
        if not isinstance(match, dict):
            violations.append(Violation("SXF-S2-002", f"matches[{index}] must be an object"))
            continue
        match_id = _fixture_id(match) or str(index)
        frozen = match.get("frozen_stage1_preference") or {}
        if not isinstance(frozen, dict) or not _nonempty(frozen.get("market")) or not _nonempty(frozen.get("selection")):
            violations.append(Violation("SXF-S2-003", f"{match_id}: frozen Stage 1 preference is required"))
        facts = match.get("facts") or []
        if not isinstance(facts, list):
            violations.append(Violation("SXF-S2-004", f"{match_id}: facts must be a list"))
            facts = []
        if len(facts) > 6:
            violations.append(Violation("SXF-S2-004", f"{match_id}: {len(facts)} meaningful facts exceeds maximum 6"))
        counter = match.get("research_counter")
        if not _nonempty(counter):
            violations.append(Violation("SXF-S2-005", f"{match_id}: strongest counter-case is required"))
        coverage = str(match.get("coverage") or "").upper()
        if coverage not in {"HIGH", "MEDIUM", "LOW"}:
            violations.append(Violation("SXF-S2-005", f"{match_id}: coverage must be HIGH/MEDIUM/LOW"))
        verdict = str(match.get("verdict") or "").upper()
        if verdict not in {"CONFIRMED", "PARTIALLY_CONFIRMED", "CONTRADICTED", "UNEXPLAINED"}:
            violations.append(Violation("SXF-S2-005", f"{match_id}: invalid Stage 2 verdict"))
        for fact_index, fact in enumerate(facts):
            if not isinstance(fact, dict):
                violations.append(Violation("SXF-S2-008", f"{match_id}: facts[{fact_index}] must be an object"))
                continue
            relationship = str(fact.get("relationship") or "").upper()
            if relationship not in {"SUPPORTS", "CONTRADICTS", "NEUTRAL"}:
                violations.append(Violation("SXF-S2-008", f"{match_id}: fact relationship must be SUPPORTS/CONTRADICTS/NEUTRAL"))
            kind = str(fact.get("kind") or "").upper()
            if kind not in {"FACT", "INFERENCE"}:
                violations.append(Violation("SXF-S2-008", f"{match_id}: fact kind must be FACT or INFERENCE"))

    return ValidationResult(not violations, tuple(violations))


def validate_price_evidence(preference: dict[str, Any], price_evidence: dict[str, Any] | None, *, decision: str) -> list[Violation]:
    violations: list[Violation] = []
    market = preference.get("market")
    selection = preference.get("selection")
    if _is_dnb(market, selection):
        violations.append(Violation("SXF-S3-006", "DNB is forbidden"))
        return violations

    native = _norm_market(market) in _NATIVE_MARKETS
    if price_evidence is None:
        if decision == "BET" and not native:
            violations.append(Violation("SXF-PRICE-005", "formal non-native BET requires actual observed execution price evidence"))
        return violations
    if not isinstance(price_evidence, dict):
        return [Violation("SXF-PRICE-001", "price_evidence must be an object")]

    origin = str(price_evidence.get("origin") or "").upper()
    if origin not in _ALLOWED_PRICE_ORIGINS:
        violations.append(Violation("SXF-PRICE-001", f"invalid price origin: {origin!r}"))
        return violations

    if origin == "THRESHOLD_ONLY":
        if decision == "BET":
            violations.append(Violation("SXF-PRICE-005", "threshold-only non-native price cannot be treated as an executed/priced BET"))
        threshold = price_evidence.get("minimum_acceptable_price")
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or threshold <= 1:
            violations.append(Violation("SXF-PRICE-005", "THRESHOLD_ONLY requires minimum_acceptable_price > 1"))
        return violations

    price = price_evidence.get("price")
    if not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 1:
        violations.append(Violation("SXF-PRICE-001", "actual observed price must be numeric and > 1"))
    if not _parse_iso(price_evidence.get("observed_at")):
        violations.append(Violation("SXF-PRICE-002", "actual observed price requires timezone-aware observed_at"))

    if origin == "USER_SUPPLIED":
        if str(price_evidence.get("market") or "").strip() != str(market or "").strip():
            violations.append(Violation("SXF-PRICE-003", "USER_SUPPLIED market must exactly match the execution preference market"))
        if str(price_evidence.get("selection") or "").strip() != str(selection or "").strip():
            violations.append(Violation("SXF-PRICE-003", "USER_SUPPLIED selection must exactly match the execution preference selection"))
        if str(price_evidence.get("status") or "OBSERVED").upper() not in {"OBSERVED", "STALE", "NEEDS_CONFIRMATION"}:
            violations.append(Violation("SXF-PRICE-004", "invalid USER_SUPPLIED price status"))
        if str(price_evidence.get("status") or "OBSERVED").upper() != "OBSERVED" and decision == "BET":
            violations.append(Violation("SXF-PRICE-004", "stale/ambiguous USER_SUPPLIED price cannot support formal BET"))

    return violations


def validate_stage3(payload: dict[str, Any]) -> ValidationResult:
    violations: list[Violation] = []
    if str(payload.get("stage") or "").upper() != "STAGE3":
        violations.append(Violation("SXF-WF-001", "payload.stage must be STAGE3"))
    if payload.get("authorized_by_user") is not True:
        violations.append(Violation("SXF-S3-001", "Stage 3 requires explicit user authorization"))

    expected = set(payload.get("stage1_candidate_ids") or [])
    matches = list(payload.get("matches") or [])
    actual = {_fixture_id(item) for item in matches if isinstance(item, dict) and _fixture_id(item)}
    if expected and actual != expected:
        violations.append(Violation("SXF-S1-009", "Stage 3 must carry the Stage 1 candidate set unless the user changes it"))

    for index, match in enumerate(matches):
        if not isinstance(match, dict):
            violations.append(Violation("SXF-S3-007", f"matches[{index}] must be an object"))
            continue
        match_id = _fixture_id(match) or str(index)
        violations.extend(_validate_visible_preference(match, rule_id="SXF-S3-010"))
        preference = match.get("preference") or {}
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
                expected_final = raw + _COUNTER_PENALTY[severity]
                if abs(float(final) - float(expected_final)) > 1e-9:
                    violations.append(Violation("SXF-S3-003", f"{match_id}: final confidence must apply {severity} penalty {_COUNTER_PENALTY[severity]}"))
            else:
                violations.append(Violation("SXF-S3-003", f"{match_id}: raw_confidence and final_confidence are required numeric fields"))

        divergence = str(match.get("divergence_state") or "").upper()
        if divergence not in {"CONFIRMED", "MIXED", "ADVERSE", "MATERIAL_REVERSAL"}:
            violations.append(Violation("SXF-S3-004", f"{match_id}: invalid divergence_state"))
        if divergence == "MATERIAL_REVERSAL" and grade in {"A+", "A"} and match.get("material_reversal_explained") is not True:
            violations.append(Violation("SXF-S3-004", f"{match_id}: unexplained MATERIAL_REVERSAL cannot receive A+/A"))

        execution_type = str(match.get("execution_type") or "").upper()
        if execution_type not in {"NATIVE", "PROTECTION", "AGGRESSION"}:
            violations.append(Violation("SXF-S3-005", f"{match_id}: execution_type must be NATIVE/PROTECTION/AGGRESSION"))

        if not _parse_iso(match.get("prediction_at")):
            violations.append(Violation("SXF-ARCH-002", f"{match_id}: timezone-aware prediction_at is required"))

        archive_intent = match.get("archive_intent")
        expected_archive = decision in {"BET", "WATCH"}
        if archive_intent is not None and bool(archive_intent) != expected_archive:
            violations.append(Violation("SXF-ARCH-001", f"{match_id}: archive_intent must be {expected_archive} for {decision}"))

        baseline = match.get("stage1_baseline") or {}
        if not isinstance(baseline, dict) or not _nonempty(baseline.get("market")) or not _nonempty(baseline.get("selection")):
            violations.append(Violation("SXF-PERF-001", f"{match_id}: frozen stage1_baseline market/selection is required for later comparison"))

        violations.extend(validate_price_evidence(preference, match.get("price_evidence"), decision=decision))

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
    market: str,
    selection: str,
    price: float,
    observed_at: str,
    status: str = "OBSERVED",
) -> dict[str, Any]:
    evidence = {
        "origin": "USER_SUPPLIED",
        "source": "USER_SUPPLIED",
        "market": market,
        "selection": selection,
        "price": price,
        "observed_at": observed_at,
        "status": status.upper(),
    }
    violations = validate_price_evidence({"market": market, "selection": selection}, evidence, decision="WATCH")
    if violations:
        rendered = "; ".join(f"{item.rule_id}: {item.message}" for item in violations)
        raise PredictorPolicyError(rendered)
    return evidence


def format_violations(violations: Iterable[Violation]) -> str:
    return "\n".join(f"{item.rule_id}: {item.message}" for item in violations)
