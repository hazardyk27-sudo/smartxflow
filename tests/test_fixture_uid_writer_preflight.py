from __future__ import annotations

from core.fixture_uid_writer_preflight import plan_provider_first_fixture_rows
from core.hash_utils import make_match_id_hash


def _match(event_id="evt-1", home="Home FC", away="Away FC", league="League", kickoff="2026-10-06T18:00:00Z"):
    return {
        "match_id": event_id,
        "teams": {"v1": home, "v2": away},
        "league": league,
        "kickoff": kickoff,
    }


def _fixture(uid="11111111-1111-1111-1111-111111111111", home="Home FC", away="Away FC", league="League", kickoff="2026-10-06T18:00:00+00:00"):
    return {
        "fixture_uid": uid,
        "match_id_hash": make_match_id_hash(home, away, league, kickoff),
        "home_team": home,
        "away_team": away,
        "league": league,
        "kickoff_utc": kickoff,
    }


def _registry(event_id="evt-1", uid="11111111-1111-1111-1111-111111111111"):
    return {
        "source": "betwatch",
        "source_event_id": event_id,
        "fixture_uid": uid,
    }


def _status(result):
    assert result["rows"] == 1
    return result["decisions"][0].status


def test_mapped_provider_event_resolves_exact_uid():
    result = plan_provider_first_fixture_rows(
        [_match()],
        [_registry()],
        [_fixture()],
    )
    assert _status(result) == "mapped_exact"
    assert result["blocking_rows"] == 0
    assert result["safe_rows"] == 1


def test_same_provider_event_with_kickoff_drift_keeps_uid_but_blocks_cutover():
    result = plan_provider_first_fixture_rows(
        [_match(kickoff="2026-10-06T19:00:00Z")],
        [_registry()],
        [_fixture(kickoff="2026-10-06T18:00:00+00:00")],
    )
    assert _status(result) == "mapped_physical_drift"
    assert result["blocking_rows"] == 1


def test_unmapped_exact_fixture_without_provider_owner_can_be_linked():
    result = plan_provider_first_fixture_rows(
        [_match(event_id="evt-new")],
        [],
        [_fixture()],
    )
    assert _status(result) == "link_existing_unowned"
    assert result["blocking_rows"] == 0


def test_unmapped_exact_fixture_owned_by_other_event_fails_closed():
    result = plan_provider_first_fixture_rows(
        [_match(event_id="evt-new")],
        [_registry(event_id="evt-old")],
        [_fixture()],
    )
    assert _status(result) == "candidate_owned_by_other_event"
    assert result["blocking_rows"] == 1


def test_new_hash_is_classified_as_new_fixture():
    result = plan_provider_first_fixture_rows(
        [_match(event_id="evt-new")],
        [],
        [],
    )
    assert _status(result) == "new_fixture"
    assert result["blocking_rows"] == 0


def test_rematch_same_hash_different_kickoff_is_not_merged():
    old = _fixture(kickoff="2026-09-01T18:00:00+00:00")
    old_uid = old["fixture_uid"]
    result = plan_provider_first_fixture_rows(
        [_match(event_id="evt-new", kickoff="2026-10-06T18:00:00Z")],
        [_registry(event_id="evt-old", uid=old_uid)],
        [old],
    )
    assert _status(result) == "rematch_blocked_by_hash_unique"
    assert result["decisions"][0].fixture_uid == old_uid
    assert result["blocking_rows"] == 1


def test_same_provider_id_on_two_physical_matches_fails_closed():
    result = plan_provider_first_fixture_rows(
        [
            _match(event_id="evt-1", kickoff="2026-10-06T18:00:00Z"),
            _match(event_id="evt-1", kickoff="2026-10-07T18:00:00Z"),
        ],
        [],
        [],
    )
    assert result["counts"] == {"payload_provider_event_collision": 2}
    assert result["blocking_rows"] == 2


def test_two_provider_events_same_legacy_hash_in_payload_fail_closed():
    result = plan_provider_first_fixture_rows(
        [
            _match(event_id="evt-1", kickoff="2026-10-06T18:00:00Z"),
            _match(event_id="evt-2", kickoff="2026-10-07T18:00:00Z"),
        ],
        [],
        [],
    )
    assert result["counts"] == {"payload_legacy_hash_collision": 2}
    assert result["blocking_rows"] == 2


def test_orphan_provider_registry_fails_closed():
    result = plan_provider_first_fixture_rows(
        [_match()],
        [_registry()],
        [],
    )
    assert _status(result) == "orphan_registry"
    assert result["blocking_rows"] == 1


def test_missing_provider_id_fails_closed():
    result = plan_provider_first_fixture_rows(
        [_match(event_id=None)],
        [],
        [],
    )
    assert _status(result) == "missing_provider_id"
    assert result["blocking_rows"] == 1
