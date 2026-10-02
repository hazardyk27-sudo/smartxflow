"""Market-movement feature engine for SmartXFlow Analysis V2.

The canonical source is ``moneyway_snapshots`` because it stores the same
per-selection shape for every supported market, including real provider DC/DNB
when those markets exist. The engine is deliberately descriptive: it measures
price and money movement but does not classify a bet as good/bad; classification
belongs to Analysis V2 Part 4.

Backtest safety rule: every anchor is selected strictly *as of* its target
instant. A later snapshot is never used to fill an earlier 6h/2h/30m anchor.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

import requests

from .market_contract import get_market
from .signal_store import validate_match_id_hash


WINDOWS = {
    "6h": timedelta(hours=6),
    "2h": timedelta(hours=2),
    "30m": timedelta(minutes=30),
}

SNAPSHOT_COLUMNS = (
    "id,match_id_hash,market,selection,odds,volume,share,scraped_at_utc"
)


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        raw = str(value or "").strip()
        if not raw:
            raise ValueError("timestamp is required")
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"invalid ISO timestamp: {raw}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _number(value: Any) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = (
        str(value)
        .strip()
        .replace("£", "")
        .replace("$", "")
        .replace("%", "")
        .replace(" ", "")
    )
    if "," in text and "." in text:
        text = text.replace(",", "")
    elif "," in text:
        left, right = text.rsplit(",", 1)
        text = (
            left + right
            if len(right) == 3 and left.replace("-", "").isdigit()
            else left + "." + right
        )
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class MovementPoint:
    at: datetime
    odds: Optional[float]
    pct: Optional[float]
    amount: Optional[float]
    market_volume: Optional[float]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "at": _iso(self.at),
            "odds": self.odds,
            "pct": self.pct,
            "amount": self.amount,
            "market_volume": self.market_volume,
        }


def _canonical_market_selection(market_key: str, selection_code: str):
    market = get_market(str(market_key or "").strip().upper())
    selection = str(selection_code or "").strip().upper()
    if selection not in market.selections:
        raise ValueError(
            f"unknown selection {selection!r} for market {market.key!r}"
        )
    return market.key, selection


def _dedupe_market_rows(
    rows: Iterable[Dict[str, Any]]
) -> Dict[datetime, Dict[str, Dict[str, Any]]]:
    """Group rows by timestamp and keep one row per selection.

    Scraper writes every runner from the same market cycle with the same
    ``scraped_at_utc``. If a duplicate exists, the largest numeric id wins.
    """
    grouped: Dict[datetime, Dict[str, Dict[str, Any]]] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        try:
            at = _timestamp(raw.get("scraped_at_utc"))
        except ValueError:
            continue
        selection = str(raw.get("selection") or "").strip().upper()
        if not selection:
            continue
        bucket = grouped.setdefault(at, {})
        current = bucket.get(selection)
        if current is None:
            bucket[selection] = raw
            continue
        try:
            current_id = int(current.get("id") or 0)
            new_id = int(raw.get("id") or 0)
        except (TypeError, ValueError):
            current_id = new_id = 0
        if new_id >= current_id:
            bucket[selection] = raw
    return grouped


def build_selection_points(
    rows: Iterable[Dict[str, Any]],
    *,
    match_id_hash: str,
    market_key: str,
    selection_code: str,
    as_of: Any,
) -> List[MovementPoint]:
    """Normalize raw ``moneyway_snapshots`` rows into per-cycle points.

    ``amount`` is the selected runner's real matched amount (snapshot volume).
    ``market_volume`` is reconstructed only from real sibling-runner amounts in
    the *same provider market and scrape cycle*. It is never synthesized from
    a different market such as 1X2 -> Double Chance.
    """
    match_hash = validate_match_id_hash(match_id_hash)
    market, selection = _canonical_market_selection(market_key, selection_code)
    cutoff = _timestamp(as_of)

    filtered = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_hash = str(row.get("match_id_hash") or "").strip().lower()
        row_market = str(row.get("market") or "").strip().upper()
        if row_hash != match_hash or row_market != market:
            continue
        try:
            row_at = _timestamp(row.get("scraped_at_utc"))
        except ValueError:
            continue
        if row_at <= cutoff:
            filtered.append(row)

    grouped = _dedupe_market_rows(filtered)
    points: List[MovementPoint] = []
    for at in sorted(grouped):
        bucket = grouped[at]
        selected = bucket.get(selection)
        if selected is None:
            continue

        amount = _number(selected.get("volume"))
        pct = _number(selected.get("share"))
        odds = _number(selected.get("odds"))

        sibling_amounts = [
            _number(item.get("volume")) for item in bucket.values()
        ]
        real_amounts = [value for value in sibling_amounts if value is not None]
        market_volume = sum(real_amounts) if real_amounts else None

        points.append(
            MovementPoint(
                at=at,
                odds=odds,
                pct=pct,
                amount=amount,
                market_volume=market_volume,
            )
        )
    return points


def _asof_point(
    points: Sequence[MovementPoint],
    target: datetime,
    *,
    tolerance: Optional[timedelta],
) -> Optional[MovementPoint]:
    candidate = None
    for point in points:
        if point.at <= target:
            candidate = point
        else:
            break
    if candidate is None:
        return None
    if tolerance is not None and target - candidate.at > tolerance:
        return None
    return candidate


def _movement(
    base: Optional[MovementPoint],
    current: Optional[MovementPoint],
) -> Optional[Dict[str, Any]]:
    if base is None or current is None:
        return None

    odds_delta = None
    odds_change_pct = None
    odds_drop_pct = None
    if base.odds not in (None, 0) and current.odds is not None:
        odds_delta = current.odds - base.odds
        odds_change_pct = odds_delta / base.odds * 100.0
        odds_drop_pct = (base.odds - current.odds) / base.odds * 100.0

    return {
        "odds_delta": odds_delta,
        "odds_change_pct": odds_change_pct,
        "odds_drop_pct": odds_drop_pct,
        "pct_delta": (
            current.pct - base.pct
            if current.pct is not None and base.pct is not None
            else None
        ),
        "amount_delta": (
            current.amount - base.amount
            if current.amount is not None and base.amount is not None
            else None
        ),
        "market_volume_delta": (
            current.market_volume - base.market_volume
            if current.market_volume is not None
            and base.market_volume is not None
            else None
        ),
    }


def build_market_movement(
    rows: Iterable[Dict[str, Any]],
    *,
    match_id_hash: str,
    market_key: str,
    selection_code: str,
    as_of: Any,
    kickoff_utc: Any = None,
    anchor_tolerance_minutes: int = 60,
    current_tolerance_minutes: int = 60,
) -> Dict[str, Any]:
    """Build opening/6h/2h/30m movement features without future leakage."""
    as_of_dt = _timestamp(as_of)
    points = build_selection_points(
        rows,
        match_id_hash=match_id_hash,
        market_key=market_key,
        selection_code=selection_code,
        as_of=as_of_dt,
    )
    market, selection = _canonical_market_selection(
        market_key, selection_code
    )

    current = _asof_point(
        points,
        as_of_dt,
        tolerance=timedelta(minutes=current_tolerance_minutes),
    )
    opening = points[0] if points else None

    anchors: Dict[str, Optional[MovementPoint]] = {}
    targets: Dict[str, datetime] = {}
    for label, delta in WINDOWS.items():
        target = as_of_dt - delta
        targets[label] = target
        anchors[label] = _asof_point(
            points,
            target,
            tolerance=timedelta(minutes=anchor_tolerance_minutes),
        )

    hours_before_kickoff = None
    if kickoff_utc not in (None, ""):
        kickoff = _timestamp(kickoff_utc)
        hours_before_kickoff = (
            kickoff - as_of_dt
        ).total_seconds() / 3600.0

    return {
        "match_id_hash": validate_match_id_hash(match_id_hash),
        "market_key": market,
        "selection_code": selection,
        "as_of": _iso(as_of_dt),
        "hours_before_kickoff": hours_before_kickoff,
        "opening": opening.as_dict() if opening else None,
        "current": current.as_dict() if current else None,
        "anchors": {
            label: point.as_dict() if point else None
            for label, point in anchors.items()
        },
        "movement": {
            "open": _movement(opening, current),
            **{
                label: _movement(anchors[label], current)
                for label in WINDOWS
            },
        },
        "coverage": {
            "point_count": len(points),
            "current_available": current is not None,
            "opening_available": opening is not None,
            **{
                f"{label}_available": anchors[label] is not None
                for label in WINDOWS
            },
            "targets": {
                label: _iso(value) for label, value in targets.items()
            },
            "anchor_tolerance_minutes": int(anchor_tolerance_minutes),
            "current_tolerance_minutes": int(current_tolerance_minutes),
        },
    }


def movement_to_signal_fields(
    features: Dict[str, Any],
) -> Dict[str, Any]:
    """Flatten movement output into the immutable Part 2 trigger columns."""
    current = features.get("current") or {}
    opening = features.get("opening") or {}
    anchors = features.get("anchors") or {}
    movement = features.get("movement") or {}

    result: Dict[str, Any] = {
        "opening_odds": opening.get("odds"),
        "trigger_odds": current.get("odds"),
        "trigger_pct": current.get("pct"),
        "trigger_amount": current.get("amount"),
        "trigger_volume": current.get("market_volume"),
        "hours_before_kickoff": features.get("hours_before_kickoff"),
    }
    for label in WINDOWS:
        point = anchors.get(label) or {}
        result[f"odds_{label}"] = point.get("odds")
        result[f"pct_{label}"] = point.get("pct")
        result[f"amount_{label}"] = point.get("amount")
        move = movement.get(label) or {}
        result[f"money_added_{label}"] = move.get("amount_delta")

    result["features"] = {"market_movement": features}
    return result


class SnapshotHistoryClient:
    """Read-only PostgREST client for Analysis V2 movement history."""

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        read_key: Optional[str] = None,
        *,
        session=None,
        timeout: int = 20,
        page_size: int = 1000,
        max_pages: int = 20,
    ):
        self.url = (
            supabase_url or os.environ.get("SUPABASE_URL", "")
        ).rstrip("/")
        self.key = (
            read_key
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_ANON_KEY", "")
        )
        self.session = session or requests
        self.timeout = timeout
        self.page_size = int(page_size)
        self.max_pages = int(max_pages)
        if not self.url or not self.key:
            raise ValueError(
                "SUPABASE_URL and a read key are required"
            )

    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    def _get(
        self,
        params: Dict[str, Any],
        *,
        range_start: Optional[int] = None,
    ):
        headers = self._headers()
        if range_start is not None:
            headers["Range"] = (
                f"{range_start}-"
                f"{range_start + self.page_size - 1}"
            )
        response = self.session.get(
            f"{self.url}/rest/v1/moneyway_snapshots",
            headers=headers,
            params=params,
            timeout=self.timeout,
        )
        if response.status_code not in (200, 206):
            raise RuntimeError(
                "moneyway_snapshots read failed: "
                f"HTTP {response.status_code} "
                f"{(response.text or '')[:300]}"
            )
        try:
            data = response.json()
        except Exception as exc:
            raise RuntimeError(
                "moneyway_snapshots returned invalid JSON"
            ) from exc
        return data if isinstance(data, list) else []

    def fetch_market_rows(
        self,
        *,
        match_id_hash: str,
        market_key: str,
        selection_code: str,
        as_of: Any,
        anchor_tolerance_minutes: int = 60,
    ) -> List[Dict[str, Any]]:
        """Fetch opening rows plus enough recent history for the 6h anchor."""
        match_hash = validate_match_id_hash(match_id_hash)
        market, selection = _canonical_market_selection(
            market_key, selection_code
        )
        cutoff = _timestamp(as_of)

        base_params = {
            "select": SNAPSHOT_COLUMNS,
            "match_id_hash": f"eq.{match_hash}",
            "market": f"eq.{market}",
            "scraped_at_utc": f"lte.{_iso(cutoff)}",
        }

        opening_selection_params = dict(base_params)
        opening_selection_params["selection"] = f"eq.{selection}"
        opening_selection_params["order"] = "scraped_at_utc.asc,id.asc"
        opening_selection_params["limit"] = "1"
        opening_selection_rows = self._get(
            opening_selection_params
        )

        opening_rows: List[Dict[str, Any]] = []
        if opening_selection_rows:
            opening_at = opening_selection_rows[0].get(
                "scraped_at_utc"
            )
            if opening_at:
                opening_cycle_params = dict(base_params)
                opening_cycle_params["scraped_at_utc"] = (
                    f"eq.{opening_at}"
                )
                opening_cycle_params["order"] = "id.asc"
                opening_cycle_params["limit"] = "25"
                opening_rows = self._get(opening_cycle_params)

        recent_from = (
            cutoff
            - WINDOWS["6h"]
            - timedelta(minutes=anchor_tolerance_minutes)
        )
        recent_params = dict(base_params)
        recent_params.pop("scraped_at_utc", None)
        recent_params["and"] = (
            f"(scraped_at_utc.gte.{_iso(recent_from)},"
            f"scraped_at_utc.lte.{_iso(cutoff)})"
        )
        recent_params["order"] = "scraped_at_utc.asc,id.asc"

        recent_rows: List[Dict[str, Any]] = []
        for page in range(self.max_pages):
            chunk = self._get(
                recent_params,
                range_start=page * self.page_size,
            )
            recent_rows.extend(chunk)
            if len(chunk) < self.page_size:
                break
        else:
            raise RuntimeError(
                "moneyway_snapshots pagination limit reached "
                "for movement query"
            )

        combined = opening_rows + recent_rows
        if not any(
            str(row.get("selection") or "").strip().upper()
            == selection
            for row in combined
        ):
            return []
        return combined

    def fetch_match_rows(
        self,
        *,
        match_id_hash: str,
        as_of: Any,
    ) -> List[Dict[str, Any]]:
        """Fetch all retained snapshot rows for one exact match in one paged read path.

        Runtime V2 uses this to build every directional/structural feature from
        the same immutable snapshot set instead of issuing one HTTP history
        request per selection.
        """
        match_hash = validate_match_id_hash(match_id_hash)
        cutoff = _timestamp(as_of)
        params = {
            "select": SNAPSHOT_COLUMNS,
            "match_id_hash": f"eq.{match_hash}",
            "scraped_at_utc": f"lte.{_iso(cutoff)}",
            "order": "scraped_at_utc.asc,id.asc",
        }
        rows: List[Dict[str, Any]] = []
        for page in range(self.max_pages):
            chunk = self._get(
                params,
                range_start=page * self.page_size,
            )
            rows.extend(chunk)
            if len(chunk) < self.page_size:
                return rows
        raise RuntimeError(
            "moneyway_snapshots pagination limit reached "
            "for exact match runtime query"
        )

    def build_features(
        self,
        *,
        match_id_hash: str,
        market_key: str,
        selection_code: str,
        as_of: Any,
        kickoff_utc: Any = None,
        anchor_tolerance_minutes: int = 60,
        current_tolerance_minutes: int = 60,
    ) -> Dict[str, Any]:
        rows = self.fetch_market_rows(
            match_id_hash=match_id_hash,
            market_key=market_key,
            selection_code=selection_code,
            as_of=as_of,
            anchor_tolerance_minutes=anchor_tolerance_minutes,
        )
        return build_market_movement(
            rows,
            match_id_hash=match_id_hash,
            market_key=market_key,
            selection_code=selection_code,
            as_of=as_of,
            kickoff_utc=kickoff_utc,
            anchor_tolerance_minutes=anchor_tolerance_minutes,
            current_tolerance_minutes=current_tolerance_minutes,
        )
