"""Analysis V2 Part 4: transparent price-money movement classifier.

The classifier is intentionally descriptive. It does not choose a betting
market and it never treats a high money percentage by itself as confirmation.

Core rule:
    money up + odds down -> price-confirmed movement
    money up + odds up   -> price-money divergence warning
    unusually large money + flat price -> anomalous-money watch
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Optional, Tuple


CLASSIFIER_VERSION = "analysis-v2-part4-1.0.0"
WINDOW_ORDER = ("30m", "2h", "6h", "open")


@dataclass(frozen=True)
class ClassificationConfig:
    min_market_volume: float = 5000.0
    min_money_added: float = 500.0
    confirmed_price_drop_pct: float = 5.0
    divergence_price_rise_pct: float = 5.0
    flat_price_band_pct: float = 1.0
    anomalous_money_added: float = 5000.0
    anomalous_selection_amount: float = 10000.0
    late_steam_hours_before_kickoff: float = 2.0
    late_steam_price_drop_pct: float = 3.0
    late_steam_money_added: float = 1000.0
    early_position_hours_before_kickoff: float = 24.0
    early_position_price_drop_pct: float = 3.0
    early_position_money_added: float = 1000.0
    decision_window_preference: Tuple[str, ...] = ("2h", "6h", "30m", "open")


def _number(value: Any) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _point(features: Dict[str, Any], label: str) -> Optional[Dict[str, Any]]:
    point = features.get("opening") if label == "open" else (features.get("anchors") or {}).get(label)
    return point if isinstance(point, dict) and point else None


def _movement(features: Dict[str, Any], label: str) -> Optional[Dict[str, Any]]:
    move = (features.get("movement") or {}).get(label)
    return move if isinstance(move, dict) and move else None


def _window_evidence(
    features: Dict[str, Any],
    label: str,
    config: ClassificationConfig,
) -> Dict[str, Any]:
    current = features.get("current") or {}
    base = _point(features, label)
    move = _movement(features, label)
    evidence: Dict[str, Any] = {
        "window": label,
        "available": bool(base and move and current),
        "state": "NO_EDGE",
        "price_state": "UNKNOWN",
        "money_state": "UNKNOWN",
        "market_volume_ok": False,
        "odds_drop_pct": None,
        "money_added": None,
        "pct_delta": None,
        "current_amount": _number(current.get("amount")),
        "current_pct": _number(current.get("pct")),
        "current_market_volume": _number(current.get("market_volume")),
        "reason_codes": [],
    }
    if not evidence["available"]:
        evidence["reason_codes"] = ["WINDOW_UNAVAILABLE"]
        return evidence

    odds_drop = _number(move.get("odds_drop_pct"))
    money_added = _number(move.get("amount_delta"))
    evidence["odds_drop_pct"] = odds_drop
    evidence["money_added"] = money_added
    evidence["pct_delta"] = _number(move.get("pct_delta"))
    market_volume = evidence["current_market_volume"]
    evidence["market_volume_ok"] = (
        market_volume is not None and market_volume >= config.min_market_volume
    )

    if odds_drop is None:
        evidence["price_state"] = "UNKNOWN"
    elif odds_drop >= config.confirmed_price_drop_pct:
        evidence["price_state"] = "SHORTENED"
    elif odds_drop <= -config.divergence_price_rise_pct:
        evidence["price_state"] = "DRIFTED"
    elif abs(odds_drop) <= config.flat_price_band_pct:
        evidence["price_state"] = "FLAT"
    elif odds_drop > 0:
        evidence["price_state"] = "SLIGHTLY_SHORTER"
    else:
        evidence["price_state"] = "SLIGHTLY_HIGHER"

    if money_added is None:
        evidence["money_state"] = "UNKNOWN"
    elif money_added >= config.min_money_added:
        evidence["money_state"] = "UP"
    elif money_added <= -config.min_money_added:
        evidence["money_state"] = "DOWN"
    else:
        evidence["money_state"] = "FLAT"

    if evidence["market_volume_ok"] and evidence["money_state"] == "UP":
        if odds_drop is not None and odds_drop >= config.confirmed_price_drop_pct:
            evidence["state"] = "CONFIRMED_MOVE"
            evidence["reason_codes"] = ["MONEY_UP", "PRICE_SHORTENED"]
            return evidence
        if odds_drop is not None and odds_drop <= -config.divergence_price_rise_pct:
            evidence["state"] = "PRICE_MONEY_DIVERGENCE"
            evidence["reason_codes"] = ["MONEY_UP", "PRICE_DRIFTED"]
            return evidence
        current_amount = evidence["current_amount"]
        extraordinary_money = (
            money_added is not None
            and (
                money_added >= config.anomalous_money_added
                or (
                    current_amount is not None
                    and current_amount >= config.anomalous_selection_amount
                    and money_added >= config.min_money_added
                )
            )
        )
        if (
            extraordinary_money
            and odds_drop is not None
            and abs(odds_drop) <= config.flat_price_band_pct
        ):
            evidence["state"] = "ANOMALOUS_MONEY"
            evidence["reason_codes"] = ["UNUSUALLY_LARGE_MONEY", "PRICE_NOT_REACTING"]
            return evidence

    evidence["reason_codes"] = ["NO_PRICE_MONEY_EDGE"]
    return evidence


def _first_available(
    window_states: Dict[str, Dict[str, Any]],
    preference: Iterable[str],
) -> Optional[Dict[str, Any]]:
    for label in preference:
        item = window_states.get(label)
        if item and item.get("available"):
            return item
    return None


def _late_steam(
    features: Dict[str, Any],
    window_states: Dict[str, Dict[str, Any]],
    config: ClassificationConfig,
) -> bool:
    hours = _number(features.get("hours_before_kickoff"))
    item = window_states.get("30m") or {}
    if hours is None or hours < 0 or hours > config.late_steam_hours_before_kickoff:
        return False
    return (
        item.get("market_volume_ok") is True
        and _number(item.get("money_added")) is not None
        and item["money_added"] >= config.late_steam_money_added
        and _number(item.get("odds_drop_pct")) is not None
        and item["odds_drop_pct"] >= config.late_steam_price_drop_pct
    )


def _early_position(
    features: Dict[str, Any],
    window_states: Dict[str, Dict[str, Any]],
    config: ClassificationConfig,
) -> bool:
    hours = _number(features.get("hours_before_kickoff"))
    if hours is None or hours < config.early_position_hours_before_kickoff:
        return False
    for label in ("6h", "open"):
        item = window_states.get(label) or {}
        if not item.get("available") or item.get("market_volume_ok") is not True:
            continue
        money_added = _number(item.get("money_added"))
        odds_drop = _number(item.get("odds_drop_pct"))
        if (
            money_added is not None
            and money_added >= config.early_position_money_added
            and odds_drop is not None
            and odds_drop >= config.early_position_price_drop_pct
        ):
            return True
    return False


def classify_market_movement(
    features: Dict[str, Any],
    config: Optional[ClassificationConfig] = None,
) -> Dict[str, Any]:
    cfg = config or ClassificationConfig()
    current = features.get("current")
    if not isinstance(current, dict) or not current:
        return {
            "classifier_version": CLASSIFIER_VERSION,
            "primary_class": "NO_EDGE",
            "base_state": "NO_EDGE",
            "decision_window": None,
            "risk_flags": ["CURRENT_SNAPSHOT_MISSING"],
            "reason_codes": ["INSUFFICIENT_CURRENT_DATA"],
            "window_states": {},
            "config_snapshot": asdict(cfg),
        }

    window_states = {
        label: _window_evidence(features, label, cfg)
        for label in WINDOW_ORDER
    }
    decision = _first_available(window_states, cfg.decision_window_preference)
    recent = _first_available(window_states, ("30m", "2h", "6h", "open"))

    risk_flags = []
    if recent and recent.get("state") == "PRICE_MONEY_DIVERGENCE":
        risk_flags.append("RECENT_PRICE_MONEY_DIVERGENCE")

    current_pct = _number(current.get("pct"))
    if current_pct is not None and current_pct >= 90:
        risk_flags.append("VERY_HIGH_MONEY_SHARE_CONTEXT_ONLY")

    late = _late_steam(features, window_states, cfg)
    early = _early_position(features, window_states, cfg)

    if recent and recent.get("state") == "PRICE_MONEY_DIVERGENCE":
        primary = "PRICE_MONEY_DIVERGENCE"
        reason_codes = list(recent.get("reason_codes") or [])
        decision_window = recent.get("window")
        base_state = "PRICE_MONEY_DIVERGENCE"
    elif late:
        primary = "LATE_STEAM"
        item = window_states["30m"]
        reason_codes = ["LATE_WINDOW", "MONEY_UP", "PRICE_SHORTENED"]
        decision_window = "30m"
        base_state = item.get("state")
    elif decision and decision.get("state") == "PRICE_MONEY_DIVERGENCE":
        primary = "PRICE_MONEY_DIVERGENCE"
        reason_codes = list(decision.get("reason_codes") or [])
        decision_window = decision.get("window")
        base_state = "PRICE_MONEY_DIVERGENCE"
    elif early:
        primary = "EARLY_POSITION"
        item = _first_available(window_states, ("6h", "open"))
        reason_codes = ["EARLY_WINDOW", "MONEY_UP", "PRICE_SHORTENED"]
        decision_window = item.get("window") if item else None
        base_state = item.get("state") if item else "CONFIRMED_MOVE"
    elif decision and decision.get("state") == "CONFIRMED_MOVE":
        primary = "CONFIRMED_MOVE"
        reason_codes = list(decision.get("reason_codes") or [])
        decision_window = decision.get("window")
        base_state = "CONFIRMED_MOVE"
    elif decision and decision.get("state") == "ANOMALOUS_MONEY":
        primary = "ANOMALOUS_MONEY"
        reason_codes = list(decision.get("reason_codes") or [])
        decision_window = decision.get("window")
        base_state = "ANOMALOUS_MONEY"
    elif recent and recent.get("state") == "ANOMALOUS_MONEY":
        primary = "ANOMALOUS_MONEY"
        reason_codes = list(recent.get("reason_codes") or [])
        decision_window = recent.get("window")
        base_state = "ANOMALOUS_MONEY"
    else:
        primary = "NO_EDGE"
        reason_codes = (
            list(decision.get("reason_codes") or [])
            if decision
            else ["INSUFFICIENT_HISTORY"]
        )
        decision_window = decision.get("window") if decision else None
        base_state = decision.get("state") if decision else "NO_EDGE"

    return {
        "classifier_version": CLASSIFIER_VERSION,
        "primary_class": primary,
        "base_state": base_state,
        "decision_window": decision_window,
        "risk_flags": risk_flags,
        "reason_codes": reason_codes,
        "window_states": window_states,
        "config_snapshot": asdict(cfg),
    }


def classification_to_signal_metadata(
    classification: Dict[str, Any],
) -> Dict[str, Any]:
    primary = classification.get("primary_class") or "NO_EDGE"
    return {
        "engine_reason": {
            "primary_class": primary,
            "base_state": classification.get("base_state"),
            "decision_window": classification.get("decision_window"),
            "reason_codes": list(classification.get("reason_codes") or []),
            "risk_flags": list(classification.get("risk_flags") or []),
        },
        "config_snapshot": dict(classification.get("config_snapshot") or {}),
        "features": {
            "classification": {
                "classifier_version": classification.get("classifier_version"),
                "primary_class": primary,
                "window_states": classification.get("window_states") or {},
            }
        },
    }
