"""Part 4C1: read-only, verified late T-6 evidence planner.

A plan is NOT a signal write. Reconciliation workers must submit a plan via a
separately approved, lease-fenced transactional RPC. Rules are frozen and only
computed using the existing Base kernel over pre-checkpoint snapshots.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable
from uuid import UUID

from .reader import _parse_time, SupabaseMoneywayReader
from .rules import Fixture, select_snapshot, evaluate_base
from .scheduler import _market_for_engine, _serialize_signal, INGESTION_GRACE

_SIDES = {"1X2": 3, "OU25": 2, "BTTS": 2}


@dataclass(frozen=True)
class ReconciliationPlan:
    fixture_uid: str
    kickoff_utc: datetime
    market: str
    origin_event_key: str
    source_snapshot_ids: tuple[int, ...]
    source_observed_at: datetime
    signals: tuple[dict, ...]
    v2_state: str


def plan_late_t6(reader: Any, *, origin_event_key: str, fixture_uid: str,
                 kickoff_utc: datetime, market: str,
                 progress_hook: Callable[[], None] | None = None) -> ReconciliationPlan | None:
    """Proof of a completed T-6 market group, never based on a legacy hash.

    Returns None when the missing T-6 source has not arrived. Fails closed on
    partial pages, fabricated evidence IDs, ambiguous identity and provenance.
    """
    if not isinstance(origin_event_key, str) or not origin_event_key or len(origin_event_key) > 450:
        raise ValueError("invalid correction origin")
    if market not in _SIDES:
        raise ValueError("invalid Base market")
    canonical = str(UUID(fixture_uid))
    kickoff = _parse_time(kickoff_utc)
    fixture, legacy = reader.load_fixture(canonical)
    if fixture.fixture_uid != canonical or fixture.kickoff_utc != kickoff:
        raise ValueError("fixture identity changed")
    checkpoint = kickoff - timedelta(hours=6)
    kwargs = {}
    if progress_hook is not None and isinstance(reader, SupabaseMoneywayReader):
        kwargs["progress_hook"] = progress_hook
    result = reader.load_checkpoints(
        fixture, hours=(6,), as_of_utc=checkpoint + INGESTION_GRACE,
        include_v2_history=True, expected_legacy_hash=legacy, **kwargs,
    )
    chosen = select_snapshot(fixture, market, 6, result.snapshots)
    if chosen is None:
        return None
    ids = getattr(result, "source_row_ids", {}).get((market, chosen.observed_at))
    if (not isinstance(ids, tuple) or len(ids) != _SIDES[market]
            or any(type(i) is not int or i <= 0 for i in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("complete market has missing or invalid source row IDs")
    calculated = evaluate_base(fixture, 6, result.snapshots)
    signals = tuple(_serialize_signal(s) for s in calculated.signals
                    if _market_for_engine(s.engine) == market)
    return ReconciliationPlan(
        fixture_uid=canonical, kickoff_utc=kickoff, market=market,
        origin_event_key=origin_event_key, source_snapshot_ids=tuple(sorted(ids)),
        source_observed_at=chosen.observed_at, signals=signals,
        v2_state=calculated.v2_state if market == "1X2" else "N/A")
