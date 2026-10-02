"""Immutable persistence primitives for SmartXFlow Analysis V2.

The V2 contract is deliberately append-only:
- a trigger snapshot is inserted once and never mutated,
- lifecycle changes are appended as state events,
- a signal can be settled only once,
- settlement identity is exact ``match_id_hash`` only.

No UPDATE/DELETE method is exposed by this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

from .entry_price import flat_stake_pnl_units, resolve_entry_odds


_HASH_RE = re.compile(r"^[0-9a-f]{12}$")

VALID_STATES = {
    "TRIGGERED",
    "ACTIVE",
    "CONFIRMED",
    "WEAKENED",
    "INVALIDATED",
    "SETTLED",
}
VALID_OUTCOMES = {"WIN", "LOSS", "PUSH", "VOID", "UNKNOWN"}

TRIGGER_NUMERIC_FIELDS = {
    "opening_odds",
    "trigger_odds",
    "recommended_odds",
    "trigger_pct",
    "trigger_amount",
    "trigger_volume",
    "odds_6h",
    "odds_2h",
    "odds_30m",
    "pct_6h",
    "pct_2h",
    "pct_30m",
    "amount_6h",
    "amount_2h",
    "amount_30m",
    "money_added_6h",
    "money_added_2h",
    "money_added_30m",
    "hours_before_kickoff",
}

REQUIRED_TRIGGER_FIELDS = (
    "engine_key",
    "engine_version",
    "match_id_hash",
    "home_team",
    "away_team",
    "market_key",
    "selection_code",
    "trigger_at",
)

TRIGGER_COLUMNS = {
    "signal_id",
    "engine_key",
    "engine_version",
    "match_id_hash",
    "home_team",
    "away_team",
    "league",
    "kickoff_utc",
    "market_key",
    "selection_code",
    "recommended_market",
    "recommended_selection",
    "trigger_at",
    *TRIGGER_NUMERIC_FIELDS,
    "engine_reason",
    "features",
    "config_snapshot",
    "raw_trigger",
}


def _clean_number(value: Any) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = (
        str(value)
        .strip()
        .replace("£", "")
        .replace("$", "")
        .replace("%", "")
        .replace(" ", "")
    )
    if "," in text and "." in text:
        text = text.replace(",", "")
    elif "," in text:
        left, right = text.rsplit(",", 1)
        text = (
            left + right
            if len(right) == 3 and left.replace("-", "").isdigit()
            else left + "." + right
        )
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
    return dt.astimezone(timezone.utc).isoformat()


def _stable_id(prefix: str, payload: Dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"


def validate_match_id_hash(match_id_hash: str) -> str:
    value = str(match_id_hash or "").strip().lower()
    if not _HASH_RE.fullmatch(value):
        raise ValueError(
            "match_id_hash must be the canonical 12-character lowercase hex hash"
        )
    return value


def make_signal_id(
    engine_key: str,
    engine_version: str,
    match_id_hash: str,
    market_key: str,
    selection_code: str,
) -> str:
    """Return the idempotency identity for one logical V2 signal.

    Trigger time is intentionally *not* part of this identity. A later scan that
    rediscovers the same engine/match/market/selection/version must resolve to
    the original immutable trigger snapshot.
    """
    return _stable_id(
        "sig",
        {
            "engine_key": str(engine_key).strip().lower(),
            "engine_version": str(engine_version).strip(),
            "match_id_hash": validate_match_id_hash(match_id_hash),
            "market_key": str(market_key).strip().upper(),
            "selection_code": str(selection_code).strip().upper(),
        },
    )


make_signal_uid = make_signal_id


def build_trigger_event(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize the trigger-time snapshot.

    Legacy draft keys ``triggered_at``, ``evidence`` and ``engine_params``
    are accepted at the boundary and mapped to the canonical V2 names.
    """
    source = dict(payload)
    if source.get("trigger_at") in (None, "") and source.get("triggered_at") not in (
        None,
        "",
    ):
        source["trigger_at"] = source["triggered_at"]
    if source.get("features") is None and isinstance(source.get("evidence"), dict):
        source["features"] = source["evidence"]
    if source.get("config_snapshot") is None and isinstance(
        source.get("engine_params"), dict
    ):
        source["config_snapshot"] = source["engine_params"]

    missing = [
        key for key in REQUIRED_TRIGGER_FIELDS if source.get(key) in (None, "")
    ]
    if missing:
        raise ValueError(f"missing trigger fields: {', '.join(missing)}")

    record = {key: source.get(key) for key in TRIGGER_COLUMNS if key in source}
    record["match_id_hash"] = validate_match_id_hash(source["match_id_hash"])
    record["engine_key"] = str(source["engine_key"]).strip().lower()
    record["engine_version"] = str(source["engine_version"]).strip()
    record["market_key"] = str(source["market_key"]).strip().upper()
    record["selection_code"] = str(source["selection_code"]).strip().upper()
    record["trigger_at"] = _timestamp(source["trigger_at"])

    if source.get("kickoff_utc"):
        record["kickoff_utc"] = _timestamp(source["kickoff_utc"])

    for field in TRIGGER_NUMERIC_FIELDS:
        if field in source:
            record[field] = _clean_number(source.get(field))

    record["recommended_market"] = (
        str(source.get("recommended_market") or record["market_key"]).strip().upper()
    )
    record["recommended_selection"] = (
        str(source.get("recommended_selection") or record["selection_code"])
        .strip()
        .upper()
    )

    for field in ("engine_reason", "features", "config_snapshot", "raw_trigger"):
        value = source.get(field)
        record[field] = value if isinstance(value, dict) else {}

    record["signal_id"] = make_signal_id(
        record["engine_key"],
        record["engine_version"],
        record["match_id_hash"],
        record["market_key"],
        record["selection_code"],
    )
    return record


