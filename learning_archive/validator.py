from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Iterable

_DECISIONS = {"BET", "WATCH", "PASS"}
_SETTLEMENT_STATUSES = {"PENDING", "WIN", "LOSS", "VOID", "NO_BET"}
_EVIDENCE_RELATIONSHIPS = {"SUPPORTS", "CONTRADICTS", "NEUTRAL", "UNKNOWN"}
_SENSITIVE_KEY_PARTS = (
    "api_key", "apikey", "access_token", "refresh_token", "auth_token", "authorization",
    "password", "passwd", "cookie", "private_key", "client_secret", "service_role", "database_url",
)
_SECRET_VALUE_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.I),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.I),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsb_secret_[A-Za-z0-9_-]{12,}\b", re.I),
)


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: tuple[str, ...]


def _parse_datetime(value: Any, field: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field}: required ISO-8601 datetime string")
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        errors.append(f"{field}: invalid ISO-8601 datetime")
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        errors.append(f"{field}: timezone offset is required")
        return None
    return parsed.astimezone(timezone.utc)


def _require_mapping(value: Any, field: str, errors: list[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(f"{field}: required object")
        return None
    return value


def _require_text(mapping: dict[str, Any], key: str, prefix: str, errors: list[str]) -> str | None:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{prefix}.{key}: required non-empty string")
        return None
    return value.strip()


def _optional_text(mapping: dict[str, Any], key: str, prefix: str, errors: list[str]) -> None:
    if key not in mapping or mapping.get(key) is None:
        return
    if not isinstance(mapping.get(key), str) or not str(mapping.get(key)).strip():
        errors.append(f"{prefix}.{key}: must be null or non-empty string")


def _walk(value: Any, path: str = "$") -> Iterable[tuple[str, str | None, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            yield child_path, str(key), child
            yield from _walk(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            yield child_path, None, child
            yield from _walk(child, child_path)


def _secret_errors(case: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for path, key, value in _walk(case):
        lower_key = (key or "").lower()
        if key and any(part in lower_key for part in _SENSITIVE_KEY_PARTS) and value not in (None, "", False):
            errors.append(f"{path}: secret/credential fields are forbidden")
        if isinstance(value, str):
            for pattern in _SECRET_VALUE_PATTERNS:
                if pattern.search(value):
                    errors.append(f"{path}: value appears to contain secret material")
                    break
    return errors


def _poly_errors(case: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for path, key, value in _walk(case):
        if not isinstance(value, str):
            continue
        lowered = value.strip().lower()
        if "polymarket" in lowered:
            errors.append(f"{path}: Polymarket/Poly intelligence is excluded from Learning Archive inputs")
        elif key and key.lower() in {"source", "category", "provider"} and lowered == "poly":
            errors.append(f"{path}: Polymarket/Poly intelligence is excluded from Learning Archive inputs")
    return errors


def validate_case(case: dict[str, Any], snapshots: list[dict[str, Any]] | None = None) -> ValidationResult:
    errors: list[str] = []
    if not isinstance(case, dict):
        return ValidationResult(False, ("$: case must be an object",))

    if case.get("archive_schema_version") != 1:
        errors.append("archive_schema_version: must equal 1")
    case_id = case.get("case_id")
    if not isinstance(case_id, str) or len(case_id.strip()) < 8:
        errors.append("case_id: required string with length >= 8")

    match = _require_mapping(case.get("match"), "match", errors)
    if match is not None:
        _require_text(match, "match_id_hash", "match", errors)
        _require_text(match, "league", "match", errors)
        _require_text(match, "home", "match", errors)
        _require_text(match, "away", "match", errors)
        _parse_datetime(match.get("kickoff_at"), "match.kickoff_at", errors)

    prediction = _require_mapping(case.get("prediction"), "prediction", errors)
    prediction_at: datetime | None = None
    decision = None
    if prediction is not None:
        prediction_at = _parse_datetime(prediction.get("prediction_at"), "prediction.prediction_at", errors)
        decision = prediction.get("decision")
        if decision not in _DECISIONS:
            errors.append("prediction.decision: must be BET, WATCH, or PASS")
        _require_text(prediction, "rationale", "prediction", errors)
        _require_text(prediction, "counterargument", "prediction", errors)
        if "confidence" not in prediction or prediction.get("confidence") is None:
            errors.append("prediction.confidence: required")
        entry_odds = prediction.get("entry_odds")
        if decision == "BET":
            _require_text(prediction, "market", "prediction", errors)
            _require_text(prediction, "selection", "prediction", errors)
            if not isinstance(entry_odds, (int, float)) or isinstance(entry_odds, bool) or entry_odds <= 1:
                errors.append("prediction.entry_odds: BET requires a number > 1")
        else:
            _optional_text(prediction, "market", "prediction", errors)
            _optional_text(prediction, "selection", "prediction", errors)
            if entry_odds is not None and (not isinstance(entry_odds, (int, float)) or isinstance(entry_odds, bool) or entry_odds <= 1):
                errors.append("prediction.entry_odds: must be null or a number > 1")

    evidence = case.get("evidence")
    if not isinstance(evidence, list):
        errors.append("evidence: required array")
    else:
        for index, item in enumerate(evidence):
            prefix = f"evidence[{index}]"
            if not isinstance(item, dict):
                errors.append(f"{prefix}: must be an object")
                continue
            _require_text(item, "source", prefix, errors)
            _require_text(item, "note", prefix, errors)
            observed_at = _parse_datetime(item.get("observed_at"), f"{prefix}.observed_at", errors)
            if item.get("published_at") is not None:
                _parse_datetime(item.get("published_at"), f"{prefix}.published_at", errors)
            if item.get("relationship", "UNKNOWN") not in _EVIDENCE_RELATIONSHIPS:
                errors.append(f"{prefix}.relationship: invalid value")
            if prediction_at is not None and observed_at is not None:
                expected_phase = "PRE" if observed_at <= prediction_at else "POST"
                supplied_phase = item.get("phase")
                if supplied_phase is not None and supplied_phase != expected_phase:
                    errors.append(f"{prefix}.phase: must be {expected_phase} from observed_at/prediction_at cutoff")

    settlement = _require_mapping(case.get("settlement"), "settlement", errors)
    if settlement is not None:
        settlement_status = settlement.get("status")
        if settlement_status not in _SETTLEMENT_STATUSES:
            errors.append("settlement.status: must be PENDING, WIN, LOSS, VOID, or NO_BET")
        if decision == "BET" and settlement_status == "NO_BET":
            errors.append("settlement.status: BET cannot settle as NO_BET")
        if decision in {"WATCH", "PASS"} and settlement_status in {"WIN", "LOSS"}:
            errors.append("settlement.status: WATCH/PASS must not be converted into a wager result")

    provenance = _require_mapping(case.get("provenance"), "provenance", errors)
    if provenance is not None:
        _parse_datetime(provenance.get("archive_created_at"), "provenance.archive_created_at", errors)
        _require_text(provenance, "source_repo", "provenance", errors)
        _require_text(provenance, "source_commit", "provenance", errors)
        if provenance.get("archive_finalized_at") is not None:
            _parse_datetime(provenance.get("archive_finalized_at"), "provenance.archive_finalized_at", errors)

    if snapshots is not None:
        if not isinstance(snapshots, list) or not snapshots:
            errors.append("snapshots: selected learning case requires non-empty SXF history")
        else:
            match_hash = match.get("match_id_hash") if match else None
            for index, snapshot in enumerate(snapshots):
                if not isinstance(snapshot, dict):
                    errors.append(f"snapshots[{index}]: must be an object")
                    continue
                if match_hash and snapshot.get("match_id_hash") not in (None, "", match_hash):
                    errors.append(f"snapshots[{index}].match_id_hash: does not match case match_id_hash")

    errors.extend(_secret_errors(case))
    errors.extend(_poly_errors(case))
    unique = tuple(sorted(set(errors)))
    return ValidationResult(not unique, unique)


def classify_evidence_phase(case: dict[str, Any]) -> list[dict[str, Any]]:
    prediction = case.get("prediction") or {}
    errors: list[str] = []
    cutoff = _parse_datetime(prediction.get("prediction_at"), "prediction.prediction_at", errors)
    if cutoff is None:
        raise ValueError("valid prediction.prediction_at is required")
    result: list[dict[str, Any]] = []
    for item in case.get("evidence") or []:
        copied = dict(item)
        item_errors: list[str] = []
        observed = _parse_datetime(copied.get("observed_at"), "evidence.observed_at", item_errors)
        if observed is None:
            raise ValueError("valid evidence.observed_at is required")
        copied["phase"] = "PRE" if observed <= cutoff else "POST"
        result.append(copied)
    return result
