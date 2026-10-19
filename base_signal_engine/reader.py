"""Read-only, UID-scoped Supabase Moneyway snapshot adapter.

No DDL, writes, hash-only matching, current-state substitution, or fabricated
checkpoint data. This is the input boundary for the future 24/7 Base worker.

Only public.fixtures and public.moneyway_snapshots are read. This adapter does
not start a worker or schedule/deploy anything. Each read is cutoff-bounded and
page-complete; failures raise instead of returning partial signals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping, Sequence
from uuid import UUID

import requests

from .rules import Fixture, Quote, Snapshot, CHECKPOINT_FRESHNESS, _utc

_REQUIRED = {"1X2": frozenset(("1", "X", "2")),
             "OU25": frozenset(("O", "U")),
             "BTTS": frozenset(("Y", "N"))}
_HISTORY_HOURS = (72, 60, 40, 24, 12, 8, 6, 5, 4, 3)


class SnapshotReadError(RuntimeError):
    """The database read cannot prove completeness; no signals may be emitted."""


@dataclass(frozen=True)
class SnapshotReadResult:
    fixture: Fixture
    snapshots: tuple[Snapshot, ...]
    fetched_rows: int
    discarded_groups: int
    hash_drift_rows: int
    queried_windows: tuple[tuple[datetime, datetime], ...]
    # Only fully verified market groups; durable proof for later reconciliation.
    source_row_ids: Mapping[tuple[str, datetime], tuple[int, ...]] = field(default_factory=dict)


def _parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _utc(value)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing timestamp")
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    return _utc(dt)


def _canonical_uid(value: Any) -> str:
    return str(UUID(str(value)))


def _iso(value: datetime) -> str:
    return _utc(value).isoformat(timespec="microseconds")


def _merge_intervals(intervals: Sequence[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


class SupabaseMoneywayReader:
    """Bounded PostgREST GET-only adapter. Supply a server-side credential.

    The constructor accepts an injected HTTP session for isolated tests. Never
    log/serialize the credential; no REST method other than GET is used.
    """

    def __init__(self, base_url: str, service_key: str, *, session: Any = None,
                 page_size: int = 750, max_pages_per_window: int = 200,
                 request_timeout_seconds: float = 20):
        if not base_url.startswith("https://") or not service_key:
            raise ValueError("HTTPS Supabase URL and server credential required")
        if not 1 <= page_size <= 1000 or max_pages_per_window < 1:
            raise ValueError("invalid bounded pagination")
        self._base = base_url.rstrip("/") + "/rest/v1"
        self._headers = {"apikey": service_key, "Authorization": "Bearer " + service_key}
        self._session = session if session is not None else requests.Session()
        self.page_size = page_size
        self.max_pages = max_pages_per_window
        self.timeout = request_timeout_seconds

    def _get(self, table: str, params: list[tuple[str, str]]) -> list[Mapping[str, Any]]:
        # Only hardcoded read-only tables are accessible via this method.
        if table not in ("fixtures", "moneyway_snapshots"):
            raise ValueError("not an allowed source table")
        try:
            response = self._session.get(self._base + "/" + table, params=params,
                                         headers=self._headers, timeout=self.timeout)
            if response.status_code not in (200, 206):
                raise SnapshotReadError(f"{table} read failed: HTTP {response.status_code}")
            body = response.json()
        except SnapshotReadError:
            raise
        except Exception as error:
            raise SnapshotReadError(f"{table} read failed ({type(error).__name__})") from error
        if not isinstance(body, list) or any(not isinstance(row, dict) for row in body):
            raise SnapshotReadError(f"{table} returned unexpected payload")
        return body

    def load_fixture(self, fixture_uid: str) -> tuple[Fixture, str]:
        """Resolve physical fixture by UID; return kernel fixture and legacy hash for audit."""
        uid = _canonical_uid(fixture_uid)
        rows = self._get("fixtures", [
            ("select", "fixture_uid,match_id_hash,kickoff_utc"),
            ("fixture_uid", "eq." + uid), ("limit", "2"),
        ])
        if len(rows) != 1:
            raise SnapshotReadError("fixture_uid is missing or non-unique")
        row = rows[0]
        try:
            if _canonical_uid(row["fixture_uid"]) != uid:
                raise ValueError("fixture UID differs from requested UID")
            fixture = Fixture(uid, _parse_time(row["kickoff_utc"]))
            match_hash = str(row.get("match_id_hash") or "").strip()
        except (KeyError, TypeError, ValueError) as error:
            raise SnapshotReadError("invalid fixture identity or kickoff") from error
        return fixture, match_hash

    def load_checkpoints(self, fixture: Fixture, *, hours: Sequence[int],
                         as_of_utc: datetime, include_v2_history: bool = True,
                         expected_legacy_hash: str = "") -> SnapshotReadResult:
        """Read all complete 1X2/OU25/BTTS snapshots for due checkpoints.

        V2 needs the full preceding three hours of 1X2 observations. Therefore
        each T-6/T-8 requested checkpoint widens its interval to [T-(h+3)-30m,T-h].
        The amount of data fetched is bounded by pagination; oversized or
        failed reads abort rather than accidentally treating rows as absent.
        """
        uid = _canonical_uid(fixture.fixture_uid)
        now = _utc(as_of_utc)
        intervals: list[tuple[datetime, datetime]] = []
        for h in sorted(set(hours), reverse=True):
            if h not in _HISTORY_HOURS:
                raise ValueError(f"unsupported checkpoint: {h}")
            endpoint = fixture.kickoff_utc - timedelta(hours=h)
            if endpoint > now:
                continue  # Future checkpoint is NOT an absent snapshot.
            widen = timedelta(hours=3) if include_v2_history and h in (6, 8) else timedelta(0)
            intervals.append((endpoint - CHECKPOINT_FRESHNESS - widen, endpoint))
        windows = _merge_intervals(intervals)
        fetched: list[Mapping[str, Any]] = []
        seen_ids: set[str] = set()
        for start, end in windows:
            complete = False
            for page in range(self.max_pages):
                rows = self._get("moneyway_snapshots", [
                    ("select", "id,fixture_uid,match_id_hash,market,selection,odds,volume,share,scraped_at_utc"),
                    ("fixture_uid", "eq." + uid),
                    ("scraped_at_utc", "gte." + _iso(start)),
                    ("scraped_at_utc", "lte." + _iso(end)),
                    ("order", "scraped_at_utc.asc,id.asc"),
                    ("limit", str(self.page_size)),
                    ("offset", str(page * self.page_size)),
                ])
                for row in rows:
                    rid = str(row.get("id") or "")
                    if not rid or rid in seen_ids:
                        raise SnapshotReadError("non-unique/missing snapshot id across pages")
                    seen_ids.add(rid)
                    try:
                        row_uid = _canonical_uid(row["fixture_uid"])
                        observed = _parse_time(row["scraped_at_utc"])
                    except (ValueError, TypeError, KeyError) as error:
                        raise SnapshotReadError("invalid snapshot identity or time") from error
                    if row_uid != uid or not (start <= observed <= end) or observed > now:
                        raise SnapshotReadError("cross-fixture, future or out-of-window snapshot")
                    fetched.append(row)
                if len(rows) < self.page_size:
                    complete = True
                    break
            if not complete:
                raise SnapshotReadError("pagination cap reached; partial snapshot history refused")

        groups: dict[tuple[str, datetime], list[Mapping[str, Any]]] = {}
        drift = 0
        for row in fetched:
            if expected_legacy_hash and row.get("match_id_hash") != expected_legacy_hash:
                drift += 1  # Legacy display hash can legitimately drift; UID remains authoritative.
            market = str(row.get("market") or "")
            observed = _parse_time(row["scraped_at_utc"])
            groups.setdefault((market, observed), []).append(row)

        discarded = 0
        snapshots: list[Snapshot] = []
        provenanced: dict[tuple[str, datetime], tuple[int, ...]] = {}
        for (market, observed), rows in sorted(groups.items(), key=lambda x: (x[0][1], x[0][0])):
            expected = _REQUIRED.get(market)
            if expected is None or len(rows) != len(expected):
                discarded += 1
                continue
            try:
                sides = {str(row["selection"]) for row in rows}
                if sides != expected:
                    discarded += 1
                    continue
                quotes = {str(row["selection"]): Quote(
                    odds=Decimal(str(row["odds"])),
                    amount=Decimal(str(row["volume"])),
                    share=Decimal(str(row["share"]))) for row in rows}
                snapshot = Snapshot(market, observed, quotes)
                raw_ids = [int(row['id']) for row in rows]
                if any(x <= 0 for x in raw_ids) or len(set(raw_ids)) != len(raw_ids):
                    discarded += 1
                    continue
                if not snapshot.complete:
                    discarded += 1
                    continue
            except (ValueError, TypeError, KeyError, ArithmeticError):
                discarded += 1
                continue
            snapshots.append(snapshot)
            provenanced[(market, observed)] = tuple(sorted(raw_ids))
        return SnapshotReadResult(fixture, tuple(snapshots), len(fetched), discarded,
                                  drift, tuple(windows), provenanced)