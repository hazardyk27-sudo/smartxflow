"""Historical edge matrix for Analysis V2.

This module answers questions such as "which odds + money + price-move band
performed best?" without turning an in-sample discovery into a production
rule. It is deliberately engine-agnostic: callers first filter records to one
source engine/market, then build and validate segments chronologically.

The matrix is descriptive. A high-ROI discovery cell is labelled RESEARCH;
it becomes HOLDOUT_SUPPORTED only when the exact locked segment is evaluated
on later, untouched observations with enough sample size.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from math import inf
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


EDGE_MATRIX_VERSION = "analysis-v2-edge-matrix-1.0.1"
DEFAULT_MIN_SAMPLE = 30


@dataclass(frozen=True)
class Bucket:
    label: str
    lower: float
    upper: float
    include_upper: bool = False

    def contains(self, value: float) -> bool:
        if value < self.lower:
            return False
        if self.include_upper:
            return value <= self.upper
        return value < self.upper


ODDS_BUCKETS: Tuple[Bucket, ...] = (
    Bucket("<1.35", -inf, 1.35),
    Bucket("1.35-1.54", 1.35, 1.55),
    Bucket("1.55-1.79", 1.55, 1.80),
    Bucket("1.80-1.99", 1.80, 2.00),
    Bucket("2.00-2.19", 2.00, 2.20),
    Bucket("2.20-2.89", 2.20, 2.90),
    Bucket("2.90-3.99", 2.90, 4.00),
    Bucket("4.00-5.99", 4.00, 6.00),
    Bucket("6.00+", 6.00, inf, True),
)

MONEY_PCT_BUCKETS: Tuple[Bucket, ...] = (
    Bucket("<50", -inf, 50.0),
    Bucket("50-59.9", 50.0, 60.0),
    Bucket("60-69.9", 60.0, 70.0),
    Bucket("70-79.9", 70.0, 80.0),
    Bucket("80-84.9", 80.0, 85.0),
    Bucket("85-89.9", 85.0, 90.0),
    Bucket("90-94.9", 90.0, 95.0),
    Bucket("95+", 95.0, inf, True),
)

PRICE_DROP_BUCKETS: Tuple[Bucket, ...] = (
    Bucket("drift_20+", -inf, -20.0),
    Bucket("drift_10-20", -20.0, -10.0),
    Bucket("drift_5-10", -10.0, -5.0),
    Bucket("drift_0-5", -5.0, 0.0),
    Bucket("drop_0-3", 0.0, 3.0),
    Bucket("drop_3-5", 3.0, 5.0),
    Bucket("drop_5-7", 5.0, 7.0),
    Bucket("drop_7-10", 7.0, 10.0),
    Bucket("drop_10-20", 10.0, 20.0),
    Bucket("drop_20+", 20.0, inf, True),
)

HOURS_TO_KICKOFF_BUCKETS: Tuple[Bucket, ...] = (
    Bucket("<2h", -inf, 2.0),
    Bucket("2-6h", 2.0, 6.0),
    Bucket("6-12h", 6.0, 12.0),
    Bucket("12-24h", 12.0, 24.0),
    Bucket("24-48h", 24.0, 48.0),
    Bucket("48h+", 48.0, inf, True),
)

DIMENSION_BUCKETS: Dict[str, Tuple[Bucket, ...]] = {
    "odds": ODDS_BUCKETS,
    "money_pct": MONEY_PCT_BUCKETS,
    "price_drop_pct": PRICE_DROP_BUCKETS,
    "hours_to_kickoff": HOURS_TO_KICKOFF_BUCKETS,
}

DIMENSION_FIELDS: Dict[str, Tuple[str, ...]] = {
    "odds": ("recommended_odds", "entry_odds", "trigger_odds", "odds_now", "odds"),
    "money_pct": ("trigger_pct", "pct_now", "current_pct", "pct"),
    "price_drop_pct": ("odds_drop_pct", "price_drop_pct"),
    "hours_to_kickoff": ("hours_before_kickoff", "hours_to_kickoff"),
}


def _number(value: Any) -> Optional[float]:
    """Parse matrix metrics; comma without dot is treated as decimal comma."""
    if value in (None, "", "-"):
        return None
    try:
        if isinstance(value, str):
            cleaned = (
                value.replace("£", "")
                .replace("€", "")
                .replace("$", "")
                .replace("%", "")
                .replace(" ", "")
                .strip()
            )
            if not cleaned:
                return None
            if "," in cleaned and "." not in cleaned:
                cleaned = cleaned.replace(",", ".")
            elif "," in cleaned and "." in cleaned:
                cleaned = cleaned.replace(",", "")
            return float(cleaned)
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_number(record: Mapping[str, Any], keys: Sequence[str]) -> Optional[float]:
    for key in keys:
        value = _number(record.get(key))
        if value is not None:
            return value
    return None


def bucket_label(dimension: str, value: Any) -> Optional[str]:
    number = _number(value)
    if number is None:
        return None
    buckets = DIMENSION_BUCKETS.get(dimension)
    if not buckets:
        raise ValueError(f"UNSUPPORTED_EDGE_DIMENSION:{dimension}")
    for bucket in buckets:
        if bucket.contains(number):
            return bucket.label
    return None


def record_dimension_value(record: Mapping[str, Any], dimension: str) -> Optional[float]:
    fields = DIMENSION_FIELDS.get(dimension)
    if not fields:
        raise ValueError(f"UNSUPPORTED_EDGE_DIMENSION:{dimension}")
    return _first_number(record, fields)


def segment_for_record(
    record: Mapping[str, Any], dimensions: Sequence[str]
) -> Optional[Tuple[str, ...]]:
    labels: List[str] = []
    for dimension in dimensions:
        value = record_dimension_value(record, dimension)
        label = bucket_label(dimension, value)
        if label is None:
            return None
        labels.append(label)
    return tuple(labels)


def _outcome(record: Mapping[str, Any]) -> str:
    return str(record.get("outcome") or record.get("result") or "").strip().upper()


def _pnl(record: Mapping[str, Any]) -> Optional[float]:
    explicit = _number(record.get("pnl_units"))
    if explicit is not None:
        return explicit
    outcome = _outcome(record)
    odds = _first_number(record, DIMENSION_FIELDS["odds"])
    if outcome == "WIN" and odds is not None and odds > 1.0:
        return odds - 1.0
    if outcome == "LOSS":
        return -1.0
    if outcome in {"PUSH", "VOID"}:
        return 0.0
    return None


def _max_drawdown(pnls: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return round(max_dd, 6)


@dataclass(frozen=True)
class EdgeCell:
    dimensions: Tuple[str, ...]
    segment: Tuple[str, ...]
    n: int
    wins: int
    losses: int
    pushes: int
    voids: int
    unknown: int
    hit_rate_pct: Optional[float]
    avg_odds: Optional[float]
    profit_units: float
    roi_pct: Optional[float]
    max_drawdown_units: float
    sample_status: str
    evidence_status: str

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["edge_matrix_version"] = EDGE_MATRIX_VERSION
        return payload


def _cell(
    records: Sequence[Mapping[str, Any]],
    *,
    dimensions: Tuple[str, ...],
    segment: Tuple[str, ...],
    min_sample: int,
    evidence_status: str,
) -> EdgeCell:
    wins = losses = pushes = voids = unknown = 0
    pnls: List[float] = []
    odds_values: List[float] = []

    for record in records:
        outcome = _outcome(record)
        if outcome == "WIN":
            wins += 1
        elif outcome == "LOSS":
            losses += 1
        elif outcome == "PUSH":
            pushes += 1
        elif outcome == "VOID":
            voids += 1
        else:
            unknown += 1

        pnl = _pnl(record)
        if pnl is not None:
            pnls.append(pnl)
        odds = _first_number(record, DIMENSION_FIELDS["odds"])
        if odds is not None:
            odds_values.append(odds)

    settled_decisions = wins + losses
    n = len(records)
    hit = (wins / settled_decisions * 100.0) if settled_decisions else None
    staked = len(pnls)
    profit = sum(pnls)
    roi = (profit / staked * 100.0) if staked else None
    avg_odds = sum(odds_values) / len(odds_values) if odds_values else None

    return EdgeCell(
        dimensions=dimensions,
        segment=segment,
        n=n,
        wins=wins,
        losses=losses,
        pushes=pushes,
        voids=voids,
        unknown=unknown,
        hit_rate_pct=round(hit, 3) if hit is not None else None,
        avg_odds=round(avg_odds, 4) if avg_odds is not None else None,
        profit_units=round(profit, 6),
        roi_pct=round(roi, 3) if roi is not None else None,
        max_drawdown_units=_max_drawdown(pnls),
        sample_status="SUFFICIENT" if n >= min_sample else "SMALL_SAMPLE",
        evidence_status=evidence_status,
    )


def build_edge_matrix(
    records: Iterable[Mapping[str, Any]],
    *,
    dimensions: Sequence[str] = ("odds", "money_pct", "price_drop_pct"),
    min_sample: int = DEFAULT_MIN_SAMPLE,
    evidence_status: str = "RESEARCH",
) -> List[Dict[str, Any]]:
    dims = tuple(dimensions)
    if not dims:
        raise ValueError("EDGE_DIMENSIONS_REQUIRED")
    for dimension in dims:
        if dimension not in DIMENSION_BUCKETS:
            raise ValueError(f"UNSUPPORTED_EDGE_DIMENSION:{dimension}")

    grouped: Dict[Tuple[str, ...], List[Mapping[str, Any]]] = {}
    for record in records:
        segment = segment_for_record(record, dims)
        if segment is None:
            continue
        grouped.setdefault(segment, []).append(record)

    cells = [
        _cell(
            rows,
            dimensions=dims,
            segment=segment,
            min_sample=min_sample,
            evidence_status=evidence_status,
        ).to_dict()
        for segment, rows in grouped.items()
    ]
    cells.sort(
        key=lambda item: (
            item["sample_status"] != "SUFFICIENT",
            -(item["roi_pct"] if item["roi_pct"] is not None else -inf),
            -item["n"],
            item["segment"],
        )
    )
    return cells


def research_candidates(
    cells: Iterable[Mapping[str, Any]], *, min_sample: int = DEFAULT_MIN_SAMPLE
) -> List[Dict[str, Any]]:
    """Return positive in-sample cells as hypotheses, never production rules."""

    result = []
    for cell in cells:
        roi = _number(cell.get("roi_pct"))
        if int(cell.get("n") or 0) < min_sample or roi is None or roi <= 0:
            continue
        payload = dict(cell)
        payload["evidence_status"] = "RESEARCH_CANDIDATE"
        result.append(payload)
    result.sort(key=lambda item: (-float(item["roi_pct"]), -int(item["n"])))
    return result


def _parse_time(record: Mapping[str, Any]) -> datetime:
    raw = str(
        record.get("trigger_at")
        or record.get("created_at")
        or record.get("settled_at")
        or ""
    ).strip()
    if not raw:
        return datetime.min
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return datetime.min


def chronological_split(
    records: Iterable[Mapping[str, Any]],
    *,
    train_fraction: float = 0.60,
    validation_fraction: float = 0.20,
) -> Dict[str, List[Mapping[str, Any]]]:
    if train_fraction <= 0 or validation_fraction < 0:
        raise ValueError("INVALID_SPLIT_FRACTIONS")
    if train_fraction + validation_fraction >= 1.0:
        raise ValueError("HOLDOUT_REQUIRED")

    ordered = sorted((dict(row) for row in records), key=_parse_time)
    n = len(ordered)
    train_end = int(n * train_fraction)
    validation_end = train_end + int(n * validation_fraction)
    return {
        "train": ordered[:train_end],
        "validation": ordered[train_end:validation_end],
        "holdout": ordered[validation_end:],
    }


def evaluate_locked_segments(
    records: Iterable[Mapping[str, Any]],
    *,
    dimensions: Sequence[str],
    locked_segments: Iterable[Sequence[str]],
    min_sample: int = DEFAULT_MIN_SAMPLE,
    evidence_status: str = "HOLDOUT",
) -> List[Dict[str, Any]]:
    """Evaluate exact preselected segments on later data without re-ranking them."""

    dims = tuple(dimensions)
    wanted = {tuple(segment) for segment in locked_segments}
    grouped: Dict[Tuple[str, ...], List[Mapping[str, Any]]] = {
        segment: [] for segment in wanted
    }
    for record in records:
        segment = segment_for_record(record, dims)
        if segment in grouped:
            grouped[segment].append(record)

    result = []
    for segment in sorted(wanted):
        cell = _cell(
            grouped[segment],
            dimensions=dims,
            segment=segment,
            min_sample=min_sample,
            evidence_status=evidence_status,
        ).to_dict()
        if cell["sample_status"] == "SUFFICIENT":
            cell["evidence_status"] = (
                "HOLDOUT_SUPPORTED"
                if (cell["roi_pct"] or 0.0) > 0
                else "HOLDOUT_REJECTED"
            )
        else:
            cell["evidence_status"] = "HOLDOUT_INSUFFICIENT"
        result.append(cell)
    return result
