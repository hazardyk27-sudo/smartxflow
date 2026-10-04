#!/usr/bin/env python3
"""Keep only the most recent seven days in SmartXFlow analysis signal tables.

This maintenance is intentionally scoped to the five Analysis/Sinyal Engine tables.
It never touches raw market history, learning archives, alarm tables, users, or fixtures.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import requests

TABLES = (
    "underdog_signals",
    "confirmed_money_signals",
    "confirmed_money_v2_signals",
    "fake_sharp_signals",
    "early_money_lock_signals",
)

RETENTION_DAYS = int(os.environ.get("SIGNAL_RETENTION_DAYS", "7"))
TIMEOUT = 30


def _required_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def _count_rows(base_url: str, headers: dict[str, str], table: str, cutoff: str | None = None) -> int:
    params = {"select": "id"}
    if cutoff:
        params["created_at"] = f"lt.{cutoff}"
    count_headers = dict(headers)
    count_headers["Prefer"] = "count=exact"
    count_headers["Range"] = "0-0"
    response = requests.get(
        f"{base_url}/rest/v1/{table}",
        headers=count_headers,
        params=params,
        timeout=TIMEOUT,
    )
    if response.status_code not in (200, 206):
        raise RuntimeError(f"{table} count failed: HTTP {response.status_code} {response.text[:200]}")
    content_range = response.headers.get("Content-Range", "")
    if "/" not in content_range:
        raise RuntimeError(f"{table} count missing Content-Range: {content_range!r}")
    total = content_range.rsplit("/", 1)[-1]
    if total == "*":
        raise RuntimeError(f"{table} count was not exact")
    return int(total)


def _oldest_created_at(base_url: str, headers: dict[str, str], table: str) -> str | None:
    response = requests.get(
        f"{base_url}/rest/v1/{table}",
        headers=headers,
        params={"select": "created_at", "order": "created_at.asc", "limit": "1"},
        timeout=TIMEOUT,
    )
    if response.status_code not in (200, 206):
        raise RuntimeError(f"{table} oldest-row check failed: HTTP {response.status_code} {response.text[:200]}")
    rows = response.json()
    return rows[0].get("created_at") if rows else None


def _delete_stale(base_url: str, headers: dict[str, str], table: str, cutoff: str) -> None:
    delete_headers = dict(headers)
    delete_headers["Prefer"] = "return=minimal"
    response = requests.delete(
        f"{base_url}/rest/v1/{table}",
        headers=delete_headers,
        params={"created_at": f"lt.{cutoff}"},
        timeout=TIMEOUT,
    )
    if response.status_code not in (200, 204):
        raise RuntimeError(f"{table} delete failed: HTTP {response.status_code} {response.text[:200]}")


def main() -> int:
    if RETENTION_DAYS != 7:
        raise RuntimeError("SmartXFlow signal retention is fixed at 7 days; refusing a different value")

    base_url = _required_env("SUPABASE_URL").rstrip("/")
    service_key = _required_env("SUPABASE_SERVICE_ROLE_KEY")
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }

    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=RETENTION_DAYS)).isoformat().replace("+00:00", "Z")
    print(f"SIGNAL_RETENTION cutoff={cutoff} days={RETENTION_DAYS}")

    failed = False
    for table in TABLES:
        try:
            before = _count_rows(base_url, headers, table)
            stale_before = _count_rows(base_url, headers, table, cutoff)
            if stale_before:
                _delete_stale(base_url, headers, table, cutoff)
            stale_after = _count_rows(base_url, headers, table, cutoff)
            after = _count_rows(base_url, headers, table)
            oldest_kept = _oldest_created_at(base_url, headers, table)
            deleted = before - after
            ok = stale_after == 0 and deleted == stale_before
            print(
                "RETENTION_RESULT "
                f"table={table} before={before} stale_before={stale_before} "
                f"deleted={deleted} after={after} stale_after={stale_after} "
                f"oldest_kept={oldest_kept or '-'} status={'ok' if ok else 'mismatch'}"
            )
            if not ok:
                failed = True
        except Exception as exc:
            failed = True
            print(f"RETENTION_ERROR table={table} error={exc}", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
