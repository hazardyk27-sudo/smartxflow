from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .source_quality import category_max_age_days, normalize_source_host, verified_source_tier
from .validator import Violation


_ALLOWED_CHECK_STATUS = {"VERIFIED", "UNKNOWN"}
_SQUAD_CATEGORIES = {"SQUAD", "LINEUP", "MANAGER_COMMENT", "CONTEXT"}
_PERFORMANCE_CATEGORIES = {"PERFORMANCE", "TACTICAL"}


def _parse_iso(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_source_record(
    *,
    match_id: str,
    label: str,
    source: Any,
    declared_tier: Any,
    observed_at: Any,
    evidence_at: Any,
    category: str,
    research_cutoff: datetime | None,
    kickoff: datetime | None,
) -> tuple[list[Violation], str | None, str | None]:
    violations: list[Violation] = []
    host = normalize_source_host(source)
    if host is None:
        violations.append(Violation("SXF-S2-009", f"{match_id}: {label} requires a real http/https source URL"))
        return violations, None, None

    verified_tier = verified_source_tier(str(source))
    claimed = str(declared_tier or "").upper()
    if claimed not in {"A", "B", "C", "D"}:
        violations.append(Violation("SXF-S2-011", f"{match_id}: {label} source_tier must be A/B/C/D"))
    elif claimed != verified_tier:
        violations.append(
            Violation(
                "SXF-S2-011",
                f"{match_id}: {label} claimed Tier {claimed} but verified source registry classifies {host} as Tier {verified_tier}",
            )
        )

    observed = _parse_iso(observed_at)
    evidence = _parse_iso(evidence_at)
    if observed is None:
        violations.append(Violation("SXF-S2-009", f"{match_id}: {label} observed_at must be a timezone-aware timestamp"))
    if evidence is None:
        violations.append(Violation("SXF-S2-012", f"{match_id}: {label} evidence_at must identify when the underlying evidence was current/published"))
    if observed is not None and evidence is not None and evidence > observed:
        violations.append(Violation("SXF-S2-012", f"{match_id}: {label} evidence_at cannot be later than observed_at"))
    if research_cutoff is not None and observed is not None and observed > research_cutoff:
        violations.append(Violation("SXF-S2-012", f"{match_id}: {label} was observed after the Stage 2 research cutoff"))
    if kickoff is not None and observed is not None and observed >= kickoff:
        violations.append(Violation("SXF-S2-012", f"{match_id}: {label} was observed at/after kickoff and is POST evidence"))
    if kickoff is not None and evidence is not None:
        if evidence >= kickoff:
            violations.append(Violation("SXF-S2-012", f"{match_id}: {label} evidence_at is at/after kickoff"))
        max_age = category_max_age_days(category)
        if max_age is not None:
            age_seconds = (kickoff - evidence).total_seconds()
            if age_seconds > max_age * 86400:
                violations.append(
                    Violation(
                        "SXF-S2-012",
                        f"{match_id}: {label} {category} evidence is too old for Stage 2 ({age_seconds / 86400:.1f}d > {max_age}d)",
                    )
                )
    return violations, host, verified_tier


def validate_stage2_quality(payload: dict[str, Any]) -> tuple[Violation, ...]:
    violations: list[Violation] = []
    research_cutoff = _parse_iso(payload.get("research_cutoff_at"))
    if research_cutoff is None:
        violations.append(Violation("SXF-S2-012", "research_cutoff_at is required and must be timezone-aware"))

    matches = payload.get("matches")
    if not isinstance(matches, list):
        return tuple(violations)

    for index, match in enumerate(matches):
        if not isinstance(match, dict):
            continue
        match_id = str(match.get("fixture_id") or match.get("fixture_uid") or match.get("match_id_hash") or index)
        kickoff = _parse_iso(match.get("fixture_kickoff_utc"))
        if kickoff is None:
            violations.append(Violation("SXF-S2-012", f"{match_id}: fixture_kickoff_utc is required for freshness/PRE validation"))
        elif research_cutoff is not None and research_cutoff >= kickoff:
            violations.append(Violation("SXF-S2-012", f"{match_id}: Stage 2 research cutoff must be before kickoff"))

        facts = match.get("facts") if isinstance(match.get("facts"), list) else []
        fact_by_id: dict[str, dict[str, Any]] = {}
        fact_hosts: set[str] = set()
        fact_tiers: list[str] = []
        primary_fact_ids: set[str] = set()

        for fact_index, fact in enumerate(facts):
            if not isinstance(fact, dict):
                continue
            fact_id = str(fact.get("fact_id") or "").strip()
            if not fact_id:
                violations.append(Violation("SXF-S2-009", f"{match_id}: facts[{fact_index}] requires fact_id"))
                continue
            if fact_id in fact_by_id:
                violations.append(Violation("SXF-S2-009", f"{match_id}: duplicate fact_id {fact_id!r}"))
                continue
            fact_by_id[fact_id] = fact

        for fact_id, fact in fact_by_id.items():
            kind = str(fact.get("kind") or "").upper()
            category = str(fact.get("category") or "").upper()
            materiality = str(fact.get("materiality") or "").upper()
            relationship = str(fact.get("relationship") or "").upper()
            derived_ids = _ids(fact.get("derived_from_fact_ids"))

            if kind == "FACT":
                primary_fact_ids.add(fact_id)
                if derived_ids:
                    violations.append(Violation("SXF-S2-009", f"{match_id}: FACT {fact_id} must not use derived_from_fact_ids"))
                source_violations, host, tier = _validate_source_record(
                    match_id=match_id,
                    label=f"FACT {fact_id}",
                    source=fact.get("source"),
                    declared_tier=fact.get("source_tier"),
                    observed_at=fact.get("observed_at"),
                    evidence_at=fact.get("evidence_at"),
                    category=category,
                    research_cutoff=research_cutoff,
                    kickoff=kickoff,
                )
                violations.extend(source_violations)
                if host:
                    fact_hosts.add(host)
                if tier:
                    fact_tiers.append(tier)

                corroborators = fact.get("corroborating_sources")
                if not isinstance(corroborators, list):
                    corroborators = []
                verified_corroborator = False
                for corr_index, corr in enumerate(corroborators):
                    if not isinstance(corr, dict):
                        violations.append(Violation("SXF-S2-011", f"{match_id}: FACT {fact_id} corroborating_sources[{corr_index}] must be an object"))
                        continue
                    corr_violations, corr_host, corr_tier = _validate_source_record(
                        match_id=match_id,
                        label=f"FACT {fact_id} corroborator {corr_index}",
                        source=corr.get("source"),
                        declared_tier=corr.get("source_tier"),
                        observed_at=corr.get("observed_at"),
                        evidence_at=corr.get("evidence_at"),
                        category=category,
                        research_cutoff=research_cutoff,
                        kickoff=kickoff,
                    )
                    violations.extend(corr_violations)
                    if corr_host:
                        fact_hosts.add(corr_host)
                    if corr_host and corr_host != host and corr_tier in {"A", "B", "C"}:
                        verified_corroborator = True
                if materiality == "CRITICAL" and tier in {"C", "D"} and not verified_corroborator:
                    violations.append(
                        Violation(
                            "SXF-S2-011",
                            f"{match_id}: CRITICAL FACT {fact_id} from Tier {tier} requires an independent Tier A/B/C corroborating source",
                        )
                    )
            elif kind == "INFERENCE":
                if fact.get("source") is not None or fact.get("source_tier") is not None or fact.get("observed_at") is not None or fact.get("evidence_at") is not None:
                    violations.append(Violation("SXF-S2-009", f"{match_id}: INFERENCE {fact_id} must derive from cited FACTs instead of carrying pseudo-source fields"))
                if not derived_ids:
                    violations.append(Violation("SXF-S2-009", f"{match_id}: INFERENCE {fact_id} requires derived_from_fact_ids"))
                for source_fact_id in derived_ids:
                    base = fact_by_id.get(source_fact_id)
                    if not isinstance(base, dict) or str(base.get("kind") or "").upper() != "FACT":
                        violations.append(Violation("SXF-S2-009", f"{match_id}: INFERENCE {fact_id} references non-FACT {source_fact_id!r}"))
            else:
                continue

            if relationship not in {"SUPPORTS", "CONTRADICTS", "NEUTRAL"}:
                continue
            if category not in {"SQUAD", "LINEUP", "MANAGER_COMMENT", "PERFORMANCE", "TACTICAL", "CONTEXT", "H2H"}:
                violations.append(Violation("SXF-S2-009", f"{match_id}: FACT/INFERENCE {fact_id} has unsupported category {category!r}"))
            if materiality not in {"CRITICAL", "MATERIAL", "CONTEXT"}:
                violations.append(Violation("SXF-S2-009", f"{match_id}: FACT/INFERENCE {fact_id} has unsupported materiality {materiality!r}"))

        checks = match.get("research_checks")
        if not isinstance(checks, dict):
            violations.append(Violation("SXF-S2-010", f"{match_id}: evidence-backed research_checks object is required"))
            checks = {}

        def check_area(name: str, categories: set[str] | None, *, require_contradiction: bool = False) -> str:
            check = checks.get(name)
            if not isinstance(check, dict):
                violations.append(Violation("SXF-S2-010", f"{match_id}: research_checks.{name} must be an object"))
                return ""
            status = str(check.get("status") or "").upper()
            fact_ids = _ids(check.get("fact_ids"))
            if status not in _ALLOWED_CHECK_STATUS:
                violations.append(Violation("SXF-S2-010", f"{match_id}: research_checks.{name}.status must be VERIFIED or UNKNOWN"))
                return status
            if not _nonempty(check.get("note")):
                violations.append(Violation("SXF-S2-010", f"{match_id}: research_checks.{name}.note is required"))
            if status == "VERIFIED" and not fact_ids:
                violations.append(Violation("SXF-S2-010", f"{match_id}: VERIFIED research_checks.{name} requires fact_ids"))
            if status == "UNKNOWN" and fact_ids:
                violations.append(Violation("SXF-S2-010", f"{match_id}: UNKNOWN research_checks.{name} cannot pretend fact-backed completion"))
            for fact_id in fact_ids:
                fact = fact_by_id.get(fact_id)
                if not isinstance(fact, dict) or str(fact.get("kind") or "").upper() != "FACT":
                    violations.append(Violation("SXF-S2-010", f"{match_id}: research_checks.{name} references missing/non-FACT {fact_id!r}"))
                    continue
                category = str(fact.get("category") or "").upper()
                if categories is not None and category not in categories:
                    violations.append(Violation("SXF-S2-010", f"{match_id}: research_checks.{name} cannot be satisfied by {category} fact {fact_id}"))
                if require_contradiction and str(fact.get("relationship") or "").upper() != "CONTRADICTS":
                    violations.append(Violation("SXF-S2-010", f"{match_id}: research_checks.{name} requires CONTRADICTS fact evidence"))
            return status

        squad_status = check_area("squad", _SQUAD_CATEGORIES)
        performance_status = check_area("performance", _PERFORMANCE_CATEGORIES)
        counter_status = check_area("counter", None, require_contradiction=True)

        support_ids = _ids(match.get("support_fact_ids"))
        counter_ids = _ids(match.get("counter_fact_ids"))
        for label, ids, expected_relationship in (
            ("support_fact_ids", support_ids, "SUPPORTS"),
            ("counter_fact_ids", counter_ids, "CONTRADICTS"),
        ):
            for fact_id in ids:
                fact = fact_by_id.get(fact_id)
                if not isinstance(fact, dict) or str(fact.get("kind") or "").upper() != "FACT":
                    violations.append(Violation("SXF-S2-010", f"{match_id}: {label} must reference real FACT ids; bad id {fact_id!r}"))
                elif str(fact.get("relationship") or "").upper() != expected_relationship:
                    violations.append(Violation("SXF-S2-010", f"{match_id}: {label} fact {fact_id} must be {expected_relationship}"))

        verdict = str(match.get("verdict") or "").upper()
        coverage = str(match.get("coverage") or "").upper()
        if verdict in {"CONFIRMED", "PARTIALLY_CONFIRMED"} and not support_ids:
            violations.append(Violation("SXF-S2-013", f"{match_id}: {verdict} requires at least one real supporting FACT"))
        if coverage in {"HIGH", "MEDIUM"} and not counter_ids:
            violations.append(Violation("SXF-S2-013", f"{match_id}: {coverage} coverage requires at least one real contradicting FACT"))
        if verdict == "CONTRADICTED" and not counter_ids:
            violations.append(Violation("SXF-S2-013", f"{match_id}: CONTRADICTED requires real counterevidence"))

        if not _nonempty(match.get("research_synthesis")):
            violations.append(Violation("SXF-S2-013", f"{match_id}: research_synthesis is required"))

        fact_count = len(primary_fact_ids)
        host_count = len(fact_hosts)
        if coverage == "HIGH":
            if fact_count < 4 or host_count < 2:
                violations.append(Violation("SXF-S2-013", f"{match_id}: HIGH coverage requires >=4 FACTs from >=2 independent source hosts"))
            if {squad_status, performance_status, counter_status} != {"VERIFIED"}:
                violations.append(Violation("SXF-S2-013", f"{match_id}: HIGH coverage requires verified squad, performance and counter checks"))
        elif coverage == "MEDIUM":
            if fact_count < 3 or host_count < 2:
                violations.append(Violation("SXF-S2-013", f"{match_id}: MEDIUM coverage requires >=3 FACTs from >=2 independent source hosts"))
            if performance_status != "VERIFIED" or counter_status != "VERIFIED":
                violations.append(Violation("SXF-S2-013", f"{match_id}: MEDIUM coverage requires verified performance and counter checks"))
        elif coverage == "LOW":
            if fact_count < 1 or host_count < 1:
                violations.append(Violation("SXF-S2-013", f"{match_id}: LOW coverage still requires at least one sourced FACT"))

        if coverage in {"HIGH", "MEDIUM"}:
            for label, ids in (("support", support_ids), ("counter", counter_ids)):
                if ids and all(str((fact_by_id.get(fid) or {}).get("category") or "").upper() == "H2H" for fid in ids):
                    violations.append(Violation("SXF-S2-013", f"{match_id}: H2H cannot be the sole {label} evidence at {coverage} coverage"))

        if fact_tiers and set(fact_tiers) == {"D"} and verdict != "UNEXPLAINED":
            violations.append(Violation("SXF-S2-011", f"{match_id}: Tier D-only research cannot materially decide the Stage 2 verdict"))

    return tuple(violations)
