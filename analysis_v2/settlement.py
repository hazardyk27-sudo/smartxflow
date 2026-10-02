"""Exact-hash settlement helpers for SmartXFlow Analysis V2.

This module never performs team-name/fuzzy matching. Finished scores are keyed
by the canonical 12-character ``match_id_hash``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional, Tuple

from .signal_store import build_settlement_event, validate_match_id_hash


_SCORE_RE = re.compile(r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$")


def parse_score(value: Any) -> Optional[Tuple[int, int]]:
    if value is None:
        return None
    if isinstance(value, (tuple, list)) and len(value) >= 2:
        try:
            return int(value[0]), int(value[1])
        except (TypeError, ValueError):
            return None
    if isinstance(value, dict):
        for home_key, away_key in (
            ("home_score", "away_score"),
            ("home", "away"),
            ("score_home", "score_away"),
        ):
            if value.get(home_key) is not None and value.get(away_key) is not None:
                try:
                    return int(value[home_key]), int(value[away_key])
                except (TypeError, ValueError):
                    pass
        if value.get("score") is not None:
            return parse_score(value.get("score"))
        return None

    match = _SCORE_RE.match(str(value))
    return (int(match.group(1)), int(match.group(2))) if match else None


def evaluate_selection(
    market_key: str, selection_code: str, home_score: int, away_score: int
) -> str:
    market = str(market_key or "").strip().upper()
    selection = str(selection_code or "").strip().upper()
    total = int(home_score) + int(away_score)

    if market == "1X2":
        result = (
            "1"
            if home_score > away_score
            else "2"
            if away_score > home_score
            else "X"
        )
        return "WIN" if selection == result else "LOSS"

    if market == "DC":
        if selection == "1X":
            return "WIN" if home_score >= away_score else "LOSS"
        if selection == "X2":
            return "WIN" if away_score >= home_score else "LOSS"
        if selection == "12":
            return "WIN" if home_score != away_score else "LOSS"
        return "UNKNOWN"

    if market == "DNB":
        if home_score == away_score:
            return "PUSH"
        if selection == "1":
            return "WIN" if home_score > away_score else "LOSS"
        if selection == "2":
            return "WIN" if away_score > home_score else "LOSS"
        return "UNKNOWN"

    if market == "OU25":
        if selection == "O":
            return "WIN" if total >= 3 else "LOSS"
        if selection == "U":
            return "WIN" if total <= 2 else "LOSS"
        return "UNKNOWN"

    if market == "BTTS":
        both_scored = home_score > 0 and away_score > 0
        if selection == "Y":
            return "WIN" if both_scored else "LOSS"
        if selection == "N":
            return "WIN" if not both_scored else "LOSS"
        return "UNKNOWN"

    return "UNKNOWN"


def flat_stake_units(odds: Any, outcome: str) -> Optional[float]:
    outcome = str(outcome or "").upper()
    if outcome in ("PUSH", "VOID"):
        return 0.0
    if outcome == "LOSS":
        return -1.0
    if outcome != "WIN":
        return None
    try:
        price = float(odds)
    except (TypeError, ValueError):
        return None
    return price - 1.0 if price > 1 else None


def build_settlements_from_hash_scores(
    signals: Iterable[Dict[str, Any]],
    finished_scores_by_hash: Dict[str, Any],
    *,
    settled_at: Any,
    settlement_source: str = "finished_scores",
):
    """Build settlement rows only when an exact hash score exists."""
    settlements = []
    skipped_no_exact_hash = []

    for signal in signals:
        match_hash = validate_match_id_hash(signal.get("match_id_hash"))
        score = parse_score(finished_scores_by_hash.get(match_hash))
        signal_id = signal.get("signal_id") or signal.get("signal_uid")
        if score is None:
            skipped_no_exact_hash.append(signal_id)
            continue

        home_score, away_score = score
        market_key = signal.get("recommended_market") or signal.get("market_key")
        selection_code = signal.get("recommended_selection") or signal.get(
            "selection_code"
        )
        outcome = evaluate_selection(
            market_key, selection_code, home_score, away_score
        )
        entry_odds = signal.get("trigger_odds")

        settlements.append(
            build_settlement_event(
                signal_id=signal_id,
                match_id_hash=match_hash,
                final_home_score=home_score,
                final_away_score=away_score,
                outcome=outcome,
                entry_odds=entry_odds,
                pnl_units=flat_stake_units(entry_odds, outcome),
                settled_at=settled_at,
                settlement_source=settlement_source,
                engine_version=signal.get("engine_version", ""),
                metadata={"match_method": "exact_match_id_hash"},
            )
        )

    return settlements, skipped_no_exact_hash
