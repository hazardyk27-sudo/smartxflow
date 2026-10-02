"""Analysis V2 Part 5: deterministic market selector.

The selector converts a confirmed team direction into the healthiest real
provider market among Match Odds, Draw No Bet and Double Chance.

It never synthesizes Double Chance/DNB data and never uses an opaque score.
Every candidate is either eligible or rejected with explicit reason codes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from .classification import ClassificationConfig, classify_market_movement
from .market_contract import get_market


SELECTOR_VERSION = "analysis-v2-part5-1.0.0"

SUPPORTIVE_CLASSES = {
    "CONFIRMED_MOVE",
    "LATE_STEAM",
    "EARLY_POSITION",
}

DIRECTION_ALIASES = {
    "1": "1",
    "HOME": "1",
    "H": "1",
    "2": "2",
    "AWAY": "2",
    "A": "2",
    "X": "X",
    "DRAW": "X",
    "D": "X",
}

DIRECTION_MARKETS = {
    "1": {"1X2": "1", "DNB": "1", "DC": "1X"},
    "2": {"1X2": "2", "DNB": "2", "DC": "X2"},
    "X": {"1X2": "X"},
}

PROTECTION_LEVEL = {
    "1X2": "FULL_RESULT",
    "DNB": "DRAW_PUSH",
    "DC": "DRAW_COVER",
}


@dataclass(frozen=True)
class MarketSelectorConfig:
    high_ml_odds: float = 2.75
    medium_ml_odds: float = 2.00
    require_source_confirmation: bool = True


def _number(value: Any) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_direction(direction: str) -> str:
    normalized = DIRECTION_ALIASES.get(str(direction or "").strip().upper())
    if normalized is None:
        raise ValueError("direction must be one of 1/HOME, X/DRAW or 2/AWAY")
    return normalized


def direction_market_selection(direction: str) -> Dict[str, str]:
    return dict(DIRECTION_MARKETS[normalize_direction(direction)])


def _candidate(
    market_key: str,
    selection_code: str,
    view: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
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

    reason_codes = []
    available = current_odds is not None and current_odds > 1.0
    eligible = False

    if not available:
        reason_codes.append("REAL_PROVIDER_QUOTE_UNAVAILABLE")
    elif primary not in SUPPORTIVE_CLASSES:
        if primary == "PRICE_MONEY_DIVERGENCE":
            reason_codes.append("MARKET_DIVERGENCE")
        elif primary == "ANOMALOUS_MONEY":
            reason_codes.append("MARKET_ANOMALY_WATCH_ONLY")
        else:
            reason_codes.append("MARKET_NOT_CONFIRMED")
    elif "RECENT_PRICE_MONEY_DIVERGENCE" in risks:
        reason_codes.append("RECENT_DIVERGENCE_RISK")
    else:
        eligible = True
        reason_codes.append("SAME_DIRECTION_CONFIRMED")

    return {
        "market_key": market_key,
        "selection_code": selection_code,
        "available": available,
        "eligible": eligible,
        "current_odds": current_odds,
        "primary_class": primary,
        "protection_level": PROTECTION_LEVEL[market_key],
        "reason_codes": reason_codes,
        "classification": classification,
    }


def _preference_order(
    direction: str,
    ml_odds: Optional[float],
    config: MarketSelectorConfig,
) -> Tuple[str, ...]:
    if direction == "X":
        return ("1X2",)
    if ml_odds is None:
        return ("DNB", "DC", "1X2")
    if ml_odds >= config.high_ml_odds:
        return ("DC", "DNB", "1X2")
    if ml_odds >= config.medium_ml_odds:
        return ("DNB", "DC", "1X2")
    return ("1X2", "DNB", "DC")


def _source_block_reason(primary: str) -> str:
    if primary == "PRICE_MONEY_DIVERGENCE":
        return "SOURCE_DIVERGENCE"
    if primary == "ANOMALOUS_MONEY":
        return "SOURCE_ANOMALY_WATCH_ONLY"
    if primary == "NO_EDGE":
        return "SOURCE_NO_EDGE"
    return "SOURCE_NOT_CONFIRMED"


def select_direction_market(
    direction: str,
    market_views: Mapping[str, Mapping[str, Any]],
    *,
    source_market: str = "1X2",
    config: Optional[MarketSelectorConfig] = None,
) -> Dict[str, Any]:
    """Select ML/DNB/DC for one already identified team direction.

    The source market is the market that established the directional signal.
    By default it must itself be confirmed; Part 6 is responsible for later
    cross-market reconciliation rather than letting Part 5 override a source
    divergence with another market.
    """
    cfg = config or MarketSelectorConfig()
    normalized = normalize_direction(direction)
    mapping = direction_market_selection(normalized)
    source_market = str(source_market or "1X2").strip().upper()
    if source_market not in mapping:
        raise ValueError(
            f"source market {source_market!r} cannot express direction {normalized!r}"
        )

    candidates = {
        market: _candidate(market, selection, market_views.get(market))
        for market, selection in mapping.items()
    }
    source = candidates[source_market]

    if cfg.require_source_confirmation and not source["eligible"]:
        source_reason = _source_block_reason(source["primary_class"])
        if "RECENT_DIVERGENCE_RISK" in source["reason_codes"]:
            source_reason = "SOURCE_RECENT_DIVERGENCE"
        return {
            "selector_version": SELECTOR_VERSION,
            "decision": "WATCH_ONLY",
            "direction": normalized,
            "source_market": source_market,
            "recommended_market": None,
            "recommended_selection": None,
            "recommended_odds": None,
            "protection_level": None,
            "reason_codes": [source_reason],
            "preference_order": [],
            "candidates": candidates,
            "config_snapshot": asdict(cfg),
        }

    ml = candidates.get("1X2") or {}
    order = _preference_order(normalized, ml.get("current_odds"), cfg)

    chosen = None
    for market in order:
        candidate = candidates.get(market)
        if candidate and candidate["eligible"]:
            chosen = candidate
            break

    if chosen is None:
        return {
            "selector_version": SELECTOR_VERSION,
            "decision": "WATCH_ONLY",
            "direction": normalized,
            "source_market": source_market,
            "recommended_market": None,
            "recommended_selection": None,
            "recommended_odds": None,
            "protection_level": None,
            "reason_codes": ["NO_CONFIRMED_REAL_MARKET"],
            "preference_order": list(order),
            "candidates": candidates,
            "config_snapshot": asdict(cfg),
        }

    reasons = ["REAL_PROVIDER_MARKET", "SAME_DIRECTION_CONFIRMED"]
    if chosen["market_key"] == "DC":
        reasons.append("DRAW_COVER_PREFERRED")
    elif chosen["market_key"] == "DNB":
        reasons.append("DRAW_PUSH_PREFERRED")
    else:
        reasons.append("MATCH_ODDS_PREFERRED")

    return {
        "selector_version": SELECTOR_VERSION,
        "decision": "RECOMMEND",
        "direction": normalized,
        "source_market": source_market,
        "recommended_market": chosen["market_key"],
        "recommended_selection": chosen["selection_code"],
        "recommended_odds": chosen["current_odds"],
        "protection_level": chosen["protection_level"],
        "reason_codes": reasons,
        "preference_order": list(order),
        "candidates": candidates,
        "config_snapshot": asdict(cfg),
    }


def build_direction_market_views(
    history_client,
    *,
    match_id_hash: str,
    direction: str,
    as_of: Any,
    kickoff_utc: Any = None,
    classification_config: Optional[ClassificationConfig] = None,
    anchor_tolerance_minutes: int = 60,
    current_tolerance_minutes: int = 60,
) -> Dict[str, Dict[str, Any]]:
    """Load and classify only real provider markets able to express direction."""
    mapping = direction_market_selection(direction)
    views: Dict[str, Dict[str, Any]] = {}
    for market_key, selection_code in mapping.items():
        contract = get_market(market_key)
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
            features, classification_config
        )
        views[market_key] = {
            "selection_code": selection_code,
            "features": features,
            "classification": classification,
        }
    return views


def select_direction_market_from_history(
    history_client,
    *,
    match_id_hash: str,
    direction: str,
    as_of: Any,
    kickoff_utc: Any = None,
    source_market: str = "1X2",
    classification_config: Optional[ClassificationConfig] = None,
    selector_config: Optional[MarketSelectorConfig] = None,
    anchor_tolerance_minutes: int = 60,
    current_tolerance_minutes: int = 60,
) -> Dict[str, Any]:
    views = build_direction_market_views(
        history_client,
        match_id_hash=match_id_hash,
        direction=direction,
        as_of=as_of,
        kickoff_utc=kickoff_utc,
        classification_config=classification_config,
        anchor_tolerance_minutes=anchor_tolerance_minutes,
        current_tolerance_minutes=current_tolerance_minutes,
    )
    return select_direction_market(
        direction,
        views,
        source_market=source_market,
        config=selector_config,
    )


def apply_market_selection_to_trigger(
    trigger_payload: Mapping[str, Any],
    selection_result: Mapping[str, Any],
) -> Dict[str, Any]:
    """Merge the selector trace into an immutable Part 2 trigger payload."""
    payload = dict(trigger_payload)
    result = dict(selection_result)
    if result.get("decision") == "RECOMMEND":
        payload["recommended_market"] = result.get("recommended_market")
        payload["recommended_selection"] = result.get("recommended_selection")
        payload["recommended_odds"] = result.get("recommended_odds")

    engine_reason = dict(payload.get("engine_reason") or {})
    engine_reason["market_selector"] = {
        "decision": result.get("decision"),
        "direction": result.get("direction"),
        "reason_codes": list(result.get("reason_codes") or []),
        "recommended_market": result.get("recommended_market"),
        "recommended_selection": result.get("recommended_selection"),
    }
    payload["engine_reason"] = engine_reason

    config_snapshot = dict(payload.get("config_snapshot") or {})
    config_snapshot["market_selector"] = dict(
        result.get("config_snapshot") or {}
    )
    payload["config_snapshot"] = config_snapshot

    features = dict(payload.get("features") or {})
    features["market_selector"] = {
        "selector_version": result.get("selector_version"),
        "decision": result.get("decision"),
        "preference_order": list(result.get("preference_order") or []),
        "candidates": result.get("candidates") or {},
        "recommended_odds": result.get("recommended_odds"),
        "protection_level": result.get("protection_level"),
    }
    payload["features"] = features
    return payload
