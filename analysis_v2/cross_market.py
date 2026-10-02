"""Analysis V2 Part 6: cross-market confirmation and context.

Team direction is confirmed only by markets that actually express that team
exposure: 1X2, DNB and real provider Double Chance. OU2.5 and BTTS are kept as
structural match context; they never manufacture home/away confirmation.

No opaque score is used. Every supporting, conflicting or unavailable market is
preserved with an explicit state and reason.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping, Optional

from .classification import ClassificationConfig, classify_market_movement
from .market_contract import get_market
from .market_selector import (
    SUPPORTIVE_CLASSES,
    build_direction_market_views,
    direction_market_selection,
    normalize_direction,
)


CROSS_MARKET_VERSION = "analysis-v2-part6-1.0.0"

STRUCTURAL_SELECTIONS = {
    "OU25": ("O", "U"),
    "BTTS": ("Y", "N"),
}


@dataclass(frozen=True)
class CrossMarketConfig:
    min_directional_confirmations: int = 2
    require_source_support: bool = True
    conflict_on_any_directional_divergence: bool = True


def _number(value: Any) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _view_state(view: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    item = dict(view or {})
    features = item.get("features") if isinstance(item.get("features"), dict) else {}
    classification = (
        item.get("classification")
        if isinstance(item.get("classification"), dict)
        else {}
    )
    current = features.get("current") if isinstance(features.get("current"), dict) else {}
    current_odds = _number(current.get("odds"))
    primary = str(classification.get("primary_class") or "NO_EDGE").upper()
    risks = list(classification.get("risk_flags") or [])

    available = current_odds is not None and current_odds > 1.0
    if not available:
        state = "UNAVAILABLE"
        reasons = ["REAL_PROVIDER_QUOTE_UNAVAILABLE"]
    elif (
        primary == "PRICE_MONEY_DIVERGENCE"
        or "RECENT_PRICE_MONEY_DIVERGENCE" in risks
    ):
        state = "DIVERGENCE"
        reasons = ["PRICE_MONEY_DIVERGENCE"]
    elif primary in SUPPORTIVE_CLASSES:
        state = "SUPPORT"
        reasons = ["PRICE_MONEY_CONFIRMED"]
    elif primary == "ANOMALOUS_MONEY":
        state = "ANOMALY"
        reasons = ["ANOMALOUS_MONEY_WATCH"]
    else:
        state = "NEUTRAL"
        reasons = ["NO_CONFIRMED_EDGE"]

    return {
        "available": available,
        "state": state,
        "current_odds": current_odds,
        "primary_class": primary,
        "risk_flags": risks,
        "reason_codes": reasons,
    }


def _structural_market(
    market_key: str,
    views: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    allowed = STRUCTURAL_SELECTIONS[market_key]
    selections = {
        selection: _view_state(views.get(selection))
        for selection in allowed
    }
    support = [
        selection
        for selection, item in selections.items()
        if item["state"] == "SUPPORT"
    ]
    divergence = [
        selection
        for selection, item in selections.items()
        if item["state"] == "DIVERGENCE"
    ]
    anomaly = [
        selection
        for selection, item in selections.items()
        if item["state"] == "ANOMALY"
    ]

    if len(support) == 1:
        dominant = support[0]
        state = "CLEAR"
    elif len(support) > 1:
        dominant = None
        state = "AMBIGUOUS"
    elif divergence:
        dominant = None
        state = "DIVERGENT"
    elif anomaly:
        dominant = None
        state = "ANOMALY"
    else:
        dominant = None
        state = "NEUTRAL"

    return {
        "market_key": market_key,
        "state": state,
        "dominant_selection": dominant,
        "supportive_selections": support,
        "divergent_selections": divergence,
        "anomalous_selections": anomaly,
        "selections": selections,
    }


def _structural_context(
    ou: Dict[str, Any],
    btts: Dict[str, Any],
) -> Dict[str, Any]:
    ou_sel = ou.get("dominant_selection")
    btts_sel = btts.get("dominant_selection")

    if ou_sel == "O" and btts_sel == "Y":
        context = "OPEN_GAME"
        reasons = ["OVER_CONFIRMED", "BTTS_YES_CONFIRMED"]
    elif ou_sel == "U" and btts_sel == "N":
        context = "LOW_EVENT"
        reasons = ["UNDER_CONFIRMED", "BTTS_NO_CONFIRMED"]
    elif ou_sel or btts_sel:
        context = "MIXED"
        reasons = ["STRUCTURAL_CONTEXT_MIXED"]
    else:
        context = "NEUTRAL"
        reasons = ["NO_CLEAR_STRUCTURAL_CONTEXT"]

    return {
        "context": context,
        "reason_codes": reasons,
        "ou25": ou,
        "btts": btts,
    }


def evaluate_cross_market(
    direction: str,
    market_views: Mapping[str, Any],
    *,
    source_market: str = "1X2",
    config: Optional[CrossMarketConfig] = None,
) -> Dict[str, Any]:
    """Reconcile directional markets and attach OU/BTTS context."""
    cfg = config or CrossMarketConfig()
    normalized = normalize_direction(direction)
    mapping = direction_market_selection(normalized)
    source_market = str(source_market or "1X2").strip().upper()
    if source_market not in mapping:
        raise ValueError(
            f"source market {source_market!r} cannot express direction {normalized!r}"
        )

    directional = {}
    for market_key, selection_code in mapping.items():
        state = _view_state(market_views.get(market_key))
        directional[market_key] = {
            "market_key": market_key,
            "selection_code": selection_code,
            **state,
        }

    supportive = [
        market
        for market, item in directional.items()
        if item["state"] == "SUPPORT"
    ]
    divergent = [
        market
        for market, item in directional.items()
        if item["state"] == "DIVERGENCE"
    ]
    anomalous = [
        market
        for market, item in directional.items()
        if item["state"] == "ANOMALY"
    ]
    unavailable = [
        market
        for market, item in directional.items()
        if item["state"] == "UNAVAILABLE"
    ]

    source = directional[source_market]
    risk_flags = []
    if divergent:
        risk_flags.append("DIRECTIONAL_MARKET_DIVERGENCE")
    if anomalous:
        risk_flags.append("DIRECTIONAL_MARKET_ANOMALY")
    if cfg.require_source_support and source["state"] != "SUPPORT":
        risk_flags.append("SOURCE_MARKET_NOT_SUPPORTIVE")

    directional_status = "NO_CONFIRMATION"
    reason_codes = []

    if (
        cfg.conflict_on_any_directional_divergence
        and divergent
    ):
        directional_status = "CONFLICT"
        reason_codes = ["SAME_DIRECTION_MARKET_CONFLICT"]
    elif cfg.require_source_support and source["state"] != "SUPPORT":
        directional_status = "NO_CONFIRMATION"
        if source["state"] == "UNAVAILABLE":
            reason_codes = ["SOURCE_MARKET_UNAVAILABLE"]
        elif source["state"] == "ANOMALY":
            reason_codes = ["SOURCE_MARKET_ANOMALY_WATCH_ONLY"]
        else:
            reason_codes = ["SOURCE_MARKET_NOT_CONFIRMED"]
    elif len(supportive) >= cfg.min_directional_confirmations:
        directional_status = "CROSS_CONFIRMED"
        reason_codes = ["MULTI_MARKET_DIRECTION_CONFIRMED"]
    elif len(supportive) == 1:
        directional_status = "SINGLE_MARKET_ONLY"
        reason_codes = ["ONLY_ONE_DIRECTIONAL_MARKET_CONFIRMED"]
    else:
        directional_status = "NO_CONFIRMATION"
        reason_codes = ["NO_DIRECTIONAL_MARKET_CONFIRMED"]

    ou_views = market_views.get("OU25")
    btts_views = market_views.get("BTTS")
    ou = _structural_market(
        "OU25",
        ou_views if isinstance(ou_views, Mapping) else {},
    )
    btts = _structural_market(
        "BTTS",
        btts_views if isinstance(btts_views, Mapping) else {},
    )
    structural = _structural_context(ou, btts)

    structural_divergence = (
        bool(ou["divergent_selections"])
        or bool(btts["divergent_selections"])
    )
    structural_anomaly = (
        bool(ou["anomalous_selections"])
        or bool(btts["anomalous_selections"])
    )
    if structural_divergence:
        risk_flags.append("STRUCTURAL_MARKET_DIVERGENCE")
    if structural_anomaly:
        risk_flags.append("STRUCTURAL_MARKET_ANOMALY")

    return {
        "cross_market_version": CROSS_MARKET_VERSION,
        "direction": normalized,
        "source_market": source_market,
        "status": directional_status,
        "reason_codes": reason_codes,
        "risk_flags": risk_flags,
        "supportive_directional_markets": supportive,
        "divergent_directional_markets": divergent,
        "anomalous_directional_markets": anomalous,
        "unavailable_directional_markets": unavailable,
        "directional_markets": directional,
        "structural_context": structural,
        "config_snapshot": asdict(cfg),
    }


def build_cross_market_views(
    history_client,
    *,
    match_id_hash: str,
    direction: str,
    as_of: Any,
    kickoff_utc: Any = None,
    classification_config: Optional[ClassificationConfig] = None,
    anchor_tolerance_minutes: int = 60,
    current_tolerance_minutes: int = 60,
) -> Dict[str, Any]:
    """Load real directional and structural selections from Part 3."""
    views: Dict[str, Any] = build_direction_market_views(
        history_client,
        match_id_hash=match_id_hash,
        direction=direction,
        as_of=as_of,
        kickoff_utc=kickoff_utc,
        classification_config=classification_config,
        anchor_tolerance_minutes=anchor_tolerance_minutes,
        current_tolerance_minutes=current_tolerance_minutes,
    )

    for market_key, selections in STRUCTURAL_SELECTIONS.items():
        contract = get_market(market_key)
        market_views: Dict[str, Any] = {}
        for selection_code in selections:
            if selection_code not in contract.selections:
                raise ValueError(
                    f"{selection_code} is not a real selection in {market_key}"
                )
            features = history_client.build_features(
                match_id_hash=match_id_hash,
                market_key=market_key,
                selection_code=selection_code,
                as_of=as_of,
                kickoff_utc=kickoff_utc,
                anchor_tolerance_minutes=anchor_tolerance_minutes,
                current_tolerance_minutes=current_tolerance_minutes,
            )
            classification = classify_market_movement(
                features,
                classification_config,
            )
            market_views[selection_code] = {
                "selection_code": selection_code,
                "features": features,
                "classification": classification,
            }
        views[market_key] = market_views

    return views


def evaluate_cross_market_from_history(
    history_client,
    *,
    match_id_hash: str,
    direction: str,
    as_of: Any,
    kickoff_utc: Any = None,
    source_market: str = "1X2",
    classification_config: Optional[ClassificationConfig] = None,
    cross_market_config: Optional[CrossMarketConfig] = None,
    anchor_tolerance_minutes: int = 60,
    current_tolerance_minutes: int = 60,
) -> Dict[str, Any]:
    views = build_cross_market_views(
        history_client,
        match_id_hash=match_id_hash,
        direction=direction,
        as_of=as_of,
        kickoff_utc=kickoff_utc,
        classification_config=classification_config,
        anchor_tolerance_minutes=anchor_tolerance_minutes,
        current_tolerance_minutes=current_tolerance_minutes,
    )
    return evaluate_cross_market(
        direction,
        views,
        source_market=source_market,
        config=cross_market_config,
    )


def reconcile_market_selection(
    selection_result: Mapping[str, Any],
    cross_market_result: Mapping[str, Any],
) -> Dict[str, Any]:
    """Apply Part 6 directional conflicts to the Part 5 recommendation."""
    result = dict(selection_result)
    cross = dict(cross_market_result)
    result["cross_market"] = {
        "status": cross.get("status"),
        "reason_codes": list(cross.get("reason_codes") or []),
        "risk_flags": list(cross.get("risk_flags") or []),
        "supportive_directional_markets": list(
            cross.get("supportive_directional_markets") or []
        ),
        "divergent_directional_markets": list(
            cross.get("divergent_directional_markets") or []
        ),
        "structural_context": (
            (cross.get("structural_context") or {}).get("context")
        ),
    }

    if result.get("decision") != "RECOMMEND":
        return result

    if cross.get("status") in {"CONFLICT", "NO_CONFIRMATION"}:
        result["decision"] = "WATCH_ONLY"
        result["recommended_market"] = None
        result["recommended_selection"] = None
        result["recommended_odds"] = None
        result["protection_level"] = None
        reasons = list(result.get("reason_codes") or [])
        block_reason = (
            "CROSS_MARKET_DIRECTIONAL_CONFLICT"
            if cross.get("status") == "CONFLICT"
            else "CROSS_MARKET_NOT_CONFIRMED"
        )
        if block_reason not in reasons:
            reasons.append(block_reason)
        result["reason_codes"] = reasons

    return result


def apply_cross_market_to_trigger(
    trigger_payload: Mapping[str, Any],
    cross_market_result: Mapping[str, Any],
) -> Dict[str, Any]:
    """Persist the Part 6 trace inside the immutable Part 2 trigger."""
    payload = dict(trigger_payload)
    cross = dict(cross_market_result)

    engine_reason = dict(payload.get("engine_reason") or {})
    engine_reason["cross_market"] = {
        "status": cross.get("status"),
        "reason_codes": list(cross.get("reason_codes") or []),
        "risk_flags": list(cross.get("risk_flags") or []),
        "supportive_directional_markets": list(
            cross.get("supportive_directional_markets") or []
        ),
        "divergent_directional_markets": list(
            cross.get("divergent_directional_markets") or []
        ),
        "structural_context": (
            (cross.get("structural_context") or {}).get("context")
        ),
    }
    payload["engine_reason"] = engine_reason

    config_snapshot = dict(payload.get("config_snapshot") or {})
    config_snapshot["cross_market"] = dict(
        cross.get("config_snapshot") or {}
    )
    payload["config_snapshot"] = config_snapshot

    features = dict(payload.get("features") or {})
    features["cross_market"] = {
        "cross_market_version": cross.get("cross_market_version"),
        "directional_markets": cross.get("directional_markets") or {},
        "structural_context": cross.get("structural_context") or {},
    }
    payload["features"] = features
    return payload
