from __future__ import annotations

from typing import Any

from .validator import PredictorPolicyError


_SUBSTANTIVE_SIGNALS = {
    "MONEY_ACCELERATION",
    "PRICE_CONFIRMATION",
    "PRICE_RESISTANCE",
    "DIVERGENCE",
    "REVERSAL",
    "LIQUIDITY_ADJUSTED_MOVE",
    "CROSS_MARKET_CONFIRMATION",
    "CROSS_MARKET_CONFLICT",
    "LATE_MOVE",
}


def _fixture_id(value: dict[str, Any]) -> str:
    return str(value.get("fixture_id") or value.get("fixture_uid") or value.get("match_id_hash") or "").strip()


def _market_quality(match: dict[str, Any]) -> dict[str, Any] | None:
    evidence = match.get("sxf_evidence")
    if not isinstance(evidence, dict):
        return None
    quality = evidence.get("market_quality")
    return quality if isinstance(quality, dict) else None


def enforce_stage1_market_quality(payload: dict[str, Any]) -> None:
    """Fail closed on Stage 1 candidate-quality mistakes using server-owned SXF evidence.

    Low liquidity is not an automatic DROP. It remains analyzable, but it cannot
    masquerade as strong evidence. Share concentration is context only, and high-
    odds underdog moves need real money, market liquidity and persistent price
    movement before they can become a frozen Stage 1 preference.
    """

    screening_by_id = {
        _fixture_id(item): item
        for item in payload.get("screening_results") or []
        if isinstance(item, dict) and _fixture_id(item)
    }
    violations: list[str] = []

    for match in payload.get("matches") or []:
        if not isinstance(match, dict):
            continue
        fixture_id = _fixture_id(match)
        quality = _market_quality(match)
        if quality is None:
            # The production StrictPredictorOrchestrator attaches this packet.
            # Standalone/unit payload validation remains backwards compatible.
            continue

        screening = screening_by_id.get(fixture_id) or {}
        signals = {str(item or "").upper() for item in screening.get("attention_signals") or []}
        if not (signals & _SUBSTANTIVE_SIGNALS):
            violations.append(
                f"SXF-S1-012: {fixture_id}: share/persistence/saturation alone cannot create a Stage 1 candidate; "
                "at least one money, price-response, reversal, late-move or cross-market signal is required"
            )

        if quality.get("share_only_risk") is True:
            violations.append(
                f"SXF-S1-012: {fixture_id}: extreme money share is contextual only; trusted evidence shows "
                "insufficient absolute-money and price movement to justify selection"
            )

        if str(quality.get("underdog_status") or "").upper() == "LOW_CONFIDENCE_MARKET_MOVE":
            violations.append(
                f"SXF-S1-013: {fixture_id}: high-odds underdog move lacks the required absolute money, market volume "
                "or price persistence and may not become a frozen Stage 1 preference"
            )

    if violations:
        raise PredictorPolicyError("; ".join(violations))
