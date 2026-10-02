"""Exact-hash result settlement for Analysis V2.

No team-name fuzzy matching is allowed here. Callers provide a finished-score
map keyed by the canonical 12-character match_id_hash.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional, Tuple

from .signal_store import (
    build_settlement_event,
    validate_match_id_hash,
)


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
        candidates = (
            ("home_score", "away_score"),
            ("home", "away"),
            ("score_home", "score_away"),
        )
        for hk, ak in candidates:
            if value.get(hk) is not None and value.get(ak) is not None:
                try:
                    return int(value[hk]), int(value[ak])
                except (TypeError, ValueError):
                    pass
        if value.get("score") is not None:
            return parse_score(value.get("score"))
        return None
    match = _SCORE_RE.match(str(value))
    return (int(match.group(1)), int(match.group(2))) if match else None


def evaluate_selection(market_key: str, selection_code: str, home_score: int, away_score: int) -> str:
    market = str(market_key or "").strip().upper()
    selection = str(selection_code or "").strip().upper()
    total = int(home_score) + int(away_score)

    if market == "1X2":
        outcome = "1" if home_score > away_score else "2" if away_score > home_score else "X"
        return "WIN" if selection == outcome else "LOSS"

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
        both = home_score > 0 and away_score > 0
        if selection == "Y":
            return "WIN" if both else "LOSS"
        if selection == "N":
            return "WIN" if not both else "LOSS"
        return "UNKNOWN"

    return "UNKNOWN"


def flat_stake_units(odds: Any, selection_result: str) -> Optional[float]:
    result = str(selection_result or "").upper()
    if result in ("PUSH", "VOID"):
        return 0.0
    if result == "LOSS":
        return -1.0
    if result != "WIN":
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
    source: str = "finished_scores",
):
    """Build settlement events only for exact canonical hash matches.

    A signal with no exact hash entry is intentionally left unsettled. There is
    no home/away fuzzy fallback.
    """
    settlements = []
    skipped_no_exact_hash = []

    for signal in signals:
        match_hash = validate_match_id_hash(signal.get("match_id_hash"))
        score_value = finished_scores_by_hash.get(match_hash)
        score = parse_score(score_value)
        if score is None:
            skipped_no_exact_hash.append(signal.get("signal_uid"))
            continue

        home_score, away_score = score
        result = evaluate_selection(
            signal.get("market_key"),
            signal.get("selection_code"),
            home_score,
            away_score,
        )
        odds = signal.get("trigger_odds")
        settlements.append(
            build_settlement_event(
                signal_uid=signal["signal_uid"],
                match_id_hash=match_hash,
                settled_at=settled_at,
                home_score=home_score,
                away_score=away_score,
                selection_result=result,
                result_code=f"{home_score}-{away_score}",
                settled_odds=odds,
                flat_stake_units=flat_stake_units(odds, result),
                source=source,
                evidence={"match_method": "exact_match_id_hash"},
            )
        )

    return settlements, skipped_no_exact_hash
