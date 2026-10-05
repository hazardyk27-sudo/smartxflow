from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(__file__))
CALC_DIR = os.path.join(ROOT, "desktop", "scraper_standalone")
if CALC_DIR not in sys.path:
    sys.path.insert(0, CALC_DIR)

import alarm_recent_shared as shared


def _rows(count: int, start: datetime):
    rows = []
    for idx in range(count):
        rows.append({
            "match_id_hash": f"m{idx % 40:03d}",
            "market": "1X2",
            "selection": "1",
            "volume": 1000 + idx,
            "share": 50,
            "odds": 2.0,
            "scraped_at_utc": (start + timedelta(seconds=idx)).isoformat().replace("+00:00", "Z"),
        })
    return rows


class _PagedGet:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __call__(self, table, query):
        self.calls.append((table, query))
        if table != "moneyway_snapshots":
            return [{"delegated": True}]
        limit_match = re.search(r"(?:^|&)limit=(\d+)", query)
        offset_match = re.search(r"(?:^|&)offset=(\d+)", query)
        limit = int(limit_match.group(1)) if limit_match else 1000
        offset = int(offset_match.group(1)) if offset_match else 0
        return self.rows[offset:offset + limit]


def test_shared_fetch_pages_once_and_keeps_timestamp_order():
    start = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
    source_rows = _rows(2500, start)
    getter = _PagedGet(source_rows)

    window = shared.fetch_shared_snapshot_window(
        getter,
        start,
        start + timedelta(hours=1),
        page_size=1000,
        max_rows=5000,
    )

    assert window.truncated is False
    assert window.db_pages == 3
    assert len(window.rows) == 2500
    assert len(getter.calls) == 3
    assert window.timestamps == sorted(window.timestamps)


def test_cached_get_serves_contained_time_pages_without_db_call():
    start = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
    source_rows = _rows(2500, start)
    getter = _PagedGet(source_rows)
    window = shared.fetch_shared_snapshot_window(
        getter,
        start,
        start + timedelta(hours=1),
        page_size=1000,
        max_rows=5000,
    )
    calls_before = len(getter.calls)
    cached_get = shared.make_cached_get(window, getter)

    page = cached_get(
        "moneyway_snapshots",
        "select=match_id_hash,market,selection,volume,share,odds,scraped_at_utc"
        "&scraped_at_utc=gte.2026-10-05T10:10:00Z"
        "&scraped_at_utc=lte.2026-10-05T10:30:00Z"
        "&order=scraped_at_utc.asc&limit=1000&offset=0",
    )

    assert page
    assert len(page) <= 1000
    assert len(getter.calls) == calls_before
    assert all(
        datetime.fromisoformat(row["scraped_at_utc"].replace("Z", "+00:00"))
        >= datetime(2026, 10, 5, 10, 10, tzinfo=timezone.utc)
        for row in page
    )


def test_cached_get_honors_offset_inside_filtered_range():
    start = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
    source_rows = _rows(1200, start)
    getter = _PagedGet(source_rows)
    window = shared.fetch_shared_snapshot_window(
        getter,
        start,
        start + timedelta(hours=1),
        page_size=1000,
        max_rows=5000,
    )
    cached_get = shared.make_cached_get(window, getter)

    query_base = (
        "select=match_id_hash,market,selection,volume,share,odds,scraped_at_utc"
        "&scraped_at_utc=gte.2026-10-05T10:00:00Z"
        "&scraped_at_utc=lte.2026-10-05T10:20:00Z"
        "&order=scraped_at_utc.asc&limit=100"
    )
    first = cached_get("moneyway_snapshots", query_base + "&offset=0")
    second = cached_get("moneyway_snapshots", query_base + "&offset=100")

    assert len(first) == 100
    assert len(second) == 100
    assert first[-1]["scraped_at_utc"] < second[0]["scraped_at_utc"]


def test_non_window_snapshot_query_delegates_to_original_get():
    start = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
    getter = _PagedGet(_rows(10, start))
    window = shared.fetch_shared_snapshot_window(
        getter,
        start,
        start + timedelta(hours=1),
        page_size=1000,
        max_rows=5000,
    )
    calls_before = len(getter.calls)
    cached_get = shared.make_cached_get(window, getter)

    result = cached_get(
        "moneyway_snapshots",
        "select=match_id_hash,market,selection,odds,scraped_at_utc"
        "&match_id_hash=in.(abc)&odds=gt.0&order=scraped_at_utc.asc&limit=2000",
    )

    assert len(getter.calls) == calls_before + 1
    assert isinstance(result, list)


def test_window_outside_shared_bounds_delegates_to_original_get():
    start = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
    getter = _PagedGet(_rows(10, start))
    window = shared.fetch_shared_snapshot_window(
        getter,
        start,
        start + timedelta(hours=1),
        page_size=1000,
        max_rows=5000,
    )
    calls_before = len(getter.calls)
    cached_get = shared.make_cached_get(window, getter)

    cached_get(
        "moneyway_snapshots",
        "select=match_id_hash,market,selection,volume,share,odds,scraped_at_utc"
        "&scraped_at_utc=gte.2026-10-05T09:59:00Z"
        "&scraped_at_utc=lte.2026-10-05T10:30:00Z"
        "&order=scraped_at_utc.asc&limit=1000&offset=0",
    )

    assert len(getter.calls) == calls_before + 1


def test_shared_fetch_marks_exact_hard_cap_as_truncated():
    start = datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc)
    getter = _PagedGet(_rows(2000, start))

    window = shared.fetch_shared_snapshot_window(
        getter,
        start,
        start + timedelta(hours=1),
        page_size=1000,
        max_rows=2000,
    )

    assert window.truncated is True
    assert len(window.rows) == 2000
    assert window.db_pages == 2
