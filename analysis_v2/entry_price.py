"""Canonical entry-price semantics for Analysis V2.

The source trigger market and the market finally recommended to the user may be
different. A source 1X2 price must never be used to settle a DNB/DC recommendation.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Tuple


def _number(value: Any) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if price > 1.0 else None


def resolve_entry_odds_with_source(
    signal: Mapping[str, Any],
) -> Tuple[Optional[float], str]:
    """Return the immutable odds for the actually recommended market.

    ``recommended_odds`` is authoritative when present. For old/same-market
    signals only, ``trigger_odds`` is a safe fallback. If the selector changed
    market/selection and no recommended quote was frozen, return ``None``
    rather than silently applying the source market's price.
    """
    recommended = _number(signal.get("recommended_odds"))
    if recommended is not None:
        return recommended, "recommended_odds"

    market = str(signal.get("market_key") or "").strip().upper()
    selection = str(signal.get("selection_code") or "").strip().upper()
    recommended_market = str(
        signal.get("recommended_market") or market
    ).strip().upper()
    recommended_selection = str(
        signal.get("recommended_selection") or selection
    ).strip().upper()

    if (
        recommended_market == market
        and recommended_selection == selection
    ):
        trigger = _number(signal.get("trigger_odds"))
        if trigger is not None:
            return trigger, "trigger_odds_same_market"

    return None, "missing_recommended_market_odds"


def resolve_entry_odds(signal: Mapping[str, Any]) -> Optional[float]:
    return resolve_entry_odds_with_source(signal)[0]