def make_state_id(
    signal_id: str, state: str, state_at: Any, reason_code: str = ""
) -> str:
    return _stable_id(
        "state",
        {
            "signal_id": str(signal_id),
            "state": str(state).strip().upper(),
            "state_at": _timestamp(state_at),
            "reason_code": str(reason_code or ""),
        },
    )


def build_state_event(
    signal_id: str,
    state: str,
    state_at: Any,
    *,
    current_odds: Any = None,
    current_pct: Any = None,
    current_amount: Any = None,
    current_volume: Any = None,
    reason_code: str = "",
    reason: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    state = str(state or "").strip().upper()
    if state not in VALID_STATES:
        raise ValueError(f"invalid signal state: {state}")

    observed = _timestamp(state_at)
    return {
        "state_id": make_state_id(signal_id, state, observed, reason_code),
        "signal_id": str(signal_id),
        "state": state,
        "state_at": observed,
        "current_odds": _clean_number(current_odds),
        "current_pct": _clean_number(current_pct),
        "current_amount": _clean_number(current_amount),
        "current_volume": _clean_number(current_volume),
        "reason_code": str(reason_code or "") or None,
        "reason": reason if isinstance(reason, dict) else {},
    }


def initial_state_for_trigger(event: Dict[str, Any]) -> Dict[str, Any]:
    return build_state_event(
        event["signal_id"],
        "TRIGGERED",
        event["trigger_at"],
        current_odds=event.get("trigger_odds"),
        current_pct=event.get("trigger_pct"),
        current_amount=event.get("trigger_amount"),
        current_volume=event.get("trigger_volume"),
        reason_code="TRIGGERED",
        reason={
            "engine_key": event.get("engine_key"),
            "engine_version": event.get("engine_version"),
        },
    )


def is_transition_allowed(previous: Optional[str], new: str) -> bool:
    new = str(new or "").strip().upper()
    if new not in VALID_STATES:
        return False
    if previous is None:
        return new == "TRIGGERED"

    previous = str(previous).strip().upper()
    allowed = {
        "TRIGGERED": {
            "TRIGGERED",
            "ACTIVE",
            "CONFIRMED",
            "WEAKENED",
            "INVALIDATED",
            "SETTLED",
        },
        "ACTIVE": {
            "ACTIVE",
            "CONFIRMED",
            "WEAKENED",
            "INVALIDATED",
            "SETTLED",
        },
        "CONFIRMED": {
            "CONFIRMED",
            "WEAKENED",
            "INVALIDATED",
            "SETTLED",
        },
        "WEAKENED": {
            "WEAKENED",
            "ACTIVE",
            "CONFIRMED",
            "INVALIDATED",
            "SETTLED",
        },
        "INVALIDATED": {"INVALIDATED", "SETTLED"},
        "SETTLED": {"SETTLED"},
    }
    return new in allowed.get(previous, set())


def make_settlement_id(signal_id: str) -> str:
    return _stable_id("settle", {"signal_id": str(signal_id)})


def build_settlement_event(
    *,
    signal_id: str,
    match_id_hash: str,
    final_home_score: Optional[int],
    final_away_score: Optional[int],
    outcome: str,
    entry_odds: Any,
    pnl_units: Any,
    settled_at: Any,
    settlement_source: str,
    engine_version: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_outcome = str(outcome or "").strip().upper()
    if normalized_outcome not in VALID_OUTCOMES:
        raise ValueError(f"invalid settlement outcome: {normalized_outcome}")

    return {
        "settlement_id": make_settlement_id(signal_id),
        "signal_id": str(signal_id),
        "match_id_hash": validate_match_id_hash(match_id_hash),
        "final_home_score": (
            int(final_home_score) if final_home_score is not None else None
        ),
        "final_away_score": (
            int(final_away_score) if final_away_score is not None else None
        ),
        "outcome": normalized_outcome,
        "entry_odds": _clean_number(entry_odds),
        "pnl_units": _clean_number(pnl_units),
        "settled_at": _timestamp(settled_at),
        "settlement_source": str(settlement_source or "finished_scores"),
        "engine_version": str(engine_version or "").strip(),
        "metadata": metadata if isinstance(metadata, dict) else {},
    }


class SignalStore:
    """PostgREST repository for the append-only V2 signal ledger."""

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        write_key: Optional[str] = None,
        *,
        session=None,
        timeout: int = 15,
    ):
        self.url = (supabase_url or os.environ.get("SUPABASE_URL", "")).rstrip("/")
        self.key = (
            write_key
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_ANON_KEY", "")
        )
        self.session = session or requests
        self.timeout = timeout
        if not self.url or not self.key:
            raise ValueError("SUPABASE_URL and a write key are required")

    def _headers(self, prefer: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    @staticmethod
    def _json_rows(response) -> List[Dict[str, Any]]:
        if not getattr(response, "text", ""):
            return []
        try:
            data = response.json()
        except Exception as exc:
            raise RuntimeError("PostgREST returned invalid JSON") from exc
        if isinstance(data, list):
            return data
        return [data] if isinstance(data, dict) else []

    def _select(
        self,
        table: str,
        *,
        filters: Optional[Dict[str, Any]] = None,
        order: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"select": "*"}
        for key, value in (filters or {}).items():
            if value is not None:
                params[key] = f"eq.{value}"
        if order:
            params["order"] = order
        if limit is not None:
            params["limit"] = str(int(limit))

        response = self.session.get(
            f"{self.url}/rest/v1/{table}",
            headers=self._headers(),
            params=params,
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"{table} read failed: HTTP {response.status_code} "
                f"{(response.text or '')[:300]}"
            )
        return self._json_rows(response)

    def _select_one(
        self, table: str, filters: Dict[str, Any], *, order: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        rows = self._select(table, filters=filters, order=order, limit=1)
        return rows[0] if rows else None

    def _insert_once(
        self, table: str, conflict_field: str, record: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], bool]:
        response = self.session.post(
            f"{self.url}/rest/v1/{table}",
            headers=self._headers(
                "resolution=ignore-duplicates,return=representation"
            ),
            params={"on_conflict": conflict_field},
            json=[record],
            timeout=self.timeout,
        )
        if response.status_code not in (200, 201, 204):
            raise RuntimeError(
                f"{table} append failed: HTTP {response.status_code} "
                f"{(response.text or '')[:300]}"
            )

        rows = self._json_rows(response)
        if rows:
            return rows[0], True

        existing = self._select_one(
            table, {conflict_field: record[conflict_field]}
        )
        if existing is None:
            raise RuntimeError(
                f"{table} insert returned no row and existing record was not found"
            )
        return existing, False

    def create_signal_once(
        self, payload: Dict[str, Any], *, with_initial_state: bool = True
    ) -> Dict[str, Any]:
        event = build_trigger_event(payload)
        stored, _inserted = self._insert_once(
            "analysis_v2_signal_events", "signal_id", event
        )
        if with_initial_state:
            self.append_state(initial_state_for_trigger(stored))
        return stored

    append_trigger = create_signal_once

    def append_state(self, state_event: Dict[str, Any]) -> Dict[str, Any]:
        required = ("state_id", "signal_id", "state", "state_at")
        if any(state_event.get(key) in (None, "") for key in required):
            raise ValueError("state event is missing required fields")

        existing = self._select_one(
            "analysis_v2_signal_state_events",
            {"state_id": state_event["state_id"]},
        )
        if existing is not None:
            return existing

        latest = self.get_latest_state(state_event["signal_id"])
        previous = latest.get("state") if latest else None
        if not is_transition_allowed(previous, state_event["state"]):
            raise ValueError(
                f"invalid signal state transition: {previous!r} -> "
                f"{state_event['state']!r}"
            )
        if latest and _timestamp(state_event["state_at"]) < _timestamp(
            latest["state_at"]
        ):
            raise ValueError("state_at cannot move backwards")

        stored, _ = self._insert_once(
            "analysis_v2_signal_state_events", "state_id", dict(state_event)
        )
        return stored

    def settle_signal(
        self,
        *,
        signal_id: str,
        match_id_hash: str,
        final_home_score: Optional[int],
        final_away_score: Optional[int],
        outcome: str,
        settled_at: Any,
        pnl_units: Any,
        settlement_source: str = "finished_scores",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        existing = self.get_settlement(signal_id)
        if existing is not None:
            if existing.get("match_id_hash") != validate_match_id_hash(
                match_id_hash
            ):
                raise ValueError("existing settlement belongs to a different match")
            return existing

        signal = self.get_signal(signal_id)
        if signal is None:
            raise ValueError(f"unknown Analysis V2 signal_id: {signal_id}")

        exact_hash = validate_match_id_hash(match_id_hash)
        if signal["match_id_hash"] != exact_hash:
            raise ValueError(
                "settlement requires exact match_id_hash; fuzzy/team-name "
                "fallback is forbidden"
            )

        entry_odds = resolve_entry_odds(signal)
        canonical_pnl_units = flat_stake_pnl_units(
            entry_odds,
            outcome,
        )
        settlement = build_settlement_event(
            signal_id=signal_id,
            match_id_hash=exact_hash,
            final_home_score=final_home_score,
            final_away_score=final_away_score,
            outcome=outcome,
            entry_odds=entry_odds,
            pnl_units=canonical_pnl_units,
            settled_at=settled_at,
            settlement_source=settlement_source,
            engine_version=signal.get("engine_version", ""),
            metadata=metadata,
        )
        stored, _inserted = self._insert_once(
            "analysis_v2_signal_settlements", "signal_id", settlement
        )

        self.append_state(
            build_state_event(
                signal_id,
                "SETTLED",
                stored["settled_at"],
                reason_code="MATCH_SETTLED",
                reason={
                    "outcome": stored.get("outcome"),
                    "settlement_id": stored.get("settlement_id"),
                },
            )
        )
        return stored

    def get_signal(self, signal_id: str) -> Optional[Dict[str, Any]]:
        return self._select_one(
            "analysis_v2_signal_events", {"signal_id": str(signal_id)}
        )

    def get_latest_state(self, signal_id: str) -> Optional[Dict[str, Any]]:
        return self._select_one(
            "analysis_v2_signal_state_events",
            {"signal_id": str(signal_id)},
            order="state_at.desc,id.desc",
        )

    def get_settlement(self, signal_id: str) -> Optional[Dict[str, Any]]:
        return self._select_one(
            "analysis_v2_signal_settlements", {"signal_id": str(signal_id)}
        )

    def list_signals(
        self,
        *,
        match_id_hash: Optional[str] = None,
        engine_key: Optional[str] = None,
        current_state: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        filters: Dict[str, Any] = {}
        if match_id_hash is not None:
            filters["match_id_hash"] = validate_match_id_hash(match_id_hash)
        if engine_key is not None:
            filters["engine_key"] = str(engine_key).strip().lower()
        if current_state is not None:
            state = str(current_state).strip().upper()
            if state not in VALID_STATES:
                raise ValueError(f"invalid current_state: {state}")
            filters["current_state"] = state

        return self._select(
            "analysis_v2_signal_current",
            filters=filters,
            order="trigger_at.desc,id.desc",
            limit=max(1, min(int(limit), 2000)),
        )


SignalLedger = SignalStore
