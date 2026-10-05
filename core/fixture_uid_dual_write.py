from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Set

import requests

from core.hash_utils import make_match_id_hash

_QUERY_CHUNK = 150

PREMATCH_CURRENT_TABLES: Set[str] = {
    "moneyway_1x2",
    "moneyway_ou25",
    "moneyway_btts",
    "dropping_1x2",
    "dropping_ou25",
    "dropping_btts",
}


def _chunks(values: List[str], size: int = _QUERY_CHUNK):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _row_hash(row: Mapping[str, Any]) -> Optional[str]:
    home = str(row.get("home") or "").strip()
    away = str(row.get("away") or "").strip()
    league = str(row.get("league") or "").strip()
    date = str(row.get("date") or "").strip()
    if not home or not away:
        return None
    return make_match_id_hash(home, away, league, date)


def _writer_cache(writer: Any) -> Dict[str, str]:
    cache = getattr(writer, "_fixture_uid_hash_cache", None)
    if not isinstance(cache, dict):
        cache = {}
        try:
            writer._fixture_uid_hash_cache = cache
        except Exception:
            pass
    return cache


def _schema_cache(writer: Any) -> Dict[str, bool]:
    cache = getattr(writer, "_fixture_uid_column_support", None)
    if not isinstance(cache, dict):
        cache = {}
        try:
            writer._fixture_uid_column_support = cache
        except Exception:
            pass
    return cache


def _table_supports_fixture_uid(writer: Any, table: str, request_get) -> bool:
    cache = _schema_cache(writer)
    if table in cache:
        return bool(cache[table])
    try:
        response = request_get(
            writer._rest_url(table),
            headers=writer._headers(),
            params={"select": "fixture_uid", "limit": 0},
            timeout=10,
        )
        supported = getattr(response, "status_code", 0) == 200
    except Exception:
        supported = False
    cache[table] = supported
    return supported


def resolve_fixture_uids_by_hash(
    writer: Any,
    match_hashes: Iterable[str],
    *,
    request_get=None,
) -> Dict[str, Any]:
    """Resolve current legacy hashes to already-created fixture_uid values.

    This helper is deliberately non-authoritative. It never inserts or updates a
    fixture and never changes match_id_hash behavior. A lookup failure returns an
    error in telemetry and leaves callers free to continue the legacy write path.
    """
    request_get = request_get or requests.get
    wanted = sorted({str(value or "").strip() for value in match_hashes if str(value or "").strip()})
    stats: Dict[str, Any] = {
        "requested_hashes": len(wanted),
        "resolved_hashes": 0,
        "unresolved_hashes": 0,
        "cache_hits": 0,
        "error": None,
        "uid_map": {},
    }
    if not wanted:
        return stats

    cache = _writer_cache(writer)
    uid_map: Dict[str, str] = {}
    missing: List[str] = []
    for match_hash in wanted:
        cached = str(cache.get(match_hash) or "").strip()
        if cached:
            uid_map[match_hash] = cached
            stats["cache_hits"] += 1
        else:
            missing.append(match_hash)

    try:
        for chunk in _chunks(missing):
            response = request_get(
                writer._rest_url("fixtures"),
                headers=writer._headers(),
                params={
                    "select": "match_id_hash,fixture_uid",
                    "match_id_hash": f"in.({','.join(chunk)})",
                },
                timeout=30,
            )
            if getattr(response, "status_code", 0) != 200:
                raise RuntimeError(f"fixtures UID lookup HTTP {getattr(response, 'status_code', 'unknown')}")
            payload = response.json()
            if not isinstance(payload, list):
                raise RuntimeError("fixtures UID lookup returned non-list payload")
            for row in payload:
                match_hash = str(row.get("match_id_hash") or "").strip()
                fixture_uid = str(row.get("fixture_uid") or "").strip()
                if match_hash and fixture_uid:
                    uid_map[match_hash] = fixture_uid
                    cache[match_hash] = fixture_uid
    except Exception as exc:
        stats["error"] = str(exc)[:300]

    stats["uid_map"] = uid_map
    stats["resolved_hashes"] = len(uid_map)
    stats["unresolved_hashes"] = max(0, len(wanted) - len(uid_map))
    return stats


def attach_fixture_uids_to_current_rows(
    writer: Any,
    table: str,
    rows: List[Dict[str, Any]],
    *,
    request_get=None,
) -> Dict[str, Any]:
    """Add fixture_uid to prematch current rows when deterministically resolvable.

    Rows are mutated in place so the same row objects later appended to history
    carry the UID too. Missing/failed UID resolution never blocks the legacy
    current/history path and never removes an existing UID.
    """
    request_get = request_get or requests.get
    stats: Dict[str, Any] = {
        "attempted": False,
        "column_available": False,
        "rows": len(rows),
        "tagged_rows": 0,
        "unresolved_rows": 0,
        "conflicting_existing_uid": 0,
        "requested_hashes": 0,
        "resolved_hashes": 0,
        "cache_hits": 0,
        "error": None,
    }
    if table not in PREMATCH_CURRENT_TABLES or not rows:
        return stats

    stats["attempted"] = True
    if not _table_supports_fixture_uid(writer, table, request_get):
        stats["error"] = "fixture_uid_column_unavailable"
        return stats
    stats["column_available"] = True

    hashes: List[str] = []
    row_hashes: List[Optional[str]] = []
    for row in rows:
        match_hash = _row_hash(row)
        row_hashes.append(match_hash)
        if match_hash:
            hashes.append(match_hash)

    resolved = resolve_fixture_uids_by_hash(writer, hashes, request_get=request_get)
    stats.update(
        requested_hashes=resolved["requested_hashes"],
        resolved_hashes=resolved["resolved_hashes"],
        cache_hits=resolved["cache_hits"],
        error=resolved["error"],
    )
    uid_map = resolved["uid_map"]

    for row, match_hash in zip(rows, row_hashes):
        fixture_uid = uid_map.get(match_hash or "")
        if not fixture_uid:
            stats["unresolved_rows"] += 1
            continue
        existing = str(row.get("fixture_uid") or "").strip()
        if existing and existing != fixture_uid:
            stats["conflicting_existing_uid"] += 1
            continue
        row["fixture_uid"] = fixture_uid
        stats["tagged_rows"] += 1

    return stats
