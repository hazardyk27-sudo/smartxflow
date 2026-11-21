"""Opt-in prospective SXF EKOL 3 / OVER_STRONG tags, separate from frozen V3 rules.

The T-6 BASE job evaluates these against only immutable complete snapshots
at or before the exact checkpoint. These tags are not calibrated probabilities.
Missing/stale or cross-source data fails closed. No external data or DB writes.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Sequence

from .rules import Fixture, Signal, Snapshot, CheckpointEvaluation, checkpoint_time

EXPERIMENTAL_RULESET = "SXF_EXPERIMENTAL_V1_2026_11_21"
MAX_EXPERIMENTAL_LAG = timedelta(minutes=10)
ZERO = Decimal("0")
ONE = Decimal("1")


def _at(fixture: Fixture, market: str, hours: int,
        snapshots: Sequence[Snapshot]) -> Snapshot | None:
    target = checkpoint_time(fixture, hours)
    valid = (s for s in snapshots if s.market == market and s.complete
             and target - MAX_EXPERIMENTAL_LAG <= s.observed_at <= target)
    return max(valid, key=lambda s: s.observed_at, default=None)


def _devig(snap: Snapshot, side: str) -> Decimal:
    implied = {key: ONE / snap.quotes[key].odds for key in ("1", "X", "2")}
    return implied[side] / sum(implied.values(), ZERO)


def _emission(engine: str, side: str, t6: Snapshot,
              evidence: dict[str, str]) -> dict:
    q = t6.quotes[side]
    event = {
        "engine": engine, "side": side, "checkpoint": 6,
        "odds": str(q.odds), "amount": str(q.amount),
        "share": str(q.share), "observed_at": t6.observed_at.isoformat(),
        "label": "EXPERIMENTAL", "selection_status": "ELIGIBLE",
        "experimental_ruleset": EXPERIMENTAL_RULESET,
        "evidence": evidence,
    }
    return event


def evaluate_t6_experiments(
    fixture: Fixture, snapshots: Sequence[Snapshot],
    core: CheckpointEvaluation,
) -> tuple[list[dict], dict[str, str]]:
    """Return independently auditable experimental tags and fail-closed states.

    Only a genuine T-6 canonical V1/Stable/Premium hit can spawn a tag.
    No T-8 fallback, later observation, double counting or new betting side.
    """
    if core.checkpoint != 6:
        return [], {"EKOL_3": "T6_ONLY", "OVER_STRONG": "T6_ONLY"}
    tags: list[dict] = []
    states = {"EKOL_3": "NO_CORE_V1", "OVER_STRONG": "NO_CORE_OVER"}

    v1 = next((s for s in core.signals
               if s.engine == "1X2_CONCENTRATION_V1"
               and s.checkpoint == 6 and s.selection_status == "ELIGIBLE"), None)
    if v1 is not None:
        c8, c7, c6 = (_at(fixture, "1X2", hour, snapshots) for hour in (8, 7, 6))
        if any(s is None for s in (c8, c7, c6)):
            states["EKOL_3"] = "MISSING_FRESH_T8_T7_T6"
        elif len({c8.observed_at, c7.observed_at, c6.observed_at}) != 3:
            states["EKOL_3"] = "DUPLICATE_CHECKPOINT_SOURCE"
        elif c6.quotes[v1.side].odds != v1.odds or c6.quotes[v1.side].share != v1.share:
            states["EKOL_3"] = "CORE_SOURCE_MISMATCH"
        else:
            keys = ("1", "X", "2")
            first = {k: c7.quotes[k].amount - c8.quotes[k].amount for k in keys}
            total = {k: c6.quotes[k].amount - c8.quotes[k].amount for k in keys}
            first_sum, total_sum = sum(first.values(), ZERO), sum(total.values(), ZERO)
            baseline_total = sum((c8.quotes[k].amount for k in keys), ZERO)
            if baseline_total <= ZERO or first_sum <= ZERO or total_sum <= ZERO:
                states["EKOL_3"] = "INSUFFICIENT_NEW_MONEY"
            elif any(value < ZERO for value in (*first.values(), *total.values())):
                states["EKOL_3"] = "NEGATIVE_SELECTION_FLOW"
            else:
                baseline = c8.quotes[v1.side].amount / baseline_total
                first_share = first[v1.side] / first_sum
                total_share = total[v1.side] / total_sum
                if first_share <= baseline:
                    states["EKOL_3"] = "FIRST_HOUR_ACCEL_FAIL"
                elif total_share <= baseline:
                    states["EKOL_3"] = "TWO_HOUR_ACCEL_FAIL"
                elif _devig(c6, v1.side) < _devig(c8, v1.side):
                    states["EKOL_3"] = "DEVIG_PRICE_CONFIRM_FAIL"
                else:
                    states["EKOL_3"] = "PASS"
                    tags.append(_emission("EKOL_3", v1.side, c6, {
                        "t8_observed_at": c8.observed_at.isoformat(),
                        "t7_observed_at": c7.observed_at.isoformat(),
                        "t6_observed_at": c6.observed_at.isoformat(),
                        "t8_base_money_share": str(baseline * 100),
                        "first_hour_new_money_share": str(first_share * 100),
                        "two_hour_new_money_share": str(total_share * 100),
                        "devig_price_delta_pp": str((_devig(c6, v1.side) - _devig(c8, v1.side)) * 100),
                    }))

    over_core = next((s for s in core.signals
                      if s.engine in ("PREMIUM_OVER_2_5", "STABLE_OVER_2_5")
                      and s.checkpoint == 6 and s.selection_status == "ELIGIBLE"), None)
    if over_core is not None:
        o8, o6, b6 = (_at(fixture, market, hour, snapshots)
                      for market, hour in (("OU25", 8), ("OU25", 6), ("BTTS", 6)))
        if any(s is None for s in (o8, o6, b6)):
            states["OVER_STRONG"] = "CROSSMARKET_UNVERIFIED"
        elif o6.observed_at != b6.observed_at:
            states["OVER_STRONG"] = "CROSSMARKET_TIMESTAMP_MISMATCH"
        elif o6.quotes["O"].odds != over_core.odds or o6.quotes["O"].share != over_core.share:
            states["OVER_STRONG"] = "CORE_SOURCE_MISMATCH"
        elif b6.quotes["Y"].odds <= Decimal("1.60"):
            states["OVER_STRONG"] = "BTTS_YES_PRICE_FAIL"
        elif o6.quotes["O"].amount < Decimal("2500"):
            states["OVER_STRONG"] = "OVER_MONEY_FAIL"
        elif o6.quotes["O"].share - o8.quotes["O"].share <= Decimal("-2"):
            states["OVER_STRONG"] = "SHARE_RETENTION_FAIL"
        else:
            states["OVER_STRONG"] = "PASS"
            tags.append(_emission("OVER_STRONG", "O", o6, {
                "over_t8_observed_at": o8.observed_at.isoformat(),
                "over_t6_observed_at": o6.observed_at.isoformat(),
                "btts_t6_observed_at": b6.observed_at.isoformat(),
                "btts_yes_t6_odds": str(b6.quotes["Y"].odds),
                "over_t8_share": str(o8.quotes["O"].share),
                "over_t6_share": str(o6.quotes["O"].share),
                "over_share_delta_pp": str(o6.quotes["O"].share - o8.quotes["O"].share),
            }))

    return tags, states
