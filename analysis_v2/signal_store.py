"""Append-only signal ledger primitives for Analysis V2.

V2 deliberately does not expose UPDATE or DELETE methods for signal history.
Trigger facts are immutable; later observations and settlements are appended.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests


_HASH_RE = re.compile(r"^[0-9a-f]{12}$")
_VALID_STATUS = {"ACTIVE", "WEAKENED", "INVALIDATED", "SETTLED"}
_VALID_RESULT = {"WIN", "LOSS", "PUSH", "VOID", "UNKNOWN"}

_NUMERIC_FIELDS = {
    "opening_odds",
    "odds_6h",
    "odds_2h",
    "odds_30m",
    "trigger_odds",
    "trigger_pct",
    "trigger_amount",
    "trigger_volume",
    "money_delta_6h",
    "money_delta_2h",
    "money_delta_30m",
    "price_move_open_pct",
    "price_move_6h_pct",
    "price_move_2h_pct",
    "price_move_30m_pct",
    "hours_before_kickoff",
}

_REQUIRED_TRIGGER_FIELDS = (
    "engine_key",
    "engine_version",
    "match_id_hash",
    "home_team",
    "away_team",
    "market_key",
    "selection_code",
    "triggered_at",
)


def _clean_number(value: Any) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("£", "").replace("%", "").replace(" ", "")
    # Money strings use comma as thousands separator in SmartXFlow.
    if "," in text and "." in text:
        text = text.replace(",", "")
    elif "," in text:
        # Odds often use comma decimal separator. A 3-digit suffix is more
        # likely a thousands separator for money values, but callers should
        # normally pass normalized numerics. Keep this conservative.
        left, right = text.rsplit(",", 1)
        text = left + right if len(right) == 3 and left.replace("-", "").isdigit() else left + "." + right
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value or "").strip()
        if not raw:
            raise ValueError("timestamp is required")
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"invalid ISO timestamp: {raw}") from exc

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _stable_uid(prefix: str, payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"


def validate_match_id_hash(match_id_hash: str) -> str:
    value = str(match_id_hash or "").strip().lower()
    if not _HASH_RE.fullmatch(value):
        raise ValueError("match_id_hash must be the canonical 12-character lowercase hex hash")
    return value


def make_signal_uid(
    engine_key: str,
    engine_version: str,
    match_id_hash: str,
    market_key: str,
    selection_code: str,
    triggered_at: Any,
) -> str:
    return _stable_uid(
        "sig",
        {
            "engine_key": str(engine_key).strip().lower(),
            "engine_version": str(engine_version).strip(),
            "match_id_hash": validate_match_id_hash(match_id_hash),
            "market_key": str(market_key).strip().upper(),
            "selection_code": str(selection_code).strip().upper(),
            "triggered_at": _timestamp(triggered_at),
        },
    )


def build_trigger_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize immutable trigger-time facts."""
    missing = [key for key in _REQUIRED_TRIGGER_FIELDS if payload.get(key) in (None, "")]
    if missing:
        raise ValueError(f"missing trigger fields: {', '.join(missing)}")

    record = dict(payload)
    record["match_id_hash"] = validate_match_id_hash(record["match_id_hash"])
    record["engine_key"] = str(record["engine_key"]).strip().lower()
    record["engine_version"] = str(record["engine_version"]).strip()
    record["market_key"] = str(record["market_key"]).strip().upper()
    record["selection_code"] = str(record["selection_code"]).strip().upper()
    record["triggered_at"] = _timestamp(record["triggered_at"])

    if record.get("kickoff_utc"):
        record["kickoff_utc"] = _timestamp(record["kickoff_utc"])

    for field in _NUMERIC_FIELDS:
        if field in record:
            record[field] = _clean_number(record.get(field))

    for field in ("evidence", "engine_params", "raw_trigger"):
        value = record.get(field)
        record[field] = value if isinstance(value, dict) else {}

    record.setdefault(
        "signal_uid",
        make_signal_uid(
            record["engine_key"],
            record["engine_version"],
            record["match_id_hash"],
            record["market_key"],
            record["selection_code"],
            record["triggered_at"],
        ),
    )
    return record


def make_state_uid(signal_uid: str, status: str, observed_at: Any, reason_code: str = "") -> str:
    return _stable_uid(
        "state",
        {
            "signal_uid": signal_uid,
            "status": status.upper(),
            "observed_at": _timestamp(observed_at),
            "reason_code": str(reason_code or ""),
        },
    )


