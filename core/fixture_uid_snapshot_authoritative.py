from __future__ import annotations

from typing import Any, Dict, List, Mapping

import requests

_QUERY_CHUNK = 150
_TRANSIENT_EVENT_KEY = "_fixture_source_event_id"


def _chunks(values: List[str], size: int = _QUERY_CHUNK):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def attach_provider_fixture_uids_to_snapshots(
    writer: Any,
    snapshots: List[Dict[str, Any]],
    *,
    request_get=None,
) -> Dict[str, Any]:
    """Attach snapshot fixture_uid from Betwatch provider identity.

    Snapshot payloads carry ``_fixture_source_event_id`` only in memory. The
    transient key is always removed before the rows are returned to the caller so
    it can never leak into the Supabase insert payload.

    This helper is intended for UID-authoritative mode only. It fails closed when
    a provider event cannot be resolved or one provider event resolves to more
    than one UID. Callers must abort the scrape on ``error`` rather than falling
    back to legacy-hash snapshot identity.
    """
    request_get = request_get or requests.get
    stats: Dict[str, Any] = {
        "rows": len(snapshots or []),
        "provider_events": 0,
        "resolved_events": 0,
        "tagged_rows": 0,
        "unresolved_rows": 0,
        "error": None,
    }
    if not snapshots:
        return stats

    event_ids = sorted(
        {
            str(row.get(_TRANSIENT_EVENT_KEY) or "").strip()
            for row in snapshots
            if str(row.get(_TRANSIENT_EVENT_KEY) or "").strip()
        }
    )
    stats["provider_events"] = len(event_ids)

    uid_by_event: Dict[str, str] = {}
    duplicate_events: set[str] = set()

    try:
        for chunk in _chunks(event_ids):
            response = request_get(
                writer._rest_url("fixture_source_ids"),
                headers=writer._headers(),
                params={
                    "select": "source_event_id,fixture_uid",
                    "source": "eq.betwatch",
                    "source_event_id": f"in.({','.join(chunk)})",
                },
                timeout=30,
            )
            if getattr(response, "status_code", 0) != 200:
                raise RuntimeError(
                    f"fixture_source_ids snapshot lookup HTTP {getattr(response, 'status_code', 'unknown')}"
                )
            payload = response.json()
            if not isinstance(payload, list):
                raise RuntimeError("fixture_source_ids snapshot lookup returned non-list payload")
            for row in payload:
                if not isinstance(row, Mapping):
                    continue
                event_id = str(row.get("source_event_id") or "").strip()
                fixture_uid = str(row.get("fixture_uid") or "").strip()
                if not event_id or not fixture_uid:
                    continue
                existing = uid_by_event.get(event_id)
                if existing and existing != fixture_uid:
                    duplicate_events.add(event_id)
                    continue
                uid_by_event[event_id] = fixture_uid
    except Exception as exc:
        stats["error"] = str(exc)[:300]

    stats["resolved_events"] = len(uid_by_event)
    if duplicate_events and not stats["error"]:
        stats["error"] = "snapshot_provider_event_maps_to_multiple_uids"

    try:
        for row in snapshots:
            event_id = str(row.pop(_TRANSIENT_EVENT_KEY, "") or "").strip()
            fixture_uid = uid_by_event.get(event_id)
            if not event_id or not fixture_uid or event_id in duplicate_events:
                stats["unresolved_rows"] += 1
                continue
            existing_uid = str(row.get("fixture_uid") or "").strip()
            if existing_uid and existing_uid != fixture_uid:
                stats["unresolved_rows"] += 1
                if not stats["error"]:
                    stats["error"] = "snapshot_existing_uid_conflict"
                continue
            row["fixture_uid"] = fixture_uid
            stats["tagged_rows"] += 1
    finally:
        # Defensive cleanup even if a malformed row raises unexpectedly.
        for row in snapshots:
            row.pop(_TRANSIENT_EVENT_KEY, None)

    if stats["unresolved_rows"] and not stats["error"]:
        stats["error"] = "snapshot_provider_identity_unresolved"
    return stats
