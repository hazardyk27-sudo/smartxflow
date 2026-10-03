"""Engine-first decision gate for Analysis V2.

This is the layer that turns an existing V1 engine candidate plus independent
validation evidence into FIRSAT / IZLE / UZAK_DUR. It deliberately refuses to
promote a signal just because money share is high or because an in-sample edge
cell looked profitable.

Important product rules enforced here:
- Price-Money Divergence never becomes an opposite-side bet.
- Underdog Pressure never becomes automatic ML.
- Research-only edge cells cannot create FIRSAT.
- Poly can confirm/downgrade but cannot create a bet by itself.
- DC/DNB recommendations require real provider market data.
- No-bet is a valid outcome.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .engine_first import EngineCandidate, source_engine_summary


ENGINE_DECISION_VERSION = "analysis-v2-engine-decision-1.0.0"

SUPPORTIVE_MOVES = {"CONFIRMED_MOVE", "LATE_STEAM", "EARLY_POSITION"}
WATCH_MOVES = {"ANOMALOUS_MONEY", "NO_EDGE", ""}
HARD_STOP_MOVES = {"PRICE_MONEY_DIVERGENCE"}
HOLDOUT_GOOD = {"HOLDOUT_SUPPORTED", "FORWARD_SUPPORTED"}
HOLDOUT_BAD = {"HOLDOUT_REJECTED", "FORWARD_REJECTED"}
RESEARCH_ONLY = {"RESEARCH", "RESEARCH_CANDIDATE", "HOLDOUT_INSUFFICIENT"}
CROSS_CONFLICT = {"CONFLICT", "DIRECTIONAL_CONFLICT"}
CROSS_SUPPORT = {"CROSS_CONFIRMED", "CONFIRMED", "SUPPORTED"}
POLY_CONFLICT = {"CONFLICT", "MIXED"}
REAL_MARKETS_REQUIRING_PROOF = {"DC", "DNB"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _text(value).upper()


def _number(value: Any) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    try:
        if isinstance(value, str):
            cleaned = value.replace("%", "").replace(" ", "").strip()
            if "," in cleaned and "." not in cleaned:
                cleaned = cleaned.replace(",", ".")
            elif "," in cleaned and "." in cleaned:
                cleaned = cleaned.replace(",", "")
            return float(cleaned)
        return float(value)
    except (TypeError, ValueError):
        return None


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def _movement_class(movement: Optional[Mapping[str, Any]]) -> str:
    if not movement:
        return ""
    return _upper(
        _first(movement, "primary_class", "movement_class", "class", "state")
    )


def _edge_status(edge: Optional[Mapping[str, Any]]) -> str:
    if not edge:
        return ""
    return _upper(_first(edge, "evidence_status", "status"))


def _cross_status(cross: Optional[Mapping[str, Any]]) -> str:
    if not cross:
        return ""
    return _upper(_first(cross, "status", "cross_status", "confirmation"))


def _poly_status(poly: Optional[Mapping[str, Any]]) -> str:
    if not poly:
        return "UNAVAILABLE"
    return _upper(_first(poly, "status", "poly_status", "confirmation")) or "UNAVAILABLE"


def _selected_market(selection: Optional[Mapping[str, Any]]) -> Tuple[str, str, Optional[float]]:
    if not selection:
        return "", "", None
    market = _upper(
        _first(selection, "recommended_market", "market_key", "market")
    )
    pick = _upper(
        _first(selection, "recommended_selection", "selection_code", "selection")
    )
    odds = _number(_first(selection, "recommended_odds", "odds", "price"))
    return market, pick, odds


def _real_market_proven(selection: Optional[Mapping[str, Any]], market: str) -> bool:
    if market not in REAL_MARKETS_REQUIRING_PROOF:
        return True
    if not selection:
        return False
    explicit = selection.get("real_market_data")
    if explicit is True:
        return True
    source = _upper(_first(selection, "data_source", "market_data_source", "source"))
    return source in {"PROVIDER", "BETWATCH", "REAL_PROVIDER", "SNAPSHOT"}


def _edge_matches_market(edge: Optional[Mapping[str, Any]], market: str) -> bool:
    if not edge:
        return False
    edge_market = _upper(_first(edge, "market_key", "market", "recommended_market"))
    return not edge_market or edge_market == market


@dataclass(frozen=True)
class EngineDecision:
    user_state: str
    source_engine: str
    source_engine_name: str
    source_selection: str
    recommended_market: Optional[str]
    recommended_selection: Optional[str]
    recommended_odds: Optional[float]
    movement_class: str
    edge_status: str
    cross_status: str
    poly_status: str
    reasons: Tuple[str, ...]
    risks: Tuple[str, ...]
    provisional: bool

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["engine_decision_version"] = ENGINE_DECISION_VERSION
        return payload


def decide_engine_candidate(
    candidate: EngineCandidate,
    *,
    movement: Optional[Mapping[str, Any]] = None,
    edge: Optional[Mapping[str, Any]] = None,
    market_selection: Optional[Mapping[str, Any]] = None,
    cross_market: Optional[Mapping[str, Any]] = None,
    poly: Optional[Mapping[str, Any]] = None,
    extra_risks: Sequence[str] = (),
) -> EngineDecision:
    source = source_engine_summary(candidate)
    move = _movement_class(movement)
    edge_status = _edge_status(edge)
    cross = _cross_status(cross_market)
    poly_state = _poly_status(poly)
    market, pick, price = _selected_market(market_selection)

    reasons = [f"SOURCE_{candidate.source_engine.upper()}"]
    risks = [str(item) for item in extra_risks if str(item).strip()]
    provisional = edge_status not in HOLDOUT_GOOD

    # Warning engines are diagnostic only. Never flip the side and recommend
    # its opponent merely because price and money diverge.
    if candidate.role == "WARNING":
        reasons.append("PRICE_MONEY_DIVERGENCE_WARNING")
        return EngineDecision(
            user_state="UZAK_DUR",
            source_engine=candidate.source_engine,
            source_engine_name=source["source_engine_name"],
            source_selection=candidate.source_selection,
            recommended_market=None,
            recommended_selection=None,
            recommended_odds=None,
            movement_class=move or "PRICE_MONEY_DIVERGENCE",
            edge_status=edge_status,
            cross_status=cross,
            poly_status=poly_state,
            reasons=tuple(reasons),
            risks=tuple(risks),
            provisional=True,
        )

    if move in HARD_STOP_MOVES:
        risks.append("CORE_PRICE_MONEY_DIVERGENCE")
        return EngineDecision(
            user_state="UZAK_DUR",
            source_engine=candidate.source_engine,
            source_engine_name=source["source_engine_name"],
            source_selection=candidate.source_selection,
            recommended_market=None,
            recommended_selection=None,
            recommended_odds=None,
            movement_class=move,
            edge_status=edge_status,
            cross_status=cross,
            poly_status=poly_state,
            reasons=tuple(reasons),
            risks=tuple(risks),
            provisional=True,
        )

    if cross in CROSS_CONFLICT:
        risks.append("CROSS_MARKET_CONFLICT")
        return EngineDecision(
            user_state="UZAK_DUR",
            source_engine=candidate.source_engine,
            source_engine_name=source["source_engine_name"],
            source_selection=candidate.source_selection,
            recommended_market=None,
            recommended_selection=None,
            recommended_odds=None,
            movement_class=move,
            edge_status=edge_status,
            cross_status=cross,
            poly_status=poly_state,
            reasons=tuple(reasons),
            risks=tuple(risks),
            provisional=True,
        )

    if edge_status in HOLDOUT_BAD:
        risks.append("HISTORICAL_EDGE_REJECTED_OUT_OF_SAMPLE")
        return EngineDecision(
            user_state="UZAK_DUR",
            source_engine=candidate.source_engine,
            source_engine_name=source["source_engine_name"],
            source_selection=candidate.source_selection,
            recommended_market=None,
            recommended_selection=None,
            recommended_odds=None,
            movement_class=move,
            edge_status=edge_status,
            cross_status=cross,
            poly_status=poly_state,
            reasons=tuple(reasons),
            risks=tuple(risks),
            provisional=False,
        )

    # Candidate market: direct-bet engines can fall back to their real source
    # 1X2 market. Underdog cannot; it needs a separately selected market or a
    # future explicitly validated market-selection path.
    if not market and source["direct_bet_allowed"]:
        market = candidate.source_market
        pick = candidate.source_selection
        price = candidate.trigger_odds
        reasons.append("SOURCE_MARKET_RETAINED")

    if candidate.source_engine == "underdog_pressure_v1" and not market:
        risks.append("UNDERDOG_MARKET_NOT_SELECTED")
        return EngineDecision(
            user_state="IZLE",
            source_engine=candidate.source_engine,
            source_engine_name=source["source_engine_name"],
            source_selection=candidate.source_selection,
            recommended_market=None,
            recommended_selection=None,
            recommended_odds=None,
            movement_class=move,
            edge_status=edge_status,
            cross_status=cross,
            poly_status=poly_state,
            reasons=tuple(reasons),
            risks=tuple(risks),
            provisional=True,
        )

    if market and not _real_market_proven(market_selection, market):
        risks.append(f"{market}_REAL_MARKET_DATA_REQUIRED")
        market = pick = ""
        price = None

    if not market or not pick:
        risks.append("NO_ACTIONABLE_MARKET")
        return EngineDecision(
            user_state="IZLE",
            source_engine=candidate.source_engine,
            source_engine_name=source["source_engine_name"],
            source_selection=candidate.source_selection,
            recommended_market=None,
            recommended_selection=None,
            recommended_odds=None,
            movement_class=move,
            edge_status=edge_status,
            cross_status=cross,
            poly_status=poly_state,
            reasons=tuple(reasons),
            risks=tuple(risks),
            provisional=True,
        )

    if not _edge_matches_market(edge, market):
        risks.append("EDGE_NOT_VALIDATED_FOR_SELECTED_MARKET")

    if move in SUPPORTIVE_MOVES:
        reasons.append(f"MOVE_{move}")
    elif move == "ANOMALOUS_MONEY":
        risks.append("ANOMALOUS_MONEY_PRICE_NOT_CONFIRMED")
    else:
        risks.append("PRICE_CONFIRMATION_NOT_STRONG")

    if cross in CROSS_SUPPORT:
        reasons.append("CROSS_MARKET_SUPPORT")
    elif not cross:
        risks.append("CROSS_MARKET_UNAVAILABLE")

    if poly_state in POLY_CONFLICT:
        risks.append("POLY_CONFLICT")
    elif poly_state in {"CONFIRMED", "SUPPORTED", "POLY_CONFIRMED"}:
        reasons.append("POLY_SUPPORT")

    if edge_status in HOLDOUT_GOOD and _edge_matches_market(edge, market):
        reasons.append("OUT_OF_SAMPLE_EDGE_SUPPORTED")
    elif edge_status in RESEARCH_ONLY or not edge_status:
        risks.append("EDGE_NOT_OUT_OF_SAMPLE_VALIDATED")

    # FIRSAT requires all core layers. Poly is intentionally not required and
    # cannot create FIRSAT; a Poly conflict downgrades an otherwise valid pick.
    core_ready = (
        move in SUPPORTIVE_MOVES
        and edge_status in HOLDOUT_GOOD
        and _edge_matches_market(edge, market)
        and "POLY_CONFLICT" not in risks
        and "EDGE_NOT_VALIDATED_FOR_SELECTED_MARKET" not in risks
    )

    user_state = "FIRSAT" if core_ready else "IZLE"
    return EngineDecision(
        user_state=user_state,
        source_engine=candidate.source_engine,
        source_engine_name=source["source_engine_name"],
        source_selection=candidate.source_selection,
        recommended_market=market or None,
        recommended_selection=pick or None,
        recommended_odds=price,
        movement_class=move,
        edge_status=edge_status,
        cross_status=cross,
        poly_status=poly_state,
        reasons=tuple(dict.fromkeys(reasons)),
        risks=tuple(dict.fromkeys(risks)),
        provisional=user_state != "FIRSAT",
    )
