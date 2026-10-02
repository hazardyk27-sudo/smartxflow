"""Analysis V2 Part 8: explainable confidence and user-state engine.

There is deliberately no opaque 0-10 score. The engine exposes six separate
components (price, money, timing, cross-market, Poly and risk) and derives the
user-facing FIRSAT / IZLE / UZAK_DUR state through explicit gates.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping, Optional


EXPLAINABLE_CONFIDENCE_VERSION = "analysis-v2-part8-1.0.0"
SUPPORTIVE_CLASSES = {"CONFIRMED_MOVE", "LATE_STEAM", "EARLY_POSITION"}

LEVEL_LABELS_TR = {
    "STRONG": "Güçlü",
    "MEDIUM": "Orta",
    "WEAK": "Zayıf",
    "NEUTRAL": "Nötr",
    "MIXED": "Karışık",
    "CONFLICT": "Çelişki",
    "UNAVAILABLE": "Veri yok",
}

USER_STATE_LABELS_TR = {
    "FIRSAT": "Fırsat",
    "IZLE": "İzle",
    "UZAK_DUR": "Uzak Dur",
}


@dataclass(frozen=True)
class ExplainableConfidenceConfig:
    strong_price_drop_pct: float = 5.0
    medium_price_drop_pct: float = 3.0
    strong_money_added: float = 5000.0
    medium_money_added: float = 1000.0
    strong_money_pct_delta: float = 15.0
    medium_money_pct_delta: float = 5.0
    opportunity_max_low_risks: int = 1


def _number(value: Any) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _component(level: str, reason_codes, evidence: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        "level": level,
        "label": LEVEL_LABELS_TR[level],
        "reason_codes": list(reason_codes or []),
        "evidence": dict(evidence or {}),
    }


def _decision_evidence(classification: Mapping[str, Any]) -> Dict[str, Any]:
    states = classification.get("window_states") or {}
    decision_window = classification.get("decision_window")
    if decision_window and isinstance(states.get(decision_window), Mapping):
        return dict(states[decision_window])
    for label in ("30m", "2h", "6h", "open"):
        if isinstance(states.get(label), Mapping) and states[label].get("available"):
            return dict(states[label])
    return {}


def _price_component(
    classification: Mapping[str, Any],
    config: ExplainableConfidenceConfig,
) -> Dict[str, Any]:
    primary = str(classification.get("primary_class") or "NO_EDGE").upper()
    evidence = _decision_evidence(classification)
    drop = _number(evidence.get("odds_drop_pct"))
    price_state = str(evidence.get("price_state") or "UNKNOWN")

    if primary == "PRICE_MONEY_DIVERGENCE" or price_state == "DRIFTED":
        level = "CONFLICT"
        reasons = ["PRICE_MOVES_AGAINST_MONEY"]
    elif drop is None:
        level = "UNAVAILABLE"
        reasons = ["PRICE_EVIDENCE_UNAVAILABLE"]
    elif drop >= config.strong_price_drop_pct:
        level = "STRONG"
        reasons = ["MEANINGFUL_PRICE_SHORTENING"]
    elif drop >= config.medium_price_drop_pct:
        level = "MEDIUM"
        reasons = ["MODERATE_PRICE_SHORTENING"]
    elif drop > 0:
        level = "WEAK"
        reasons = ["SLIGHT_PRICE_SHORTENING"]
    elif abs(drop) <= 1.0:
        level = "WEAK"
        reasons = ["PRICE_FLAT"]
    else:
        level = "CONFLICT"
        reasons = ["PRICE_DRIFTING"]

    return _component(
        level,
        reasons,
        {
            "decision_window": classification.get("decision_window"),
            "odds_drop_pct": drop,
            "price_state": price_state,
            "primary_class": primary,
        },
    )


def _money_component(
    classification: Mapping[str, Any],
    config: ExplainableConfidenceConfig,
) -> Dict[str, Any]:
    evidence = _decision_evidence(classification)
    state = str(evidence.get("money_state") or "UNKNOWN")
    added = _number(evidence.get("money_added"))
    pct_delta = _number(evidence.get("pct_delta"))

    if state == "DOWN":
        level = "CONFLICT"
        reasons = ["MONEY_FLOW_REVERSED"]
    elif state == "UP":
        strong = (
            (added is not None and added >= config.strong_money_added)
            or (pct_delta is not None and pct_delta >= config.strong_money_pct_delta)
        )
        medium = (
            (added is not None and added >= config.medium_money_added)
            or (pct_delta is not None and pct_delta >= config.medium_money_pct_delta)
        )
        if strong:
            level = "STRONG"
            reasons = ["LARGE_CONFIRMED_MONEY_INFLOW"]
        elif medium:
            level = "MEDIUM"
            reasons = ["MEANINGFUL_MONEY_INFLOW"]
        else:
            level = "WEAK"
            reasons = ["SMALL_MONEY_INFLOW"]
    elif state == "FLAT":
        level = "WEAK"
        reasons = ["MONEY_FLOW_FLAT"]
    else:
        level = "UNAVAILABLE"
        reasons = ["MONEY_EVIDENCE_UNAVAILABLE"]

    return _component(
        level,
        reasons,
        {
            "decision_window": classification.get("decision_window"),
            "money_state": state,
            "money_added": added,
            "pct_delta": pct_delta,
            "current_amount": _number(evidence.get("current_amount")),
            "current_pct": _number(evidence.get("current_pct")),
        },
    )


def _timing_component(
    classification: Mapping[str, Any],
    movement_features: Mapping[str, Any],
) -> Dict[str, Any]:
    primary = str(classification.get("primary_class") or "NO_EDGE").upper()
    window = classification.get("decision_window")
    hours = _number(movement_features.get("hours_before_kickoff"))

    if primary == "LATE_STEAM":
        level = "STRONG"
        reasons = ["LATE_STEAM_TIMING"]
    elif primary == "EARLY_POSITION":
        level = "MEDIUM"
        reasons = ["EARLY_POSITION_TIMING"]
    elif window in {"30m", "2h"}:
        level = "STRONG"
        reasons = ["RECENT_DECISION_WINDOW"]
    elif window == "6h":
        level = "MEDIUM"
        reasons = ["MID_RANGE_DECISION_WINDOW"]
    elif window == "open":
        level = "WEAK"
        reasons = ["OPENING_ONLY_TIMING"]
    else:
        level = "UNAVAILABLE"
        reasons = ["TIMING_EVIDENCE_UNAVAILABLE"]

    return _component(
        level,
        reasons,
        {
            "primary_class": primary,
            "decision_window": window,
            "hours_before_kickoff": hours,
        },
    )


def _cross_component(cross: Mapping[str, Any]) -> Dict[str, Any]:
    status = str(cross.get("status") or "NO_CONFIRMATION").upper()
    if status == "CROSS_CONFIRMED":
        level = "STRONG"
        reasons = ["MULTI_MARKET_DIRECTION_CONFIRMED"]
    elif status == "SINGLE_MARKET_ONLY":
        level = "WEAK"
        reasons = ["ONLY_ONE_DIRECTIONAL_MARKET"]
    elif status == "CONFLICT":
        level = "CONFLICT"
        reasons = ["DIRECTIONAL_MARKETS_CONFLICT"]
    elif status == "NO_CONFIRMATION":
        level = "WEAK"
        reasons = ["CROSS_MARKET_NOT_CONFIRMED"]
    else:
        level = "UNAVAILABLE"
        reasons = ["CROSS_MARKET_UNAVAILABLE"]

    structural = cross.get("structural_context") or {}
    return _component(
        level,
        reasons,
        {
            "status": status,
            "supportive_directional_markets": list(
                cross.get("supportive_directional_markets") or []
            ),
            "divergent_directional_markets": list(
                cross.get("divergent_directional_markets") or []
            ),
            "structural_context": structural.get("context"),
        },
    )


def _poly_component(poly: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not isinstance(poly, Mapping) or not poly:
        return _component("UNAVAILABLE", ["POLY_NOT_ATTACHED"], {})

    status = str(poly.get("status") or "POLY_UNAVAILABLE").upper()
    if status == "POLY_CONFIRMED":
        level = "STRONG"
        reasons = ["POLY_MULTI_COMPONENT_SUPPORT"]
    elif status == "POLY_CONFLICT":
        level = "CONFLICT"
        reasons = ["POLY_MULTI_COMPONENT_CONFLICT"]
    elif status == "POLY_MIXED":
        level = "MIXED"
        reasons = ["POLY_INTERNAL_DISAGREEMENT"]
    elif status == "POLY_NEUTRAL":
        level = "NEUTRAL"
        reasons = ["POLY_NOT_DECISIVE"]
    else:
        level = "UNAVAILABLE"
        reasons = ["POLY_UNAVAILABLE"]

    return _component(
        level,
        reasons,
        {
            "status": status,
            "supporting_components": list(poly.get("supporting_components") or []),
            "conflicting_components": list(poly.get("conflicting_components") or []),
        },
    )


def _risk_item(code: str, severity: str, source: str) -> Dict[str, str]:
    return {"code": code, "severity": severity, "source": source}


def _risk_component(
    classification: Mapping[str, Any],
    selector: Mapping[str, Any],
    cross: Mapping[str, Any],
    poly: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    items = []
    context = []
    primary = str(classification.get("primary_class") or "NO_EDGE").upper()
    selector_reasons = set(selector.get("reason_codes") or [])
    cross_status = str(cross.get("status") or "NO_CONFIRMATION").upper()
    cross_risks = set(cross.get("risk_flags") or [])
    poly_status = str((poly or {}).get("status") or "POLY_UNAVAILABLE").upper()

    if primary == "PRICE_MONEY_DIVERGENCE":
        items.append(_risk_item("CORE_PRICE_MONEY_DIVERGENCE", "HARD", "classification"))
    if "RECENT_PRICE_MONEY_DIVERGENCE" in set(classification.get("risk_flags") or []):
        items.append(_risk_item("RECENT_PRICE_MONEY_DIVERGENCE", "HARD", "classification"))
    if primary == "ANOMALOUS_MONEY":
        items.append(_risk_item("ANOMALOUS_MONEY_WATCH", "MEDIUM", "classification"))
    if primary == "NO_EDGE":
        items.append(_risk_item("CORE_NO_EDGE", "MEDIUM", "classification"))

    for code in (
        "SOURCE_DIVERGENCE",
        "SOURCE_RECENT_DIVERGENCE",
        "CROSS_MARKET_DIRECTIONAL_CONFLICT",
    ):
        if code in selector_reasons:
            items.append(_risk_item(code, "HARD", "market_selector"))

    if cross_status == "CONFLICT":
        items.append(_risk_item("CROSS_MARKET_CONFLICT", "HARD", "cross_market"))
    elif cross_status == "NO_CONFIRMATION":
        items.append(_risk_item("CROSS_MARKET_NO_CONFIRMATION", "MEDIUM", "cross_market"))
    elif cross_status == "SINGLE_MARKET_ONLY":
        items.append(_risk_item("SINGLE_MARKET_ONLY", "MEDIUM", "cross_market"))

    if "STRUCTURAL_MARKET_DIVERGENCE" in cross_risks:
        items.append(_risk_item("STRUCTURAL_MARKET_DIVERGENCE", "MEDIUM", "cross_market"))
    if "DIRECTIONAL_MARKET_ANOMALY" in cross_risks:
        items.append(_risk_item("DIRECTIONAL_MARKET_ANOMALY", "MEDIUM", "cross_market"))
    if "STRUCTURAL_MARKET_ANOMALY" in cross_risks:
        items.append(_risk_item("STRUCTURAL_MARKET_ANOMALY", "LOW", "cross_market"))

    if poly_status == "POLY_CONFLICT":
        items.append(_risk_item("POLY_CONFLICT", "MEDIUM", "poly"))
    elif poly_status == "POLY_MIXED":
        items.append(_risk_item("POLY_MIXED", "MEDIUM", "poly"))

    if selector.get("decision") != "RECOMMEND" and not any(
        item["source"] == "market_selector" and item["severity"] == "HARD"
        for item in items
    ):
        items.append(
            _risk_item(
                "NO_ACTIVE_MARKET_RECOMMENDATION",
                "MEDIUM",
                "market_selector",
            )
        )

    if "VERY_HIGH_MONEY_SHARE_CONTEXT_ONLY" in set(classification.get("risk_flags") or []):
        context.append("VERY_HIGH_MONEY_SHARE_CONTEXT_ONLY")

    deduped = []
    seen = set()
    for item in items:
        if item["code"] in seen:
            continue
        seen.add(item["code"])
        deduped.append(item)

    hard = [item for item in deduped if item["severity"] == "HARD"]
    medium = [item for item in deduped if item["severity"] == "MEDIUM"]
    low = [item for item in deduped if item["severity"] == "LOW"]
    if hard:
        level = "CONFLICT"
    elif medium:
        level = "MEDIUM"
    elif low:
        level = "WEAK"
    else:
        level = "NEUTRAL"

    return _component(
        level,
        [item["code"] for item in deduped] or ["NO_MATERIAL_RISK"],
        {
            "risk_count": len(deduped),
            "hard_count": len(hard),
            "medium_count": len(medium),
            "low_count": len(low),
            "items": deduped,
            "context_flags": context,
        },
    )


def build_explainable_confidence(
    *,
    movement_features: Mapping[str, Any],
    classification: Mapping[str, Any],
    selector_result: Mapping[str, Any],
    cross_market_result: Mapping[str, Any],
    poly_result: Optional[Mapping[str, Any]] = None,
    config: Optional[ExplainableConfidenceConfig] = None,
) -> Dict[str, Any]:
    """Build explainable components and the gated user-facing state."""
    cfg = config or ExplainableConfidenceConfig()

    price = _price_component(classification, cfg)
    money = _money_component(classification, cfg)
    timing = _timing_component(classification, movement_features)
    cross = _cross_component(cross_market_result)
    poly = _poly_component(poly_result)
    risk = _risk_component(
        classification,
        selector_result,
        cross_market_result,
        poly_result,
    )

    primary = str(classification.get("primary_class") or "NO_EDGE").upper()
    selector_decision = str(
        selector_result.get("decision") or "WATCH_ONLY"
    ).upper()
    cross_status = str(
        cross_market_result.get("status") or "NO_CONFIRMATION"
    ).upper()
    risk_evidence = risk["evidence"]

    hard_risk = risk_evidence["hard_count"] > 0
    medium_risk = risk_evidence["medium_count"] > 0
    too_many_low_risks = (
        risk_evidence["low_count"] > cfg.opportunity_max_low_risks
    )

    if hard_risk:
        user_state = "UZAK_DUR"
        state_reasons = ["HARD_MARKET_CONTRADICTION"]
    elif (
        selector_decision != "RECOMMEND"
        or primary not in SUPPORTIVE_CLASSES
        or cross_status != "CROSS_CONFIRMED"
        or medium_risk
        or too_many_low_risks
    ):
        user_state = "IZLE"
        state_reasons = ["CONFIRMATION_INCOMPLETE_OR_RISK_PRESENT"]
    else:
        user_state = "FIRSAT"
        state_reasons = ["CORE_AND_CROSS_MARKET_CONFIRMED"]

    components = {
        "price_confirmation": price,
        "money_flow": money,
        "timing": timing,
        "cross_market": cross,
        "poly": poly,
        "risk": risk,
    }

    return {
        "explainable_confidence_version": EXPLAINABLE_CONFIDENCE_VERSION,
        "user_state": user_state,
        "user_state_label": USER_STATE_LABELS_TR[user_state],
        "state_reason_codes": state_reasons,
        "recommended_market": selector_result.get("recommended_market"),
        "recommended_selection": selector_result.get("recommended_selection"),
        "recommended_odds": selector_result.get("recommended_odds"),
        "components": components,
        "risk_count": risk_evidence["risk_count"],
        "config_snapshot": asdict(cfg),
    }


def apply_explainable_confidence_to_trigger(
    trigger_payload: Mapping[str, Any],
    confidence_result: Mapping[str, Any],
) -> Dict[str, Any]:
    """Freeze the Part 8 explanation inside the Part 2 immutable trigger."""
    payload = dict(trigger_payload)
    confidence = dict(confidence_result)

    engine_reason = dict(payload.get("engine_reason") or {})
    engine_reason["explainable_confidence"] = {
        "user_state": confidence.get("user_state"),
        "state_reason_codes": list(
            confidence.get("state_reason_codes") or []
        ),
        "risk_count": confidence.get("risk_count"),
    }
    payload["engine_reason"] = engine_reason

    config_snapshot = dict(payload.get("config_snapshot") or {})
    config_snapshot["explainable_confidence"] = dict(
        confidence.get("config_snapshot") or {}
    )
    payload["config_snapshot"] = config_snapshot

    features = dict(payload.get("features") or {})
    features["explainable_confidence"] = {
        "version": confidence.get("explainable_confidence_version"),
        "user_state": confidence.get("user_state"),
        "components": confidence.get("components") or {},
    }
    payload["features"] = features
    return payload
