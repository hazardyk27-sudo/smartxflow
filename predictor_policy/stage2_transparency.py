from __future__ import annotations

from typing import Any

from .validator import Violation


_ALLOWED_ABSENCE_STATUS = {"NONE", "UNKNOWN", "IDENTIFIED"}
_ALLOWED_AVAILABILITY = {"NONE", "OUT", "DOUBTFUL", "SUSPENDED", "ROTATION_RISK", "UNKNOWN"}
_ALLOWED_IMPORTANCE = {"NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"}
_ALLOWED_EFFECT = {"SUPPORTS", "CONTRADICTS", "NEUTRAL", "UNKNOWN"}


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _valid_quant_metric(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if not _nonempty(value.get("metric")) or not _nonempty(value.get("unit")) or not _nonempty(value.get("sample")):
        return False
    metric_value = value.get("value")
    return isinstance(metric_value, (int, float)) and not isinstance(metric_value, bool)


def validate_stage2_transparency(payload: dict[str, Any]) -> tuple[Violation, ...]:
    violations: list[Violation] = []
    matches = payload.get("matches")
    if not isinstance(matches, list):
        return tuple(violations)

    for index, match in enumerate(matches):
        if not isinstance(match, dict):
            continue
        match_id = str(match.get("fixture_id") or match.get("fixture_uid") or match.get("match_id_hash") or index)
        facts = match.get("facts") if isinstance(match.get("facts"), list) else []
        fact_by_id = {
            str(fact.get("fact_id") or "").strip(): fact
            for fact in facts
            if isinstance(fact, dict) and str(fact.get("fact_id") or "").strip()
        }

        for fact_id, fact in fact_by_id.items():
            if not _nonempty(fact.get("importance_reason")):
                violations.append(
                    Violation("SXF-S2-014", f"{match_id}: FACT/INFERENCE {fact_id} requires importance_reason explaining why it matters")
                )
            quantitative = fact.get("quantitative_context")
            if not isinstance(quantitative, list):
                violations.append(Violation("SXF-S2-014", f"{match_id}: {fact_id} quantitative_context must be an explicit list"))
                continue
            if len(quantitative) > 4:
                violations.append(Violation("SXF-S2-014", f"{match_id}: {fact_id} quantitative_context exceeds maximum 4 metrics"))
            for metric_index, metric in enumerate(quantitative):
                if not _valid_quant_metric(metric):
                    violations.append(
                        Violation(
                            "SXF-S2-014",
                            f"{match_id}: {fact_id} quantitative_context[{metric_index}] requires metric, numeric value, unit and sample",
                        )
                    )

        checks = match.get("research_checks") if isinstance(match.get("research_checks"), dict) else {}
        performance = checks.get("performance") if isinstance(checks.get("performance"), dict) else {}
        if str(performance.get("status") or "").upper() == "VERIFIED":
            performance_ids = _ids(performance.get("fact_ids"))
            if not any(
                isinstance(fact_by_id.get(fid), dict)
                and str(fact_by_id[fid].get("category") or "").upper() in {"PERFORMANCE", "TACTICAL"}
                and isinstance(fact_by_id[fid].get("quantitative_context"), list)
                and any(_valid_quant_metric(metric) for metric in fact_by_id[fid]["quantitative_context"])
                for fid in performance_ids
            ):
                violations.append(
                    Violation(
                        "SXF-S2-014",
                        f"{match_id}: VERIFIED performance check requires at least one source-backed quantitative metric",
                    )
                )

        assessment = match.get("absence_assessment")
        if not isinstance(assessment, dict):
            violations.append(Violation("SXF-S2-014", f"{match_id}: absence_assessment object is required"))
            continue

        status = str(assessment.get("status") or "").upper()
        availability = str(assessment.get("availability") or "").upper()
        importance = str(assessment.get("importance") or "").upper()
        thesis_effect = str(assessment.get("thesis_effect") or "").upper()
        fact_ids = _ids(assessment.get("fact_ids"))
        if status not in _ALLOWED_ABSENCE_STATUS:
            violations.append(Violation("SXF-S2-014", f"{match_id}: absence_assessment.status must be NONE/UNKNOWN/IDENTIFIED"))
        if availability not in _ALLOWED_AVAILABILITY:
            violations.append(Violation("SXF-S2-014", f"{match_id}: absence_assessment.availability is invalid"))
        if importance not in _ALLOWED_IMPORTANCE:
            violations.append(Violation("SXF-S2-014", f"{match_id}: absence_assessment.importance is invalid"))
        if thesis_effect not in _ALLOWED_EFFECT:
            violations.append(Violation("SXF-S2-014", f"{match_id}: absence_assessment.thesis_effect is invalid"))
        if not _nonempty(assessment.get("importance_reason")):
            violations.append(Violation("SXF-S2-014", f"{match_id}: absence_assessment.importance_reason is required"))

        quantified = assessment.get("quantified_context")
        if not isinstance(quantified, list):
            violations.append(Violation("SXF-S2-014", f"{match_id}: absence_assessment.quantified_context must be an explicit list"))
            quantified = []
        for metric_index, metric in enumerate(quantified):
            if not _valid_quant_metric(metric):
                violations.append(
                    Violation(
                        "SXF-S2-014",
                        f"{match_id}: absence_assessment.quantified_context[{metric_index}] requires metric, numeric value, unit and sample",
                    )
                )

        if status == "IDENTIFIED":
            if not _nonempty(assessment.get("subject")):
                violations.append(Violation("SXF-S2-014", f"{match_id}: identified absence requires subject"))
            if not _nonempty(assessment.get("role")):
                violations.append(Violation("SXF-S2-014", f"{match_id}: identified absence requires role"))
            if availability in {"NONE", "UNKNOWN"}:
                violations.append(Violation("SXF-S2-014", f"{match_id}: identified absence requires concrete availability status"))
            if importance in {"NONE", "UNKNOWN"}:
                violations.append(Violation("SXF-S2-014", f"{match_id}: identified absence requires LOW/MEDIUM/HIGH/CRITICAL importance"))
            if thesis_effect == "UNKNOWN":
                violations.append(Violation("SXF-S2-014", f"{match_id}: identified absence requires thesis_effect"))
            if not fact_ids:
                violations.append(Violation("SXF-S2-014", f"{match_id}: identified absence requires evidence fact_ids"))
            for fact_id in fact_ids:
                fact = fact_by_id.get(fact_id)
                if not isinstance(fact, dict) or str(fact.get("kind") or "").upper() != "FACT":
                    violations.append(Violation("SXF-S2-014", f"{match_id}: absence fact_id {fact_id!r} must reference a real FACT"))
                    continue
                if str(fact.get("category") or "").upper() not in {"SQUAD", "LINEUP", "MANAGER_COMMENT", "PERFORMANCE"}:
                    violations.append(Violation("SXF-S2-014", f"{match_id}: absence fact {fact_id} has unrelated category"))
            if importance in {"HIGH", "CRITICAL"}:
                if not any(
                    isinstance(fact_by_id.get(fid), dict)
                    and str(fact_by_id[fid].get("materiality") or "").upper() in {"MATERIAL", "CRITICAL"}
                    for fid in fact_ids
                ):
                    violations.append(
                        Violation("SXF-S2-014", f"{match_id}: {importance} absence importance requires MATERIAL/CRITICAL evidence")
                    )
        elif status == "NONE":
            if importance != "NONE" or availability != "NONE" or thesis_effect not in {"NEUTRAL", "UNKNOWN"}:
                violations.append(Violation("SXF-S2-014", f"{match_id}: NONE absence must use importance=NONE and availability=NONE"))
            if fact_ids:
                for fact_id in fact_ids:
                    if fact_id not in fact_by_id:
                        violations.append(Violation("SXF-S2-014", f"{match_id}: NONE absence references missing fact {fact_id!r}"))
        elif status == "UNKNOWN":
            if importance != "UNKNOWN" or availability != "UNKNOWN" or thesis_effect != "UNKNOWN":
                violations.append(Violation("SXF-S2-014", f"{match_id}: UNKNOWN absence must remain UNKNOWN instead of inventing impact"))
            if fact_ids:
                violations.append(Violation("SXF-S2-014", f"{match_id}: UNKNOWN absence cannot pretend evidence-backed certainty"))

    return tuple(violations)
