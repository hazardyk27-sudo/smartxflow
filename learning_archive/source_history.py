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

    This client never connects to Supabase directly. The SmartXFlow backend remains responsible
    for its own database connection and returns the already-stored history for the requested case.
    """
    if not isinstance(match_id_hash, str) or not match_id_hash.strip():
        raise SXFHistoryError("match_id_hash is required")

    base_url, token = _api_config()
    http = session or requests.Session()
    http.headers.update({
        "Accept": "application/json",
        "X-SmartXFlow-Learning-Key": token,
        "User-Agent": "smartxflow-learning-archive-history-reader",
    })

    endpoint = f"{base_url}/api/internal/learning/match/{quote(match_id_hash.strip(), safe='')}/history"
    try:
        response = http.get(endpoint, timeout=30)
    except requests.RequestException as exc:
        raise SXFHistoryError("SmartXFlow history API request failed") from exc

    if response.status_code == 401 or response.status_code == 403:
        raise SXFHistoryError("SmartXFlow history API authentication failed")
    if response.status_code == 404:
        raise SXFHistoryError(f"no stored SXF history found for selected match {match_id_hash}")
    if response.status_code != 200:
        raise SXFHistoryError(f"SmartXFlow history API failed ({response.status_code})")

    try:
        payload = response.json()
    except ValueError as exc:
        raise SXFHistoryError("SmartXFlow history API returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise SXFHistoryError("SmartXFlow history API returned invalid payload")

    returned_hash = str(payload.get("match_id_hash") or "").strip()
    if returned_hash and returned_hash != match_id_hash.strip():
        raise SXFHistoryError("SmartXFlow history API returned a different match_id_hash")

    snapshots = payload.get("snapshots")
    if not isinstance(snapshots, list) or not snapshots:
        raise SXFHistoryError(f"no stored SXF history found for selected match {match_id_hash}")

    normalized: list[dict] = []
    for index, row in enumerate(snapshots):
        if not isinstance(row, dict):
            raise SXFHistoryError(f"SmartXFlow history API snapshot {index} is not an object")
        copied = dict(row)
        row_hash = copied.get("match_id_hash")
        if row_hash not in (None, "", match_id_hash.strip()):
            raise SXFHistoryError(f"SmartXFlow history API snapshot {index} belongs to a different match")
        normalized.append(copied)

    normalized.sort(key=lambda row: (
        str(row.get("scraped_at") or row.get("scraped_at_utc") or row.get("snapshot_at") or row.get("created_at") or ""),
        str(row.get("_archive_source_table") or row.get("source_table") or row.get("market") or ""),
    ))

    source_tables_raw = payload.get("source_tables") or []
    if not isinstance(source_tables_raw, list):
        raise SXFHistoryError("SmartXFlow history API source_tables must be an array")
    source_tables = tuple(str(item) for item in source_tables_raw if str(item).strip())

    unavailable_raw = payload.get("unavailable_optional_tables") or []
    if not isinstance(unavailable_raw, list):
        raise SXFHistoryError("SmartXFlow history API unavailable_optional_tables must be an array")
    unavailable_optional = tuple(sorted({str(item) for item in unavailable_raw if str(item).strip()}))

    return HistoryFetchResult(
        snapshots=normalized,
        source_tables=source_tables,
        unavailable_optional_tables=unavailable_optional,
    )