def build_state_event(
    signal_uid: str,
    status: str,
    observed_at: Any,
    *,
    current_odds: Any = None,
    current_pct: Any = None,
    current_amount: Any = None,
    current_volume: Any = None,
    reason_code: str = "",
    reason_detail: Optional[Dict[str, Any]] = None,
    metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    status = str(status or "").strip().upper()
    if status not in _VALID_STATUS:
        raise ValueError(f"invalid signal status: {status}")

    observed = _timestamp(observed_at)
    return {
        "state_uid": make_state_uid(signal_uid, status, observed, reason_code),
        "signal_uid": signal_uid,
        "status": status,
        "observed_at": observed,
        "current_odds": _clean_number(current_odds),
        "current_pct": _clean_number(current_pct),
        "current_amount": _clean_number(current_amount),
        "current_volume": _clean_number(current_volume),
        "reason_code": str(reason_code or "") or None,
        "reason_detail": reason_detail if isinstance(reason_detail, dict) else {},
        "metrics": metrics if isinstance(metrics, dict) else {},
    }


def initial_state_for_trigger(event: Dict[str, Any]) -> Dict[str, Any]:
    return build_state_event(
        event["signal_uid"],
        "ACTIVE",
        event["triggered_at"],
        current_odds=event.get("trigger_odds"),
        current_pct=event.get("trigger_pct"),
        current_amount=event.get("trigger_amount"),
        current_volume=event.get("trigger_volume"),
        reason_code="TRIGGERED",
        reason_detail={"engine_key": event.get("engine_key"), "engine_version": event.get("engine_version")},
    )


def is_transition_allowed(previous: Optional[str], new: str) -> bool:
    new = str(new or "").upper()
    if new not in _VALID_STATUS:
        return False
    if previous is None:
        return new == "ACTIVE"
    previous = str(previous).upper()
    allowed = {
        "ACTIVE": {"ACTIVE", "WEAKENED", "INVALIDATED", "SETTLED"},
        "WEAKENED": {"ACTIVE", "WEAKENED", "INVALIDATED", "SETTLED"},
        "INVALIDATED": {"INVALIDATED", "SETTLED"},
        "SETTLED": {"SETTLED"},
    }
    return new in allowed.get(previous, set())


def make_settlement_uid(
    signal_uid: str,
    match_id_hash: str,
    settled_at: Any,
    home_score: Optional[int],
    away_score: Optional[int],
    selection_result: str,
) -> str:
    return _stable_uid(
        "settle",
        {
            "signal_uid": signal_uid,
            "match_id_hash": validate_match_id_hash(match_id_hash),
            "settled_at": _timestamp(settled_at),
            "home_score": home_score,
            "away_score": away_score,
            "selection_result": selection_result.upper(),
        },
    )


def build_settlement_event(
    *,
    signal_uid: str,
    match_id_hash: str,
    settled_at: Any,
    home_score: Optional[int],
    away_score: Optional[int],
    selection_result: str,
    result_code: Optional[str] = None,
    settled_odds: Any = None,
    flat_stake_units: Any = None,
    source: str = "finished_scores",
    evidence: Optional[Dict[str, Any]] = None,
    correction_of: Optional[str] = None,
) -> Dict[str, Any]:
    result = str(selection_result or "").strip().upper()
    if result not in _VALID_RESULT:
        raise ValueError(f"invalid selection_result: {result}")

    match_hash = validate_match_id_hash(match_id_hash)
    settled = _timestamp(settled_at)
    return {
        "settlement_uid": make_settlement_uid(
            signal_uid, match_hash, settled, home_score, away_score, result
        ),
        "signal_uid": signal_uid,
        "match_id_hash": match_hash,
        "settled_at": settled,
        "home_score": home_score,
        "away_score": away_score,
        "result_code": result_code,
        "selection_result": result,
        "settled_odds": _clean_number(settled_odds),
        "flat_stake_units": _clean_number(flat_stake_units),
        "source": str(source or "finished_scores"),
        "evidence": evidence if isinstance(evidence, dict) else {},
        "correction_of": correction_of,
    }


class SignalLedger:
    """Small PostgREST writer with append-only semantics.

    There are intentionally no patch/update/delete methods.
    """

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        write_key: Optional[str] = None,
        *,
        session=None,
        timeout: int = 15,
    ):
        self.url = (supabase_url or os.environ.get("SUPABASE_URL", "")).rstrip("/")
        self.key = write_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY", "")
        self.session = session or requests
        self.timeout = timeout
        if not self.url or not self.key:
            raise ValueError("SUPABASE_URL and a write key are required")

    def _headers(self):
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=ignore-duplicates,return=representation",
        }

    def _append(self, table: str, unique_field: str, record: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.url}/rest/v1/{table}?on_conflict={unique_field}"
        response = self.session.post(
            url,
            headers=self._headers(),
            json=[record],
            timeout=self.timeout,
        )
        if response.status_code not in (200, 201, 204):
            raise RuntimeError(f"{table} append failed: HTTP {response.status_code} {(response.text or '')[:300]}")
        if response.status_code == 204 or not getattr(response, "text", ""):
            return record
        try:
            rows = response.json()
            return rows[0] if rows else record
        except Exception:
            return record

    def append_trigger(self, payload: Dict[str, Any], *, with_initial_state: bool = True) -> Dict[str, Any]:
        event = build_trigger_event(payload)
        self._append("analysis_v2_signal_events", "signal_uid", event)
        if with_initial_state:
            self.append_state(initial_state_for_trigger(event))
        return event

    def append_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        required = ("state_uid", "signal_uid", "status", "observed_at")
        if any(state.get(k) in (None, "") for k in required):
            raise ValueError("state event is missing required fields")
        return self._append("analysis_v2_signal_state_events", "state_uid", state)

    def append_settlement(self, settlement: Dict[str, Any], *, append_settled_state: bool = True) -> Dict[str, Any]:
        required = ("settlement_uid", "signal_uid", "match_id_hash", "settled_at")
        if any(settlement.get(k) in (None, "") for k in required):
            raise ValueError("settlement event is missing required fields")
        result = self._append(
            "analysis_v2_signal_settlement_events",
            "settlement_uid",
            settlement,
        )
        if append_settled_state:
            self.append_state(
                build_state_event(
                    settlement["signal_uid"],
                    "SETTLED",
                    settlement["settled_at"],
                    reason_code="MATCH_SETTLED",
                    reason_detail={
                        "selection_result": settlement.get("selection_result"),
                        "settlement_uid": settlement.get("settlement_uid"),
                    },
                )
            )
        return result
