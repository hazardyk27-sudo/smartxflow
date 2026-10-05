from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import requests

from core.fixture_identity_v2 import BETWATCH_SOURCE
from core.hash_utils import make_match_id_hash

_QUERY_CHUNK = 150
PhysicalKey = Tuple[str, str, str, str]


def _chunks(values: List[str], size: int = _QUERY_CHUNK):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _normalize_instant(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return raw
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat(timespec="seconds")


def _row_hash(row: Mapping[str, Any]) -> Optional[str]:
    home = str(row.get("home") or "").strip()
    away = str(row.get("away") or "").strip()
    league = str(row.get("league") or "").strip()
    date = str(row.get("date") or "").strip()
    if not home or not away:
        return None
    return make_match_id_hash(home, away, league, date)


def _row_physical(row: Mapping[str, Any]) -> PhysicalKey:
    return (
        str(row.get("league") or "").strip(),
        str(row.get("home") or "").strip(),
        str(row.get("away") or "").strip(),
        _normalize_instant(row.get("date")),
    )


def _context_physical(value: Any) -> Optional[PhysicalKey]:
    if not isinstance(value, (tuple, list)) or len(value) != 4:
        return None
    return (
        str(value[0] or "").strip(),
        str(value[1] or "").strip(),
        str(value[2] or "").strip(),
        _normalize_instant(value[3]),
    )


def _fixture_matches(row: Mapping[str, Any], fixture: Mapping[str, Any], match_hash: str) -> bool:
    return (
        str(fixture.get("match_id_hash") or "").strip() == match_hash
        and str(fixture.get("league") or "").strip() == str(row.get("league") or "").strip()[:150]
        and str(fixture.get("home_team") or "").strip() == str(row.get("home") or "").strip()[:100]
        and str(fixture.get("away_team") or "").strip() == str(row.get("away") or "").strip()[:100]
        and _normalize_instant(fixture.get("kickoff_utc")) == _normalize_instant(row.get("date"))
    )


def _read_event_uid_map(writer: Any, event_ids: Iterable[str], request_get) -> Dict[str, str]:
    wanted = sorted({str(value or "").strip() for value in event_ids if str(value or "").strip()})
    result: Dict[str, str] = {}
    for chunk in _chunks(wanted):
        response = request_get(
            writer._rest_url("fixture_source_ids"),
            headers=writer._headers(),
            params={
                "select": "source_event_id,fixture_uid",
                "source": f"eq.{BETWATCH_SOURCE}",
                "source_event_id": f"in.({','.join(chunk)})",
            },
            timeout=30,
        )
        if getattr(response, "status_code", 0) != 200:
            raise RuntimeError(f"fixture source lookup HTTP {getattr(response, 'status_code', 'unknown')}")
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("fixture source lookup returned non-list payload")
        for item in payload:
            event_id = str(item.get("source_event_id") or "").strip()
            fixture_uid = str(item.get("fixture_uid") or "").strip()
            if event_id and fixture_uid:
                result[event_id] = fixture_uid
    return result


def _read_fixture_map(writer: Any, fixture_uids: Iterable[str], request_get) -> Dict[str, Dict[str, Any]]:
    wanted = sorted({str(value or "").strip() for value in fixture_uids if str(value or "").strip()})
    result: Dict[str, Dict[str, Any]] = {}
    for chunk in _chunks(wanted):
        response = request_get(
            writer._rest_url("fixtures"),
            headers=writer._headers(),
            params={
                "select": "fixture_uid,match_id_hash,league,home_team,away_team,kickoff_utc",
                "fixture_uid": f"in.({','.join(chunk)})",
            },
            timeout=30,
        )
        if getattr(response, "status_code", 0) != 200:
            raise RuntimeError(f"fixture identity lookup HTTP {getattr(response, 'status_code', 'unknown')}")
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("fixture identity lookup returned non-list payload")
        for item in payload:
            fixture_uid = str(item.get("fixture_uid") or "").strip()
            if fixture_uid:
                result[fixture_uid] = dict(item)
    return result


def attach_provider_verified_fixture_uids(
    writer: Any,
    rows: List[Dict[str, Any]],
    *,
    request_get=None,
) -> Dict[str, Any]:
    """Best-effort Part 4 dual-write with provider + physical proof.

    A row is tagged only if the current staged Betwatch event, immutable registry
    mapping, payload physical key, and fixture row all agree. Any uncertainty
    leaves the legacy row untouched.
    """
    request_get = request_get or requests.get
    stats: Dict[str, Any] = {
        "rows": len(rows),
        "tagged_rows": 0,
        "unresolved_rows": 0,
        "identity_mismatch_rows": 0,
        "conflicting_existing_uid": 0,
        "provider_context_hashes": 0,
        "resolved_hashes": 0,
        "error": None,
    }
    if not rows:
        return stats

    event_by_hash = getattr(writer, "_fixture_identity_event_by_hash", None)
    physical_by_hash = getattr(writer, "_fixture_identity_physical_by_hash", None)
    if not isinstance(event_by_hash, dict) or not isinstance(physical_by_hash, dict):
        stats["unresolved_rows"] = len(rows)
        stats["error"] = "provider_identity_context_unavailable"
        return stats

    row_hashes = [_row_hash(row) for row in rows]
    wanted_hashes = sorted({value for value in row_hashes if value})
    stats["provider_context_hashes"] = sum(1 for value in wanted_hashes if value in event_by_hash)

    try:
        event_ids = [event_by_hash[value] for value in wanted_hashes if value in event_by_hash]
        event_uid = _read_event_uid_map(writer, event_ids, request_get)
        fixture_map = _read_fixture_map(writer, event_uid.values(), request_get)
    except Exception as exc:
        stats["unresolved_rows"] = len(rows)
        stats["error"] = str(exc)[:300]
        return stats

    verified: Dict[str, str] = {}
    for row, match_hash in zip(rows, row_hashes):
        if not match_hash:
            continue
        event_id = str(event_by_hash.get(match_hash) or "").strip()
        context = _context_physical(physical_by_hash.get(match_hash))
        if not event_id or context is None:
            continue
        if context != _row_physical(row):
            stats["identity_mismatch_rows"] += 1
            continue
        fixture_uid = str(event_uid.get(event_id) or "").strip()
        fixture = fixture_map.get(fixture_uid)
        if not fixture_uid or not fixture or not _fixture_matches(row, fixture, match_hash):
            stats["identity_mismatch_rows"] += 1
            continue
        verified[match_hash] = fixture_uid

    stats["resolved_hashes"] = len(verified)
    for row, match_hash in zip(rows, row_hashes):
        fixture_uid = verified.get(match_hash or "")
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
