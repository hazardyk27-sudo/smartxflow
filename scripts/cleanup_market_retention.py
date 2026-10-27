#!/usr/bin/env python3
"""Keep SmartXFlow operational market data within a seven-day rolling window.

This explicit allowlist covers market snapshots/history, current market rows,
fixtures, Polymarket feed rows, and operational signal/alarm logs. It never
queries or deletes Learning Archive, SXF research archive, or PRATIK files.
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, time as day_time, timedelta, timezone
from typing import Iterable

import requests


@dataclass(frozen=True)
class Table:
    name: str
    column: str
    kind: str = "timestamp"  # timestamp, text_timestamp, or date
    optional: bool = False


TABLES = (
    Table("moneyway_snapshots", "scraped_at_utc"),
    Table("dropping_odds_snapshots", "scraped_at_utc", optional=True),
    Table("live_snapshots", "snapshot_at"),
    Table("polymarket_price_snapshots", "created_at"),
    Table("polymarket_trades", "scraped_at"),
    Table("moneyway_1x2_history", "scraped_at", "text_timestamp"),
    Table("moneyway_ou25_history", "scraped_at", "text_timestamp"),
    Table("moneyway_btts_history", "scraped_at", "text_timestamp"),
    Table("dropping_1x2_history", "scraped_at", "text_timestamp"),
    Table("dropping_ou25_history", "scraped_at", "text_timestamp"),
    Table("dropping_btts_history", "scraped_at", "text_timestamp"),
    Table("matchbook_1x2_history", "scraped_at"),
    Table("matchbook_ou25_history", "scraped_at"),
    Table("matchbook_btts_history", "scraped_at"),
    Table("moneyway_1x2", "date", "text_timestamp"),
    Table("moneyway_ou25", "date", "text_timestamp"),
    Table("moneyway_btts", "date", "text_timestamp"),
    Table("dropping_1x2", "date", "text_timestamp"),
    Table("dropping_ou25", "date", "text_timestamp"),
    Table("dropping_btts", "date", "text_timestamp"),
    Table("fixtures", "fixture_date", "date"),
    Table("live_fixtures", "fixture_date", "text_timestamp"),
    Table("scraper_signal", "created_at"),
    Table("telegram_sent_log", "last_sent_at"),
)

RETENTION_DAYS = int(os.environ.get("MARKET_RETENTION_DAYS", "7"))
TIMEOUT = 60
RETRIES = 3


def _required_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def _headers(service_key: str) -> dict[str, str]:
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }


def _request(method: str, url: str, headers: dict[str, str], params: Iterable[tuple[str, str]]):
    last_error = None
    for attempt in range(RETRIES):
        try:
            response = requests.request(method, url, headers=headers, params=list(params), timeout=TIMEOUT)
            if response.status_code not in (408, 429, 500, 502, 503, 504):
                return response
            last_error = RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")
        except requests.RequestException as exc:
            last_error = exc
        if attempt + 1 < RETRIES:
            time.sleep(2 ** attempt)
    raise RuntimeError(str(last_error))


def _count(base_url: str, headers: dict[str, str], table: Table, cutoff: str | None = None) -> int:
    params = [("select", "id")]
    if cutoff:
        params.append((table.column, f"lt.{cutoff}"))
    count_headers = dict(headers)
    count_headers["Prefer"] = "count=exact"
    count_headers["Range"] = "0-0"
    response = _request("GET", f"{base_url}/rest/v1/{table.name}", count_headers, params)
    if response.status_code == 404 and table.optional:
        return -1
    if response.status_code not in (200, 206):
        raise RuntimeError(f"{table.name} count failed: HTTP {response.status_code} {response.text[:200]}")
    content_range = response.headers.get("Content-Range", "")
    if "/" not in content_range or content_range.rsplit("/", 1)[-1] == "*":
        raise RuntimeError(f"{table.name} exact count missing: {content_range!r}")
    return int(content_range.rsplit("/", 1)[-1])


def _oldest(base_url: str, headers: dict[str, str], table: Table) -> str | None:
    response = _request(
        "GET",
        f"{base_url}/rest/v1/{table.name}",
        headers,
        [("select", table.column), ("order", f"{table.column}.asc"), ("limit", "1")],
    )
    if response.status_code == 404 and table.optional:
        return None
    if response.status_code not in (200, 206):
        raise RuntimeError(f"{table.name} oldest-row check failed: HTTP {response.status_code} {response.text[:200]}")
    rows = response.json()
    return rows[0].get(table.column) if rows else None


def _delete(base_url: str, headers: dict[str, str], table: Table, cutoff: str) -> None:
    delete_headers = dict(headers)
    delete_headers["Prefer"] = "return=minimal"
    response = _request(
        "DELETE",
        f"{base_url}/rest/v1/{table.name}",
        delete_headers,
        [(table.column, f"lt.{cutoff}")],
    )
    if response.status_code == 404 and table.optional:
        return
    if response.status_code not in (200, 204):
        raise RuntimeError(f"{table.name} delete failed: HTTP {response.status_code} {response.text[:200]}")


def _as_day(value: str, kind: str) -> date:
    if kind == "date":
        return date.fromisoformat(value[:10])
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if kind == "text_timestamp":
        # Historical text timestamps use ISO format; day-level lexical chunks
        # preserve the project's documented +03:00 ordering behavior.
        return date.fromisoformat(value[:10])
    return parsed.astimezone(timezone.utc).date()


def _day_bounds(day: date, kind: str) -> tuple[str, str]:
    following = day + timedelta(days=1)
    if kind == "timestamp":
        start = datetime.combine(day, day_time.min, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        end = datetime.combine(following, day_time.min, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        return start, end
    return day.isoformat(), following.isoformat()


def _fallback_by_day(base_url: str, headers: dict[str, str], table: Table, cutoff: str, cutoff_day: date) -> None:
    """Recover a timed-out backlog from the table's actual oldest saved day."""
    oldest = _oldest(base_url, headers, table)
    if oldest is None:
        return
    day = _as_day(oldest, table.kind)
    while day < cutoff_day:
        start, end = _day_bounds(day, table.kind)
        delete_headers = dict(headers)
        delete_headers["Prefer"] = "return=minimal"
        response = _request(
            "DELETE",
            f"{base_url}/rest/v1/{table.name}",
            delete_headers,
            [(table.column, f"gte.{start}"), (table.column, f"lt.{end}")],
        )
        if response.status_code not in (200, 204):
            raise RuntimeError(f"{table.name} day chunk {day} failed: HTTP {response.status_code} {response.text[:200]}")
        print(f"RETENTION_CHUNK table={table.name} day={day} status=ok")
        day += timedelta(days=1)
    # Keep the exact rolling cutoff for the final partial day.
    _delete(base_url, headers, table, cutoff)


