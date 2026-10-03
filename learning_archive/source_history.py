from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Iterable
from urllib.parse import quote

import requests


DEFAULT_HISTORY_TABLES = (
    "moneyway_1x2_history",
    "moneyway_ou25_history",
    "moneyway_btts_history",
    "dropping_1x2_history",
    "dropping_ou25_history",
    "dropping_btts_history",
    "moneyway_double_chance_history",
    "moneyway_draw_no_bet_history",
)
OPTIONAL_HISTORY_TABLES = {
    "moneyway_double_chance_history",
    "moneyway_draw_no_bet_history",
}


class SXFHistoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class HistoryFetchResult:
    snapshots: list[dict]
    source_tables: tuple[str, ...]
    unavailable_optional_tables: tuple[str, ...]


def configured_history_tables() -> tuple[str, ...]:
    raw = os.environ.get("SMARTXFLOW_LEARNING_HISTORY_TABLES", "").strip()
    if not raw:
        return DEFAULT_HISTORY_TABLES
    values = tuple(item.strip() for item in raw.split(",") if item.strip())
    if not values:
        raise SXFHistoryError("SMARTXFLOW_LEARNING_HISTORY_TABLES is configured but empty")
    return values


def _is_missing_table_response(response: requests.Response) -> bool:
    if response.status_code == 404:
        return True
    try:
        body = response.json()
    except Exception:
        return False
    if not isinstance(body, dict):
        return False
    code = str(body.get("code") or "")
    message = str(body.get("message") or "").lower()
    return code in {"42P01", "PGRST205"} or "could not find the table" in message or "does not exist" in message


def fetch_selected_match_history(
    match_id_hash: str,
    *,
    tables: Iterable[str] | None = None,
    page_size: int = 1000,
    session: requests.Session | None = None,
) -> HistoryFetchResult:
    """Read stored SmartXFlow history for a selected match; never recollect/scrape it."""
    if not isinstance(match_id_hash, str) or not match_id_hash.strip():
        raise SXFHistoryError("match_id_hash is required")
    if page_size < 1 or page_size > 1000:
        raise SXFHistoryError("page_size must be between 1 and 1000")

    base_url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = os.environ.get("SUPABASE_KEY", "").strip()
    if not base_url or not key:
        raise SXFHistoryError("SUPABASE_URL/SUPABASE_KEY are required to read stored SXF history")

    http = session or requests.Session()
    http.headers.update({
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "User-Agent": "smartxflow-learning-archive-history-reader",
    })

    selected_tables = tuple(tables or configured_history_tables())
    all_rows: list[dict] = []
    available: list[str] = []
    unavailable_optional: list[str] = []

    for table in selected_tables:
        offset = 0
        table_rows: list[dict] = []
        while True:
            url = f"{base_url}/rest/v1/{quote(table, safe='')}"
            response = http.get(
                url,
                params={
                    "select": "*",
                    "match_id_hash": f"eq.{match_id_hash.strip()}",
                    "limit": str(page_size),
                    "offset": str(offset),
                },
                timeout=30,
            )
            if response.status_code != 200:
                if table in OPTIONAL_HISTORY_TABLES and _is_missing_table_response(response):
                    unavailable_optional.append(table)
                    table_rows = []
                    break
                raise SXFHistoryError(f"history read failed for {table} ({response.status_code})")
            try:
                page = response.json()
            except ValueError as exc:
                raise SXFHistoryError(f"history read returned invalid JSON for {table}") from exc
            if not isinstance(page, list):
                raise SXFHistoryError(f"history read returned non-array payload for {table}")
            for row in page:
                if not isinstance(row, dict):
                    raise SXFHistoryError(f"history row from {table} is not an object")
                copied = dict(row)
                copied["_archive_source_table"] = table
                table_rows.append(copied)
            if len(page) < page_size:
                break
            offset += page_size

        if table_rows:
            available.append(table)
            all_rows.extend(table_rows)

    if not all_rows:
        raise SXFHistoryError(f"no stored SXF history found for selected match {match_id_hash}")

    all_rows.sort(key=lambda row: (
        str(row.get("scraped_at") or row.get("scraped_at_utc") or row.get("created_at") or ""),
        str(row.get("_archive_source_table") or ""),
    ))
    return HistoryFetchResult(
        snapshots=all_rows,
        source_tables=tuple(available),
        unavailable_optional_tables=tuple(sorted(set(unavailable_optional))),
    )
