"""Engine-first Analysis V2 contract.

V2 is an upgrade layer for the existing Analyses engines, not an independent
match-discovery engine. A V2 evaluation must therefore start from a real V1
engine trigger (Underdog Pressure, Confirmed Money, Early Money Lock or
Fake Sharp / Price-Money Divergence).

This module is intentionally pure: it does not read or write the database and
it does not create bets by itself. It normalizes a V1 trigger into one stable
candidate contract that later layers can enrich with price/money movement,
calibration, cross-market evidence and market selection.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple


ENGINE_FIRST_VERSION = "analysis-v2-engine-first-1.0.0"

ENGINE_ALIASES = {
    "underdog": "underdog_pressure_v1",
    "underdog_pressure": "underdog_pressure_v1",
    "underdog_pressure_v1": "underdog_pressure_v1",
    "confirmed_money": "confirmed_money_v1",
    "confirmed_money_v1": "confirmed_money_v1",
    "early_money_lock": "early_money_lock_v1",
    "early_money_lock_v1": "early_money_lock_v1",
    "fake_sharp": "price_money_divergence_v1",
    "fake_sharp_v1": "price_money_divergence_v1",
    "price_money_divergence": "price_money_divergence_v1",
    "price_money_divergence_v1": "price_money_divergence_v1",
}

ENGINE_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "underdog_pressure_v1": {
        "display_name": "Underdog Pressure",
        "role": "DIRECTION_CANDIDATE",
        "default_market": "1X2",
        "allowed_selections": ("1", "2"),
        "direct_bet": False,
    },
    "confirmed_money_v1": {
        "display_name": "Confirmed Money",
        "role": "BET_CANDIDATE",
        "default_market": "1X2",
        "allowed_selections": ("1", "X", "2"),
        "direct_bet": True,
    },
    "early_money_lock_v1": {
        "display_name": "Early Money Lock",
        "role": "BET_CANDIDATE",
        "default_market": "1X2",
        "allowed_selections": ("1", "X", "2"),
        "direct_bet": True,
    },
    "price_money_divergence_v1": {
        "display_name": "Price-Money Divergence",
        "role": "WARNING",
        "default_market": "1X2",
        "allowed_selections": ("1", "2"),
        "direct_bet": False,
    },
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _text(value).upper()


def _number(value: Any) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    try:
        if isinstance(value, str):
            cleaned = (
                value.replace("£", "")
                .replace("€", "")
                .replace("$", "")
                .replace("%", "")
                .replace(",", "")
                .strip()
            )
            return float(cleaned) if cleaned else None
        return float(value)
    except (TypeError, ValueError):
        return None


def canonical_engine_key(engine_key: Any) -> str:
    key = _text(engine_key).lower()
    canonical = ENGINE_ALIASES.get(key)
    if not canonical:
        raise ValueError(f"UNSUPPORTED_SOURCE_ENGINE:{key or 'missing'}")
    return canonical


@dataclass(frozen=True)
class EngineCandidate:
    source_engine: str
    source_engine_version: str
    source_signal_id: str
    match_id_hash: str
    legacy_match_key: str
    home_team: str
    away_team: str
    league: str
    kickoff_utc: str
    source_market: str
    source_selection: str
    trigger_at: str
    trigger_odds: Optional[float]
    trigger_pct: Optional[float]
    trigger_amount: Optional[float]
    trigger_volume: Optional[float]
    source_payload: Dict[str, Any] = field(default_factory=dict)

    @property
    def definition(self) -> Dict[str, Any]:
        return dict(ENGINE_DEFINITIONS[self.source_engine])

    @property
    def exact_identity_ready(self) -> bool:
        return len(self.match_id_hash) == 12 and all(
            ch in "0123456789abcdef" for ch in self.match_id_hash.lower()
        )

    @property
    def role(self) -> str:
        return str(self.definition["role"])

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["engine_first_version"] = ENGINE_FIRST_VERSION
        payload["engine_definition"] = self.definition
        payload["exact_identity_ready"] = self.exact_identity_ready
        return payload


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def candidate_from_v1_signal(
    engine_key: Any,
    row: Mapping[str, Any],
    *,
    match_id_hash: Optional[str] = None,
    engine_version: Optional[str] = None,
) -> EngineCandidate:
    """Normalize one real V1 signal row into the V2 candidate contract.

    No synthetic V2 candidate can be created without a named supported source
    engine. Legacy rows may not yet contain an exact match hash; callers can
    provide the exact fixture hash through ``match_id_hash``. Such rows remain
    inspectable but must not be persisted/settled by V2 until exact identity is
    available.
    """

    canonical = canonical_engine_key(engine_key)
    definition = ENGINE_DEFINITIONS[canonical]

    selection = _upper(
        _first(row, "selection_code", "selection", "sel", "pick")
    )
    if selection not in definition["allowed_selections"]:
        raise ValueError(
            f"INVALID_SOURCE_SELECTION:{canonical}:{selection or 'missing'}"
        )

    market = _upper(_first(row, "market_key", "market")) or str(
        definition["default_market"]
    )
    if market != definition["default_market"]:
        raise ValueError(f"INVALID_SOURCE_MARKET:{canonical}:{market}")

    exact_hash = _text(match_id_hash or row.get("match_id_hash")).lower()
    legacy_key = _text(_first(row, "match_key", "legacy_match_key"))

    signal_id = _text(_first(row, "signal_id", "id"))
    if not signal_id:
        raise ValueError("SOURCE_SIGNAL_ID_REQUIRED")

    trigger_odds = _number(
        _first(row, "trigger_odds", "odds", "odds_now", "current_odds")
    )
    trigger_pct = _number(
        _first(row, "trigger_pct", "pct", "pct_now", "current_pct")
    )
    trigger_amount = _number(
        _first(row, "trigger_amount", "amount", "amt_now", "current_amt")
    )
    trigger_volume = _number(
        _first(row, "trigger_volume", "volume", "volume_now", "current_volume")
    )

    source_version = _text(
        engine_version or _first(row, "engine_version", "source_engine_version")
    ) or "v1-legacy"

    candidate = EngineCandidate(
        source_engine=canonical,
        source_engine_version=source_version,
        source_signal_id=signal_id,
        match_id_hash=exact_hash,
        legacy_match_key=legacy_key,
        home_team=_text(_first(row, "home_team", "home")),
        away_team=_text(_first(row, "away_team", "away")),
        league=_text(row.get("league")),
        kickoff_utc=_text(_first(row, "kickoff_utc", "date", "match_date")),
        source_market=market,
        source_selection=selection,
        trigger_at=_text(_first(row, "trigger_at", "created_at")),
        trigger_odds=trigger_odds,
        trigger_pct=trigger_pct,
        trigger_amount=trigger_amount,
        trigger_volume=trigger_volume,
        source_payload=dict(row),
    )

    validate_candidate(candidate)
    return candidate


def validate_candidate(candidate: EngineCandidate) -> None:
    definition = ENGINE_DEFINITIONS.get(candidate.source_engine)
    if not definition:
        raise ValueError("SOURCE_ENGINE_REQUIRED")
    if candidate.source_market != definition["default_market"]:
        raise ValueError("SOURCE_MARKET_MISMATCH")
    if candidate.source_selection not in definition["allowed_selections"]:
        raise ValueError("SOURCE_SELECTION_MISMATCH")
    if not candidate.source_signal_id:
        raise ValueError("SOURCE_SIGNAL_ID_REQUIRED")
    if not candidate.home_team or not candidate.away_team:
        raise ValueError("SOURCE_FIXTURE_REQUIRED")


def persistence_gate(candidate: EngineCandidate) -> Tuple[bool, Tuple[str, ...]]:
    """Return whether the candidate is safe for immutable V2 persistence."""

    reasons = []
    if not candidate.exact_identity_ready:
        reasons.append("EXACT_MATCH_ID_REQUIRED")
    if not candidate.trigger_at:
        reasons.append("TRIGGER_TIME_REQUIRED")
    if candidate.trigger_pct is None:
        reasons.append("TRIGGER_PCT_MISSING")
    if candidate.trigger_volume is None:
        reasons.append("TRIGGER_VOLUME_MISSING")
    if (
        candidate.source_engine == "early_money_lock_v1"
        and candidate.trigger_odds is None
    ):
        reasons.append("EML_TRIGGER_ODDS_MISSING")
    return not reasons, tuple(reasons)


def source_engine_summary(candidate: EngineCandidate) -> Dict[str, Any]:
    """Small explainable source block for presenter/runtime layers."""

    definition = candidate.definition
    return {
        "engine_first_version": ENGINE_FIRST_VERSION,
        "source_engine": candidate.source_engine,
        "source_engine_name": definition["display_name"],
        "source_role": definition["role"],
        "source_signal_id": candidate.source_signal_id,
        "source_market": candidate.source_market,
        "source_selection": candidate.source_selection,
        "trigger_odds": candidate.trigger_odds,
        "trigger_pct": candidate.trigger_pct,
        "trigger_amount": candidate.trigger_amount,
        "trigger_volume": candidate.trigger_volume,
        "direct_bet_allowed": bool(definition["direct_bet"]),
        "exact_identity_ready": candidate.exact_identity_ready,
    }


def reject_generic_discovery(payload: Mapping[str, Any]) -> None:
    """Fail closed if a caller tries to create a V2 candidate without V1 provenance."""

    source_engine = _first(payload, "source_engine", "engine_key", "v1_engine")
    source_signal_id = _first(payload, "source_signal_id", "v1_signal_id")
    if not source_engine or not source_signal_id:
        raise ValueError("ENGINE_FIRST_SOURCE_REQUIRED")
    canonical_engine_key(source_engine)
