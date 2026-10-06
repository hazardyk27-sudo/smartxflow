from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

import requests

from core.fixture_identity_payload_stage import clear_betwatch_authoritative_payload
from core.fixture_identity_shadow import clear_betwatch_identity_stage
from core.fixture_identity_v2 import extract_betwatch_identity
from core.hash_utils import make_match_id_hash


def _text(value: Any) -> str:
    return str(value or "").strip()


def _kickoff(value: Any) -> str:
    raw = _text(value)
    if raw.endswith("Z"):
        return raw[:-1] + "+00:00"
    return raw


def build_betwatch_fixture_rpc_rows(
    matches: Sequence[Mapping[str, Any]],
) -> Tuple[list[Dict[str, Any]], Dict[str, Any]]:
    """Build one provider-authoritative fixture row per Betwatch event.

    The builder is deliberately fail-closed. A provider event may not describe
    two physical fixtures in one payload, while two different events are allowed
    to share the same legacy matchup hash (the rematch case Identity V2 exists to
    support).
    """
    stats: Dict[str, Any] = {
        "payload_rows": len(matches or []),
        "rpc_rows": 0,
        "missing_provider_ids": 0,
        "incomplete_identity_rows": 0,
        "provider_event_collision_groups": 0,
        "physical_event_collision_groups": 0,
        "error": None,
    }

    by_event: Dict[str, Dict[str, Any]] = {}
    event_physical: Dict[str, set[tuple[str, str, str, str]]] = {}
    physical_events: Dict[tuple[str, str, str, str], set[str]] = {}

    for match in matches or []:
        identity = extract_betwatch_identity(match)
        if identity is None:
            stats["missing_provider_ids"] += 1
            continue

        teams = match.get("teams") or {}
        home = _text(teams.get("v1")) if isinstance(teams, Mapping) else ""
        away = _text(teams.get("v2")) if isinstance(teams, Mapping) else ""
        league = _text(match.get("league"))
        kickoff = _kickoff(match.get("kickoff"))
        event_id = _text(identity.event_id)

        if not event_id or not home or not away or not league or not kickoff:
            stats["incomplete_identity_rows"] += 1
            continue

        match_hash = make_match_id_hash(home, away, league, kickoff)
        physical = (league, home, away, kickoff)
        row = {
            "source_event_id": event_id,
            "match_id_hash": match_hash,
            "home_team": home[:100],
            "away_team": away[:100],
            "league": league[:150],
            "kickoff_utc": kickoff,
        }
        event_physical.setdefault(event_id, set()).add(physical)
        physical_events.setdefault(physical, set()).add(event_id)
        by_event.setdefault(event_id, row)

    stats["provider_event_collision_groups"] = sum(
        1 for values in event_physical.values() if len(values) > 1
    )
    stats["physical_event_collision_groups"] = sum(
        1 for values in physical_events.values() if len(values) > 1
    )

    if stats["missing_provider_ids"]:
        stats["error"] = "missing_provider_id"
        return [], stats
    if stats["incomplete_identity_rows"]:
        stats["error"] = "incomplete_physical_identity"
        return [], stats
    if stats["provider_event_collision_groups"]:
        stats["error"] = "provider_event_collision"
        return [], stats
    if stats["physical_event_collision_groups"]:
        stats["error"] = "physical_event_collision"
        return [], stats

    rows = [by_event[event_id] for event_id in sorted(by_event)]
    stats["rpc_rows"] = len(rows)
    return rows, stats


def _install_physical_provider_context(
    writer: Any,
    matches: Sequence[Mapping[str, Any]],
) -> None:
    """Expose exact physical -> provider-event context to current-table UID tagging."""
    context: Dict[tuple[str, str, str, str], str] = {}
    for match in matches or []:
        identity = extract_betwatch_identity(match)
        teams = match.get("teams") or {}
        if identity is None or not isinstance(teams, Mapping):
            continue
        physical = (
            _text(match.get("league")),
            _text(teams.get("v1")),
            _text(teams.get("v2")),
            _kickoff(match.get("kickoff")),
        )
        event_id = _text(identity.event_id)
        if all(physical) and event_id:
            context[physical] = event_id
    try:
        writer._fixture_identity_event_by_physical = context
        writer._fixture_identity_authoritative_active = True
        writer._fixture_identity_authoritative_failed = False
    except Exception:
        pass


def _runtime_service_headers() -> Optional[Dict[str, str]]:
    key = _text(os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))
    if not key:
        return None
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def write_provider_authoritative_fixture_batch(
    writer: Any,
    matches: Sequence[Mapping[str, Any]],
    *,
    observed_at: Optional[str] = None,
    request_post=None,
) -> Dict[str, Any]:
    """Call the transactional provider-authoritative fixture RPC once.

    Runtime calls require ``SUPABASE_SERVICE_ROLE_KEY`` because the RPC is not
    executable by anon/authenticated roles. Tests may inject ``request_post`` and
    therefore keep using the supplied writer headers. No legacy hash fallback
    exists on any error path.
    """
    injected_post = request_post is not None
    request_post = request_post or requests.post
    rows, stats = build_betwatch_fixture_rpc_rows(matches)
    stats.update(
        received_count=0,
        mapped_updated_count=0,
        linked_existing_count=0,
        inserted_new_count=0,
    )
    if stats.get("error"):
        return stats
    if not rows:
        return stats

    if observed_at is None:
        observed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    if injected_post:
        headers = writer._headers()
    else:
        headers = _runtime_service_headers()
        if headers is None:
            stats["error"] = "service_role_key_unavailable"
            return stats

    # Provider-authoritative mode owns identity for this scrape. Prevent the old
    # hash-scoped shadow stage or a staged fallback payload from being replayed.
    clear_betwatch_identity_stage()
    clear_betwatch_authoritative_payload()

    try:
        response = request_post(
            writer._rest_url("rpc/record_betwatch_fixture_batch_v2"),
            headers=headers,
            json={
                "p_observed_at": observed_at,
                "p_rows": rows,
            },
            timeout=45,
        )
        if getattr(response, "status_code", 0) != 200:
            stats["error"] = f"provider_fixture_rpc_http_{getattr(response, 'status_code', 'unknown')}"
            return stats
        payload = response.json()
        row = payload[0] if isinstance(payload, list) and payload else payload
        if not isinstance(row, Mapping):
            stats["error"] = "provider_fixture_rpc_unexpected_payload"
            return stats
        for key in (
            "received_count",
            "mapped_updated_count",
            "linked_existing_count",
            "inserted_new_count",
        ):
            stats[key] = int(row.get(key) or 0)
        if stats["received_count"] != len(rows):
            stats["error"] = "provider_fixture_rpc_incomplete_batch"
            return stats
        _install_physical_provider_context(writer, matches)
        return stats
    except Exception as exc:
        stats["error"] = str(exc)[:300]
        return stats
