"""Frozen SXF base signal definitions from MAÇ. MOTOR V1.1 (2026-10-18).

This module is a *pure calculation kernel*, not a deployed signal worker. It
intentionally never fetches, inserts, updates or deletes data. Older checkpoint
rules in the source document are superseded by the user's explicit 2026-10-18
BASE decision: T-6 takes precedence, T-8 only when T-6 data is unavailable.
Early Money Core retains its independent 72/60/40/24 and 6/5/4/3 schedule.
Surprise Hold, Draw Trap and experimental growth are intentionally excluded.

T-24 Early is a cohort of Early Core, NOT a separate frozen engine. The
standalone EARLY_MONEY_T12 engine was retired on 2026-10-30.

Operational freshness uses the historic 30-minute observation window. Exact
production latency/grace and identity checks belong to the future worker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Mapping, Sequence


BASE_CHECKPOINTS = (8, 6)
EARLY_CORE_CHECKPOINTS = (72, 60, 40, 24)
EARLY_RETENTION_CHECKPOINTS = (6, 5, 4, 3)
CHECKPOINT_FRESHNESS = timedelta(minutes=59)
PRICE_FLOOR = Decimal("1.30")
SHARE_TOLERANCE = Decimal("0.5")


def d(value: object) -> Decimal:
    return Decimal(str(value))


def _utc(ts: datetime) -> datetime:
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError("all timestamps must be timezone-aware")
    return ts.astimezone(timezone.utc)


@dataclass(frozen=True)
class Quote:
    odds: Decimal
    amount: Decimal
    share: Decimal

    def __post_init__(self) -> None:
        for name in ("odds", "amount", "share"):
            value = d(getattr(self, name))
            if not value.is_finite():
                raise ValueError(f"{name} must be finite")
            object.__setattr__(self, name, value)
        if self.odds < 1 or self.amount < 0 or not (0 <= self.share <= 100):
            raise ValueError("invalid price, money or money share")


@dataclass(frozen=True)
class Fixture:
    fixture_uid: str
    kickoff_utc: datetime

    def __post_init__(self) -> None:
        if not self.fixture_uid.strip():
            raise ValueError("fixture_uid required; legacy hash alone is insufficient")
        object.__setattr__(self, "kickoff_utc", _utc(self.kickoff_utc))


@dataclass(frozen=True)
class Snapshot:
    market: str
    observed_at: datetime
    quotes: Mapping[str, Quote]

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", _utc(self.observed_at))
        if self.market not in {"1X2", "OU25", "BTTS"}:
            raise ValueError("unsupported market")

    @property
    def complete(self) -> bool:
        expected = {"1X2": {"1", "X", "2"}, "OU25": {"O", "U"}, "BTTS": {"Y", "N"}}[self.market]
        if set(self.quotes) != expected:
            return False
        if any(not isinstance(q, Quote) for q in self.quotes.values()):
            return False
        return abs(sum((q.share for q in self.quotes.values()), Decimal(0)) - 100) <= SHARE_TOLERANCE


@dataclass(frozen=True)
class Signal:
    engine: str
    side: str
    checkpoint: int
    odds: Decimal
    amount: Decimal
    share: Decimal
    observed_at: datetime
    label: str = "SIGNAL"
    selection_status: str = "ELIGIBLE"


@dataclass(frozen=True)
class CheckpointEvaluation:
    checkpoint: int
    signals: tuple[Signal, ...] = ()
    market_states: Mapping[str, str] = field(default_factory=dict)
    v2_state: str = "NOT_EVALUATED"


@dataclass(frozen=True)
class EarlyEvaluation:
    core_signal: Signal | None
    t24_cohort: bool
    retention_status: str
    retention_checkpoints: tuple[tuple[int, str], ...]
    core_v2_signal: Signal | None = None


def checkpoint_time(fixture: Fixture, hours: int) -> datetime:
    return fixture.kickoff_utc - timedelta(hours=hours)


def select_snapshot(
    fixture: Fixture,
    market: str,
    hours: int,
    snapshots: Sequence[Snapshot],
) -> Snapshot | None:
    """Nearest complete historical quote in [T-h-59m, T-h], never later than T-h."""
    when = checkpoint_time(fixture, hours)
    return next((s for s in sorted(snapshots, key=lambda x: x.observed_at, reverse=True)
                 if s.market == market and s.complete
                 and when - CHECKPOINT_FRESHNESS <= s.observed_at <= when), None)


def _make(engine: str, side: str, hours: int, snap: Snapshot, label: str = "SIGNAL") -> Signal:
    q = snap.quotes[side]
    return Signal(engine, side, hours, q.odds, q.amount, q.share, snap.observed_at,
                  label, "PRICE_FILTER_REJECT" if q.odds < PRICE_FLOOR else "ELIGIBLE")


def _top_team(snap: Snapshot) -> str:
    # Highest HOME/AWAY volume, never DRAW. Ties use deterministic HOME precedence.
    return "1" if snap.quotes["1"].amount >= snap.quotes["2"].amount else "2"


def _v2_valid(
    fixture: Fixture,
    hours: int,
    side: str,
    snapshots: Sequence[Snapshot],
) -> tuple[bool, str]:
    """Three-hour persistence, fail-closed when an hourly anchor is missing.

    Each anchor T-(h+3), T-(h+2), T-(h+1), T-h needs a fresh 1X2 market.
    All complete observed snapshots in that window are checked for share dips
    and odds rising >3% from ANY earlier observed trough (chronological
    running minimum), not merely from the first anchored quote. Incomplete
    snapshots are not evidence for meeting the persistence requirement.
    """
    anchors = [select_snapshot(fixture, "1X2", h, snapshots) for h in (hours+3, hours+2, hours+1, hours)]
    if any(s is None for s in anchors):
        return False, "MISSING_THREE_HOUR_COVERAGE"
    # Every V2 hourly anchor must be distinct; a single stale observation
    # cannot prove three hours of persistence.
    if len({s.observed_at for s in anchors if s is not None}) != 4:
        return False, "DUPLICATE_HOURLY_ANCHORS"
    first = anchors[0]
    assert first is not None
    latest = anchors[-1]
    assert latest is not None
    window = [s for s in snapshots if s.market == "1X2" and s.complete
              and first.observed_at <= s.observed_at <= latest.observed_at]
    if any(s.quotes[side].share < 70 for s in window):
        return False, "THREE_HOUR_SHARE_BREAK"
    # Inspect in source-time order: a rebound above 3% from ANY earlier
    # observed low is adverse even when the initial T-(h+3) quote was higher.
    # A future trough must never be used to reject a past observation.
    trough = first.quotes[side].odds
    for snap in sorted(window, key=lambda s: s.observed_at):
        odds = snap.quotes[side].odds
        if odds > trough * d("1.03"):
            return False, "THREE_HOUR_ADVERSE_ODDS"
        trough = min(trough, odds)
    return True, "QUALIFIED"


def evaluate_base(fixture: Fixture, hours: int, snapshots: Sequence[Snapshot]) -> CheckpointEvaluation:
    if hours not in BASE_CHECKPOINTS:
        raise ValueError("Base motors accept only T-6 or T-8; T-5/4/3 are not base checkpoints")
    states: dict[str, str] = {}
    hits: list[Signal] = []
    v2_state = "NOT_EVALUATED"
    home_market = select_snapshot(fixture, "1X2", hours, snapshots)
    if home_market is None:
        states["1X2"] = "INSUFFICIENT_DATA"
        v2_state = "INSUFFICIENT_DATA"
    else:
        states["1X2"] = "EVALUATED"
        side = _top_team(home_market)
        quote = home_market.quotes[side]
        v1 = quote.amount >= 1000 and quote.share >= 80 and d("1.40") <= quote.odds <= d("2.50")
        if v1:
            hits.append(_make("1X2_CONCENTRATION_V1", side, hours, home_market))
            v2, v2_state = _v2_valid(fixture, hours, side, snapshots)
            if v2:
                hits.append(_make("1X2_CONCENTRATION_V2", side, hours, home_market))
        else:
            v2_state = "V1_NOT_QUALIFIED"
        # HEAVY is a stronger V1 tag, never a standalone pick. A high share
        # and amount cannot bypass V1's inclusive 1.40–2.50 odds requirement.
        if v1 and quote.amount >= 10000:
            hits.append(_make("HEAVY_1X2_CONCENTRATION", side, hours, home_market, "STRENGTH_TAG"))
        for s in ("1", "2"):
            q = home_market.quotes[s]
            if d("2.90") <= q.odds <= d("4.49") and q.share >= 50:
                hits.append(_make("SURPRISE_TEAM", s, hours, home_market))

    over_market = select_snapshot(fixture, "OU25", hours, snapshots)
    if over_market is None:
        states["OU25"] = "INSUFFICIENT_DATA"
    else:
        states["OU25"] = "EVALUATED"
        over = over_market.quotes["O"]
        if d("1.40") <= over.odds <= d("1.80"):
            if over.amount >= 1500 and over.share >= 65:
                hits.append(_make("STABLE_OVER_2_5", "O", hours, over_market))
            if over.amount >= 2500 and over.share >= 75:
                hits.append(_make("PREMIUM_OVER_2_5", "O", hours, over_market, "STRENGTH_TAG"))
                if over.odds >= d("1.70"):
                    hits.append(_make("PREMIUM_OVER_MIN1_70", "O", hours, over_market, "STRENGTH_TAG"))

    btts_market = select_snapshot(fixture, "BTTS", hours, snapshots)
    if btts_market is None:
        states["BTTS"] = "INSUFFICIENT_DATA"
    else:
        states["BTTS"] = "EVALUATED"
        yes = btts_market.quotes["Y"]
        if yes.amount >= 750 and yes.share >= 60 and d("1.60") <= yes.odds <= d("1.90"):
            hits.append(_make("BTTS_YES", "Y", hours, btts_market))

    return CheckpointEvaluation(hours, tuple(hits), states, v2_state)


def choose_base_checkpoint(
    fixture: Fixture,
    market: str,
    snapshots: Sequence[Snapshot],
    now: datetime,
    grace: timedelta = timedelta(minutes=10),
) -> tuple[int | None, str]:
    """Authority selection for the future worker; grace is explicit/overridable.

    T-8 can be preliminary before T-6. After T-6 and ingestion grace, T-8 is
    fallback only if a valid T-6 snapshot is absent. A failed T-6 *rule* is NOT
    an excuse to fall back to T-8.
    """
    at = _utc(now)
    cp8, cp6 = checkpoint_time(fixture, 8), checkpoint_time(fixture, 6)
    if at < cp8:
        return None, "NOT_DUE"
    if at < cp6:
        return (8, "PRELIMINARY_T8") if select_snapshot(fixture, market, 8, snapshots) else (None, "INSUFFICIENT_DATA")
    if select_snapshot(fixture, market, 6, snapshots):
        return 6, "AUTHORITATIVE_T6"
    if at < cp6 + grace:
        return None, "WAITING_FOR_T6_INGESTION"
    # A missing T-6 market is SKIPPED, not silently substituted with a
    # T-8 price from another checkpoint. The earlier T-8 remains historical.
    return None, "INSUFFICIENT_DATA"


def evaluate_early(fixture: Fixture, snapshots: Sequence[Snapshot]) -> EarlyEvaluation:
    first: Signal | None = None
    for hours in EARLY_CORE_CHECKPOINTS:
        snap = select_snapshot(fixture, "1X2", hours, snapshots)
        if snap is None:
            continue
        side = _top_team(snap)
        q = snap.quotes[side]
        minimum = 5000 if hours in (72, 60) else 10000
        if q.amount >= minimum and q.share >= 50:
            first = _make("EARLY_MONEY_CORE", side, hours, snap)
            break
    if first is None:
        return EarlyEvaluation(None, False, "NO_CORE_SIGNAL", (), None)

    # EARLY CORE V2 is a separate engine built from the same first-hit CORE
    # candidate. Its first signal must also be a favorite (<2.00) and must
    # avoid extreme concentration (share <95%). Retention-55 is tracked below.
    core_v2 = None
    first_snapshot = select_snapshot(fixture, "1X2", first.checkpoint, snapshots)
    if first_snapshot is not None:
        first_quote = first_snapshot.quotes[first.side]
        if first_quote.odds < d("2.00") and first_quote.share < d("95"):
            core_v2 = _make("EARLY_MONEY_CORE_V2", first.side, first.checkpoint, first_snapshot)

    states = []
    broken = False
    missing = False
    for hours in EARLY_RETENTION_CHECKPOINTS:
        snap = select_snapshot(fixture, "1X2", hours, snapshots)
        if snap is None:
            missing = True
            states.append((hours, "INSUFFICIENT_DATA"))
        elif snap.quotes[first.side].share < 55:
            broken = True
            states.append((hours, "RETENTION_BREAK"))
        else:
            states.append((hours, "RETAINED_AT_CHECKPOINT"))
    status = "RETENTION_BREAK" if broken else ("INSUFFICIENT_DATA" if missing else "RETAINED")
    return EarlyEvaluation(first, first.checkpoint == 24, status, tuple(states), core_v2)