def main() -> int:
    if RETENTION_DAYS != 7:
        raise RuntimeError("market-data retention is fixed at 7 days; refusing a different value")

    base_url = _required_env("SUPABASE_URL").rstrip("/")
    service_key = _required_env("SUPABASE_SERVICE_ROLE_KEY")
    headers = _headers(service_key)
    now = datetime.now(timezone.utc)
    timestamp_cutoff = (now - timedelta(days=RETENTION_DAYS)).isoformat().replace("+00:00", "Z")
    date_cutoff = (now - timedelta(days=RETENTION_DAYS)).date().isoformat()
    cutoff_day = date.fromisoformat(date_cutoff)
    print(f"MARKET_RETENTION timestamp_cutoff={timestamp_cutoff} date_cutoff={date_cutoff} days={RETENTION_DAYS}")

    failed = False
    for table in TABLES:
        cutoff = date_cutoff if table.kind == "date" else timestamp_cutoff
        try:
            before = _count(base_url, headers, table)
            if before == -1:
                print(f"RETENTION_RESULT table={table.name} status=optional_missing")
                continue
            stale_before = _count(base_url, headers, table, cutoff)
            if stale_before:
                try:
                    _delete(base_url, headers, table, cutoff)
                except Exception:
                    _fallback_by_day(base_url, headers, table, cutoff, cutoff_day)
            stale_after = _count(base_url, headers, table, cutoff)
            after = _count(base_url, headers, table)
            deleted = before - after
            ok = stale_after == 0 and deleted == stale_before
            print(
                "RETENTION_RESULT "
                f"table={table.name} before={before} stale_before={stale_before} "
                f"deleted={deleted} after={after} stale_after={stale_after} "
                f"status={'ok' if ok else 'incomplete_or_protected'}"
            )
            if not ok:
                failed = True
        except Exception as exc:
            failed = True
            print(f"RETENTION_ERROR table={table.name} error={exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
