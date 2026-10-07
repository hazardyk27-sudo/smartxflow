from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from learning_archive.settlement import _selection_outcome


_ALLOWED_CHANGE_DRIVERS = {"NONE", "STAGE2_RESEARCH", "EXECUTION_OPTIMIZATION", "MARKET_UPDATE", "BOTH"}
_STAGE2_DRIVERS = {"STAGE2_RESEARCH", "BOTH"}


@dataclass(frozen=True)
class StageOutcome:
    market: str
    selection: str
    result: str
    price: float | None


@dataclass(frozen=True)
class StageComparison:
    fixture_id: str
    stage1: StageOutcome
    stage3: StageOutcome
    stage3_action: str
    preference_changed: bool
    transition: str
    change_driver: str


def _price(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value > 1:
        return float(value)
    return None


def _case_for(match: dict[str, Any], preference: dict[str, Any]) -> dict[str, Any]:
    return {
        "match": match,
        "prediction": {
            "market": preference.get("market"),
            "selection": preference.get("selection"),
        },
    }


def _stage_outcome(match: dict[str, Any], preference: dict[str, Any], final_score: str) -> StageOutcome:
    result = _selection_outcome(_case_for(match, preference), final_score)
    price = _price(preference.get("price"))
    if price is None:
        price_evidence = preference.get("price_evidence") or {}
        if isinstance(price_evidence, dict):
            price = _price(price_evidence.get("price"))
    return StageOutcome(
        market=str(preference.get("market") or "").strip(),
        selection=str(preference.get("selection") or "").strip(),
        result=result,
        price=price,
    )


def _result_rank(result: str) -> int:
    return {"LOSS": 0, "VOID": 1, "WIN": 2}.get(result, -1)


def _transition(stage1: str, stage3: str) -> str:
    left = _result_rank(stage1)
    right = _result_rank(stage3)
    if left < 0 or right < 0:
        return "UNRESOLVED"
    if right > left:
        return "IMPROVED"
    if right < left:
        return "WORSENED"
    return "SAME"


def compare_stage_preferences(
    *,
    fixture_id: str,
    match: dict[str, Any],
    stage1_preference: dict[str, Any],
    stage3_preference: dict[str, Any],
    stage3_action: str,
    final_score: str,
    change_driver: str = "NONE",
) -> StageComparison:
    stage1 = _stage_outcome(match, stage1_preference, final_score)
    stage3 = _stage_outcome(match, stage3_preference, final_score)
    changed = (stage1.market, stage1.selection) != (stage3.market, stage3.selection)
    driver = str(change_driver or "NONE").upper()
    if driver not in _ALLOWED_CHANGE_DRIVERS:
        raise ValueError(f"unsupported change_driver: {change_driver!r}")
    if changed and driver == "NONE":
        raise ValueError("changed preference requires a non-NONE change_driver")
    if not changed and driver != "NONE":
        raise ValueError("unchanged preference requires change_driver=NONE")
    return StageComparison(
        fixture_id=fixture_id,
        stage1=stage1,
        stage3=stage3,
        stage3_action=str(stage3_action or "").upper(),
        preference_changed=changed,
        transition=_transition(stage1.result, stage3.result),
        change_driver=driver,
    )


def _hypothetical_pnl(result: str, price: float | None) -> float | None:
    if price is None:
        return None
    if result == "WIN":
        return price - 1.0
    if result == "LOSS":
        return -1.0
    if result == "VOID":
        return 0.0
    return None


def _hit_rate(results: list[str]) -> float | None:
    decided = [item for item in results if item in {"WIN", "LOSS"}]
    if not decided:
        return None
    return sum(1 for item in decided if item == "WIN") / len(decided)


def _roi(outcomes: Iterable[StageOutcome]) -> dict[str, Any]:
    pnl: list[float] = []
    for outcome in outcomes:
        value = _hypothetical_pnl(outcome.result, outcome.price)
        if value is not None:
            pnl.append(value)
    if not pnl:
        return {"sample_size": 0, "roi": None, "pnl_units": None}
    total = sum(pnl)
    return {
        "sample_size": len(pnl),
        "roi": total / len(pnl),
        "pnl_units": total,
    }


def _transition_counts(rows: list[StageComparison]) -> dict[str, int]:
    return {
        "IMPROVED": sum(1 for row in rows if row.transition == "IMPROVED"),
        "WORSENED": sum(1 for row in rows if row.transition == "WORSENED"),
        "SAME": sum(1 for row in rows if row.transition == "SAME"),
        "UNRESOLVED": sum(1 for row in rows if row.transition == "UNRESOLVED"),
    }


def _matched_summary(rows: list[StageComparison]) -> dict[str, Any]:
    stage1_hit = _hit_rate([row.stage1.result for row in rows])
    stage3_hit = _hit_rate([row.stage3.result for row in rows])
    return {
        "matched_cases": len(rows),
        "stage1_hit_rate": stage1_hit,
        "stage3_hit_rate": stage3_hit,
        "hit_rate_delta": None if stage1_hit is None or stage3_hit is None else stage3_hit - stage1_hit,
        "transitions": _transition_counts(rows),
    }


def summarize_comparisons(comparisons: Iterable[StageComparison]) -> dict[str, Any]:
    rows = list(comparisons)
    stage1_hit = _hit_rate([row.stage1.result for row in rows])
    stage3_hit = _hit_rate([row.stage3.result for row in rows])
    stage2_rows = [row for row in rows if row.change_driver in _STAGE2_DRIVERS]
    by_driver = {
        driver: _matched_summary([row for row in rows if row.change_driver == driver])
        for driver in sorted(_ALLOWED_CHANGE_DRIVERS)
    }
    return {
        "matched_cases": len(rows),
        "stage1": {
            "hit_rate": stage1_hit,
            "roi": _roi(row.stage1 for row in rows),
        },
        "stage3": {
            "hit_rate": stage3_hit,
            "roi": _roi(row.stage3 for row in rows),
        },
        "hit_rate_delta": None if stage1_hit is None or stage3_hit is None else stage3_hit - stage1_hit,
        "preference_changed": sum(1 for row in rows if row.preference_changed),
        "preference_unchanged": sum(1 for row in rows if not row.preference_changed),
        "transitions": _transition_counts(rows),
        "by_change_driver": by_driver,
        "stage2_influenced": _matched_summary(stage2_rows),
        "interpretation_rule": "Compare Stage 1 and Stage 3 on the same settled candidate set. Use change_driver to separate cases influenced by Stage 2 research from execution optimization or later market updates. Positive/negative deltas are evidence, not causal proof.",
    }
