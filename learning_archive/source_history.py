from __future__ import annotations

from dataclasses import dataclass
import os
from urllib.parse import quote

import requests


class SXFHistoryError(RuntimeError):
    pass


@dataclass(frozen=True)
class HistoryFetchResult:
    snapshots: list[dict]
    source_tables: tuple[str, ...]
    unavailable_optional_tables: tuple[str, ...]


def _api_config() -> tuple[str, str]:
    base_url = os.environ.get("SMARTXFLOW_LEARNING_API_BASE_URL", "").strip().rstrip("/")
    token = os.environ.get("SMARTXFLOW_LEARNING_API_TOKEN", "").strip()
    if not base_url:
        raise SXFHistoryError("SMARTXFLOW_LEARNING_API_BASE_URL is not configured")
    if not token:
        raise SXFHistoryError("SMARTXFLOW_LEARNING_API_TOKEN is not configured")
    return base_url, token


def fetch_selected_match_history(
    match_id_hash: str,
    *,
    session: requests.Session | None = None,
) -> HistoryFetchResult:
    """Read selected-match stored history through the SmartXFlow backend API.

    The Learning Archive client never connects to Supabase directly. SmartXFlow's backend
    owns the database connection and returns only the already-stored, allow-listed history
    for the requested match.
    """
    match_hash = str(match_id_hash or "").strip().lower()
    if not match_hash:
        raise SXFHistoryError("match_id_hash is required")

    base_url, token = _api_config()
    http = session or requests.Session()
    http.headers.update({
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "smartxflow-learning-archive-history-reader",
    })

    endpoint = (
        f"{base_url}/api/internal/learning-archive/match/"
        f"{quote(match_hash, safe='')}/history"
    )
    try:
        response = http.get(endpoint, timeout=30)
    except requests.RequestException as exc:
        raise SXFHistoryError("SmartXFlow history API request failed") from exc

    if response.status_code in (401, 403):
        raise SXFHistoryError("SmartXFlow history API authentication failed")
    if response.status_code == 404:
        raise SXFHistoryError(f"no stored SXF history found for selected match {match_hash}")
    if response.status_code == 400:
        raise SXFHistoryError("SmartXFlow history API rejected match_id_hash")
    if response.status_code == 503:
        raise SXFHistoryError("SmartXFlow history API is not configured/available")
    if response.status_code != 200:
        raise SXFHistoryError(f"SmartXFlow history API failed ({response.status_code})")

    try:
        payload = response.json()
    except ValueError as exc:
        raise SXFHistoryError("SmartXFlow history API returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise SXFHistoryError("SmartXFlow history API returned invalid payload")

    returned_hash = str(payload.get("match_id_hash") or "").strip().lower()
    if returned_hash and returned_hash != match_hash:
        raise SXFHistoryError("SmartXFlow history API returned a different match_id_hash")

    histories = payload.get("histories")
    if not isinstance(histories, dict):
        raise SXFHistoryError("SmartXFlow history API histories must be an object")

    source_tables_raw = payload.get("source_tables") or []
    if not isinstance(source_tables_raw, list):
        raise SXFHistoryError("SmartXFlow history API source_tables must be an array")
    source_tables = tuple(str(item) for item in source_tables_raw if str(item).strip())

    unavailable_raw = payload.get("unavailable_optional_tables") or []
    if not isinstance(unavailable_raw, list):
        raise SXFHistoryError("SmartXFlow history API unavailable_optional_tables must be an array")
    unavailable_optional = tuple(sorted({str(item) for item in unavailable_raw if str(item).strip()}))

    flattened: list[dict] = []
    for table_name, rows in histories.items():
        if not isinstance(table_name, str) or not table_name.strip():
            raise SXFHistoryError("SmartXFlow history API returned invalid history table name")
        if not isinstance(rows, list):
            raise SXFHistoryError(f"SmartXFlow history API history {table_name} must be an array")
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise SXFHistoryError(
                    f"SmartXFlow history API {table_name}[{index}] is not an object"
                )
            copied = dict(row)
            row_hash = str(copied.get("match_id_hash") or "").strip().lower()
            if row_hash and row_hash != match_hash:
                raise SXFHistoryError(
                    f"SmartXFlow history API {table_name}[{index}] belongs to a different match"
                )
            copied["_archive_source_table"] = table_name
            flattened.append(copied)

    if not flattened:
        raise SXFHistoryError(f"no stored SXF history found for selected match {match_hash}")

    flattened.sort(key=lambda row: (
        str(
            row.get("scraped_at")
            or row.get("scraped_at_utc")
            or row.get("snapshot_at")
            or row.get("created_at")
            or ""
        ),
        str(row.get("_archive_source_table") or ""),
    ))

    return HistoryFetchResult(
        snapshots=flattened,
        source_tables=source_tables,
        unavailable_optional_tables=unavailable_optional,
    )
