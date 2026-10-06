from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from core.fixture_identity_v2 import extract_betwatch_identity
from core.hash_utils import make_fixture_identity_key, make_match_id_hash


SAFE_STATUSES = {
    "mapped_exact",
    "new_fixture",
    "link_existing_unowned",
}

BLOCKING_STATUSES = {
    "missing_provider_id",
    "incomplete_physical_identity",
    "payload_provider_event_collision",
    "payload_legacy_hash_collision",
    "orphan_registry",
    "mapped_physical_drift",
    "candidate_owned_by_other_event",
    "exact_candidate_ambiguous",
    "rematch_blocked_by_hash_unique",
    "legacy_hash_collision_unowned",
    "legacy_hash_candidate_ambiguous",
}


@dataclass(frozen=True)
class WriterPreflightDecision:
    source_event_id: Optional[str]
    match_id_hash: Optional[str]
    fixture_uid: Optional[str]
    status: str
    league: str
    home: str
    away: str
    kickoff: str


def _text(value: Any) -> str:
    return str(value or "").strip()


def _match_fields(match: Mapping[str, Any]) -> Tuple[str, str, str, str]:
    teams = match.get("teams") or {}
    home = _text(teams.get("v1"))
    away = _text(teams.get("v2"))
    league = _text(match.get("league"))
    kickoff = _text(match.get("kickoff"))
    return league, home, away, kickoff


def _fixture_fields(row: Mapping[str, Any]) -> Tuple[str, str, str, str]:
    return (
        _text(row.get("league")),
        _text(row.get("home_team")),
        _text(row.get("away_team")),
        _text(row.get("kickoff_utc")),
    )


def _physical_key_from_match(match: Mapping[str, Any]):
    league, home, away, kickoff = _match_fields(match)
    return make_fixture_identity_key(home, away, league, kickoff)


def _physical_key_from_fixture(row: Mapping[str, Any]):
    league, home, away, kickoff = _fixture_fields(row)
    return make_fixture_identity_key(home, away, league, kickoff)


def _fixture_uid(row: Mapping[str, Any]) -> str:
    return _text(row.get("fixture_uid"))


def plan_provider_first_fixture_rows(
    matches: Sequence[Mapping[str, Any]],
    registry_rows: Iterable[Mapping[str, Any]],
    fixture_rows: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Classify Betwatch rows for a future provider-first fixture writer.

    This function is intentionally pure. It performs no HTTP or database writes.
    It exists to prove which live cases are safe before the legacy
    ``UNIQUE(match_id_hash)`` constraint is retired.
    """
    registry_by_event: Dict[str, str] = {}
    events_by_uid: Dict[str, Set[str]] = defaultdict(set)
    for row in registry_rows:
        if _text(row.get("source")) != "betwatch":
            continue
        event_id = _text(row.get("source_event_id"))
        uid = _fixture_uid(row)
        if event_id and uid:
            registry_by_event[event_id] = uid
            events_by_uid[uid].add(event_id)

    fixture_by_uid: Dict[str, Mapping[str, Any]] = {}
    fixtures_by_hash: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for row in fixture_rows:
        uid = _fixture_uid(row)
        match_hash = _text(row.get("match_id_hash"))
        if uid:
            fixture_by_uid[uid] = row
        if match_hash:
            fixtures_by_hash[match_hash].append(row)

    payload_event_to_physical: Dict[str, Set[Tuple[str, str, str, str]]] = defaultdict(set)
    payload_hash_to_events: Dict[str, Set[str]] = defaultdict(set)
    prepared: List[Tuple[Mapping[str, Any], Optional[str], Optional[str], Any]] = []

    for match in matches:
        identity = extract_betwatch_identity(match)
        event_id = identity.event_id if identity is not None else None
        physical_key = _physical_key_from_match(match)
        league, home, away, kickoff = _match_fields(match)
        match_hash = make_match_id_hash(home, away, league, kickoff) if home and away else None
        prepared.append((match, event_id, match_hash, physical_key))
        if event_id and physical_key:
            payload_event_to_physical[event_id].add(physical_key)
        if event_id and match_hash:
            payload_hash_to_events[match_hash].add(event_id)

    decisions: List[WriterPreflightDecision] = []

    for match, event_id, match_hash, physical_key in prepared:
        league, home, away, kickoff = _match_fields(match)

        def emit(status: str, uid: Optional[str] = None) -> None:
            decisions.append(
                WriterPreflightDecision(
                    source_event_id=event_id,
                    match_id_hash=match_hash,
                    fixture_uid=uid,
                    status=status,
                    league=league,
                    home=home,
                    away=away,
                    kickoff=kickoff,
                )
            )

        if not event_id:
            emit("missing_provider_id")
            continue
        if physical_key is None or not match_hash:
            emit("incomplete_physical_identity")
            continue
        if len(payload_event_to_physical[event_id]) != 1:
            emit("payload_provider_event_collision")
            continue
        if len(payload_hash_to_events[match_hash]) != 1:
            emit("payload_legacy_hash_collision")
            continue

        mapped_uid = registry_by_event.get(event_id)
        if mapped_uid:
            fixture = fixture_by_uid.get(mapped_uid)
            if fixture is None:
                emit("orphan_registry", mapped_uid)
                continue
            if _physical_key_from_fixture(fixture) == physical_key:
                emit("mapped_exact", mapped_uid)
            else:
                # Same provider event must keep the same UID, but changing physical
                # metadata must be reviewed before update-by-UID is activated.
                emit("mapped_physical_drift", mapped_uid)
            continue

        hash_candidates = list(fixtures_by_hash.get(match_hash, []))
        exact_candidates = [
            row for row in hash_candidates
            if _physical_key_from_fixture(row) == physical_key
        ]

        if len(exact_candidates) == 1:
            uid = _fixture_uid(exact_candidates[0])
            owners = events_by_uid.get(uid, set())
            if owners:
                emit("candidate_owned_by_other_event", uid)
            else:
                emit("link_existing_unowned", uid)
            continue
        if len(exact_candidates) > 1:
            emit("exact_candidate_ambiguous")
            continue

        if not hash_candidates:
            emit("new_fixture")
            continue

        if len(hash_candidates) > 1:
            emit("legacy_hash_candidate_ambiguous")
            continue

        uid = _fixture_uid(hash_candidates[0])
        owners = events_by_uid.get(uid, set())
        if owners:
            # This is the exact rematch case V2 must eventually support: same
            # legacy matchup fingerprint, a different physical kickoff/event.
            emit("rematch_blocked_by_hash_unique", uid)
        else:
            emit("legacy_hash_collision_unowned", uid)

    counts = Counter(decision.status for decision in decisions)
    blockers = sum(counts.get(status, 0) for status in BLOCKING_STATUSES)
    safe = sum(counts.get(status, 0) for status in SAFE_STATUSES)

    return {
        "rows": len(decisions),
        "safe_rows": safe,
        "blocking_rows": blockers,
        "counts": dict(sorted(counts.items())),
        "decisions": decisions,
    }
