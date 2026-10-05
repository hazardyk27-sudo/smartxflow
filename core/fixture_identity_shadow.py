"""Fail-closed shadow binding for Fixture Identity V2.

This module is deliberately non-authoritative. It observes Betwatch ``match_id``
values, resolves the already-written legacy fixture by ``match_id_hash``, and
records the provider -> ``fixture_uid`` relationship in the shadow registry.
Nothing here is allowed to choose, merge, rewrite, or delete a production
fixture. Failures are reported as shadow telemetry and must not alter the legacy
scrape result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict, Iterable, List, Mapping, Optional, Set, Tuple

import requests

from core.fixture_identity_v2 import BETWATCH_SOURCE, extract_betwatch_identity
from core.hash_utils import make_match_id_hash

_QUERY_CHUNK = 150
_STAGE_LOCK = Lock()
_STAGE: Optional["StagedIdentityBatch"] = None
PhysicalKey = Tuple[str, str, str, str]


@dataclass
class StagedIdentityBatch:
    total_rows: int = 0
    eligible_rows: int = 0
    missing_provider_ids: int = 0
    hash_to_event_ids: Dict[str, Set[str]] = field(default_factory=dict)
    hash_to_physical_keys: Dict[str, Set[PhysicalKey]] = field(default_factory=dict)


def _normalize_kickoff(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.endswith("Z"):
        return raw[:-1] + "+00:00"
    return raw


def build_betwatch_identity_stage(matches: Iterable[Mapping[str, Any]]) -> StagedIdentityBatch:
    batch = StagedIdentityBatch()
    for match in matches or []:
        batch.total_rows += 1
        if not isinstance(match, Mapping):
            continue
        teams = match.get("teams") or {}
        if not isinstance(teams, Mapping):
            teams = {}
        home = str(teams.get("v1") or "").strip()
        away = str(teams.get("v2") or "").strip()
        league = str(match.get("league") or "").strip()
        if not home or not away:
            continue

        identity = extract_betwatch_identity(match)
        if identity is None:
            batch.missing_provider_ids += 1
            continue

        kickoff = _normalize_kickoff(match.get("kickoff"))
        match_hash = make_match_id_hash(home, away, league, kickoff)
        batch.hash_to_event_ids.setdefault(match_hash, set()).add(identity.event_id)
        batch.hash_to_physical_keys.setdefault(match_hash, set()).add(
            (league, home, away, kickoff)
        )
        batch.eligible_rows += 1
    return batch


def stage_betwatch_identity_payload(matches: Iterable[Mapping[str, Any]]) -> StagedIdentityBatch:
    """Replace the in-memory stage with the latest successfully fetched payload."""
    global _STAGE
    batch = build_betwatch_identity_stage(matches)
    with _STAGE_LOCK:
        _STAGE = batch
    return batch


def peek_safe_betwatch_event_by_hash() -> Dict[str, str]:
    """Return only payload-local hash -> event pairs with one physical fixture."""
    with _STAGE_LOCK:
        batch = _STAGE
        if batch is None:
            return {}
        result: Dict[str, str] = {}
        for match_hash, event_ids in batch.hash_to_event_ids.items():
            physical_keys = batch.hash_to_physical_keys.get(match_hash, set())
            if len(event_ids) == 1 and len(physical_keys) == 1:
                result[match_hash] = next(iter(event_ids))
        return result


def consume_betwatch_identity_stage() -> Optional[StagedIdentityBatch]:
    global _STAGE
    with _STAGE_LOCK:
        batch = _STAGE
        _STAGE = None
    return batch


def clear_betwatch_identity_stage() -> None:
    global _STAGE
    with _STAGE_LOCK:
        _STAGE = None


def _chunks(values: List[str], size: int = _QUERY_CHUNK):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _read_fixture_uid_map(writer: Any, match_hashes: List[str]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for chunk in _chunks(match_hashes):
        response = requests.get(
            writer._rest_url("fixtures"),
            headers=writer._headers(),
            params={
                "select": "match_id_hash,fixture_uid",
                "match_id_hash": f"in.({','.join(chunk)})",
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("fixtures identity lookup returned non-list payload")
        for row in payload:
            match_hash = str(row.get("match_id_hash") or "").strip()
            fixture_uid = str(row.get("fixture_uid") or "").strip()
            if match_hash and fixture_uid:
                result[match_hash] = fixture_uid
    return result


def _read_betwatch_events_by_uid(writer: Any, fixture_uids: Iterable[str]) -> Dict[str, Set[str]]:
    """Read existing Betwatch provider bindings for candidate fixture UIDs."""
    wanted = sorted({str(value or "").strip() for value in fixture_uids if str(value or "").strip()})
    result: Dict[str, Set[str]] = {}
    for chunk in _chunks(wanted):
        response = requests.get(
            writer._rest_url("fixture_source_ids"),
            headers=writer._headers(),
            params={
                "select": "fixture_uid,source_event_id",
                "source": f"eq.{BETWATCH_SOURCE}",
                "fixture_uid": f"in.({','.join(chunk)})",
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("fixture source lookup returned non-list payload")
        for row in payload:
            fixture_uid = str(row.get("fixture_uid") or "").strip()
            event_id = str(row.get("source_event_id") or "").strip()
            if fixture_uid and event_id:
                result.setdefault(fixture_uid, set()).add(event_id)
    return result


def _empty_stats() -> Dict[str, Any]:
    return {
        "attempted": False,
        "total_rows": 0,
        "eligible_rows": 0,
        "missing_provider_ids": 0,
        "hash_collision_groups": 0,
        "physical_collision_groups": 0,
        "provider_event_collision_groups": 0,
        "uid_provider_collision_groups": 0,
        "unresolved_hashes": 0,
        "submitted_bindings": 0,
        "inserted_count": 0,
        "matched_count": 0,
        "conflict_count": 0,
        "received_count": 0,
        "error": None,
    }


def flush_staged_betwatch_identity_shadow(
    writer: Any,
    *,
    observed_at: Optional[str] = None,
    logger=None,
) -> Dict[str, Any]:
    """Consume one staged Betwatch payload and record only safe shadow bindings.

    The legacy fixture writer has already run by the time this hook is called.
    Hashes with multiple provider IDs or physical keys, provider IDs resolving to
    multiple fixture UIDs, missing fixture UIDs, a UID already owned by a
    different Betwatch event, and DB identity conflicts are excluded or counted;
    none is auto-merged.
    """
    stats = _empty_stats()
    batch = consume_betwatch_identity_stage()
    if batch is None:
        return stats

    stats.update(
        attempted=True,
        total_rows=batch.total_rows,
        eligible_rows=batch.eligible_rows,
        missing_provider_ids=batch.missing_provider_ids,
    )

    try:
        safe_hash_to_event: Dict[str, str] = {}
        safe_hash_to_physical: Dict[str, PhysicalKey] = {}
        for match_hash, event_ids in batch.hash_to_event_ids.items():
            physical_keys = batch.hash_to_physical_keys.get(match_hash, set())
            if len(event_ids) != 1:
                stats["hash_collision_groups"] += 1
                continue
            if len(physical_keys) != 1:
                stats["physical_collision_groups"] += 1
                continue
            safe_hash_to_event[match_hash] = next(iter(event_ids))
            safe_hash_to_physical[match_hash] = next(iter(physical_keys))

        # Preserve only payload-local, physically unambiguous context for Part 4
        # dual-write after the stage is consumed. This context is observational;
        # registry and exact fixture checks remain mandatory before any UID tag.
        try:
            writer._fixture_identity_event_by_hash = dict(safe_hash_to_event)
            writer._fixture_identity_physical_by_hash = dict(safe_hash_to_physical)
        except Exception:
            pass

        if not safe_hash_to_event:
            return stats

        uid_map = _read_fixture_uid_map(writer, sorted(safe_hash_to_event))
        event_to_uids: Dict[str, Set[str]] = {}
        for match_hash, event_id in safe_hash_to_event.items():
            fixture_uid = uid_map.get(match_hash)
            if not fixture_uid:
                stats["unresolved_hashes"] += 1
                continue
            event_to_uids.setdefault(event_id, set()).add(fixture_uid)

        candidate_pairs: List[tuple[str, str]] = []
        for event_id, fixture_uids in event_to_uids.items():
            if len(fixture_uids) != 1:
                stats["provider_event_collision_groups"] += 1
                continue
            candidate_pairs.append((event_id, next(iter(fixture_uids))))

        existing_events_by_uid = _read_betwatch_events_by_uid(
            writer,
            (fixture_uid for _, fixture_uid in candidate_pairs),
        )

        bindings = []
        for event_id, fixture_uid in candidate_pairs:
            existing_events = existing_events_by_uid.get(fixture_uid, set())
            if existing_events and event_id not in existing_events:
                # Critical rematch guard: legacy hash reuse must never attach a
                # new physical Betwatch event to an old fixture UID.
                stats["uid_provider_collision_groups"] += 1
                continue
            bindings.append(
                {
                    "source_event_id": event_id,
                    "fixture_uid": fixture_uid,
                }
            )

        stats["submitted_bindings"] = len(bindings)
        if not bindings:
            return stats

        response = requests.post(
            writer._rest_url("rpc/record_fixture_identity_shadow_batch"),
            headers=writer._headers(),
            json={
                "p_source": BETWATCH_SOURCE,
                "p_observed_at": observed_at,
                "p_bindings": bindings,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        row = payload[0] if isinstance(payload, list) and payload else payload
        if not isinstance(row, Mapping):
            raise RuntimeError("identity shadow RPC returned unexpected payload")

        for key in ("inserted_count", "matched_count", "conflict_count", "received_count"):
            stats[key] = int(row.get(key) or 0)

        if logger:
            logger(
                "[IdentityShadow] "
                f"submitted={stats['submitted_bindings']} "
                f"inserted={stats['inserted_count']} matched={stats['matched_count']} "
                f"conflicts={stats['conflict_count']} missing_id={stats['missing_provider_ids']} "
                f"hash_collision={stats['hash_collision_groups']} "
                f"physical_collision={stats['physical_collision_groups']} "
                f"event_collision={stats['provider_event_collision_groups']} "
                f"uid_event_collision={stats['uid_provider_collision_groups']} "
                f"unresolved={stats['unresolved_hashes']}"
            )
        return stats
    except Exception as exc:
        stats["error"] = str(exc)[:300]
        if logger:
            logger(f"[IdentityShadow] WARN — shadow kayıt atlandı: {stats['error']}")
        return stats
