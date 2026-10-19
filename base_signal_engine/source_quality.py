"""Read-only source-completeness classification for the *durable* Base worker.

Never modifies motor eligibility thresholds or chooses a betting side. Snapshot
completeness is independently derived from source records and frozen checkpoint
windows, rather than from whether a motor happened to emit a signal.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from .rules import Fixture, Snapshot, select_snapshot
from .scheduler import CheckpointJob

_MARKETS = ("1X2", "OU25", "BTTS")
_EARLY_CORE = (72, 60, 40, 24)
_RETENTION = (6, 5, 4, 3)


class CapturingReader:
    """Pass-through read adapter; retain only the already-fetched source batch."""

    def __init__(self, reader: Any):
        self._reader = reader
        self.source: Any = None

    def load_fixture(self, fixture_uid: str):
        return self._reader.load_fixture(fixture_uid)

    def load_checkpoints(self, *args: Any, **kwargs: Any):
        self.source = self._reader.load_checkpoints(*args, **kwargs)
        return self.source


def source_coverage(job: CheckpointJob, source: Any, payload: dict) -> dict:
    """Return deterministic coverage with an explicit WAITING_DATA disposition.

    BASE evaluates available markets independently. A completely empty Base
    checkpoint waits. A partial Base checkpoint may commit its proven markets,
    but missing markets / absent T-6 authority are expressly marked provisional
    and require a future append-only reconciliation (not yet implemented).

    Early first-hit/retention chronology is stricter: missing earlier eligible
    checkpoints mean a later "first" or retained judgment is unprovable.
    """
    if source is None or not hasattr(source, "snapshots"):
        raise ValueError("source read evidence unavailable")
    snapshots: Sequence[Snapshot] = tuple(source.snapshots)
    fixture = Fixture(job.fixture.fixture_uid, job.fixture.kickoff_utc)
    if job.family == "BASE":
        details = {}
        usable = 0
        missing = []
        t6_missing = []
        for market in _MARKETS:
            snap6 = select_snapshot(fixture, market, 6, snapshots) if job.hours == 6 else None
            snap8 = select_snapshot(fixture, market, 8, snapshots)
            chosen = snap6 if snap6 is not None else snap8
            hours = 6 if snap6 is not None else (8 if snap8 is not None else None)
            reported = payload.get("markets", {}).get(market, {}).get("checkpoint")
            if reported != hours:
                raise ValueError("market/source checkpoint conflict")
            if chosen is None:
                missing.append(market)
            else:
                usable += 1
            if job.hours == 6 and snap6 is None:
                t6_missing.append(market)
            details[market] = {
                "selected_checkpoint": hours,
                "source_observed_at": chosen.observed_at.isoformat() if chosen else None,
                "authority": ("T6" if snap6 else
                              "T8_PRELIMINARY" if job.hours == 8 and snap8 else
                              "T8_FALLBACK" if snap8 else "MISSING"),
            }
        return {
            "disposition": "WAITING_DATA" if usable == 0 else "EVALUATE",
            "state": "MISSING_ALL" if usable == 0 else
                     ("PARTIAL" if missing or t6_missing else "COMPLETE"),
            "markets": details,
            "missing_markets": missing,
            "missing_t6_markets": t6_missing,
            "requires_reconciliation": bool(missing or t6_missing),
        }

    if job.family == "EARLY_CORE":
        required = tuple(h for h in _EARLY_CORE if h >= job.hours)
    elif job.family == "EARLY_T12":
        required = (12,)
    elif job.family == "EARLY_RETENTION":
        required = _EARLY_CORE + tuple(h for h in _RETENTION if h >= job.hours)
    else:
        raise ValueError("unknown checkpoint family")
    observations = {
        str(hour): select_snapshot(fixture, "1X2", hour, snapshots)
        for hour in required
    }
    missing_hours = [hour for hour in required if observations[str(hour)] is None]
    return {
        "disposition": "WAITING_DATA" if missing_hours else "EVALUATE",
        "state": "PARTIAL" if missing_hours else "COMPLETE",
        "required_1x2_checkpoints": list(required),
        "missing_1x2_checkpoints": missing_hours,
        "observed_at": {k: (v.observed_at.isoformat() if v else None)
                        for k, v in observations.items()},
        "requires_reconciliation": bool(missing_hours),
    }
