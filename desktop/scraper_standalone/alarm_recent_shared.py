from __future__ import annotations

import bisect
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


_SELECT = "match_id_hash,market,selection,volume,share,odds,scraped_at_utc"
_GTE_RE = re.compile(r"(?:^|&)scraped_at_utc=gte\.([^&]+)")
_LTE_RE = re.compile(r"(?:^|&)scraped_at_utc=lte\.([^&]+)")
_LIMIT_RE = re.compile(r"(?:^|&)limit=(\d+)")
_OFFSET_RE = re.compile(r"(?:^|&)offset=(\d+)")


def _dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class SharedSnapshotWindow:
    rows: List[Dict[str, Any]]
    timestamps: List[datetime]
    start_dt: datetime
    end_dt: datetime
    page_size: int
    max_rows: int
    truncated: bool = False
    db_pages: int = 0
    invalid_timestamp_rows: int = 0

    def can_serve(self, query: str) -> bool:
        if "scraped_at_utc=gte." not in query or "scraped_at_utc=lte." not in query:
            return False
        start_match = _GTE_RE.search(query)
        end_match = _LTE_RE.search(query)
        if not start_match or not end_match:
            return False
        start = _dt(start_match.group(1))
        end = _dt(end_match.group(1))
        if start is None or end is None:
            return False
        return start >= self.start_dt and end <= self.end_dt

    def page(self, query: str) -> Optional[List[Dict[str, Any]]]:
        if not self.can_serve(query):
            return None
        start_match = _GTE_RE.search(query)
        end_match = _LTE_RE.search(query)
        start = _dt(start_match.group(1)) if start_match else None
        end = _dt(end_match.group(1)) if end_match else None
        if start is None or end is None:
            return None

        left = bisect.bisect_left(self.timestamps, start)
        right = bisect.bisect_right(self.timestamps, end)
        offset_match = _OFFSET_RE.search(query)
        limit_match = _LIMIT_RE.search(query)
        offset = int(offset_match.group(1)) if offset_match else 0
        limit = int(limit_match.group(1)) if limit_match else self.page_size
        start_idx = min(right, left + max(0, offset))
        end_idx = min(right, start_idx + max(0, limit))
        return self.rows[start_idx:end_idx]


def fetch_shared_snapshot_window(
    original_get: Callable[[str, str], Any],
    start_dt: datetime,
    end_dt: datetime,
    *,
    page_size: int,
    max_rows: int,
    logger: Optional[Callable[[str], None]] = None,
) -> SharedSnapshotWindow:
    """Fetch one superset snapshot window for all incremental alarm motors.

    The caller may later intercept the individual motor queries and serve every
    contained time-range page from this in-memory, timestamp-sorted superset.
    Queries that are not a contained time-range query remain delegated to the
    original calculator client (fixtures, alarm tables, immutable opening odds,
    settings, etc.).
    """
    start_dt = start_dt.astimezone(timezone.utc)
    end_dt = end_dt.astimezone(timezone.utc)
    rows: List[Dict[str, Any]] = []
    offset = 0
    db_pages = 0

    while offset < max_rows:
        query = (
            f"select={_SELECT}"
            f"&scraped_at_utc=gte.{_iso_z(start_dt)}"
            f"&scraped_at_utc=lte.{_iso_z(end_dt)}"
            "&order=scraped_at_utc.asc"
            f"&limit={int(page_size)}&offset={int(offset)}"
        )
        page = original_get("moneyway_snapshots", query) or []
        if not isinstance(page, list):
            raise RuntimeError("shared snapshot fetch returned non-list response")
        db_pages += 1
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size

    truncated = len(rows) >= max_rows
    valid = []
    invalid_timestamp_rows = 0
    for row in rows:
        ts = _dt(row.get("scraped_at_utc"))
        if ts is None:
            invalid_timestamp_rows += 1
            continue
        valid.append((ts, row))
    valid.sort(key=lambda item: item[0])

    window = SharedSnapshotWindow(
        rows=[row for _, row in valid],
        timestamps=[ts for ts, _ in valid],
        start_dt=start_dt,
        end_dt=end_dt,
        page_size=page_size,
        max_rows=max_rows,
        truncated=truncated,
        db_pages=db_pages,
        invalid_timestamp_rows=invalid_timestamp_rows,
    )
    if logger:
        logger(
            f"[SharedAlarmWindow] rows={len(window.rows)} pages={db_pages} "
            f"invalid_ts={invalid_timestamp_rows} truncated={truncated} "
            f"window={_iso_z(start_dt)}..{_iso_z(end_dt)}"
        )
    return window


def make_cached_get(
    window: SharedSnapshotWindow,
    original_get: Callable[[str, str], Any],
) -> Callable[[str, str], Any]:
    """Return a calculator._get compatible cache interceptor."""

    def cached_get(table: str, query: str):
        if table == "moneyway_snapshots":
            page = window.page(query)
            if page is not None:
                return page
        return original_get(table, query)

    return cached_get
