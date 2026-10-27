"""Checkpoint-driven, read-only orchestration for SXF Base signals.

No scraper, DB writes, betting, deployment or notification side-effects.
Input/output ports are injected. A checkpoint record is immutable and replayable;
the durable journal/storage implementation belongs to a separate phase.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Protocol, Sequence

from .rules import (
    Fixture, Snapshot, _utc, choose_base_checkpoint, evaluate_base,
    evaluate_early, evaluate_early_t12, select_snapshot,
)

# Prospective V3 release identity: V1/V2 immutable history remains untouched.
RULESET_VERSION = "SXF_SIGNAL_MOTOR_V4_2026_10_27"
INGESTION_GRACE = timedelta(minutes=10)
# Early's T-5/T-4/T-3 checkpoints are retention ONLY, not Base triggers.
CHECKPOINT_TASKS = (
    (72, "EARLY_CORE"), (60, "EARLY_CORE"), (40, "EARLY_CORE"),
    (24, "EARLY_CORE"), (12, "EARLY_T12"),
    (8, "BASE"), (6, "BASE"), (6, "EARLY_RETENTION"),
    (5, "EARLY_RETENTION"), (4, "EARLY_RETENTION"), (3, "EARLY_RETENTION"),
)


@dataclass(frozen=True)
class FixtureRef:
    fixture_uid: str
    kickoff_utc: datetime
    match_id_hash: str = ""

    def __post_init__(self):
        if not self.fixture_uid:
            raise ValueError("fixture UID required")
        object.__setattr__(self, "kickoff_utc", _utc(self.kickoff_utc))


@dataclass(frozen=True)
class CheckpointJob:
    fixture: FixtureRef
    hours: int
    family: str

    @property
    def timestamp(self) -> datetime:
        return self.fixture.kickoff_utc - timedelta(hours=self.hours)

    @property
    def key(self) -> str:
        return f"{RULESET_VERSION}:{self.fixture.fixture_uid}:{self.fixture.kickoff_utc.isoformat()}:{self.family}:T-{self.hours}"


class SnapshotPort(Protocol):
    def load_fixture(self, fixture_uid: str) -> tuple[Fixture, str]: ...
    def load_checkpoints(self, fixture: Fixture, *, hours: Sequence[int],
                         as_of_utc: datetime, include_v2_history: bool = True,
                         expected_legacy_hash: str = ""): ...


class CompletionPort(Protocol):
    def has_completed(self, key: str) -> bool: ...
    def commit(self, key: str, payload: dict) -> bool: ...


def due_jobs(fixtures: Sequence[FixtureRef], now: datetime, completed: CompletionPort,
             *, grace: timedelta = INGESTION_GRACE, limit: int = 250) -> list[CheckpointJob]:
    """Every due task is replayable; no T-5/4/3 Base task exists.

    The caller must enumerate all fixtures in its backlog. Limit controls safe
    gradual recovery after outages, never silently drops work.
    """
    at = _utc(now)
    if grace < timedelta(0) or limit < 1:
        raise ValueError("invalid grace/limit")
    jobs = []
    seen = set()
    for fixture in fixtures:
        for hours, family in CHECKPOINT_TASKS:
            job = CheckpointJob(fixture, hours, family)
            if job.key in seen or job.timestamp + grace > at or completed.has_completed(job.key):
                continue
            seen.add(job.key)
            jobs.append(job)
    return sorted(jobs, key=lambda j: (j.timestamp, j.fixture.fixture_uid, j.family))[:limit]


def _serialize_signal(signal) -> dict:
    return {"engine": signal.engine, "side": signal.side,
            "checkpoint": signal.checkpoint, "odds": str(signal.odds),
            "amount": str(signal.amount), "share": str(signal.share),
            "observed_at": signal.observed_at.isoformat(),
            "label": signal.label, "selection_status": signal.selection_status}


def _market_for_engine(name: str) -> str:
    if name.startswith(("1X2_", "HEAVY_", "SURPRISE_")):
        return "1X2"
    if "OVER" in name:
        return "OU25"
    if name.startswith("BTTS_"):
        return "BTTS"
    raise ValueError("unknown signal engine: " + name)


def _reader_hours(job: CheckpointJob) -> tuple[int, ...]:
    if job.family == "BASE":
        return (8,) if job.hours == 8 else (8, 6)
    if job.family == "EARLY_T12":
        return (12,)
    if job.family == "EARLY_CORE":
        return tuple(h for h in (72, 60, 40, 24) if h >= job.hours)
    if job.family == "EARLY_RETENTION":
        # Read only already due retention checkpoints, never inspect the future.
        return (72, 60, 40, 24) + tuple(h for h in (6, 5, 4, 3) if h >= job.hours)
    raise ValueError("unsupported checkpoint family")


def evaluate_job(job: CheckpointJob, reader: SnapshotPort,
                 *, grace: timedelta = INGESTION_GRACE) -> dict:
    """Evaluate a job as of its historical due time, NOT wall-clock now.

    If any database page fails, propagate error; the journal must not mark the
    job completed. No future snapshot can influence a replayed decision.
    """
    fixture, observed_hash = reader.load_fixture(job.fixture.fixture_uid)
    if (fixture.fixture_uid != job.fixture.fixture_uid or
            fixture.kickoff_utc != job.fixture.kickoff_utc):
        raise ValueError("fixture identity changed; refusing ambiguous checkpoint replay")
    cutoff = job.timestamp + grace
    data = reader.load_checkpoints(
        fixture, hours=_reader_hours(job), as_of_utc=cutoff,
        include_v2_history=job.family == "BASE",
        expected_legacy_hash=observed_hash,
    )
    snaps = data.snapshots
    payload = {"key": job.key, "ruleset": RULESET_VERSION,
               "fixture_uid": job.fixture.fixture_uid, "legacy_hash": observed_hash,
               "kickoff_utc": fixture.kickoff_utc.isoformat(),
               "checkpoint": job.hours, "family": job.family,
               "checkpoint_utc": job.timestamp.isoformat(),
               "evaluated_as_of_utc": cutoff.isoformat(),
               "fetched_rows": data.fetched_rows,
               "discarded_groups": data.discarded_groups,
               "hash_drift_rows": data.hash_drift_rows,
               "markets": {}, "signals": [], "status": "EVALUATED"}

    if job.family == "BASE":
        evaluations = {}
        for market in ("1X2", "OU25", "BTTS"):
            chosen, state = choose_base_checkpoint(fixture, market, snaps, cutoff, grace=grace)
            payload["markets"][market] = {"checkpoint": chosen, "state": state}
            if chosen is None:
                continue
            if chosen not in evaluations:
                evaluations[chosen] = evaluate_base(fixture, chosen, snaps)
            result = evaluations[chosen]
            payload["markets"][market]["v2_state"] = result.v2_state if market == "1X2" else "N/A"
            payload["signals"].extend(_serialize_signal(s) for s in result.signals
                                      if _market_for_engine(s.engine) == market)
    elif job.family == "EARLY_T12":
        signal = evaluate_early_t12(fixture, snaps)
        payload["status"] = "SIGNAL" if signal else "NO_SIGNAL"
        if signal:
            payload["signals"] = [_serialize_signal(signal)]
    else:
        early = evaluate_early(fixture, snaps)
        if job.family == "EARLY_CORE":
            # Store first qualifying Core only at its own checkpoint.
            found = early.core_signal
            signal = found if found and found.checkpoint == job.hours else None
            # A true earliest/Core first-hit is only verified when all
            # earlier checkpoints have causal, complete 1X2 evidence.
            # If earlier snapshots do not exist, preserve a REAL current
            # candidate but mark its historical-first status unverified.
            history_gaps = [
                h for h in (72, 60, 40, 24) if h > job.hours
                and select_snapshot(fixture, "1X2", h, snaps) is None
            ]
            payload["missing_prior_early_checkpoints"] = history_gaps
            payload["status"] = (
                "HISTORY_INCOMPLETE_SIGNAL" if signal and history_gaps else
                "SIGNAL" if signal else "NO_NEW_SIGNAL"
            )
            if signal:
                item = _serialize_signal(signal)
                if history_gaps and item["selection_status"] == "ELIGIBLE":
                    item["selection_status"] = "HISTORY_INCOMPLETE"
                    item["label"] = "FIRST_OBSERVED_NOT_VERIFIED"
                payload["signals"] = [item]
                payload["t24_cohort"] = early.t24_cohort
        else:
            state = dict(early.retention_checkpoints).get(job.hours, "NO_CORE_SIGNAL")
            payload["status"] = state
            payload["retention"] = {"first_core_checkpoint": early.core_signal.checkpoint if early.core_signal else None,
                                     "first_core_side": early.core_signal.side if early.core_signal else None,
                                     "current_checkpoint_state": state,
                                     "overall_state": early.retention_status}
    return payload


def process_due_jobs(fixtures: Sequence[FixtureRef], now: datetime,
                     reader: SnapshotPort, journal: CompletionPort,
                     *, grace: timedelta = INGESTION_GRACE,
                     limit: int = 250, verify_source: bool = False) -> dict:
    """Fail-closed per job, continue others; missing source retries next cycle.

    For real shadow scans, verify_source=True is mandatory: an absent historic
    snapshot is WAITING_DATA, *not* an evaluated/completed checkpoint. This
    changes only lifecycle integrity, never motor rules or thresholds.
    """
    jobs = due_jobs(fixtures, now, journal, grace=grace, limit=limit)
    stats = {"due": len(jobs), "committed": 0, "already_done": 0,
             "failed": 0, "waiting_data": 0, "errors": []}
    for job in jobs:
        try:
            if verify_source:
                # Local import avoids scheduler <-> source_quality module cycle.
                from .source_quality import CapturingReader, source_coverage
                capture = CapturingReader(reader)
                payload = evaluate_job(job, capture, grace=grace)
                coverage = source_coverage(job, capture.source, payload)
                if coverage["disposition"] != "EVALUATE":
                    stats["waiting_data"] += 1
                    continue   # IMPORTANT: never write an empty-data checkpoint.
                payload["source_coverage"] = coverage
            else:
                payload = evaluate_job(job, reader, grace=grace)
            if journal.commit(job.key, payload):
                stats["committed"] += 1
            else:
                stats["already_done"] += 1
        except Exception as exc:
            stats["failed"] += 1
            # Never log credentials, full exception URLs or raw HTTP payloads.
            stats["errors"].append({"key": job.key, "error_type": type(exc).__name__})
    return stats